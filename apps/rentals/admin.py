from django.contrib import admin

from .models import (
    Amenity,
    Building,
    Contract,
    ContractMember,
    Incident,
    Invoice,
    InvoiceItem,
    MeterReading,
    Notification,
    Payment,
    Room,
    Service,
    Tenant,
)


class ContractMemberInline(admin.TabularInline):
    model = ContractMember
    extra = 1


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    readonly_fields = ("amount",)


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
    inlines = (ContractMemberInline,)


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

admin.site.site_header = "Quản lý phòng cho thuê"
admin.site.site_title = "QL Phòng Cho Thuê"
admin.site.index_title = "Quản trị hệ thống"
