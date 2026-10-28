import json
import os
import time
from urllib.parse import unquote, urlparse

import cloudinary
import cloudinary.uploader
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from cloudinary.utils import api_sign_request
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, F, Min, OuterRef, ProtectedError, Q, Subquery, Sum
from django.db.models.functions import Abs
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    BuildingForm,
    ContractForm,
    ContractMemberForm,
    ContractRenewForm,
    ContractServiceForm,
    IncidentManageForm,
    InvoiceBulkCreateForm,
    InvoiceCancelForm,
    InvoiceCreateForm,
    InvoiceDraftUpdateForm,
    InvoiceItemForm,
    MeterReadingForm,
    NotificationCreateForm,
    PaymentCreateForm,
    RoomForm,
    ServiceForm,
    TenantForm,
    TenantIncidentForm,
    TenantUserLinkForm,
)
from .models import (
    Amenity,
    Building,
    ChatMessage,
    Contract,
    Conversation,
    Incident,
    Invoice,
    MeterReading,
    Notification,
    Payment,
    Room,
    RoomMedia,
    Service,
    Tenant,
)
from .permissions import (
    get_accessible_buildings,
    get_accessible_contracts,
    get_accessible_conversations,
    get_accessible_incidents,
    get_accessible_invoices,
    get_accessible_notifications,
    get_accessible_payments,
    get_accessible_queryset,
    get_accessible_rooms,
    get_accessible_services,
    get_accessible_tenants,
    get_default_owner_for_operator,
    get_tenant_profile,
    is_admin,
    is_owner,
    is_staff_role,
    is_tenant,
    require_operator,
)
from .services import (
    activate_contract,
    add_contract_member,
    add_invoice_item,
    attach_contract_service,
    cancel_contract,
    cancel_invoice,
    create_monthly_invoice,
    generate_bulk_invoices,
    get_previous_meter_reading_value,
    issue_invoice,
    notify_expiring_contracts,
    recalculate_invoice,
    record_payment,
    remove_contract_member,
    remove_contract_service,
    remove_invoice_item,
    renew_contract,
    send_targeted_notifications,
    terminate_contract,
    update_incident_management,
    void_payment,
)


def _is_tenant(user):
    return is_tenant(user)


def _require_operator(user):
    require_operator(user)


def _tenant_profile(user):
    return get_tenant_profile(user)


def _tenant_contracts(tenant):
    return Contract.objects.filter(Q(representative=tenant) | Q(members__tenant=tenant)).distinct()


def _with_cover_image(rooms):
    latest_image = RoomMedia.objects.filter(
        room_id=OuterRef("pk"), media_type=RoomMedia.MediaType.IMAGE
    ).order_by("-is_primary", "-created_at", "-id")
    return rooms.annotate(cover_image_url=Subquery(latest_image.values("url")[:1]))


def _apply_primary_image(room, selection, new_images):
    """Keep an existing cover unless the operator explicitly selects another image."""
    selected = None
    if selection.startswith("new:"):
        try:
            selected = new_images[int(selection[4:])]
        except (ValueError, IndexError):
            pass
    elif selection.startswith("existing:"):
        try:
            selected = room.media.filter(pk=selection[9:], media_type=RoomMedia.MediaType.IMAGE).first()
        except (ValueError, ValidationError):
            pass
    if selected is None and not room.media.filter(media_type=RoomMedia.MediaType.IMAGE, is_primary=True).exists():
        selected = room.media.filter(media_type=RoomMedia.MediaType.IMAGE).order_by("-created_at", "-id").first()
    if selected is not None:
        room.media.filter(media_type=RoomMedia.MediaType.IMAGE, is_primary=True).update(is_primary=False)
        room.media.filter(pk=selected.pk).update(is_primary=True)


def _delete_room_media(room, media_ids):
    failed = []
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    parsed = urlparse(cloudinary_url)
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname,
        api_key=os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or ""),
        api_secret=os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or ""),
        secure=True,
    )
    for media in room.media.filter(pk__in=media_ids):
        try:
            result = cloudinary.uploader.destroy(media.public_id, resource_type=media.media_type)
            if result.get("result") not in {"ok", "not found"}:
                raise RuntimeError(result.get("result", "unknown"))
        except Exception:
            failed.append(media.id)
            continue
        media.delete()
    return failed


def public_home(request):
    rooms = _with_cover_image(Room.objects.filter(status=Room.Status.AVAILABLE, building__is_active=True).select_related("building").prefetch_related("amenities"))
    buildings = Building.objects.filter(is_active=True, rooms__status=Room.Status.AVAILABLE).distinct().order_by("name")
    building_groups = []
    for building in buildings:
        building_groups.append({
            "building": building,
            "rooms": list(rooms.filter(building=building)[:4]),
            "available_count": rooms.filter(building=building).count(),
            "floor_count": Room.objects.filter(building=building).values("floor").distinct().count(),
        })
    context = {
        "featured_rooms": rooms[:6],
        "building_groups": building_groups,
        "buildings": buildings,
        "available_count": rooms.count(),
        "building_count": buildings.count(),
    }
    return render(request, "public/home.html", context)


def public_rooms(request):
    rooms = _with_cover_image(Room.objects.filter(status=Room.Status.AVAILABLE, building__is_active=True).select_related("building", "building__owner").prefetch_related("amenities"))
    q = request.GET.get("q", "").strip()
    district = request.GET.get("district", "").strip()
    selected_buildings = [name.strip() for name in request.GET.getlist("building") if name.strip()]
    selected_amenities = [name.strip() for name in request.GET.getlist("amenity") if name.strip()]
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    sort = request.GET.get("sort", "").strip()
    if q:
        rooms = rooms.filter(Q(number__icontains=q) | Q(building__name__icontains=q) | Q(building__address__icontains=q))
    if district:
        rooms = rooms.filter(building__address__icontains=district)
    if selected_buildings:
        rooms = rooms.filter(building__name__in=selected_buildings)
    for amenity in selected_amenities:
        rooms = rooms.filter(amenities__name=amenity)
    try:
        if min_price:
            rooms = rooms.filter(monthly_rent__gte=min_price)
        if max_price:
            rooms = rooms.filter(monthly_rent__lte=max_price)
    except (TypeError, ValueError):
        min_price = max_price = ""
    if sort == "price_asc":
        rooms = rooms.order_by("monthly_rent")
    elif sort == "price_desc":
        rooms = rooms.order_by("-monthly_rent")
    return render(request, "public/room_list.html", {
        "rooms": rooms.distinct(), "q": q, "district": district,
        "min_price": min_price, "max_price": max_price, "sort": sort,
        "selected_buildings": selected_buildings, "selected_amenities": selected_amenities,
        "buildings": Building.objects.filter(is_active=True).order_by("name"),
    })


def public_room_detail(request, room_id):
    room = get_object_or_404(
        _with_cover_image(Room.objects.select_related("building", "building__owner").prefetch_related("amenities")),
        pk=room_id,
        status=Room.Status.AVAILABLE,
        building__is_active=True,
    )
    amenity_icons = {
        "Máy lạnh": "snowflake",
        "Tủ lạnh": "refrigerator",
        "Máy giặt chung": "washing-machine",
        "Ban công": "sun",
        "Gác lửng": "layers-3",
        "Bếp riêng": "cooking-pot",
        "Thang máy": "move-vertical",
        "Bãi xe": "circle-parking",
        "Camera an ninh": "cctv",
        "Wi-Fi": "wifi",
    }
    amenities = [
        {"name": amenity.name, "icon": amenity_icons.get(amenity.name, "sparkles")}
        for amenity in room.amenities.all()
    ]
    related_candidates = _with_cover_image(
        Room.objects.filter(status=Room.Status.AVAILABLE, building__is_active=True)
        .exclude(pk=room.pk)
        .select_related("building")
    ).annotate(price_difference=Abs(F("monthly_rent") - room.monthly_rent))
    related_rooms = list(
        related_candidates.filter(building=room.building).order_by("price_difference", "number")[:4]
    )
    if len(related_rooms) < 4:
        related_rooms.extend(
            related_candidates.exclude(building=room.building)
            .order_by("price_difference", "building__name", "number")[: 4 - len(related_rooms)]
        )
    contact = get_user_model().objects.filter(role="admin", is_active=True).order_by("date_joined").first()
    return render(request, "public/room_detail.html", {
        "room": room,
        "contact": contact or room.building.owner,
        "amenities": amenities,
        "related_rooms": related_rooms,
        "room_images": room.media.filter(media_type=RoomMedia.MediaType.IMAGE).order_by("-is_primary", "-created_at", "-id"),
        "room_videos": room.media.filter(media_type=RoomMedia.MediaType.VIDEO).order_by("-created_at", "-id"),
    })


@login_required
def dashboard(request):
    if _is_tenant(request.user):
        return redirect("tenant-portal")
    _require_operator(request.user)
    rooms = get_accessible_rooms(request.user)
    contracts = get_accessible_contracts(request.user)
    invoices = get_accessible_invoices(request.user).exclude(status=Invoice.Status.CANCELLED)
    incidents = get_accessible_incidents(request.user)
    context = {
        "room_count": rooms.count(),
        "available_count": rooms.filter(status=Room.Status.AVAILABLE).count(),
        "occupied_count": rooms.filter(status=Room.Status.OCCUPIED).count(),
        "active_contract_count": contracts.filter(status=Contract.Status.ACTIVE).count(),
        "unpaid_total": invoices.aggregate(total=Sum("total_amount") - Sum("paid_amount"))["total"] or 0,
        "open_incident_count": incidents.filter(status__in=(Incident.Status.OPEN, Incident.Status.IN_PROGRESS)).count(),
        "recent_invoices": invoices.select_related("contract__room__building")[:8],
        "expiring_contracts": contracts.filter(status=Contract.Status.ACTIVE).select_related("room", "representative").order_by("end_date")[:8],
    }
    return render(request, "rentals/dashboard.html", context)


LIST_CONFIG = {
    "buildings": (Building, "rentals/building_list.html"),
    "rooms": (Room, "rentals/room_list.html"),
    "tenants": (Tenant, "rentals/tenant_list.html"),
    "contracts": (Contract, "rentals/contract_list.html"),
    "services": (Service, "rentals/service_list.html"),
    "invoices": (Invoice, "rentals/invoice_list.html"),
    "payments": (Payment, "rentals/payment_list.html"),
    "meters": (MeterReading, "rentals/meter_list.html"),
    "incidents": (Incident, "rentals/incident_list.html"),
    "notifications": (Notification, "rentals/notification_list.html"),
}


@login_required
def object_list(request, resource):
    _require_operator(request.user)
    _, template = LIST_CONFIG[resource]
    queryset = get_accessible_queryset(request.user, resource)
    q = request.GET.get("q", "").strip()
    if q:
        search_map = {
            "buildings": Q(name__icontains=q) | Q(address__icontains=q),
            "rooms": Q(number__icontains=q) | Q(building__name__icontains=q),
            "tenants": Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(identity_number__icontains=q),
            "contracts": Q(code__icontains=q) | Q(representative__full_name__icontains=q),
            "services": Q(name__icontains=q),
            "invoices": Q(code__icontains=q) | Q(contract__code__icontains=q) | Q(contract__representative__full_name__icontains=q),
            "payments": Q(invoice__code__icontains=q) | Q(reference__icontains=q),
            "meters": Q(room__number__icontains=q) | Q(room__building__name__icontains=q),
            "incidents": Q(title__icontains=q) | Q(room__number__icontains=q) | Q(reported_by__full_name__icontains=q),
            "notifications": Q(title__icontains=q) | Q(content__icontains=q) | Q(recipient__username__icontains=q),
        }
        queryset = queryset.filter(search_map[resource])
    context = {"q": q}
    if resource == "buildings":
        queryset = queryset.annotate(
            total_rooms=Count("rooms", distinct=True),
            available_rooms=Count("rooms", filter=Q(rooms__status=Room.Status.AVAILABLE), distinct=True),
            occupied_rooms=Count("rooms", filter=Q(rooms__status=Room.Status.OCCUPIED), distinct=True),
        )
        status = request.GET.get("status", "").strip()
        sort = request.GET.get("sort", "newest").strip()
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        queryset = queryset.order_by("name" if sort == "name" else "-created_at")
        all_buildings = get_accessible_buildings(request.user)
        context.update({
            "status": status,
            "sort": sort,
            "building_total": all_buildings.count(),
            "building_active": all_buildings.filter(is_active=True).count(),
            "building_inactive": all_buildings.filter(is_active=False).count(),
        })
    if resource == "rooms":
        building_id = request.GET.get("building", "").strip()
        accessible_buildings = get_accessible_buildings(request.user).filter(is_active=True).order_by("name")
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        queryset = queryset.select_related("building")
        context.update({
            "buildings": accessible_buildings,
            "selected_building": building_id,
        })
    if resource == "tenants":
        status = request.GET.get("status", "").strip()
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        queryset = queryset.select_related("user", "owner")
        context.update({"status": status})
    if resource == "contracts":
        status = request.GET.get("status", "").strip()
        building_id = request.GET.get("building", "").strip()
        valid_statuses = {choice for choice, _ in Contract.Status.choices}
        if status in valid_statuses:
            queryset = queryset.filter(status=status)
        else:
            status = ""
        if building_id:
            queryset = queryset.filter(room__building_id=building_id)
        queryset = queryset.select_related("room__building", "representative")
        context.update({
            "status": status,
            "status_choices": Contract.Status.choices,
            "buildings": get_accessible_buildings(request.user).order_by("name"),
            "selected_building": building_id,
        })
    if resource == "services":
        unit = request.GET.get("unit", "").strip()
        status = request.GET.get("status", "").strip()
        valid_units = {choice for choice, _ in Service.Unit.choices}
        if unit in valid_units:
            queryset = queryset.filter(unit=unit)
        else:
            unit = ""
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        queryset = queryset.select_related("owner")
        context.update({
            "unit": unit,
            "unit_choices": Service.Unit.choices,
            "status": status,
        })
    if resource == "meters":
        meter_type = request.GET.get("meter_type", "").strip()
        building_id = request.GET.get("building", "").strip()
        valid_types = {choice for choice, _ in MeterReading.MeterType.choices}
        if meter_type in valid_types:
            queryset = queryset.filter(meter_type=meter_type)
        else:
            meter_type = ""
        if building_id:
            queryset = queryset.filter(room__building_id=building_id)
        queryset = queryset.select_related("room__building", "recorded_by")
        context.update({
            "meter_type": meter_type,
            "meter_type_choices": MeterReading.MeterType.choices,
            "buildings": get_accessible_buildings(request.user).order_by("name"),
            "selected_building": building_id,
        })
    if resource == "invoices":
        status = request.GET.get("status", "").strip()
        building_id = request.GET.get("building", "").strip()
        valid_statuses = {choice for choice, _ in Invoice.Status.choices}
        if status in valid_statuses:
            queryset = queryset.filter(status=status)
        else:
            status = ""
        if building_id:
            queryset = queryset.filter(contract__room__building_id=building_id)
        queryset = queryset.select_related("contract__room__building", "contract__representative")
        context.update({
            "status": status,
            "status_choices": Invoice.Status.choices,
            "buildings": get_accessible_buildings(request.user).order_by("name"),
            "selected_building": building_id,
        })
    if resource == "payments":
        method = request.GET.get("method", "").strip()
        void_filter = request.GET.get("void", "").strip()
        valid_methods = {choice for choice, _ in Payment.Method.choices}
        if method in valid_methods:
            queryset = queryset.filter(method=method)
        else:
            method = ""
        if void_filter == "valid":
            queryset = queryset.filter(is_void=False)
        elif void_filter == "void":
            queryset = queryset.filter(is_void=True)
        queryset = queryset.select_related("invoice__contract__room__building", "received_by")
        context.update({
            "method": method,
            "method_choices": Payment.Method.choices,
            "void_filter": void_filter,
        })
    if resource == "incidents":
        status = request.GET.get("status", "").strip()
        priority = request.GET.get("priority", "").strip()
        building_id = request.GET.get("building", "").strip()
        valid_statuses = {choice for choice, _ in Incident.Status.choices}
        valid_priorities = {choice for choice, _ in Incident.Priority.choices}
        if status in valid_statuses:
            queryset = queryset.filter(status=status)
        else:
            status = ""
        if priority in valid_priorities:
            queryset = queryset.filter(priority=priority)
        else:
            priority = ""
        if building_id:
            queryset = queryset.filter(room__building_id=building_id)
        queryset = queryset.select_related("room__building", "reported_by", "assigned_to")
        context.update({
            "status": status,
            "status_choices": Incident.Status.choices,
            "priority": priority,
            "priority_choices": Incident.Priority.choices,
            "buildings": get_accessible_buildings(request.user).order_by("name"),
            "selected_building": building_id,
        })
    if resource == "notifications":
        read_filter = request.GET.get("read", "").strip()
        building_id = request.GET.get("building", "").strip()
        if read_filter == "unread":
            queryset = queryset.filter(is_read=False)
        elif read_filter == "read":
            queryset = queryset.filter(is_read=True)
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        queryset = queryset.select_related("recipient", "building", "created_by")
        context.update({
            "read_filter": read_filter,
            "buildings": get_accessible_buildings(request.user).order_by("name"),
            "selected_building": building_id,
        })
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    if resource == "buildings":
        for building in page_obj.object_list:
            amenity_names = list(Amenity.objects.filter(rooms__building=building).values_list("name", flat=True).distinct())
            building.amenity_tags = amenity_names[:3]
            building.amenity_extra = max(0, len(amenity_names) - 3)
            building.occupancy_percent = round(building.occupied_rooms * 100 / building.total_rooms) if building.total_rooms else 0
    context.update({"objects": page_obj, "page_obj": page_obj, "paginator": paginator})
    return render(request, template, context)


@login_required
def room_map(request):
    _require_operator(request.user)
    building_id = request.GET.get("building", "").strip()
    status = request.GET.get("status", "").strip()
    accessible_buildings = (
        get_accessible_buildings(request.user)
        .filter(is_active=True)
        .annotate(first_room_number=Min("rooms__number"))
        .order_by("first_room_number", "name")
    )
    buildings = accessible_buildings
    if building_id:
        buildings = buildings.filter(pk=building_id)

    summary_rooms = get_accessible_rooms(request.user).filter(building__in=buildings)
    displayed_rooms = summary_rooms.select_related("building").prefetch_related("amenities")
    valid_statuses = {choice for choice, _ in Room.Status.choices}
    if status in valid_statuses:
        displayed_rooms = displayed_rooms.filter(status=status)
    else:
        status = ""

    building_cards = []
    for building in buildings:
        all_building_rooms = list(summary_rooms.filter(building=building))
        visible_building_rooms = list(displayed_rooms.filter(building=building))
        for room in visible_building_rooms:
            room.has_air_conditioner = any(amenity.name == "Máy lạnh" for amenity in room.amenities.all())
        floors = []
        for floor_number in sorted({room.floor for room in all_building_rooms}, reverse=True):
            floor_rooms = [room for room in visible_building_rooms if room.floor == floor_number]
            if floor_rooms:
                floors.append({"number": floor_number, "rooms": floor_rooms})
        counts = {key: sum(room.status == key for room in all_building_rooms) for key in valid_statuses}
        building_cards.append({"building": building, "floors": floors, "total": len(all_building_rooms), "counts": counts})

    total = summary_rooms.count()
    stats = {
        "total": total,
        "available": summary_rooms.filter(status=Room.Status.AVAILABLE).count(),
        "occupied": summary_rooms.filter(status=Room.Status.OCCUPIED).count(),
        "reserved": summary_rooms.filter(status=Room.Status.RESERVED).count(),
        "maintenance": summary_rooms.filter(status=Room.Status.MAINTENANCE).count(),
        "air_conditioned": summary_rooms.filter(amenities__name="Máy lạnh").distinct().count(),
    }
    stats["without_air_conditioner"] = stats["total"] - stats["air_conditioned"]
    return render(request, "rentals/room_map.html", {
        "all_buildings": accessible_buildings,
        "building_cards": building_cards,
        "selected_building": building_id,
        "selected_status": status,
        "status_choices": Room.Status.choices,
        "stats": stats,
    })


FORM_CONFIG = {
    "buildings": (BuildingForm, "Danh mục tòa nhà"),
    "rooms": (RoomForm, "Phòng cho thuê"),
    "tenants": (TenantForm, "Khách thuê"),
    "contracts": (ContractForm, "Hợp đồng"),
    "services": (ServiceForm, "Danh mục dịch vụ"),
    "meters": (MeterReadingForm, "Chỉ số điện nước"),
}


@login_required
@require_http_methods(["GET", "POST"])
def object_create(request, resource):
    _require_operator(request.user)
    if resource == "buildings" and is_staff_role(request.user):
        raise PermissionDenied("Nhân viên không có quyền thêm tòa nhà.")
    form_class, title = FORM_CONFIG[resource]
    form = form_class(request.POST or None, request.FILES or None, user=request.user)
    media_items = []
    if resource == "rooms" and request.method == "POST":
        try:
            media_items = json.loads(request.POST.get("media_payload", "[]"))
            if not isinstance(media_items, list):
                raise ValueError
            for item in media_items:
                if item.get("media_type") not in {RoomMedia.MediaType.IMAGE, RoomMedia.MediaType.VIDEO}:
                    raise ValueError
                if not item.get("url", "").startswith("https://res.cloudinary.com/") or not item.get("public_id"):
                    raise ValueError
                item["bytes"] = max(0, int(item.get("bytes", 0)))
        except (TypeError, ValueError, json.JSONDecodeError):
            form.add_error(None, "Thông tin ảnh/video tải lên không hợp lệ.")
    if form.is_valid():
        obj = form.save(commit=False)
        if isinstance(obj, Building) and is_owner(request.user):
            obj.owner = request.user
        elif isinstance(obj, Tenant) and obj.owner_id is None and not is_admin(request.user):
            obj.owner = get_default_owner_for_operator(request.user)
        elif isinstance(obj, MeterReading):
            obj.recorded_by = request.user
        obj.save()
        form.save_m2m()
        if isinstance(obj, Contract) and obj.representative_id and obj.room_id:
            if obj.representative.owner_id is None:
                obj.representative.owner_id = obj.room.building.owner_id
                obj.representative.save(update_fields=["owner", "updated_at"])
        if isinstance(obj, Room):
            new_media = RoomMedia.objects.bulk_create([
                RoomMedia(
                    room=obj,
                    media_type=item["media_type"],
                    url=item["url"],
                    public_id=item["public_id"],
                    format=item.get("format", ""),
                    bytes=item["bytes"],
                ) for item in media_items
            ])
            _apply_primary_image(obj, request.POST.get("primary_image", ""),
                                 [media for media in new_media if media.media_type == RoomMedia.MediaType.IMAGE])
            messages.success(request, f"Đã thêm phòng {obj.number} thành công.")
        else:
            messages.success(request, f"Đã thêm {title.lower()} thành công.")
        return redirect(resource)
    template = "rentals/room_form.html" if resource == "rooms" else "rentals/form.html"
    return render(request, template, {"form": form, "title": f"Thêm {title.lower()}"})


@login_required
@require_POST
def cloudinary_upload_signature(request):
    _require_operator(request.user)
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if not cloudinary_url:
        return JsonResponse({"error": "Cloudinary chưa được cấu hình."}, status=503)
    parsed = urlparse(cloudinary_url)
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname
    api_key = os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or "")
    if not cloud_name or not api_key or not api_secret:
        return JsonResponse({"error": "Cloudinary thiếu Cloud name, API Key hoặc API Secret."}, status=503)
    timestamp = int(time.time())
    folder = "ql-phong-cho-thue/rooms"
    signature = api_sign_request({"folder": folder, "timestamp": timestamp}, api_secret)
    return JsonResponse({
        "timestamp": timestamp,
        "folder": folder,
        "signature": signature,
        "cloud_name": cloud_name,
        "api_key": api_key,
    })


@login_required
@require_POST
def cloudinary_upload(request):
    _require_operator(request.user)
    uploaded_file = request.FILES.get("file")
    media_type = request.POST.get("media_type")
    if uploaded_file is None or media_type not in {RoomMedia.MediaType.IMAGE, RoomMedia.MediaType.VIDEO}:
        return JsonResponse({"error": "Tệp tải lên không hợp lệ."}, status=400)

    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    parsed = urlparse(cloudinary_url)
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname
    api_key = os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or "")
    if not cloud_name or not api_key or not api_secret:
        return JsonResponse({"error": "Cloudinary thiếu Cloud name, API Key hoặc API Secret."}, status=503)

    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
    try:
        result = cloudinary.uploader.upload(
            uploaded_file,
            resource_type=media_type,
            folder="ql-phong-cho-thue/rooms",
        )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({
        "media_type": media_type,
        "url": result["secure_url"],
        "public_id": result["public_id"],
        "format": result.get("format", ""),
        "bytes": result.get("bytes", 0),
    })


@login_required
@require_http_methods(["GET", "POST"])
def object_update(request, resource, object_id):
    _require_operator(request.user)
    form_class, title = FORM_CONFIG[resource]
    obj = get_object_or_404(get_accessible_queryset(request.user, resource), pk=object_id)
    if resource == "contracts" and obj.status != Contract.Status.DRAFT:
        messages.error(request, "Chỉ có thể chỉnh sửa hợp đồng khi đang ở trạng thái bản nháp.")
        return redirect("contract-detail", contract_id=obj.id)
    form = form_class(request.POST or None, instance=obj, user=request.user)
    media_items = []
    if resource == "rooms" and request.method == "POST":
        try:
            media_items = json.loads(request.POST.get("media_payload", "[]"))
            if not isinstance(media_items, list):
                raise ValueError
            for item in media_items:
                if item.get("media_type") not in {RoomMedia.MediaType.IMAGE, RoomMedia.MediaType.VIDEO}:
                    raise ValueError
                if not item.get("url", "").startswith("https://res.cloudinary.com/") or not item.get("public_id"):
                    raise ValueError
                item["bytes"] = max(0, int(item.get("bytes", 0)))
        except (TypeError, ValueError, AttributeError):
            form.add_error(None, "Thông tin ảnh/video tải lên không hợp lệ.")
    if form.is_valid():
        form.save()
        if resource == "rooms":
            failed_deletions = _delete_room_media(obj, request.POST.getlist("delete_media"))
            new_media = RoomMedia.objects.bulk_create([
                RoomMedia(room=obj, media_type=item["media_type"], url=item["url"],
                          public_id=item["public_id"], format=item.get("format", ""), bytes=item["bytes"])
                for item in media_items
            ])
            _apply_primary_image(obj, request.POST.get("primary_image", ""),
                                 [media for media in new_media if media.media_type == RoomMedia.MediaType.IMAGE])
            messages.success(request, f"Đã lưu thay đổi phòng {obj.number} thành công.")
            if failed_deletions:
                messages.warning(request, "Có ảnh hoặc video chưa xóa được khỏi Cloudinary. Vui lòng thử lại.")
        else:
            messages.success(request, f"Đã cập nhật {title.lower()} thành công.")
        if resource == "tenants":
            return redirect("tenant-detail", tenant_id=obj.id)
        if resource == "contracts":
            return redirect("contract-detail", contract_id=obj.id)
        return redirect(resource)
    if resource == "rooms":
        return render(request, "rentals/room_form.html", {
            "form": form, "title": f"Sửa phòng {obj.number}", "editing": True,
            "existing_images": obj.media.filter(media_type=RoomMedia.MediaType.IMAGE),
            "existing_videos": obj.media.filter(media_type=RoomMedia.MediaType.VIDEO),
        })
    return render(request, "rentals/form.html", {"form": form, "title": f"Cập nhật {title.lower()}"})


def _extract_error_message(exc):
    if hasattr(exc, "messages") and exc.messages:
        return " ".join(exc.messages)
    return str(exc)


@login_required
def tenant_detail(request, tenant_id):
    _require_operator(request.user)
    tenant = get_object_or_404(
        get_accessible_tenants(request.user).select_related("user", "owner"),
        pk=tenant_id,
    )
    contracts = list(
        get_accessible_contracts(request.user)
        .filter(Q(representative=tenant) | Q(members__tenant=tenant))
        .select_related("room__building", "representative")
        .distinct()
        .order_by("-start_date")
    )
    active_contracts = [c for c in contracts if c.status == Contract.Status.ACTIVE]
    current_rooms = []
    seen_room_ids = set()
    for c in active_contracts:
        if c.room_id not in seen_room_ids:
            seen_room_ids.add(c.room_id)
            current_rooms.append(c.room)
    invoices = (
        get_accessible_invoices(request.user)
        .filter(contract__in=contracts)
        .select_related("contract__room__building")
        .order_by("-period", "-issued_date")
    )
    payments = (
        Payment.objects.filter(invoice__in=invoices)
        .select_related("invoice__contract__room__building")
        .order_by("-paid_at")
    )
    link_form = TenantUserLinkForm(instance=tenant)
    return render(
        request,
        "rentals/tenant_detail.html",
        {
            "tenant": tenant,
            "contracts": contracts,
            "active_contracts": active_contracts,
            "current_rooms": current_rooms,
            "invoices": invoices,
            "payments": payments,
            "link_form": link_form,
        },
    )


@login_required
@require_POST
def tenant_toggle_active(request, tenant_id):
    _require_operator(request.user)
    tenant = get_object_or_404(get_accessible_tenants(request.user), pk=tenant_id)
    tenant.is_active = not tenant.is_active
    tenant.save(update_fields=["is_active", "updated_at"])
    if tenant.is_active:
        messages.success(request, f"Đã kích hoạt lại khách thuê {tenant.full_name}.")
    else:
        messages.success(request, f"Đã ngừng kích hoạt khách thuê {tenant.full_name}.")
    return redirect("tenant-detail", tenant_id=tenant.id)


@login_required
@require_POST
def tenant_link_user(request, tenant_id):
    _require_operator(request.user)
    tenant = get_object_or_404(get_accessible_tenants(request.user), pk=tenant_id)
    form = TenantUserLinkForm(request.POST, instance=tenant)
    if form.is_valid():
        form.save()
        if tenant.user_id:
            messages.success(request, f"Đã liên kết khách thuê {tenant.full_name} với tài khoản {tenant.user.username}.")
        else:
            messages.success(request, f"Đã gỡ liên kết tài khoản của khách thuê {tenant.full_name}.")
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("tenant-detail", tenant_id=tenant.id)


@login_required
def contract_detail(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(
        get_accessible_contracts(request.user).select_related("room__building", "representative"),
        pk=contract_id,
    )
    members = contract.members.select_related("tenant").order_by("joined_date", "created_at")
    contract_services = contract.contract_services.select_related("service").all()
    invoices = (
        get_accessible_invoices(request.user)
        .filter(contract=contract)
        .order_by("-period", "-issued_date")
    )
    member_form = ContractMemberForm(contract=contract, user=request.user, initial={"joined_date": contract.start_date})
    service_form = ContractServiceForm(contract=contract, user=request.user)
    renew_form = ContractRenewForm()
    return render(
        request,
        "rentals/contract_detail.html",
        {
            "contract": contract,
            "members": members,
            "contract_services": contract_services,
            "invoices": invoices,
            "member_form": member_form,
            "service_form": service_form,
            "renew_form": renew_form,
        },
    )


@login_required
@require_POST
def contract_activate(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    try:
        activate_contract(contract)
        messages.success(request, f"Đã kích hoạt hợp đồng {contract.code} thành công.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_renew(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    form = ContractRenewForm(request.POST)
    if form.is_valid():
        try:
            renew_contract(
                contract,
                new_end_date=form.cleaned_data["new_end_date"],
                new_monthly_rent=form.cleaned_data.get("new_monthly_rent"),
                notes=form.cleaned_data.get("notes", ""),
            )
            contract.refresh_from_db()
            messages.success(request, f"Đã gia hạn hợp đồng {contract.code} đến ngày {contract.end_date:%d/%m/%Y}.")
        except ValidationError as exc:
            messages.error(request, _extract_error_message(exc))
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_terminate(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    try:
        terminate_contract(contract, reason=request.POST.get("reason", "").strip())
        messages.success(request, f"Đã chấm dứt/thanh lý hợp đồng {contract.code}.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_cancel(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    try:
        cancel_contract(contract, reason=request.POST.get("reason", "").strip())
        messages.success(request, f"Đã hủy hợp đồng {contract.code}.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_member_add(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    form = ContractMemberForm(request.POST, contract=contract, user=request.user)
    if form.is_valid():
        try:
            member = add_contract_member(
                contract,
                form.cleaned_data["tenant"],
                joined_date=form.cleaned_data["joined_date"],
                left_date=form.cleaned_data.get("left_date"),
            )
            messages.success(request, f"Đã thêm người ở cùng {member.tenant.full_name} vào hợp đồng {contract.code}.")
        except ValidationError as exc:
            messages.error(request, _extract_error_message(exc))
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_member_remove(request, contract_id, member_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    try:
        remove_contract_member(contract, member_id)
        messages.success(request, f"Đã xóa người ở cùng khỏi hợp đồng {contract.code}.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_service_add(request, contract_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    form = ContractServiceForm(request.POST, contract=contract, user=request.user)
    if form.is_valid():
        try:
            cs = attach_contract_service(
                contract,
                service=form.cleaned_data["service"],
                unit_price=form.cleaned_data.get("unit_price"),
                quantity=form.cleaned_data.get("quantity"),
                is_active=form.cleaned_data.get("is_active", True),
            )
            messages.success(request, f"Đã gắn dịch vụ {cs.service.name} vào hợp đồng {contract.code}.")
        except ValidationError as exc:
            messages.error(request, _extract_error_message(exc))
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def contract_service_remove(request, contract_id, contract_service_id):
    _require_operator(request.user)
    contract = get_object_or_404(get_accessible_contracts(request.user), pk=contract_id)
    try:
        remove_contract_service(contract, contract_service_id)
        messages.success(request, f"Đã gỡ dịch vụ khỏi hợp đồng {contract.code}.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("contract-detail", contract_id=contract.id)


@login_required
@require_POST
def service_delete(request, service_id):
    _require_operator(request.user)
    service = get_object_or_404(get_accessible_services(request.user), pk=service_id)
    if not is_admin(request.user) and service.owner_id is None:
        raise PermissionDenied("Bạn không có quyền xóa dịch vụ dùng chung của hệ thống.")
    name = service.name
    try:
        service.delete()
        messages.success(request, f"Đã xóa dịch vụ {name}.")
    except ProtectedError:
        service.is_active = False
        service.save(update_fields=["is_active", "updated_at"])
        messages.warning(request, f"Dịch vụ {name} đã phát sinh dữ liệu nên được chuyển sang ngừng áp dụng.")
    return redirect("services")


@login_required
def api_meter_previous(request):
    _require_operator(request.user)
    room_id = request.GET.get("room", "").strip()
    meter_type = request.GET.get("meter_type", "").strip()
    period_raw = request.GET.get("period", "").strip()
    if not room_id or not meter_type:
        return JsonResponse({"previous_value": "0"})
    room = get_object_or_404(get_accessible_rooms(request.user), pk=room_id)
    period = None
    if period_raw:
        try:
            period = timezone.datetime.strptime(period_raw, "%Y-%m-%d").date()
        except ValueError:
            period = None
    prev_val = get_previous_meter_reading_value(room.id, meter_type, period)
    return JsonResponse({"previous_value": str(prev_val)})


@login_required
@require_http_methods(["GET", "POST"])
def invoice_create(request):
    _require_operator(request.user)
    initial = {}
    contract_id = request.GET.get("contract", "").strip()
    if contract_id:
        initial["contract"] = contract_id
    form = InvoiceCreateForm(request.POST or None, user=request.user, initial=initial)
    if form.is_valid():
        try:
            invoice = create_monthly_invoice(
                contract=form.cleaned_data["contract"],
                period=form.cleaned_data["period"],
                due_date=form.cleaned_data.get("due_date"),
                discount=form.cleaned_data.get("discount"),
                surcharge=form.cleaned_data.get("surcharge"),
                surcharge_description=form.cleaned_data.get("surcharge_description") or "Phụ thu",
                status=form.cleaned_data.get("status") or Invoice.Status.DRAFT,
                notes=form.cleaned_data.get("notes", ""),
                created_by=request.user,
            )
            messages.success(request, f"Đã tạo hóa đơn {invoice.code} thành công.")
            return redirect("invoice-detail", invoice_id=invoice.id)
        except ValidationError as exc:
            form.add_error(None, _extract_error_message(exc))
    return render(
        request,
        "rentals/invoice_form.html",
        {"form": form, "title": "Tạo hóa đơn theo hợp đồng", "bulk": False},
    )


@login_required
@require_http_methods(["GET", "POST"])
def invoice_bulk_create(request):
    _require_operator(request.user)
    form = InvoiceBulkCreateForm(request.POST or None, user=request.user)
    if form.is_valid():
        try:
            contracts = get_accessible_contracts(request.user)
            building = form.cleaned_data.get("building")
            if building:
                contracts = contracts.filter(room__building=building)
            created, skipped = generate_bulk_invoices(
                contracts_queryset=contracts,
                period=form.cleaned_data["period"],
                due_date=form.cleaned_data.get("due_date"),
                status=form.cleaned_data.get("status") or Invoice.Status.DRAFT,
                created_by=request.user,
            )
            messages.success(
                request,
                f"Đã tạo hàng loạt {len(created)} hóa đơn mới (bỏ qua {skipped} hợp đồng đã có hóa đơn trong kỳ).",
            )
            return redirect("invoices")
        except ValidationError as exc:
            form.add_error(None, _extract_error_message(exc))
    return render(
        request,
        "rentals/invoice_form.html",
        {"form": form, "title": "Tạo hóa đơn hàng loạt theo kỳ", "bulk": True},
    )


@login_required
def invoice_detail(request, invoice_id):
    _require_operator(request.user)
    invoice = get_object_or_404(
        get_accessible_invoices(request.user)
        .select_related("contract__room__building", "contract__representative")
        .prefetch_related("items__service", "payments__received_by"),
        pk=invoice_id,
    )
    item_form = InvoiceItemForm(user=request.user)
    cancel_form = InvoiceCancelForm()
    return render(
        request,
        "rentals/invoice_detail.html",
        {
            "invoice": invoice,
            "items": invoice.items.all(),
            "payments": invoice.payments.all(),
            "item_form": item_form,
            "cancel_form": cancel_form,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def invoice_update(request, invoice_id):
    _require_operator(request.user)
    invoice = get_object_or_404(get_accessible_invoices(request.user), pk=invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        messages.error(request, "Chỉ có thể chỉnh sửa hóa đơn khi đang ở trạng thái bản nháp.")
        return redirect("invoice-detail", invoice_id=invoice.id)
    form = InvoiceDraftUpdateForm(request.POST or None, instance=invoice, user=request.user)
    if form.is_valid():
        try:
            form.save()
            recalculate_invoice(invoice)
            messages.success(request, f"Đã cập nhật hóa đơn nháp {invoice.code}.")
            return redirect("invoice-detail", invoice_id=invoice.id)
        except ValidationError as exc:
            form.add_error(None, _extract_error_message(exc))
    return render(request, "rentals/form.html", {"form": form, "title": f"Chỉnh sửa hóa đơn nháp {invoice.code}"})


@login_required
@require_POST
def invoice_item_add(request, invoice_id):
    _require_operator(request.user)
    invoice = get_object_or_404(get_accessible_invoices(request.user), pk=invoice_id)
    form = InvoiceItemForm(request.POST, user=request.user)
    if form.is_valid():
        try:
            add_invoice_item(
                invoice=invoice,
                description=form.cleaned_data["description"],
                quantity=form.cleaned_data["quantity"],
                unit_price=form.cleaned_data["unit_price"],
                service=form.cleaned_data.get("service"),
            )
            messages.success(request, "Đã thêm khoản mục vào hóa đơn nháp.")
        except ValidationError as exc:
            messages.error(request, _extract_error_message(exc))
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("invoice-detail", invoice_id=invoice.id)


@login_required
@require_POST
def invoice_item_remove(request, invoice_id, item_id):
    _require_operator(request.user)
    invoice = get_object_or_404(get_accessible_invoices(request.user), pk=invoice_id)
    try:
        remove_invoice_item(invoice, item_id)
        messages.success(request, "Đã xóa khoản mục khỏi hóa đơn nháp.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("invoice-detail", invoice_id=invoice.id)


@login_required
@require_POST
def invoice_issue(request, invoice_id):
    _require_operator(request.user)
    invoice = get_object_or_404(get_accessible_invoices(request.user), pk=invoice_id)
    try:
        issue_invoice(invoice, issued_by=request.user)
        messages.success(request, f"Đã phát hành hóa đơn {invoice.code} và gửi thông báo cho khách thuê.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    return redirect("invoice-detail", invoice_id=invoice.id)


@login_required
@require_POST
def invoice_cancel(request, invoice_id):
    _require_operator(request.user)
    invoice = get_object_or_404(get_accessible_invoices(request.user), pk=invoice_id)
    form = InvoiceCancelForm(request.POST)
    if form.is_valid():
        try:
            cancel_invoice(invoice, reason=form.cleaned_data["reason"])
            messages.success(request, f"Đã hủy hóa đơn {invoice.code}.")
        except ValidationError as exc:
            messages.error(request, _extract_error_message(exc))
    else:
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
    return redirect("invoice-detail", invoice_id=invoice.id)


@login_required
@require_http_methods(["GET", "POST"])
def payment_create(request):
    _require_operator(request.user)
    initial = {}
    invoice_id = request.GET.get("invoice", "").strip()
    if invoice_id:
        inv = get_accessible_invoices(request.user).filter(pk=invoice_id).first()
        if inv:
            initial["invoice"] = inv.id
            initial["amount"] = inv.balance
    form = PaymentCreateForm(request.POST or None, user=request.user, initial=initial)
    if form.is_valid():
        try:
            payment = record_payment(
                invoice=form.cleaned_data["invoice"],
                amount=form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                received_by=request.user,
                paid_at=form.cleaned_data.get("paid_at"),
                reference=form.cleaned_data.get("reference", ""),
                notes=form.cleaned_data.get("notes", ""),
            )
            messages.success(request, f"Đã ghi nhận thanh toán cho hóa đơn {payment.invoice.code}.")
            return redirect("invoice-detail", invoice_id=payment.invoice_id)
        except ValidationError as exc:
            form.add_error(None, _extract_error_message(exc))
    return render(request, "rentals/form.html", {"form": form, "title": "Ghi nhận thanh toán"})


@login_required
@require_POST
def payment_void(request, payment_id):
    _require_operator(request.user)
    payment = get_object_or_404(get_accessible_payments(request.user), pk=payment_id)
    try:
        void_payment(payment, reason=request.POST.get("reason", "").strip())
        messages.success(request, f"Đã hủy giao dịch thanh toán của hóa đơn {payment.invoice.code}.")
    except ValidationError as exc:
        messages.error(request, _extract_error_message(exc))
    next_url = request.POST.get("next", "").strip()
    if next_url == "invoice":
        return redirect("invoice-detail", invoice_id=payment.invoice_id)
    return redirect("payments")


@login_required
@require_http_methods(["GET", "POST"])
def incident_detail(request, incident_id):
    _require_operator(request.user)
    incident = get_object_or_404(
        get_accessible_incidents(request.user).select_related("room__building", "reported_by", "assigned_to"),
        pk=incident_id,
    )
    form = IncidentManageForm(request.POST or None, instance=incident, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            try:
                update_incident_management(
                    incident=incident,
                    priority=form.cleaned_data["priority"],
                    status=form.cleaned_data["status"],
                    assigned_to=form.cleaned_data.get("assigned_to"),
                    resolution_notes=form.cleaned_data.get("resolution_notes", ""),
                    updated_by=request.user,
                )
                messages.success(request, "Đã cập nhật thông tin xử lý sự cố.")
                return redirect("incident-detail", incident_id=incident.id)
            except ValidationError as exc:
                form.add_error(None, _extract_error_message(exc))
        else:
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
    return render(
        request,
        "rentals/incident_detail.html",
        {"incident": incident, "form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def notification_create(request):
    _require_operator(request.user)
    form = NotificationCreateForm(request.POST or None, user=request.user)
    if form.is_valid():
        try:
            created = send_targeted_notifications(
                target_type=form.cleaned_data["target_type"],
                title=form.cleaned_data["title"],
                content=form.cleaned_data["content"],
                created_by=request.user,
                tenant=form.cleaned_data.get("tenant"),
                room=form.cleaned_data.get("room"),
                building=form.cleaned_data.get("building"),
            )
            messages.success(request, f"Đã gửi thông báo đến {len(created)} tài khoản khách thuê.")
            return redirect("notifications")
        except ValidationError as exc:
            form.add_error(None, _extract_error_message(exc))
    return render(request, "rentals/form.html", {"form": form, "title": "Gửi thông báo cho khách thuê"})


@login_required
@require_POST
def notification_expiring_contracts(request):
    _require_operator(request.user)
    contracts = get_accessible_contracts(request.user)
    created = notify_expiring_contracts(contracts, days=30, created_by=request.user)
    messages.success(request, f"Đã gửi {len(created)} thông báo nhắc hợp đồng sắp hết hạn.")
    return redirect("notifications")


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    _require_operator(request.user)
    notif = get_object_or_404(get_accessible_notifications(request.user), pk=notification_id)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=["is_read", "read_at", "updated_at"])
    return redirect("notifications")


@login_required
def api_dashboard_summary(request):
    _require_operator(request.user)
    rooms = get_accessible_rooms(request.user)
    invoices = get_accessible_invoices(request.user).exclude(status=Invoice.Status.CANCELLED)
    contracts = get_accessible_contracts(request.user)
    room_statuses = list(rooms.values("status").annotate(count=Count("id")).order_by("status"))
    debt = invoices.aggregate(total=Sum("total_amount") - Sum("paid_amount"))["total"] or 0
    return JsonResponse({"rooms": room_statuses, "total_debt": str(debt), "active_contracts": contracts.filter(status=Contract.Status.ACTIVE).count()})


@login_required
def api_room_detail(request, room_id):
    _require_operator(request.user)
    room = get_object_or_404(get_accessible_rooms(request.user).select_related("building"), pk=room_id)
    return JsonResponse({"id": str(room.id), "building": room.building.name, "number": room.number, "status": room.status, "monthly_rent": str(room.monthly_rent)})


@login_required
def tenant_portal(request):
    tenant = _tenant_profile(request.user)
    contracts = _tenant_contracts(tenant).select_related("room__building", "representative")
    invoices = Invoice.objects.filter(contract__in=contracts).exclude(status=Invoice.Status.CANCELLED)
    notifications = request.user.notifications.all()
    context = {
        "tenant": tenant,
        "active_contract": contracts.filter(status=Contract.Status.ACTIVE).first(),
        "contracts": contracts.order_by("-start_date")[:5],
        "unpaid_invoices": invoices.exclude(status=Invoice.Status.PAID).order_by("due_date")[:8],
        "total_debt": invoices.aggregate(total=Sum("total_amount") - Sum("paid_amount"))["total"] or 0,
        "incidents": tenant.reported_incidents.select_related("room").all()[:5],
        "notifications": notifications[:5],
        "unread_count": notifications.filter(is_read=False).count(),
    }
    return render(request, "tenant/portal.html", context)


@login_required
def tenant_contracts(request):
    tenant = _tenant_profile(request.user)
    objects = _tenant_contracts(tenant).select_related("room__building", "representative").order_by("-start_date")
    return render(request, "tenant/contracts.html", {"tenant": tenant, "objects": objects})


@login_required
def tenant_invoices(request):
    tenant = _tenant_profile(request.user)
    objects = (
        Invoice.objects.filter(contract__in=_tenant_contracts(tenant))
        .exclude(status=Invoice.Status.DRAFT)
        .select_related("contract__room__building")
        .order_by("-period")
    )
    return render(request, "tenant/invoices.html", {"tenant": tenant, "objects": objects})


@login_required
def tenant_rooms(request):
    tenant = _tenant_profile(request.user)
    contracts = (
        _tenant_contracts(tenant)
        .select_related("room__building", "representative")
        .prefetch_related("room__amenities", "room__media", "members__tenant")
        .order_by("-start_date")
    )
    return render(request, "tenant/rooms.html", {"tenant": tenant, "contracts": contracts})


@login_required
def tenant_payments(request):
    tenant = _tenant_profile(request.user)
    contracts = _tenant_contracts(tenant)
    payments = (
        Payment.objects.filter(invoice__contract__in=contracts, is_void=False)
        .select_related("invoice__contract__room__building")
        .order_by("-paid_at")
    )
    total_paid = payments.aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "tenant/payments.html",
        {"tenant": tenant, "objects": payments, "total_paid": total_paid},
    )


@login_required
def tenant_invoice_detail(request, invoice_id):
    tenant = _tenant_profile(request.user)
    invoice = get_object_or_404(
        Invoice.objects.prefetch_related("items", "payments")
        .select_related("contract__room__building")
        .exclude(status=Invoice.Status.DRAFT),
        pk=invoice_id,
        contract__in=_tenant_contracts(tenant),
    )
    return render(request, "tenant/invoice_detail.html", {"tenant": tenant, "invoice": invoice})


@login_required
@require_http_methods(["GET", "POST"])
def tenant_report_incident(request):
    tenant = _tenant_profile(request.user)
    form = TenantIncidentForm(request.POST or None, tenant=tenant)
    if form.is_valid():
        incident = form.save(commit=False)
        incident.reported_by = tenant
        incident.save()
        return redirect("tenant-incidents")
    return render(request, "tenant/incident_form.html", {"tenant": tenant, "form": form})


@login_required
def tenant_incidents(request):
    tenant = _tenant_profile(request.user)
    objects = tenant.reported_incidents.select_related("room", "assigned_to").all()
    return render(request, "tenant/incidents.html", {"tenant": tenant, "objects": objects})


@login_required
@require_http_methods(["GET", "POST"])
def tenant_notifications(request):
    tenant = _tenant_profile(request.user)
    if request.method == "POST" and request.POST.get("mark_all"):
        request.user.notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        messages.success(request, "Đã đánh dấu tất cả thông báo là đã đọc.")
        return redirect("tenant-notifications")
    objects = request.user.notifications.all()
    unread_count = objects.filter(is_read=False).count()
    return render(
        request,
        "tenant/notifications.html",
        {"tenant": tenant, "objects": objects, "unread_count": unread_count},
    )


@login_required
@require_POST
def tenant_notification_mark_read(request, notification_id):
    _tenant_profile(request.user)
    notif = get_object_or_404(request.user.notifications.all(), pk=notification_id)
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = timezone.now()
        notif.save(update_fields=["is_read", "read_at", "updated_at"])
        messages.success(request, "Đã đánh dấu thông báo đã đọc.")
    return redirect("tenant-notifications")


@login_required
def chat_list(request):
    conversations = list(get_accessible_conversations(request.user))
    for conversation in conversations:
        conversation.latest_message = conversation.chat_messages.select_related("sender").last()
        conversation.unread_count = conversation.chat_messages.exclude(sender=request.user).exclude(read_by=request.user).count()
    available_tenants = (
        get_accessible_tenants(request.user).filter(user__isnull=False, is_active=True)
        if not is_tenant(request.user)
        else Tenant.objects.none()
    )
    return render(request, "chat/list.html", {"conversations": conversations, "available_tenants": available_tenants})


@login_required
@require_POST
def chat_start(request):
    if is_tenant(request.user):
        tenant = get_tenant_profile(request.user)
    else:
        tenant = get_object_or_404(
            get_accessible_tenants(request.user).filter(user__isnull=False, is_active=True),
            pk=request.POST.get("tenant_id"),
        )
    subject = request.POST.get("subject", "").strip()[:200] or "Trao đổi với ban quản lý"
    conversation = Conversation.objects.create(tenant=tenant, subject=subject)
    participants = [request.user]
    if tenant.user_id:
        participants.append(tenant.user)
    if tenant.owner_id:
        participants.append(tenant.owner)
    conversation.participants.add(*participants)
    return redirect("chat-detail", conversation_id=conversation.pk)


def _mark_conversation_read(conversation, user):
    unread_ids = conversation.chat_messages.exclude(sender=user).exclude(read_by=user).values_list("id", flat=True)
    through = ChatMessage.read_by.through
    through.objects.bulk_create(
        [through(chatmessage_id=message_id, user_id=user.pk) for message_id in unread_ids],
        ignore_conflicts=True,
    )


@login_required
def chat_detail(request, conversation_id):
    conversation = get_object_or_404(get_accessible_conversations(request.user), pk=conversation_id)
    conversation.participants.add(request.user)
    _mark_conversation_read(conversation, request.user)
    messages_list = conversation.chat_messages.select_related("sender").prefetch_related("read_by")
    return render(request, "chat/detail.html", {"conversation": conversation, "chat_messages": messages_list})


@login_required
@require_POST
def chat_send(request, conversation_id):
    conversation = get_object_or_404(get_accessible_conversations(request.user), pk=conversation_id, is_closed=False)
    content = request.POST.get("message", "").strip()
    if not content or len(content) > 4000:
        messages.error(request, "Tin nhắn phải có từ 1 đến 4.000 ký tự.")
        return redirect("chat-detail", conversation_id=conversation.pk)
    chat_message = ChatMessage.objects.create(conversation=conversation, sender=request.user, content=content)
    chat_message.read_by.add(request.user)
    conversation.participants.add(request.user)
    conversation.last_message_at = chat_message.created_at
    conversation.save(update_fields=("last_message_at", "updated_at"))
    async_to_sync(get_channel_layer().group_send)(
        f"chat-{conversation.pk}",
        {
            "type": "chat.message",
            "message": {
                "id": str(chat_message.pk),
                "content": chat_message.content,
                "sender_id": str(request.user.pk),
                "sender_name": request.user.get_full_name() or request.user.username,
                "created_at": timezone.localtime(chat_message.created_at).strftime("%H:%M %d/%m/%Y"),
            },
        },
    )
    return redirect("chat-detail", conversation_id=conversation.pk)

