from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Contract, Room, RoomMedia, Tenant


class RoomWalkthroughTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="tour-owner", role="owner")
        cls.other_owner = User.objects.create_user(username="tour-other-owner", role="owner")
        cls.admin = User.objects.create_user(username="tour-admin", role="admin")
        cls.staff = User.objects.create_user(username="tour-staff", role="staff")
        cls.unassigned_staff = User.objects.create_user(username="tour-unassigned", role="staff")
        cls.tenant_user = User.objects.create_user(username="tour-tenant", role="tenant")
        cls.unlinked_tenant = User.objects.create_user(username="tour-unlinked", role="tenant")
        cls.building = Building.objects.create(name="Tòa nhà An Tâm", address="Test", owner=cls.owner)
        cls.building.staff.add(cls.staff)
        cls.room = Room.objects.create(building=cls.building, number="A101", monthly_rent=3000000)
        cls.adjacent_room = Room.objects.create(building=cls.building, number="A102", monthly_rent=3500000)
        cls.other_room = Room.objects.create(building=cls.building, number="A103", monthly_rent=3000000)
        other_building = Building.objects.create(name="Other", address="Test", owner=cls.other_owner)
        cls.private_room = Room.objects.create(building=other_building, number="A101", monthly_rent=3000000)
        cls.image = RoomMedia.objects.create(
            room=cls.room, media_type="image", public_id="tour-image",
            url="https://res.cloudinary.com/example/image/upload/tour.jpg",
        )
        cls.video = RoomMedia.objects.create(
            room=cls.room, media_type="video", public_id="tour-video",
            url="https://res.cloudinary.com/example/video/upload/tour.mp4",
        )
        cls.adjacent_image = RoomMedia.objects.create(
            room=cls.adjacent_room, media_type="image", public_id="adjacent-image",
            url="https://res.cloudinary.com/example/image/upload/a102.jpg",
        )
        cls.adjacent_video = RoomMedia.objects.create(
            room=cls.adjacent_room, media_type="video", public_id="adjacent-video",
            url="https://res.cloudinary.com/example/video/upload/a102.mp4",
        )
        cls.private_image = RoomMedia.objects.create(
            room=cls.private_room, media_type="image", public_id="private-image",
            url="https://res.cloudinary.com/example/image/upload/private.jpg",
        )
        tenant = Tenant.objects.create(user=cls.tenant_user, owner=cls.owner, full_name="Tour tenant")
        Contract.objects.create(
            code="TOUR-001", room=cls.room, representative=tenant,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            monthly_rent=3000000, status=Contract.Status.ACTIVE,
        )
        cls.url = reverse("room-walkthrough", args=[cls.room.id])

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=" + self.url, response.url)

    def test_owner_sees_only_room_media_and_edit_return_link(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rentals/room_walkthrough.html")
        self.assertEqual(response.context["room"], self.room)
        self.assertEqual(response.context["room_images"], [self.image])
        self.assertEqual(response.context["room_videos"], [self.video])
        self.assertEqual(response.context["tour_config"], {"entryRoom": "A101", "rooms": ["A101", "A102"]})
        self.assertEqual(response.context["tour_rooms"], [
            {"number": "A101", "images": [self.image], "videos": [self.video]},
            {"number": "A102", "images": [self.adjacent_image], "videos": [self.adjacent_video]},
        ])
        self.assertEqual(response.context["return_url"], reverse("room-update", args=[self.room.id]))
        self.assertNotContains(response, self.private_image.url)

    def test_other_owner_cannot_open_walkthrough(self):
        self.client.force_login(self.other_owner)
        for room in (self.room, self.adjacent_room):
            with self.subTest(room=room.number):
                self.assertEqual(self.client.get(reverse("room-walkthrough", args=[room.id])).status_code, 404)

    def test_a102_entry_uses_its_own_media_and_keeps_a101_accessible(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("room-walkthrough", args=[self.adjacent_room.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["room"], self.adjacent_room)
        self.assertEqual(response.context["room_images"], [self.adjacent_image])
        self.assertEqual(response.context["room_videos"], [self.adjacent_video])
        self.assertEqual(response.context["tour_config"], {"entryRoom": "A102", "rooms": ["A101", "A102"]})
        self.assertEqual(response.context["return_url"], reverse("room-update", args=[self.adjacent_room.id]))

    def test_admin_shared_tour_does_not_include_other_buildings(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("room-walkthrough", args=[self.private_room.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tour_config"], {"entryRoom": "A101", "rooms": ["A101"]})
        self.assertEqual(response.context["tour_rooms"], [
            {"number": "A101", "images": [self.private_image], "videos": []},
        ])
        self.assertNotContains(response, self.image.url)
        self.assertNotContains(response, self.adjacent_image.url)

    def test_assigned_staff_and_admin_can_open_walkthrough(self):
        for user in (self.staff, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_unassigned_staff_and_unlinked_tenant_cannot_open_walkthrough(self):
        for user in (self.unassigned_staff, self.unlinked_tenant):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_tenant_can_only_open_their_room_and_returns_to_tenant_portal(self):
        self.client.force_login(self.tenant_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["return_url"], reverse("tenant-rooms"))
        self.assertEqual(response.context["tour_config"], {"entryRoom": "A101", "rooms": ["A101"]})
        self.assertEqual(response.context["tour_rooms"], [
            {"number": "A101", "images": [self.image], "videos": [self.video]},
        ])
        self.assertNotContains(response, self.adjacent_image.url)
        self.assertNotContains(response, self.adjacent_video.url)
        adjacent_url = reverse("room-walkthrough", args=[self.adjacent_room.id])
        self.assertEqual(self.client.get(adjacent_url).status_code, 404)
        private_url = reverse("room-walkthrough", args=[self.private_room.id])
        self.assertEqual(self.client.get(private_url).status_code, 404)

    def test_tenant_of_a102_does_not_receive_a101_media_or_layout(self):
        Contract.objects.filter(representative__user=self.tenant_user).update(room=self.adjacent_room)
        self.client.force_login(self.tenant_user)
        response = self.client.get(reverse("room-walkthrough", args=[self.adjacent_room.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tour_config"], {"entryRoom": "A102", "rooms": ["A102"]})
        self.assertEqual(response.context["tour_rooms"], [
            {"number": "A102", "images": [self.adjacent_image], "videos": [self.adjacent_video]},
        ])
        self.assertNotContains(response, self.image.url)
        self.assertNotContains(response, self.video.url)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_rooms_without_a_walkthrough_return_404(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("room-walkthrough", args=[self.other_room.id]))
        self.assertEqual(response.status_code, 404)

    def test_walkthrough_still_loads_when_no_media_has_been_uploaded(self):
        self.client.force_login(self.owner)
        self.room.media.all().delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["room_images"], [])
        self.assertEqual(response.context["room_videos"], [])
        self.assertEqual(response.context["tour_rooms"][0], {"number": "A101", "images": [], "videos": []})

    def test_room_list_and_editor_link_only_to_supported_room(self):
        self.client.force_login(self.owner)
        list_response = self.client.get(reverse("rooms"))
        self.assertContains(list_response, self.url)
        adjacent_url = reverse("room-walkthrough", args=[self.adjacent_room.id])
        self.assertContains(list_response, adjacent_url)
        self.assertNotContains(list_response, reverse("room-walkthrough", args=[self.other_room.id]))
        self.assertNotContains(list_response, reverse("room-walkthrough", args=[self.private_room.id]))
        edit_response = self.client.get(reverse("room-update", args=[self.room.id]))
        self.assertContains(edit_response, self.url)
        adjacent_edit = self.client.get(reverse("room-update", args=[self.adjacent_room.id]))
        self.assertContains(adjacent_edit, adjacent_url)
        other_edit = self.client.get(reverse("room-update", args=[self.other_room.id]))
        self.assertNotContains(other_edit, "Tham quan 3D")

    def test_walkthrough_does_not_accept_post_requests(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url).status_code, 405)
