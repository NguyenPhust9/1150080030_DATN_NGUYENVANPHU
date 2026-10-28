from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q

from .models import (
    Building,
    Contract,
    Conversation,
    Incident,
    Invoice,
    MeterReading,
    Notification,
    Payment,
    Room,
    Service,
    Tenant,
)

User = get_user_model()


def is_admin(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", None) == "admin")
    )


def is_owner(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and not user.is_superuser
        and getattr(user, "role", None) == "owner"
    )


def is_staff_role(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and not user.is_superuser
        and getattr(user, "role", None) == "staff"
    )


def is_tenant(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and not user.is_superuser
        and getattr(user, "role", None) == "tenant"
    )


def is_operator(user) -> bool:
    return is_admin(user) or is_owner(user) or is_staff_role(user)


def require_operator(user):
    if not is_operator(user):
        raise PermissionDenied("Bạn không có quyền truy cập khu vực quản lý.")


def get_tenant_profile(user) -> Tenant:
    try:
        return user.tenant_profile
    except (Tenant.DoesNotExist, AttributeError) as exc:
        raise PermissionDenied("Tài khoản chưa được liên kết với hồ sơ khách thuê.") from exc


def get_owner_ids_for_user(user) -> set:
    if not user or not user.is_authenticated:
        return set()
    if is_admin(user):
        return set(
            User.objects.filter(Q(role__in=["owner", "admin"]) | Q(is_superuser=True)).values_list(
                "id", flat=True
            )
        )
    if is_owner(user):
        return {user.pk}
    if is_staff_role(user):
        owner_ids = set(
            Building.objects.filter(staff=user).values_list("owner_id", flat=True)
        )
        if getattr(user, "managed_owner_id", None):
            owner_ids.add(user.managed_owner_id)
        return owner_ids
    return set()


def get_default_owner_for_operator(user):
    if is_owner(user):
        return user
    if is_staff_role(user):
        if getattr(user, "managed_owner_id", None):
            return user.managed_owner
        first_building = Building.objects.filter(staff=user).select_related("owner").first()
        if first_building:
            return first_building.owner
    if is_admin(user):
        return user
    return None


def get_accessible_buildings(user):
    if not user or not user.is_authenticated:
        return Building.objects.none()
    if is_admin(user):
        return Building.objects.all()
    if is_owner(user):
        return Building.objects.filter(owner=user)
    if is_staff_role(user):
        q = Q(staff=user)
        if getattr(user, "managed_owner_id", None):
            q |= Q(owner_id=user.managed_owner_id)
        return Building.objects.filter(q).distinct()
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        if not tenant:
            return Building.objects.none()
        return Building.objects.filter(
            Q(rooms__contracts__representative=tenant)
            | Q(rooms__contracts__members__tenant=tenant)
        ).distinct()
    return Building.objects.none()


def get_accessible_rooms(user):
    if not user or not user.is_authenticated:
        return Room.objects.none()
    if is_admin(user):
        return Room.objects.all()
    if is_owner(user) or is_staff_role(user):
        return Room.objects.filter(building__in=get_accessible_buildings(user))
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        if not tenant:
            return Room.objects.none()
        return Room.objects.filter(
            Q(contracts__representative=tenant) | Q(contracts__members__tenant=tenant)
        ).distinct()
    return Room.objects.none()


def get_accessible_tenants(user):
    if not user or not user.is_authenticated:
        return Tenant.objects.none()
    if is_admin(user):
        return Tenant.objects.all()
    if is_owner(user) or is_staff_role(user):
        buildings = get_accessible_buildings(user)
        owner_ids = get_owner_ids_for_user(user)
        q = (
            Q(represented_contracts__room__building__in=buildings)
            | Q(contract_memberships__contract__room__building__in=buildings)
        )
        if owner_ids:
            q |= Q(owner_id__in=owner_ids)
        return Tenant.objects.filter(q).distinct()
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        if not tenant:
            return Tenant.objects.none()
        return Tenant.objects.filter(pk=tenant.pk)
    return Tenant.objects.none()


def get_accessible_contracts(user):
    if not user or not user.is_authenticated:
        return Contract.objects.none()
    if is_admin(user):
        return Contract.objects.all()
    if is_owner(user) or is_staff_role(user):
        return Contract.objects.filter(room__building__in=get_accessible_buildings(user))
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        if not tenant:
            return Contract.objects.none()
        return Contract.objects.filter(
            Q(representative=tenant) | Q(members__tenant=tenant)
        ).distinct()
    return Contract.objects.none()


def get_accessible_meter_readings(user):
    if not user or not user.is_authenticated:
        return MeterReading.objects.none()
    if is_admin(user):
        return MeterReading.objects.all()
    if is_owner(user) or is_staff_role(user):
        return MeterReading.objects.filter(room__building__in=get_accessible_buildings(user))
    if is_tenant(user):
        return MeterReading.objects.filter(room__in=get_accessible_rooms(user))
    return MeterReading.objects.none()


def get_accessible_invoices(user):
    if not user or not user.is_authenticated:
        return Invoice.objects.none()
    if is_admin(user):
        return Invoice.objects.all()
    if is_owner(user) or is_staff_role(user):
        return Invoice.objects.filter(contract__room__building__in=get_accessible_buildings(user))
    if is_tenant(user):
        return Invoice.objects.filter(contract__in=get_accessible_contracts(user))
    return Invoice.objects.none()


def get_accessible_payments(user):
    if not user or not user.is_authenticated:
        return Payment.objects.none()
    if is_admin(user):
        return Payment.objects.all()
    if is_owner(user) or is_staff_role(user):
        return Payment.objects.filter(
            invoice__contract__room__building__in=get_accessible_buildings(user)
        )
    if is_tenant(user):
        return Payment.objects.filter(
            invoice__contract__in=get_accessible_contracts(user),
            is_void=False,
        )
    return Payment.objects.none()


def get_accessible_incidents(user):
    if not user or not user.is_authenticated:
        return Incident.objects.none()
    if is_admin(user):
        return Incident.objects.all()
    if is_owner(user) or is_staff_role(user):
        return Incident.objects.filter(room__building__in=get_accessible_buildings(user))
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        if not tenant:
            return Incident.objects.none()
        return Incident.objects.filter(reported_by=tenant)
    return Incident.objects.none()


def get_accessible_notifications(user):
    if not user or not user.is_authenticated:
        return Notification.objects.none()
    if is_admin(user):
        return Notification.objects.all()
    if is_owner(user) or is_staff_role(user):
        buildings = get_accessible_buildings(user)
        tenants = get_accessible_tenants(user)
        return Notification.objects.filter(
            Q(building__in=buildings)
            | Q(building__isnull=True, recipient__tenant_profile__in=tenants)
            | Q(created_by=user)
            | Q(recipient=user)
        ).distinct()
    if is_tenant(user):
        return Notification.objects.filter(recipient=user)
    return Notification.objects.none()


def get_accessible_services(user):
    if not user or not user.is_authenticated:
        return Service.objects.none()
    if is_admin(user):
        return Service.objects.all()
    if is_owner(user) or is_staff_role(user):
        owner_ids = get_owner_ids_for_user(user)
        return Service.objects.filter(Q(owner__isnull=True) | Q(owner_id__in=owner_ids))
    return Service.objects.filter(is_active=True)


def get_accessible_conversations(user):
    if not user or not user.is_authenticated:
        return Conversation.objects.none()
    queryset = Conversation.objects.select_related("tenant", "tenant__owner").prefetch_related("participants").order_by(
        F("last_message_at").desc(nulls_last=True), "-created_at", "-id"
    )
    if is_admin(user):
        return queryset
    if is_owner(user) or is_staff_role(user):
        return queryset.filter(tenant__in=get_accessible_tenants(user)).distinct()
    if is_tenant(user):
        tenant = getattr(user, "tenant_profile", None)
        return queryset.filter(tenant=tenant) if tenant else Conversation.objects.none()
    return Conversation.objects.none()


def get_accessible_queryset(user, resource: str):
    mapping = {
        "buildings": get_accessible_buildings,
        "rooms": get_accessible_rooms,
        "tenants": get_accessible_tenants,
        "contracts": get_accessible_contracts,
        "meters": get_accessible_meter_readings,
        "invoices": get_accessible_invoices,
        "payments": get_accessible_payments,
        "incidents": get_accessible_incidents,
        "notifications": get_accessible_notifications,
        "services": get_accessible_services,
    }
    getter = mapping.get(resource)
    if getter is None:
        raise KeyError(f"Unknown resource: {resource}")
    return getter(user)


def get_assignable_staff(user, building=None):
    if not user or not user.is_authenticated:
        return User.objects.none()
    if is_admin(user):
        if building is not None:
            return User.objects.filter(
                Q(is_superuser=True)
                | Q(role="admin")
                | Q(pk=building.owner_id)
                | Q(role="staff", managed_owner_id=building.owner_id)
                | Q(role="staff", assigned_buildings=building)
            ).distinct()
        return User.objects.filter(
            Q(is_superuser=True) | Q(role__in=["admin", "owner", "staff"])
        ).distinct()
    if is_owner(user):
        q = Q(pk=user.pk) | Q(role="staff", managed_owner=user) | Q(
            role="staff", assigned_buildings__owner=user
        )
        if building is not None:
            q = (
                Q(pk=building.owner_id)
                | Q(role="staff", managed_owner_id=building.owner_id)
                | Q(role="staff", assigned_buildings=building)
            )
        return User.objects.filter(q).distinct()
    if is_staff_role(user):
        owner_ids = get_owner_ids_for_user(user)
        buildings = get_accessible_buildings(user)
        q = Q(pk=user.pk) | Q(role="staff", assigned_buildings__in=buildings)
        if owner_ids:
            q |= Q(pk__in=owner_ids) | Q(role="staff", managed_owner_id__in=owner_ids)
        if building is not None:
            q &= (
                Q(pk=building.owner_id)
                | Q(role="staff", managed_owner_id=building.owner_id)
                | Q(role="staff", assigned_buildings=building)
            )
        return User.objects.filter(q).distinct()
    return User.objects.none()


# ==============================================================================
# CENTRALIZED PERMISSION REGISTRY & PERMISSION MATRIX
# ==============================================================================

ROLE_ORDER = ("admin", "owner", "staff", "tenant")

ROLE_LABELS = {
    "admin": "Quản trị viên (Admin)",
    "owner": "Chủ nhà (Owner)",
    "staff": "Nhân viên (Staff)",
    "tenant": "Khách thuê (Tenant)",
}

# Single source of truth for resource permissions across roles.
# Each resource defines for every role:
#   view, create, change, lock_or_cancel (bool), scope_label (str), and extra_codes (tuple[str, ...])
PERMISSION_MATRIX_DEFINITION = [
    {
        "key": "accounts",
        "name": "Quản lý tài khoản",
        "description": "Quản lý tài khoản người dùng, phân công phạm vi, khóa/mở và đặt lại mật khẩu.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn hệ thống (owner, staff, tenant)",
                "codes": (
                    "accounts.view_user",
                    "accounts.create_user",
                    "accounts.change_user",
                    "accounts.lock_user",
                    "accounts.reset_password",
                    "accounts.view_login_history",
                    "accounts.view_permission_matrix",
                ),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Staff và Tenant thuộc tòa nhà/chủ nhà của mình",
                "codes": (
                    "accounts.view_user",
                    "accounts.create_user",
                    "accounts.change_user",
                    "accounts.lock_user",
                    "accounts.reset_password",
                    "accounts.view_login_history",
                    "accounts.view_permission_matrix",
                ),
            },
            "staff": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ xem/sửa hồ sơ cá nhân và lịch sử đăng nhập của chính mình",
                "codes": (
                    "accounts.view_login_history",
                    "accounts.view_permission_matrix",
                ),
            },
            "tenant": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ xem/sửa hồ sơ cá nhân và lịch sử đăng nhập của chính mình",
                "codes": ("accounts.view_login_history",),
            },
        },
    },
    {
        "key": "buildings",
        "name": "Tòa nhà",
        "description": "Quản lý danh sách khu nhà/tòa nhà cho thuê và phân công nhân sự.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ tòa nhà",
                "codes": ("buildings.view", "buildings.create", "buildings.change", "buildings.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Tòa nhà do mình sở hữu",
                "codes": ("buildings.view", "buildings.create", "buildings.change", "buildings.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Tòa nhà được phân công hoặc thuộc chủ nhà quản lý",
                "codes": ("buildings.view", "buildings.create", "buildings.change"),
            },
            "tenant": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Không truy cập trang quản lý tòa nhà",
                "codes": (),
            },
        },
    },
    {
        "key": "rooms",
        "name": "Phòng",
        "description": "Quản lý phòng cho thuê, sơ đồ phòng, giá thuê và tiện nghi.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ phòng",
                "codes": ("rooms.view", "rooms.create", "rooms.change", "rooms.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Phòng thuộc tòa nhà mình sở hữu",
                "codes": ("rooms.view", "rooms.create", "rooms.change", "rooms.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Phòng thuộc tòa nhà được phân công",
                "codes": ("rooms.view", "rooms.create", "rooms.change"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ xem phòng đang thuê của chính mình",
                "codes": ("rooms.view",),
            },
        },
    },
    {
        "key": "tenants",
        "name": "Khách thuê",
        "description": "Quản lý hồ sơ khách thuê, liên kết tài khoản và lịch sử thuê.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ hồ sơ khách thuê",
                "codes": ("tenants.view", "tenants.create", "tenants.change", "tenants.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Khách thuê thuộc phạm vi tòa nhà của mình",
                "codes": ("tenants.view", "tenants.create", "tenants.change", "tenants.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Khách thuê thuộc tòa nhà được phân công",
                "codes": ("tenants.view", "tenants.create", "tenants.change", "tenants.lock_or_cancel"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Chỉ hồ sơ cá nhân của chính mình",
                "codes": ("tenants.view", "tenants.change"),
            },
        },
    },
    {
        "key": "contracts",
        "name": "Hợp đồng",
        "description": "Tạo, kích hoạt, gia hạn, thanh lý/hủy hợp đồng và quản lý người ở cùng.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ hợp đồng",
                "codes": ("contracts.view", "contracts.create", "contracts.change", "contracts.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Hợp đồng thuộc tòa nhà của mình",
                "codes": ("contracts.view", "contracts.create", "contracts.change", "contracts.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Hợp đồng thuộc tòa nhà được phân công",
                "codes": ("contracts.view", "contracts.create", "contracts.change", "contracts.lock_or_cancel"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ hợp đồng mà mình đứng tên hoặc ở cùng",
                "codes": ("contracts.view",),
            },
        },
    },
    {
        "key": "services",
        "name": "Dịch vụ",
        "description": "Danh mục dịch vụ (điện, nước, internet, vệ sinh, gửi xe...) và đơn giá.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ dịch vụ",
                "codes": ("services.view", "services.create", "services.change", "services.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Dịch vụ chung và dịch vụ thuộc chủ nhà",
                "codes": ("services.view", "services.create", "services.change", "services.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Dịch vụ thuộc chủ nhà quản lý",
                "codes": ("services.view", "services.create", "services.change"),
            },
            "tenant": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Xem gián tiếp qua hợp đồng và hóa đơn của mình",
                "codes": (),
            },
        },
    },
    {
        "key": "meters",
        "name": "Điện nước",
        "description": "Ghi chỉ số đồng hồ điện, nước định kỳ theo phòng.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Toàn bộ chỉ số điện nước",
                "codes": ("meters.view", "meters.create", "meters.change"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Chỉ số các phòng thuộc tòa nhà của mình",
                "codes": ("meters.view", "meters.create", "meters.change"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Chỉ số các phòng thuộc tòa nhà được phân công",
                "codes": ("meters.view", "meters.create", "meters.change"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Xem chỉ số phòng của mình trên hóa đơn",
                "codes": ("meters.view",),
            },
        },
    },
    {
        "key": "invoices",
        "name": "Hóa đơn",
        "description": "Tạo hóa đơn định kỳ/hàng loạt, phát hành và hủy hóa đơn.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ hóa đơn",
                "codes": ("invoices.view", "invoices.create", "invoices.change", "invoices.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Hóa đơn thuộc tòa nhà của mình",
                "codes": ("invoices.view", "invoices.create", "invoices.change", "invoices.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Hóa đơn thuộc tòa nhà được phân công",
                "codes": ("invoices.view", "invoices.create", "invoices.change", "invoices.lock_or_cancel"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ hóa đơn thuộc hợp đồng của chính mình",
                "codes": ("invoices.view",),
            },
        },
    },
    {
        "key": "payments",
        "name": "Thanh toán",
        "description": "Ghi nhận giao dịch thanh toán hóa đơn và hủy giao dịch sai.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": False,
                "lock_or_cancel": True,
                "scope": "Toàn bộ giao dịch thanh toán",
                "codes": ("payments.view", "payments.create", "payments.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": False,
                "lock_or_cancel": True,
                "scope": "Thanh toán thuộc tòa nhà của mình",
                "codes": ("payments.view", "payments.create", "payments.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": False,
                "lock_or_cancel": True,
                "scope": "Thanh toán thuộc tòa nhà được phân công",
                "codes": ("payments.view", "payments.create", "payments.lock_or_cancel"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Chỉ lịch sử thanh toán hợp lệ của chính mình",
                "codes": ("payments.view",),
            },
        },
    },
    {
        "key": "incidents",
        "name": "Sự cố",
        "description": "Tiếp nhận, phân công và cập nhật tiến độ xử lý sự cố/hỗ trợ.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Toàn bộ sự cố",
                "codes": ("incidents.view", "incidents.create", "incidents.change", "incidents.lock_or_cancel"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Sự cố thuộc tòa nhà của mình",
                "codes": ("incidents.view", "incidents.create", "incidents.change", "incidents.lock_or_cancel"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": True,
                "scope": "Sự cố thuộc tòa nhà được phân công",
                "codes": ("incidents.view", "incidents.create", "incidents.change", "incidents.lock_or_cancel"),
            },
            "tenant": {
                "view": True,
                "create": True,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Gửi và xem sự cố do chính mình báo cáo",
                "codes": ("incidents.view", "incidents.create"),
            },
        },
    },
    {
        "key": "notifications",
        "name": "Thông báo",
        "description": "Gửi thông báo theo tòa nhà/phòng/khách thuê và đánh dấu đã đọc.",
        "roles": {
            "admin": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Toàn bộ thông báo",
                "codes": ("notifications.view", "notifications.create", "notifications.change"),
            },
            "owner": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Thông báo thuộc tòa nhà/khách thuê của mình",
                "codes": ("notifications.view", "notifications.create", "notifications.change"),
            },
            "staff": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Thông báo thuộc tòa nhà được phân công",
                "codes": ("notifications.view", "notifications.create", "notifications.change"),
            },
            "tenant": {
                "view": True,
                "create": False,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Chỉ thông báo gửi cho chính mình (đánh dấu đã đọc)",
                "codes": ("notifications.view", "notifications.change"),
            },
        },
    },
    {
        "key": "dashboard",
        "name": "Dashboard",
        "description": "Bảng điều khiển tổng quan vận hành, công nợ, hợp đồng và sự cố.",
        "roles": {
            "admin": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Số liệu toàn hệ thống",
                "codes": ("dashboard.view",),
            },
            "owner": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Số liệu các tòa nhà của mình",
                "codes": ("dashboard.view",),
            },
            "staff": {
                "view": True,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Số liệu các tòa nhà được phân công",
                "codes": ("dashboard.view",),
            },
            "tenant": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Không truy cập Dashboard quản lý (dùng Cổng khách thuê)",
                "codes": (),
            },
        },
    },
    {
        "key": "tenant_portal",
        "name": "Cổng khách thuê",
        "description": "Giao diện dành riêng cho khách thuê tra cứu phòng, hợp đồng, hóa đơn, thanh toán và gửi sự cố.",
        "roles": {
            "admin": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Dành riêng cho vai trò Khách thuê",
                "codes": (),
            },
            "owner": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Dành riêng cho vai trò Khách thuê",
                "codes": (),
            },
            "staff": {
                "view": False,
                "create": False,
                "change": False,
                "lock_or_cancel": False,
                "scope": "Dành riêng cho vai trò Khách thuê",
                "codes": (),
            },
            "tenant": {
                "view": True,
                "create": True,
                "change": True,
                "lock_or_cancel": False,
                "scope": "Dữ liệu gắn với hồ sơ khách thuê của chính mình",
                "codes": ("tenant_portal.view", "tenant_portal.create", "tenant_portal.change"),
            },
        },
    },
]


def _build_role_permission_Lookup() -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = {role: set() for role in ROLE_ORDER}
    for resource in PERMISSION_MATRIX_DEFINITION:
        for role, rule in resource["roles"].items():
            for code in rule.get("codes", ()):
                lookup[role].add(code)
    return lookup


ROLE_PERMISSION_LOOKUP = _build_role_permission_Lookup()


def get_effective_role(user) -> str:
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    if is_admin(user):
        return "admin"
    return getattr(user, "role", "") or ""


def has_perm_code(user, perm_code: str) -> bool:
    role = get_effective_role(user)
    if not role:
        return False
    return perm_code in ROLE_PERMISSION_LOOKUP.get(role, set())


def require_perm_code(user, perm_code: str, message: str = "Bạn không có quyền thực hiện thao tác này."):
    if not has_perm_code(user, perm_code):
        raise PermissionDenied(message)


def get_permission_matrix() -> list[dict]:
    """Return structured permission matrix built directly from PERMISSION_MATRIX_DEFINITION."""
    rows = []
    for item in PERMISSION_MATRIX_DEFINITION:
        role_cells = []
        for role_key in ROLE_ORDER:
            r_data = item["roles"][role_key]
            role_cells.append({
                "role": role_key,
                "role_label": ROLE_LABELS[role_key],
                "view": r_data["view"],
                "create": r_data["create"],
                "change": r_data["change"],
                "lock_or_cancel": r_data["lock_or_cancel"],
                "scope": r_data["scope"],
                "codes": r_data.get("codes", ()),
            })
        rows.append({
            "key": item["key"],
            "name": item["name"],
            "description": item["description"],
            "role_cells": role_cells,
        })
    return rows


# ==============================================================================
# ACCOUNT MANAGEMENT SCOPING & AUTHORIZATION HELPERS
# ==============================================================================

def get_accessible_users(user):
    """
    Return queryset of User accounts visible in the Account Management module:
    - Admin/superuser: all accounts.
    - Owner: self + staff belonging to owner/owner's buildings + tenants linked to owner's tenant profiles/contracts.
    - Staff/Tenant: none in account management list.
    """
    if not user or not user.is_authenticated:
        return User.objects.none()
    if is_admin(user):
        return User.objects.all()
    if is_owner(user):
        q = (
            Q(pk=user.pk)
            | Q(role="staff", managed_owner=user)
            | Q(role="staff", assigned_buildings__owner=user)
            | Q(role="tenant", tenant_profile__owner=user)
            | Q(role="tenant", tenant_profile__represented_contracts__room__building__owner=user)
            | Q(role="tenant", tenant_profile__contract_memberships__contract__room__building__owner=user)
        )
        return (
            User.objects.filter(q)
            .exclude(is_superuser=True)
            .exclude(role="admin")
            .exclude(~Q(pk=user.pk) & Q(role="owner"))
            .distinct()
        )
    return User.objects.none()


def get_creatable_roles(user) -> list[tuple[str, str]]:
    """
    Roles that `user` is allowed to create via Account Management UI:
    - Admin: owner, staff, tenant
    - Owner: staff, tenant
    - Others: none
    """
    if is_admin(user):
        return [
            (User.Role.OWNER, "Chủ nhà"),
            (User.Role.STAFF, "Nhân viên"),
            (User.Role.TENANT, "Khách thuê"),
        ]
    if is_owner(user):
        return [
            (User.Role.STAFF, "Nhân viên"),
            (User.Role.TENANT, "Khách thuê"),
        ]
    return []


def can_view_user(actor, target_user) -> bool:
    if not actor or not actor.is_authenticated or not target_user:
        return False
    if not has_perm_code(actor, "accounts.view_user"):
        return False
    return get_accessible_users(actor).filter(pk=target_user.pk).exists()


def can_edit_user(actor, target_user) -> bool:
    if not actor or not actor.is_authenticated or not target_user:
        return False
    if not has_perm_code(actor, "accounts.change_user"):
        return False
    if target_user.is_superuser and actor.pk != target_user.pk:
        return False
    if is_admin(actor):
        return True
    if is_owner(actor):
        if target_user.pk == actor.pk:
            return True
        if target_user.role not in (User.Role.STAFF, User.Role.TENANT):
            return False
        return get_accessible_users(actor).filter(pk=target_user.pk).exists()
    return False


def is_last_active_admin(target_user) -> bool:
    if not (target_user.is_superuser or getattr(target_user, "role", None) == "admin"):
        return False
    if not target_user.is_active:
        return False
    other_active_admins = (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(role="admin"))
        .exclude(pk=target_user.pk)
        .exists()
    )
    return not other_active_admins


def can_lock_or_unlock_user(actor, target_user) -> tuple[bool, str]:
    """
    Return (allowed: bool, reason_if_denied: str) for locking/unlocking `target_user`.
    """
    if not actor or not actor.is_authenticated or not target_user:
        return False, "Bạn không có quyền thực hiện thao tác này."
    if not has_perm_code(actor, "accounts.lock_user"):
        return False, "Bạn không có quyền khóa hoặc mở khóa tài khoản."
    if actor.pk == target_user.pk:
        return False, "Không thể tự khóa hoặc mở khóa tài khoản của chính mình."
    if target_user.is_superuser:
        return False, "Không được phép khóa tài khoản Superuser."
    if is_owner(actor):
        if target_user.role not in (User.Role.STAFF, User.Role.TENANT):
            return False, "Chủ nhà chỉ được khóa/mở tài khoản nhân viên hoặc khách thuê trong phạm vi quản lý."
        if not get_accessible_users(actor).filter(pk=target_user.pk).exists():
            return False, "Tài khoản này nằm ngoài phạm vi quản lý của bạn."
    if target_user.is_active and is_last_active_admin(target_user):
        return False, "Không thể khóa quản trị viên (Admin) cuối cùng đang hoạt động."
    return True, ""


def can_reset_user_password(actor, target_user) -> tuple[bool, str]:
    """
    Return (allowed: bool, reason_if_denied: str) for resetting `target_user` password.
    """
    if not actor or not actor.is_authenticated or not target_user:
        return False, "Bạn không có quyền thực hiện thao tác này."
    if not has_perm_code(actor, "accounts.reset_password"):
        return False, "Bạn không có quyền đặt lại mật khẩu."
    if target_user.is_superuser:
        return False, "Không cho phép đặt lại mật khẩu của Superuser từ giao diện này."
    if is_admin(actor):
        return True, ""
    if is_owner(actor):
        if target_user.role not in (User.Role.STAFF, User.Role.TENANT):
            return False, "Chủ nhà chỉ được đặt lại mật khẩu của nhân viên hoặc khách thuê trong phạm vi."
        if not get_accessible_users(actor).filter(pk=target_user.pk).exists():
            return False, "Tài khoản này nằm ngoài phạm vi quản lý của bạn."
        return True, ""
    return False, "Bạn không có quyền đặt lại mật khẩu cho tài khoản khác."


def get_linkable_tenants_for_user(actor, current_user=None):
    """
    Return queryset of Tenant profiles in `actor`'s scope that do not have a linked account yet
    (plus the tenant currently linked to `current_user`, if any).
    """
    base_qs = get_accessible_tenants(actor)
    if current_user is not None and getattr(current_user, "pk", None):
        return base_qs.filter(Q(user__isnull=True) | Q(user=current_user)).distinct().order_by("full_name")
    return base_qs.filter(user__isnull=True).distinct().order_by("full_name")


def get_accessible_login_history(user):
    from apps.accounts.models import LoginHistory

    if not user or not user.is_authenticated:
        return LoginHistory.objects.none()
    if is_admin(user):
        return LoginHistory.objects.all()
    if is_owner(user):
        accessible_users = get_accessible_users(user)
        return LoginHistory.objects.filter(user__in=accessible_users)
    return LoginHistory.objects.filter(user=user)

