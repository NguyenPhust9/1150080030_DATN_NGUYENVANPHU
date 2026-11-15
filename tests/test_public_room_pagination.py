from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Room


class PublicRoomPaginationTests(TestCase):
    def setUp(self):
        owner = get_user_model().objects.create_user(username="list-owner", password="test", role="owner")
        self.building = Building.objects.create(name="Tòa A", address="Quận 3", owner=owner)
        for number in range(25):
            Room.objects.create(
                building=self.building, number=f"A{number + 101}", monthly_rent=2000000 + number * 10000
            )

    def test_pages_have_twelve_rooms_and_show_total_count(self):
        url = reverse("public-rooms")
        first = self.client.get(url)
        second = self.client.get(url, {"page": 2})
        third = self.client.get(url, {"page": 3})
        self.assertEqual([len(response.context["rooms"]) for response in (first, second, third)], [12, 12, 1])
        self.assertEqual(first.context["page_obj"].paginator.count, 25)
        self.assertContains(first, "Tìm thấy <strong>25</strong>", html=False)
        self.assertContains(first, "?page=2")

    def test_filter_and_sort_survive_page_change(self):
        response = self.client.get(reverse("public-rooms"), {
            "building": self.building.name, "sort": "price_desc", "page": 2,
        })
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 25)
        self.assertContains(response, "building=T%C3%B2a+A")
        self.assertContains(response, "sort=price_desc")

    def test_invalid_page_falls_back_to_first_page(self):
        response = self.client.get(reverse("public-rooms"), {"page": "abc"})
        self.assertEqual(response.context["page_obj"].number, 1)

    def test_public_room_contact_uses_support_phone_and_email(self):
        room = Room.objects.filter(building=self.building).first()
        response = self.client.get(reverse("public-room-detail", args=[room.pk]))
        self.assertContains(response, 'href="tel:0902966704"')
        self.assertContains(response, 'href="mailto:1150080030@sv.hcmunre.edu.vn"')
