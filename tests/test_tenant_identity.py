from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.rentals.models import Tenant, TenantIdentityImage


def photo(name="identity.png", color="blue"):
    output = BytesIO()
    Image.new("RGB", (160, 100), color).save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


class TenantIdentityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="identity_owner", role="owner")
        self.other = User.objects.create_user(username="identity_other", role="owner")
        self.tenant_user = User.objects.create_user(username="identity_tenant", role="tenant")
        self.tenant = Tenant.objects.create(owner=self.owner, full_name="Khách hiện tại", identity_number="079000001111")
        self.client.force_login(self.owner)

    def test_name_only_creates_multiple_tenants_without_identity_or_contacts(self):
        for name in ("Khách A", "Khách B"):
            response = self.client.post(reverse("tenant-create"), {"full_name": name, "is_active": "on"})
            self.assertRedirects(response, reverse("tenants"))
            tenant = Tenant.objects.get(full_name=name)
            self.assertIsNone(tenant.identity_number)
            self.assertEqual(tenant.phone, "")
            self.assertEqual(tenant.email, "")
            self.assertEqual(tenant.owner, self.owner)
            self.assertFalse(tenant.identity_images.exists())

    def test_duplicate_nonempty_identity_and_invalid_email_still_rejected(self):
        response = self.client.post(reverse("tenant-create"), {"full_name": "Trùng", "identity_number": self.tenant.identity_number})
        self.assertEqual(response.status_code, 200)
        self.assertIn("identity_number", response.context["form"].errors)
        response = self.client.post(reverse("tenant-create"), {"full_name": "Sai email", "email": "invalid"})
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(Tenant.objects.filter(full_name="Sai email").exists())

    @patch("apps.rentals.tenant_views.configure_chat_cloudinary")
    @patch("apps.rentals.tenant_views.cloudinary.uploader.upload")
    def test_optional_two_sided_private_upload_and_occupation(self, upload, configure):
        upload.side_effect = [{"public_id": "private/front", "format": "png"}, {"public_id": "private/back", "format": "png"}]
        response = self.client.post(reverse("tenant-create"), {
            "full_name": "Có ảnh", "identity_front": photo(), "identity_back": photo("back.png"),
            "occupation": "Sinh viên", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        tenant = Tenant.objects.get(full_name="Có ảnh")
        self.assertEqual(tenant.occupation, "Sinh viên")
        self.assertEqual(set(tenant.identity_images.values_list("side", flat=True)), {"front", "back"})
        configure.assert_called_once()
        for call in upload.call_args_list:
            self.assertEqual(call.kwargs["type"], "authenticated")
            self.assertTrue(call.kwargs["public_id"].startswith("ql-phong-cho-thue/tenant-identities/"))

    @patch("apps.rentals.tenant_views.cloudinary.uploader.upload")
    def test_malformed_and_oversized_images_are_rejected_before_upload(self, upload):
        for image in (SimpleUploadedFile("fake.jpg", b"not an image", "image/jpeg"),
                      SimpleUploadedFile("huge.png", b"0" * (5 * 1024 * 1024 + 1), "image/png")):
            response = self.client.post(reverse("tenant-create"), {"full_name": "Ảnh lỗi", "identity_front": image})
            self.assertEqual(response.status_code, 200)
            self.assertIn("identity_front", response.context["form"].errors)
        upload.assert_not_called()
        self.assertFalse(Tenant.objects.filter(full_name="Ảnh lỗi").exists())

    @patch("apps.rentals.tenant_views.configure_chat_cloudinary")
    @patch("apps.rentals.tenant_views.remove_chat_uploads")
    @patch("apps.rentals.tenant_views.cloudinary.uploader.upload")
    def test_failed_second_upload_cleans_first_and_does_not_create_tenant(self, upload, cleanup, configure):
        upload.side_effect = [{"public_id": "private/first", "format": "png"}, RuntimeError("provider secret")]
        response = self.client.post(reverse("tenant-create"), {
            "full_name": "Không lưu", "identity_front": photo(), "identity_back": photo("back.png"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chưa lưu được hồ sơ")
        self.assertNotContains(response, "provider secret")
        self.assertFalse(Tenant.objects.filter(full_name="Không lưu").exists())
        self.assertEqual(cleanup.call_args.args[0][0]["public_id"], "private/first")

    @patch("apps.rentals.tenant_views.configure_chat_cloudinary")
    @patch("apps.rentals.tenant_views.remove_chat_uploads")
    @patch("apps.rentals.tenant_views.cloudinary.uploader.upload", return_value={"public_id": "private/new", "format": "png"})
    def test_replace_preserve_and_remove_images(self, upload, cleanup, configure):
        TenantIdentityImage.objects.create(tenant=self.tenant, side="front", public_id="private/old")
        url = reverse("tenant-update", args=[self.tenant.pk])
        self.client.post(url, {"full_name": "Đã sửa", "is_active": "on"})
        self.assertEqual(self.tenant.identity_images.get().public_id, "private/old")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {"full_name": "Đã sửa", "identity_front": photo(), "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.tenant.identity_images.get().public_id, "private/new")
        cleanup.assert_called_with([{"public_id": "private/old"}])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {"full_name": "Đã sửa", "remove_identity_front": "on", "is_active": "on"})
        self.assertFalse(self.tenant.identity_images.exists())
        cleanup.assert_called_with([{"public_id": "private/new"}])

    @patch("apps.rentals.tenant_views.chat_image_url", return_value="https://res.cloudinary.com/fixture/private-signed")
    def test_image_access_scoped_and_private(self, signed_url):
        TenantIdentityImage.objects.create(tenant=self.tenant, side="front", public_id="private/id")
        url = reverse("tenant-identity-image", args=[self.tenant.pk, "front"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        signed_url.reset_mock()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("tenant-update", args=[self.tenant.pk]), {"full_name": "X"}).status_code, 404)
        self.client.force_login(self.tenant_user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(reverse("tenant-create")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        signed_url.assert_not_called()

    @patch("apps.rentals.tenant_views.configure_chat_cloudinary")
    @patch("apps.rentals.tenant_views.remove_chat_uploads")
    @patch("apps.rentals.tenant_views.cloudinary.uploader.upload", return_value={"public_id": "private/rollback", "format": "png"})
    @patch("apps.rentals.tenant_views.TenantIdentityImage.objects.create", side_effect=IntegrityError("DB failure"))
    def test_database_failure_rolls_back_tenant_and_cleans_cloud_image(self, create, upload, cleanup, configure):
        response = self.client.post(reverse("tenant-create"), {"full_name": "Rollback", "identity_front": photo()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tenant.objects.filter(full_name="Rollback").exists())
        self.assertEqual(cleanup.call_args.args[0][0]["public_id"], "private/rollback")

    def test_form_edit_renders_tabs_existing_image_and_date(self):
        from datetime import date
        self.tenant.date_of_birth = date(1998, 5, 20)
        self.tenant.save()
        TenantIdentityImage.objects.create(tenant=self.tenant, side="front", public_id="private/render")
        response = self.client.get(reverse("tenant-update", args=[self.tenant.pk]))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'value="1998-05-20"')
        self.assertContains(response, 'id="tenant-images"')
        self.assertNotContains(response, "private/render")
        self.assertContains(response, reverse("tenant-identity-image", args=[self.tenant.pk, "front"]))
