from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import (
    Building,
    Contract,
    ContractMember,
    ContractService,
    Incident,
    Invoice,
    InvoiceItem,
    MeterReading,
    Payment,
    Room,
    Service,
    Tenant,
)
from .permissions import (
    get_accessible_buildings,
    get_accessible_contracts,
    get_accessible_invoices,
    get_accessible_rooms,
    get_accessible_services,
    get_accessible_tenants,
    get_assignable_staff,
    get_default_owner_for_operator,
    get_owner_ids_for_user,
    is_admin,
    is_owner,
    is_staff_role,
)
from .services import get_previous_meter_reading_value

User = get_user_model()


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class BuildingForm(StyledModelForm):
    class Meta:
        model = Building
        fields = ("name", "address", "owner", "staff", "description", "is_active")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["staff"].required = False
        self.fields["staff"].queryset = User.objects.filter(role="staff", is_active=True)
        if user is not None:
            if is_admin(user):
                self.fields["owner"].queryset = User.objects.filter(
                    Q(role__in=["owner", "admin"]) | Q(is_superuser=True)
                ).distinct()
                self.fields["staff"].queryset = User.objects.filter(role="staff", is_active=True)
            elif is_owner(user):
                self.fields["owner"].queryset = User.objects.filter(pk=user.pk)
                self.fields["owner"].initial = user.pk
                self.fields["owner"].required = False
                self.fields["staff"].queryset = User.objects.filter(
                    role="staff", is_active=True
                ).filter(Q(managed_owner=user) | Q(assigned_buildings__owner=user)).distinct()
            elif is_staff_role(user):
                owner_ids = get_owner_ids_for_user(user)
                self.fields["owner"].queryset = User.objects.filter(pk__in=owner_ids)
                self.fields["owner"].required = False
                self.fields["staff"].queryset = get_assignable_staff(user).filter(role="staff")

    def clean_owner(self):
        owner = self.cleaned_data.get("owner")
        if self.user is not None:
            if is_owner(self.user):
                return self.user
            if is_staff_role(self.user):
                if self.instance and self.instance.pk and self.instance.owner_id:
                    return self.instance.owner
                default_owner = get_default_owner_for_operator(self.user)
                if owner is None and default_owner is not None:
                    return default_owner
        if owner is None:
            raise forms.ValidationError("Vui lòng chọn chủ sở hữu tòa nhà.")
        return owner


class RoomForm(StyledModelForm):
    class Meta:
        model = Room
        fields = (
            "building",
            "number",
            "floor",
            "area",
            "monthly_rent",
            "deposit_amount",
            "max_occupants",
            "status",
            "amenities",
            "description",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user is not None:
            self.fields["building"].queryset = get_accessible_buildings(user)


class TenantForm(StyledModelForm):
    class Meta:
        model = Tenant
        fields = (
            "full_name",
            "phone",
            "email",
            "date_of_birth",
            "gender",
            "identity_number",
            "identity_issued_date",
            "permanent_address",
            "emergency_contact",
            "user",
            "is_active",
        )
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "identity_issued_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["user"].required = False
        self.fields["user"].label = "Tài khoản khách thuê liên kết"
        linked_filter = Q(tenant_profile__isnull=True)
        if self.instance and self.instance.pk and self.instance.user_id:
            linked_filter |= Q(pk=self.instance.user_id)
        self.fields["user"].queryset = User.objects.filter(role="tenant").filter(linked_filter)

    def save(self, commit=True):
        obj = super().save(commit=False)
        if obj.owner_id is None and self.user is not None:
            default_owner = get_default_owner_for_operator(self.user)
            if default_owner is not None and not is_admin(self.user):
                obj.owner = default_owner
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class TenantUserLinkForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ("user",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].required = False
        self.fields["user"].label = "Tài khoản tenant"
        self.fields["user"].widget.attrs.setdefault("class", "form-control")
        linked_filter = Q(tenant_profile__isnull=True)
        if self.instance and self.instance.pk and self.instance.user_id:
            linked_filter |= Q(pk=self.instance.user_id)
        self.fields["user"].queryset = User.objects.filter(role="tenant").filter(linked_filter)


class ContractForm(StyledModelForm):
    class Meta:
        model = Contract
        fields = (
            "code",
            "room",
            "representative",
            "start_date",
            "end_date",
            "monthly_rent",
            "deposit_amount",
            "billing_day",
            "due_day",
            "status",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["status"].required = False
        self.fields["status"].choices = [(Contract.Status.DRAFT, "Bản nháp")]
        self.fields["status"].initial = Contract.Status.DRAFT
        if user is not None:
            self.fields["room"].queryset = get_accessible_rooms(user)
            tenants_qs = get_accessible_tenants(user)
            if self.instance and self.instance.pk and self.instance.representative_id:
                tenants_qs = Tenant.objects.filter(
                    Q(pk__in=tenants_qs.values("pk")) | Q(pk=self.instance.representative_id)
                )
            else:
                tenants_qs = tenants_qs.filter(is_active=True)
            self.fields["representative"].queryset = tenants_qs

    def clean_status(self):
        return Contract.Status.DRAFT

    def clean(self):
        if self.instance and self.instance.pk:
            db_status = (
                Contract.objects.filter(pk=self.instance.pk)
                .values_list("status", flat=True)
                .first()
            )
            if db_status and db_status != Contract.Status.DRAFT:
                raise forms.ValidationError(
                    "Chỉ có thể chỉnh sửa hợp đồng khi đang ở trạng thái Bản nháp."
                )
        return super().clean()

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.status = Contract.Status.DRAFT
        if commit:
            obj.save()
            self.save_m2m()
            if obj.representative_id and obj.room_id:
                rep = obj.representative
                if rep.owner_id is None:
                    rep.owner_id = obj.room.building.owner_id
                    rep.save(update_fields=["owner", "updated_at"])
        return obj


class ContractRenewForm(forms.Form):
    new_end_date = forms.DateField(
        label="Ngày kết thúc mới",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    new_monthly_rent = forms.DecimalField(
        label="Giá thuê mới (để trống nếu giữ nguyên)",
        max_digits=14,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Giữ nguyên giá hiện tại"}),
    )
    notes = forms.CharField(
        label="Ghi chú gia hạn",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Ghi chú thêm..."}),
    )


class ContractMemberForm(StyledModelForm):
    class Meta:
        model = ContractMember
        fields = ("tenant", "joined_date", "left_date")
        widgets = {
            "joined_date": forms.DateInput(attrs={"type": "date"}),
            "left_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, contract=None, **kwargs):
        self.contract = contract
        super().__init__(*args, user=user, **kwargs)
        tenants_qs = get_accessible_tenants(user).filter(is_active=True) if user else Tenant.objects.filter(is_active=True)
        if contract is not None:
            existing_member_ids = contract.members.values_list("tenant_id", flat=True)
            tenants_qs = tenants_qs.exclude(pk=contract.representative_id).exclude(pk__in=existing_member_ids)
        self.fields["tenant"].queryset = tenants_qs


class ServiceForm(StyledModelForm):
    class Meta:
        model = Service
        fields = ("name", "unit", "unit_price", "is_metered", "is_active")

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("unit")
        if unit in {Service.Unit.KWH, Service.Unit.CUBIC_METER}:
            cleaned["is_metered"] = True
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if obj.owner_id is None and self.user is not None and not is_admin(self.user):
            obj.owner = get_default_owner_for_operator(self.user)
        if commit:
            obj.save()
        return obj


class ContractServiceForm(StyledModelForm):
    unit_price = forms.DecimalField(
        label="Đơn giá áp dụng (để trống sẽ lấy giá mặc định của dịch vụ)",
        max_digits=14,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Theo đơn giá danh mục"}),
    )

    class Meta:
        model = ContractService
        fields = ("service", "unit_price", "quantity", "is_active")

    def __init__(self, *args, user=None, contract=None, **kwargs):
        self.contract = contract
        super().__init__(*args, user=user, **kwargs)
        services_qs = get_accessible_services(user).filter(is_active=True) if user else Service.objects.filter(is_active=True)
        self.fields["service"].queryset = services_qs


class MeterReadingForm(StyledModelForm):
    previous_value = forms.DecimalField(
        label="Chỉ số đầu (để trống sẽ tự lấy chỉ số cuối kỳ trước)",
        max_digits=14,
        decimal_places=2,
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Tự động lấy từ kỳ trước"}),
    )

    class Meta:
        model = MeterReading
        fields = ("room", "meter_type", "period", "previous_value", "current_value")
        widgets = {"period": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        if user is not None:
            self.fields["room"].queryset = get_accessible_rooms(user)

    def clean(self):
        cleaned = super().clean()
        room = cleaned.get("room")
        meter_type = cleaned.get("meter_type")
        period = cleaned.get("period")
        prev_val = cleaned.get("previous_value")
        curr_val = cleaned.get("current_value")

        if room and meter_type and period:
            dup_qs = MeterReading.objects.filter(room=room, meter_type=meter_type, period=period)
            if self.instance and self.instance.pk:
                dup_qs = dup_qs.exclude(pk=self.instance.pk)
            if dup_qs.exists():
                raise forms.ValidationError("Đã tồn tại bản ghi chỉ số cho phòng, loại đồng hồ và kỳ này.")

            if prev_val is None:
                prev_val = get_previous_meter_reading_value(room, meter_type, period)
                cleaned["previous_value"] = prev_val
                self.instance.previous_value = prev_val

        if prev_val is not None and curr_val is not None:
            if curr_val < prev_val:
                self.add_error("current_value", "Chỉ số cuối không được nhỏ hơn chỉ số đầu.")

        return cleaned


class InvoiceCreateForm(forms.Form):
    contract = forms.ModelChoiceField(
        label="Hợp đồng",
        queryset=Contract.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    period = forms.DateField(
        label="Kỳ hóa đơn (ngày 01 của tháng)",
        initial=lambda: date.today().replace(day=1),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    due_date = forms.DateField(
        label="Hạn thanh toán",
        initial=lambda: date.today().replace(day=10),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    surcharge = forms.DecimalField(
        label="Phụ thu",
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    surcharge_description = forms.CharField(
        label="Nội dung phụ thu",
        max_length=255,
        required=False,
        initial="Phụ thu",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    discount = forms.DecimalField(
        label="Giảm trừ",
        max_digits=14,
        decimal_places=2,
        required=False,
        initial=Decimal("0"),
        min_value=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    status = forms.ChoiceField(
        label="Trạng thái khi tạo",
        choices=[
            (Invoice.Status.DRAFT, "Bản nháp (kiểm tra trước khi phát hành)"),
            (Invoice.Status.ISSUED, "Phát hành ngay"),
        ],
        initial=Invoice.Status.DRAFT,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    notes = forms.CharField(
        label="Ghi chú",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["contract"].queryset = (
                get_accessible_contracts(user)
                .filter(status=Contract.Status.ACTIVE)
                .select_related("room__building", "representative")
            )


class InvoiceBulkCreateForm(forms.Form):
    building = forms.ModelChoiceField(
        label="Tòa nhà (để trống để lập cho tất cả tòa nhà thuộc phạm vi)",
        queryset=Building.objects.none(),
        required=False,
        empty_label="Tất cả tòa nhà trong phạm vi",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    period = forms.DateField(
        label="Kỳ hóa đơn (ngày 01 của tháng)",
        initial=lambda: date.today().replace(day=1),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    due_date = forms.DateField(
        label="Hạn thanh toán",
        initial=lambda: date.today().replace(day=10),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    status = forms.ChoiceField(
        label="Trạng thái hóa đơn",
        choices=[
            (Invoice.Status.DRAFT, "Bản nháp"),
            (Invoice.Status.ISSUED, "Phát hành ngay"),
        ],
        initial=Invoice.Status.DRAFT,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["building"].queryset = get_accessible_buildings(user).filter(is_active=True)


class InvoiceDraftUpdateForm(StyledModelForm):
    class Meta:
        model = Invoice
        fields = ("due_date", "discount", "notes")
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        if self.instance and self.instance.pk:
            db_status = Invoice.objects.filter(pk=self.instance.pk).values_list("status", flat=True).first()
            if db_status and db_status != Invoice.Status.DRAFT:
                raise forms.ValidationError("Chỉ có thể chỉnh sửa hóa đơn khi đang ở trạng thái Bản nháp.")
        return super().clean()


class InvoiceItemForm(StyledModelForm):
    class Meta:
        model = InvoiceItem
        fields = ("service", "description", "quantity", "unit_price")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["service"].required = False
        if user is not None:
            self.fields["service"].queryset = get_accessible_services(user).filter(is_active=True)


class InvoiceCancelForm(forms.Form):
    reason = forms.CharField(
        label="Lý do hủy hóa đơn",
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Nhập lý do hủy..."}),
    )


class PaymentCreateForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ("invoice", "amount", "paid_at", "method", "reference", "notes")
        widgets = {
            "paid_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, user=None, initial_invoice=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["paid_at"].initial = timezone.now().strftime("%Y-%m-%dT%H:%M")
        if user is not None:
            qs = (
                get_accessible_invoices(user)
                .exclude(status__in=[Invoice.Status.DRAFT, Invoice.Status.CANCELLED, Invoice.Status.PAID])
                .select_related("contract__room__building")
            )
            if initial_invoice is not None:
                qs = Invoice.objects.filter(Q(pk__in=qs.values("pk")) | Q(pk=initial_invoice.pk))
                self.fields["invoice"].initial = initial_invoice.pk
                self.fields["amount"].initial = initial_invoice.balance
            self.fields["invoice"].queryset = qs


class IncidentManageForm(StyledModelForm):
    class Meta:
        model = Incident
        fields = ("priority", "status", "assigned_to", "resolution_notes")
        widgets = {
            "resolution_notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Ghi chú quá trình xử lý..."}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].label = "Người xử lý"
        building = self.instance.room.building if (self.instance and self.instance.pk and self.instance.room_id) else None
        if user is not None:
            self.fields["assigned_to"].queryset = get_assignable_staff(user, building=building)


class NotificationCreateForm(forms.Form):
    TARGET_CHOICES = [
        ("tenant", "Một khách thuê"),
        ("room", "Tất cả khách của một phòng"),
        ("building", "Tất cả khách của một tòa nhà"),
    ]

    target_type = forms.ChoiceField(
        label="Đối tượng nhận",
        choices=TARGET_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    tenant = forms.ModelChoiceField(
        label="Khách thuê (nếu gửi cho 1 khách thuê)",
        queryset=Tenant.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    room = forms.ModelChoiceField(
        label="Phòng (nếu gửi cho khách của 1 phòng)",
        queryset=Room.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    building = forms.ModelChoiceField(
        label="Tòa nhà (nếu gửi cho khách của 1 tòa nhà)",
        queryset=Building.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    title = forms.CharField(
        label="Tiêu đề thông báo",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    content = forms.CharField(
        label="Nội dung thông báo",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["tenant"].queryset = get_accessible_tenants(user).filter(is_active=True)
            self.fields["room"].queryset = get_accessible_rooms(user).select_related("building")
            self.fields["building"].queryset = get_accessible_buildings(user).filter(is_active=True)


class TenantIncidentForm(StyledModelForm):
    class Meta:
        model = Incident
        fields = ("room", "title", "description", "priority")
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant:
            self.fields["room"].queryset = Room.objects.filter(
                Q(contracts__representative=tenant) | Q(contracts__members__tenant=tenant),
                contracts__status=Contract.Status.ACTIVE,
            ).distinct()

    def clean_room(self):
        room = self.cleaned_data["room"]
        if self.tenant and not Contract.objects.filter(
            Q(representative=self.tenant) | Q(members__tenant=self.tenant),
            room=room,
            status=Contract.Status.ACTIVE,
        ).exists():
            raise forms.ValidationError("Bạn không có hợp đồng hiệu lực tại phòng này.")
        return room
