"""Tenant forms and permission-checked access to private identity images."""
from uuid import uuid4

import cloudinary.uploader
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .chat_media import ChatUploadError, chat_image_url, configure_chat_cloudinary, remove_chat_uploads
from .forms import TenantForm
from .models import Tenant, TenantIdentityImage
from .permissions import get_accessible_tenants, require_operator


def save_tenant_form(form):
    uploaded = []
    old_images = []
    try:
        if form.prepared_identity_images:
            configure_chat_cloudinary()
        for side, (file, _name, mime) in form.prepared_identity_images.items():
            result = cloudinary.uploader.upload(
                file, resource_type="image", type="authenticated",
                public_id=f"ql-phong-cho-thue/tenant-identities/{uuid4().hex}",
                overwrite=False, timeout=30,
            )
            uploaded.append({"side": side, "public_id": result["public_id"],
                             "format": result.get("format") or ("png" if mime == "image/png" else "jpg")})
        with transaction.atomic():
            if form.instance.pk and not form.instance._state.adding:
                Tenant.objects.select_for_update().get(pk=form.instance.pk)
            tenant = form.save()
            for side in ("front", "back"):
                replacement = next((item for item in uploaded if item["side"] == side), None)
                if replacement or form.cleaned_data.get(f"remove_identity_{side}"):
                    existing = tenant.identity_images.filter(side=side)
                    old_images.extend(existing.values("public_id"))
                    existing.delete()
                if replacement:
                    TenantIdentityImage.objects.create(tenant=tenant, **replacement)
            if old_images:
                transaction.on_commit(lambda: remove_chat_uploads(old_images))
        return tenant
    except Exception:
        if uploaded:
            remove_chat_uploads(uploaded)
        raise


@login_required
@require_http_methods(["GET", "POST"])
def tenant_form(request, object_id=None):
    require_operator(request.user)
    tenant = get_object_or_404(get_accessible_tenants(request.user), pk=object_id) if object_id else None
    form = TenantForm(request.POST if request.method == "POST" else None,
                      request.FILES or None, instance=tenant, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_tenant_form(form)
        except Exception:
            form.add_error(None, "Chưa lưu được hồ sơ hoặc ảnh CCCD. Vui lòng thử lại; nếu đã chọn ảnh, hãy chọn lại ảnh.")
        else:
            messages.success(request, "Đã cập nhật khách thuê." if tenant else "Đã thêm khách thuê mới.")
            return redirect("tenant-detail", tenant_id=saved.pk) if tenant else redirect("tenants")
    images = {image.side: image for image in tenant.identity_images.all()} if tenant else {}
    response = render(request, "rentals/tenant_form.html", {
        "form": form, "tenant": tenant, "editing": tenant is not None,
        "front_image": images.get("front"), "back_image": images.get("back"),
    })
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_http_methods(["GET"])
def tenant_identity_image(request, tenant_id, side):
    require_operator(request.user)
    tenant = get_object_or_404(get_accessible_tenants(request.user), pk=tenant_id)
    image = get_object_or_404(TenantIdentityImage, tenant=tenant, side=side)
    try:
        response = redirect(chat_image_url(image))
    except ChatUploadError:
        response = HttpResponse("Chưa tải được ảnh CCCD. Vui lòng thử lại.", status=503)
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Content-Type-Options"] = "nosniff"
    return response
