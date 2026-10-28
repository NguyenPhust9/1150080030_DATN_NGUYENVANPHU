import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Quản trị viên"
        OWNER = "owner", "Chủ nhà"
        STAFF = "staff", "Nhân viên"
        TENANT = "tenant", "Khách thuê"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField("vai trò", max_length=20, choices=Role.choices, default=Role.STAFF)
    phone = models.CharField("số điện thoại", max_length=20, blank=True)
    managed_owner = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
        verbose_name="chủ nhà quản lý",
    )
    must_change_password = models.BooleanField("buộc đổi mật khẩu", default=False)
    password_changed_at = models.DateTimeField("thời điểm đổi mật khẩu", null=True, blank=True)
    locked_at = models.DateTimeField("thời điểm khóa", null=True, blank=True)
    locked_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_users",
        verbose_name="người khóa",
    )
    lock_reason = models.CharField("lý do khóa/mở", max_length=255, blank=True)

    class Meta:
        verbose_name = "tài khoản"
        verbose_name_plural = "tài khoản"

    def __str__(self):
        return self.get_full_name() or self.username


class LoginHistory(models.Model):
    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Đăng nhập thành công"
        LOGIN_FAILED = "login_failed", "Đăng nhập thất bại"
        LOGOUT = "logout", "Đăng xuất"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_histories",
        verbose_name="tài khoản",
    )
    username_attempted = models.CharField("username đăng nhập", max_length=150)
    event_type = models.CharField(
        "loại sự kiện",
        max_length=30,
        choices=EventType.choices,
        default=EventType.LOGIN_SUCCESS,
    )
    occurred_at = models.DateTimeField("thời điểm", default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField("địa chỉ IP", null=True, blank=True)
    user_agent = models.TextField("trình duyệt / thiết bị", blank=True)
    session_key = models.CharField("session key", max_length=64, blank=True)
    failure_reason = models.CharField("lý do thất bại", max_length=255, blank=True)

    class Meta:
        ordering = ("-occurred_at",)
        verbose_name = "lịch sử đăng nhập"
        verbose_name_plural = "lịch sử đăng nhập"

    def __str__(self):
        return f"{self.username_attempted} - {self.get_event_type_display()} ({self.occurred_at:%d/%m/%Y %H:%M})"


class AccountAuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE_USER = "create_user", "Tạo tài khoản"
        UPDATE_USER = "update_user", "Cập nhật tài khoản"
        LOCK_USER = "lock_user", "Khóa tài khoản"
        UNLOCK_USER = "unlock_user", "Mở khóa tài khoản"
        RESET_PASSWORD = "reset_password", "Đặt lại mật khẩu"
        CHANGE_PASSWORD = "change_password", "Đổi mật khẩu"
        ASSIGN_SCOPE = "assign_scope", "Phân công phạm vi"
        LINK_TENANT = "link_tenant", "Liên kết khách thuê"
        UNLINK_TENANT = "unlink_tenant", "Gỡ liên kết khách thuê"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_account_audits",
        verbose_name="người thực hiện",
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_audit_logs",
        verbose_name="tài khoản bị tác động",
    )
    action = models.CharField("hành động", max_length=40, choices=Action.choices)
    occurred_at = models.DateTimeField("thời điểm", default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField("địa chỉ IP", null=True, blank=True)
    reason = models.CharField("lý do", max_length=255, blank=True)
    changes = models.JSONField("thay đổi", default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at",)
        verbose_name = "nhật ký tác động tài khoản"
        verbose_name_plural = "nhật ký tác động tài khoản"

    def __str__(self):
        target_label = self.target_user.username if self.target_user else "—"
        return f"{self.get_action_display()} -> {target_label} ({self.occurred_at:%d/%m/%Y %H:%M})"

