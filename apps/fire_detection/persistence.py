"""Bounded, single-worker database writes, independent of camera inference."""

import logging
import queue
import threading
from dataclasses import dataclass

from django.db import close_old_connections, connections

logger = logging.getLogger(__name__)

PERSISTENCE_ERROR = "Chưa thể lưu cảnh báo vào cơ sở dữ liệu. Ảnh và lịch sử vẫn được giữ trên máy."
CLEANUP_ERROR = "Tác vụ lưu cảnh báo chưa hoàn tất bình thường. Hãy kiểm tra kết nối cơ sở dữ liệu."
QUEUE_FULL_ERROR = "Hàng đợi lưu cảnh báo đã đầy. Cảnh báo này chỉ được lưu trên máy."


@dataclass(frozen=True)
class AlertWrite:
    event_id: str
    detections: tuple
    image_url: str


def persist_camera_alert(detections, image_url):
    from .services import record_camera_alert

    return record_camera_alert(detections, image_url)


class AlertPersistenceWorker:
    """At most one DB writer and ``capacity`` waiting jobs per detector/process.

    Jobs contain metadata only, never webcam frames. A blocked database can hold
    the one writer, but cannot hold inference or create additional writer threads.
    The worker owns and closes its Django connections after every attempted job.
    """

    def __init__(self, on_update, capacity=8, persist=None):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Alert queue capacity must be a positive integer.")
        self._queue = queue.Queue(maxsize=capacity)
        self._on_update = on_update
        self._persist = persist or persist_camera_alert
        self._lock = threading.Lock()
        self._thread = None
        self._closing = threading.Event()
        self._active = False
        self._failed = 0
        self._last_error = ""

    def submit(self, event_id, detections, image_url):
        task = AlertWrite(event_id, tuple(dict(item) for item in detections), image_url)
        with self._lock:
            if self._closing.is_set():
                return False
            try:
                self._queue.put_nowait(task)
            except queue.Full:
                self._failed += 1
                self._last_error = QUEUE_FULL_ERROR
                logger.warning("Alert persistence queue is full; retaining local alert only")
                return False
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="fire-alert-persistence", daemon=True
                )
                try:
                    self._thread.start()
                except Exception:
                    self._thread = None
                    self._queue.get_nowait()
                    self._queue.task_done()
                    self._failed += 1
                    self._last_error = PERSISTENCE_ERROR
                    raise
        return True

    def snapshot(self):
        with self._lock:
            return {
                "pending": self._queue.qsize(),
                "active": self._active,
                "failed": self._failed,
                "queue_capacity": self._queue.maxsize,
                "last_error": self._last_error,
            }

    def close(self, timeout=0.5):
        """Stop accepting work and drain accepted jobs; never wait indefinitely.

        Camera stop deliberately does not call this: already queued alerts may
        finish independently, and restarting a camera reuses this same writer.
        """
        with self._lock:
            self._closing.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)

    def _notify(self, event_id, state, error=""):
        try:
            self._on_update(event_id, state, error)
        except Exception:
            logger.exception("Could not update in-memory alert persistence status")

    def _run(self):
        while True:
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                with self._lock:
                    if self._closing.is_set() and self._queue.empty():
                        return
                continue
            with self._lock:
                self._active = True
            self._notify(task.event_id, "saving")
            state, error = "failed", ""
            try:
                close_old_connections()
                saved = self._persist(task.detections, task.image_url)
                state = "saved" if saved is not None else "unmapped"
            except Exception:
                error = PERSISTENCE_ERROR
                logger.exception("Could not persist webcam alert to Indoor Map")
            finally:
                try:
                    # connections is thread-local; this does not close request
                    # connections or another process's database sessions.
                    connections.close_all()
                except Exception:
                    state, error = "failed", CLEANUP_ERROR
                    logger.exception("Could not close alert writer database connections")
                with self._lock:
                    self._active = False
                    if state == "failed":
                        self._failed += 1
                        self._last_error = error
                self._notify(task.event_id, state, error)
                self._queue.task_done()
