"""Knowledge-base retrieval (no embeddings, no AI).

Deterministic keyword matching over published KnowledgeBaseEntry rows:

1. Keyword hits: each entry's ``keywords`` field is matched against the
   message; entries are ranked by number of distinct keyword hits, then by
   title hits, then recency.
2. Title/content fallback: icontains matching for messages like
   "what is the reservation policy".

Entries whose status is not PUBLISHED are never served. The optional
``facility`` FK allows facility-scoped entries; pass ``facility`` to include
them in scoring.
"""

from __future__ import annotations

from facilities.models import Facility

from ..models import KnowledgeBaseEntry  # noqa: F401 — re-exported for tests


def _entry_score(entry: KnowledgeBaseEntry, message: str) -> tuple[int, int]:
    """(keyword_hits, title_hits) for ranking."""
    lowered = message.lower()
    keyword_hits = sum(
        1 for kw in entry.keyword_list if kw and kw in lowered
    )
    title_hits = 0
    for word in entry.title.lower().replace(",", " ").split():
        if len(word) >= 4 and word in lowered:
            title_hits += 1
    return keyword_hits, title_hits


def search_knowledge(
    message: str,
    *,
    category: str | None = None,
    facility: Facility | None = None,
    limit: int = 3,
) -> list[KnowledgeBaseEntry]:
    """Published entries matching the message, best first."""
    qs = KnowledgeBaseEntry.objects.filter(status=KnowledgeBaseEntry.Status.PUBLISHED)
    if category:
        qs = qs.filter(category=category)

    candidates = list(qs.select_related("facility"))
    if facility is not None:
        # Facility-specific entries rank above general ones for that facility.
        def sort_key(entry):
            score = _entry_score(entry, message)
            facility_bonus = 1 if entry.facility_id == facility.id else 0
            return (facility_bonus, score[0], score[1])

        candidates.sort(key=sort_key, reverse=True)
    else:
        candidates.sort(
            key=lambda e: _entry_score(e, message), reverse=True
        )

    results = [
        e for e in candidates
        if (_entry_score(e, message) > (0, 0))
        or (facility is not None and e.facility_id == facility.id)
    ]
    return results[:limit]


def search_knowledge_for_intent(
    message: str, intent: str, facility: Facility | None = None
) -> list[KnowledgeBaseEntry]:
    """Intent-aware knowledge search.

    Maps intents to KB categories so policy questions retrieve the right
    document set without any statistical model.
    """
    from .intents import Intent

    category_map = {
        Intent.RESERVATION_POLICY: KnowledgeBaseEntry.Category.RESERVATION_POLICY,
        Intent.CANCELLATION_POLICY: KnowledgeBaseEntry.Category.CANCELLATION_POLICY,
        Intent.FACILITY_RULES: KnowledgeBaseEntry.Category.FACILITY_RULES,
        Intent.BOOKING_GUIDE: KnowledgeBaseEntry.Category.BOOKING_GUIDE,
    }
    category = category_map.get(intent)
    if category:
        results = search_knowledge(message, category=category, facility=facility)
        if results:
            return results
    return search_knowledge(message, facility=facility)
