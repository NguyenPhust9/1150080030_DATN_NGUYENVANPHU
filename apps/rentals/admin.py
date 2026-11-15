from django.contrib import admin

from .models import (
    AlertEvent,
    Amenity,
    Building,
    Camera,
    ChatMessage,
    Contract,
    ContractMember,
    ContractService,
    Conversation,
    ExitPoint,
    HazardZone,
    Incident,
    IndoorMap,
    Invoice,
    InvoiceItem,
    MapEdge,
    MapNode,
    MapZone,
    MeterReading,
    Notification,
    Payment,
    PriceSuggestion,
    Room,
    RoomMedia,
    SafetyDevice,
    Service,
    Tenant,
)


class ContractMemberInline(admin.TabularInline):
    model = ContractMember
    extra = 1


class ContractServiceInline(admin.TabularInline):
    model = ContractService
    extra = 1


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ("amount",)


@admin.register(IndoorMap)
class IndoorMapAdmin(admin.ModelAdmin):
    list_display = ("building", "floor", "name", "width", "height")
    list_filter = ("building",)


@admin.register(MapNode)
class MapNodeAdmin(admin.ModelAdmin):
    list_display = ("label", "indoor_map", "kind", "room", "x", "y", "is_blocked")
    list_filter = ("indoor_map", "kind", "is_blocked")
    autocomplete_fields = ("room",)


@admin.register(MapEdge)
class MapEdgeAdmin(admin.ModelAdmin):
    list_display = ("start", "end", "indoor_map", "is_blocked")
    list_filter = ("indoor_map", "is_blocked")


@admin.register(MapZone)
class MapZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "indoor_map", "kind", "room", "x", "y", "width", "height")
    list_filter = ("indoor_map", "kind")
    autocomplete_fields = ("room",)


@admin.register(ExitPoint)
class ExitPointAdmin(admin.ModelAdmin):
    list_display = ("name", "indoor_map", "node")
    list_filter = ("indoor_map",)


@admin.register(SafetyDevice)
class SafetyDeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "indoor_map", "kind", "x", "y")
    list_filter = ("indoor_map", "kind")


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "indoor_map", "zone", "is_active")
    list_filter = ("indoor_map", "is_active")


@admin.register(HazardZone)
class HazardZoneAdmin(admin.ModelAdmin):
    list_display = ("zone", "indoor_map", "camera", "is_active", "is_simulation", "created_at")
    list_filter = ("indoor_map", "is_active", "is_simulation")


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = ("camera", "label", "confidence", "status", "created_at")
    list_filter = ("status", "camera__indoor_map")


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "owner", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "address")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("number", "building", "floor", "monthly_rent", "status")
    list_filter = ("building", "status", "floor")
    search_fields = ("number", "building__name")
    filter_horizontal = ("amenities",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "identity_number", "is_active")
    list_filter = ("is_active", "gender")
    search_fields = ("full_name", "phone", "email", "identity_number")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("code", "room", "representative", "start_date", "end_date", "status")
    list_filter = ("status", "room__building")
    search_fields = ("code", "representative__full_name", "room__number")
    inlines = (ContractMemberInline, ContractServiceInline)


@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("room", "meter_type", "period", "previous_value", "current_value", "consumption")
    list_filter = ("meter_type", "period", "room__building")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("code", "contract", "period", "total_amount", "paid_amount", "status", "due_date")
    list_filter = ("status", "period")
    search_fields = ("code", "contract__code", "contract__representative__full_name")
    inlines = (InvoiceItemInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "amount", "paid_at", "method", "is_void")
    list_filter = ("method", "is_void")
    search_fields = ("invoice__code", "reference")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("title", "room", "priority", "status", "assigned_to", "created_at")
    list_filter = ("priority", "status", "room__building")
    search_fields = ("title", "description", "room__number")


admin.site.register(Amenity)
admin.site.register(Service)
admin.site.register(Notification)
admin.site.register(RoomMedia)
admin.site.register(Conversation)
admin.site.register(ChatMessage)
admin.site.register(PriceSuggestion)

admin.site.site_header = "Quản lý phòng cho thuê"
admin.site.site_title = "QL Phòng Cho Thuê"
admin.site.index_title = "Quản trị hệ thống"
