"""Public homepage content and navigation survive presentation changes.

Run with --settings=config.test_indoor_settings to keep the database isolated.
"""
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.rentals.models import Building, Room, RoomMedia


class HomepageElements(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.elements = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def attributes(self, tag):
        return [attrs for element_tag, attrs in self.elements if element_tag == tag]


class PublicHomeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="homepage-owner", password="test-only", role="owner"
        )
        cls.building = Building.objects.create(
            name="A Test Building", address="Quận 3", owner=cls.owner
        )

    def room(self, number, **kwargs):
        return Room.objects.create(
            building=kwargs.pop("building", self.building),
            number=number,
            monthly_rent=3000000,
            **kwargs,
        )

    def media(self, room, name, **kwargs):
        return RoomMedia.objects.create(
            room=room,
            media_type=kwargs.pop("media_type", RoomMedia.MediaType.IMAGE),
            url=f"https://res.cloudinary.com/example/image/upload/{name}.jpg",
            public_id=name,
            **kwargs,
        )

    def test_available_active_rooms_remain_complete_in_carousel(self):
        rooms = [self.room(f"A{101 + number}") for number in range(8)]
        occupied = self.room("A201", floor=2, status=Room.Status.OCCUPIED)
        reserved = self.room("A202", floor=2, status=Room.Status.RESERVED)
        inactive_building = Building.objects.create(
            name="B Hidden Building", address="Hidden address", owner=self.owner,
            is_active=False,
        )
        hidden = self.room("B101", building=inactive_building)
        response = self.client.get(reverse("public-home"))

        self.assertEqual(response.context["available_count"], 8)
        self.assertEqual(response.context["building_count"], 1)
        groups = response.context["building_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["available_count"], 8)
        self.assertEqual(groups[0]["floor_count"], 2)
        self.assertEqual([room.pk for room in groups[0]["rooms"]], [room.pk for room in rooms])
        for room in rooms:
            self.assertContains(response, f'data-room-id="{room.pk}"')
            self.assertContains(response, f'data-favorite-room="{room.pk}"')
            self.assertContains(response, reverse("public-room-detail", args=[room.pk]))
        for room in (occupied, reserved, hidden):
            self.assertNotContains(response, f'data-room-id="{room.pk}"')
        self.assertNotContains(response, inactive_building.name)
        self.assertContains(response, "data-room-carousel")
        self.assertContains(response, "data-room-prev")
        self.assertContains(response, "data-room-next")

    def test_hero_uses_first_available_room_with_image_across_all_rooms(self):
        first = self.room("A101")
        self.media(first, "video-only", media_type=RoomMedia.MediaType.VIDEO)
        # A hero may use an image beyond the six rooms in featured_rooms.
        for number in range(102, 108):
            self.room(f"A{number}")
        pictured = self.room("A108")
        image = self.media(pictured, "actual-room-cover")
        later = self.room("A109")
        self.media(later, "another-room-cover")
        response = self.client.get(reverse("public-home"))

        self.assertEqual(response.context["hero_room"].pk, pictured.pk)
        self.assertEqual(response.context["hero_room"].cover_image_url, image.url)
        self.assertContains(response, image.url)

    def test_hero_respects_primary_image_and_excludes_unavailable_rooms(self):
        occupied = self.room("A101", status=Room.Status.OCCUPIED)
        hidden_image = self.media(occupied, "occupied-cover")
        available = self.room("A102")
        primary = self.media(available, "primary-cover", is_primary=True)
        self.media(available, "newer-secondary-cover")
        response = self.client.get(reverse("public-home"))

        self.assertEqual(response.context["hero_room"].pk, available.pk)
        self.assertEqual(response.context["hero_room"].cover_image_url, primary.url)
        self.assertContains(response, primary.url)
        self.assertNotContains(response, hidden_image.url)

    def test_home_renders_when_no_room_has_image(self):
        room = self.room("A101")
        self.media(room, "video-without-photo", media_type=RoomMedia.MediaType.VIDEO)
        response = self.client.get(reverse("public-home"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["hero_room"])
        self.assertContains(response, f'data-room-id="{room.pk}"')

    def test_empty_home_remains_searchable(self):
        response = self.client.get(reverse("public-home"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["hero_room"])
        self.assertEqual(response.context["building_groups"], [])
        self.assertEqual(response.context["available_count"], 0)
        self.assertContains(response, "Chưa có phòng trống")
        self.assertContains(response, f'action="{reverse("public-rooms")}"')

    def test_search_favorites_navigation_and_contact_controls_are_preserved(self):
        self.room("A101")
        response = self.client.get(reverse("public-home"))
        elements = HomepageElements(response.content.decode())
        links = {attrs.get("href") for attrs in elements.attributes("a")}
        self.assertTrue({
            reverse("public-home"), reverse("public-rooms"),
            reverse("public-about"), reverse("public-contact"),
            f'{reverse("public-rooms")}?favorites=1', reverse("login"),
            "tel:0902966704", "mailto:1150080030@sv.hcmunre.edu.vn",
        }.issubset(links))
        forms = elements.attributes("form")
        self.assertGreaterEqual(
            sum(form.get("action") == reverse("public-rooms") for form in forms), 2
        )
        inputs = elements.attributes("input")
        selects = elements.attributes("select")
        names = {attrs.get("name") for attrs in inputs + selects}
        self.assertTrue({"q", "building", "min_price", "max_price", "district", "amenity"}.issubset(names))
        amenities = {attrs.get("value") for attrs in inputs if attrs.get("name") == "amenity"}
        self.assertEqual(amenities, {"Máy lạnh", "Bãi xe", "Wi-Fi"})
        self.assertTrue(any(
            attrs.get("type") == "checkbox" and attrs.get("name") == "building"
            and attrs.get("value") == self.building.name for attrs in inputs
        ))
        self.assertContains(response, 'id="favorite-count"')
        self.assertContains(response, 'id="price-filter"')
        self.assertContains(response, 'id="price-filter-value"')

    def test_authenticated_users_keep_role_specific_system_link(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("public-home"))
        self.assertContains(response, f'href="{reverse("dashboard")}"')
        tenant = get_user_model().objects.create_user(
            username="homepage-tenant", password="test-only", role="tenant"
        )
        self.client.force_login(tenant)
        response = self.client.get(reverse("public-home"))
        self.assertContains(response, f'href="{reverse("tenant-portal")}"')


class PublicInformationPageTests(TestCase):
    pages = (
        ("public-about", "public/about.html", "Về chúng tôi"),
        ("public-contact", "public/contact.html", "Liên hệ"),
    )

    def test_guests_can_read_pages_and_reach_search_favorites_and_login(self):
        for route, template, label in self.pages:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                self.assertContains(response, label)
                elements = HomepageElements(response.content.decode())
                self.assertEqual(len(elements.attributes("h1")), 1)
                links = {attrs.get("href") for attrs in elements.attributes("a")}
                self.assertTrue({
                    reverse("public-home"), reverse("public-rooms"),
                    reverse("public-about"), reverse("public-contact"),
                    f'{reverse("public-rooms")}?favorites=1', reverse("login"),
                }.issubset(links))
                active_links = [attrs.get("href") for attrs in elements.attributes("a")
                                if attrs.get("aria-current") == "page"]
                self.assertEqual(active_links, [reverse(route)])

    def test_contact_page_links_to_existing_phone_and_email(self):
        response = self.client.get(reverse("public-contact"))
        elements = HomepageElements(response.content.decode())
        links = {attrs.get("href") for attrs in elements.attributes("a")}
        self.assertIn("tel:0902966704", links)
        self.assertTrue(any(
            href and href.split("?", 1)[0] == "mailto:1150080030@sv.hcmunre.edu.vn"
            for href in links
        ))
        # A contact page must not offer an unimplemented form submission.
        self.assertFalse(any(
            attrs.get("method", "get").lower() == "post"
            for attrs in elements.attributes("form")
        ))

    def test_signed_in_users_keep_their_role_specific_system_links(self):
        for role, destination in (("owner", "dashboard"), ("tenant", "tenant-portal")):
            user = get_user_model().objects.create_user(
                username=f"information-{role}", password="test-only", role=role
            )
            self.client.force_login(user)
            for route, template, label in self.pages:
                with self.subTest(role=role, route=route):
                    response = self.client.get(reverse(route))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f'href="{reverse(destination)}"')
            self.client.logout()
