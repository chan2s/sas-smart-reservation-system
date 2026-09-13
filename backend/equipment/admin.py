from django.contrib import admin

from .models import Equipment, EquipmentCategory, EquipmentImage, MaintenanceRecord


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")


class EquipmentImageInline(admin.TabularInline):
    model = EquipmentImage
    extra = 0
    fields = ("image", "caption", "display_order", "is_primary")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_quantity", "condition", "is_active")
    list_filter = ("category", "condition", "is_active")
    search_fields = ("name",)
    inlines = (EquipmentImageInline,)


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("equipment", "quantity", "issue_type", "status", "created_at")
    list_filter = ("issue_type", "status")