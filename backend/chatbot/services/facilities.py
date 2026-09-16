"""Facility resolution — mapping user phrasing to Facility records.

Order of attempts (deterministic, first hit wins):
1. Exact name match (case-insensitive).
2. Alias table (facility-type abbreviations like "AVR", "MPH", plus
   lowercase/short names) seeded from FacilityType choices.
3. Unique substring match (icontains) over active facilities.
4. difflib fuzzy match with a conservative cutoff.

All matching runs against ACTIVE facilities only.
"""

from __future__ import annotations

import difflib
import re

from facilities.models import Facility

# Phrases to strip from around a facility mention to recover the bare name.
_STRIP_WORDS = {
    "the", "a", "an", "is", "are", "was", "be", "been", "at", "on", "in",
    "for", "of", "to", "about", "available", "availability", "free", "vacant",
    "booked", "reserved", "open", "closed", "tell", "me", "about", "where",
    "what", "when", "how", "rules", "schedule", "hours", "capacity",
    "tomorrow", "today", "tonight", "morning", "afternoon", "evening",
}

# Deterministic aliases: facility_type -> user-facing short names.
_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    Facility.FacilityType.AVR: ("avr", "av room", "audio visual room", "audio-visual room"),
    Facility.FacilityType.GYMNASIUM: ("gym", "gymnasium"),
    Facility.FacilityType.CAFETERIA: ("canteen", "cafeteria"),
    Facility.FacilityType.MULTI_PURPOSE: ("mph", "multi purpose hall", "multi-purpose hall", "multipurpose hall"),
    Facility.FacilityType.OUTDOOR: ("outdoor", "outdoor area", "ground", "field", "courtyard"),
}

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9\- ]*")


def _facility_aliases(facility: Facility) -> set[str]:
    """Alias strings this facility answers to (lowercase)."""
    aliases = {facility.name.lower()}
    aliases.update(_TYPE_ALIASES.get(facility.facility_type, ()))
    return aliases


def strip_facility_phrase(text: str, known_names: list[str]) -> str:
    """Best-effort removal of a facility mention from a message.

    Used to avoid treating a facility name as the *whole* question when
    detecting intents for messages like "gym rules".
    """
    cleaned = text
    for name in sorted(known_names, key=len, reverse=True):
        pattern = re.escape(name.lower())
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(
        w for w in cleaned.split() if w not in _STRIP_WORDS
    )
    return cleaned


def resolve_facility(text: str) -> tuple[Facility | None, str | None]:
    """Resolve a facility from free text.

    Returns (facility, unmatched_text). ``unmatched_text`` is the raw
    text the user wrote when no facility matched — for echo-back in the
    "facility not found" template.
    """
    if not text:
        return None, None

    lowered = text.lower().strip()
    facilities = list(Facility.objects.filter(is_active=True))

    # 1. Exact name.
    for facility in facilities:
        if facility.name.lower() == lowered:
            return facility, None

    # 2. Aliases (whole-phrase or word-boundary within the text).
    for facility in facilities:
        for alias in _facility_aliases(facility):
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, lowered):
                return facility, None

    # 3. Unique substring match of the real name inside the text.
    matches = [
        f for f in facilities
        if f.name.lower() in lowered
    ]
    if matches:
        # Longest name wins if several substring-match (e.g. "Room" matches
        # several) — but only if it is unambiguous at that length.
        matches.sort(key=lambda f: -len(f.name))
        if len(matches) == 1 or len(matches[0].name) > len(matches[1].name):
            return matches[0], None
        # Ambiguous: fall through to fuzzy matching below.

    # 4. Fuzzy match per-word against names/aliases (typo tolerance).
    words = _WORD_RE.findall(lowered)
    candidates: dict[int, float] = {}
    for facility in facilities:
        score = 0.0
        for alias in _facility_aliases(facility):
            for word in words:
                if len(word) < 4:
                    continue
                ratio = difflib.SequenceMatcher(None, word, alias).ratio()
                if ratio > score:
                    score = ratio
    # Also try the whole lowered string against names for multiword names.
    for facility in facilities:
        ratio = difflib.SequenceMatcher(None, lowered, facility.name.lower()).ratio()
        if ratio > candidates.get(facility.id, 0):
            candidates[facility.id] = ratio
        for alias in _facility_aliases(facility):
            ratio = difflib.SequenceMatcher(None, lowered, alias).ratio()
            if ratio > candidates.get(facility.id, 0):
                candidates[facility.id] = ratio

    if candidates:
        best_id = max(candidates, key=candidates.get)
        best_score = candidates[best_id]
        if best_score >= 0.75:
            facility = next(f for f in facilities if f.id == best_id)
            return facility, None

    return None, text


def facility_status_label(facility: Facility) -> str:
    return facility.get_status_display()
