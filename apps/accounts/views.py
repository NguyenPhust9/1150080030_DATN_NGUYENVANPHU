from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Q, Value
from django.db.models.functions import Concat
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from apps.rentals.permissions import (
    ROLE_LABELS,
    ROLE_ORDER,
    can_edit_user,
    can_lock_or_unlock_user,
    can_reset_user_password,
    get_accessible_buildings,
    get_accessible_login_history,
    get_accessible_users,
    get_permission_matrix,
    has_perm_code,
    is_admin,
    is_owner,
    require_perm_code,
)

from .forms import (
    AdminPasswordResetForm,
    StyledPasswordChangeForm,
    TenantProfileForm,
    UserCreateForm,
    UserLockUnlockForm,
    UserProfileForm,
    UserUpdateForm,
)
from .models import AccountAuditLog, LoginHistory
from .services import (
    admin_reset_user_password,
    create_managed_user,
    lock_or_unlock_user_account,
    log_account_audit,
    update_managed_user,
)

User = get_user_model()


class CustomPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("password-change")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save(update_fields=["must_change_password", "password_changed_at"])
        log_account_audit(
            actor=user,
            target_user=user,
            action=AccountAuditLog.Action.CHANGE_PASSWORD,
            request=self.request,
            changes={"self_changed": True, "must_change_password": False},
        )
        messages.success(self.request, "Đổi mật khẩu thành công! Mật khẩu mới đã được kích hoạt.")
        return response


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    user = request.user
    tenant = getattr(user, "tenant_profile", None)
    is_tenant_account = (user.role == "tenant") and (tenant is not None)

    if is_tenant_account:
        if request.method == "POST":
            form = TenantProfileForm(request.POST, instance=tenant)
            if form.is_valid():
                tenant = form.save()
                if tenant.email:
                    user.email = tenant.email
                if tenant.phone:
                    user.phone = tenant.phone
                parts = tenant.full_name.strip().rsplit(" ", 1)
                if len(parts) == 2:
                    user.last_name, user.first_name = parts[0], parts[1]
                else:
                    user.first_name = tenant.full_name.strip()
                    user.last_name = ""
                user.save(update_fields=["email", "phone", "first_name", "last_name"])
                messages.success(request, "Cập nhật hồ sơ khách thuê thành công!")
                return redirect("user-profile")
        else:
            form = TenantProfileForm(instance=tenant)
    else:
        if request.method == "POST":
            form = UserProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                messages.success(request, "Cập nhật hồ sơ tài khoản thành công!")
                return redirect("user-profile")
        else:
            form = UserProfileForm(instance=user)

    recent_login_history = LoginHistory.objects.filter(user=user).order_by("-occurred_at")[:10]
    context = {
        "title": "Hồ sơ cá nhân",
        "form": form,
        "is_tenant": is_tenant_account,
        "tenant": tenant,
        "recent_login_history": recent_login_history,
    }
    return render(request, "accounts/profile.html", context)


@login_required
@require_http_methods(["GET"])
def account_list(request):
    require_perm_code(request.user, "accounts.view_user")
    queryset = (
        get_accessible_users(request.user)
        .select_related("managed_owner", "tenant_profile", "locked_by")
        .prefetch_related("assigned_buildings", "buildings")
        .annotate(
            full_name_concat=Concat("last_name", Value(" "), "first_name"),
        )
    )

    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    status = request.GET.get("status", "").strip()
    owner_id = request.GET.get("owner", "").strip()
    building_id = request.GET.get("building", "").strip()
    sort = request.GET.get("sort", "newest").strip()

    if q:
        queryset = queryset.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(full_name_concat__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
        )

    valid_roles = {r for r, _ in User.Role.choices}
    if role in valid_roles:
        queryset = queryset.filter(role=role)
    else:
        role = ""

    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "locked":
        queryset = queryset.filter(is_active=False)
    else:
        status = ""

    accessible_buildings = get_accessible_buildings(request.user).order_by("name")
    owners_qs = User.objects.filter(role=User.Role.OWNER).order_by("username") if is_admin(request.user) else User.objects.none()

    if owner_id and is_admin(request.user):
        queryset = queryset.filter(
            Q(pk=owner_id)
            | Q(managed_owner_id=owner_id)
            | Q(assigned_buildings__owner_id=owner_id)
            | Q(tenant_profile__owner_id=owner_id)
        ).distinct()
    else:
        owner_id = ""

    if building_id and accessible_buildings.filter(pk=building_id).exists():
        queryset = queryset.filter(
            Q(assigned_buildings__pk=building_id)
            | Q(buildings__pk=building_id)
            | Q(tenant_profile__represented_contracts__room__building_id=building_id)
            | Q(tenant_profile__contract_memberships__contract__room__building_id=building_id)
        ).distinct()
    else:
        building_id = ""

    if sort == "name":
        queryset = queryset.order_by("last_name", "first_name", "username")
    elif sort == "last_login":
        queryset = queryset.order_by(F("last_login").desc(nulls_last=True), "-date_joined")
    elif sort == "oldest":
        queryset = queryset.order_by("date_joined", "username")
    else:
        sort = "newest"
        queryset = queryset.order_by("-date_joined", "username")

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    for account in page_obj.object_list:
        account.can_edit = can_edit_user(request.user, account)
        account.can_lock, account.lock_denied_reason = can_lock_or_unlock_user(request.user, account)
        account.can_reset_pw, account.reset_pw_denied_reason = can_reset_user_password(request.user, account)

    filter_params = {}
    if q:
        filter_params["q"] = q
    if role:
        filter_params["role"] = role
    if status:
        filter_params["status"] = status
    if owner_id:
        filter_params["owner"] = owner_id
    if building_id:
        filter_params["building"] = building_id
    if sort and sort != "newest":
        filter_params["sort"] = sort

    base_scope_qs = get_accessible_users(request.user)
    context = {
        "objects": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q,
        "role": role,
        "role_choices": User.Role.choices if is_admin(request.user) else [
            (User.Role.OWNER, "Chủ nhà"),
            (User.Role.STAFF, "Nhân viên"),
            (User.Role.TENANT, "Khách thuê"),
        ],
        "status": status,
        "selected_owner": owner_id,
        "owners": owners_qs,
        "selected_building": building_id,
        "buildings": accessible_buildings,
        "sort": sort,
        "filter_query": urlencode(filter_params),
        "total_accounts": base_scope_qs.count(),
        "active_accounts": base_scope_qs.filter(is_active=True).count(),
        "locked_accounts": base_scope_qs.filter(is_active=False).count(),
        "can_create_account": has_perm_code(request.user, "accounts.create_user"),
    }
    return render(request, "accounts/account_list.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def account_create(request):
    require_perm_code(request.user, "accounts.create_user")
    if request.method == "POST":
        form = UserCreateForm(request.POST, actor=request.user)
        if form.is_valid():
            try:
                new_user = create_managed_user(
                    actor=request.user,
                    username=form.cleaned_data["username"],
                    password=form.cleaned_data["password1"],
                    role=form.cleaned_data["role"],
                    first_name=form.cleaned_data.get("first_name", ""),
                    last_name=form.cleaned_data.get("last_name", ""),
                    email=form.cleaned_data.get("email", ""),
                    phone=form.cleaned_data.get("phone", ""),
                    is_active=form.cleaned_data.get("is_active", True),
                    managed_owner=form.cleaned_data.get("managed_owner"),
                    assigned_buildings=form.cleaned_data.get("assigned_buildings"),
                    owned_buildings=form.cleaned_data.get("owned_buildings"),
                    linked_tenant=form.cleaned_data.get("linked_tenant"),
                    request=request,
                )
                messages.success(
                    request,
                    f"Đã tạo tài khoản '{new_user.username}' ({new_user.get_role_display()}) thành công.",
                )
                return redirect("account-detail", user_id=new_user.pk)
            except ValidationError as exc:
                if hasattr(exc, "error_dict"):
                    for field, errors in exc.error_dict.items():
                        for err in errors:
                            form.add_error(field if field in form.fields else None, err)
                else:
                    for err in exc.messages:
                        form.add_error(None, err)
    else:
        form = UserCreateForm(actor=request.user)

    return render(
        request,
        "accounts/account_form.html",
        {
            "form": form,
            "is_create": True,
            "title": "Thêm tài khoản mới",
            "is_admin_actor": is_admin(request.user),
            "is_owner_actor": is_owner(request.user),
        },
    )


@login_required
@require_http_methods(["GET"])
def account_detail(request, user_id):
    require_perm_code(request.user, "accounts.view_user")
    target_user = get_object_or_404(
        get_accessible_users(request.user)
        .select_related("managed_owner", "tenant_profile", "locked_by")
        .prefetch_related("assigned_buildings", "buildings"),
        pk=user_id,
    )
    can_edit = can_edit_user(request.user, target_user)
    can_lock, lock_denied_reason = can_lock_or_unlock_user(request.user, target_user)
    can_reset_pw, reset_pw_denied_reason = can_reset_user_password(request.user, target_user)

    login_histories = LoginHistory.objects.filter(user=target_user).order_by("-occurred_at")[:15]
    audit_logs = (
        AccountAuditLog.objects.filter(target_user=target_user)
        .select_related("actor")
        .order_by("-occurred_at")[:20]
    )
    lock_form = UserLockUnlockForm(initial={"reason": target_user.lock_reason})

    return render(
        request,
        "accounts/account_detail.html",
        {
            "target_user": target_user,
            "can_edit": can_edit,
            "can_lock": can_lock,
            "lock_denied_reason": lock_denied_reason,
            "can_reset_pw": can_reset_pw,
            "reset_pw_denied_reason": reset_pw_denied_reason,
            "login_histories": login_histories,
            "audit_logs": audit_logs,
            "lock_form": lock_form,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def account_update(request, user_id):
    require_perm_code(request.user, "accounts.change_user")
    target_user = get_object_or_404(
        get_accessible_users(request.user).select_related("managed_owner", "tenant_profile"),
        pk=user_id,
    )
    if not can_edit_user(request.user, target_user):
        raise PermissionDenied("Bạn không có quyền chỉnh sửa tài khoản này.")

    if request.method == "POST":
        form = UserUpdateForm(request.POST, actor=request.user, instance=target_user)
        if form.is_valid():
            try:
                updated_user = update_managed_user(
                    actor=request.user,
                    target_user=target_user,
                    username=form.cleaned_data["username"],
                    role=form.cleaned_data["role"],
                    first_name=form.cleaned_data.get("first_name", ""),
                    last_name=form.cleaned_data.get("last_name", ""),
                    email=form.cleaned_data.get("email", ""),
                    phone=form.cleaned_data.get("phone", ""),
                    is_active=form.cleaned_data.get("is_active", False),
                    managed_owner=form.cleaned_data.get("managed_owner"),
                    assigned_buildings=form.cleaned_data.get("assigned_buildings"),
                    owned_buildings=form.cleaned_data.get("owned_buildings"),
                    linked_tenant=form.cleaned_data.get("linked_tenant"),
                    request=request,
                )
                messages.success(request, f"Đã cập nhật thông tin tài khoản '{updated_user.username}'.")
                return redirect("account-detail", user_id=updated_user.pk)
            except ValidationError as exc:
                if hasattr(exc, "error_dict"):
                    for field, errors in exc.error_dict.items():
                        for err in errors:
                            form.add_error(field if field in form.fields else None, err)
                else:
                    for err in exc.messages:
                        form.add_error(None, err)
    else:
        form = UserUpdateForm(actor=request.user, instance=target_user)

    return render(
        request,
        "accounts/account_form.html",
        {
            "form": form,
            "is_create": False,
            "target_user": target_user,
            "title": f"Chỉnh sửa tài khoản: {target_user.username}",
            "is_admin_actor": is_admin(request.user),
            "is_owner_actor": is_owner(request.user),
        },
    )


@login_required
@require_POST
def account_toggle_lock(request, user_id):
    require_perm_code(request.user, "accounts.lock_user")
    target_user = get_object_or_404(get_accessible_users(request.user), pk=user_id)
    allowed, denial_reason = can_lock_or_unlock_user(request.user, target_user)
    if not allowed:
        raise PermissionDenied(denial_reason)

    form = UserLockUnlockForm(request.POST)
    reason = ""
    if form.is_valid():
        reason = form.cleaned_data.get("reason", "")

    lock_action = target_user.is_active
    lock_or_unlock_user_account(
        actor=request.user,
        target_user=target_user,
        lock=lock_action,
        reason=reason,
        request=request,
    )
    if lock_action:
        messages.success(request, f"Đã khóa tài khoản '{target_user.username}' và hủy các phiên đăng nhập hiện tại.")
    else:
        messages.success(request, f"Đã mở khóa tài khoản '{target_user.username}'.")

    next_url = request.POST.get("next", "").strip()
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("account-detail", user_id=target_user.pk)


@login_required
@require_http_methods(["GET", "POST"])
def account_reset_password(request, user_id):
    require_perm_code(request.user, "accounts.reset_password")
    target_user = get_object_or_404(get_accessible_users(request.user), pk=user_id)
    allowed, denial_reason = can_reset_user_password(request.user, target_user)
    if not allowed:
        raise PermissionDenied(denial_reason)

    if request.method == "POST":
        form = AdminPasswordResetForm(request.POST, target_user=target_user)
        if form.is_valid():
            admin_reset_user_password(
                actor=request.user,
                target_user=target_user,
                new_password=form.cleaned_data["new_password1"],
                must_change_password=form.cleaned_data.get("must_change_password", True),
                reason=form.cleaned_data.get("reason", ""),
                request=request,
            )
            messages.success(
                request,
                f"Đã đặt lại mật khẩu cho tài khoản '{target_user.username}' thành công.",
            )
            return redirect("account-detail", user_id=target_user.pk)
    else:
        form = AdminPasswordResetForm(target_user=target_user)

    return render(
        request,
        "accounts/account_reset_password.html",
        {
            "form": form,
            "target_user": target_user,
            "title": f"Đặt lại mật khẩu: {target_user.username}",
        },
    )


@login_required
@require_http_methods(["GET"])
def login_history_list(request):
    require_perm_code(request.user, "accounts.view_login_history")
    queryset = get_accessible_login_history(request.user).select_related("user")

    q = request.GET.get("q", "").strip()
    event_type = request.GET.get("event_type", "").strip()
    selected_user = request.GET.get("user", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    if q:
        queryset = queryset.filter(
            Q(username_attempted__icontains=q)
            | Q(user__username__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(failure_reason__icontains=q)
        )

    valid_events = {choice for choice, _ in LoginHistory.EventType.choices}
    if event_type in valid_events:
        queryset = queryset.filter(event_type=event_type)
    else:
        event_type = ""

    accessible_users = get_accessible_users(request.user).order_by("username")
    if selected_user and accessible_users.filter(pk=selected_user).exists():
        queryset = queryset.filter(user_id=selected_user)
    else:
        selected_user = ""

    parsed_from = parse_date(date_from) if date_from else None
    parsed_to = parse_date(date_to) if date_to else None
    if parsed_from:
        queryset = queryset.filter(occurred_at__date__gte=parsed_from)
    else:
        date_from = ""
    if parsed_to:
        queryset = queryset.filter(occurred_at__date__lte=parsed_to)
    else:
        date_to = ""

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    filter_params = {}
    if q:
        filter_params["q"] = q
    if event_type:
        filter_params["event_type"] = event_type
    if selected_user:
        filter_params["user"] = selected_user
    if date_from:
        filter_params["date_from"] = date_from
    if date_to:
        filter_params["date_to"] = date_to

    return render(
        request,
        "accounts/login_history.html",
        {
            "objects": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "q": q,
            "event_type": event_type,
            "event_type_choices": LoginHistory.EventType.choices,
            "selected_user": selected_user,
            "accessible_users": accessible_users,
            "date_from": date_from,
            "date_to": date_to,
            "filter_query": urlencode(filter_params),
        },
    )


@login_required
@require_http_methods(["GET"])
def permission_matrix_view(request):
    require_perm_code(request.user, "accounts.view_permission_matrix")
    matrix_rows = get_permission_matrix()
    role_headers = [{"key": r, "label": ROLE_LABELS[r]} for r in ROLE_ORDER]
    return render(
        request,
        "accounts/permission_matrix.html",
        {
            "matrix_rows": matrix_rows,
            "role_headers": role_headers,
        },
    )
