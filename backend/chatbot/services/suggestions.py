"""Deterministic next-question suggestions (no AI, no ML).

Pure rule engine: given the answered intent, the detected entities, the
retrieved records (refs), and the caller's auth state, produce up to four
follow-up questions as ``{"text", "action"}`` dicts.

Design constraints (all enforced here, none probabilistic):

* Facility names come from the response's own refs (live DB rows), or from
  the facility table for generic branches — never hard-coded.
* "Can I reserve …" is only suggested for facilities the retrieval service
  confirms open for the relevant day (same business rules as the answers).
* Personal-data suggestions ("my reservations", "cancel my reservation")
  are only ever produced for authenticated callers.
* The exact question just asked is never suggested again.
* Dates ("today", "tomorrow", "September 18") are computed, never literals.
* Priority: direct action on the current result → follow-up on an entity →
  related information → general help. Candidates are emitted in that order
  and the list is truncated at four.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.utils import timezone

from . import retrieval
from .intents import Intent

_MAX_SUGGESTIONS = 4


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _date_phrase(day, today) -> str:
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    phrase = f"{day.strftime('%B')} {day.day}"
    if day.year != today.year:
        phrase += f", {day.year}"
    return phrase


def _when(phrase: str) -> str:
    """'tomorrow' vs 'on September 18' — relative days read bare."""
    return phrase if phrase in ("today", "tomorrow") else f"on {phrase}"


def _facilities_from_refs(refs: list) -> list:
    """Facility objects referenced by the response, in ref order."""
    from facilities.models import Facility

    ids: list[int] = []
    for ref in refs:
        ref_id = ref.get("id")
        if ref.get("type") == "facility" and ref_id not in ids:
            ids.append(ref_id)
    if not ids:
        return []
    by_id = {f.id: f for f in Facility.objects.filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id]


class _Availability:
    """Day-level open/closed classification via the existing retrieval
    service, cached per (facility, day) so one response's suggestions cost
    at most one query per facility."""

    def __init__(self) -> None:
        self._cache: dict = {}

    def is_open(self, facility, day) -> bool:
        key = (facility.id, day)
        if key not in self._cache:
            try:
                report = retrieval.availability_report(facility, day, None, None)
                self._cache[key] = bool(report["free_windows"]) and not report["under_maintenance"]
            except retrieval.RetrievalError:
                self._cache[key] = False
        return self._cache[key]


def _first_open_facility(facilities: list, day, avail: _Availability):
    for facility in facilities:
        if avail.is_open(facility, day):
            return facility
    return None


def build(intent: str, entities, refs: list, user) -> list[dict]:
    """Return up to four ``{"text", "action"}`` follow-up suggestions."""

    asked = (entities.extra.get("_raw_message") or "").strip()
    today = timezone.localdate()
    day = entities.date
    day_phrase = _date_phrase(day, today) if day else None
    next_day = (day or today) + timedelta(days=1)
    next_phrase = _date_phrase(next_day, today)
    facilities = _facilities_from_refs(refs)
    avail = _Availability()

    # --- Shared building blocks (deterministic phrasings) -------------------
    def reserve(name: str, phrase: str) -> tuple[str, str]:
        return (f"Can I reserve the {name} {_when(phrase)}?", Intent.MAKE_RESERVATION)

    def time_question(name: str, phrase: str) -> tuple[str, str]:
        return (f"What time is the {name} available {_when(phrase)}?", Intent.FACILITY_SCHEDULE)

    def available_on(phrase: str) -> tuple[str, str]:
        return (f"What facilities are available {_when(phrase)}?", Intent.LIST_FACILITIES)

    def is_available(name: str, phrase: str) -> tuple[str, str]:
        return (f"Is the {name} available {_when(phrase)}?", Intent.CHECK_AVAILABILITY)

    rules = ("What are the reservation rules?", Intent.RESERVATION_POLICY)
    cancel_policy = ("What is the cancellation policy?", Intent.CANCELLATION_POLICY)
    reservation_policy = ("What is the reservation policy?", Intent.RESERVATION_POLICY)
    book_how = ("How do I book a facility?", Intent.BOOKING_GUIDE)
    list_facilities = ("What facilities are available?", Intent.LIST_FACILITIES)
    register = ("How do I register?", Intent.REGISTRATION_HELP)
    login = ("How do I log in?", Intent.LOGIN_HELP)
    my_upcoming = ("Show my upcoming reservations", Intent.MY_UPCOMING_RESERVATIONS)
    my_reservations = ("Show my reservations", Intent.MY_RESERVATIONS)
    my_cancelled = ("What are my cancelled reservations?", Intent.MY_CANCELLED_RESERVATIONS)
    cancel_action = ("Cancel my reservation", Intent.CANCEL_RESERVATION)

    def facility_tomorrow(facility) -> tuple[str, str] | None:
        return is_available(facility.name, "tomorrow") if facility else None

    candidates: list[tuple[str, str]] = []
    auth = user is not None

    # --- Per-intent rule table (priority order within each intent) ----------
    if intent == Intent.CHECK_AVAILABILITY:
        facility = facilities[0] if facilities else None
        if facility is not None:
            open_day = day or today
            if avail.is_open(facility, open_day):
                if day_phrase:
                    candidates.append(reserve(facility.name, day_phrase))
                candidates.append(time_question(facility.name, day_phrase or next_phrase))
            else:
                candidates.append(available_on(day_phrase or next_phrase))
            candidates.append(is_available(facility.name, next_phrase))
        else:
            candidates.append(available_on(day_phrase or next_phrase))
        candidates.append(rules)
        if not auth:
            candidates.append(register)
        else:
            candidates.append(my_upcoming)

    elif intent == Intent.LIST_FACILITIES:
        open_ones = [f for f in facilities if avail.is_open(f, day or today)]
        if day:
            if open_ones:
                candidates.append(reserve(open_ones[0].name, day_phrase))
            if len(open_ones) > 1:
                candidates.append(time_question(open_ones[1].name, day_phrase))
            candidates.append(available_on(next_phrase))
        else:
            for facility in open_ones[:2]:
                candidates.append(is_available(facility.name, "tomorrow"))
            candidates.append(book_how)
        candidates.append(rules)
        if not auth:
            candidates.append(register)

    elif intent in (Intent.FACILITY_INFORMATION, Intent.FACILITY_SCHEDULE):
        facility = facilities[0] if facilities else None
        if facility is not None:
            candidates.append(facility_tomorrow(facility))
            if intent == Intent.FACILITY_INFORMATION:
                candidates.append((f"What are the {facility.name}'s rules?", Intent.FACILITY_RULES))
        candidates.append(rules)
        candidates.append(book_how)

    elif intent == Intent.FACILITY_RULES:
        facility = facilities[0] if facilities else None
        if facility is not None:
            candidates.append(facility_tomorrow(facility))
        candidates.append(book_how)
        candidates.append(cancel_policy)
        candidates.append(list_facilities)

    elif intent == Intent.RESERVATION_POLICY:
        candidates.append(cancel_policy)
        candidates.append(book_how)
        facility = _first_open_facility(facilities, day or today, avail)
        if facility is not None:
            candidates.append(facility_tomorrow(facility))
        else:
            candidates.append(list_facilities)
        candidates.append(my_upcoming if auth else register)

    elif intent == Intent.CANCELLATION_POLICY:
        if auth:
            candidates.append(cancel_action)
            candidates.append(my_reservations)
        candidates.append(reservation_policy)
        candidates.append(book_how)
        if not auth:
            candidates.append(login)

    elif intent == Intent.VIEW_RESERVATION:
        if auth:
            candidates.append(my_upcoming)
            candidates.append(cancel_action)
            candidates.append(my_cancelled)
            candidates.append(cancel_policy)
        else:
            candidates += [register, login, list_facilities, rules]

    elif intent in (Intent.MY_RESERVATIONS, Intent.MY_UPCOMING_RESERVATIONS,
                    Intent.MY_CANCELLED_RESERVATIONS):
        candidates.append(cancel_action)
        candidates.append(cancel_policy)
        candidates.append(list_facilities)
        candidates.append(rules)

    elif intent == Intent.CANCEL_RESERVATION:
        candidates.append(cancel_policy)
        candidates.append(my_upcoming)
        candidates.append(rules)
        candidates.append(list_facilities)

    elif intent in (Intent.MAKE_RESERVATION, Intent.BOOKING_GUIDE):
        facility = _first_open_facility(facilities, today, avail)
        if facility is not None:
            candidates.append(facility_tomorrow(facility))
        else:
            candidates.append(list_facilities)
        candidates.append(("What are the reservation requirements?", Intent.RESERVATION_POLICY))
        candidates.append(rules)
        candidates.append(my_upcoming if auth else register)

    elif intent == Intent.EQUIPMENT_AVAILABILITY:
        candidates += [list_facilities, book_how, rules]
        candidates.append(my_upcoming if auth else register)

    elif intent == Intent.MAINTENANCE_STATUS:
        candidates += [list_facilities, book_how, rules]

    elif intent == Intent.PUBLIC_ANNOUNCEMENT:
        candidates += [list_facilities, book_how, rules]
        candidates.append(my_upcoming if auth else register)

    elif intent == Intent.REGISTRATION_HELP:
        candidates += [login, book_how, list_facilities, rules]

    elif intent == Intent.LOGIN_HELP:
        if auth:
            candidates += [list_facilities, my_upcoming, rules]
        else:
            candidates += [register, book_how, list_facilities, rules]

    else:  # SYSTEM_HELP, UNKNOWN, off-topic, greetings — the starter set.
        candidates += [list_facilities, rules, book_how]
        candidates.append(my_upcoming if auth else register)

    # --- Assemble: dedupe, drop the asked question, cap at four -------------
    seen: set[str] = set()
    out: list[dict] = []
    asked_norm = _norm(asked) if asked else None
    for text, action in candidates:
        key = _norm(text)
        if not key or key in seen:
            continue
        if asked_norm and key == asked_norm:
            continue
        seen.add(key)
        out.append({"text": text, "action": action})
        if len(out) >= _MAX_SUGGESTIONS:
            break
    return out
