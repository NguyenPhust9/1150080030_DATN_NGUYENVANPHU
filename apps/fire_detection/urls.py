from django.urls import path

from . import views

app_name = "fire_detection"

urlpatterns = [
    path("", views.monitor, name="monitor"),
    path("stream/", views.video_stream, name="stream"),
    path("trang-thai/", views.status, name="status"),
    path("bat/", views.start, name="start"),
    path("tat/", views.stop, name="stop"),
]
