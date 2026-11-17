"""Organization registry helpers: name normalization and de-duplicated lookup.

The registry is the single place that decides *which* organization record a
reservation belongs to. Two rules keep it trustworthy:

* Identity is ``(normalized_name, organization_type)``. Names are normalized
  the same way everywhere (case, punctuation, whitespace, common legal
  suffixes) before comparison, so "ABC School", "ABC  school" and "ABC School,
  Inc." are one organization of a given type.
* An existing record is always reused instead of creating a second one. A
  concurrent insert that loses the unique-constraint race is resolved by
  re-reading the winner rather than surfacing an error.

This module deliberately has no view/serializer dependencies so it can be used
from registration, reservation submission, and management commands alike.
"""

import re
import unicodedata

from django.db import IntegrityError, transaction

#: Trailing legal/structural words that do not identify an organization.
#: Only removed when at least one other token remains, so an organization
#: literally named "Company" is never normalized to nothing.
_IGNORED_TRAILING_WORDS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "llc",
}

NORMALIZED_NAME_MAX_LENGTH = 200


def normalize_organization_name(value: str) -> str:
    """Return the canonical identity string for an organization name.

    Unicode is NFKC-normalized and case-folded, punctuation becomes a space,
    runs of whitespace collapse, and a trailing legal suffix is dropped. The
    result is stable and safe to store in ``Organization.normalized_name``.
    """
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("&", " and ")
    # Keep letters (any script) and digits; everything else separates words.
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split(" ")
    while len(tokens) > 1 and tokens[-1] in _IGNORED_TRAILING_WORDS:
        tokens.pop()
    return " ".join(tokens)[:NORMALIZED_NAME_MAX_LENGTH]


def normalize_phone_number(value: str) -> str:
    """Canonical Philippine mobile number (``+639XXXXXXXXX``), or ``""``.

    Only used for returning-booker lookup and matching; legacy values already
    stored on reservations may use ``09…`` or ``639…`` and are matched by their
    significant digits rather than by exact string equality.
    """
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    if len(digits) == 12 and digits.startswith("63"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+63{digits[1:]}"
    if len(digits) == 10 and digits.startswith("9"):
        return f"+63{digits}"
    return ""


def phone_lookup_variants(value: str) -> list[str]:
    """Stored spellings that can represent the same phone number."""
    canonical = normalize_phone_number(value)
    if not canonical:
        return []
    national = canonical[3:]  # 9XXXXXXXXX
    return [canonical, f"0{national}", national, f"63{national}"]


def find_organization(name: str, organization_type: str):
    """Return the registered organization matching name + type, or ``None``."""
    from .models import Organization

    normalized = normalize_organization_name(name)
    if not normalized:
        return None
    return (
        Organization.objects.filter(
            normalized_name=normalized,
            organization_type=organization_type,
        )
        .order_by("id")
        .first()
    )


def resolve_organization(
    name: str,
    organization_type: str,
    *,
    create: bool = False,
    contact_person: str = "",
    contact_email: str = "",
    contact_number: str = "",
    address: str = "",
    verification_status: str | None = None,
):
    """Find the matching organization, optionally creating it once.

    Returns ``(organization, created)``. With ``create=False`` a missing record
    simply returns ``(None, False)`` — callers that must not invent an
    organization (duplicate checks, historical backfills) use that form.
    """
    from .models import Organization

    normalized = normalize_organization_name(name)
    if not normalized:
        return None, False

    existing = find_organization(name, organization_type)
    if existing is not None:
        return existing, False
    if not create:
        return None, False

    defaults = {
        "organization_name": (name or "").strip(),
        "organization_type": organization_type,
    }
    if contact_person:
        defaults["contact_person"] = contact_person
    if contact_email:
        defaults["contact_email"] = contact_email
    if contact_number:
        defaults["contact_number"] = contact_number
    if address:
        defaults["address"] = address
    if verification_status:
        defaults["verification_status"] = verification_status

    try:
        with transaction.atomic():
            return Organization.objects.create(**defaults), True
    except IntegrityError:
        # Another request created the same identity between our lookup and
        # insert. Reuse that record — never create a duplicate.
        existing = find_organization(name, organization_type)
        if existing is None:
            raise
        return existing, False


def duplicate_groups():
    """Groups of organizations sharing a normalized name across types.

    The exact ``(normalized_name, organization_type)`` pair is protected by a
    unique constraint, so the only remaining ambiguity is the same name used
    for different types. Those groups are surfaced for staff review rather
    than merged automatically: merging would move historical reservations and
    change an organization's declared type, both of which are the SAS Office's
    decision, not an automatic migration's.
    """
    from django.db.models import Count

    from .models import Organization

    return (
        Organization.objects.values("normalized_name")
        .annotate(total=Count("id"))
        .filter(total__gt=1, normalized_name__gt="")
        .order_by("normalized_name")
    )


def record_organization_reservation(
    organization,
    reservation,
    *,
    update_contact: bool = False,
) -> None:
    """Attach a submitted reservation to its organization record.

    ``last_reservation_date`` only moves forward, so importing an older
    historical reservation can never make the registry look less recent.
    Contact details are refreshed only for a trusted update (a verified
    returning booker or a newly created record); a free-text submission must
    not be able to overwrite an approved organization's official contacts.
    """
    from django.utils import timezone

    update_fields = []
    if reservation.date and (
        organization.last_reservation_date is None
        or reservation.date > organization.last_reservation_date
    ):
        organization.last_reservation_date = reservation.date
        update_fields.append("last_reservation_date")

    if update_contact:
        for field, value in (
            ("contact_person", reservation.contact_person),
            ("contact_number", reservation.contact_phone),
            ("contact_email", reservation.contact_email),
        ):
            value = (value or "").strip()
            if value and getattr(organization, field) != value:
                setattr(organization, field, value)
                update_fields.append(field)

    if update_fields:
        update_fields.append("updated_at")
        organization.save(update_fields=sorted(set(update_fields)))

    if reservation.organization_ref_id != organization.id:
        reservation.organization_ref = organization
        reservation.save(update_fields=["organization_ref"])


def link_reservation_organization(
    reservation,
    *,
    create: bool = True,
    trusted_update: bool = False,
):
    """Ensure ``reservation.organization_ref`` points at the registry record.

    External reservations are the ones that can arrive with only a free-text
    organization name. A first successful submission creates the record (with
    the representative and phone/email supplied) in the PENDING state: it is a
    real registry entry but still needs the normal SAS review before its
    members can book under it. Internal reservations already carry a validated
    managed organization, so they are only timestamped.

    Returns the organization, or ``None`` when there is nothing to link.
    """
    from .models import Organization

    organization = reservation.organization_ref
    if organization is None:
        name = (reservation.organization or "").strip()
        if not name:
            return None
        if reservation.requester_type == reservation.RequesterType.CAMPUS:
            # Never invent a campus organization from free text; internal
            # reservations are resolved server-side before they reach here.
            return None
        mapped_type = {
            "SCHOOL": Organization.OrganizationType.SCHOOL_UNIVERSITY,
            "GOVERNMENT": Organization.OrganizationType.GOVERNMENT_AGENCY,
            "PRIVATE": Organization.OrganizationType.PRIVATE_ORGANIZATION,
            "COMMUNITY": Organization.OrganizationType.COMMUNITY_ORGANIZATION,
            "NGO": Organization.OrganizationType.NGO,
            "OTHER": Organization.OrganizationType.OTHER,
        }.get(reservation.organization_type, Organization.OrganizationType.OTHER)
        organization, _created = resolve_organization(
            name,
            mapped_type,
            create=create,
            contact_person=reservation.contact_person,
            contact_email=reservation.contact_email,
            contact_number=reservation.contact_phone or "",
            address=reservation.organization_address,
            verification_status=Organization.VerificationStatus.PENDING,
        )
        if organization is None:
            return None

    record_organization_reservation(
        organization, reservation, update_contact=trusted_update
    )
    return organization


def organization_for_phone(phone: str):
    """Most recent reserving organization associated with a phone number.

    The phone is only a *lookup convenience*: nothing is returned until the
    caller proves control of the email on file with an OTP. Successful
    submissions are the only source, so abandoned/invalid attempts (which
    never create a reservation) cannot be discovered here.
    """
    from django.db.models import Q

    from reservations.models import Reservation

    variants = phone_lookup_variants(phone)
    if not variants:
        return None, None
    query = Q()
    for value in variants:
        query |= Q(contact_phone__iexact=value)
    canonical = normalize_phone_number(phone)
    if canonical:
        # Legacy rows may contain formatting characters; match the significant
        # digits as a fallback without ever using the phone as an identity key.
        query |= Q(contact_phone__endswith=canonical[-10:])
    reservation = (
        Reservation.objects.filter(query, organization__gt="")
        .select_related("organization_ref")
        .order_by("-created_at")
        .first()
    )
    if reservation is None:
        return None, None

    organization = reservation.organization_ref
    if organization is None:
        organization, _created = resolve_organization(
            reservation.organization,
            {
                "SCHOOL": "SCHOOL_UNIVERSITY",
                "GOVERNMENT": "GOVERNMENT_AGENCY",
                "PRIVATE": "PRIVATE_ORGANIZATION",
                "COMMUNITY": "COMMUNITY_ORGANIZATION",
                "NGO": "NGO",
                "OTHER": "OTHER",
            }.get(reservation.organization_type, "OTHER"),
            create=False,
        )
    return organization, reservation
