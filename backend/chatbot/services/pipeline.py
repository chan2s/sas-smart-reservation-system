"""The chatbot pipeline.

    message → normalize → intent detection → entity extraction
            → live DB retrieval and/or knowledge search
            → template rendering (data-filled, deterministic)
            → response + log

The LLM-free equivalent of "grounded generation": every value rendered into
the response comes from a database record, a knowledge-base entry, or a
business rule. When retrieval fails to find anything relevant, a fixed
fallback is returned — the pipeline never invents content.
"""

from __future__ import annotations

import logging
import re
import time as time_module
from datetime import date as date_cls, datetime, time as time_cls, timedelta

from django.utils import timezone

from facilities.models import Facility

from . import retrieval, templates
from .entities import Entities, extract_entities
from .facilities import resolve_facility
from .intents import Intent, detect_intent
from .knowledge import search_knowledge_for_intent
from ..models import ChatLog
from reservations.models import Reservation

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = Reservation.ACTIVE_STATUSES


def _fmt_date(d: date_cls) -> str:
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _fmt_time(t: time_cls) -> str:
    hour = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    minute = f":{t.minute:02d}" if t.minute else ""
    return f"{hour}{minute} {meridiem}"


def _render_reservation_row(r) -> str:
    return (
        f"• {r.reservation_id} — \"{r.event_name}\" · {r.facility.name} · "
        f"{_fmt_date(r.date)} · {retrieval._fmt_time(r.start_time)}–"
        f"{retrieval._fmt_time(r.end_time)} · {r.get_status_display()}"
    )


def _as_response(
    message: str,
    intent: str,
    confidence: str,
    source: str,
    entities: Entities,
    refs: list,
    started: float,
    user,
    error: str = "",
) -> dict:
    latency = int((time_module.perf_counter() - started) * 1000)
    ChatLog.objects.create(
        user=user,
        question=entities.extra.get("_raw_message", ""),
        intent=intent,
        confidence=confidence,
        entities=_serializable_entities(entities),
        source=source,
        retrieved_refs=refs,
        response=message,
        latency_ms=latency,
        error=error,
    )
    return {
        "message": message,
        "intent": intent,
        "confidence": confidence,
        "source": source,
        "data": {"entities": _serializable_entities(entities), "refs": refs},
    }


def _serializable_entities(entities: Entities) -> dict:
    return {
        "date": entities.date.isoformat() if entities.date else None,
        "date_text": entities.date_text,
        "has_time": entities.has_time,
        "start_time": entities.start_time.isoformat() if entities.start_time else None,
        "end_time": entities.end_time.isoformat() if entities.end_time else None,
        "reservation_id": entities.reservation_id,
        "participants": entities.participants,
    }


def _render_conflicts(conflicts: list) -> str:
    parts = []
    for r in conflicts:
        parts.append(
            f"\"{r.event_name}\" from {retrieval._fmt_time(r.start_time)} to "
            f"{retrieval._fmt_time(r.end_time)}"
        )
    return "; ".join(parts)


def _render_free_windows(windows: list[dict]) -> str:
    return ", ".join(f"{w['start']}–{w['end']}" for w in windows) or "none found"


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

def _handle_check_availability(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    if not entities.facility_resolved:
        if entities.facility_text:
            names = ", ".join(f.name for f in retrieval.all_facilities())
            return (
                templates.FACILITY_NOT_FOUND.format(
                    facility_name=entities.facility_text, facility_names=names
                ),
                "fallback",
                [],
            )
        return (
            "Which facility would you like me to check? For example: "
            + ", ".join(f.name for f in retrieval.all_facilities())
            + ".",
            "fallback",
            [],
        )

    facility = entities.facility_resolved
    if not entities.has_date:
        return (
            "Which date should I check for the "
            f"{facility.name}? (e.g. \"tomorrow\", \"September 20\", \"2026-09-20\")",
            "fallback",
            [],
        )

    try:
        if entities.has_time:
            start = entities.start_time
            end = entities.end_time or (
                datetime.combine(entities.date, start) + timedelta(hours=1)
            ).time()
            report = retrieval.availability_report(facility, entities.date, start, end)
        else:
            report = retrieval.availability_report(facility, entities.date, None, None)
    except retrieval.RetrievalError:
        return templates.DB_UNAVAILABLE, "fallback", []

    if report["kind"] == "window":
        if report["under_maintenance"]:
            return (
                templates.UNAVAILABLE_MAINTENANCE.format(
                    facility_name=facility.name, date=_fmt_date(report["date"])
                ),
                "database",
                [_ref_facility(facility)],
            )
        oh = report.get("operating_hours")
        if not report["within_hours"] and oh and oh.get("open") and oh.get("close"):
            return (
                templates.OUTSIDE_HOURS.format(
                    facility_name=facility.name,
                    date=_fmt_date(report["date"]),
                    day=report["date"].strftime("%A"),
                    open_time=retrieval._fmt_time(_parse_hhmm(oh["open"])),
                    close_time=retrieval._fmt_time(_parse_hhmm(oh["close"])),
                    start_time=retrieval._fmt_time(report["start"]),
                    end_time=retrieval._fmt_time(report["end"]),
                ),
                "database",
                [_ref_facility(facility)],
            )
        if report["conflicts"]:
            conflict = report["conflicts"][0]
            conflict_window = (
                f"{retrieval._fmt_time(conflict.start_time)} to "
                f"{retrieval._fmt_time(conflict.end_time)}"
            )
            template = (
                templates.UNAVAILABLE_CONFLICT
                if conflict.event_name
                else templates.UNAVAILABLE_CONFLICT_NO_EVENT
            )
            return (
                template.format(
                    facility_name=facility.name,
                    date=_fmt_date(report["date"]),
                    start_time=retrieval._fmt_time(report["start"]),
                    end_time=retrieval._fmt_time(report["end"]),
                    event_name=conflict.event_name or "an existing booking",
                    conflict_window=conflict_window,
                ),
                "database",
                [_ref_facility(facility), _ref_reservation(conflict)],
            )
        return (
            templates.AVAILABLE.format(
                facility_name=facility.name,
                date=_fmt_date(report["date"]),
                start_time=retrieval._fmt_time(report["start"]),
                end_time=retrieval._fmt_time(report["end"]),
            ),
            "database",
            [_ref_facility(facility)],
        )

    # Whole-day report.
    if report["under_maintenance"]:
        return (
            templates.UNAVAILABLE_MAINTENANCE.format(
                facility_name=facility.name, date=_fmt_date(report["date"])
            ),
            "database",
            [_ref_facility(facility)],
        )
    if not report["free_windows"]:
        return (
            templates.FACILITY_CLOSED.format(
                facility_name=facility.name,
                day=report["date"].strftime("%A"),
            ),
            "database",
            [_ref_facility(facility)],
        )
    if report["conflicts"] and len(report["free_windows"]) <= 2:
        return (
            templates.AVAILABLE_PARTIAL.format(
                facility_name=facility.name,
                date=_fmt_date(report["date"]),
                conflicts=_render_conflicts(report["conflicts"]),
                free_windows=_render_free_windows(report["free_windows"]),
            ),
            "database",
            [_ref_facility(facility)]
            + [_ref_reservation(r) for r in report["conflicts"]],
        )
    return (
        templates.AVAILABLE_NO_TIME.format(
            facility_name=facility.name, date=_fmt_date(report["date"])
        )
        + f" Free windows: {_render_free_windows(report['free_windows'])}.",
        "database",
        [_ref_facility(facility)]
        + [_ref_reservation(r) for r in report["conflicts"]],
    )


def _parse_hhmm(value: str) -> time_cls:
    hour, minute = value.split(":")
    return time_cls(int(hour), int(minute))


def _handle_facility_information(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    if not entities.facility_resolved:
        return (
            "Which facility would you like to know about? I know about: "
            + ", ".join(f.name for f in retrieval.all_facilities())
            + ".",
            "fallback",
            [],
        )
    profile = retrieval.facility_profile(entities.facility_resolved)
    facility = profile["facility"]
    message = templates.FACILITY_INFO.format(
        facility_name=facility.name,
        facility_type=profile["type_label"],
        location=facility.location or "Not recorded",
        capacity=facility.capacity,
        status=profile["status_label"],
        description=f"\n{facility.description}" if facility.description else "",
    )
    return message, "database", [_ref_facility(facility)]


def _handle_facility_rules(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    if not entities.facility_resolved:
        return (
            "Which facility's rules? I know about: "
            + ", ".join(f.name for f in retrieval.all_facilities())
            + ".",
            "fallback",
            [],
        )
    facility = entities.facility_resolved
    profile = retrieval.facility_profile(facility)
    if profile["rules"]:
        return (
            templates.FACILITY_RULES.format(
                facility_name=facility.name,
                rules="\n".join(f"• {rule}" for rule in profile["rules"]),
            ),
            "database",
            [_ref_facility(facility)],
        )
    # Fall back to knowledge-base facility rules.
    entries = search_knowledge_for_intent(raw, Intent.FACILITY_RULES, facility)
    if entries:
        entry = entries[0]
        return (
            templates.POLICY_ANSWER.format(content=entry.content)
            + templates.POLICY_SOURCE.format(title=entry.title),
            "knowledge",
            [_ref_kb(entry)],
        )
    return (
        templates.FACILITY_NO_RULES.format(facility_name=facility.name),
        "fallback",
        [],
    )


def _handle_facility_schedule(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    if not entities.facility_resolved:
        return (
            "Which facility's schedule? I know about: "
            + ", ".join(f.name for f in retrieval.all_facilities())
            + ".",
            "fallback",
            [],
        )
    facility = entities.facility_resolved
    profile = retrieval.facility_profile(facility)
    return (
        templates.SCHEDULE.format(
            facility_name=facility.name,
            hours="\n".join(profile["hours_lines"]),
        ),
        "database",
        [_ref_facility(facility)],
    )


def _handle_list_facilities(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    facilities = retrieval.all_facilities()
    if not facilities:
        return templates.NOT_FOUND, "fallback", []

    # "What facilities are available tomorrow?" — a cross-facility
    # availability question. Answer per-facility for the extracted date.
    if entities.has_date:
        lines = []
        refs: list = []
        for f in facilities:
            try:
                report = retrieval.availability_report(f, entities.date, None, None)
            except retrieval.RetrievalError:
                return templates.DB_UNAVAILABLE, "fallback", []
            refs.append(_ref_facility(f))
            if report["under_maintenance"]:
                lines.append(f"• {f.name} — under maintenance")
            elif not report["free_windows"]:
                lines.append(f"• {f.name} — closed")
            else:
                windows = _render_free_windows(report["free_windows"])
                booked = " booked" if report["conflicts"] else " completely free"
                lines.append(f"• {f.name} — available {windows}{booked}")
        return (
            f"Facility availability on {_fmt_date(entities.date)}:\n"
            + "\n".join(lines),
            "database",
            refs,
        )

    lines = []
    for f in facilities:
        lines.append(
            f"• {f.name} ({f.get_facility_type_display()}, capacity {f.capacity}) — "
            f"{f.get_status_display()}"
        )
    return (
        templates.LIST_FACILITIES.format(facilities="\n".join(lines)),
        "database",
        [_ref_facility(f) for f in facilities],
    )


def _handle_my_reservations(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    rows = retrieval.user_reservations(user)
    if not rows:
        return templates.MY_RESERVATIONS_EMPTY, "database", []
    return (
        templates.MY_RESERVATIONS.format(
            reservations="\n".join(_render_reservation_row(r) for r in rows)
        ),
        "database",
        [_ref_reservation(r) for r in rows],
    )


def _handle_view_reservation(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    reservation_id = entities.reservation_id
    if not reservation_id:
        match = re.search(r"SAS[- ]?\d{0,4}[- ]?\d{0,5}", raw, re.IGNORECASE)
        if match:
            return templates.RESERVATION_ID_INCOMPLETE, "fallback", []
        return templates.RESERVATION_NOT_FOUND, "fallback", []

    reservation = retrieval.find_reservation_by_id(user, reservation_id)
    if reservation is None:
        # Does it exist at all (staff-only visibility check)?
        from reservations.models import Reservation as R

        exists = R.objects.filter(reservation_id=reservation_id).exists()
        if exists:
            return templates.RESERVATION_FORBIDDEN, "database", []
        return templates.RESERVATION_NOT_FOUND, "fallback", []

    return (
        templates.RESERVATION_FOUND.format(
            reservation_id=reservation.reservation_id,
            event_name=reservation.event_name,
            facility_name=reservation.facility.name,
            date=_fmt_date(reservation.date),
            day=reservation.date.strftime("%A"),
            start_time=retrieval._fmt_time(reservation.start_time),
            end_time=retrieval._fmt_time(reservation.end_time),
            status=reservation.get_status_display(),
        ),
        "database",
        [_ref_reservation(reservation)],
    )


def _handle_make_reservation(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    # Read-only chatbot: guide, plus a grounded availability check when the
    # user included a facility and date.
    if entities.facility_resolved and entities.has_date:
        message, source, refs = _handle_check_availability(user, entities, raw)
        if source == "database":
            return (
                templates.MAKE_RESERVATION_GUIDE + "\n\n" + message,
                "hybrid",
                refs,
            )
    return templates.MAKE_RESERVATION_GUIDE, "help", []


def _handle_cancel_reservation(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    # Read-only chatbot: point at the user's matching reservation + policy.
    reservation = None
    if entities.reservation_id:
        reservation = retrieval.find_reservation_by_id(user, entities.reservation_id)
    elif entities.facility_resolved:
        matches = [
            r for r in retrieval.user_reservations(user, limit=20)
            if r.facility_id == entities.facility_resolved.id
            and r.status in _ACTIVE_STATUSES
        ]
        if entities.has_date:
            matches = [r for r in matches if r.date == entities.date]
        if len(matches) == 1:
            reservation = matches[0]
    if reservation is None:
        mine = [
            r for r in retrieval.user_reservations(user, limit=20)
            if r.status in _ACTIVE_STATUSES
        ]
        if len(mine) == 1:
            reservation = mine[0]
    if reservation is None:
        return templates.CANCEL_GUIDE_NO_MATCH, "fallback", []
    return (
        templates.CANCEL_RESERVATION_GUIDE.format(
            reservation_id=reservation.reservation_id,
            policy_excerpt=retrieval.cancellation_policy_excerpt(),
        ),
        "database",
        [_ref_reservation(reservation)],
    )


def _handle_equipment_availability(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    from equipment.models import Equipment

    target_date = entities.date or timezone.localdate()
    start = entities.start_time
    end = entities.end_time or (
        datetime.combine(target_date, start) + timedelta(hours=1)
    ).time() if start else None

    rows = retrieval.equipment_availability(target_date, start, end)
    if not rows:
        return templates.EQUIPMENT_NONE, "database", []

    # Try to narrow to equipment mentioned in the message.
    lowered = raw.lower()
    mentioned = [
        row for row in rows
        if row["equipment"].name.lower() in lowered
        or any(
            word in lowered
            for word in row["equipment"].name.lower().split()
            if len(word) >= 5
        )
    ]
    if entities.extra.get("category_word"):
        mentioned = [
            row for row in rows
            if row["equipment"].category.name.lower().startswith(
                entities.extra["category_word"]
            )
        ]
    rows = mentioned or rows
    if len(rows) > 6:
        rows = rows[:6]

    lines = [
        templates.EQUIPMENT_AVAILABLE.format(
            name=row["equipment"].name,
            available=row["available"],
            total=row["total"],
            unit=row["equipment"].unit,
        )
        for row in rows
    ]
    when = (
        f" on {_fmt_date(target_date)}"
        + (
            f" from {retrieval._fmt_time(start)} to {retrieval._fmt_time(end)}"
            if start and end
            else ""
        )
    )
    return (
        f"Equipment availability{when}:\n" + "\n".join(f"• {line}" for line in lines),
        "database",
        [_ref_equipment(row["equipment"]) for row in rows],
    )


def _handle_maintenance_status(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    records = retrieval.open_maintenance_records()
    if not records:
        return templates.MAINTENANCE_NONE, "database", []
    lines = [
        f"• {rec.equipment.name} — {rec.get_issue_type_display()} "
        f"(reported {rec.created_at.strftime('%B %d, %Y').replace(' 0', ' ')})"
        for rec in records
    ]
    return (
        templates.MAINTENANCE_OPEN.format(items="\n".join(lines)),
        "database",
        [_ref_equipment(rec.equipment) for rec in records],
    )


def _handle_policy(user, entities: Entities, raw: str, intent: str) -> tuple[str, str, list]:
    entries = search_knowledge_for_intent(raw, intent, entities.facility_resolved)
    if not entries:
        return templates.NOT_FOUND, "fallback", []
    entry = entries[0]
    return (
        templates.POLICY_ANSWER.format(content=entry.content)
        + templates.POLICY_SOURCE.format(title=entry.title),
        "knowledge",
        [_ref_kb(entry)],
    )


def _handle_help(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    return templates.HELP, "help", []


def _handle_booking_guide(user, entities: Entities, raw: str) -> tuple[str, str, list]:
    """'How do I book…' — answer from the knowledge base's booking guide."""
    return _handle_policy(user, entities, raw, Intent.BOOKING_GUIDE)


# ---------------------------------------------------------------------------
# Facility resolution glue
# ---------------------------------------------------------------------------

def _resolve_facility_entities(message: str, entities: Entities) -> None:
    """Populate entities.facility_resolved / facility_text from the message."""
    facility, unmatched = resolve_facility(message)
    entities.facility_resolved = facility
    if facility is not None:
        entities.facility_text = facility.name
    else:
        # Echo back a plausible short phrase rather than the whole message.
        text = (unmatched or "").strip()
        if len(text) > 60:
            text = text[:57] + "…"
        entities.facility_text = text


# ---------------------------------------------------------------------------
# Reference helpers
# ---------------------------------------------------------------------------

def _ref_facility(facility: Facility) -> dict:
    return {"type": "facility", "id": facility.id, "name": facility.name}


def _ref_reservation(reservation) -> dict:
    return {
        "type": "reservation",
        "id": reservation.id,
        "reservation_id": reservation.reservation_id,
    }


def _ref_equipment(equipment) -> dict:
    return {"type": "equipment", "id": equipment.id, "name": equipment.name}


def _ref_kb(entry) -> dict:
    return {"type": "knowledge_base", "id": entry.id, "title": entry.title}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_HANDLERS = {
    Intent.CHECK_AVAILABILITY: _handle_check_availability,
    Intent.FACILITY_INFORMATION: _handle_facility_information,
    Intent.FACILITY_RULES: _handle_facility_rules,
    Intent.FACILITY_SCHEDULE: _handle_facility_schedule,
    Intent.LIST_FACILITIES: _handle_list_facilities,
    Intent.MY_RESERVATIONS: _handle_my_reservations,
    Intent.VIEW_RESERVATION: _handle_view_reservation,
    Intent.MAKE_RESERVATION: _handle_make_reservation,
    Intent.CANCEL_RESERVATION: _handle_cancel_reservation,
    Intent.EQUIPMENT_AVAILABILITY: _handle_equipment_availability,
    Intent.MAINTENANCE_STATUS: _handle_maintenance_status,
    Intent.BOOKING_GUIDE: _handle_booking_guide,
}


def process_message(user, message: str) -> dict:
    """Process one chat message and return the API response payload."""
    started = time_module.perf_counter()
    raw = (message or "").strip()

    if not raw:
        return _as_response(
            templates.UNKNOWN_INTENT, Intent.UNKNOWN, "low", "fallback",
            Entities(), [], started, user,
        )

    match = detect_intent(raw)
    entities = extract_entities(raw)
    _resolve_facility_entities(raw, entities)
    entities.extra["_raw_message"] = raw

    handler = _HANDLERS.get(match.intent)

    try:
        if match.intent == Intent.SYSTEM_HELP:
            message_out, source, refs = _handle_help(user, entities, raw)
        elif _is_greeting(raw):
            message_out, source, refs = templates.WELCOME, "help", []
        elif match.intent == Intent.RESERVATION_POLICY:
            message_out, source, refs = _handle_policy(user, entities, raw, Intent.RESERVATION_POLICY)
        elif match.intent == Intent.CANCELLATION_POLICY:
            message_out, source, refs = _handle_policy(user, entities, raw, Intent.CANCELLATION_POLICY)
        elif match.intent == Intent.UNKNOWN:
            message_out, source, refs = _out_of_scope_or_unknown(raw)
        elif handler is not None:
            message_out, source, refs = handler(user, entities, raw)
        else:
            message_out, source, refs = _out_of_scope_or_unknown(raw)
    except Exception as exc:  # noqa: BLE001 — never leak internals to users
        logger.exception("Chatbot pipeline error")
        message_out, source, refs = templates.DB_UNAVAILABLE, "fallback", []
        _as_response(
            message_out, match.intent, match.confidence, source, entities,
            refs, started, user, error=str(exc)[:500],
        )
        raise

    return _as_response(
        message_out, match.intent, match.confidence, source, entities,
        refs, started, user,
    )


def _out_of_scope_or_unknown(raw: str) -> tuple[str, str, list]:
    """Distinguish off-topic questions from unrecognized system questions."""
    system_words = {
        "facility", "facilities", "room", "reserve", "reservation", "book",
        "booking", "available", "availability", "schedule", "hours", "open",
        "close", "equipment", "maintenance", "cancel", "cancellation",
        "policy", "policies", "capacity", "gym", "gymnasium", "cafeteria",
        "avr", "canteen", "mic", "microphone", "projector", "chair", "table",
        "status", "approve", "pending", "approved", "sas",
    }
    lowered = raw.lower()
    if any(word in lowered for word in system_words):
        return templates.UNKNOWN_INTENT, "fallback", []
    return templates.OUT_OF_SCOPE, "fallback", []


_GREETING_RE = re.compile(
    r"^(hi|hello|hey|good\s*(morning|afternoon|evening)|greetings|yo)\b", re.IGNORECASE
)


def _is_greeting(raw: str) -> bool:
    """Short greetings get the welcome message rather than a fallback."""
    return bool(_GREETING_RE.match(raw)) and len(raw.split()) <= 4
