from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class AccountSecurityMiddleware:
    """
    1. Immediately log out inactive/locked users if they still hold a session.
    2. Redirect users with `must_change_password=True` to the password change page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if not user.is_active:
                logout(request)
                messages.error(request, "Tài khoản của bạn đã bị khóa. Vui lòng liên hệ quản trị viên.")
                return redirect("login")

            if getattr(user, "must_change_password", False):
                password_change_path = reverse("password-change")
                logout_path = reverse("logout")
                login_path = reverse("login")
                allowed_prefixes = ("/static/", "/media/")
                if (
                    request.path not in (password_change_path, logout_path, login_path)
                    and not request.path.startswith(allowed_prefixes)
                ):
                    messages.warning(
                        request,
                        "Mật khẩu của bạn vừa được đặt lại. Vui lòng đổi mật khẩu mới để tiếp tục sử dụng hệ thống.",
                    )
                    return redirect("password-change")

        return self.get_response(request)

