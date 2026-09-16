from django.contrib import admin

from .models import ChatLog, KnowledgeBaseEntry


@admin.register(KnowledgeBaseEntry)
class KnowledgeBaseEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "status", "facility", "updated_at")
    list_filter = ("category", "status", "facility")
    search_fields = ("title", "content", "keywords")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user",
        "intent",
        "source",
        "latency_ms",
        "short_question",
    )
    list_filter = ("intent", "source")
    search_fields = ("question", "response")
    readonly_fields = (
        "user",
        "question",
        "intent",
        "confidence",
        "entities",
        "source",
        "retrieved_refs",
        "response",
        "latency_ms",
        "error",
        "created_at",
    )

    @admin.display(description="Question")
    def short_question(self, obj: ChatLog) -> str:
        return obj.question[:60]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
