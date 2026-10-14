from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Tenant

User = get_user_model()


class ProfileAndPasswordTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_user",
            password="OldPassword123!",
            role="staff",
            first_name="Văn",
            last_name="Nguyễn",
            email="staff@example.com",
            phone="0911223344",
        )
        self.tenant_user = User.objects.create_user(
            username="tenant_user",
            password="TenantPassword123!",
            role="tenant",
            email="tenant@example.com",
            phone="0988776655",
        )
        self.tenant_profile = Tenant.objects.create(
            user=self.tenant_user,
            full_name="Trần Thị B",
            phone="0988776655",
            email="tenant@example.com",
            identity_number="012345678901",
            permanent_address="Hà Nội",
        )

    def test_anonymous_redirected_from_profile_and_password_change(self):
        res_profile = self.client.get(reverse("user-profile"))
        self.assertEqual(res_profile.status_code, 302)
        self.assertIn("/dang-nhap/", res_profile.url)

        res_pwd = self.client.get(reverse("password-change"))
        self.assertEqual(res_pwd.status_code, 302)
        self.assertIn("/dang-nhap/", res_pwd.url)

    def test_staff_view_and_update_profile(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("user-profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hồ sơ cá nhân")
        self.assertContains(response, "Cập nhật thông tin tài khoản")

        post_data = {
            "first_name": "Minh",
            "last_name": "Lê",
            "email": "leminh@example.com",
            "phone": "0933445566",
        }
        post_res = self.client.post(reverse("user-profile"), post_data)
        self.assertRedirects(post_res, reverse("user-profile"))

        self.staff_user.refresh_from_db()
        self.assertEqual(self.staff_user.first_name, "Minh")
        self.assertEqual(self.staff_user.last_name, "Lê")
        self.assertEqual(self.staff_user.email, "leminh@example.com")
        self.assertEqual(self.staff_user.phone, "0933445566")

    def test_tenant_view_and_update_profile_syncs_user(self):
        self.client.force_login(self.tenant_user)
        response = self.client.get(reverse("user-profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thông tin khách thuê")
        self.assertContains(response, "012345678901")

        post_data = {
            "full_name": "Trần Thị Mai",
            "phone": "0977112233",
            "email": "mai.tran@example.com",
            "gender": "female",
            "date_of_birth": "1998-05-20",
            "identity_number": "012345678901",
            "permanent_address": "Đà Nẵng",
            "emergency_contact": "Bố - 0912345678",
        }
        post_res = self.client.post(reverse("user-profile"), post_data)
        self.assertRedirects(post_res, reverse("user-profile"))

        self.tenant_profile.refresh_from_db()
        self.assertEqual(self.tenant_profile.full_name, "Trần Thị Mai")
        self.assertEqual(self.tenant_profile.phone, "0977112233")
        self.assertEqual(self.tenant_profile.email, "mai.tran@example.com")
        self.assertEqual(self.tenant_profile.permanent_address, "Đà Nẵng")

        # Đồng bộ sang user
        self.tenant_user.refresh_from_db()
        self.assertEqual(self.tenant_user.email, "mai.tran@example.com")
        self.assertEqual(self.tenant_user.phone, "0977112233")
        self.assertEqual(self.tenant_user.first_name, "Mai")
        self.assertEqual(self.tenant_user.last_name, "Trần Thị")

    def test_password_change_success_and_login_maintained(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("password-change"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đổi mật khẩu")

        post_data = {
            "old_password": "OldPassword123!",
            "new_password1": "NewSecretPassword456!",
            "new_password2": "NewSecretPassword456!",
        }
        res_post = self.client.post(reverse("password-change"), post_data)
        self.assertRedirects(res_post, reverse("password-change"))

        # Kiểm tra mật khẩu mới hoạt động
        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.check_password("NewSecretPassword456!"))

    def test_password_change_with_wrong_old_password_fails(self):
        self.client.force_login(self.staff_user)
        post_data = {
            "old_password": "WrongPassword999!",
            "new_password1": "NewSecretPassword456!",
            "new_password2": "NewSecretPassword456!",
        }
        res_post = self.client.post(reverse("password-change"), post_data)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("old_password", res_post.context["form"].errors)
