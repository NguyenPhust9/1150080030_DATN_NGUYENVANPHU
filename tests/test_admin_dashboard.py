"""Dashboard data remains readable and its chart works in Vietnamese locale.

Run with --settings=config.test_indoor_settings to use isolated SQLite only.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from apps.rentals.models import Building, Contract, Invoice, Payment, Room, Tenant


class DashboardChartParser(HTMLParser):
    """Read the chart's bars and visible values independently of attribute order."""

    def __init__(self, html):
        super().__init__()
        self.bars = []
        self.months = []
        self.current_month = None
        self.current_field = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if "chart-bar" in classes:
            self.bars.append(attrs)
        if tag == "article" and "chart-month" in classes:
            self.current_month = {"label": "", "values": []}
        if self.current_month is not None:
            if tag == "h3":
                self.current_field = "label"
            elif tag == "dd":
                self.current_field = "values"
                self.current_month["values"].append("")

    def handle_data(self, data):
        if self.current_month is None:
            return
        if self.current_field == "label":
            self.current_month["label"] += data
        elif self.current_field == "values":
            self.current_month["values"][-1] += data

    def handle_endtag(self, tag):
        if tag in ("h3", "dd"):
            self.current_field = None
        if tag == "article" and self.current_month is not None:
            self.months.append(self.current_month)
            self.current_month = None


@override_settings(LANGUAGE_CODE="vi")
class AdminDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="dashboard-owner", password="test-only", role="owner"
        )
        building = Building.objects.create(
            name="Tòa nhà kiểm thử", address="TP.HCM", owner=cls.owner
        )
        room = Room.objects.create(
            building=building, number="A101", monthly_rent=Decimal("7000000")
        )
        tenant = Tenant.objects.create(
            full_name="Khách kiểm thử", phone="0900000001", identity_number="DASHBOARD-001"
        )
        cls.contract = Contract.objects.create(
            code="HD-DASHBOARD", room=room, representative=tenant,
            start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
            monthly_rent=Decimal("7000000"), status=Contract.Status.ACTIVE,
        )
        for month, amount in ((6, "7000000"), (11, "2000000")):
            invoice = Invoice.objects.create(
                code=f"HDON-DASHBOARD-{month}", contract=cls.contract,
                period=date(2026, month, 1), issued_date=date(2026, month, 1),
                due_date=date(2026, month, 10), subtotal=Decimal(amount),
                total_amount=Decimal(amount), status=Invoice.Status.ISSUED,
            )
        cls.latest_invoice = invoice
        invoice.paid_amount = Decimal("1000000")
        invoice.status = Invoice.Status.PARTIAL
        invoice.save(update_fields=["paid_amount", "status"])
        Payment.objects.create(
            invoice=invoice, amount=Decimal("1000000"),
            paid_at=datetime(2026, 11, 5, 8, tzinfo=timezone.utc),
            method=Payment.Method.CASH, received_by=cls.owner,
        )

    def get_dashboard(self, user=None):
        self.client.force_login(user or self.owner)
        with translation.override("vi"), patch(
            "apps.rentals.views.timezone.localdate", return_value=date(2026, 11, 18)
        ):
            response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        return response, DashboardChartParser(response.content.decode())

    def test_fractional_chart_heights_are_valid_under_vietnamese_locale(self):
        _, chart = self.get_dashboard()
        self.assertEqual(len(chart.bars), 12)
        percentages = []
        for bar in chart.bars:
            # A localized value such as "28,6" was previously converted to NaN
            # by JavaScript, flattening every nonzero bar. Heights now render
            # valid CSS on the server and also work with JavaScript disabled.
            raw_percent = bar["data-percent"]
            self.assertRegex(raw_percent, r"^\d+(?:\.\d+)?$")
            height = re.fullmatch(r"height:\s*(\d+(?:\.\d+)?)%", bar["style"])
            self.assertIsNotNone(height)
            percent = Decimal(raw_percent)
            self.assertEqual(Decimal(height.group(1)), percent)
            self.assertGreaterEqual(percent, 0)
            self.assertLessEqual(percent, 100)
            percentages.append(percent)
        self.assertIn(Decimal("28.6"), percentages)
        self.assertIn(Decimal("14.3"), percentages)
        self.assertIn(Decimal("0"), percentages)

    def test_all_six_months_keep_both_visible_currency_values_and_links(self):
        response, chart = self.get_dashboard()
        self.assertEqual(
            [month["label"] for month in chart.months],
            [f"Tháng {month}/2026" for month in range(6, 12)],
        )
        self.assertEqual(
            [month["values"] for month in chart.months],
            [["7.000.000 đ", "0 đ"], *[["0 đ", "0 đ"]] * 4,
             ["2.000.000 đ", "1.000.000 đ"]],
        )
        self.assertContains(response, "8.000.000 đ")
        for name, args in (
            ("invoices", []), ("contracts", []),
            ("invoice-detail", [self.latest_invoice.pk]),
            ("contract-detail", [self.contract.pk]),
        ):
            self.assertContains(response, f'href="{reverse(name, args=args)}"')

    def test_empty_account_has_six_zero_months_and_zero_height_bars(self):
        empty_owner = get_user_model().objects.create_user(
            username="empty-dashboard-owner", password="test-only", role="owner"
        )
        _, chart = self.get_dashboard(empty_owner)
        self.assertEqual(len(chart.months), 6)
        self.assertEqual(len(chart.bars), 12)
        for month in chart.months:
            self.assertEqual(month["values"], ["0 đ", "0 đ"])
        for bar in chart.bars:
            self.assertEqual(Decimal(bar["data-percent"]), 0)
            self.assertRegex(bar["style"], r"^height:\s*0(?:\.0+)?%$")
