"""External-organization endpoints (affiliation, registration, verification).

Design rules (see the task's Security section):

* Google identifies the person; this module identifies what they represent.
  Nothing here participates in authentication — every endpoint requires an
  already-authenticated user.
* A client NEVER sends an organization id that is trusted. The organization a
  user may read or act on is always reached through
  ``request.user.organization_ref``.
* Approval is a staff action and is always recorded in the audit log.
"""

from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from accounts.models import AuditLog, Organization, User
from accounts.permissions import IsSasStaff
from accounts.serializers import (
    AffiliationUpdateSerializer,
    OrganizationListSerializer,
    OrganizationSerializer,
    OrganizationVerificationSerializer,
)

# External registration fields that may be edited by the organization's own
# members through the affiliation form.
_EDITABLE_ORGANIZATION_FIELDS = (
    "organization_name",
    "organization_type",
    "contact_person",
    "contact_email",
    "contact_number",
    "address",
    "purpose",
)


def _affiliation_payload(user) -> dict:
    """The affiliation block the frontend profile/onboarding pages render."""
    organization = user.organization_ref
    return {
        "affiliation": user.affiliation,
        "affiliation_label": user.get_affiliation_display() if user.affiliation else "",
        "has_affiliation": user.has_affiliation,
        "organization_text": user.organization,
        "organization": (
            OrganizationListSerializer(organization).data if organization else None
        ),
        "organization_verification_status": user.organization_verification_status,
        "can_create_reservations": user.can_create_reservations,
        "reservation_block_reason": user.reservation_block_reason,
    }


class MyAffiliationView(generics.GenericAPIView):
    """GET /api/auth/affiliation/ — the caller's own affiliation summary.

    Only ever returns the caller's own organization; there is no id to tamper
    with. POST sets the affiliation and, for external organizations, registers
    (or updates) the caller's organization.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AffiliationUpdateSerializer

    def get(self, request):
        return Response(_affiliation_payload(request.user))

    def post(self, request):
        serializer = AffiliationUpdateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        previous_affiliation = user.affiliation
        affiliation = data["affiliation"]

        # Once attached to an organization, a user cannot re-affiliate
        # themselves out of the external restrictions (that would be a way to
        # bypass the Pending/Rejected/Suspended block). Only SAS staff may
        # move a user off an organization.
        if user.organization_ref_id and affiliation != User.Affiliation.EXTERNAL_ORGANIZATION:
            return Response(
                {
                    "detail": (
                        "Your account is linked to an external organization. "
                        "Contact the SAS Office to change your affiliation."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            if affiliation == User.Affiliation.EXTERNAL_ORGANIZATION:
                organization = user.organization_ref
                if organization is not None and (
                    organization.verification_status
                    == Organization.VerificationStatus.SUSPENDED
                ):
                    return Response(
                        {
                            "detail": (
                                "Your organization is suspended. Contact the SAS "
                                "Office to reactivate it."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                registration_fields = {
                    field: data[field]
                    for field in _EDITABLE_ORGANIZATION_FIELDS
                    if field in data
                }

                if organization is None:
                    organization = Organization.objects.create(
                        created_by=user,
                        verification_status=Organization.VerificationStatus.PENDING,
                        **registration_fields,
                    )
                    AuditLog.record(
                        user,
                        AuditLog.Action.ORGANIZATION_REGISTERED,
                        object_type="organization",
                        object_id=organization.pk,
                        object_repr=str(organization),
                        detail="External organization registration submitted",
                        request=request,
                    )
                else:
                    # Same organization — update it in place (never a switch).
                    for field, value in registration_fields.items():
                        setattr(organization, field, value)
                    update_fields = list(registration_fields.keys())
                    # A rejected registration that is edited becomes a fresh
                    # submission and must be re-reviewed.
                    if (
                        organization.verification_status
                        == Organization.VerificationStatus.REJECTED
                    ):
                        organization.verification_status = (
                            Organization.VerificationStatus.PENDING
                        )
                        organization.review_notes = ""
                        organization.reviewed_by = None
                        organization.reviewed_at = None
                        update_fields += [
                            "verification_status",
                            "review_notes",
                            "reviewed_by",
                            "reviewed_at",
                        ]
                    if update_fields:
                        organization.save(update_fields=update_fields + ["updated_at"])
                        AuditLog.record(
                            user,
                            AuditLog.Action.ORGANIZATION_UPDATED,
                            object_type="organization",
                            object_id=organization.pk,
                            object_repr=str(organization),
                            detail="Organization details resubmitted",
                            request=request,
                        )

                user.affiliation = affiliation
                user.organization_ref = organization
                user.save(update_fields=["affiliation", "organization_ref"])
            else:
                # Internal NORSU affiliation: free-text unit/department only.
                user.affiliation = affiliation
                if "organization" in data:
                    user.organization = data["organization"]
                    user.save(update_fields=["affiliation", "organization"])
                else:
                    user.save(update_fields=["affiliation"])

        if previous_affiliation != affiliation:
            AuditLog.record(
                user,
                AuditLog.Action.AFFILIATION_CHANGED,
                object_type="user",
                object_id=user.pk,
                object_repr=user.display_name,
                detail=(
                    f"Affiliation set to {user.get_affiliation_display()}"
                    if affiliation
                    else "Affiliation cleared"
                ),
                request=request,
            )

        return Response(_affiliation_payload(user))


class OrganizationListView(generics.ListAPIView):
    """GET /api/auth/organizations/ — staff verification queue.

    Filters: ``?status=`` (verification status), ``?type=`` (organization
    type), ``?search=`` (code / name / contact).
    """

    permission_classes = [permissions.IsAuthenticated, IsSasStaff]
    serializer_class = OrganizationListSerializer

    def get_queryset(self):
        from django.db.models import Q

        qs = Organization.objects.select_related("created_by", "reviewed_by")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(verification_status=status_filter)
        type_filter = self.request.query_params.get("type")
        if type_filter:
            qs = qs.filter(organization_type=type_filter)
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(organization_code__icontains=search)
                | Q(organization_name__icontains=search)
                | Q(contact_person__icontains=search)
                | Q(contact_email__icontains=search)
            )
        return qs


class OrganizationDetailView(generics.RetrieveAPIView):
    """GET /api/auth/organizations/<pk>/ — details + members (staff only).

    Members are only reachable from here: an external user can never list
    another organization's users.
    """

    permission_classes = [permissions.IsAuthenticated, IsSasStaff]
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.select_related(
        "created_by", "reviewed_by"
    ).prefetch_related("members")


class OrganizationVerifyView(generics.GenericAPIView):
    """POST /api/auth/organizations/<pk>/verify/ — staff decision.

    ``action`` is one of approve / reject / suspend / reactivate. Approving a
    suspended organization is treated as a reactivation and audited as such.
    """

    permission_classes = [permissions.IsAuthenticated, IsSasStaff]
    serializer_class = OrganizationVerificationSerializer

    def post(self, request, pk):
        try:
            organization = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = OrganizationVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        notes = serializer.validated_data.get("notes", "")

        new_status = OrganizationVerificationSerializer.STATUS_FOR_ACTION[action]
        was_suspended = (
            organization.verification_status == Organization.VerificationStatus.SUSPENDED
        )

        organization.verification_status = new_status
        organization.review_notes = notes
        organization.reviewed_by = request.user
        from django.utils import timezone

        organization.reviewed_at = timezone.now()
        organization.save(
            update_fields=[
                "verification_status",
                "review_notes",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        if action == OrganizationVerificationSerializer.Action.REACTIVATE or (
            was_suspended and new_status == Organization.VerificationStatus.APPROVED
        ):
            audit_action = AuditLog.Action.ORGANIZATION_REACTIVATED
        else:
            audit_action = (
                OrganizationVerificationSerializer.AUDIT_ACTION_FOR_STATUS[new_status]
            )

        AuditLog.record(
            request.user,
            audit_action,
            object_type="organization",
            object_id=organization.pk,
            object_repr=str(organization),
            detail=notes or f"Status set to {organization.get_verification_status_display()}",
            request=request,
        )

        return Response(OrganizationSerializer(organization).data)
