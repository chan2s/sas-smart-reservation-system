"""Chatbot API.

POST /api/chatbot/ — one question in, one grounded answer out.

Access: public. Unauthenticated visitors get PUBLIC knowledge-base entries
and public facility facts only; the pipeline gates every personal-data
intent behind authentication (see services/pipeline.py). Role scoping for
authenticated users happens inside the retrieval layer, exactly like the
rest of the API — the chatbot never exposes records the caller could not
read through the regular endpoints.
"""

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from accounts.throttling import throttled_exception_handler
from .serializers import ChatRequestSerializer
from .services.pipeline import process_message


class ChatbotUserThrottle(UserRateThrottle):
    """Signed-in callers: endpoint-specific limit, cheap but not free."""

    scope = "chatbot"  # rate comes from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']


class ChatbotAnonThrottle(AnonRateThrottle):
    """Visitors: IP-based limit so public pages can't be hammered."""

    scope = "chatbot_anon"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ChatbotUserThrottle, ChatbotAnonThrottle])
def chat(request):
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        # The pipeline distinguishes visitors with None; DRF hands us an
        # AnonymousUser instance, which the ChatLog FK cannot accept.
        user = request.user if request.user.is_authenticated else None
        payload = process_message(user, serializer.validated_data["message"])
    except Exception:  # noqa: BLE001 — surfaced below as a uniform 503
        return Response(
            {
                "message": (
                    "The system is currently unable to retrieve the latest "
                    "information. Please try again later."
                ),
                "intent": "ERROR",
                "source": "fallback",
            },
            status=503,
        )

    return Response(payload)
