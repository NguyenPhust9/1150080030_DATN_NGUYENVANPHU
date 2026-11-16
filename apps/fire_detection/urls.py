from django.urls import path

from . import browser_views, views

app_name = "fire_detection"

urlpatterns = [
    path("camera/cau-hinh/", browser_views.browser_config, name="browser-config"),
    path("camera/bat/", browser_views.browser_start, name="browser-start"),
    path("camera/tat/", browser_views.browser_stop, name="browser-stop"),
    path("camera/khung-hinh/", browser_views.browser_frame, name="browser-frame"),
    path("camera/canh-bao/<uuid:alert_id>/gui/", browser_views.browser_deliver, name="browser-deliver"),
    path("", views.monitor, name="monitor"),
    path("stream/", views.video_stream, name="stream"),
    path("trang-thai/", views.status, name="status"),
    path("bat/", views.start, name="start"),
    path("tat/", views.stop, name="stop"),
]
