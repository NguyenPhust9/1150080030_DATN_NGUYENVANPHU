import hashlib
import io
import os
from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from apps.fire_detection.inference import DetectorConfig
from apps.fire_detection.models import BrowserFireAlert
from apps.fire_detection.onnx_inference import decode_predictions

FIRE = [{"label": "fire", "confidence": 0.9, "xyxy": [1, 2, 30, 40]}]
URL = "https://res.cloudinary.com/test/image/upload/alert.jpg"


def jpeg(color="orange"):
    result = io.BytesIO()
    Image.new("RGB", (80, 60), color).save(result, format="JPEG")
    return result.getvalue()


def upload(raw=None):
    return SimpleUploadedFile("frame.jpg", raw if raw is not None else jpeg(), content_type="image/jpeg")


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": "https://n8n.example/webhook/fire", "FIRE_CAMERA_ID": "", "FIRE_CONFIRM_FRAMES": "2"})
class BrowserFireTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="camera-owner", role="owner", password="test")
        self.client.force_login(self.user)
        self.run_id = self.client.post(reverse("fire_detection:browser-start")).json()["run_id"]

    def frame(self, sequence, raw=None):
        return self.client.post(reverse("fire_detection:browser-frame"), {"run_id": self.run_id, "sequence": sequence, "image": upload(raw)})

    def test_monitor_page_renders_after_login_without_server_camera_context(self):
        response = self.client.get(reverse("fire_detection:monitor"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "fire_detection/browser_monitor.html")
        self.assertContains(response, 'id="browser-camera"')
        self.assertContains(response, "browser-fire-monitor.js")
        self.assertContains(response, "YOLO lửa/khói")
        self.assertContains(response, reverse("fire_detection:browser-frame"))

    def test_config_is_private_and_tenant_cannot_use_detection(self):
        self.assertEqual(Client().get(reverse("fire_detection:browser-config")).status_code, 302)
        tenant = get_user_model().objects.create_user(username="camera-tenant", role="tenant")
        self.client.force_login(tenant)
        self.assertEqual(self.client.post(reverse("fire_detection:browser-start")).status_code, 403)

    def test_browser_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("fire_detection:browser-start")).status_code, 403)

    @patch("apps.fire_detection.browser_views.predict_image", return_value=FIRE)
    def test_confirmation_cooldown_and_distinct_frames(self, predict):
        self.assertEqual(self.frame(1).json()["state"], "detecting")
        self.assertFalse(BrowserFireAlert.objects.exists())
        result = self.frame(2).json()
        self.assertEqual(result["state"], "alert")
        self.assertTrue(result["alert"]["id"])
        self.assertEqual(self.frame(3).json()["alert"], None)
        self.assertEqual(self.frame(3).status_code, 409)
        self.assertEqual(BrowserFireAlert.objects.count(), 1)
        self.assertEqual(predict.call_count, 3)

    @patch("apps.fire_detection.browser_views.predict_image", return_value=FIRE)
    def test_stale_window_does_not_confirm_old_evidence(self, predict):
        self.frame(1)
        session = self.client.session
        data = session["fire_browser"]
        data["last_seen"] = 1
        session["fire_browser"] = data
        session.save()
        self.assertEqual(self.frame(2).json()["state"], "detecting")

    @patch("apps.fire_detection.browser_views.predict_image")
    def test_invalid_large_and_wrong_session_frames_do_not_run_model(self, predict):
        self.assertEqual(self.frame(1, b"fake image").status_code, 400)
        self.assertEqual(self.frame(1, b"x" * (1024 * 1024 + 1)).status_code, 400)
        self.client.post(reverse("fire_detection:browser-stop"), {"run_id": self.run_id})
        self.assertEqual(self.frame(1).status_code, 409)
        predict.assert_not_called()

    @patch("apps.fire_detection.browser_views.predict_image", side_effect=RuntimeError("private-details"))
    def test_inference_failure_is_not_reported_as_safe(self, predict):
        response = self.frame(1)
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "private-details", status_code=503)

    @patch("apps.fire_detection.browser_views.predict_image", return_value=FIRE)
    @patch("apps.fire_detection.browser_views.upload_alert_image", return_value=URL)
    @patch("apps.fire_detection.browser_views.post_alert_webhook")
    def test_delivery_is_bound_to_confirmed_image_and_only_posts_once(self, post, cloud, predict):
        raw = jpeg()
        self.frame(1, raw)
        alert_id = self.frame(2, raw).json()["alert"]["id"]
        url = reverse("fire_detection:browser-deliver", args=[alert_id])
        wrong = self.client.post(url, {"image": upload(jpeg("blue"))})
        self.assertEqual(wrong.status_code, 400)
        cloud.assert_not_called()
        delivered = self.client.post(url, {"image": upload(raw)})
        self.assertEqual(delivered.json()["webhook_state"], "sent")
        self.assertEqual(delivered.json()["image_url"], URL)
        self.assertEqual(self.client.post(url, {"image": upload(raw)}).json()["webhook_state"], "sent")
        post.assert_called_once()
        cloud.assert_called_once()
        event, detections, image_url = post.call_args.args
        self.assertEqual(event["id"], alert_id)
        self.assertEqual(detections, FIRE)
        self.assertEqual(image_url, URL)

    def test_alerts_are_scoped_to_their_user(self):
        other = get_user_model().objects.create_user(username="other-camera", role="owner")
        event = BrowserFireAlert.objects.create(user=other, detections=FIRE, image_sha256=hashlib.sha256(jpeg()).hexdigest())
        self.assertEqual(self.client.post(reverse("fire_detection:browser-deliver", args=[event.pk]), {"image": upload()}).status_code, 404)
        self.assertEqual(self.client.get(reverse("fire_detection:browser-config")).json()["events"], [])

    @patch("apps.fire_detection.browser_views.upload_alert_image", return_value=URL)
    @patch("apps.fire_detection.browser_views.post_alert_webhook", side_effect=TimeoutError)
    def test_webhook_failure_retains_cloud_image_without_automatic_retry(self, post, cloud):
        raw = jpeg()
        event = BrowserFireAlert.objects.create(user=self.user, detections=FIRE, image_sha256=hashlib.sha256(raw).hexdigest())
        url = reverse("fire_detection:browser-deliver", args=[event.pk])
        result = self.client.post(url, {"image": upload(raw)}).json()
        self.assertEqual(result["webhook_state"], "failed")
        self.assertEqual(result["image_url"], URL)
        self.client.post(url, {"image": upload(raw)})
        post.assert_called_once()

    def test_decoder_keeps_class_mapping_thresholds_and_nms(self):
        # Each column is one [cx, cy, w, h, smoke score, fire score] prediction.
        output = np.array([[[20, 20, 10, 10, 0.1, 0.9], [20, 20, 10, 10, 0.1, 0.8],
                            [50, 40, 10, 10, 0.6, 0.1], [70, 40, 10, 10, 0.5, 0.1]]], dtype=np.float32).transpose(0, 2, 1)
        config = DetectorConfig.from_environment(".", {})
        result = decode_predictions(output, {0: "smoke", 1: "fire"}, 512, 100, 80, 1, 0, 0, config)
        self.assertEqual([item["label"] for item in result], ["fire", "smoke"])
