import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UUIDTimeStampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField("ngày tạo", auto_now_add=True)
    updated_at = models.DateTimeField("ngày cập nhật", auto_now=True)

    class Meta:
        abstract = True


class Building(UUIDTimeStampedModel):
    name = models.CharField("tên tòa nhà", max_length=150)
    address = models.TextField("địa chỉ")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="buildings", verbose_name="chủ sở hữu")
    description = models.TextField("mô tả", blank=True)
    is_active = models.BooleanField("đang hoạt động", default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "tòa nhà"
        verbose_name_plural = "tòa nhà"

    def __str__(self):
        return self.name


class Amenity(UUIDTimeStampedModel):
    name = models.CharField("tên tiện nghi", max_length=100, unique=True)
    description = models.TextField("mô tả", blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "tiện nghi"
        verbose_name_plural = "tiện nghi"

    def __str__(self):
        return self.name


class Room(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Còn trống"
        RESERVED = "reserved", "Đã đặt"
        OCCUPIED = "occupied", "Đang thuê"
        MAINTENANCE = "maintenance", "Bảo trì"
        INACTIVE = "inactive", "Ngừng sử dụng"

    building = models.ForeignKey(Building, on_delete=models.PROTECT, related_name="rooms", verbose_name="tòa nhà")
    number = models.CharField("số/tên phòng", max_length=50)
    floor = models.PositiveSmallIntegerField("tầng", default=1)
    area = models.DecimalField("diện tích (m²)", max_digits=8, decimal_places=2, null=True, blank=True)
    monthly_rent = models.DecimalField("giá thuê/tháng", max_digits=14, decimal_places=2)
    deposit_amount = models.DecimalField("tiền cọc đề xuất", max_digits=14, decimal_places=2, default=0)
    max_occupants = models.PositiveSmallIntegerField("số người tối đa", default=2)
    status = models.CharField("trạng thái", max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="rooms", verbose_name="tiện nghi")
    description = models.TextField("mô tả", blank=True)

    class Meta:
        ordering = ("building__name", "floor", "number")
        constraints = [
            models.UniqueConstraint(fields=("building", "number"), name="unique_room_number_per_building"),
            models.CheckConstraint(condition=Q(monthly_rent__gte=0), name="room_rent_non_negative"),
            models.CheckConstraint(condition=Q(deposit_amount__gte=0), name="room_deposit_non_negative"),
        ]
        verbose_name = "phòng"
        verbose_name_plural = "phòng"

    def __str__(self):
        return f"{self.building.name} - Phòng {self.number}"


class Service(UUIDTimeStampedModel):
    class Unit(models.TextChoices):
        KWH = "kwh", "kWh"
        CUBIC_METER = "m3", "m³"
        PERSON = "person", "Người"
        ROOM = "room", "Phòng"
        FIXED = "fixed", "Cố định"

    name = models.CharField("tên dịch vụ", max_length=100, unique=True)
    unit = models.CharField("đơn vị", max_length=20, choices=Unit.choices)
    unit_price = models.DecimalField("đơn giá", max_digits=14, decimal_places=2)
    is_metered = models.BooleanField("tính theo chỉ số", default=False)
    is_active = models.BooleanField("đang áp dụng", default=True)

    class Meta:
        ordering = ("name",)
        constraints = [models.CheckConstraint(condition=Q(unit_price__gte=0), name="service_price_non_negative")]
        verbose_name = "dịch vụ"
        verbose_name_plural = "dịch vụ"

    def __str__(self):
        return self.name


class Tenant(UUIDTimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "Nam"
        FEMALE = "female", "Nữ"
        OTHER = "other", "Khác"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="tenant_profile", null=True, blank=True)
    full_name = models.CharField("họ và tên", max_length=150)
    phone = models.CharField("số điện thoại", max_length=20, db_index=True)
    email = models.EmailField("email", blank=True)
    date_of_birth = models.DateField("ngày sinh", null=True, blank=True)
    gender = models.CharField("giới tính", max_length=10, choices=Gender.choices, blank=True)
    identity_number = models.CharField("số CCCD/hộ chiếu", max_length=30, unique=True)
    identity_issued_date = models.DateField("ngày cấp", null=True, blank=True)
    permanent_address = models.TextField("địa chỉ thường trú", blank=True)
    emergency_contact = models.CharField("liên hệ khẩn cấp", max_length=150, blank=True)
    is_active = models.BooleanField("đang hoạt động", default=True)

    class Meta:
        ordering = ("full_name",)
        verbose_name = "khách thuê"
        verbose_name_plural = "khách thuê"

    def __str__(self):
        return self.full_name


class Contract(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Bản nháp"
        ACTIVE = "active", "Đang hiệu lực"
        EXPIRED = "expired", "Hết hạn"
        TERMINATED = "terminated", "Đã chấm dứt"
        CANCELLED = "cancelled", "Đã hủy"

    code = models.CharField("mã hợp đồng", max_length=40, unique=True)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="contracts", verbose_name="phòng")
    representative = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="represented_contracts", verbose_name="người đại diện")
    start_date = models.DateField("ngày bắt đầu", db_index=True)
    end_date = models.DateField("ngày kết thúc", db_index=True)
    monthly_rent = models.DecimalField("giá thuê/tháng", max_digits=14, decimal_places=2)
    deposit_amount = models.DecimalField("tiền cọc", max_digits=14, decimal_places=2, default=0)
    billing_day = models.PositiveSmallIntegerField("ngày lập hóa đơn", default=1)
    due_day = models.PositiveSmallIntegerField("hạn thanh toán", default=5)
    status = models.CharField("trạng thái", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.TextField("ghi chú", blank=True)

    class Meta:
        ordering = ("-start_date",)
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="contract_dates_valid"),
            models.CheckConstraint(condition=Q(monthly_rent__gte=0), name="contract_rent_non_negative"),
            models.CheckConstraint(condition=Q(deposit_amount__gte=0), name="contract_deposit_non_negative"),
            models.CheckConstraint(condition=Q(billing_day__gte=1, billing_day__lte=28), name="billing_day_valid"),
            models.CheckConstraint(condition=Q(due_day__gte=1, due_day__lte=28), name="due_day_valid"),
        ]
        verbose_name = "hợp đồng"
        verbose_name_plural = "hợp đồng"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "Ngày kết thúc phải sau ngày bắt đầu."})
        if self.room_id and self.start_date and self.end_date and self.status == self.Status.ACTIVE:
            overlap = Contract.objects.filter(
                room_id=self.room_id,
                status=self.Status.ACTIVE,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError({"room": "Phòng đã có hợp đồng hiệu lực trong khoảng thời gian này."})

    def __str__(self):
        return self.code


class ContractMember(UUIDTimeStampedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="members", verbose_name="hợp đồng")
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="contract_memberships", verbose_name="khách thuê")
    joined_date = models.DateField("ngày vào ở")
    left_date = models.DateField("ngày rời đi", null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("contract", "tenant"), name="unique_tenant_per_contract")]
        verbose_name = "thành viên hợp đồng"
        verbose_name_plural = "thành viên hợp đồng"

    def __str__(self):
        return f"{self.tenant} - {self.contract}"


class MeterReading(UUIDTimeStampedModel):
    class MeterType(models.TextChoices):
        ELECTRICITY = "electricity", "Điện"
        WATER = "water", "Nước"

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="meter_readings", verbose_name="phòng")
    meter_type = models.CharField("loại đồng hồ", max_length=20, choices=MeterType.choices)
    period = models.DateField("kỳ ghi chỉ số", help_text="Dùng ngày đầu tiên của tháng")
    previous_value = models.DecimalField("chỉ số đầu", max_digits=14, decimal_places=2)
    current_value = models.DecimalField("chỉ số cuối", max_digits=14, decimal_places=2)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_meter_readings")
    recorded_at = models.DateTimeField("thời gian ghi", auto_now_add=True)

    class Meta:
        ordering = ("-period", "room")
        constraints = [
            models.UniqueConstraint(fields=("room", "meter_type", "period"), name="unique_meter_reading_per_period"),
            models.CheckConstraint(condition=Q(previous_value__gte=0), name="meter_previous_non_negative"),
            models.CheckConstraint(condition=Q(current_value__gte=models.F("previous_value")), name="meter_current_gte_previous"),
        ]
        verbose_name = "chỉ số điện nước"
        verbose_name_plural = "chỉ số điện nước"

    @property
    def consumption(self):
        return self.current_value - self.previous_value

    def __str__(self):
        return f"{self.room} - {self.get_meter_type_display()} - {self.period:%m/%Y}"


class Invoice(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Bản nháp"
        ISSUED = "issued", "Đã phát hành"
        PARTIAL = "partial", "Thanh toán một phần"
        PAID = "paid", "Đã thanh toán"
        OVERDUE = "overdue", "Quá hạn"
        CANCELLED = "cancelled", "Đã hủy"

    code = models.CharField("mã hóa đơn", max_length=40, unique=True)
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, related_name="invoices", verbose_name="hợp đồng")
    period = models.DateField("kỳ hóa đơn", help_text="Dùng ngày đầu tiên của tháng", db_index=True)
    issued_date = models.DateField("ngày phát hành")
    due_date = models.DateField("hạn thanh toán", db_index=True)
    subtotal = models.DecimalField("tiền trước điều chỉnh", max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField("giảm trừ", max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField("tổng tiền", max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField("đã thanh toán", max_digits=14, decimal_places=2, default=0)
    status = models.CharField("trạng thái", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    notes = models.TextField("ghi chú", blank=True)

    class Meta:
        ordering = ("-period", "-issued_date")
        constraints = [
            models.UniqueConstraint(fields=("contract", "period"), condition=~Q(status="cancelled"), name="unique_active_invoice_period"),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name="invoice_subtotal_non_negative"),
            models.CheckConstraint(condition=Q(discount__gte=0), name="invoice_discount_non_negative"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="invoice_total_non_negative"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="invoice_paid_non_negative"),
        ]
        verbose_name = "hóa đơn"
        verbose_name_plural = "hóa đơn"

    @property
    def balance(self):
        return max(self.total_amount - self.paid_amount, Decimal("0"))

    def __str__(self):
        return self.code


class InvoiceItem(UUIDTimeStampedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items", verbose_name="hóa đơn")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, null=True, blank=True, related_name="invoice_items")
    description = models.CharField("nội dung", max_length=255)
    quantity = models.DecimalField("số lượng", max_digits=14, decimal_places=2, default=1)
    unit_price = models.DecimalField("đơn giá", max_digits=14, decimal_places=2)
    amount = models.DecimalField("thành tiền", max_digits=14, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=0), name="invoice_item_quantity_non_negative"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="invoice_item_price_non_negative"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="invoice_item_amount_non_negative"),
        ]
        verbose_name = "chi tiết hóa đơn"
        verbose_name_plural = "chi tiết hóa đơn"

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return self.description


class Payment(UUIDTimeStampedModel):
    class Method(models.TextChoices):
        CASH = "cash", "Tiền mặt"
        TRANSFER = "transfer", "Chuyển khoản"
        OTHER = "other", "Khác"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments", verbose_name="hóa đơn")
    amount = models.DecimalField("số tiền", max_digits=14, decimal_places=2)
    paid_at = models.DateTimeField("thời gian thanh toán")
    method = models.CharField("phương thức", max_length=20, choices=Method.choices)
    reference = models.CharField("mã tham chiếu", max_length=100, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_payments")
    notes = models.TextField("ghi chú", blank=True)
    is_void = models.BooleanField("đã hủy", default=False)

    class Meta:
        ordering = ("-paid_at",)
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive")]
        verbose_name = "thanh toán"
        verbose_name_plural = "thanh toán"

    def __str__(self):
        return f"{self.invoice.code} - {self.amount}"


class Incident(UUIDTimeStampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Thấp"
        MEDIUM = "medium", "Trung bình"
        HIGH = "high", "Cao"
        URGENT = "urgent", "Khẩn cấp"

    class Status(models.TextChoices):
        OPEN = "open", "Mới"
        IN_PROGRESS = "in_progress", "Đang xử lý"
        RESOLVED = "resolved", "Đã xử lý"
        CLOSED = "closed", "Đã đóng"

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="incidents", verbose_name="phòng")
    reported_by = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="reported_incidents", verbose_name="người báo")
    title = models.CharField("tiêu đề", max_length=200)
    description = models.TextField("mô tả")
    priority = models.CharField("mức ưu tiên", max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField("trạng thái", max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_incidents")
    resolved_at = models.DateTimeField("thời gian xử lý xong", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "sự cố"
        verbose_name_plural = "sự cố"

    def __str__(self):
        return self.title


class Notification(UUIDTimeStampedModel):
    title = models.CharField("tiêu đề", max_length=200)
    content = models.TextField("nội dung")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", verbose_name="người nhận")
    is_read = models.BooleanField("đã đọc", default=False, db_index=True)
    read_at = models.DateTimeField("thời gian đọc", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "thông báo"
        verbose_name_plural = "thông báo"

    def __str__(self):
        return self.title
