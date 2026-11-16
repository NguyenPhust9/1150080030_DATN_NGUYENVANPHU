"""Camera-free regression checks; safe to run without a database or GPU."""

import asyncio
import itertools
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase

from apps.fire_detection.inference import (
    DetectorConfig,
    TemporalConfirmation,
    filter_detections,
    validate_model_classes,
)
from apps.fire_detection.persistence import AlertPersistenceWorker
from apps.fire_detection.services import record_camera_alert
from apps.fire_detection.views import video_stream
from apps.fire_detection.webcam import WebcamFireDetector


def box(label, score, coordinates):
    return SimpleNamespace(
        cls=SimpleNamespace(item=lambda: label),
        conf=SimpleNamespace(item=lambda: score),
        xyxy=[SimpleNamespace(tolist=lambda: coordinates)],
    )


def prediction(boxes):
    return SimpleNamespace(boxes=boxes, names={0: "fire", 1: "smoke", 2: "person"})


def fire(score=0.75):
    return {"label": "fire", "confidence": score, "xyxy": (100, 100, 102, 104)}


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class DetectorConfigTests(SimpleTestCase):
    def test_default_resolution_and_thresholds(self):
        config = DetectorConfig.from_environment(settings.BASE_DIR, {})
        self.assertEqual(config.image_size, 512)
        self.assertEqual((config.fire_confidence, config.smoke_confidence), (0.25, 0.55))

    def test_supported_resolution_override(self):
        config = DetectorConfig.from_environment(settings.BASE_DIR, {"FIRE_IMAGE_SIZE": "960"})
        self.assertEqual(config.image_size, 960)

    def test_invalid_resolution_and_configuration_fail_explicitly(self):
        invalid = [
            ("FIRE_IMAGE_SIZE", "319"), ("FIRE_IMAGE_SIZE", "1537"),
            ("FIRE_IMAGE_SIZE", "767"), ("FIRE_IMAGE_SIZE", "invalid"),
            ("FIRE_CONFIRM_FRAMES", "6"), ("FIRE_CONFIRM_FRAMES", "0"),
            ("FIRE_CONFIDENCE", "nan"), ("SMOKE_CONFIDENCE", "inf"),
            ("FIRE_CONFIDENCE", "0"), ("SMOKE_CONFIDENCE", "1.01"),
            ("FIRE_CAMERA_INDEX", "-1"), ("FIRE_ALERT_COOLDOWN_SECONDS", "0"),
        ]
        for name, value in invalid:
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, name):
                DetectorConfig.from_environment(settings.BASE_DIR, {name: value})


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class DetectionFilteringTests(SimpleTestCase):
    def setUp(self):
        self.config = DetectorConfig.from_environment(settings.BASE_DIR, {})

    def test_model_class_order_and_names_are_validated(self):
        validate_model_classes({0: "smoke", 1: "fire"})
        validate_model_classes([" Fire ", "Smoke"])
        with self.assertRaisesRegex(ValueError, "fire, smoke"):
            validate_model_classes({0: "person", 1: "car"})
        with self.assertRaisesRegex(ValueError, "smoke"):
            validate_model_classes({0: "fire"})

    def test_tiny_fire_box_is_not_discarded(self):
        result = prediction([box(0, 0.25, [600, 350, 601, 352])])
        self.assertEqual(filter_detections(result, (720, 1280, 3), self.config)[0]["xyxy"],
                         (600, 350, 601, 352))

    def test_large_smoke_box_is_not_unconditionally_rejected(self):
        result = prediction([box(1, 0.9, [0, 0, 1280, 720])])
        self.assertEqual(filter_detections(result, (720, 1280, 3), self.config)[0]["label"], "smoke")

    def test_class_thresholds_are_preserved(self):
        result = prediction([box(0, 0.24, [0, 0, 20, 20]), box(1, 0.54, [0, 0, 20, 20]),
                             box(0, 0.25, [0, 0, 20, 20]), box(1, 0.55, [0, 0, 20, 20])])
        self.assertEqual([d["label"] for d in filter_detections(result, (720, 1280, 3), self.config)],
                         ["fire", "smoke"])

    def test_invalid_and_unrelated_boxes_do_not_create_detections(self):
        result = prediction([box(0, float("nan"), [0, 0, 20, 20]), box(2, 0.9, [0, 0, 20, 20]),
                             box(0, 0.9, [2, 2, 1, 1]), box(0, 0.9, [0, 0, float("inf"), 20])])
        self.assertEqual(filter_detections(result, (720, 1280, 3), self.config), [])
        self.assertEqual(filter_detections(prediction(None), (720, 1280, 3), self.config), [])


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class TemporalConfirmationTests(SimpleTestCase):
    def test_nonconsecutive_positive_frames_confirm(self):
        tracker = TemporalConfirmation()
        self.assertEqual(tracker.update([fire()])[0], "detecting")
        self.assertEqual(tracker.update([])[0], "detecting")
        self.assertEqual(tracker.update([fire()])[0], "alert")

    def test_empty_frame_retains_fire_evidence_not_fabricated_smoke(self):
        tracker = TemporalConfirmation()
        tracker.update([fire(0.6)])
        tracker.update([fire(0.8)])
        state, evidence = tracker.update([])
        self.assertEqual(state, "alert")
        self.assertEqual(evidence, [fire(0.8)])

    def test_distinct_single_class_hits_do_not_confirm_each_other(self):
        tracker = TemporalConfirmation()
        tracker.update([fire()])
        self.assertEqual(tracker.update([{**fire(), "label": "smoke"}]), ("detecting", []))

    def test_expired_evidence_returns_to_neutral_monitoring(self):
        tracker = TemporalConfirmation()
        tracker.update([fire()])
        tracker.update([fire()])
        for _ in range(5):
            state, evidence = tracker.update([])
        self.assertEqual((state, evidence), ("monitoring", []))


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class DetectorLifecycleTests(SimpleTestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.detector = WebcamFireDetector()

    def test_initial_snapshot_is_stopped_and_stale_not_safe(self):
        status = self.detector.snapshot()
        self.assertEqual(status["state"], "stopped")
        self.assertTrue(status["result_stale"])
        self.assertIsNone(status["last_frame_at"])

    def test_snapshot_uses_frozen_active_config(self):
        self.detector._active_config = DetectorConfig.from_environment(settings.BASE_DIR, {"FIRE_IMAGE_SIZE": "960"})
        with patch.dict(os.environ, {"FIRE_IMAGE_SIZE": "512", "FIRE_CONFIDENCE": "0.8"}):
            status = self.detector.snapshot()
        self.assertEqual(status["image_size"], 960)
        self.assertEqual(status["fire_confidence"], 0.25)
        self.assertEqual(status["configuration_source"], "active")

    def test_result_freshness_expires(self):
        self.detector._last_frame_tick = 100.0
        with patch("apps.fire_detection.webcam.time.monotonic", return_value=101.0):
            self.assertFalse(self.detector.snapshot()["result_stale"])
        with patch("apps.fire_detection.webcam.time.monotonic", return_value=111.0):
            self.assertTrue(self.detector.snapshot()["result_stale"])

    def test_bad_config_fails_start_without_opening_camera(self):
        with patch.dict(os.environ, {"FIRE_IMAGE_SIZE": "513"}):
            ok, message = self.detector.start()
            status = self.detector.snapshot()
        self.assertFalse(ok)
        self.assertIn("FIRE_IMAGE_SIZE", message)
        self.assertEqual(status["state"], "error")
        self.assertIsNone(self.detector._thread)

    def test_missing_model_clears_stale_frame(self):
        self.detector._frame = b"old"
        with patch.object(Path, "is_file", return_value=False):
            self.assertFalse(self.detector.start()[0])
        self.assertIsNone(self.detector._frame)

    def test_stop_does_not_report_finished_or_allow_competing_worker(self):
        worker = Mock()
        worker.is_alive.return_value = True
        self.detector._thread = worker
        self.detector._running = True
        self.detector._frame = b"old"
        self.detector.stop()
        self.assertEqual(self.detector.snapshot()["state"], "stopping")
        self.assertIsNone(self.detector._frame)
        self.assertFalse(self.detector.start()[0])
        self.assertTrue(self.detector._stop_event.is_set())
        worker.join.assert_called_once_with(timeout=3)

    def test_restart_allocates_new_event_and_freezes_configuration(self):
        old_event = self.detector._stop_event
        old_event.set()
        with patch.object(Path, "is_file", return_value=True), patch("apps.fire_detection.webcam.threading.Thread") as thread:
            thread.return_value.is_alive.return_value = False
            self.assertTrue(self.detector.start()[0])
        self.assertIsNot(self.detector._stop_event, old_event)
        self.assertTrue(old_event.is_set())
        self.assertFalse(self.detector._stop_event.is_set())
        self.assertEqual(self.detector.snapshot()["state"], "starting")
        thread.return_value.start.assert_called_once()

    def test_error_stream_ends_without_replaying_stale_image(self):
        self.detector._frame = b"old"
        self.detector._state = "error"

        async def collect():
            return [frame async for frame in self.detector.mjpeg_frames()]

        self.assertEqual(asyncio.run(collect()), [])

    def test_worker_uses_configured_resolution_and_clears_failure(self):
        config = DetectorConfig.from_environment(settings.BASE_DIR, {"FIRE_IMAGE_SIZE": "960"})
        frame = Mock(shape=(720, 1280, 3))
        frame.copy.return_value = frame
        capture = Mock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(True, frame), (False, None)]
        cv2 = Mock()
        cv2.VideoCapture.return_value = capture
        cv2.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b"fresh"))
        model = Mock()
        model.names = {0: "fire", 1: "smoke"}
        model.predict.return_value = [prediction([])]
        ultralytics = SimpleNamespace(YOLO=Mock(return_value=model))
        with patch.dict("sys.modules", {"cv2": cv2, "ultralytics": ultralytics}), self.assertLogs("apps.fire_detection.webcam", level="ERROR"):
            self.detector._run(config, threading.Event())
        model.predict.assert_called_once_with(frame, imgsz=960, conf=0.25,
                                               iou=0.7, max_det=300, verbose=False)
        self.assertEqual(self.detector.snapshot()["state"], "error")
        self.assertIsNone(self.detector._frame)
        self.assertIsNone(self.detector.snapshot()["last_frame_at"])
        self.assertFalse(self.detector.snapshot()["running"])
        capture.release.assert_called()

    def test_wrong_model_fails_before_opening_camera(self):
        config = DetectorConfig.from_environment(settings.BASE_DIR, {})
        model = Mock(names={0: "person", 1: "car"})
        cv2 = Mock()
        ultralytics = SimpleNamespace(YOLO=Mock(return_value=model))
        with (patch.dict("sys.modules", {"cv2": cv2, "ultralytics": ultralytics}),
              self.assertLogs("apps.fire_detection.webcam", level="ERROR")):
            self.detector._run(config, threading.Event())
        self.assertEqual(self.detector.snapshot()["state"], "error")
        self.assertIn("fire, smoke", self.detector.snapshot()["error"])
        cv2.VideoCapture.assert_not_called()
        model.predict.assert_not_called()

    def test_worker_preserves_fire_label_but_does_not_save_empty_alert(self):
        config = DetectorConfig.from_environment(settings.BASE_DIR, {"FIRE_ALERT_COOLDOWN_SECONDS": "1"})
        frame = Mock(shape=(720, 1280, 3))
        frame.copy.return_value = frame
        frames = iter([(True, frame), (True, frame), (True, frame), (False, None)])
        snapshots = []

        def read_frame():
            snapshots.append(self.detector.snapshot())
            return next(frames)

        capture = Mock()
        capture.isOpened.return_value = True
        capture.read.side_effect = read_frame
        cv2 = Mock()
        cv2.VideoCapture.return_value = capture
        cv2.imencode.return_value = (True, SimpleNamespace(tobytes=lambda: b"fresh"))
        model = Mock()
        model.names = {0: "fire", 1: "smoke"}
        model.predict.side_effect = [[prediction([box(0, 0.6, [100, 100, 102, 104])])],
                                     [prediction([box(0, 0.8, [100, 100, 102, 104])])],
                                     [prediction([])]]
        ultralytics = SimpleNamespace(YOLO=Mock(return_value=model))
        with (patch.dict("sys.modules", {"cv2": cv2, "ultralytics": ultralytics}),
              patch("apps.fire_detection.webcam.time.monotonic", side_effect=itertools.count(100, 2)),
              patch.object(self.detector, "_save_event", return_value=True) as save_event,
              self.assertLogs("apps.fire_detection.webcam", level="ERROR")):
            self.detector._run(config, threading.Event())
        self.assertEqual(snapshots[-1]["state"], "alert")
        self.assertEqual(snapshots[-1]["detections"], [])
        self.assertEqual(snapshots[-1]["alert_labels"], ["fire"])
        self.assertIsNotNone(snapshots[-1]["last_frame_at"])
        save_event.assert_called_once()
        self.assertEqual(save_event.call_args.args[1], [fire(0.8)])
        captions = [call.args[1] for call in cv2.putText.call_args_list]
        self.assertNotIn("CANH BAO KHOI", captions)
        self.assertNotIn("AN TOAN", captions)


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class CameraAlertPersistenceTests(SimpleTestCase):
    def test_empty_or_invalid_alerts_never_touch_database(self):
        with patch.dict(os.environ, {"FIRE_CAMERA_ID": "d7b5ab1a-812f-4100-967e-6443f4c7d329"}):
            for detections in ([], None, [{"label": "smoke", "confidence": 0}],
                               [{"label": "fire", "confidence": float("nan")}],
                               [{"label": "person", "confidence": 0.9}]):
                self.assertIsNone(record_camera_alert(detections, "/media/example.jpg"))

    def test_unmapped_camera_never_touches_database(self):
        with patch.dict(os.environ, {"FIRE_CAMERA_ID": ""}):
            self.assertIsNone(record_camera_alert([fire()], "/media/example.jpg"))

    def test_empty_alert_does_not_write_image(self):
        cv2 = Mock()
        self.assertFalse(WebcamFireDetector()._save_event(None, [], cv2))
        cv2.imwrite.assert_not_called()


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class BackgroundAlertPersistenceTests(SimpleTestCase):
    def test_slow_database_cannot_block_history_or_create_unbounded_workers(self):
        detector = WebcamFireDetector()
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        saved_ids = []
        database_threads, cleanup_threads = [], []

        def slow_write(detections, image_url):
            database_threads.append(threading.get_ident())
            entered.set()
            if not release.wait(timeout=3):
                raise RuntimeError("Test did not release simulated database")
            return object()

        def updated(event_id, state, error):
            detector._update_event_persistence(event_id, state, error)
            if state == "saved":
                saved_ids.append(event_id)
                if len(saved_ids) == 3:
                    completed.set()

        worker = AlertPersistenceWorker(updated, capacity=2, persist=slow_write)
        detector._persistence = worker
        cv2 = Mock()
        cv2.imwrite.return_value = True
        with (patch.object(Path, "mkdir"),
              patch("apps.fire_detection.persistence.close_old_connections") as before,
              patch("apps.fire_detection.persistence.connections.close_all",
                    side_effect=lambda: cleanup_threads.append(threading.get_ident())) as after):
            try:
                started = time.perf_counter()
                self.assertTrue(detector._save_event(None, [fire()], cv2))
                self.assertLess(time.perf_counter() - started, 0.5)
                self.assertTrue(entered.wait(timeout=1))
                snapshot = detector.snapshot()
                self.assertEqual(len(snapshot["events"]), 1)
                self.assertEqual(snapshot["events"][0]["persistence_state"], "saving")
                self.assertTrue(snapshot["persistence"]["active"])
                writer_thread = worker._thread
                # One active job plus two waiting jobs, with no frame/image copies.
                for _ in range(3):
                    self.assertTrue(detector._save_event(None, [fire()], cv2))
                snapshot = detector.snapshot()
                self.assertEqual(len(snapshot["events"]), 4)
                self.assertEqual(snapshot["events"][0]["persistence_state"], "queue_full")
                self.assertEqual(snapshot["persistence"]["pending"], 2)
                self.assertEqual(snapshot["persistence"]["queue_capacity"], 2)
                self.assertEqual(snapshot["persistence"]["failed"], 1)
                self.assertIs(worker._thread, writer_thread)
                self.assertEqual(len(database_threads), 1)
                # Camera stop stays immediate and does not cancel accepted alerts.
                detector.stop()
                self.assertIs(detector._persistence, worker)
                self.assertFalse(release.is_set())
                worker.close(timeout=0.01)
                self.assertTrue(writer_thread.is_alive())
                self.assertFalse(worker.submit("after-close", [fire()], "/media/late.jpg"))
                release.set()
                self.assertTrue(completed.wait(timeout=1))
            finally:
                release.set()
                worker.close(timeout=1)
            self.assertFalse(worker._thread.is_alive())
            self.assertEqual(before.call_count, 3)
            self.assertEqual(after.call_count, 3)
        self.assertEqual(len(set(database_threads)), 1)
        self.assertEqual(database_threads, cleanup_threads)
        self.assertNotEqual(database_threads[0], threading.get_ident())

    def _complete_job(self, persist, before_error=None, after_error=None):
        completed = threading.Event()
        updates = []

        def update(event_id, state, error):
            updates.append((event_id, state, error))
            if state != "saving":
                completed.set()

        worker = AlertPersistenceWorker(update, persist=persist)
        with (patch("apps.fire_detection.persistence.close_old_connections", side_effect=before_error) as before,
              patch("apps.fire_detection.persistence.connections.close_all", side_effect=after_error) as after):
            try:
                self.assertTrue(worker.submit("event-id", [fire()], "/media/fire.jpg"))
                self.assertTrue(completed.wait(timeout=1))
            finally:
                worker.close(timeout=1)
            self.assertFalse(worker._thread.is_alive())
            before.assert_called_once()
            after.assert_called_once()
        return worker.snapshot(), updates

    def test_success_only_reports_saved_after_database_and_cleanup(self):
        snapshot, updates = self._complete_job(Mock(return_value=object()))
        self.assertEqual([item[1] for item in updates], ["saving", "saved"])
        self.assertEqual(snapshot["failed"], 0)
        self.assertEqual(snapshot["pending"], 0)
        self.assertFalse(snapshot["active"])

    def test_missing_mapping_is_local_only_not_a_saved_database_alert(self):
        snapshot, updates = self._complete_job(Mock(return_value=None))
        self.assertEqual(updates[-1][1], "unmapped")
        self.assertEqual(snapshot["failed"], 0)

    def test_database_error_is_sanitized_and_connections_still_closed(self):
        with self.assertLogs("apps.fire_detection.persistence", level="ERROR"):
            snapshot, updates = self._complete_job(Mock(side_effect=RuntimeError("password=private-secret")))
        self.assertEqual(updates[-1][1], "failed")
        self.assertEqual(snapshot["failed"], 1)
        self.assertTrue(snapshot["last_error"])
        self.assertNotIn("private-secret", str(updates))
        self.assertNotIn("private-secret", str(snapshot))

    def test_connection_setup_error_still_closes_worker_connections(self):
        persist = Mock()
        with self.assertLogs("apps.fire_detection.persistence", level="ERROR"):
            snapshot, updates = self._complete_job(persist, before_error=RuntimeError("unavailable"))
        persist.assert_not_called()
        self.assertEqual(updates[-1][1], "failed")
        self.assertEqual(snapshot["failed"], 1)

    def test_connection_cleanup_error_is_reported_without_leaking_details(self):
        with self.assertLogs("apps.fire_detection.persistence", level="ERROR"):
            snapshot, updates = self._complete_job(Mock(return_value=object()),
                                                   after_error=RuntimeError("private-hostname"))
        self.assertEqual(updates[-1][1], "failed")
        self.assertEqual(snapshot["failed"], 1)
        self.assertNotIn("private-hostname", str(updates))

    def test_enqueue_error_keeps_local_history_without_crashing_inference(self):
        detector, cv2 = WebcamFireDetector(), Mock()
        cv2.imwrite.return_value = True
        with (patch.object(Path, "mkdir"),
              patch.object(detector._persistence, "submit", side_effect=RuntimeError("private-detail")),
              self.assertLogs("apps.fire_detection.webcam", level="ERROR")):
            self.assertTrue(detector._save_event(None, [fire()], cv2))
        event = detector.snapshot()["events"][0]
        self.assertEqual(event["persistence_state"], "failed")
        self.assertNotIn("private-detail", event["persistence_error"])


@patch.dict(os.environ, {"FIRE_WEBHOOK_URL": ""})
class CameraStreamViewTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/giam-sat-chay/stream/")
        self.request.user = SimpleNamespace(is_authenticated=True, is_superuser=False, role="owner")

    def test_get_stopped_stream_never_starts_camera(self):
        with patch("apps.fire_detection.views.detector") as detector:
            detector.snapshot.return_value = {"state": "stopped", "running": False, "loading": False}
            response = video_stream(self.request)
            self.assertEqual(response.status_code, 409)
            detector.start.assert_not_called()
            detector.mjpeg_frames.assert_not_called()

    def test_loading_stream_is_allowed_without_restarting_worker(self):
        async def empty_stream():
            if False:
                yield b""

        with patch("apps.fire_detection.views.detector") as detector:
            detector.snapshot.return_value = {"state": "starting", "running": False, "loading": True}
            detector.mjpeg_frames.return_value = empty_stream()
            response = video_stream(self.request)
            self.assertEqual(response.status_code, 200)
            detector.start.assert_not_called()

    def test_tenant_cannot_open_operator_camera(self):
        self.request.user.role = "tenant"
        with patch("apps.fire_detection.views.detector") as detector, self.assertRaises(PermissionDenied):
            video_stream(self.request)
        detector.snapshot.assert_not_called()
