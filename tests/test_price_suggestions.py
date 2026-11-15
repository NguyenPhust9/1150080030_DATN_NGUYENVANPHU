from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, PriceSuggestion, Room


class PriceSuggestionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username="price-owner", password="test", role="owner")
        self.other_owner = user_model.objects.create_user(username="other-owner", password="test", role="owner")
        self.building = Building.objects.create(name="Tòa A", address="Hà Nội", owner=self.owner)
        other_building = Building.objects.create(name="Tòa B", address="Hà Nội", owner=self.other_owner)
        self.room = Room.objects.create(
            building=self.building, number="A101", area=Decimal("25"), monthly_rent=Decimal("3000000")
        )
        for index in range(20):
            Room.objects.create(
                building=self.building, number=f"A{index + 102}", area=Decimal(20 + index),
                floor=1 + index % 4, monthly_rent=Decimal(2500000 + index * 100000),
            )
        for index in range(20):
            Room.objects.create(
                building=other_building, number=f"B{index + 101}", area=Decimal(20 + index),
                monthly_rent=Decimal("50000000"),
            )

    def test_owner_can_suggest_then_apply_without_changing_contracts(self):
        self.client.force_login(self.owner)
        url = reverse("price-suggestion", args=[self.room.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        suggestion = PriceSuggestion.objects.get(room=self.room)
        self.assertEqual(suggestion.sample_count, 20)
        self.assertIsNotNone(suggestion.validation_mae)
        self.assertIsNotNone(suggestion.validation_rmse)
        self.assertIsNotNone(suggestion.validation_r2)
        self.assertLess(suggestion.suggested_price, Decimal("10000000"))
        self.room.refresh_from_db()
        self.assertEqual(self.room.monthly_rent, Decimal("3000000"))
        apply_url = reverse("price-suggestion-apply", args=[self.room.pk, suggestion.pk])
        self.assertEqual(self.client.post(apply_url).status_code, 302)
        self.room.refresh_from_db()
        suggestion.refresh_from_db()
        self.assertEqual(self.room.monthly_rent, suggestion.suggested_price)
        self.assertIsNotNone(suggestion.applied_at)

    def test_other_owner_and_staff_cannot_see_or_apply_suggestion(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("price-suggestion", args=[self.room.pk]))
        suggestion = PriceSuggestion.objects.get(room=self.room)
        self.client.force_login(self.other_owner)
        self.assertEqual(self.client.get(reverse("price-suggestion", args=[self.room.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("price-suggestion-apply", args=[self.room.pk, suggestion.pk])).status_code,
            404,
        )
        staff = get_user_model().objects.create_user(username="price-staff", password="test", role="staff")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("price-suggestion", args=[self.room.pk])).status_code, 403)

    def test_stale_suggestion_does_not_overwrite_new_price(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("price-suggestion", args=[self.room.pk]))
        suggestion = PriceSuggestion.objects.get(room=self.room)
        self.room.monthly_rent = Decimal("4200000")
        self.room.save()
        self.client.post(reverse("price-suggestion-apply", args=[self.room.pk, suggestion.pk]))
        self.room.refresh_from_db()
        self.assertEqual(self.room.monthly_rent, Decimal("4200000"))
