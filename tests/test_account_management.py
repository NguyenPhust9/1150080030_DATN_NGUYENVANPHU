from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import AccountAuditLog, LoginHistory
from apps.rentals.models import Building, Tenant
from apps.rentals.permissions import PERMISSION_MATRIX_DEFINITION, get_permission_matrix

User = get_user_model()


class AccountManagementTestSuite(TestCase):
    def setUp(self):
        # Superuser & Admin
        self.superuser = User.objects.create_superuser(
            username="root_super",
            email="root@example.com",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )
        self.admin_user = User.objects.create_user(
            username="admin_main",
            email="admin@example.com",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )

        # Two Owners
        self.owner_a = User.objects.create_user(
            username="owner_a",
            email="ownera@example.com",
            password="StrongPass!2026",
            role=User.Role.OWNER,
            first_name="An",
            last_name="Nguyễn",
        )
        self.owner_b = User.objects.create_user(
            username="owner_b",
            email="ownerb@example.com",
            password="StrongPass!2026",
            role=User.Role.OWNER,
            first_name="Bình",
            last_name="Trần",
        )

        # Buildings for each Owner
        self.building_a = Building.objects.create(
            name="Khu nhà A",
            address="100 Đường A",
            owner=self.owner_a,
        )
        self.building_b = Building.objects.create(
            name="Khu nhà B",
            address="200 Đường B",
            owner=self.owner_b,
        )

        # Staff for Owner A and Owner B
        self.staff_a = User.objects.create_user(
            username="staff_a",
            email="staffa@example.com",
            password="StrongPass!2026",
            role=User.Role.STAFF,
            managed_owner=self.owner_a,
        )
        self.staff_a.assigned_buildings.add(self.building_a)

        self.staff_b = User.objects.create_user(
            username="staff_b",
            email="staffb@example.com",
            password="StrongPass!2026",
            role=User.Role.STAFF,
            managed_owner=self.owner_b,
        )
        self.staff_b.assigned_buildings.add(self.building_b)

        # Tenant profiles for Owner A and Owner B
        self.tenant_profile_a1 = Tenant.objects.create(
            owner=self.owner_a,
            full_name="Lê Minh Khách A1",
            phone="0901111111",
            email="khacha1@example.com",
            identity_number="001099000001",
        )
        self.tenant_profile_a2 = Tenant.objects.create(
            owner=self.owner_a,
            full_name="Phạm Thị Khách A2",
            phone="0901111112",
            email="khacha2@example.com",
            identity_number="001099000002",
        )
        self.tenant_profile_b1 = Tenant.objects.create(
            owner=self.owner_b,
            full_name="Hoàng Văn Khách B1",
            phone="0902222221",
            email="khachb1@example.com",
            identity_number="001099000003",
        )

        # Linked Tenant user for A1 and B1
        self.tenant_user_a1 = User.objects.create_user(
            username="tenant_a1",
            email="khacha1@example.com",
            password="StrongPass!2026",
            role=User.Role.TENANT,
        )
        self.tenant_profile_a1.user = self.tenant_user_a1
        self.tenant_profile_a1.save(update_fields=["user"])

        self.tenant_user_b1 = User.objects.create_user(
            username="tenant_b1",
            email="khachb1@example.com",
            password="StrongPass!2026",
            role=User.Role.TENANT,
        )
        self.tenant_profile_b1.user = self.tenant_user_b1
        self.tenant_profile_b1.save(update_fields=["user"])

    # ------------------------------------------------------------------
    # 1, 2, 3. Danh sách & Cô lập dữ liệu tài khoản theo vai trò
    # ------------------------------------------------------------------
    def test_admin_can_view_all_accounts(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("accounts"))
        self.assertEqual(resp.status_code, 200)
        usernames = {u.username for u in resp.context["objects"]}
        self.assertTrue(
            {"root_super", "admin_main", "owner_a", "owner_b", "staff_a", "staff_b", "tenant_a1", "tenant_b1"}.issubset(
                usernames
            )
        )

    def test_owner_only_sees_scoped_accounts_and_cannot_access_other_owner_accounts(self):
        self.client.force_login(self.owner_a)
        resp = self.client.get(reverse("accounts"))
        self.assertEqual(resp.status_code, 200)
        usernames = {u.username for u in resp.context["objects"]}
        self.assertEqual(usernames, {"owner_a", "staff_a", "tenant_a1"})
        self.assertNotIn("owner_b", usernames)
        self.assertNotIn("staff_b", usernames)
        self.assertNotIn("tenant_b1", usernames)
        self.assertNotIn("admin_main", usernames)

        # Direct UUID access to Owner B's staff or tenant must return 404
        self.assertEqual(
            self.client.get(reverse("account-detail", args=[self.staff_b.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("account-update", args=[self.tenant_user_b1.pk])).status_code,
            404,
        )

    def test_staff_and_tenant_cannot_access_account_management(self):
        for restricted_user in (self.staff_a, self.tenant_user_a1):
            self.client.force_login(restricted_user)
            self.assertEqual(self.client.get(reverse("accounts")).status_code, 403)
            self.assertEqual(self.client.get(reverse("account-create")).status_code, 403)
            self.assertEqual(self.client.get(reverse("account-detail", args=[self.staff_a.pk])).status_code, 403)
            self.assertEqual(self.client.get(reverse("account-update", args=[self.staff_a.pk])).status_code, 403)

    # ------------------------------------------------------------------
    # 4, 5, 6, 7. Tạo và chỉnh sửa tài khoản (owner, staff, tenant)
    # ------------------------------------------------------------------
    def test_admin_can_create_owner_staff_tenant_with_hashed_password(self):
        self.client.force_login(self.admin_user)
        raw_pw = "NewSafePass!999"

        # 1. Create Owner
        resp = self.client.post(
            reverse("account-create"),
            {
                "username": "  Owner_New  ",
                "last_name": "Đặng",
                "first_name": "Chủ",
                "email": "owner_new@example.com",
                "phone": "0912345678",
                "role": User.Role.OWNER,
                "password1": raw_pw,
                "password2": raw_pw,
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 302)
        new_owner = User.objects.get(username="Owner_New")
        self.assertEqual(new_owner.role, User.Role.OWNER)
        self.assertFalse(new_owner.is_superuser)
        self.assertTrue(new_owner.check_password(raw_pw))
        self.assertNotEqual(new_owner.password, raw_pw)

        # 2. Create Staff assigned to building_a
        resp_staff = self.client.post(
            reverse("account-create"),
            {
                "username": "staff_new",
                "last_name": "Vũ",
                "first_name": "Nhân Viên",
                "email": "staff_new@example.com",
                "phone": "0912345679",
                "role": User.Role.STAFF,
                "password1": raw_pw,
                "password2": raw_pw,
                "is_active": "on",
                "managed_owner": str(self.owner_a.pk),
                "assigned_buildings": [str(self.building_a.pk)],
            },
        )
        self.assertEqual(resp_staff.status_code, 302)
        new_staff = User.objects.get(username="staff_new")
        self.assertEqual(new_staff.managed_owner, self.owner_a)
        self.assertIn(self.building_a, new_staff.assigned_buildings.all())

        # 3. Create Tenant linked to tenant_profile_a2
        resp_tenant = self.client.post(
            reverse("account-create"),
            {
                "username": "tenant_a2_user",
                "last_name": "Phạm Thị",
                "first_name": "Khách A2 Mới",
                "email": "new_a2@example.com",
                "phone": "0988888888",
                "role": User.Role.TENANT,
                "password1": raw_pw,
                "password2": raw_pw,
                "is_active": "on",
                "linked_tenant": str(self.tenant_profile_a2.pk),
            },
        )
        self.assertEqual(resp_tenant.status_code, 302)
        new_tenant_user = User.objects.get(username="tenant_a2_user")
        self.tenant_profile_a2.refresh_from_db()
        self.assertEqual(self.tenant_profile_a2.user, new_tenant_user)
        self.assertEqual(self.tenant_profile_a2.email, "new_a2@example.com")
        self.assertEqual(self.tenant_profile_a2.phone, "0988888888")
        self.assertEqual(self.tenant_profile_a2.full_name, "Phạm Thị Khách A2 Mới")

        # Audit log should not contain password
        audit = AccountAuditLog.objects.filter(
            target_user=new_tenant_user, action=AccountAuditLog.Action.CREATE_USER
        ).first()
        self.assertIsNotNone(audit)
        self.assertNotIn(raw_pw, str(audit.changes))

    def test_owner_cannot_create_owner_or_admin_account(self):
        self.client.force_login(self.owner_a)
        for forbidden_role in (User.Role.OWNER, User.Role.ADMIN):
            resp = self.client.post(
                reverse("account-create"),
                {
                    "username": f"illegal_{forbidden_role}",
                    "role": forbidden_role,
                    "password1": "StrongPass!2026",
                    "password2": "StrongPass!2026",
                    "is_active": "on",
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(User.objects.filter(username=f"illegal_{forbidden_role}").exists())

    def test_create_staff_requires_owner_or_building_and_valid_scope(self):
        # Admin creating staff without owner AND without building -> form error
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse("account-create"),
            {
                "username": "orphan_staff",
                "role": User.Role.STAFF,
                "password1": "StrongPass!2026",
                "password2": "StrongPass!2026",
                "is_active": "on",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="orphan_staff").exists())

        # Admin assigning building_b (Owner B) to staff with managed_owner=Owner A -> form error
        resp_mismatch = self.client.post(
            reverse("account-create"),
            {
                "username": "mismatch_staff",
                "role": User.Role.STAFF,
                "password1": "StrongPass!2026",
                "password2": "StrongPass!2026",
                "managed_owner": str(self.owner_a.pk),
                "assigned_buildings": [str(self.building_b.pk)],
            },
        )
        self.assertEqual(resp_mismatch.status_code, 200)
        self.assertFalse(User.objects.filter(username="mismatch_staff").exists())

        # Owner A trying to assign Owner B's building to their staff -> rejected
        self.client.force_login(self.owner_a)
        resp_owner_cross = self.client.post(
            reverse("account-create"),
            {
                "username": "staff_cross_b",
                "role": User.Role.STAFF,
                "password1": "StrongPass!2026",
                "password2": "StrongPass!2026",
                "assigned_buildings": [str(self.building_b.pk)],
            },
        )
        self.assertEqual(resp_owner_cross.status_code, 200)
        self.assertFalse(User.objects.filter(username="staff_cross_b").exists())

    def test_tenant_linking_prevents_duplicate_or_out_of_scope_tenant(self):
        self.client.force_login(self.owner_a)
        # Try linking already-linked tenant_profile_a1
        resp_dup = self.client.post(
            reverse("account-create"),
            {
                "username": "dup_tenant_user",
                "role": User.Role.TENANT,
                "password1": "StrongPass!2026",
                "password2": "StrongPass!2026",
                "linked_tenant": str(self.tenant_profile_a1.pk),
            },
        )
        self.assertEqual(resp_dup.status_code, 200)
        self.assertFalse(User.objects.filter(username="dup_tenant_user").exists())

        # Try linking Owner B's unlinked tenant from Owner A's account
        unlinked_b2 = Tenant.objects.create(
            owner=self.owner_b,
            full_name="Khách B2 Chưa TK",
            phone="0902222229",
            identity_number="001099000099",
        )
        resp_cross = self.client.post(
            reverse("account-create"),
            {
                "username": "cross_tenant_user",
                "role": User.Role.TENANT,
                "password1": "StrongPass!2026",
                "password2": "StrongPass!2026",
                "linked_tenant": str(unlinked_b2.pk),
            },
        )
        self.assertEqual(resp_cross.status_code, 200)
        self.assertFalse(User.objects.filter(username="cross_tenant_user").exists())

    # ------------------------------------------------------------------
    # 8, 9, 10, 15, 17. Khóa và mở khóa tài khoản
    # ------------------------------------------------------------------
    def test_lock_and_unlock_account_flow_and_session_invalidation(self):
        # Log in staff_a in a separate client to create an active session
        staff_client = Client()
        logged_in = staff_client.login(username="staff_a", password="StrongPass!2026")
        self.assertTrue(logged_in)
        staff_session_key = staff_client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=staff_session_key).exists())

        # GET request to lock endpoint must be rejected (405)
        self.client.force_login(self.owner_a)
        get_resp = self.client.get(reverse("account-toggle-lock", args=[self.staff_a.pk]))
        self.assertEqual(get_resp.status_code, 405)

        # POST lock by Owner A
        lock_resp = self.client.post(
            reverse("account-toggle-lock", args=[self.staff_a.pk]),
            {"reason": "Tạm nghỉ phép"},
        )
        self.assertEqual(lock_resp.status_code, 302)
        self.staff_a.refresh_from_db()
        self.assertFalse(self.staff_a.is_active)
        self.assertEqual(self.staff_a.locked_by, self.owner_a)
        self.assertEqual(self.staff_a.lock_reason, "Tạm nghỉ phép")
        self.assertIsNotNone(self.staff_a.locked_at)

        # Active session of staff_a must be invalidated
        self.assertFalse(Session.objects.filter(session_key=staff_session_key).exists())

        # Locked account cannot log in
        relogin = staff_client.post(
            reverse("login"),
            {"username": "staff_a", "password": "StrongPass!2026"},
        )
        self.assertEqual(relogin.status_code, 200)
        self.assertFalse(relogin.wsgi_request.user.is_authenticated)

        # Unlock by Owner A
        unlock_resp = self.client.post(
            reverse("account-toggle-lock", args=[self.staff_a.pk]),
            {"reason": "Đi làm trở lại"},
        )
        self.assertEqual(unlock_resp.status_code, 302)
        self.staff_a.refresh_from_db()
        self.assertTrue(self.staff_a.is_active)
        self.assertIsNone(self.staff_a.locked_at)

        # Unlocked account can log in again
        self.assertTrue(staff_client.login(username="staff_a", password="StrongPass!2026"))

    def test_prevent_self_lock_superuser_lock_last_admin_lock_and_cross_scope_lock(self):
        # 1. Prevent locking self
        self.client.force_login(self.admin_user)
        resp_self = self.client.post(reverse("account-toggle-lock", args=[self.admin_user.pk]))
        self.assertEqual(resp_self.status_code, 403)
        self.admin_user.refresh_from_db()
        self.assertTrue(self.admin_user.is_active)

        # 2. Prevent locking superuser
        resp_super = self.client.post(reverse("account-toggle-lock", args=[self.superuser.pk]))
        self.assertEqual(resp_super.status_code, 403)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

        # 3. Prevent locking last active admin (when superuser is inactive)
        User.objects.filter(pk=self.superuser.pk).update(is_active=False)
        other_admin = User.objects.create_user(
            username="admin_two",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )
        # Locking admin_two while admin_main is active succeeds
        resp_lock_admin2 = self.client.post(reverse("account-toggle-lock", args=[other_admin.pk]))
        self.assertEqual(resp_lock_admin2.status_code, 302)
        other_admin.refresh_from_db()
        self.assertFalse(other_admin.is_active)

        # Now admin_main is the ONLY active admin; even if another actor or check is called, is_last_active_admin is True
        from apps.rentals.permissions import is_last_active_admin

        self.assertTrue(is_last_active_admin(self.admin_user))

        # 4. Prevent Owner A from locking Owner B, Admin, or Owner B's staff
        self.client.force_login(self.owner_a)
        self.assertIn(
            self.client.post(reverse("account-toggle-lock", args=[self.owner_b.pk])).status_code,
            (403, 404),
        )
        self.assertIn(
            self.client.post(reverse("account-toggle-lock", args=[self.staff_b.pk])).status_code,
            (403, 404),
        )
        self.staff_b.refresh_from_db()
        self.assertTrue(self.staff_b.is_active)

    # ------------------------------------------------------------------
    # 11. Đặt lại mật khẩu & buộc đổi mật khẩu (must_change_password)
    # ------------------------------------------------------------------
    def test_reset_password_validation_permissions_and_must_change_password_redirect(self):
        # Owner A cannot reset Owner B's password or Superuser's password
        self.client.force_login(self.owner_a)
        self.assertIn(
            self.client.post(
                reverse("account-reset-password", args=[self.owner_b.pk]),
                {"new_password1": "ResetStrong!123", "new_password2": "ResetStrong!123"},
            ).status_code,
            (403, 404),
        )
        # Owner A cannot reset even their own Owner password if rule says only Admin resets Owner password
        self.assertEqual(
            self.client.post(
                reverse("account-reset-password", args=[self.owner_a.pk]),
                {"new_password1": "ResetStrong!123", "new_password2": "ResetStrong!123"},
            ).status_code,
            403,
        )

        # Admin cannot reset Superuser password from this UI
        self.client.force_login(self.admin_user)
        self.assertEqual(
            self.client.post(
                reverse("account-reset-password", args=[self.superuser.pk]),
                {"new_password1": "ResetStrong!123", "new_password2": "ResetStrong!123"},
            ).status_code,
            403,
        )

        # Mismatched passwords on staff_a
        self.client.force_login(self.owner_a)
        resp_mismatch = self.client.post(
            reverse("account-reset-password", args=[self.staff_a.pk]),
            {
                "new_password1": "ResetStrong!123",
                "new_password2": "Different!123",
                "must_change_password": "on",
            },
        )
        self.assertEqual(resp_mismatch.status_code, 200)
        self.staff_a.refresh_from_db()
        self.assertTrue(self.staff_a.check_password("StrongPass!2026"))

        # Weak password (e.g. "12345" or "12345678") rejected by password validators
        resp_weak = self.client.post(
            reverse("account-reset-password", args=[self.staff_a.pk]),
            {
                "new_password1": "12345",
                "new_password2": "12345",
                "must_change_password": "on",
            },
        )
        self.assertEqual(resp_weak.status_code, 200)
        self.staff_a.refresh_from_db()
        self.assertTrue(self.staff_a.check_password("StrongPass!2026"))

        # Valid password reset by Owner A on staff_a with must_change_password=True
        new_pw = "BrandNewPass!2026"
        resp_ok = self.client.post(
            reverse("account-reset-password", args=[self.staff_a.pk]),
            {
                "new_password1": new_pw,
                "new_password2": new_pw,
                "must_change_password": "on",
                "reason": "Cấp lại mật khẩu cho nhân viên",
            },
        )
        self.assertEqual(resp_ok.status_code, 302)
        self.staff_a.refresh_from_db()
        self.assertTrue(self.staff_a.check_password(new_pw))
        self.assertTrue(self.staff_a.must_change_password)
        self.assertIsNotNone(self.staff_a.password_changed_at)

        # Verify audit log does NOT store plaintext password
        reset_audit = AccountAuditLog.objects.filter(
            target_user=self.staff_a, action=AccountAuditLog.Action.RESET_PASSWORD
        ).first()
        self.assertIsNotNone(reset_audit)
        self.assertNotIn(new_pw, str(reset_audit.changes))
        self.assertNotIn(new_pw, reset_audit.reason)

        # When staff_a logs in, middleware forces redirect to password-change page
        staff_client = Client()
        self.assertTrue(staff_client.login(username="staff_a", password=new_pw))
        dash_resp = staff_client.get(reverse("dashboard"))
        self.assertEqual(dash_resp.status_code, 302)
        self.assertEqual(dash_resp.url, reverse("password-change"))

        # After changing password on password-change page, must_change_password becomes False
        change_resp = staff_client.post(
            reverse("password-change"),
            {
                "old_password": new_pw,
                "new_password1": "UpdatedSelfPass!888",
                "new_password2": "UpdatedSelfPass!888",
            },
        )
        self.assertEqual(change_resp.status_code, 302)
        self.staff_a.refresh_from_db()
        self.assertFalse(self.staff_a.must_change_password)
        self.assertTrue(self.staff_a.check_password("UpdatedSelfPass!888"))

    # ------------------------------------------------------------------
    # 12, 13. Lịch sử đăng nhập (thành công, thất bại, đăng xuất, khóa, không lưu mật khẩu)
    # ------------------------------------------------------------------
    def test_login_history_records_success_failure_logout_and_locked_without_passwords(self):
        anon_client = Client()
        secret_attempt = "MySecretWrongPass!777"

        # 1. Failed login (wrong password)
        anon_client.post(
            reverse("login"),
            {"username": "staff_a", "password": secret_attempt},
            HTTP_USER_AGENT="TestBrowser/1.0",
            REMOTE_ADDR="203.0.113.15",
        )
        failed_log = LoginHistory.objects.filter(
            username_attempted="staff_a", event_type=LoginHistory.EventType.LOGIN_FAILED
        ).first()
        self.assertIsNotNone(failed_log)
        self.assertEqual(failed_log.user, self.staff_a)
        self.assertEqual(failed_log.ip_address, "203.0.113.15")
        self.assertIn("TestBrowser/1.0", failed_log.user_agent)

        # 2. Successful login
        anon_client.post(
            reverse("login"),
            {"username": "staff_a", "password": "StrongPass!2026"},
            HTTP_USER_AGENT="TestBrowser/1.0",
            REMOTE_ADDR="203.0.113.15",
        )
        success_log = LoginHistory.objects.filter(
            user=self.staff_a, event_type=LoginHistory.EventType.LOGIN_SUCCESS
        ).first()
        self.assertIsNotNone(success_log)

        # 3. Logout
        anon_client.post(reverse("logout"))
        logout_log = LoginHistory.objects.filter(
            user=self.staff_a, event_type=LoginHistory.EventType.LOGOUT
        ).first()
        self.assertIsNotNone(logout_log)

        # 4. Locked account login attempt
        self.staff_a.is_active = False
        self.staff_a.save(update_fields=["is_active"])
        anon_client.post(
            reverse("login"),
            {"username": "staff_a", "password": "StrongPass!2026"},
        )
        locked_log = (
            LoginHistory.objects.filter(
                user=self.staff_a,
                event_type=LoginHistory.EventType.LOGIN_FAILED,
            )
            .order_by("-occurred_at")
            .first()
        )
        self.assertIsNotNone(locked_log)
        self.assertIn("khóa", locked_log.failure_reason.lower())

        # 5. Ensure plaintext passwords never appear in LoginHistory
        for entry in LoginHistory.objects.all():
            serialized = f"{entry.username_attempted} {entry.failure_reason} {entry.user_agent} {entry.session_key}"
            self.assertNotIn(secret_attempt, serialized)
            self.assertNotIn("StrongPass!2026", serialized)

        # 6. Scope check on login history page
        self.client.force_login(self.owner_b)
        resp_hist_b = self.client.get(reverse("login-history"))
        self.assertEqual(resp_hist_b.status_code, 200)
        for item in resp_hist_b.context["objects"]:
            self.assertNotEqual(item.user, self.staff_a)

    # ------------------------------------------------------------------
    # 14. Ma trận quyền đồng bộ từ cấu hình phân quyền tập trung
    # ------------------------------------------------------------------
    def test_permission_matrix_renders_from_centralized_definition(self):
        self.client.force_login(self.owner_a)
        resp = self.client.get(reverse("permission-matrix"))
        self.assertEqual(resp.status_code, 200)
        matrix_rows = resp.context["matrix_rows"]
        expected_matrix = get_permission_matrix()
        self.assertEqual(len(matrix_rows), len(PERMISSION_MATRIX_DEFINITION))
        self.assertEqual(matrix_rows, expected_matrix)

        for row in matrix_rows:
            self.assertContains(resp, row["name"])
            for cell in row["role_cells"]:
                self.assertContains(resp, cell["scope"])

        # Tenant cannot access permission matrix management page
        self.client.force_login(self.tenant_user_a1)
        self.assertEqual(self.client.get(reverse("permission-matrix")).status_code, 403)

