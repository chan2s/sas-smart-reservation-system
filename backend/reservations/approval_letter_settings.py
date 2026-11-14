import tempfile
from copy import deepcopy
from pathlib import Path
from django.core.paginator import Paginator

from django.db import transaction
from django.db.models import Max
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAccountApprovedOrReadOnly, IsAdmin
from reservations.services.approval_letter_templates import (
    ALLOWED_PLACEHOLDERS,
    PLACEHOLDER_HELP,
    PLACEHOLDER_PATTERN,
)
from .models import ApprovalLetterSettings, ApprovalLetterTemplateVersion, Reservation


CONTENT_FIELDS = (
    "letter_title",
    "approval_message",
    "introductory_paragraphs",
    "instructions_template",
    "additional_content",
    "footer_disclaimer",
)
PLACEHOLDER_FIELDS = CONTENT_FIELDS + ("approval_label",)
SIGNATORY_FIELDS = (
    "authorized_signatory_name",
    "credentials",
    "designation",
    "approval_label",
)
STAFF_FIELDS = ("sas_staff_display_name", "sas_staff_designation")
SETTINGS_FIELDS = SIGNATORY_FIELDS + STAFF_FIELDS + CONTENT_FIELDS
SETTINGS_FIELDS += ("body_content",)

RICH_NODE_KEYS = {
    "doc": {"type", "content"},
    "paragraph": {"type", "attrs", "content"},
    "heading": {"type", "attrs", "content"},
    "text": {"type", "text", "marks"},
    "hardBreak": {"type"},
    "bulletList": {"type", "content"},
    "orderedList": {"type", "content"},
    "listItem": {"type", "content"},
    "reservationDetails": {"type"},
    "reservationConditions": {"type"},
    "documentMetadata": {"type"},
}


def _validate_body_content(value):
    """Validate the bounded Tiptap JSON subset accepted by the DOCX renderer."""
    errors = []
    text_size = 0
    slot_counts = {
        "documentMetadata": 0,
        "reservationDetails": 0,
        "reservationConditions": 0,
    }
    slot_order = []

    def walk(node, context, depth=0):
        nonlocal text_size
        if depth > 5 or not isinstance(node, dict):
            errors.append("The letter body contains an invalid or overly nested block.")
            return
        node_type = node.get("type")
        if node_type not in RICH_NODE_KEYS or set(node) - RICH_NODE_KEYS.get(node_type, set()):
            errors.append("The letter body contains an unsupported rich-text node or attribute.")
            return
        if context == "inline" and node_type not in {"text", "hardBreak"}:
            errors.append("Paragraphs may contain only text and line breaks.")
            return
        if context == "list" and node_type != "listItem":
            errors.append("Lists may contain only list items.")
            return
        if context == "listItem" and node_type != "paragraph":
            errors.append("List items may contain only paragraphs.")
            return
        if node_type in slot_counts:
            slot_counts[node_type] += 1
            slot_order.append(node_type)
            return

        if node_type == "text":
            text = node.get("text")
            if not isinstance(text, str):
                errors.append("Rich-text content must use plain text nodes.")
                return
            text_size += len(text)
            if len(text) > 8000:
                errors.append("A text block exceeds the maximum length.")
            unknown = sorted({
                match.group(1) for match in PLACEHOLDER_PATTERN.finditer(text)
                if match.group(1) not in ALLOWED_PLACEHOLDERS
            })
            remainder = PLACEHOLDER_PATTERN.sub("", text)
            if "{{" in remainder or "}}" in remainder:
                errors.append("Placeholders must use the supported {{name}} format.")
            elif unknown:
                errors.append("Unsupported placeholders: " + ", ".join("{{" + name + "}}" for name in unknown))
            marks = node.get("marks", [])
            if not isinstance(marks, list):
                errors.append("Text formatting is invalid.")
            else:
                for mark in marks:
                    if not isinstance(mark, dict) or mark.get("type") not in {"bold", "italic"} or set(mark) != {"type"}:
                        errors.append("Only bold and italic text formatting is supported.")
            return

        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict):
            errors.append("Paragraph attributes are invalid.")
            return
        if node_type in {"paragraph", "heading"}:
            allowed_attrs = {"spaceAfter", "textAlign"} | ({"level"} if node_type == "heading" else set())
            if set(attrs) - allowed_attrs:
                errors.append("Unsupported paragraph formatting was submitted.")
            align = attrs.get("textAlign")
            if align not in (None, "left", "center", "right", "justify"):
                errors.append("Use left, centered, right, or justified paragraph alignment.")
            spacing = attrs.get("spaceAfter", 4)
            if isinstance(spacing, bool) or not isinstance(spacing, (int, float)) or not 0 <= spacing <= 24:
                errors.append("Paragraph spacing must be between 0 and 24 points.")
            if node_type == "heading" and attrs.get("level") not in (1, 2, 3):
                errors.append("Headings may use levels 1 through 3.")
        elif attrs:
            errors.append("This list block does not accept custom attributes.")

        content = node.get("content", [])
        if not isinstance(content, list):
            errors.append("Rich-text block content must be a list.")
            return
        if len(content) > 100:
            errors.append("A rich-text block contains too many child nodes.")
            return
        child_context = {
            "doc": "block", "paragraph": "inline", "heading": "inline",
            "bulletList": "list", "orderedList": "list", "listItem": "listItem",
        }.get(node_type)
        allowed_children = {
            "doc": {
                "paragraph", "heading", "bulletList", "orderedList",
                "documentMetadata", "reservationDetails", "reservationConditions",
            },
            "bulletList": {"listItem"}, "orderedList": {"listItem"},
            "listItem": {"paragraph"},
        }
        if node_type in allowed_children and any(
            not isinstance(child, dict) or child.get("type") not in allowed_children[node_type]
            for child in content
        ):
            errors.append("Rich-text blocks are nested in an unsupported way.")
            return
        for child in content:
            walk(child, child_context or "block", depth + 1)

    walk(value, "root")
    if not isinstance(value, dict) or value.get("type") != "doc":
        errors.append("The letter body must be a structured document.")
    if isinstance(value, dict) and len(value.get("content", [])) > 100:
        errors.append("The letter body may contain at most 100 blocks.")
    if text_size > 24000:
        errors.append("The letter body exceeds the maximum text length.")
    if slot_counts["reservationDetails"] != 1:
        errors.append("Keep exactly one protected reservation details block in the letter.")
    if slot_counts["reservationConditions"] != 1:
        errors.append("Keep exactly one protected reservation conditions block in the letter.")
    if slot_counts["documentMetadata"] != 1:
        errors.append("Keep exactly one protected document reference and issue date block in the letter.")
    if slot_order != ["documentMetadata", "reservationDetails", "reservationConditions"]:
        errors.append("Keep the protected reference, reservation details, and conditions blocks in their application order.")
    if errors:
        raise serializers.ValidationError({"body_content": list(dict.fromkeys(errors))})


class ApprovalLetterSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalLetterSettings
        fields = SETTINGS_FIELDS
        extra_kwargs = {
            "letter_title": {"required": False, "allow_blank": False, "max_length": 140},
            "approval_message": {"required": False, "allow_blank": False, "max_length": 3000},
            "introductory_paragraphs": {"required": False, "max_length": 6000},
            "instructions_template": {"required": False, "max_length": 6000},
            "additional_content": {"required": False, "max_length": 6000},
            "footer_disclaimer": {"required": False, "max_length": 4000},
        }

    def validate(self, attrs):
        errors = {}
        name = attrs.get(
            "authorized_signatory_name",
            getattr(self.instance, "authorized_signatory_name", ""),
        )
        designation = attrs.get("designation", getattr(self.instance, "designation", ""))
        if not name.strip():
            errors["authorized_signatory_name"] = "Enter the authorized signatory's full name."
        if not designation.strip():
            errors["designation"] = "Enter the official designation."
        staff_name = attrs.get(
            "sas_staff_display_name", getattr(self.instance, "sas_staff_display_name", "")
        )
        staff_designation = attrs.get(
            "sas_staff_designation", getattr(self.instance, "sas_staff_designation", "")
        )
        if not staff_name.strip():
            errors["sas_staff_display_name"] = "Enter the SAS/UED staff display name."
        if not staff_designation.strip():
            errors["sas_staff_designation"] = "Enter the SAS/UED staff designation."

        title = attrs.get("letter_title", getattr(self.instance, "letter_title", ""))
        message = attrs.get("approval_message", getattr(self.instance, "approval_message", ""))
        if not title.strip():
            errors["letter_title"] = "Enter a letter title."
        if not message.strip():
            errors["approval_message"] = "Enter the approval message."

        for field in PLACEHOLDER_FIELDS:
            value = attrs.get(field, getattr(self.instance, field, "")) or ""
            unknown = sorted({
                match.group(1)
                for match in PLACEHOLDER_PATTERN.finditer(value)
                if match.group(1) not in ALLOWED_PLACEHOLDERS
            })
            remainder = PLACEHOLDER_PATTERN.sub("", value)
            if "{{" in remainder or "}}" in remainder:
                errors[field] = "Placeholders must use the supported {{name}} format."
            elif unknown:
                errors[field] = "Unsupported placeholders: " + ", ".join("{{" + item + "}}" for item in unknown)

        if errors:
            raise serializers.ValidationError(errors)
        for field in (
            "authorized_signatory_name", "designation", "credentials", "approval_label",
            "letter_title", *STAFF_FIELDS,
        ):
            if field in attrs:
                attrs[field] = attrs[field].strip()
        if not attrs.get("approval_label", getattr(self.instance, "approval_label", "Approved by:")).strip():
            attrs["approval_label"] = "Approved by:"
        elif "approval_label" in attrs:
            attrs["approval_label"] = attrs["approval_label"].strip()
        if "body_content" not in attrs and self.instance:
            body = deepcopy(self.instance.body_content or {})
            content = body.get("content", []) if isinstance(body, dict) else []
            if "letter_title" in attrs:
                heading = next((
                    node for node in content
                    if node.get("type") == "heading"
                    and node.get("attrs", {}).get("level") == 1
                ), None)
                if heading is not None:
                    heading["content"] = [{"type": "text", "text": attrs["letter_title"]}]
            if "approval_message" in attrs:
                old_message = self.instance.approval_message
                message = next((
                    node for node in content
                    if node.get("type") == "paragraph"
                    and "".join(
                        child.get("text", "") for child in node.get("content", [])
                        if child.get("type") == "text"
                    ) == old_message
                ), None)
                if message is not None:
                    message["content"] = [{"type": "text", "text": attrs["approval_message"]}]
            if body and body != self.instance.body_content:
                attrs["body_content"] = body

        body_content = attrs.get("body_content", getattr(self.instance, "body_content", None))
        if body_content is not None:
            _validate_body_content(body_content)
        return attrs


class ApprovalLetterTemplateVersionSerializer(serializers.ModelSerializer):
    modified_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalLetterTemplateVersion
        fields = ("id", "version", "configuration", "modified_by_name", "change_note", "created_at")

    def get_modified_by_name(self, obj):
        return obj.modified_by.display_name if obj.modified_by_id else "System"


def _snapshot_configuration(instance):
    return {field: getattr(instance, field) for field in SETTINGS_FIELDS}


def _save_version(instance, actor, note=""):
    last_version = ApprovalLetterTemplateVersion.objects.aggregate(value=Max("version"))["value"] or 0
    return ApprovalLetterTemplateVersion.objects.create(
        version=last_version + 1,
        configuration=_snapshot_configuration(instance),
        modified_by=actor,
        change_note=note[:180],
    )


def _admin_permissions():
    return [IsAuthenticated, IsAccountApprovedOrReadOnly, IsAdmin]


@api_view(["GET", "PATCH"])
@permission_classes(_admin_permissions())
def approval_letter_settings(request):
    """Read/update current wording and signatory configuration (administrator only)."""
    instance, _ = ApprovalLetterSettings.objects.get_or_create(pk=1)
    if request.method == "GET":
        data = ApprovalLetterSettingsSerializer(instance).data
        data["version"] = ApprovalLetterTemplateVersion.objects.aggregate(value=Max("version"))["value"] or 0
        return Response(data)

    payload = request.data.copy()
    change_note = payload.pop("change_note", "")
    with transaction.atomic():
        instance = ApprovalLetterSettings.objects.select_for_update().get(pk=1)
        serializer = ApprovalLetterSettingsSerializer(instance, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        changed = any(getattr(instance, key) != value for key, value in serializer.validated_data.items())
        serializer.save()
        version = None
        if changed:
            version = _save_version(instance, request.user, change_note or "Updated approval letter")
    data = ApprovalLetterSettingsSerializer(instance).data
    data["version"] = version.version if version else (
        ApprovalLetterTemplateVersion.objects.aggregate(value=Max("version"))["value"] or 0
    )
    return Response(data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes(_admin_permissions())
def approval_letter_template_versions(request):
    try:
        page_number = int(request.query_params.get("page", "1"))
    except (TypeError, ValueError):
        return Response({"page": "Enter a whole-number page."}, status=status.HTTP_400_BAD_REQUEST)
    if page_number < 1:
        return Response({"page": "Page number must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)
    paginator = Paginator(
        ApprovalLetterTemplateVersion.objects.select_related("modified_by").all(),
        3,
    )
    page = paginator.get_page(page_number)
    return Response({
        "results": ApprovalLetterTemplateVersionSerializer(page.object_list, many=True).data,
        "count": paginator.count,
        "page": page.number,
        "page_size": 3,
        "pages": paginator.num_pages,
    })


@api_view(["POST"])
@permission_classes(_admin_permissions())
def restore_approval_letter_template_version(request, version):
    previous = ApprovalLetterTemplateVersion.objects.filter(version=version).first()
    if previous is None:
        return Response({"detail": "Approval letter version not found."}, status=status.HTTP_404_NOT_FOUND)
    with transaction.atomic():
        instance = ApprovalLetterSettings.objects.select_for_update().get_or_create(pk=1)[0]
        serializer = ApprovalLetterSettingsSerializer(
            instance, data=previous.configuration, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        restored = _save_version(instance, request.user, f"Restored version {version}")
    data = ApprovalLetterSettingsSerializer(instance).data
    data["version"] = restored.version
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes(_admin_permissions())
def preview_approval_letter(request):
    """Render an unsaved admin draft as a PDF without touching workflow state."""
    instance, _ = ApprovalLetterSettings.objects.get_or_create(pk=1)
    serializer = ApprovalLetterSettingsSerializer(
        instance, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    raw_reservation_id = request.data.get("reservation_reference") or ""
    if not isinstance(raw_reservation_id, str):
        return Response(
            {"reservation_reference": "Enter a reservation reference as text."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reservation_id = raw_reservation_id.strip()
    if not reservation_id:
        return Response(
            {"reservation_reference": "Select an approved external reservation for the preview."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    reservations = Reservation.objects.filter(
        requester_type=Reservation.RequesterType.EXTERNAL,
        status=Reservation.Status.APPROVED,
    ).select_related("requester", "facility", "approved_by")
    if reservation_id:
        reservation = reservations.filter(reservation_id=reservation_id).first()
    if reservation is None:
        return Response(
            {"detail": "No approved external reservation was found for preview."},
            status=status.HTTP_404_NOT_FOUND,
        )

    from reservations.services.approval_documents import _build_docx, _convert_pdf

    draft = ApprovalLetterSettings(**{
        **ApprovalLetterSettingsSerializer(instance).data,
        **serializer.validated_data,
    })
    with tempfile.TemporaryDirectory(prefix="sas-approval-preview-") as temp_dir:
        directory = Path(temp_dir)
        docx_path = directory / f"{reservation.reservation_id}-preview.docx"
        _build_docx(reservation, docx_path, letter_settings=draft)
        pdf_path = _convert_pdf(docx_path, directory)
        response = HttpResponse(pdf_path.read_bytes(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="approval-preview-{reservation.reservation_id}.pdf"'
    response["X-Approval-Preview-Reservation"] = reservation.reservation_id
    return response
