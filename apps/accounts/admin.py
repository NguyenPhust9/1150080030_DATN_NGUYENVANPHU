from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AccountAuditLog, LoginHistory, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Thông tin hệ thống",
            {
                "fields": (
                    "role",
                    "phone",
                    "managed_owner",
                    "must_change_password",
                    "password_changed_at",
                    "locked_at",
                    "locked_by",
                    "lock_reason",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Thông tin hệ thống", {"fields": ("role", "phone", "email", "managed_owner")}),
    )
    list_display = ("username", "email", "role", "managed_owner", "is_active", "must_change_password", "is_staff")
    list_filter = ("role", "is_active", "must_change_password", "is_staff")


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ("username_attempted", "user", "event_type", "ip_address", "occurred_at", "failure_reason")
    list_filter = ("event_type", "occurred_at")
    search_fields = ("username_attempted", "user__username", "ip_address", "failure_reason")
    readonly_fields = (
        "id",
        "user",
        "username_attempted",
        "event_type",
        "occurred_at",
        "ip_address",
        "user_agent",
        "session_key",
        "failure_reason",
    )


@admin.register(AccountAuditLog)
class AccountAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "target_user", "ip_address", "occurred_at", "reason")
    list_filter = ("action", "occurred_at")
    search_fields = ("actor__username", "target_user__username", "reason")
    readonly_fields = ("id", "actor", "target_user", "action", "occurred_at", "ip_address", "reason", "changes")

