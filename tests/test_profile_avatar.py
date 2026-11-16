from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.rentals.models import Tenant


def avatar_file():
    buffer = BytesIO()
    Image.new("RGB", (80, 80), "#2863d7").save(buffer, format="PNG")
    return SimpleUploadedFile("avatar.png", buffer.getvalue(), content_type="image/png")


class ProfileAvatarTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        settings_override = override_settings(MEDIA_ROOT=self.media_dir.name, AVATAR_USE_CLOUDINARY=False)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.user = get_user_model().objects.create_user(username="avatar-admin", password="test", role="admin")
        self.client.force_login(self.user)

    def test_avatar_upload_appears_in_profile_and_both_header_locations(self):
        response = self.client.post(reverse("user-profile"), {
            "profile_action": "avatar", "avatar": avatar_file(),
        })
        self.assertRedirects(response, reverse("user-profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/"))
        self.assertTrue(self.user.avatar.storage.exists(self.user.avatar.name))
        profile = self.client.get(reverse("user-profile"))
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.content.decode().count(self.user.avatar.url), 3)

    def test_invalid_file_does_not_change_avatar(self):
        response = self.client.post(reverse("user-profile"), {
            "profile_action": "avatar",
            "avatar": SimpleUploadedFile("fake.png", b"not an image", content_type="image/png"),
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertContains(response, "Vui lòng kiểm tra")

    def test_tenant_can_upload_avatar_without_changing_profile_fields(self):
        tenant_user = get_user_model().objects.create_user(username="avatar-tenant", password="test", role="tenant")
        tenant = Tenant.objects.create(
            user=tenant_user, full_name="Nguyễn Văn A", phone="0900000000", identity_number="avatar-test-001"
        )
        self.client.force_login(tenant_user)
        response = self.client.post(reverse("user-profile"), {
            "profile_action": "avatar", "avatar": avatar_file(),
        })
        self.assertRedirects(response, reverse("user-profile"))
        tenant_user.refresh_from_db()
        tenant.refresh_from_db()
        self.assertTrue(tenant_user.avatar)
        self.assertEqual(tenant.full_name, "Nguyễn Văn A")

    @override_settings(AVATAR_USE_CLOUDINARY=True)
    @patch.dict("os.environ", {"CLOUDINARY_URL": "cloudinary://test-key:test-secret@test-cloud", "CLOUDINARY_CLOUD_NAME": "", "CLOUDINARY_API_KEY": "", "CLOUDINARY_API_SECRET": ""})
    @patch("apps.accounts.avatar_storage.cloudinary.uploader.upload")
    def test_cloudinary_upload_stores_https_url_without_writing_local_file(self, upload):
        url = "https://res.cloudinary.com/test-cloud/image/upload/v123/ql-phong-cho-thue/avatars/test.png"
        upload.return_value = {"secure_url": url}
        with patch("django.core.files.storage.filesystem.FileSystemStorage._save", side_effect=OSError("read-only")):
            response = self.client.post(reverse("user-profile"), {"profile_action": "avatar", "avatar": avatar_file()})
        self.assertRedirects(response, reverse("user-profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, url)
        self.assertEqual(self.user.avatar.url, url)
        self.assertEqual(upload.call_args.kwargs["cloud_name"], "test-cloud")
        self.assertContains(self.client.get(reverse("user-profile")), url, count=3)

    @override_settings(AVATAR_USE_CLOUDINARY=True)
    @patch.dict("os.environ", {"CLOUDINARY_URL": "cloudinary://test-key:test-secret@test-cloud", "CLOUDINARY_CLOUD_NAME": "", "CLOUDINARY_API_KEY": "", "CLOUDINARY_API_SECRET": ""})
    @patch("apps.accounts.avatar_storage.cloudinary.uploader.upload", side_effect=RuntimeError("provider unavailable"))
    def test_provider_failure_keeps_previous_avatar_and_returns_form(self, upload):
        previous = "https://res.cloudinary.com/test-cloud/image/upload/old.png"
        self.user.avatar = previous
        self.user.save(update_fields=["avatar"])
        response = self.client.post(reverse("user-profile"), {"profile_action": "avatar", "avatar": avatar_file()})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chưa tải được ảnh đại diện lên Cloudinary")
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, previous)
        self.assertContains(response, previous)

    def test_legacy_local_avatar_keeps_its_media_url(self):
        self.user.avatar = "avatars/legacy.png"
        self.assertEqual(self.user.avatar.url, "/media/avatars/legacy.png")
