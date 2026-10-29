"""Production-safe seed for the SAS RESERVE standard pricing configuration.

This command configures *rates only*. It creates/updates the rows the pricing
engine (``reservations.services.pricing``) reads, and nothing else:

* ``PricingRule`` ``FACILITY`` rows for Gymnasium and Cafeteria — ₱5,000 flat
  for the standard 8:00 AM–5:00 PM day, recorded as ``included_hours = 9``.
  The model keys facility rates by *facility type*, so the rule applies to
  every facility of that type; facility types without a rule (AVR, Outdoor,
  …) stay free and are deliberately not given one.
* ``PricingRule`` ``OVERTIME`` rows for the same two types — ₱300 per hour
  beyond the base period, using the engine's existing overtime calculation
  (``end_time - start_time`` minus the facility rule's ``included_hours``).
* The Folding Chair's ₱5.00 per-unit rate, using the existing priority in the
  engine: the item's own ``Equipment.price`` (primary) and the per-category
  ``PricingRule`` (fallback). A different non-zero production price is a
  conflict and is reported, never overwritten.
* The Sound System Operator's ₱500 flat service fee, using both existing
  mechanisms: the ``PricingRule`` ``OPERATOR`` row for the sound-system
  category, and the ``FacilityResource.operator_fee`` of sound systems
  already assigned to a facility (only where the operator is offered).

Nothing here creates facilities or equipment — inventory, quantities,
availability, users, reservations, and historical fee snapshots are left
untouched. A missing equipment item or category is reported instead of being
invented, and its category fallback is still configured when possible.

Idempotency: every write is matched on the same keys the pricing engine uses
(``fee_type`` + ``facility_type``, or ``fee_type`` + ``equipment_category``),
so a repeated run creates no duplicates and rewrites nothing that already
matches. Conflicting rates are never silently replaced; when a conflict is
found during an apply run the command finishes the safe writes, prints each
conflict, and raises ``CommandError`` so the discrepancy is visible.

Internal campus requesters remain free and external organizations are charged
the configured rates: that split lives in the pricing service, which this
command does not touch.

Usage::

    python manage.py seed_production_pricing --dry-run
    python manage.py seed_production_pricing
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from equipment.models import Equipment, EquipmentCategory, FacilityResource
from facilities.models import Facility
from reservations.models import PricingRule

#: The standard booking period is 8:00 AM–5:00 PM, i.e. nine hours.
STANDARD_INCLUDED_HOURS = Decimal("9.00")

FACILITY_RATES = (
    (Facility.FacilityType.GYMNASIUM, "Gymnasium", Decimal("5000.00")),
    (Facility.FacilityType.CAFETERIA, "Cafeteria", Decimal("5000.00")),
)

OVERTIME_RATES = (
    (Facility.FacilityType.GYMNASIUM, "Gymnasium Overtime"),
    (Facility.FacilityType.CAFETERIA, "Cafeteria Overtime"),
)
OVERTIME_UNIT_PRICE = Decimal("300.00")

FOLDING_CHAIR_NAME = "Folding Chair"
FOLDING_CHAIR_RATE = Decimal("5.00")
CHAIR_CATEGORY_NAME = "Chairs"

SOUND_CATEGORY_NAME = "Sound Systems"
OPERATOR_LABEL = "Sound System Operator"
OPERATOR_RATE = Decimal("500.00")

#: Console order for the summary.
STATUS_ORDER = ("created", "updated", "unchanged", "skipped", "missing", "conflict")
STATUS_LABEL = {
    "created": "CREATED",
    "updated": "UPDATED",
    "unchanged": "UNCHANGED",
    "skipped": "SKIPPED",
    "missing": "MISSING",
    "conflict": "CONFLICT",
}


@dataclass
class Action:
    status: str
    subject: str
    detail: str = ""


def _number(value) -> str:
    """Format a Decimal without insignificant zeros (9.00 -> 9)."""
    text = f"{Decimal(value):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class Command(BaseCommand):
    help = (
        "Create or verify the standard SAS RESERVE external-organization pricing "
        "(Gymnasium/Cafeteria PHP 5,000 per day, PHP 300 overtime per hour, "
        "Folding Chair PHP 5.00/unit, Sound System Operator PHP 500). Existing "
        "conflicting rates are "
        "reported, never overwritten. Use --dry-run to preview."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the records that would be created or updated without writing.",
        )

    def handle(self, *args, **options):
        self.dry_run = bool(options["dry_run"])
        self.actions: list[Action] = []

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run: previewing pricing changes. Nothing will be written."
                )
            )
            self.stdout.write("")
            self._seed()
        else:
            with transaction.atomic():
                self._seed()

        self._write_report()
        conflicts = [action for action in self.actions if action.status == "conflict"]
        if conflicts and not self.dry_run:
            raise CommandError(
                f"{len(conflicts)} pricing conflict(s) need manual review; "
                "existing rates were left unchanged."
            )
        return None

    # -- seeding ----------------------------------------------------------

    def _seed(self):
        for facility_type, label, price in FACILITY_RATES:
            self._ensure_rule(
                lookup={
                    "fee_type": PricingRule.FeeType.FACILITY,
                    "facility_type": facility_type,
                },
                subject=f"Facility fee | {label}",
                defaults={
                    "label": label,
                    "unit": PricingRule.Unit.FLAT,
                    "unit_price": price,
                    "included_hours": STANDARD_INCLUDED_HOURS,
                    "is_active": True,
                },
                expected={
                    "unit": PricingRule.Unit.FLAT,
                    "unit_price": price,
                    "included_hours": STANDARD_INCLUDED_HOURS,
                },
            )

        for facility_type, label in OVERTIME_RATES:
            self._ensure_rule(
                lookup={
                    "fee_type": PricingRule.FeeType.OVERTIME,
                    "facility_type": facility_type,
                },
                subject=f"Overtime fee | {label}",
                defaults={
                    "label": label,
                    "unit": PricingRule.Unit.HOUR,
                    "unit_price": OVERTIME_UNIT_PRICE,
                    "included_hours": STANDARD_INCLUDED_HOURS,
                    "is_active": True,
                },
                expected={
                    "unit": PricingRule.Unit.HOUR,
                    "unit_price": OVERTIME_UNIT_PRICE,
                },
            )

        self._seed_folding_chair()
        self._seed_sound_system_operator()

    def _seed_folding_chair(self):
        items = list(
            Equipment.objects.filter(name__iexact=FOLDING_CHAIR_NAME)
            .select_related("category")
            .order_by("id")
        )
        subject = "Equipment price | Folding Chair"

        if not items:
            category = self._category(CHAIR_CATEGORY_NAME)
            if category is None:
                self._record(
                    "missing",
                    subject,
                    "no equipment named 'Folding Chair' and no 'Chairs' category; "
                    "the PHP 5.00 rate could not be configured (no inventory was created)",
                )
                return
            self._record(
                "missing",
                subject,
                "no equipment named 'Folding Chair'; configuring the 'Chairs' "
                "category fallback instead (no inventory was created)",
            )
            self._ensure_equipment_rate(category, label=CHAIR_CATEGORY_NAME)
            return

        if len(items) > 1:
            self._record(
                "conflict",
                subject,
                f"{len(items)} equipment records share this name "
                f"(ids {', '.join(str(item.pk) for item in items)}); "
                "resolve the duplicate manually, no price was changed",
            )
            return

        item = items[0]
        subject = f"Equipment price | {item.name} (#{item.pk})"
        if item.price == FOLDING_CHAIR_RATE:
            self._record(
                "unchanged",
                subject,
                f"price is already PHP {FOLDING_CHAIR_RATE:.2f} per unit",
            )
        elif item.price == 0:
            if self.dry_run:
                self._record(
                    "updated",
                    subject,
                    f"would set the price to PHP {FOLDING_CHAIR_RATE:.2f} per unit "
                    "(no conflicting price configured)",
                )
            else:
                item.price = FOLDING_CHAIR_RATE
                item.save(update_fields=["price", "updated_at"])
                self._record(
                    "updated",
                    subject,
                    f"price set to PHP {FOLDING_CHAIR_RATE:.2f} per unit "
                    "(no conflicting price was configured)",
                )
        else:
            self._record(
                "conflict",
                subject,
                f"configured price is PHP {item.price:.2f} per unit but the "
                f"standard rate is PHP {FOLDING_CHAIR_RATE:.2f}; left unchanged",
            )

        self._ensure_equipment_rate(item.category, label=item.name)

    def _ensure_equipment_rate(self, category: EquipmentCategory, *, label: str):
        self._ensure_rule(
            lookup={
                "fee_type": PricingRule.FeeType.EQUIPMENT,
                "equipment_category": category,
            },
            subject=f"Equipment fee | {category.name}",
            defaults={
                "label": label,
                "unit": PricingRule.Unit.UNIT,
                "unit_price": FOLDING_CHAIR_RATE,
                "is_active": True,
            },
            expected={
                "unit": PricingRule.Unit.UNIT,
                "unit_price": FOLDING_CHAIR_RATE,
            },
        )

    def _seed_sound_system_operator(self):
        category = self._category(SOUND_CATEGORY_NAME)
        if category is None:
            self._record(
                "missing",
                f"Operator fee | {OPERATOR_LABEL}",
                f"no '{SOUND_CATEGORY_NAME}' equipment category; the service fee "
                "could not be configured (no category was created)",
            )
            return

        self._ensure_rule(
            lookup={
                "fee_type": PricingRule.FeeType.OPERATOR,
                "equipment_category": category,
            },
            subject=f"Operator fee | {OPERATOR_LABEL}",
            defaults={
                "label": OPERATOR_LABEL,
                "unit": PricingRule.Unit.FLAT,
                "unit_price": OPERATOR_RATE,
                "is_active": True,
            },
            expected={
                "unit": PricingRule.Unit.FLAT,
                "unit_price": OPERATOR_RATE,
            },
        )

        resources = (
            FacilityResource.objects.filter(
                equipment__category=category, is_active=True
            )
            .select_related("facility", "equipment")
            .order_by("id")
        )
        for resource in resources:
            subject = (
                f"Operator service | {resource.equipment.name} @ "
                f"{resource.facility.name} (#{resource.pk})"
            )
            if not (resource.operator_available or resource.operator_required):
                self._record(
                    "skipped",
                    subject,
                    "operator service is not offered at this facility; "
                    "its fee was left unchanged",
                )
                continue
            if resource.operator_fee == OPERATOR_RATE:
                self._record(
                    "unchanged",
                    subject,
                    f"service fee is already PHP {OPERATOR_RATE:.2f}",
                )
            elif resource.operator_fee == 0:
                if self.dry_run:
                    self._record(
                        "updated",
                        subject,
                        f"would set the service fee to PHP {OPERATOR_RATE:.2f} "
                        "(operator offered, no fee configured)",
                    )
                else:
                    resource.operator_fee = OPERATOR_RATE
                    resource.save(update_fields=["operator_fee", "updated_at"])
                    self._record(
                        "updated",
                        subject,
                        f"service fee set to PHP {OPERATOR_RATE:.2f} "
                        "(operator offered, no fee was configured)",
                    )
            else:
                self._record(
                    "conflict",
                    subject,
                    f"configured service fee is PHP {resource.operator_fee:.2f} but "
                    f"the standard rate is PHP {OPERATOR_RATE:.2f}; left unchanged",
                )

    # -- pricing rules ----------------------------------------------------

    def _ensure_rule(self, *, lookup, subject, defaults, expected):
        """Create a rate row, or verify the effective one without overwriting.

        The pricing engine uses the lowest ``id`` among *active* rows for a
        target, so that is the row compared. A different rate, unit, or
        included-hours value is a conflict: the row is reported and left alone.
        """
        rows = list(PricingRule.objects.filter(**lookup).order_by("id"))

        if not rows:
            description = self._describe(expected)
            if self.dry_run:
                self._record("created", subject, f"would create {description}")
                return
            rule = PricingRule.objects.create(**lookup, **defaults)
            self._record(
                "created", subject, f"rule #{rule.pk} - {description}"
            )
            return

        active = [row for row in rows if row.is_active]
        if not active:
            self._record(
                "conflict",
                subject,
                f"rule #{rows[0].pk} exists but is inactive, so the engine "
                "charges nothing; reactivate it in Django admin (rate unchanged)",
            )
            return

        effective = active[0]
        differences = [
            f"{field} is {self._value(getattr(effective, field))}, expected "
            f"{self._value(expected[field])}"
            for field in expected
            if getattr(effective, field) != expected[field]
        ]
        if differences:
            self._record(
                "conflict",
                subject,
                f"rule #{effective.pk}: " + "; ".join(differences) + "; left unchanged",
            )
            return

        detail = f"rule #{effective.pk} - {self._describe(expected)}"
        if len(active) > 1:
            detail += (
                f" ({len(active) - 1} additional active rule(s) target the same "
                "fee; the lowest id is effective)"
            )
        self._record("unchanged", subject, detail)

    @staticmethod
    def _value(value) -> str:
        if isinstance(value, Decimal):
            return _number(value)
        return str(value)

    def _describe(self, values: dict) -> str:
        price = Decimal(values["unit_price"])
        if values["unit"] == PricingRule.Unit.FLAT:
            parts = [f"PHP {price:,.2f} flat"]
        else:
            parts = [f"PHP {price:,.2f} per {values['unit']}"]
        if "included_hours" in values:
            parts.append(f"{_number(values['included_hours'])} included hours")
        return " | ".join(parts)

    def _category(self, name: str) -> EquipmentCategory | None:
        return (
            EquipmentCategory.objects.filter(name__iexact=name)
            .order_by("id")
            .first()
        )

    # -- reporting --------------------------------------------------------

    def _record(self, status: str, subject: str, detail: str = ""):
        self.actions.append(Action(status=status, subject=subject, detail=detail))

    def _write_report(self):
        groups: dict[str, list[Action]] = {}
        for action in self.actions:
            groups.setdefault(action.status, []).append(action)

        for status in STATUS_ORDER:
            actions = groups.get(status, [])
            if not actions:
                continue
            heading = STATUS_LABEL[status]
            self.stdout.write(self._style(status, heading))
            for action in actions:
                line = f"  {action.subject}"
                if action.detail:
                    line += f" - {action.detail}"
                self.stdout.write(self._style(status, line))
            self.stdout.write("")

        counts = Counter(action.status for action in self.actions)
        summary = ", ".join(
            f"{counts[status]} {STATUS_LABEL[status].lower()}"
            for status in STATUS_ORDER
            if counts[status]
        ) or "nothing to do"

        self.stdout.write(self.style.MIGRATE_HEADING("Summary"))
        self.stdout.write(f"  {summary}")
        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("  Dry run: no pricing records were written.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "  Applied in a single database transaction; inventory, "
                    "facilities, reservations, and fee snapshots were not touched."
                )
            )

        conflicts = groups.get("conflict", [])
        if conflicts:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    f"  {len(conflicts)} conflicting rate(s) were left unchanged "
                    "and need SAS Office review."
                )
            )

    def _style(self, status: str, text: str):
        if status == "conflict":
            return self.style.ERROR(text)
        if status in {"created", "updated"}:
            return self.style.SUCCESS(text)
        if status in {"missing", "skipped"}:
            return self.style.WARNING(text)
        return text
