from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import BuildingForm, ContractForm, MeterReadingForm, RoomForm, TenantForm, TenantIncidentForm
from .models import Amenity, Building, Contract, Incident, Invoice, MeterReading, Payment, Room, Tenant


def _is_tenant(user):
    return getattr(user, "role", None) == "tenant"


def _require_operator(user):
    if getattr(user, "role", None) not in {"admin", "owner", "staff"} and not user.is_superuser:
        raise PermissionDenied("Bạn không có quyền truy cập khu vực quản lý.")


def _tenant_profile(user):
    try:
        return user.tenant_profile
    except Tenant.DoesNotExist as exc:
        raise PermissionDenied("Tài khoản chưa được liên kết với hồ sơ khách thuê.") from exc


def _tenant_contracts(tenant):
    return Contract.objects.filter(Q(representative=tenant) | Q(members__tenant=tenant)).distinct()


def public_home(request):
    rooms = Room.objects.filter(status=Room.Status.AVAILABLE, building__is_active=True).select_related("building").prefetch_related("amenities")
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
    rooms = Room.objects.filter(status=Room.Status.AVAILABLE, building__is_active=True).select_related("building", "building__owner").prefetch_related("amenities")
    q = request.GET.get("q", "").strip()
    selected_buildings = [name.strip() for name in request.GET.getlist("building") if name.strip()]
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    if q:
        rooms = rooms.filter(Q(number__icontains=q) | Q(building__name__icontains=q) | Q(building__address__icontains=q))
    if selected_buildings:
        rooms = rooms.filter(building__name__in=selected_buildings)
    try:
        if min_price:
            rooms = rooms.filter(monthly_rent__gte=min_price)
        if max_price:
            rooms = rooms.filter(monthly_rent__lte=max_price)
    except (TypeError, ValueError):
        min_price = max_price = ""
    return render(request, "public/room_list.html", {"rooms": rooms, "q": q, "min_price": min_price, "max_price": max_price, "selected_buildings": selected_buildings})


def public_room_detail(request, room_id):
    room = get_object_or_404(
        Room.objects.select_related("building", "building__owner").prefetch_related("amenities"),
        pk=room_id,
        status=Room.Status.AVAILABLE,
        building__is_active=True,
    )
    return render(request, "public/room_detail.html", {"room": room})


@login_required
def dashboard(request):
    if _is_tenant(request.user):
        return redirect("tenant-portal")
    _require_operator(request.user)
    invoices = Invoice.objects.exclude(status=Invoice.Status.CANCELLED)
    context = {
        "room_count": Room.objects.count(),
        "available_count": Room.objects.filter(status=Room.Status.AVAILABLE).count(),
        "occupied_count": Room.objects.filter(status=Room.Status.OCCUPIED).count(),
        "active_contract_count": Contract.objects.filter(status=Contract.Status.ACTIVE).count(),
        "unpaid_total": invoices.aggregate(total=Sum("total_amount") - Sum("paid_amount"))["total"] or 0,
        "open_incident_count": Incident.objects.filter(status__in=(Incident.Status.OPEN, Incident.Status.IN_PROGRESS)).count(),
        "recent_invoices": invoices.select_related("contract__room__building")[:8],
        "expiring_contracts": Contract.objects.filter(status=Contract.Status.ACTIVE).select_related("room", "representative").order_by("end_date")[:8],
    }
    return render(request, "rentals/dashboard.html", context)


LIST_CONFIG = {
    "buildings": (Building, "rentals/building_list.html"),
    "rooms": (Room, "rentals/room_list.html"),
    "tenants": (Tenant, "rentals/tenant_list.html"),
    "contracts": (Contract, "rentals/contract_list.html"),
    "invoices": (Invoice, "rentals/invoice_list.html"),
    "payments": (Payment, "rentals/payment_list.html"),
    "meters": (MeterReading, "rentals/meter_list.html"),
    "incidents": (Incident, "rentals/incident_list.html"),
}


@login_required
def object_list(request, resource):
    _require_operator(request.user)
    model, template = LIST_CONFIG[resource]
    queryset = model.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        search_map = {
            "buildings": Q(name__icontains=q) | Q(address__icontains=q),
            "rooms": Q(number__icontains=q) | Q(building__name__icontains=q),
            "tenants": Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(identity_number__icontains=q),
            "contracts": Q(code__icontains=q) | Q(representative__full_name__icontains=q),
            "invoices": Q(code__icontains=q) | Q(contract__code__icontains=q),
            "payments": Q(invoice__code__icontains=q) | Q(reference__icontains=q),
            "meters": Q(room__number__icontains=q) | Q(room__building__name__icontains=q),
            "incidents": Q(title__icontains=q) | Q(room__number__icontains=q),
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
        all_buildings = Building.objects.all()
        context.update({
            "status": status,
            "sort": sort,
            "building_total": all_buildings.count(),
            "building_active": all_buildings.filter(is_active=True).count(),
            "building_inactive": all_buildings.filter(is_active=False).count(),
        })
    if resource == "rooms":
        building_id = request.GET.get("building", "").strip()
        if building_id:
            queryset = queryset.filter(building_id=building_id)
        queryset = queryset.select_related("building")
        context.update({
            "buildings": Building.objects.filter(is_active=True).order_by("name"),
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
    buildings = Building.objects.filter(is_active=True).order_by("name")
    if building_id:
        buildings = buildings.filter(pk=building_id)

    summary_rooms = Room.objects.filter(building__in=buildings)
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
        "all_buildings": Building.objects.filter(is_active=True).order_by("name"),
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
    "meters": (MeterReadingForm, "Chỉ số điện nước"),
}


@login_required
@require_http_methods(["GET", "POST"])
def object_create(request, resource):
    _require_operator(request.user)
    form_class, title = FORM_CONFIG[resource]
    form = form_class(request.POST or None)
    if form.is_valid():
        obj = form.save(commit=False)
        if isinstance(obj, MeterReading):
            obj.recorded_by = request.user
        obj.save()
        form.save_m2m()
        return redirect(resource)
    return render(request, "rentals/form.html", {"form": form, "title": f"Thêm {title.lower()}"})


@login_required
@require_http_methods(["GET", "POST"])
def object_update(request, resource, object_id):
    _require_operator(request.user)
    form_class, title = FORM_CONFIG[resource]
    obj = get_object_or_404(form_class._meta.model, pk=object_id)
    form = form_class(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return redirect(resource)
    return render(request, "rentals/form.html", {"form": form, "title": f"Cập nhật {title.lower()}"})


@login_required
def api_dashboard_summary(request):
    _require_operator(request.user)
    room_statuses = list(Room.objects.values("status").annotate(count=Count("id")).order_by("status"))
    debt = Invoice.objects.exclude(status=Invoice.Status.CANCELLED).aggregate(total=Sum("total_amount") - Sum("paid_amount"))["total"] or 0
    return JsonResponse({"rooms": room_statuses, "total_debt": str(debt), "active_contracts": Contract.objects.filter(status=Contract.Status.ACTIVE).count()})


@login_required
def api_room_detail(request, room_id):
    _require_operator(request.user)
    room = get_object_or_404(Room.objects.select_related("building"), pk=room_id)
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
    objects = Invoice.objects.filter(contract__in=_tenant_contracts(tenant)).select_related("contract__room__building").order_by("-period")
    return render(request, "tenant/invoices.html", {"tenant": tenant, "objects": objects})


@login_required
def tenant_invoice_detail(request, invoice_id):
    tenant = _tenant_profile(request.user)
    invoice = get_object_or_404(
        Invoice.objects.prefetch_related("items", "payments").select_related("contract__room__building"),
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
def tenant_notifications(request):
    tenant = _tenant_profile(request.user)
    objects = request.user.notifications.all()
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "tenant/notifications.html", {"tenant": tenant, "objects": objects})
