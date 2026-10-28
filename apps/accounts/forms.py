from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from apps.rentals.models import Building, Tenant
from apps.rentals.permissions import (
    can_lock_or_unlock_user,
    get_accessible_buildings,
    get_creatable_roles,
    get_linkable_tenants_for_user,
    is_admin,
    is_owner,
)

from .services import validate_account_password

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


class UserCreateForm(forms.Form):
    username = forms.CharField(
        label="Tên đăng nhập (Username)",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: nguyenvana", "autocomplete": "off"}),
    )
    last_name = forms.CharField(
        label="Họ và tên đệm",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: Nguyễn Văn"}),
    )
    first_name = forms.CharField(
        label="Tên",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: An"}),
    )
    email = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "email@example.com"}),
    )
    phone = forms.CharField(
        label="Số điện thoại",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "09xxxxxxxx"}),
    )
    role = forms.ChoiceField(
        label="Vai trò",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control", "id": "id_role"}),
    )
    password1 = forms.CharField(
        label="Mật khẩu",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Tối thiểu 8 ký tự...", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Xác nhận mật khẩu",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Nhập lại mật khẩu...", "autocomplete": "new-password"}),
    )
    is_active = forms.BooleanField(
        label="Trạng thái hoạt động (Cho phép đăng nhập)",
        required=False,
        initial=True,
    )
    managed_owner = forms.ModelChoiceField(
        label="Chủ nhà quản lý (Dành cho Nhân viên)",
        queryset=User.objects.none(),
        required=False,
        empty_label="--- Chọn chủ nhà quản lý ---",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    assigned_buildings = forms.ModelMultipleChoiceField(
        label="Tòa nhà được phân công (Dành cho Nhân viên)",
        queryset=Building.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    owned_buildings = forms.ModelMultipleChoiceField(
        label="Tòa nhà sở hữu (Dành cho Chủ nhà)",
        queryset=Building.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    linked_tenant = forms.ModelChoiceField(
        label="Liên kết hồ sơ khách thuê (Dành cho Khách thuê)",
        queryset=Tenant.objects.none(),
        required=False,
        empty_label="--- Chưa liên kết hồ sơ khách thuê ---",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        role_choices = get_creatable_roles(actor)
        self.fields["role"].choices = role_choices
        if role_choices and not self.initial.get("role"):
            self.fields["role"].initial = role_choices[0][0]

        if is_admin(actor):
            self.fields["managed_owner"].queryset = User.objects.filter(role=User.Role.OWNER, is_active=True).order_by("username")
            self.fields["owned_buildings"].queryset = Building.objects.all().order_by("name")
        elif is_owner(actor):
            self.fields["managed_owner"].queryset = User.objects.filter(pk=actor.pk)
            self.fields["managed_owner"].initial = actor.pk
            self.fields["managed_owner"].widget = forms.HiddenInput()
            self.fields["owned_buildings"].widget = forms.MultipleHiddenInput()

        self.fields["assigned_buildings"].queryset = get_accessible_buildings(actor).order_by("name")
        self.fields["linked_tenant"].queryset = get_linkable_tenants_for_user(actor)

    def clean_username(self):
        raw = (self.cleaned_data.get("username") or "").strip()
        normalized = User.normalize_username(raw)
        if not normalized:
            raise ValidationError("Tên đăng nhập không được để trống.")
        if " " in normalized:
            raise ValidationError("Tên đăng nhập không được chứa khoảng trắng.")
        if User.objects.filter(username__iexact=normalized).exists():
            raise ValidationError("Tên đăng nhập này đã tồn tại. Vui lòng chọn tên khác.")
        return normalized

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        pw1 = cleaned.get("password1")
        pw2 = cleaned.get("password2")
        username = cleaned.get("username") or ""
        first_name = cleaned.get("first_name") or ""
        last_name = cleaned.get("last_name") or ""
        email = cleaned.get("email") or ""

        if pw1 and pw2 and pw1 != pw2:
            self.add_error("password2", "Hai trường mật khẩu không khớp.")
        elif pw1:
            temp_user = User(username=username, first_name=first_name, last_name=last_name, email=email)
            try:
                validate_account_password(pw1, user=temp_user)
            except ValidationError as exc:
                self.add_error("password1", exc)

        managed_owner = cleaned.get("managed_owner")
        assigned_buildings = list(cleaned.get("assigned_buildings") or [])
        linked_tenant = cleaned.get("linked_tenant")

        if role == User.Role.OWNER:
            if not is_admin(self.actor):
                self.add_error("role", "Chỉ Quản trị viên mới được phép tạo tài khoản Chủ nhà.")
        elif role == User.Role.STAFF:
            if is_owner(self.actor):
                cleaned["managed_owner"] = self.actor
                managed_owner = self.actor
            if not managed_owner and not assigned_buildings:
                self.add_error(
                    "managed_owner",
                    "Nhân viên phải thuộc một Chủ nhà quản lý hoặc được phân công ít nhất một tòa nhà.",
                )
            if managed_owner and assigned_buildings:
                invalid_buildings = [
                    b.name for b in assigned_buildings if b.owner_id and b.owner_id != managed_owner.pk
                ]
                if invalid_buildings:
                    self.add_error(
                        "assigned_buildings",
                        f"Các tòa nhà sau không thuộc chủ nhà {managed_owner}: {', '.join(invalid_buildings)}.",
                    )
        elif role == User.Role.TENANT:
            if linked_tenant and linked_tenant.user_id is not None:
                self.add_error("linked_tenant", "Hồ sơ khách thuê này đã được liên kết với một tài khoản khác.")

        return cleaned


class UserUpdateForm(forms.Form):
    username = forms.CharField(
        label="Tên đăng nhập (Username)",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        label="Họ và tên đệm",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        label="Tên",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(
        label="Email",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    phone = forms.CharField(
        label="Số điện thoại",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    role = forms.ChoiceField(
        label="Vai trò",
        choices=(),
        widget=forms.Select(attrs={"class": "form-control", "id": "id_role"}),
    )
    is_active = forms.BooleanField(
        label="Trạng thái hoạt động (Cho phép đăng nhập)",
        required=False,
    )
    managed_owner = forms.ModelChoiceField(
        label="Chủ nhà quản lý (Dành cho Nhân viên)",
        queryset=User.objects.none(),
        required=False,
        empty_label="--- Chọn chủ nhà quản lý ---",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    assigned_buildings = forms.ModelMultipleChoiceField(
        label="Tòa nhà được phân công (Dành cho Nhân viên)",
        queryset=Building.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    owned_buildings = forms.ModelMultipleChoiceField(
        label="Tòa nhà sở hữu (Dành cho Chủ nhà)",
        queryset=Building.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    linked_tenant = forms.ModelChoiceField(
        label="Liên kết hồ sơ khách thuê (Dành cho Khách thuê)",
        queryset=Tenant.objects.none(),
        required=False,
        empty_label="--- Chưa liên kết hồ sơ khách thuê ---",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, actor=None, instance: User = None, **kwargs):
        self.actor = actor
        self.instance = instance
        existing_tenant = getattr(instance, "tenant_profile", None) if instance else None

        if instance and not kwargs.get("initial"):
            kwargs["initial"] = {
                "username": instance.username,
                "last_name": instance.last_name,
                "first_name": instance.first_name,
                "email": instance.email,
                "phone": instance.phone,
                "role": instance.role,
                "is_active": instance.is_active,
                "managed_owner": instance.managed_owner_id,
                "assigned_buildings": list(instance.assigned_buildings.values_list("pk", flat=True)),
                "owned_buildings": list(instance.buildings.values_list("pk", flat=True)),
                "linked_tenant": existing_tenant.pk if existing_tenant else None,
            }

        super().__init__(*args, **kwargs)

        if instance and instance.role == User.Role.ADMIN:
            role_choices = [(User.Role.ADMIN, "Quản trị viên")]
        elif actor and instance and actor.pk == instance.pk:
            role_choices = [(instance.role, instance.get_role_display())]
        else:
            role_choices = get_creatable_roles(actor)
            if instance and (instance.role, instance.get_role_display()) not in role_choices:
                role_choices = [(instance.role, instance.get_role_display())] + list(role_choices)
        self.fields["role"].choices = role_choices

        if is_admin(actor):
            self.fields["managed_owner"].queryset = User.objects.filter(role=User.Role.OWNER).order_by("username")
            self.fields["owned_buildings"].queryset = Building.objects.all().order_by("name")
        elif is_owner(actor):
            self.fields["managed_owner"].queryset = User.objects.filter(pk=actor.pk)
            self.fields["managed_owner"].initial = actor.pk
            self.fields["managed_owner"].widget = forms.HiddenInput()
            self.fields["owned_buildings"].widget = forms.MultipleHiddenInput()

        self.fields["assigned_buildings"].queryset = get_accessible_buildings(actor).order_by("name")
        self.fields["linked_tenant"].queryset = get_linkable_tenants_for_user(actor, current_user=instance)

    def clean_username(self):
        raw = (self.cleaned_data.get("username") or "").strip()
        normalized = User.normalize_username(raw)
        if not normalized:
            raise ValidationError("Tên đăng nhập không được để trống.")
        if " " in normalized:
            raise ValidationError("Tên đăng nhập không được chứa khoảng trắng.")
        qs = User.objects.filter(username__iexact=normalized)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Tên đăng nhập này đã tồn tại. Vui lòng chọn tên khác.")
        return normalized

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        is_active = bool(cleaned.get("is_active"))
        managed_owner = cleaned.get("managed_owner")
        assigned_buildings = list(cleaned.get("assigned_buildings") or [])
        linked_tenant = cleaned.get("linked_tenant")

        if self.actor and self.instance and self.actor.pk == self.instance.pk and role != self.instance.role:
            self.add_error("role", "Không thể tự thay đổi vai trò của chính mình.")

        if self.instance and is_active != self.instance.is_active:
            allowed_lock, lock_msg = can_lock_or_unlock_user(self.actor, self.instance)
            if not allowed_lock:
                self.add_error("is_active", lock_msg)

        if role == User.Role.STAFF:
            if is_owner(self.actor):
                cleaned["managed_owner"] = self.actor
                managed_owner = self.actor
            if not managed_owner and not assigned_buildings:
                self.add_error(
                    "managed_owner",
                    "Nhân viên phải thuộc một Chủ nhà quản lý hoặc được phân công ít nhất một tòa nhà.",
                )
            if managed_owner and assigned_buildings:
                invalid_buildings = [
                    b.name for b in assigned_buildings if b.owner_id and b.owner_id != managed_owner.pk
                ]
                if invalid_buildings:
                    self.add_error(
                        "assigned_buildings",
                        f"Các tòa nhà sau không thuộc chủ nhà {managed_owner}: {', '.join(invalid_buildings)}.",
                    )
        elif role == User.Role.TENANT:
            if linked_tenant and linked_tenant.user_id is not None and (
                not self.instance or linked_tenant.user_id != self.instance.pk
            ):
                self.add_error("linked_tenant", "Hồ sơ khách thuê này đã được liên kết với một tài khoản khác.")

        return cleaned


class UserLockUnlockForm(forms.Form):
    reason = forms.CharField(
        label="Lý do khóa / mở khóa tài khoản",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nhập lý do khóa hoặc mở khóa tài khoản (ví dụ: Nghỉ việc, hết hợp đồng...)",
            }
        ),
    )


class AdminPasswordResetForm(forms.Form):
    new_password1 = forms.CharField(
        label="Mật khẩu mới",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nhập mật khẩu mới (tối thiểu 8 ký tự)...",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Xác nhận mật khẩu mới",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nhập lại mật khẩu mới...",
                "autocomplete": "new-password",
            }
        ),
    )
    must_change_password = forms.BooleanField(
        label="Buộc người dùng đổi mật khẩu ở lần đăng nhập tiếp theo",
        required=False,
        initial=True,
    )
    reason = forms.CharField(
        label="Ghi chú / Lý do đặt lại mật khẩu",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ví dụ: Người dùng quên mật khẩu, yêu cầu cấp lại...",
            }
        ),
    )

    def __init__(self, *args, target_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_user = target_user

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get("new_password1")
        pw2 = cleaned.get("new_password2")
        if pw1 and pw2 and pw1 != pw2:
            self.add_error("new_password2", "Mật khẩu xác nhận không khớp với mật khẩu mới.")
        elif pw1:
            try:
                validate_account_password(pw1, user=self.target_user)
            except ValidationError as exc:
                self.add_error("new_password1", exc)
        return cleaned

