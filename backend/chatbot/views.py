"""Chatbot API.

POST /api/chatbot/ — one question in, one grounded answer out.

Access: any authenticated user (requester, staff, or admin). All role
scoping happens inside the retrieval layer, exactly like the rest of the
API — the chatbot never exposes records the caller could not read through
the regular endpoints.
"""

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from accounts.throttling import throttled_exception_handler
from .serializers import ChatRequestSerializer
from .services.pipeline import process_message


class ChatbotThrottle(UserRateThrottle):
    """Endpoint-specific limit: chat is cheap but not free."""

    scope = "chatbot"  # rate comes from REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ChatbotThrottle])
def chat(request):
    serializer = ChatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        payload = process_message(request.user, serializer.validated_data["message"])
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
