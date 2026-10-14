from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts import views as account_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("dang-nhap/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("dang-xuat/", auth_views.LogoutView.as_view(), name="logout"),
    path("doi-mat-khau/", account_views.CustomPasswordChangeView.as_view(), name="password-change"),
    path("ho-so/", account_views.profile_view, name="user-profile"),
    path("", include("apps.rentals.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
