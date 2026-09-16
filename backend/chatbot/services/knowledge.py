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

import re

from facilities.models import Facility

from ..models import KnowledgeBaseEntry  # noqa: F401 — re-exported for tests

# Too generic to discriminate between documents; matched keywords from this
# set would make every English sentence hit every entry.
_STOPWORDS = frozenset({
    "i", "me", "my", "we", "us", "you", "your", "it", "its",
    "is", "are", "was", "were", "be", "been", "am",
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "with", "by", "from", "as",
    "do", "does", "did", "can", "could", "will", "would", "should",
    "what", "when", "where", "who", "how", "why", "which",
    "if", "that", "this", "there", "here", "about", "after", "before",
})


def _keyword_pattern(kw: str) -> re.Pattern[str]:
    """Word-boundary pattern tolerant of simple singular/plural forms.

    "announcement" matches "announcements", "facility" matches
    "facilities", but "book" does NOT match "booking" — the optional
    suffix only covers plurals, not other derivations.
    """
    stem = kw
    if stem.endswith("ies") and len(stem) > 4:
        stem = stem[:-3] + "y"
    elif stem.endswith("s") and not stem.endswith("ss") and len(stem) > 3:
        stem = stem[:-1]
    return re.compile(rf"\b{re.escape(stem)}(?:s|es|ies)?\b")


def _entry_score(entry: KnowledgeBaseEntry, message: str) -> tuple[int, int]:
    """(keyword_hits, title_hits) for ranking.

    Single-word keywords match on word boundaries (so "is" cannot match
    inside "this"), and common English stop words are ignored entirely —
    otherwise nearly every sentence matches nearly every entry via words
    like "what" or "is".
    """
    lowered = message.lower()
    keyword_hits = 0
    for kw in entry.keyword_list:
        if not kw:
            continue
        kw = kw.lower()
        if len(kw) < 3 or kw in _STOPWORDS:
            continue
        if " " in kw or "-" in kw:
            if kw in lowered:
                keyword_hits += 1
        elif _keyword_pattern(kw).search(lowered):
            keyword_hits += 1
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
    viewer_is_authenticated: bool = True,
    viewer_is_admin: bool = False,
    limit: int = 3,
    require_keyword_hit: bool = False,
) -> list[KnowledgeBaseEntry]:
    """Published entries matching the message, best first.

    Visibility is enforced here — the single choke point every knowledge
    lookup flows through — so an unauthenticated visitor can never retrieve
    AUTHENTICATED or ADMIN content no matter which keywords they guess.

    ``require_keyword_hit`` (used for unscoped fallback searches) demands a
    real keywords-field hit, so generic words like "what" matching an entry
    title cannot surface an unrelated document.
    """
    qs = KnowledgeBaseEntry.objects.filter(status=KnowledgeBaseEntry.Status.PUBLISHED)
    if viewer_is_admin:
        pass  # Admins may see everything.
    elif viewer_is_authenticated:
        qs = qs.exclude(visibility=KnowledgeBaseEntry.Visibility.ADMIN)
    else:
        qs = qs.filter(visibility=KnowledgeBaseEntry.Visibility.PUBLIC)

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

    if require_keyword_hit:
        results = [e for e in candidates if _entry_score(e, message)[0] > 0]
    else:
        results = [
            e for e in candidates
            if (_entry_score(e, message) > (0, 0))
            or (facility is not None and e.facility_id == facility.id)
        ]
    return results[:limit]


def search_knowledge_for_intent(
    message: str,
    intent: str,
    facility: Facility | None = None,
    *,
    viewer_is_authenticated: bool = True,
    viewer_is_admin: bool = False,
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
        Intent.REGISTRATION_HELP: KnowledgeBaseEntry.Category.REGISTRATION_HELP,
        Intent.LOGIN_HELP: KnowledgeBaseEntry.Category.LOGIN_HELP,
        Intent.PUBLIC_ANNOUNCEMENT: KnowledgeBaseEntry.Category.ANNOUNCEMENT,
    }
    scope = {
        "viewer_is_authenticated": viewer_is_authenticated,
        "viewer_is_admin": viewer_is_admin,
    }
    category = category_map.get(intent)
    if category:
        results = search_knowledge(message, category=category, facility=facility, **scope)
        if results:
            return results
    return search_knowledge(message, facility=facility, **scope)
