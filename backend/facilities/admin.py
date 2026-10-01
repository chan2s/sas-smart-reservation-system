from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from equipment.models import Equipment, FacilityResource
from reservations.models import PricingRule

from .models import Facility, FacilityImage, OperatingHour


class OperatingHourInline(admin.TabularInline):
    model = OperatingHour
    extra = 0


class FacilityResourceInline(admin.TabularInline):
    """Assign the resources/equipment that belong to this facility.

    This is the facility-side view of the relationship; the same rows are
    editable from the equipment side (Equipment admin). No code change is
    needed to add or move a resource between facilities.
    """

    model = FacilityResource
    extra = 0
    autocomplete_fields = ("equipment",)
    fields = (
        "equipment",
        "quantity",
        "status",
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
        "display_order",
        "is_active",
    )


class FacilityImageInline(admin.TabularInline):
    """Multiple images per facility, edited right on the Facility page.

    ``extra = 3`` gives the administrator room to add several images in one
    pass. The primary image is shown first by the model ordering, and
    ``is_primary`` / ``order`` let the admin choose the cover image.
    """

    model = FacilityImage
    extra = 3
    fields = ("image", "is_primary", "order")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "facility_type",
        "capacity",
        "seating_type",
        "built_in_seats",
        "status",
        "is_active",
        "manage_equipment_link",
    )
    list_filter = ("facility_type", "seating_type", "status")
    search_fields = ("name", "location")
    # ``seating_type`` / ``built_in_seats`` / ``built_ins`` are plain model
    # fields, so they are editable on the change form. ``built_ins`` expects a
    # JSON list of tokens, e.g. ["tables", "chairs", "projector"].
    inlines = [FacilityImageInline, FacilityResourceInline, OperatingHourInline]

    # ------------------------------------------------------------------
    # Manage Equipment
    # ------------------------------------------------------------------

    def get_urls(self):
        """Add the per-facility "Manage Equipment" page to the admin URLs."""
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/manage-equipment/",
                self.admin_site.admin_view(self.manage_equipment),
                name="facilities_facility_manage_equipment",
            ),
        ]
        return custom + urls

    @admin.display(description="Equipment & resources")
    def manage_equipment_link(self, obj):
        """Changelist shortcut straight to this facility's assignment page."""
        url = reverse("admin:facilities_facility_manage_equipment", args=[obj.pk])
        return format_html('<a class="button" href="{}">Manage Equipment</a>', url)

    def manage_equipment(self, request, object_id):
        """One page to assign/unassign resources for a facility.

        The administrator sees every equipment item, ticked when it is a
        resource of this facility. Saving adds the newly ticked items and
        removes the ones that were unticked — the database relationship is the
        single source of truth the reservation form reads from. Per-resource
        quantity, availability, and fees are edited on the assignment's own
        admin page (linked from each row), so this page stays a simple
        checklist.
        """
        facility = get_object_or_404(Facility, pk=object_id)
        assignments = {
            row.equipment_id: row
            for row in FacilityResource.objects.filter(facility=facility).select_related(
                "equipment__category"
            )
        }
        equipments = list(
            Equipment.objects.select_related("category").order_by(
                "category__name", "name"
            )
        )

        if request.method == "POST":
            return self._handle_manage_equipment_post(request, facility, assignments)

        rows = [
            {
                "equipment": equipment,
                "assignment": assignments.get(equipment.id),
                "assigned": equipment.id in assignments,
            }
            for equipment in equipments
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": f"Manage equipment — {facility.name}",
            "facility": facility,
            "rows": rows,
            "assigned_count": sum(1 for row in rows if row["assigned"]),
            # Read-only reminder that facility pricing stays separate from the
            # per-resource equipment/service fees.
            "rates": PricingRule.objects.filter(
                facility_type=facility.facility_type,
                fee_type__in=(
                    PricingRule.FeeType.FACILITY,
                    PricingRule.FeeType.OVERTIME,
                ),
            ).order_by("fee_type"),
            "opts": self.model._meta,
        }
        return TemplateResponse(
            request, "admin/facilities/facility/manage_equipment.html", context
        )

    def _handle_manage_equipment_post(self, request, facility, assignments):
        """Apply adds/removes, then return to the page with a summary message."""

        def page():
            return redirect(
                "admin:facilities_facility_manage_equipment", facility.pk
            )

        # Single-row quick actions (the [Add] / [Remove] buttons).
        add_id = request.POST.get("add")
        if add_id:
            equipment = get_object_or_404(Equipment, pk=add_id)
            row, created = FacilityResource.objects.get_or_create(
                facility=facility,
                equipment=equipment,
                defaults={"quantity": 0, "status": FacilityResource.Status.AVAILABLE},
            )
            if not created and not row.is_active:
                row.is_active = True
                row.save(update_fields=["is_active", "updated_at"])
                created = True
            messages.success(
                request,
                (
                    f"{equipment.name} was added to {facility.name}."
                    if created
                    else f"{equipment.name} is already assigned to {facility.name}."
                ),
            )
            return page()

        remove_id = request.POST.get("remove")
        if remove_id:
            row = FacilityResource.objects.filter(
                facility=facility, equipment_id=remove_id
            ).first()
            if row is not None:
                name = row.equipment.name
                row.delete()
                messages.success(
                    request, f"{name} was removed from {facility.name}."
                )
            return page()

        # Checklist save: ticked equipment is assigned, unticked is removed.
        if "equipment" in request.POST or "_save" in request.POST:
            selected = set()
            for value in request.POST.getlist("equipment"):
                try:
                    selected.add(int(value))
                except (TypeError, ValueError):
                    continue
            created = 0
            reactivated = 0
            removed = 0
            with transaction.atomic():
                for equipment in Equipment.objects.all():
                    row = assignments.get(equipment.id)
                    if equipment.id in selected:
                        if row is None:
                            FacilityResource.objects.create(
                                facility=facility, equipment=equipment
                            )
                            created += 1
                        elif not row.is_active:
                            row.is_active = True
                            row.save(update_fields=["is_active", "updated_at"])
                            reactivated += 1
                    elif row is not None:
                        row.delete()
                        removed += 1
            if created or reactivated or removed:
                messages.success(
                    request,
                    (
                        f"{facility.name} resources updated — "
                        f"{created} added, {reactivated} restored, {removed} removed."
                    ),
                )
            else:
                messages.info(request, "No resource changes were made.")
            return page()

        messages.warning(request, "Nothing to do — no resource selection was sent.")
        return page()
