"""Guard the pre-merge local presentation without rolling back app features.

Run with --settings=config.test_indoor_settings so fixtures use SQLite only.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Room


class LocalDesignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="local-design-owner", password="test-only", role="owner"
        )
        cls.building = Building.objects.create(
            name="Tòa kiểm thử giao diện", address="Quận 3", owner=cls.owner
        )
        cls.available_room = Room.objects.create(
            building=cls.building,
            number="LOCAL-101",
            monthly_rent=Decimal("3000000"),
            status=Room.Status.AVAILABLE,
        )
        cls.occupied_room = Room.objects.create(
            building=cls.building,
            number="LOCAL-102",
            monthly_rent=Decimal("3200000"),
            status=Room.Status.OCCUPIED,
        )

    def assert_local_public_shell(self, response):
        self.assertContains(response, static("css/public-home.css"))
        self.assertContains(response, static("images/favicon.png"))
        self.assertContains(response, static("js/favorites.js"))
        self.assertContains(response, static("js/loading.js"))
        self.assertContains(response, f'href="{reverse("public-home")}#gioi-thieu"')
        self.assertContains(response, 'class="public-footer"')
        for obsolete in (
            "css/hero-banner.css",
            "css/about.css",
            "images/logo.png",
            "images/anhnen.jpg",
            "hero-search-capsule",
            "custom-hero",
            "hero-cyan-subtitle",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotContains(response, obsolete)

    def test_home_restores_local_hero_and_search_controls(self):
        response = self.client.get(reverse("public-home"))
        self.assertTemplateUsed(response, "public/home.html")
        self.assert_local_public_shell(response)
        self.assertContains(response, '<section class="guest-hero">')
        self.assertContains(response, 'class="guest-hero-inner"')
        self.assertContains(response, 'class="hero-assurance"')
        self.assertContains(response, 'class="guest-search"')
        self.assertContains(response, 'name="building"')
        self.assertContains(response, 'name="min_price" type="number"')
        self.assertContains(response, 'name="max_price" type="number"')
        self.assertContains(response, 'id="gioi-thieu" class="property-browser"')
        self.assertContains(response, self.building.name)
        self.assertContains(response, self.available_room.number)
        self.assertNotContains(response, self.occupied_room.number)

    def test_previous_about_url_redirects_to_local_home_section(self):
        response = self.client.get(reverse("public-about"))
        self.assertRedirects(
            response,
            f'{reverse("public-home")}#gioi-thieu',
            fetch_redirect_response=False,
        )

    def test_login_restores_local_brand_assets(self):
        response = self.client.get(reverse("login"))
        self.assertTemplateUsed(response, "registration/login.html")
        self.assertContains(response, static("images/favicon.png"))
        self.assertContains(response, static("images/anhlogo.png"), count=2)
        self.assertContains(response, static("images/anhlogin.png"))
        self.assertContains(response, static("css/loading.css"))
        self.assertNotContains(response, "images/logo.png")

    def test_manager_dashboard_keeps_local_sidebar_and_features(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, static("images/favicon.png"))
        self.assertContains(response, 'class="nav-group-toggle"')
        self.assertContains(response, reverse("indoor-map-list"))
        self.assertContains(response, reverse("fire_detection:monitor"))
        self.assertContains(response, reverse("chat-list"))
        self.assertContains(response, static("css/management.css"))
        self.assertNotContains(response, 'class="brand"')
        self.assertNotContains(response, "images/logo.png")

    def test_guest_room_listing_keeps_local_shell_and_availability(self):
        response = self.client.get(reverse("public-rooms"))
        self.assert_local_public_shell(response)
        self.assertContains(response, self.available_room.number)
        self.assertNotContains(response, self.occupied_room.number)

    def test_guest_room_detail_keeps_local_shell_and_contact(self):
        response = self.client.get(
            reverse("public-room-detail", args=[self.available_room.pk])
        )
        self.assert_local_public_shell(response)
        self.assertContains(response, f"Phòng {self.available_room.number}")
        self.assertContains(response, 'href="tel:0902966704"')
        self.assertContains(response, 'href="mailto:1150080030@sv.hcmunre.edu.vn"')
        hidden = self.client.get(
            reverse("public-room-detail", args=[self.occupied_room.pk])
        )
        self.assertEqual(hidden.status_code, 404)
