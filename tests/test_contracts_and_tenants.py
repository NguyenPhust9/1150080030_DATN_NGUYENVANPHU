from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, ContractMember, Room, Tenant

User = get_user_model()


class TenantAndContractLifecycleTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user(
            username="owner_c1", password="Password123!", role="owner", first_name="Chủ nhà 1"
        )
        self.owner2 = User.objects.create_user(
            username="owner_c2", password="Password123!", role="owner", first_name="Chủ nhà 2"
        )
        self.tenant_user1 = User.objects.create_user(
            username="tenant_u1", password="Password123!", role="tenant", first_name="Tài khoản Khách 1"
        )
        self.tenant_user2 = User.objects.create_user(
            username="tenant_u2", password="Password123!", role="tenant", first_name="Tài khoản Khách 2"
        )

        self.b1 = Building.objects.create(name="Tòa A", address="10 Lê Lợi", owner=self.owner1)
        self.b2 = Building.objects.create(name="Tòa B", address="20 Nguyễn Huệ", owner=self.owner2)

        self.room1 = Room.objects.create(
            building=self.b1,
            number="101",
            floor=1,
            monthly_rent=Decimal("3500000"),
            deposit_amount=Decimal("3500000"),
            max_occupants=3,
        )
        self.room2 = Room.objects.create(
            building=self.b2,
            number="201",
            floor=2,
            monthly_rent=Decimal("4000000"),
            deposit_amount=Decimal("4000000"),
            max_occupants=3,
        )

        self.tenant1 = Tenant.objects.create(
            owner=self.owner1,
            full_name="Nguyễn Văn A",
            phone="0901111222",
            email="nva@example.com",
            identity_number="079000111222",
        )
        self.tenant1_mate = Tenant.objects.create(
            owner=self.owner1,
            full_name="Lê Thị C",
            phone="0901111333",
            identity_number="079000111333",
        )
        self.tenant2 = Tenant.objects.create(
            owner=self.owner2,
            full_name="Trần Văn B",
            phone="0902222333",
            identity_number="079000222333",
        )

        self.draft_contract = Contract.objects.create(
            code="HD-DRAFT-101",
            room=self.room1,
            representative=self.tenant1,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            monthly_rent=Decimal("3500000"),
            deposit_amount=Decimal("3500000"),
            billing_day=1,
            due_day=5,
            status=Contract.Status.DRAFT,
        )

    def test_tenant_detail_edit_soft_deactivate_and_link_user(self):
        self.client.force_login(self.owner1)

        # Detail view displays personal info
        res = self.client.get(reverse("tenant-detail", args=[self.tenant1.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Nguyễn Văn A")
        self.assertContains(res, "079000111222")
        self.assertContains(res, "HD-DRAFT-101")

        # Edit tenant info
        res = self.client.post(
            reverse("tenant-update", args=[self.tenant1.id]),
            {
                "user": "",
                "full_name": "Nguyễn Văn A (Đã sửa)",
                "phone": "0909999888",
                "email": "nva_updated@example.com",
                "date_of_birth": "1995-05-15",
                "gender": "male",
                "identity_number": "079000111222",
                "identity_issued_date": "2020-01-10",
                "permanent_address": "Quận 1, TP.HCM",
                "emergency_contact": "0911222333",
                "is_active": "on",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.tenant1.refresh_from_db()
        self.assertEqual(self.tenant1.full_name, "Nguyễn Văn A (Đã sửa)")
        self.assertEqual(self.tenant1.phone, "0909999888")

        # Link tenant profile to user account
        res = self.client.post(
            reverse("tenant-link-user", args=[self.tenant1.id]),
            {"user": str(self.tenant_user1.id)},
        )
        self.assertEqual(res.status_code, 302)
        self.tenant1.refresh_from_db()
        self.assertEqual(self.tenant1.user, self.tenant_user1)

        # Soft deactivate tenant instead of hard delete
        res = self.client.post(reverse("tenant-toggle-active", args=[self.tenant1.id]))
        self.assertEqual(res.status_code, 302)
        self.tenant1.refresh_from_db()
        self.assertFalse(self.tenant1.is_active)
        self.assertTrue(Tenant.objects.filter(pk=self.tenant1.id).exists())

        # Reactivate tenant
        res = self.client.post(reverse("tenant-toggle-active", args=[self.tenant1.id]))
        self.assertEqual(res.status_code, 302)
        self.tenant1.refresh_from_db()
        self.assertTrue(self.tenant1.is_active)

        # Cross-owner access blocked
        self.assertEqual(self.client.get(reverse("tenant-detail", args=[self.tenant2.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("tenant-toggle-active", args=[self.tenant2.id])).status_code, 404)

    def test_contract_draft_edit_and_block_edit_when_active_or_terminated(self):
        self.client.force_login(self.owner1)

        # Draft contract can be edited
        res = self.client.post(
            reverse("contract-update", args=[self.draft_contract.id]),
            {
                "code": "HD-DRAFT-101",
                "room": str(self.room1.id),
                "representative": str(self.tenant1.id),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
                "monthly_rent": "3700000",
                "deposit_amount": "3700000",
                "billing_day": "1",
                "due_day": "10",
                "notes": "Không nuôi thú cưng",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.draft_contract.refresh_from_db()
        self.assertEqual(self.draft_contract.monthly_rent, Decimal("3700000"))
        self.assertEqual(self.draft_contract.due_day, 10)

        # Activate contract
        res = self.client.post(reverse("contract-activate", args=[self.draft_contract.id]))
        self.assertEqual(res.status_code, 302)
        self.draft_contract.refresh_from_db()
        self.room1.refresh_from_db()
        self.assertEqual(self.draft_contract.status, Contract.Status.ACTIVE)
        self.assertEqual(self.room1.status, Room.Status.OCCUPIED)

        # Editing active contract is blocked
        res = self.client.post(
            reverse("contract-update", args=[self.draft_contract.id]),
            {
                "code": "HD-DRAFT-101-HACK",
                "room": str(self.room1.id),
                "representative": str(self.tenant1.id),
                "start_date": "2026-01-01",
                "end_date": "2026-06-30",
                "monthly_rent": "9999999",
                "deposit_amount": "3700000",
                "billing_day": "1",
                "due_day": "10",
                "notes": "Sửa trái phép",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.draft_contract.refresh_from_db()
        self.assertEqual(self.draft_contract.code, "HD-DRAFT-101")
        self.assertEqual(self.draft_contract.monthly_rent, Decimal("3700000"))

    def test_contract_overlap_check_renew_terminate_and_cancel(self):
        self.client.force_login(self.owner1)

        # Activate first contract (2026-01-01 -> 2026-06-30)
        self.client.post(reverse("contract-activate", args=[self.draft_contract.id]))
        self.draft_contract.refresh_from_db()
        self.assertEqual(self.draft_contract.status, Contract.Status.ACTIVE)

        # Create overlapping draft contract on same room (2026-05-01 -> 2026-10-31)
        overlapping = Contract.objects.create(
            code="HD-OVERLAP-101",
            room=self.room1,
            representative=self.tenant1_mate,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 10, 31),
            monthly_rent=Decimal("3500000"),
            deposit_amount=Decimal("3500000"),
            billing_day=1,
            due_day=5,
            status=Contract.Status.DRAFT,
        )
        res = self.client.post(reverse("contract-activate", args=[overlapping.id]))
        self.assertEqual(res.status_code, 302)
        overlapping.refresh_from_db()
        self.assertEqual(overlapping.status, Contract.Status.DRAFT)

        # Cancel the overlapping draft contract
        res = self.client.post(reverse("contract-cancel", args=[overlapping.id]))
        self.assertEqual(res.status_code, 302)
        overlapping.refresh_from_db()
        self.assertEqual(overlapping.status, Contract.Status.CANCELLED)
        # Room should still be OCCUPIED because draft_contract is still ACTIVE
        self.room1.refresh_from_db()
        self.assertEqual(self.room1.status, Room.Status.OCCUPIED)

        # Renew active contract to 2026-12-31 with new rent
        res = self.client.post(
            reverse("contract-renew", args=[self.draft_contract.id]),
            {"new_end_date": "2026-12-31", "new_monthly_rent": "3800000", "notes": "Gia hạn 6 tháng"},
        )
        self.assertEqual(res.status_code, 302)
        self.draft_contract.refresh_from_db()
        self.assertEqual(self.draft_contract.end_date, date(2026, 12, 31))
        self.assertEqual(self.draft_contract.monthly_rent, Decimal("3800000"))

        # Create a non-overlapping future contract (2027-01-01 -> 2027-06-30) and activate it
        future_contract = Contract.objects.create(
            code="HD-FUTURE-101",
            room=self.room1,
            representative=self.tenant1_mate,
            start_date=date(2027, 1, 1),
            end_date=date(2027, 6, 30),
            monthly_rent=Decimal("4000000"),
            deposit_amount=Decimal("4000000"),
            billing_day=1,
            due_day=5,
            status=Contract.Status.DRAFT,
        )
        self.client.post(reverse("contract-activate", args=[future_contract.id]))
        future_contract.refresh_from_db()
        self.assertEqual(future_contract.status, Contract.Status.ACTIVE)

        # Terminate first contract: since future_contract is still ACTIVE, room stays OCCUPIED
        self.client.post(reverse("contract-terminate", args=[self.draft_contract.id]))
        self.draft_contract.refresh_from_db()
        self.room1.refresh_from_db()
        self.assertEqual(self.draft_contract.status, Contract.Status.TERMINATED)
        self.assertEqual(self.room1.status, Room.Status.OCCUPIED)

        # Terminate second contract: now no active contracts remain, room becomes AVAILABLE
        self.client.post(reverse("contract-terminate", args=[future_contract.id]))
        future_contract.refresh_from_db()
        self.room1.refresh_from_db()
        self.assertEqual(future_contract.status, Contract.Status.TERMINATED)
        self.assertEqual(self.room1.status, Room.Status.AVAILABLE)

    def test_contract_members_management(self):
        self.client.force_login(self.owner1)

        # Add roommate
        res = self.client.post(
            reverse("contract-member-add", args=[self.draft_contract.id]),
            {"tenant": str(self.tenant1_mate.id), "joined_date": "2026-01-05", "left_date": ""},
        )
        self.assertEqual(res.status_code, 302)
        member = ContractMember.objects.filter(
            contract=self.draft_contract, tenant=self.tenant1_mate
        ).first()
        self.assertIsNotNone(member)
        self.assertEqual(member.joined_date, date(2026, 1, 5))

        # Remove roommate
        res = self.client.post(
            reverse("contract-member-remove", args=[self.draft_contract.id, member.id])
        )
        self.assertEqual(res.status_code, 302)
        self.assertFalse(ContractMember.objects.filter(pk=member.id).exists())
