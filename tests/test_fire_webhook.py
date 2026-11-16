import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase

from apps.fire_detection.webcam import WebcamFireDetector
from apps.fire_detection.webhook import WEBHOOK_ERROR, AlertWebhookWorker, deliver_fire_alert

ENV = {
    "FIRE_WEBHOOK_URL": "https://n8n.example/webhook/fire",
    "CLOUDINARY_URL": "cloudinary://key:secret@test-cloud",
    "CLOUDINARY_CLOUD_NAME": "", "CLOUDINARY_API_KEY": "", "CLOUDINARY_API_SECRET": "",
    "FIRE_CAMERA_NAME": "Camera tang 1", "FIRE_CAMERA_LOCATION": "Hanh lang",
}
EVENT = {"id": "event-001", "detected_at": "2026-11-16T15:00:00+00:00"}
DETECTIONS = [{"label": "fire", "confidence": 0.92, "xyxy": [1, 2, 30, 40]}]
IMAGE_URL = "https://res.cloudinary.com/test-cloud/image/upload/fire.jpg"


@patch.dict(os.environ, ENV)
class FireWebhookTests(SimpleTestCase):
    def test_upload_then_post_matches_existing_n8n_contract(self):
        response = Mock(status=200)
        opener = MagicMock()
        opener.return_value.__enter__.return_value = response
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image:
            image.write(b"test image")
            name = image.name
        self.addCleanup(Path(name).unlink)
        with patch("apps.fire_detection.webhook.cloudinary.uploader.upload", return_value={"secure_url": IMAGE_URL}) as upload, \
                patch("apps.fire_detection.webhook.urlopen", opener):
            self.assertEqual(deliver_fire_alert(EVENT, DETECTIONS, name), IMAGE_URL)
        upload.assert_called_once()
        request = opener.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(payload["event_id"], EVENT["id"])
        self.assertEqual(payload["image_url"], IMAGE_URL)
        self.assertEqual(payload["confidence"], 0.92)
        self.assertEqual(payload["camera_name"], "Camera tang 1")
        self.assertEqual(payload["label"], "fire")
        self.assertEqual(request.get_header("Idempotency-key"), EVENT["id"])
        self.assertEqual(opener.call_args.kwargs["timeout"], 15)

    def test_invalid_endpoint_does_not_upload_evidence(self):
        with patch.dict(os.environ, {"FIRE_WEBHOOK_URL": "http://example.com/webhook"}), \
                patch("apps.fire_detection.webhook.cloudinary.uploader.upload") as upload:
            with self.assertRaises(ValueError):
                deliver_fire_alert(EVENT, DETECTIONS, "unused.jpg")
        upload.assert_not_called()

    def test_worker_does_not_block_and_reports_delivery_separately(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        updates = []
        def deliver(*args):
            entered.set()
            release.wait(3)
            return IMAGE_URL
        def update(*args):
            updates.append(args)
            if args[1] == "sent":
                finished.set()
        worker = AlertWebhookWorker(update, capacity=1, deliver=deliver)
        self.addCleanup(worker.close, 2)
        self.addCleanup(release.set)
        self.assertTrue(worker.submit(EVENT, DETECTIONS, "unused.jpg"))
        self.assertTrue(entered.wait(2))
        self.assertTrue(worker.snapshot()["active"])
        self.assertTrue(worker.submit({**EVENT, "id": "event-002"}, DETECTIONS, "unused.jpg"))
        self.assertFalse(worker.submit({**EVENT, "id": "event-003"}, DETECTIONS, "unused.jpg"))
        release.set()
        self.assertTrue(finished.wait(2))
        self.assertTrue(any(update[1] == "sent" and update[3] == IMAGE_URL for update in updates))

    def test_worker_failure_is_redacted_and_does_not_retry(self):
        finished = threading.Event()
        updates = []
        def update(*args):
            updates.append(args)
            if args[1] == "failed":
                finished.set()
        delivery = Mock(side_effect=RuntimeError("private-token"))
        worker = AlertWebhookWorker(update, deliver=delivery)
        self.addCleanup(worker.close, 2)
        self.assertTrue(worker.submit(EVENT, DETECTIONS, "unused.jpg"))
        self.assertTrue(finished.wait(2))
        delivery.assert_called_once()
        self.assertEqual(updates[-1][2], WEBHOOK_ERROR)
        self.assertNotIn("private-token", str(updates))

    def test_confirmed_saved_event_enqueues_webhook_even_when_database_fails(self):
        detector = WebcamFireDetector()
        with tempfile.TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=Path(directory)), \
                patch.object(detector._webhook, "submit", return_value=True) as submit, \
                patch.object(detector._persistence, "submit", side_effect=RuntimeError("db unavailable")):
            cv2 = Mock()
            cv2.imwrite.return_value = True
            self.assertTrue(detector._save_event(None, DETECTIONS, cv2))
        submit.assert_called_once()
        state = detector.snapshot()["events"][0]
        self.assertEqual(state["webhook_state"], "queued")
        self.assertEqual(state["persistence_state"], "failed")
        self.assertIn("detected_at", submit.call_args.args[0])

    def test_empty_detection_does_not_send_and_vercel_does_not_open_webcam(self):
        detector = WebcamFireDetector()
        with patch.object(detector._webhook, "submit") as submit:
            self.assertFalse(detector._save_event(None, [], Mock()))
        submit.assert_not_called()
        with patch.dict(os.environ, {"VERCEL": "1"}), patch("threading.Thread.start") as start:
            self.assertFalse(detector.start()[0])
        start.assert_not_called()
