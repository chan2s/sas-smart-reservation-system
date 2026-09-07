from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "role", "organization", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Institution", {"fields": ("role", "organization", "phone", "avatar")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Institution", {"fields": ("role", "organization", "phone")}),
    )