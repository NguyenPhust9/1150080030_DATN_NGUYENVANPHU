import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Quản trị viên"
        OWNER = "owner", "Chủ nhà"
        STAFF = "staff", "Nhân viên"
        TENANT = "tenant", "Khách thuê"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField("vai trò", max_length=20, choices=Role.choices, default=Role.STAFF)
    phone = models.CharField("số điện thoại", max_length=20, blank=True)

    class Meta:
        verbose_name = "tài khoản"
        verbose_name_plural = "tài khoản"

    def __str__(self):
        return self.get_full_name() or self.username
