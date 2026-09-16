from django.conf import settings
from django.db import models

from facilities.models import Facility


class KnowledgeBaseEntry(models.Model):
    """A curated, system-approved document for the chatbot.

    Static/semi-static knowledge only: policies, FAQs, booking guides,
    facility rules. Dynamic data (reservations, availability, maintenance)
    is NEVER stored here — it is always queried live from the source tables,
    so nothing in this table can go stale.
    """

    class Category(models.TextChoices):
        RESERVATION_POLICY = "RESERVATION_POLICY", "Reservation Policy"
        CANCELLATION_POLICY = "CANCELLATION_POLICY", "Cancellation Policy"
        FACILITY_RULES = "FACILITY_RULES", "Facility Rules"
        BOOKING_GUIDE = "BOOKING_GUIDE", "Booking Instructions"
        FAQ = "FAQ", "Frequently Asked Questions"
        GENERAL = "GENERAL", "General Information"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    category = models.CharField(max_length=32, choices=Category.choices)
    title = models.CharField(max_length=200)
    content = models.TextField()
    # Comma/space-separated keywords used by the retrieval service for
    # deterministic keyword matching (no embeddings, no AI).
    keywords = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma or space separated keywords for matching user questions.",
    )
    # Optional facility scope, e.g. facility-specific rules.
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="knowledge_entries",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PUBLISHED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]
        indexes = [
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip().lower() for k in self.keywords.replace(",", " ").split() if k.strip()]


class ChatLog(models.Model):
    """Append-only log of chatbot interactions for debugging and monitoring.

    Stores what the pipeline did (intent, entities, retrieval refs, latency)
    but never sensitive personal information: the raw question is kept for
    debugging, and reservation references are limited to IDs.
    """

    class Source(models.TextChoices):
        DATABASE = "database", "Live database"
        KNOWLEDGE = "knowledge", "Knowledge base"
        HYBRID = "hybrid", "Database + knowledge base"
        HELP = "help", "Help/capabilities"
        FALLBACK = "fallback", "Fallback"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_logs",
    )
    question = models.TextField()
    intent = models.CharField(max_length=40, blank=True)
    confidence = models.CharField(max_length=16, blank=True)
    entities = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, blank=True)
    retrieved_refs = models.JSONField(default=list, blank=True)
    response = models.TextField(blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.intent or 'UNKNOWN'} — {self.question[:60]}"
