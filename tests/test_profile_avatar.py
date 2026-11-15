from io import BytesIO
from tempfile import TemporaryDirectory

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
        settings_override = override_settings(MEDIA_ROOT=self.media_dir.name)
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
