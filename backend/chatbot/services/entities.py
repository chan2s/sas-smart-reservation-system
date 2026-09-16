"""Deterministic entity extraction.

Parses dates ("today", "tomorrow", weekday names, "September 20",
"2026-09-20"), times ("2 PM", "14:00", "9:30am"), durations, reservation IDs
and equipment quantities from a normalized message. No AI libraries — plain
regex + the standard library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as time_cls, timedelta

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    # Common abbreviations.
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

RELATIVE_DAYS = {
    "today": 0, "tonight": 0, "tomorrow": 1,
    "day after tomorrow": 2,
}

_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b"
)
_DATE_DAY_MONTH_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\b"
)
_TIME_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|noon|midnight)?\b"
)
# Reservation IDs look like SAS-2026-00012 (this deployment's format) but
# older data may use other short prefixes (e.g. RSV-2026-0003) — accept both.
_RESERVATION_ID_RE = re.compile(
    r"\b([A-Z]{2,4}-\d{4}-\d{1,5})\b", re.IGNORECASE
)
_PARTIAL_ID_RE = re.compile(r"\bSAS-?\d{0,4}-?\d{0,5}\b")
_DURATION_RE = re.compile(r"\b(\d+)\s*(hours?|hrs?|h)\b|\b(\d+)\s*(minutes?|mins?)\b")
# "for 50 people", "50 participants", "capacity 50"
_PARTICIPANTS_RE = re.compile(
    r"\b(?:for|of|about|around)\s+(\d{1,5})\s*(?:people|persons|participants|attendees|guests|pax)\b"
    r"|\b(\d{1,5})\s*(?:people|persons|participants|attendees|guests|pax)\b",
    re.IGNORECASE,
)


@dataclass
class Entities:
    date: date | None = None
    date_text: str = ""  # what the user said, for echoing back
    has_date: bool = False
    start_time: time_cls | None = None
    end_time: time_cls | None = None
    has_time: bool = False
    duration_hours: float | None = None
    participants: int | None = None
    reservation_id: str | None = None
    facility_text: str = ""  # raw text around the matched facility name
    # Set by the pipeline after facility resolution (services/facilities.py).
    facility_resolved: "object | None" = None
    extra: dict = field(default_factory=dict)


def _next_weekday(today: date, weekday: int) -> date:
    """The coming weekday (not today itself)."""
    days_ahead = (weekday - today.weekday()) % 7
    days_ahead = days_ahead or 7
    return today + timedelta(days=days_ahead)


def extract_entities(message: str, today: date | None = None) -> Entities:
    today = today or date.today()
    text = re.sub(r"[^\w\s:.\-]", " ", message.lower())

    # Remove ISO dates up front so the time parser cannot misread the day
    # or month number inside "2026-09-20" as a clock time.
    text = _DATE_ISO_RE.sub(" ", text)

    entities = Entities()

    # --- ISO date (removed from `text` already; match on the original) ------
    match = _DATE_ISO_RE.search(re.sub(r"[^\w\s:.\-]", " ", message.lower()))
    if match:
        try:
            entities.date = date(int(match[1]), int(match[2]), int(match[3]))
            entities.date_text = match[0]
            entities.has_date = True
        except ValueError:
            pass

    # --- "September 20" / "sep 20th" ----------------------------------------
    if not entities.has_date:
        match = _DATE_MONTH_DAY_RE.search(text)
        if match:
            month = MONTHS[match[1]]
            day = int(match[2])
            year = today.year
            try:
                candidate = date(year, month, day)
            except ValueError:
                candidate = None
            if candidate:
                # If the date already passed this year, assume next year.
                if candidate < today:
                    try:
                        candidate = date(year + 1, month, day)
                    except ValueError:
                        candidate = None
                if candidate:
                    entities.date = candidate
                    entities.date_text = match[0]
                    entities.has_date = True

    # --- "20 September" ------------------------------------------------------
    if not entities.has_date:
        match = _DATE_DAY_MONTH_RE.search(text)
        if match:
            day = int(match[1])
            month = MONTHS[match[2]]
            year = today.year
            try:
                candidate = date(year, month, day)
            except ValueError:
                candidate = None
            if candidate:
                if candidate < today:
                    try:
                        candidate = date(year + 1, month, day)
                    except ValueError:
                        candidate = None
                if candidate:
                    entities.date = candidate
                    entities.date_text = match[0]
                    entities.has_date = True

    # --- Weekday names -------------------------------------------------------
    if not entities.has_date:
        for name, weekday in WEEKDAYS.items():
            if re.search(rf"\b{name}\b", text):
                entities.date = _next_weekday(today, weekday)
                entities.date_text = name
                entities.has_date = True
                break

    # --- Relative days --------------------------------------------------------
    if not entities.has_date:
        for phrase, offset in sorted(
            RELATIVE_DAYS.items(), key=lambda kv: -len(kv[0])
        ):
            if phrase in text:
                entities.date = today + timedelta(days=offset)
                entities.date_text = phrase
                entities.has_date = True
                break

    # --- Times ---------------------------------------------------------------
    times: list[time_cls] = []
    for match in _TIME_RE.finditer(text):
        hour = int(match[1])
        minute = int(match[2] or 0)
        meridiem = (match[3] or "").replace(".", "")
        if meridiem == "noon" and hour <= 12:
            times.append(time_cls(12, minute))
            continue
        if meridiem == "midnight":
            times.append(time_cls(0, minute))
            continue
        if meridiem in ("am", "pm"):
            if not 1 <= hour <= 12:
                continue
            if meridiem == "pm" and hour != 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            times.append(time_cls(hour, minute))
        elif ":" in match[0] and not times:
            # "14:00" style without meridiem — accept unambiguously.
            times.append(time_cls(hour % 24, minute))
        elif 6 <= hour <= 11 and not times:
            # Bare "at 9" — plausibly 9 AM in a facilities context.
            times.append(time_cls(hour, minute))

    # Ignore times that are part of the date ("september 20" -> 20 as hour? no;
    # _TIME_RE may capture the day number, e.g. "on september 20 at 2 pm" is
    # fine, but "20 september 2 pm" could double count. Keep only times that
    # follow "at"/"from"/"by"/"around" or stand alone.
    if times:
        entities.start_time = times[0]
        entities.has_time = True
        if len(times) >= 2:
            entities.end_time = times[1]

    # --- Duration ------------------------------------------------------------
    match = _DURATION_RE.search(text)
    if match:
        if match[1]:
            entities.duration_hours = float(match[1])
        elif match[3]:
            entities.duration_hours = int(match[3]) / 60.0

    # If a single time + duration -> derive end_time.
    if entities.start_time and entities.duration_hours and not entities.end_time:
        start_dt = datetime.combine(today, entities.start_time) + timedelta(
            hours=entities.duration_hours
        )
        entities.end_time = start_dt.time()

    # --- Participants ----------------------------------------------------------
    match = _PARTICIPANTS_RE.search(text)
    if match:
        entities.participants = int(match[1] or match[2])

    # --- Reservation ID --------------------------------------------------------
    match = _RESERVATION_ID_RE.search(message)
    if match:
        entities.reservation_id = match[1].upper()

    return entities
