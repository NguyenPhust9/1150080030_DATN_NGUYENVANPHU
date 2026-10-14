from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from apps.rentals.models import Tenant

User = get_user_model()


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Mật khẩu hiện tại"
        self.fields["old_password"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nhập mật khẩu hiện tại...",
            "autocomplete": "current-password",
        })
        self.fields["new_password1"].label = "Mật khẩu mới"
        self.fields["new_password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nhập mật khẩu mới...",
            "autocomplete": "new-password",
        })
        self.fields["new_password2"].label = "Xác nhận mật khẩu mới"
        self.fields["new_password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Nhập lại mật khẩu mới...",
            "autocomplete": "new-password",
        })


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("last_name", "first_name", "email", "phone")
        labels = {
            "last_name": "Họ và tên đệm",
            "first_name": "Tên",
            "email": "Địa chỉ Email",
            "phone": "Số điện thoại",
        }
        widgets = {
            "last_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: Nguyễn Văn"}),
            "first_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: An"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "09xxxxxxxx"}),
        }


class TenantProfileForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = (
            "full_name",
            "phone",
            "email",
            "gender",
            "date_of_birth",
            "identity_number",
            "identity_issued_date",
            "permanent_address",
            "emergency_contact",
        )
        labels = {
            "full_name": "Họ và tên",
            "phone": "Số điện thoại",
            "email": "Địa chỉ Email",
            "gender": "Giới tính",
            "date_of_birth": "Ngày sinh",
            "identity_number": "Số CCCD / CMND / Hộ chiếu",
            "identity_issued_date": "Ngày cấp CCCD",
            "permanent_address": "Địa chỉ thường trú",
            "emergency_contact": "Thông tin liên hệ khẩn cấp",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Họ và tên đầy đủ"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "09xxxxxxxx"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
            "gender": forms.Select(attrs={"class": "form-control"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "identity_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Số CCCD 12 số"}),
            "identity_issued_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "permanent_address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Địa chỉ hộ khẩu thường trú"}),
            "emergency_contact": forms.TextInput(attrs={"class": "form-control", "placeholder": "Tên người thân - Số điện thoại"}),
        }

