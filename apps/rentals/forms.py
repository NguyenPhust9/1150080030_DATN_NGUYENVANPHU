from django import forms
from django.db.models import Q

from .models import Building, Contract, Incident, MeterReading, Room, Tenant


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class BuildingForm(StyledModelForm):
    class Meta:
        model = Building
        fields = ("name", "address", "owner", "description", "is_active")


class RoomForm(StyledModelForm):
    class Meta:
        model = Room
        fields = ("building", "number", "floor", "area", "monthly_rent", "deposit_amount", "max_occupants", "status", "amenities", "description")


class TenantForm(StyledModelForm):
    class Meta:
        model = Tenant
        fields = ("full_name", "phone", "email", "date_of_birth", "gender", "identity_number", "identity_issued_date", "permanent_address", "emergency_contact", "is_active")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}), "identity_issued_date": forms.DateInput(attrs={"type": "date"})}


class ContractForm(StyledModelForm):
    class Meta:
        model = Contract
        fields = ("code", "room", "representative", "start_date", "end_date", "monthly_rent", "deposit_amount", "billing_day", "due_day", "status", "notes")
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"})}


class MeterReadingForm(StyledModelForm):
    class Meta:
        model = MeterReading
        fields = ("room", "meter_type", "period", "previous_value", "current_value")
        widgets = {"period": forms.DateInput(attrs={"type": "date"})}


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
