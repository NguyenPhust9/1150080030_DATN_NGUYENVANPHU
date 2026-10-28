from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import LoginHistory
from .services import get_client_ip, get_user_agent

User = get_user_model()


def _extract_session_key(request) -> str:
    if request is not None and hasattr(request, "session"):
        return (getattr(request.session, "session_key", None) or "")[:64]
    return ""


@receiver(user_logged_in)
def record_login_success(sender, request, user, **kwargs):
    if not user or not getattr(user, "pk", None):
        return
    # Skip recording when force_login is used by test runner unless it came through login view or normal auth backend
    if request is not None and getattr(request, "_skip_login_history", False):
        return
    LoginHistory.objects.create(
        user=user,
        username_attempted=user.username[:150],
        event_type=LoginHistory.EventType.LOGIN_SUCCESS,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        session_key=_extract_session_key(request),
        failure_reason="",
    )


@receiver(user_login_failed)
def record_login_failed(sender, credentials, request, **kwargs):
    raw_username = ""
    if isinstance(credentials, dict):
        raw_username = str(credentials.get("username") or "").strip()

    matched_user = None
    if raw_username:
        matched_user = User.objects.filter(username__iexact=raw_username).first()

    if matched_user is not None and not matched_user.is_active:
        failure_reason = "Tài khoản đã bị khóa"
    elif matched_user is not None:
        failure_reason = "Thông tin xác thực không hợp lệ"
    else:
        failure_reason = "Tài khoản không tồn tại hoặc thông tin không hợp lệ"

    LoginHistory.objects.create(
        user=matched_user,
        username_attempted=(raw_username or "(trống)")[:150],
        event_type=LoginHistory.EventType.LOGIN_FAILED,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        session_key=_extract_session_key(request),
        failure_reason=failure_reason,
    )


@receiver(user_logged_out)
def record_logout(sender, request, user, **kwargs):
    if not user or not getattr(user, "pk", None):
        return
    LoginHistory.objects.create(
        user=user,
        username_attempted=user.username[:150],
        event_type=LoginHistory.EventType.LOGOUT,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        session_key=_extract_session_key(request),
        failure_reason="",
    )

