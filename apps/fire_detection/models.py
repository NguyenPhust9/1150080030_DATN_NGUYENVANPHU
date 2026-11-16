import uuid

from django.conf import settings
from django.db import models


class BrowserFireAlert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="browser_fire_alerts")
    created_at = models.DateTimeField(auto_now_add=True)
    image_sha256 = models.CharField(max_length=64)
    detections = models.JSONField(default=list)
    delivery_state = models.CharField(max_length=16, default="pending")
    image_url = models.CharField(max_length=500, blank=True)
    persistence_state = models.CharField(max_length=16, default="pending")

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]
