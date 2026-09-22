import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Room, RoomMedia


class RoomEditTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="room-admin", password="test", role="admin")
        self.building = Building.objects.create(name="Tòa A", address="Hà Nội", owner=self.admin)
        self.room = Room.objects.create(building=self.building, number="A101", floor=1, monthly_rent=3000000)

    def test_admin_can_edit_room_and_add_cloudinary_image(self):
        self.client.force_login(self.admin)
        url = reverse("room-update", args=[self.room.id])
        self.assertContains(self.client.get(url), "Sửa phòng A101")
        response = self.client.post(url, {
            "building": str(self.building.id), "number": "A102", "floor": 2,
            "area": "25", "monthly_rent": "3500000", "deposit_amount": "1000000",
            "max_occupants": 2, "status": "available", "description": "Phòng mới sửa",
            "media_payload": json.dumps([{
                "media_type": "image", "url": "https://res.cloudinary.com/example/image/upload/test.jpg",
                "public_id": "test", "format": "jpg", "bytes": 100,
            }]),
        })
        self.assertRedirects(response, reverse("rooms"))
        self.room.refresh_from_db()
        self.assertEqual(self.room.number, "A102")
        self.assertEqual(self.room.media.count(), 1)

    def test_anonymous_user_cannot_edit_room(self):
        response = self.client.get(reverse("room-update", args=[self.room.id]))
        self.assertEqual(response.status_code, 302)
