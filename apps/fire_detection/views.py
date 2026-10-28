from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.rentals.permissions import require_operator

from .webcam import detector


def _operator(request):
    require_operator(request.user)


@login_required
def monitor(request):
    _operator(request)
    return render(request, "fire_detection/monitor.html", detector.snapshot())


@login_required
@require_POST
def start(request):
    _operator(request)
    ok, message = detector.start()
    return JsonResponse({"ok": ok, "message": message, **detector.snapshot()}, status=200 if ok else 503)


@login_required
@require_POST
def stop(request):
    _operator(request)
    detector.stop()
    return JsonResponse({"ok": True, "message": "Đã dừng camera.", **detector.snapshot()})


@login_required
@require_GET
def status(request):
    _operator(request)
    return JsonResponse(detector.snapshot())


@login_required
@require_GET
def video_stream(request):
    _operator(request)
    detector.start()
    return StreamingHttpResponse(
        detector.mjpeg_frames(),
        content_type="multipart/x-mixed-replace; boundary=frame",
    )
