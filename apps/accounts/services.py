import ipaddress

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
    validate_password,
)
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.rentals.models import Building, Tenant
from apps.rentals.permissions import (
    can_edit_user,
    can_lock_or_unlock_user,
    can_reset_user_password,
    get_accessible_buildings,
    get_accessible_tenants,
    get_creatable_roles,
    is_admin,
    is_owner,
    require_perm_code,
)

from .models import AccountAuditLog

User = get_user_model()

SENSITIVE_AUDIT_KEYS = ("password", "token", "secret", "hash", "credential")


def get_client_ip(request) -> str | None:
    """
    Safely extract client IP address from request.
    Only trusts X-Forwarded-For if explicitly enabled or when REMOTE_ADDR is absent/loopback.
    """
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    remote_addr = (meta.get("REMOTE_ADDR") or "").strip()
    trust_xff = getattr(settings, "TRUST_X_FORWARDED_FOR", False)

    candidates = []
    if trust_xff or remote_addr in ("", "127.0.0.1", "::1"):
        xff = (meta.get("HTTP_X_FORWARDED_FOR") or "").strip()
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                candidates.append(parts[0])
    if remote_addr:
        candidates.append(remote_addr)

    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None


def get_user_agent(request) -> str:
    if request is None:
        return ""
    meta = getattr(request, "META", {}) or {}
    return (meta.get("HTTP_USER_AGENT") or "")[:500]


def validate_account_password(password: str, user=None):
    """
    Validate password using Django's password validators.
    If settings.AUTH_PASSWORD_VALIDATORS is empty, applies standard Django validators
    so weak passwords (too short, all numeric, common, similar to username) are rejected.
    """
    if getattr(settings, "AUTH_PASSWORD_VALIDATORS", None):
        validate_password(password, user=user)
    else:
        default_validators = [
            UserAttributeSimilarityValidator(),
            MinimumLengthValidator(min_length=8),
            CommonPasswordValidator(),
            NumericPasswordValidator(),
        ]
        validate_password(password, user=user, password_validators=default_validators)


def sanitize_audit_changes(changes: dict | None) -> dict:
    if not changes:
        return {}
    clean = {}
    for key, val in changes.items():
        lower_key = str(key).lower()
        if any(s in lower_key for s in SENSITIVE_AUDIT_KEYS):
            continue
        clean[key] = val
    return clean


def log_account_audit(
    *,
    actor,
    target_user,
    action: str,
    request=None,
    reason: str = "",
    changes: dict | None = None,
) -> AccountAuditLog:
    return AccountAuditLog.objects.create(
        actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        target_user=target_user,
        action=action,
        ip_address=get_client_ip(request),
        reason=(reason or "")[:255],
        changes=sanitize_audit_changes(changes),
    )


def invalidate_user_sessions(user, exclude_session_key: str | None = None) -> int:
    """
    Invalidate all active Django database sessions belonging to `user`.
    """
    if not user or not getattr(user, "pk", None):
        return 0
    target_uid = str(user.pk)
    active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    if exclude_session_key:
        active_sessions = active_sessions.exclude(session_key=exclude_session_key)

    keys_to_delete = []
    for session in active_sessions.iterator():
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if str(data.get("_auth_user_id", "")) == target_uid:
            keys_to_delete.append(session.session_key)

    if keys_to_delete:
        Session.objects.filter(session_key__in=keys_to_delete).delete()
    return len(keys_to_delete)


def sync_user_and_tenant_profile(user: User, tenant: Tenant, *, prefer_user_fields: bool = True):
    """
    Synchronize full name, email, and phone between User and Tenant profile.
    """
    user_full_name = f"{user.last_name} {user.first_name}".strip() or user.get_full_name().strip()
    user_changed_fields = []
    tenant_changed_fields = ["user", "updated_at"]

    tenant.user = user

    if prefer_user_fields:
        if user_full_name:
            tenant.full_name = user_full_name
            tenant_changed_fields.append("full_name")
        elif tenant.full_name:
            parts = tenant.full_name.strip().rsplit(" ", 1)
            if len(parts) == 2:
                user.last_name, user.first_name = parts[0], parts[1]
            else:
                user.last_name, user.first_name = "", tenant.full_name.strip()
            user_changed_fields.extend(["first_name", "last_name"])

        if user.email:
            tenant.email = user.email
            tenant_changed_fields.append("email")
        elif tenant.email:
            user.email = tenant.email
            user_changed_fields.append("email")

        if user.phone:
            tenant.phone = user.phone
            tenant_changed_fields.append("phone")
        elif tenant.phone:
            user.phone = tenant.phone
            user_changed_fields.append("phone")
    else:
        if tenant.full_name:
            parts = tenant.full_name.strip().rsplit(" ", 1)
            if len(parts) == 2:
                user.last_name, user.first_name = parts[0], parts[1]
            else:
                user.last_name, user.first_name = "", tenant.full_name.strip()
            user_changed_fields.extend(["first_name", "last_name"])
        if tenant.email:
            user.email = tenant.email
            user_changed_fields.append("email")
        if tenant.phone:
            user.phone = tenant.phone
            user_changed_fields.append("phone")

    if user_changed_fields:
        user.save(update_fields=list(dict.fromkeys(user_changed_fields)))
    tenant.save(update_fields=list(dict.fromkeys(tenant_changed_fields)))


@transaction.atomic
def create_managed_user(
    *,
    actor: User,
    username: str,
    password: str,
    role: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    is_active: bool = True,
    managed_owner: User | None = None,
    assigned_buildings=None,
    owned_buildings=None,
    linked_tenant: Tenant | None = None,
    request=None,
) -> User:
    require_perm_code(actor, "accounts.create_user")
    allowed_roles = {r for r, _ in get_creatable_roles(actor)}
    if role not in allowed_roles:
        raise PermissionDenied("Bạn không có quyền tạo tài khoản với vai trò này.")

    normalized_username = User.normalize_username((username or "").strip())
    if not normalized_username:
        raise ValidationError({"username": "Tên đăng nhập không được để trống."})
    if User.objects.filter(username__iexact=normalized_username).exists():
        raise ValidationError({"username": "Tên đăng nhập đã tồn tại trong hệ thống."})

    assigned_building_list = list(assigned_buildings) if assigned_buildings is not None else []
    owned_building_list = list(owned_buildings) if owned_buildings is not None else []

    if role == User.Role.OWNER:
        if not is_admin(actor):
            raise PermissionDenied("Chỉ Quản trị viên (Admin) mới được tạo tài khoản Chủ nhà.")
        managed_owner = None
        assigned_building_list = []
        linked_tenant = None
    elif role == User.Role.STAFF:
        linked_tenant = None
        owned_building_list = []
        if is_owner(actor):
            if managed_owner is not None and managed_owner.pk != actor.pk:
                raise PermissionDenied("Chủ nhà chỉ được tạo nhân viên thuộc quyền quản lý của chính mình.")
            managed_owner = actor
            accessible_b_ids = set(get_accessible_buildings(actor).values_list("id", flat=True))
            for b in assigned_building_list:
                if b.pk not in accessible_b_ids:
                    raise PermissionDenied(f"Tòa nhà {b.name} không thuộc quyền sở hữu của bạn.")
        elif is_admin(actor):
            if managed_owner is not None and managed_owner.role != User.Role.OWNER:
                raise ValidationError({"managed_owner": "Chủ nhà quản lý phải có vai trò Chủ nhà."})
            if managed_owner is not None:
                for b in assigned_building_list:
                    if b.owner_id and b.owner_id != managed_owner.pk:
                        raise ValidationError(
                            {"assigned_buildings": f"Tòa nhà {b.name} không thuộc chủ nhà {managed_owner}."}
                        )
            elif assigned_building_list:
                owner_ids = {b.owner_id for b in assigned_building_list if b.owner_id}
                if len(owner_ids) == 1:
                    managed_owner = User.objects.filter(pk=next(iter(owner_ids))).first()
        if managed_owner is None and not assigned_building_list:
            raise ValidationError(
                "Tài khoản Nhân viên phải thuộc một Chủ nhà hoặc được phân công ít nhất một tòa nhà."
            )
    elif role == User.Role.TENANT:
        managed_owner = None
        assigned_building_list = []
        owned_building_list = []
        if linked_tenant is not None:
            accessible_tenants = get_accessible_tenants(actor)
            if not accessible_tenants.filter(pk=linked_tenant.pk).exists():
                raise PermissionDenied("Hồ sơ khách thuê không nằm trong phạm vi quản lý của bạn.")
            if linked_tenant.user_id is not None:
                raise ValidationError({"linked_tenant": "Hồ sơ khách thuê này đã được liên kết với một tài khoản khác."})

    user = User(
        username=normalized_username,
        first_name=(first_name or "").strip(),
        last_name=(last_name or "").strip(),
        email=(email or "").strip(),
        phone=(phone or "").strip(),
        role=role,
        is_active=bool(is_active),
        is_superuser=False,
        is_staff=False,
        managed_owner=managed_owner,
        password_changed_at=timezone.now(),
    )
    validate_account_password(password, user=user)
    user.set_password(password)
    user.save()

    if role == User.Role.OWNER and owned_building_list:
        Building.objects.filter(pk__in=[b.pk for b in owned_building_list]).update(owner=user)
    elif role == User.Role.STAFF and assigned_building_list:
        user.assigned_buildings.set(assigned_building_list)
    elif role == User.Role.TENANT and linked_tenant is not None:
        sync_user_and_tenant_profile(user, linked_tenant, prefer_user_fields=True)

    log_account_audit(
        actor=actor,
        target_user=user,
        action=AccountAuditLog.Action.CREATE_USER,
        request=request,
        changes={
            "username": user.username,
            "role": user.role,
            "is_active": user.is_active,
            "managed_owner": str(user.managed_owner_id) if user.managed_owner_id else None,
            "assigned_buildings": [str(b.pk) for b in assigned_building_list],
            "owned_buildings": [str(b.pk) for b in owned_building_list],
            "linked_tenant": str(linked_tenant.pk) if linked_tenant else None,
        },
    )
    if linked_tenant is not None:
        log_account_audit(
            actor=actor,
            target_user=user,
            action=AccountAuditLog.Action.LINK_TENANT,
            request=request,
            changes={"tenant_id": str(linked_tenant.pk), "tenant_name": linked_tenant.full_name},
        )
    return user


@transaction.atomic
def update_managed_user(
    *,
    actor: User,
    target_user: User,
    username: str,
    role: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    is_active: bool = True,
    managed_owner: User | None = None,
    assigned_buildings=None,
    owned_buildings=None,
    linked_tenant: Tenant | None = None,
    request=None,
) -> User:
    if not can_edit_user(actor, target_user):
        raise PermissionDenied("Bạn không có quyền chỉnh sửa tài khoản này.")

    # Không cho tự nâng vai trò của chính mình
    if actor.pk == target_user.pk and role != target_user.role:
        raise PermissionDenied("Bạn không được phép tự thay đổi vai trò của chính mình.")

    # Không cho nâng bất kỳ tài khoản nào lên admin nếu người sửa không phải admin hoặc từ giao diện tạo/sửa thường
    if role == User.Role.ADMIN and target_user.role != User.Role.ADMIN:
        raise PermissionDenied("Không được nâng vai trò lên Quản trị viên từ giao diện này.")

    if is_owner(actor) and role not in (User.Role.STAFF, User.Role.TENANT) and actor.pk != target_user.pk:
        raise PermissionDenied("Chủ nhà chỉ được phép gán vai trò Nhân viên hoặc Khách thuê.")

    normalized_username = User.normalize_username((username or "").strip())
    if not normalized_username:
        raise ValidationError({"username": "Tên đăng nhập không được để trống."})
    if User.objects.filter(username__iexact=normalized_username).exclude(pk=target_user.pk).exists():
        raise ValidationError({"username": "Tên đăng nhập đã tồn tại trong hệ thống."})

    # Kiểm tra nếu thay đổi trạng thái is_active qua form sửa
    if bool(is_active) != bool(target_user.is_active):
        allowed_lock, lock_msg = can_lock_or_unlock_user(actor, target_user)
        if not allowed_lock:
            raise ValidationError({"is_active": lock_msg})

    assigned_building_list = list(assigned_buildings) if assigned_buildings is not None else []
    owned_building_list = list(owned_buildings) if owned_buildings is not None else None

    if role == User.Role.OWNER:
        if not is_admin(actor) and actor.pk != target_user.pk:
            raise PermissionDenied("Chỉ Quản trị viên mới được phép chỉnh sửa tài khoản Chủ nhà.")
        managed_owner = None
        assigned_building_list = []
        linked_tenant = None
    elif role == User.Role.STAFF:
        linked_tenant = None
        owned_building_list = None
        if is_owner(actor):
            if managed_owner is not None and managed_owner.pk != actor.pk:
                raise PermissionDenied("Chủ nhà chỉ được phân công nhân viên cho chính mình.")
            managed_owner = actor
            accessible_b_ids = set(get_accessible_buildings(actor).values_list("id", flat=True))
            for b in assigned_building_list:
                if b.pk not in accessible_b_ids:
                    raise PermissionDenied(f"Tòa nhà {b.name} không thuộc quyền sở hữu của bạn.")
        elif is_admin(actor):
            if managed_owner is not None and managed_owner.role != User.Role.OWNER:
                raise ValidationError({"managed_owner": "Chủ nhà quản lý phải có vai trò Chủ nhà."})
            if managed_owner is not None:
                for b in assigned_building_list:
                    if b.owner_id and b.owner_id != managed_owner.pk:
                        raise ValidationError(
                            {"assigned_buildings": f"Tòa nhà {b.name} không thuộc chủ nhà {managed_owner}."}
                        )
            elif assigned_building_list:
                owner_ids = {b.owner_id for b in assigned_building_list if b.owner_id}
                if len(owner_ids) == 1:
                    managed_owner = User.objects.filter(pk=next(iter(owner_ids))).first()
        if managed_owner is None and not assigned_building_list:
            raise ValidationError(
                "Tài khoản Nhân viên phải thuộc một Chủ nhà hoặc được phân công ít nhất một tòa nhà."
            )
    elif role == User.Role.TENANT:
        managed_owner = None
        assigned_building_list = []
        owned_building_list = None
        if linked_tenant is not None:
            accessible_tenants = get_accessible_tenants(actor)
            if not accessible_tenants.filter(pk=linked_tenant.pk).exists():
                raise PermissionDenied("Hồ sơ khách thuê không nằm trong phạm vi quản lý của bạn.")
            if linked_tenant.user_id is not None and linked_tenant.user_id != target_user.pk:
                raise ValidationError({"linked_tenant": "Hồ sơ khách thuê này đã được liên kết với một tài khoản khác."})

    old_snapshot = {
        "username": target_user.username,
        "first_name": target_user.first_name,
        "last_name": target_user.last_name,
        "email": target_user.email,
        "phone": target_user.phone,
        "role": target_user.role,
        "is_active": target_user.is_active,
        "managed_owner": str(target_user.managed_owner_id) if target_user.managed_owner_id else None,
    }
    was_active = target_user.is_active

    target_user.username = normalized_username
    target_user.first_name = (first_name or "").strip()
    target_user.last_name = (last_name or "").strip()
    target_user.email = (email or "").strip()
    target_user.phone = (phone or "").strip()
    target_user.role = role
    target_user.is_active = bool(is_active)
    target_user.managed_owner = managed_owner
    if was_active and not target_user.is_active:
        target_user.locked_at = timezone.now()
        target_user.locked_by = actor
    elif not was_active and target_user.is_active:
        target_user.locked_at = None
        target_user.locked_by = None
    target_user.save()

    if was_active and not target_user.is_active:
        invalidate_user_sessions(target_user)

    # Cập nhật phân công tòa nhà
    if role == User.Role.STAFF:
        target_user.assigned_buildings.set(assigned_building_list)
    else:
        target_user.assigned_buildings.clear()

    if role == User.Role.OWNER and is_admin(actor) and owned_building_list is not None:
        Building.objects.filter(pk__in=[b.pk for b in owned_building_list]).update(owner=target_user)

    # Cập nhật liên kết hồ sơ khách thuê
    existing_tenant = getattr(target_user, "tenant_profile", None)
    if role != User.Role.TENANT:
        if existing_tenant is not None:
            old_t_id = str(existing_tenant.pk)
            existing_tenant.user = None
            existing_tenant.save(update_fields=["user", "updated_at"])
            log_account_audit(
                actor=actor,
                target_user=target_user,
                action=AccountAuditLog.Action.UNLINK_TENANT,
                request=request,
                changes={"unlinked_tenant_id": old_t_id},
            )
    else:
        if existing_tenant is not None and (linked_tenant is None or existing_tenant.pk != linked_tenant.pk):
            old_t_id = str(existing_tenant.pk)
            existing_tenant.user = None
            existing_tenant.save(update_fields=["user", "updated_at"])
            log_account_audit(
                actor=actor,
                target_user=target_user,
                action=AccountAuditLog.Action.UNLINK_TENANT,
                request=request,
                changes={"unlinked_tenant_id": old_t_id},
            )
        if linked_tenant is not None:
            was_different = existing_tenant is None or existing_tenant.pk != linked_tenant.pk
            sync_user_and_tenant_profile(target_user, linked_tenant, prefer_user_fields=True)
            if was_different:
                log_account_audit(
                    actor=actor,
                    target_user=target_user,
                    action=AccountAuditLog.Action.LINK_TENANT,
                    request=request,
                    changes={"tenant_id": str(linked_tenant.pk), "tenant_name": linked_tenant.full_name},
                )

    new_snapshot = {
        "username": target_user.username,
        "first_name": target_user.first_name,
        "last_name": target_user.last_name,
        "email": target_user.email,
        "phone": target_user.phone,
        "role": target_user.role,
        "is_active": target_user.is_active,
        "managed_owner": str(target_user.managed_owner_id) if target_user.managed_owner_id else None,
    }
    diff = {
        k: {"from": old_snapshot[k], "to": new_snapshot[k]}
        for k in old_snapshot
        if old_snapshot[k] != new_snapshot[k]
    }
    log_account_audit(
        actor=actor,
        target_user=target_user,
        action=AccountAuditLog.Action.UPDATE_USER,
        request=request,
        changes=diff or {"updated": True},
    )
    return target_user


@transaction.atomic
def lock_or_unlock_user_account(
    *,
    actor: User,
    target_user: User,
    lock: bool,
    reason: str = "",
    request=None,
) -> User:
    allowed, denial_reason = can_lock_or_unlock_user(actor, target_user)
    if not allowed:
        raise PermissionDenied(denial_reason)

    clean_reason = (reason or "").strip()
    if lock:
        target_user.is_active = False
        target_user.locked_at = timezone.now()
        target_user.locked_by = actor
        target_user.lock_reason = clean_reason
        target_user.save(update_fields=["is_active", "locked_at", "locked_by", "lock_reason"])
        invalidated_count = invalidate_user_sessions(target_user)
        log_account_audit(
            actor=actor,
            target_user=target_user,
            action=AccountAuditLog.Action.LOCK_USER,
            request=request,
            reason=clean_reason,
            changes={"is_active": False, "invalidated_sessions": invalidated_count},
        )
    else:
        target_user.is_active = True
        target_user.locked_at = None
        target_user.locked_by = None
        target_user.lock_reason = clean_reason
        target_user.save(update_fields=["is_active", "locked_at", "locked_by", "lock_reason"])
        log_account_audit(
            actor=actor,
            target_user=target_user,
            action=AccountAuditLog.Action.UNLOCK_USER,
            request=request,
            reason=clean_reason,
            changes={"is_active": True},
        )
    return target_user


@transaction.atomic
def admin_reset_user_password(
    *,
    actor: User,
    target_user: User,
    new_password: str,
    must_change_password: bool = True,
    reason: str = "",
    request=None,
) -> User:
    allowed, denial_reason = can_reset_user_password(actor, target_user)
    if not allowed:
        raise PermissionDenied(denial_reason)

    validate_account_password(new_password, user=target_user)
    target_user.set_password(new_password)
    target_user.must_change_password = bool(must_change_password)
    target_user.password_changed_at = timezone.now()
    target_user.save(update_fields=["password", "must_change_password", "password_changed_at"])

    exclude_key = None
    if request is not None and actor.pk == target_user.pk and hasattr(request, "session"):
        exclude_key = request.session.session_key
    invalidated_count = invalidate_user_sessions(target_user, exclude_session_key=exclude_key)

    log_account_audit(
        actor=actor,
        target_user=target_user,
        action=AccountAuditLog.Action.RESET_PASSWORD,
        request=request,
        reason=(reason or "").strip(),
        changes={
            "must_change_password": target_user.must_change_password,
            "invalidated_sessions": invalidated_count,
        },
    )
    return target_user

