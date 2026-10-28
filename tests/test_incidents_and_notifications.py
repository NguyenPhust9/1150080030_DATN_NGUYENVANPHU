from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, ContractMember, Incident, Notification, Room, Tenant

User = get_user_model()


class IncidentAndNotificationTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user(
            username="owner_in1", password="Password123!", role="owner", first_name="Chủ nhà 1"
        )
        self.owner2 = User.objects.create_user(
            username="owner_in2", password="Password123!", role="owner", first_name="Chủ nhà 2"
        )
        self.staff1 = User.objects.create_user(
            username="staff_in1",
            password="Password123!",
            role="staff",
            managed_owner=self.owner1,
            first_name="Nhân viên 1",
        )
        self.staff2 = User.objects.create_user(
            username="staff_in2",
            password="Password123!",
            role="staff",
            managed_owner=self.owner2,
            first_name="Nhân viên 2",
        )
        self.tenant_user1 = User.objects.create_user(
            username="tenant_in1", password="Password123!", role="tenant", first_name="Khách 1"
        )
        self.tenant_user1_mate = User.objects.create_user(
            username="tenant_in1_mate", password="Password123!", role="tenant", first_name="Bạn phòng 1"
        )
        self.tenant_user1_room2 = User.objects.create_user(
            username="tenant_in1_r2", password="Password123!", role="tenant", first_name="Khách phòng 2"
        )
        self.tenant_user2 = User.objects.create_user(
            username="tenant_in2", password="Password123!", role="tenant", first_name="Khách 2"
        )

        self.b1 = Building.objects.create(name="Tòa nhà A", address="100 Điện Biên Phủ", owner=self.owner1)
        self.b1.staff.add(self.staff1)
        self.b2 = Building.objects.create(name="Tòa nhà B", address="200 Hai Bà Trưng", owner=self.owner2)
        self.b2.staff.add(self.staff2)

        self.room101 = Room.objects.create(
            building=self.b1, number="101", floor=1, monthly_rent=Decimal("3000000"), status=Room.Status.OCCUPIED
        )
        self.room102 = Room.objects.create(
            building=self.b1, number="102", floor=1, monthly_rent=Decimal("3200000"), status=Room.Status.OCCUPIED
        )
        self.room201 = Room.objects.create(
            building=self.b2, number="201", floor=2, monthly_rent=Decimal("4000000"), status=Room.Status.OCCUPIED
        )

        self.tenant1 = Tenant.objects.create(
            owner=self.owner1, user=self.tenant_user1, full_name="Nguyễn Khách 1", phone="0901111001", identity_number="ID-IN-101"
        )
        self.tenant1_mate = Tenant.objects.create(
            owner=self.owner1, user=self.tenant_user1_mate, full_name="Trần Bạn Cùng Phòng", phone="0901111002", identity_number="ID-IN-102"
        )
        self.tenant1_r2 = Tenant.objects.create(
            owner=self.owner1, user=self.tenant_user1_room2, full_name="Lê Khách Phòng 102", phone="0901111003", identity_number="ID-IN-103"
        )
        self.tenant2 = Tenant.objects.create(
            owner=self.owner2, user=self.tenant_user2, full_name="Phạm Khách Tòa B", phone="0902222001", identity_number="ID-IN-201"
        )

        today = date.today()
        self.contract101 = Contract.objects.create(
            code="HD-IN-101",
            room=self.room101,
            representative=self.tenant1,
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=15),  # Expiring within 30 days!
            monthly_rent=Decimal("3000000"),
            status=Contract.Status.ACTIVE,
        )
        ContractMember.objects.create(
            contract=self.contract101, tenant=self.tenant1_mate, joined_date=today - timedelta(days=60)
        )
        self.contract102 = Contract.objects.create(
            code="HD-IN-102",
            room=self.room102,
            representative=self.tenant1_r2,
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=180),
            monthly_rent=Decimal("3200000"),
            status=Contract.Status.ACTIVE,
        )
        self.contract201 = Contract.objects.create(
            code="HD-IN-201",
            room=self.room201,
            representative=self.tenant2,
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=10),
            monthly_rent=Decimal("4000000"),
            status=Contract.Status.ACTIVE,
        )

        self.incident1 = Incident.objects.create(
            room=self.room101,
            reported_by=self.tenant1,
            title="Hỏng vòi nước bồn rửa",
            description="Nước rò rỉ liên tục",
            priority=Incident.Priority.MEDIUM,
            status=Incident.Status.OPEN,
        )
        self.incident2 = Incident.objects.create(
            room=self.room201,
            reported_by=self.tenant2,
            title="Mất điện hành lang",
            description="Đèn hành lang không sáng",
            priority=Incident.Priority.HIGH,
            status=Incident.Status.OPEN,
        )

    def test_incident_management_workflow_staff_scope_and_auto_notification(self):
        self.client.force_login(self.owner1)

        # Detail view accessible for owner1's incident, 404 for owner2's incident
        res = self.client.get(reverse("incident-detail", args=[self.incident1.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Hỏng vòi nước bồn rửa")
        self.assertEqual(self.client.get(reverse("incident-detail", args=[self.incident2.id])).status_code, 404)

        # Cannot assign staff2 (belongs to owner2) to incident1
        res = self.client.post(
            reverse("incident-detail", args=[self.incident1.id]),
            {
                "priority": Incident.Priority.HIGH,
                "status": Incident.Status.IN_PROGRESS,
                "assigned_to": str(self.staff2.id),
                "resolution_notes": "Thử gán sai nhân viên",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.incident1.refresh_from_db()
        self.assertEqual(self.incident1.status, Incident.Status.OPEN)

        # Assign staff1 and transition OPEN -> IN_PROGRESS
        res = self.client.post(
            reverse("incident-detail", args=[self.incident1.id]),
            {
                "priority": Incident.Priority.URGENT,
                "status": Incident.Status.IN_PROGRESS,
                "assigned_to": str(self.staff1.id),
                "resolution_notes": "Đã cử thợ điện nước xuống kiểm tra",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.incident1.refresh_from_db()
        self.assertEqual(self.incident1.priority, Incident.Priority.URGENT)
        self.assertEqual(self.incident1.status, Incident.Status.IN_PROGRESS)
        self.assertEqual(self.incident1.assigned_to, self.staff1)
        self.assertEqual(self.incident1.resolution_notes, "Đã cử thợ điện nước xuống kiểm tra")
        self.assertIsNone(self.incident1.resolved_at)

        # Notification created for tenant1 on status transition
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.tenant_user1,
                title__icontains="Hỏng vòi nước bồn rửa",
            ).exists()
        )

        # Transition IN_PROGRESS -> RESOLVED sets resolved_at timestamp
        res = self.client.post(
            reverse("incident-detail", args=[self.incident1.id]),
            {
                "priority": Incident.Priority.URGENT,
                "status": Incident.Status.RESOLVED,
                "assigned_to": str(self.staff1.id),
                "resolution_notes": "Đã thay van khóa mới hoàn tất",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.incident1.refresh_from_db()
        self.assertEqual(self.incident1.status, Incident.Status.RESOLVED)
        self.assertIsNotNone(self.incident1.resolved_at)

        # Transition RESOLVED -> CLOSED keeps resolved_at
        res = self.client.post(
            reverse("incident-detail", args=[self.incident1.id]),
            {
                "priority": Incident.Priority.URGENT,
                "status": Incident.Status.CLOSED,
                "assigned_to": str(self.staff1.id),
                "resolution_notes": "Khách thuê đã nghiệm thu và đóng yêu cầu",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.incident1.refresh_from_db()
        self.assertEqual(self.incident1.status, Incident.Status.CLOSED)
        self.assertIsNotNone(self.incident1.resolved_at)

    def test_targeted_notifications_expiring_contracts_and_tenant_mark_read(self):
        self.client.force_login(self.owner1)

        # 1. Send notification to a single tenant
        res = self.client.post(
            reverse("notification-create"),
            {
                "target_type": "tenant",
                "tenant": str(self.tenant1.id),
                "room": "",
                "building": "",
                "title": "Nhắc lịch kiểm tra định kỳ",
                "content": "Chiều mai kỹ thuật kiểm tra bình nóng lạnh.",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertEqual(
            Notification.objects.filter(recipient=self.tenant_user1, title="Nhắc lịch kiểm tra định kỳ").count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(recipient=self.tenant_user1_mate, title="Nhắc lịch kiểm tra định kỳ").count(),
            0,
        )

        # 2. Send notification to all tenants of a room (room101 has tenant1 + tenant1_mate = 2 recipients)
        res = self.client.post(
            reverse("notification-create"),
            {
                "target_type": "room",
                "tenant": "",
                "room": str(self.room101.id),
                "building": "",
                "title": "Thông báo vệ sinh phòng 101",
                "content": "Phòng 101 kiểm tra đồng hồ nước.",
            },
        )
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(recipient=self.tenant_user1, title="Thông báo vệ sinh phòng 101").exists()
        )
        self.assertTrue(
            Notification.objects.filter(recipient=self.tenant_user1_mate, title="Thông báo vệ sinh phòng 101").exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.tenant_user1_room2, title="Thông báo vệ sinh phòng 101").exists()
        )

        # 3. Send notification to all tenants of a building (b1 has tenant1, tenant1_mate, tenant1_r2 = 3 recipients)
        res = self.client.post(
            reverse("notification-create"),
            {
                "target_type": "building",
                "tenant": "",
                "room": "",
                "building": str(self.b1.id),
                "title": "Thông báo bảo trì thang máy Tòa A",
                "content": "Tạm ngưng thang máy từ 9h đến 11h.",
            },
        )
        self.assertEqual(res.status_code, 302)
        for u in (self.tenant_user1, self.tenant_user1_mate, self.tenant_user1_room2):
            self.assertTrue(
                Notification.objects.filter(recipient=u, title="Thông báo bảo trì thang máy Tòa A").exists()
            )
        self.assertFalse(
            Notification.objects.filter(recipient=self.tenant_user2, title="Thông báo bảo trì thang máy Tòa A").exists()
        )

        # 4. Trigger expiring contracts notification (contract101 expires in 15 days; contract201 belongs to owner2)
        res = self.client.post(reverse("notification-expiring-contracts"))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(
            Notification.objects.filter(recipient=self.tenant_user1, title__icontains="HD-IN-101 sắp hết hạn").exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.tenant_user2, title__icontains="HD-IN-201 sắp hết hạn").exists()
        )

        # 5. Tenant views notifications, sees unread count in bell, and marks individual notification as read
        self.client.force_login(self.tenant_user1)
        res = self.client.get(reverse("tenant-notifications"))
        self.assertEqual(res.status_code, 200)
        # 4 unread notifications for tenant_user1
        self.assertEqual(res.context["unread_count"], 4)
        self.assertContains(res, reverse("tenant-notifications"))

        first_notif = self.tenant_user1.notifications.filter(is_read=False).first()
        res = self.client.post(reverse("tenant-notification-mark-read", args=[first_notif.id]))
        self.assertEqual(res.status_code, 302)
        first_notif.refresh_from_db()
        self.assertTrue(first_notif.is_read)
        self.assertIsNotNone(first_notif.read_at)
        self.assertEqual(self.tenant_user1.notifications.filter(is_read=False).count(), 3)
