from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SMSCode, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("phone", "first_name", "last_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("phone", "first_name", "last_name")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Личные данные", {"fields": ("first_name", "last_name")}),
        (
            "Права",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "password1", "password2")}),)


@admin.register(SMSCode)
class SMSCodeAdmin(admin.ModelAdmin):
    list_display = ("phone", "code", "purpose", "is_used", "attempts", "created_at", "expires_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("phone", "code")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
