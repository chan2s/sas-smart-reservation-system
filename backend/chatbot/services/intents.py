"""Deterministic intent detection.

Every intent is matched by an ordered rule table of keyword groups and
optional regular expressions. No AI, no embeddings: the first rule whose
keywords ALL appear in the normalized message wins. Longer, more specific
keyword sets are evaluated first so "cancellation policy" is never read as
"cancel reservation".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class Intent:
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    MAKE_RESERVATION = "MAKE_RESERVATION"
    VIEW_RESERVATION = "VIEW_RESERVATION"
    MY_RESERVATIONS = "MY_RESERVATIONS"
    CANCEL_RESERVATION = "CANCEL_RESERVATION"
    FACILITY_INFORMATION = "FACILITY_INFORMATION"
    FACILITY_RULES = "FACILITY_RULES"
    FACILITY_SCHEDULE = "FACILITY_SCHEDULE"
    LIST_FACILITIES = "LIST_FACILITIES"
    EQUIPMENT_AVAILABILITY = "EQUIPMENT_AVAILABILITY"
    MAINTENANCE_STATUS = "MAINTENANCE_STATUS"
    RESERVATION_POLICY = "RESERVATION_POLICY"
    CANCELLATION_POLICY = "CANCELLATION_POLICY"
    BOOKING_GUIDE = "BOOKING_GUIDE"
    REGISTRATION_HELP = "REGISTRATION_HELP"
    LOGIN_HELP = "LOGIN_HELP"
    PUBLIC_ANNOUNCEMENT = "PUBLIC_ANNOUNCEMENT"
    MY_UPCOMING_RESERVATIONS = "MY_UPCOMING_RESERVATIONS"
    MY_CANCELLED_RESERVATIONS = "MY_CANCELLED_RESERVATIONS"
    SYSTEM_HELP = "SYSTEM_HELP"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IntentRule:
    intent: str
    # All keywords in any one group must appear (AND); any group may match (OR).
    any_of_groups: tuple[tuple[str, ...], ...]
    # Extra regexes the message must also satisfy (None = no extra constraint).
    patterns: tuple[re.Pattern, ...] = field(default=())
    weight: int = 0  # higher = evaluated earlier


_RULES: tuple[IntentRule, ...] = (
    # --- Greeting / help (before everything, they are unambiguous) ----------
    IntentRule(
        Intent.SYSTEM_HELP,
        (("help",), ("what can you do",), ("how can you help", "what do you do")),
        weight=100,
    ),
    # --- Policies (checked before action intents: "cancellation policy"
    #     contains "cancel" but is a policy question) -------------------------
    IntentRule(
        Intent.CANCELLATION_POLICY,
        (("cancellation policy",), ("cancel", "policy"), ("cancel", "rules"), ("cancel", "fee"), ("cancel", "charge")),
        weight=95,
    ),
    IntentRule(
        Intent.RESERVATION_POLICY,
        (("reservation policy",), ("booking policy",), ("policy",), ("policies",), ("rules", "reservation"), ("requirements",)),
        weight=90,
    ),
    IntentRule(
        Intent.BOOKING_GUIDE,
        (("how do i book",), ("how do i reserve",), ("how to book",), ("how to reserve",), ("how can i book",), ("how can i reserve",), ("steps", "book"), ("book", "instructions"), ("reserve", "instructions")),
        weight=92,
    ),
    # --- Public onboarding help (weight 93: above BOOKING_GUIDE's 92 so
    #     "how do I register" wins over generic booking vocabulary; must be
    #     public so landing/login/register visitors get answers) ------------
    IntentRule(
        Intent.REGISTRATION_HELP,
        (("register",), ("registration",), ("sign up",), ("create", "account"), ("create an account",)),
        weight=93,
    ),
    IntentRule(
        Intent.LOGIN_HELP,
        (("log in",), ("log in to",), ("sign in",), ("forgot", "password"), ("forgot", "username"), ("reset", "password"), ("password",), ("can t log in",), ("cannot log in",), ("access", "reservation system")),
        weight=93,
    ),
    IntentRule(
        Intent.PUBLIC_ANNOUNCEMENT,
        (("announcement",), ("announcements",), ("any news",), ("latest news",), ("what s new",), ("advisory",)),
        weight=91,
    ),
    # --- Reservation lookups -------------------------------------------------
    IntentRule(
        Intent.VIEW_RESERVATION,
        (("reservation", "sas-"), ("reservation", "rsv-"), ("my reservation",), ("reservation status",), ("where is my",), ("details for", "reservation"), ("reservation", "details")),
        weight=88,
    ),
    IntentRule(
        Intent.MY_RESERVATIONS,
        (("my reservations",), ("my bookings",), ("my booking",), ("reservations i made",), ("bookings i made",), ("my pending",), ("my upcoming",)),
        weight=86,
    ),
    IntentRule(
        Intent.MY_UPCOMING_RESERVATIONS,
        (("upcoming", "reservations"), ("upcoming", "bookings"), ("future", "reservations"), ("reservations", "coming up")),
        weight=87,
    ),
    IntentRule(
        Intent.MY_CANCELLED_RESERVATIONS,
        (("cancelled", "reservations"), ("canceled", "reservations"), ("cancelled", "bookings"), ("my", "cancelled")),
        weight=87,
    ),
    IntentRule(
        Intent.CANCEL_RESERVATION,
        (("cancel", "reservation"), ("cancel", "booking"), ("cancel", "my"),),
        # Above VIEW_RESERVATION: "cancel my reservation SAS-..." must be a
        # cancellation request, not a lookup — "cancel" is the strong signal.
        weight=89,
    ),
    IntentRule(
        Intent.MAKE_RESERVATION,
        (("book", "facility"), ("reserve", "facility"), ("make", "reservation"), ("create", "reservation"), ("new reservation",), ("book", "room"), ("reserve", "room"), ("i want to book",), ("i want to reserve",), ("i'd like to book",), ("reserve", "for"), ("book", "for")),
        weight=84,
    ),
    # --- Facility data -------------------------------------------------------
    IntentRule(
        Intent.FACILITY_SCHEDULE,
        (("operating hours",), ("what time", "open"), ("what time", "close"), ("opening hours",), ("schedule", "facility"), ("schedule", "open"), ("hours", "open")),
        weight=82,
    ),
    IntentRule(
        Intent.FACILITY_RULES,
        (("rules",), ("rule",), ("guidelines",)),
        weight=80,
    ),
    IntentRule(
        Intent.LIST_FACILITIES,
        (("what facilities",), ("list", "facilities"), ("all facilities",), ("facilities are",), ("what rooms",), ("list", "rooms"), ("what venues",), ("available facilities",)),
        weight=78,
    ),
    IntentRule(
        Intent.FACILITY_INFORMATION,
        (("tell me about",), ("information about",), ("details about",), ("where is",), ("what is the", "capacity"), ("capacity of",), ("describe",)),
        weight=76,
    ),
    # --- Equipment / maintenance ----------------------------------------------
    IntentRule(
        Intent.EQUIPMENT_AVAILABILITY,
        (("how many",), ("equipment", "available"), ("available", "equipment"), ("microphone",), ("projector",), ("sound system",), ("speaker",), ("chair",), ("table", "available"), ("equipment", "inventory"), ("units",)),
        weight=74,
    ),
    IntentRule(
        Intent.MAINTENANCE_STATUS,
        (("maintenance",), ("under repair",), ("broken",), ("damaged",)),
        weight=72,
    ),
    # --- Availability LAST among data intents: its vocabulary ("available",
    #     "free", "reserved") overlaps everything, so it must lose ties. -----
    IntentRule(
        Intent.CHECK_AVAILABILITY,
        (("available",), ("availability",), ("is", "free"), ("vacant",), ("taken",), ("reserved", "that"), ("booked",)),
        weight=50,
    ),
)


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    confidence: str  # "high" | "medium" | "low"


def _normalize(message: str) -> str:
    """Lowercase and strip punctuation except hyphens (SAS-2026-00012)."""
    return re.sub(r"[^\w\s-]", " ", message.lower())


def _keyword_matches(keyword: str, normalized: str) -> bool:
    """Match a rule keyword against the normalized message.

    Multi-word phrases and ID prefixes ("sas-") stay substring-based, but
    single words require a word boundary — otherwise "cancel" would also
    match inside "cancelled" and steal MY_CANCELLED_RESERVATIONS questions
    ("show my cancelled reservations") as cancellation *requests*.
    """
    if " " in keyword or "-" in keyword:
        return keyword in normalized
    return re.search(rf"\b{re.escape(keyword)}\b", normalized) is not None


def detect_intent(message: str) -> IntentMatch:
    """Return the highest-weight rule whose keywords all match."""
    normalized = _normalize(message)

    best: IntentRule | None = None
    for rule in sorted(_RULES, key=lambda r: r.weight, reverse=True):
        for group in rule.any_of_groups:
            if all(_keyword_matches(kw, normalized) for kw in group):
                best = rule
                break
        if best is not None:
            break

    if best is None:
        return IntentMatch(Intent.UNKNOWN, confidence="low")

    if best.intent in (Intent.SYSTEM_HELP, Intent.LIST_FACILITIES, Intent.MAINTENANCE_STATUS):
        return IntentMatch(best.intent, confidence="high")
    if len(normalized.split()) >= 3:
        return IntentMatch(best.intent, confidence="high")
    return IntentMatch(best.intent, confidence="medium")
