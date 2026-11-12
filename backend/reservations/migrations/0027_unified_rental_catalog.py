from decimal import Decimal

from django.db import migrations, models


def merge_reservation_items(ReservationItem, duplicate_equipment_id, canonical_equipment_id, db):
    """Move legacy equipment references without losing reservation snapshots.

    ReservationItem has no price or total fields: its historical request data is
    quantity, operator_requested, and returned. Financial snapshots live in
    ReservationFee and Reservation.estimated_total and must not be recalculated
    as part of catalog consolidation.
    """
    duplicate_items = ReservationItem.objects.using(db).filter(
        equipment_id=duplicate_equipment_id
    ).order_by("pk")
    for duplicate_item in duplicate_items.iterator():
        canonical_item = ReservationItem.objects.using(db).filter(
            reservation_id=duplicate_item.reservation_id,
            equipment_id=canonical_equipment_id,
        ).first()
        if canonical_item is None:
            duplicate_item.equipment_id = canonical_equipment_id
            duplicate_item.save(using=db, update_fields=["equipment"])
            continue

        # These are duplicate catalog representations of the same requested
        # equipment. Preserve all requested units, but do not touch any stored
        # financial snapshots or totals.
        canonical_item.quantity += duplicate_item.quantity
        operator_choices = (canonical_item.operator_requested, duplicate_item.operator_requested)
        if True in operator_choices:
            canonical_item.operator_requested = True
        elif False in operator_choices:
            canonical_item.operator_requested = False
        else:
            canonical_item.operator_requested = None
        # A merged row is returned only when every source row was returned.
        canonical_item.returned = canonical_item.returned and duplicate_item.returned
        canonical_item.save(
            using=db,
            update_fields=["quantity", "operator_requested", "returned"],
        )
        duplicate_item.delete(using=db)


def standardize_catalog(apps, schema_editor):
    Facility = apps.get_model("facilities", "Facility")
    Equipment = apps.get_model("equipment", "Equipment")
    MaintenanceRecord = apps.get_model("equipment", "MaintenanceRecord")
    Category = apps.get_model("equipment", "EquipmentCategory")
    Resource = apps.get_model("equipment", "FacilityResource")
    ReservationItem = apps.get_model("reservations", "ReservationItem")
    Rule = apps.get_model("reservations", "PricingRule")
    db = schema_editor.connection.alias
    Rule.objects.using(db).all().update(is_active=False)

    dorm_exists = Facility.objects.using(db).filter(name__iexact="Dorm Cafeteria").exists()
    for facility in Facility.objects.using(db).all():
        if facility.name.casefold() in {"cafeteria", "dorm cafeteria"}:
            facility.facility_type = "CAFETERIA"
            if facility.name.casefold() == "cafeteria" and dorm_exists:
                facility.is_active = False
            else:
                facility.name = "Dorm Cafeteria"
                facility.is_active = True
                dorm_exists = True
        elif facility.name.casefold() != "gymnasium":
            facility.is_active = False
        facility.save(using=db, update_fields=["name", "facility_type", "is_active"])

    allowed_categories = {}
    for name in ("LED Wall", "Sound System", "Plastic Chairs"):
        category, _ = Category.objects.using(db).get_or_create(name=name)
        category.is_active = True
        category.save(using=db, update_fields=["is_active"])
        allowed_categories[name] = category

    aliases = {
        "LED Wall": {"led wall"},
        "Sound System": {"sound system", "portable sound system", "stage sound system"},
        "Plastic Chairs": {"plastic chairs", "folding chair", "stackable chair"},
    }
    kept = set()
    source_ids = {}
    canonical_ids = {}
    for label, names in aliases.items():
        candidates = [
            item for item in Equipment.objects.using(db).filter(is_active=True).order_by("id")
            if item.name.strip().casefold() in names
        ]
        candidates.sort(key=lambda item: (item.name.strip().casefold() != label.casefold(), item.pk))
        source_ids[label] = [item.pk for item in candidates]
        if candidates:
            canonical = candidates[0]
            canonical.name = label
            canonical.category = allowed_categories[label]
            canonical.total_quantity = sum(item.total_quantity for item in candidates)
            if label == "Plastic Chairs":
                canonical.unit = "piece"
            canonical.is_active = True
            canonical.save(using=db, update_fields=["name", "category", "total_quantity", "unit", "is_active"])
            kept.add(canonical.pk)
            for duplicate in candidates[1:]:
                merge_reservation_items(
                    ReservationItem,
                    duplicate_equipment_id=duplicate.pk,
                    canonical_equipment_id=canonical.pk,
                    db=db,
                )
                MaintenanceRecord.objects.using(db).filter(equipment_id=duplicate.pk).update(
                    equipment_id=canonical.pk
                )
                duplicate.is_active = False
                duplicate.save(using=db, update_fields=["is_active"])
        else:
            canonical = Equipment.objects.using(db).create(
                name=label,
                category=allowed_categories[label],
                total_quantity=0,
                unit="piece" if label == "Plastic Chairs" else "unit",
                price=Decimal("0.00"),
                is_active=True,
            )
            kept.add(canonical.pk)
        canonical_ids[label] = canonical.pk

    Equipment.objects.using(db).exclude(pk__in=kept).update(is_active=False)
    Category.objects.using(db).exclude(name__in=allowed_categories).update(is_active=False)
    Resource.objects.using(db).exclude(equipment_id__in=kept).update(is_active=False)
    official_facilities = Facility.objects.using(db).filter(is_active=True, name__in=["Gymnasium", "Dorm Cafeteria"])
    for facility in official_facilities:
        for name, equipment_id in canonical_ids.items():
            related_ids = source_ids.get(name, [])
            source_resources = list(Resource.objects.using(db).filter(facility_id=facility.pk, equipment_id__in=related_ids))
            quantity = sum(row.quantity for row in source_resources)
            Resource.objects.using(db).update_or_create(
                facility_id=facility.pk,
                equipment_id=equipment_id,
                defaults={
                    "is_active": True,
                    "quantity": quantity,
                    "operator_available": False,
                    "operator_required": False,
                    "operator_fee": Decimal("0.00"),
                    "additional_fee": Decimal("0.00"),
                },
            )

    period_rates = (
        ("WHOLE_DAY", Decimal("5000.00")),
        ("HALF_DAY", Decimal("2500.00")),
        ("PER_HOUR", Decimal("650.00")),
    )
    for facility_type, label in (("GYMNASIUM", "Gymnasium"), ("CAFETERIA", "Dorm Cafeteria")):
        for period, price in period_rates:
            Rule.objects.using(db).update_or_create(
                fee_type="FACILITY",
                facility_type=facility_type,
                rental_period=period,
                equipment_category=None,
                defaults={
                    "label": label,
                    "unit": "hour" if period == "PER_HOUR" else "flat",
                    "unit_price": price,
                    "included_hours": Decimal("0.00"),
                    "is_active": True,
                },
            )
    # Retire the obsolete overtime and all other charge rows. Historical fee
    # snapshots are separate records and are intentionally left untouched.
    for name, price in (("LED Wall", Decimal("15000.00")), ("Sound System", Decimal("1000.00")), ("Plastic Chairs", Decimal("5.00"))):
        category = allowed_categories[name]
        if name == "LED Wall":
            for period, amount in (("WHOLE_DAY", Decimal("15000.00")), ("HALF_DAY", Decimal("7500.00"))):
                Rule.objects.using(db).update_or_create(
                    fee_type="EQUIPMENT",
                    equipment_category=category,
                    rental_period=period,
                    defaults={"label": name, "unit": "flat", "unit_price": amount, "is_active": True},
                )
            continue
        Rule.objects.using(db).update_or_create(
            fee_type="EQUIPMENT",
            equipment_category=category,
            rental_period="",
            defaults={"label": name, "unit": "unit", "unit_price": price, "is_active": True},
        )
    for name in ("LED Wall", "Sound System"):
        Rule.objects.using(db).update_or_create(
            fee_type="OPERATOR",
            equipment_category=allowed_categories[name],
            defaults={"label": f"{name} Operator", "unit": "flat", "unit_price": Decimal("500.00"), "is_active": True},
        )
    Rule.objects.using(db).update_or_create(
        fee_type="ENVIRONMENTAL",
        facility_type="",
        equipment_category=None,
        defaults={"label": "Environmental Fee", "unit": "flat", "unit_price": Decimal("500.00"), "is_active": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0011_equipmentcategory_is_active"),
        ("reservations", "0026_alter_reservation_organization_ref_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pricingrule",
            name="rental_period",
            field=models.CharField(blank=True, choices=[("WHOLE_DAY", "Whole day"), ("HALF_DAY", "Half day"), ("PER_HOUR", "Per hour")], help_text="Facility rental period covered by this official rate.", max_length=16),
        ),
        migrations.AlterField(
            model_name="pricingrule",
            name="fee_type",
            field=models.CharField(choices=[("FACILITY", "Facility fee"), ("OVERTIME", "Overtime fee"), ("EQUIPMENT", "Equipment fee"), ("OPERATOR", "Operator fee"), ("ENVIRONMENTAL", "Environmental fee")], db_index=True, max_length=16),
        ),
        migrations.AlterField(
            model_name="reservationfee",
            name="fee_type",
            field=models.CharField(choices=[("FACILITY", "Facility"), ("OVERTIME", "Overtime"), ("EQUIPMENT", "Equipment"), ("OPERATOR", "Operator"), ("ENVIRONMENTAL", "Environmental")], max_length=16),
        ),
        migrations.RunPython(standardize_catalog, migrations.RunPython.noop),
    ]
