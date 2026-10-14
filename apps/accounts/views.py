from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods

from .forms import StyledPasswordChangeForm, TenantProfileForm, UserProfileForm

User = get_user_model()


class CustomPasswordChangeView(PasswordChangeView):
    form_class = StyledPasswordChangeForm
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("password-change")

    def form_valid(self, form):
        messages.success(self.request, "Đổi mật khẩu thành công! Mật khẩu mới đã được kích hoạt.")
        return super().form_valid(form)


@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    user = request.user
    tenant = getattr(user, "tenant_profile", None)
    is_tenant_account = (user.role == "tenant") and (tenant is not None)

    if is_tenant_account:
        if request.method == "POST":
            form = TenantProfileForm(request.POST, instance=tenant)
            if form.is_valid():
                tenant = form.save()
                # Đồng bộ thông tin cơ bản sang bảng User
                if tenant.email:
                    user.email = tenant.email
                if tenant.phone:
                    user.phone = tenant.phone
                parts = tenant.full_name.strip().rsplit(" ", 1)
                if len(parts) == 2:
                    user.last_name, user.first_name = parts[0], parts[1]
                else:
                    user.first_name = tenant.full_name.strip()
                    user.last_name = ""
                user.save(update_fields=["email", "phone", "first_name", "last_name"])
                messages.success(request, "Cập nhật hồ sơ khách thuê thành công!")
                return redirect("user-profile")
        else:
            form = TenantProfileForm(instance=tenant)
    else:
        if request.method == "POST":
            form = UserProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                messages.success(request, "Cập nhật hồ sơ tài khoản thành công!")
                return redirect("user-profile")
        else:
            form = UserProfileForm(instance=user)

    context = {
        "title": "Hồ sơ cá nhân",
        "form": form,
        "is_tenant": is_tenant_account,
        "tenant": tenant,
    }
    return render(request, "accounts/profile.html", context)

