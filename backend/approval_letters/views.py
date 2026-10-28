"""Approval-letter API endpoints.

Access model:

* The active position holder and administrators
  see all letters. The signatory's account is module-scoped: every other
  management surface refuses it, so this is its only working module.
* A requester sees only letters issued for their OWN reservations — enforced
  in the queryset AND re-checked on every detail/download, so a crafted id
  from another user's letter returns 404 like any other missing object.
* Approval is restricted server-side to the active position holder,
  re-checked by the service under a row lock;
  frontend checks are cosmetic.
* Finalized PDF/DOCX files exist only for signed letters, so a pending letter
  has nothing to leak: downloads 404 until signing, and the preview is always
  rendered visibly unsigned.
"""

import logging
from io import BytesIO

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsAccountApprovedOrReadOnly,
    IsApprovalSignatory,
    IsSasStaff,
)

from .documents import render_letter_pdf
from .models import ApprovalLetter
from .serializers import (
    ApprovalLetterPreviewSerializer,
    ApprovalLetterSerializer,
)
from .services import LetterSignError, retry_email, sign_letter

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class IsApprovalLetterWorkspaceOrRequesterDownload(BasePermission):
    """Allow the approver workspace and requesters' own finalized downloads."""

    message = {
        "detail": "Only the designated approver may access the approval-letter workspace.",
        "code": "approval_letter_workspace_forbidden",
    }

    def has_permission(self, request, view):
        user = request.user
        if getattr(user, "is_admin", False) or getattr(
            user, "is_authorized_letter_approver", False
        ):
            return True
        return bool(
            getattr(user, "role", None) == user.Role.REQUESTER
            and getattr(view, "action", None) in ("download_pdf", "download_docx")
        )


def _attachment_response(file_field, content_type: str) -> FileResponse:
    filename = file_field.name.rsplit("/", 1)[-1]
    response = FileResponse(default_storage.open(file_field.name, "rb"), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ApprovalLetterViewSet(viewsets.ReadOnlyModelViewSet):
    """List / retrieve / preview / download / sign / retry approval letters."""

    permission_classes = [
        IsAuthenticated,
        IsAccountApprovedOrReadOnly,
        IsApprovalLetterWorkspaceOrRequesterDownload,
    ]
    serializer_class = ApprovalLetterSerializer

    def get_queryset(self):
        user = self.request.user
        # Expiration first, mirroring the reservations view: a stale PENDING
        # reservation must never back a signable letter.
        from reservations.services import expiration

        expiration.expire_overdue_reservations()

        queryset = ApprovalLetter.objects.select_related(
            "reservation", "reservation__facility", "reservation__requester", "signatory"
        )
        if user.is_admin or getattr(user, "is_authorized_letter_approver", False):
            pass
        elif self.action in ("sign", "approve") and user.is_sas_staff:
            # Let the approval actions reach their server-side authorization
            # check so unauthorized staff receive 403, without granting
            # list/detail use.
            pass
        elif self.action == "retry_email" and user.is_sas_staff:
            # SAS staff may retry delivery for an already-signed letter; the
            # action still rechecks signed state and email outcome under lock.
            pass
        elif user.is_sas_staff:
            # General staff and administrators do not get access to the
            # position holder's review workspace by virtue of staff role.
            queryset = queryset.none()
        else:
            queryset = queryset.filter(reservation__requester=user)

        params = self.request.query_params
        # ``status`` accepts one status or a comma-separated set
        # ("SIGNED,SENT,EMAIL_FAILED") so the dashboard's Signed tab covers
        # every post-signature state in one request.
        letter_status = params.get("status")
        if letter_status:
            statuses = [s.strip() for s in letter_status.split(",") if s.strip()]
            queryset = queryset.filter(status__in=statuses)
        reservation = params.get("reservation")
        if reservation:
            queryset = queryset.filter(reservation__pk=reservation)
        search = (params.get("search") or "").strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(letter_id__icontains=search)
                | Q(reservation__reservation_id__icontains=search)
                | Q(reservation__event_name__icontains=search)
                | Q(requester_name__icontains=search)
            )
        return queryset

    # -- Signatory actions -------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[
            IsAuthenticated,
            IsAccountApprovedOrReadOnly,
            IsApprovalSignatory,
        ],
    )
    def sign(self, request, pk=None):
        """Apply the test signature. Designated signatory only (server-checked)."""
        letter = self.get_object()
        try:
            letter = sign_letter(letter, request.user)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except LetterSignError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:  # render/storage failures roll back signing atomically
            logger.exception("Approval-letter signing failed for letter id %s.", pk)
            return Response(
                {
                    "detail": (
                        "The documents could not be finalized. No signature was "
                        "applied; please retry after the issue is resolved."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ApprovalLetterSerializer(letter, context={"request": request}).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[
            IsAuthenticated,
            IsAccountApprovedOrReadOnly,
            IsApprovalSignatory,
        ],
    )
    def approve(self, request, pk=None):
        """Approve a pending letter (explicit designated-signatory action).

        The approval and the existing test-signature step are the same
        server-side transition: the letter records the approving account and
        timestamp, becomes ``SIGNED``, and the finalized documents are
        generated. Accepting both action names keeps the existing signatory
        workflow intact while giving the module its explicit "Approve Letter"
        operation. It never auto-approves anything and never touches the
        reservation's status.
        """
        return self.sign(request, pk)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[
            IsAuthenticated,
            IsAccountApprovedOrReadOnly,
            IsSasStaff,
        ],
        url_path="retry-email",
    )
    def retry_email(self, request, pk=None):
        """Retry a failed signed-letter email. Administrator or SAS staff."""
        letter = self.get_object()
        try:
            letter = retry_email(letter, request.user)
        except LetterSignError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApprovalLetterSerializer(letter, context={"request": request}).data)

    # -- Documents ----------------------------------------------------------

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """Readable letter content for the in-app document preview."""
        letter = self.get_object()
        return Response(ApprovalLetterPreviewSerializer.from_letter(letter))

    @action(detail=True, methods=["get"], url_path="download/pdf")
    def download_pdf(self, request, pk=None):
        """Download the SIGNED PDF. 404 for a pending letter (nothing final)."""
        letter = self.get_object()
        if not letter.has_signed_pdf:
            raise NotFound("The signed PDF is not available yet.")
        return _attachment_response(letter.pdf_file, PDF_CONTENT_TYPE)

    @action(detail=True, methods=["get"], url_path="download/docx")
    def download_docx(self, request, pk=None):
        """Download the signed DOCX (when one was generated)."""
        letter = self.get_object()
        if not letter.has_signed_docx:
            raise NotFound("The DOCX version is not available.")
        return _attachment_response(letter.docx_file, DOCX_CONTENT_TYPE)

    @action(detail=True, methods=["get"], url_path="preview/pdf")
    def preview_pdf(self, request, pk=None):
        """Inline PDF preview (rendered on demand for pending letters).

        Pending letters stream a freshly rendered, VISIBLY UNSIGNED copy; a
        signed letter streams its stored finalized file. Not an attachment —
        the SPA fetches it as a blob for the embedded viewer.
        """
        letter = self.get_object()
        if letter.has_signed_pdf:
            response = FileResponse(
                default_storage.open(letter.pdf_file.name, "rb"),
                content_type=PDF_CONTENT_TYPE,
            )
        else:
            pdf_bytes = render_letter_pdf(letter, signed=False)
            response = FileResponse(BytesIO(pdf_bytes), content_type=PDF_CONTENT_TYPE)
        response["Content-Disposition"] = f'inline; filename="{letter.letter_id}.pdf"'
        return response
