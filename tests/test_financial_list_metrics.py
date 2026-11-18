from datetime import date, datetime
from decimal import Decimal
from html import unescape
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.rentals.models import Building, Contract, Invoice, Payment, Room, Tenant


class FinancialListMetricsTests(TestCase):
    """The cards summarize the complete, filtered set visible to the operator."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="metrics-owner", role="owner")
        cls.other_owner = User.objects.create_user(username="metrics-other", role="owner")
        cls.staff = User.objects.create_user(username="metrics-staff", role="staff")
        cls.building = Building.objects.create(name="Metrics A", address="A", owner=cls.owner)
        cls.second_building = Building.objects.create(name="Metrics B", address="B", owner=cls.owner)
        cls.foreign_building = Building.objects.create(name="Hidden building", address="C", owner=cls.other_owner)
        cls.building.staff.add(cls.staff)
        contracts = []
        for index, building in enumerate((cls.building, cls.second_building, cls.foreign_building)):
            room = Room.objects.create(building=building, number=f"A{index}01", monthly_rent=1000)
            tenant = Tenant.objects.create(owner=building.owner, full_name=f"Resident {index}")
            contracts.append(Contract.objects.create(
                code=f"METRICS-CONTRACT-{index}", room=room, representative=tenant,
                start_date=date(2026, 1, 1), end_date=date(2027, 1, 1),
                monthly_rent=1000, status=Contract.Status.ACTIVE,
            ))
        cls.contract, cls.second_contract, cls.foreign_contract = contracts
        cls.paid = cls.make_invoice("PAID", cls.contract, 9, Invoice.Status.PAID, 1000, 1000)
        cls.partial = cls.make_invoice("PARTIAL", cls.contract, 10, Invoice.Status.PARTIAL, 2000, 500)
        cls.future = cls.make_invoice(
            "FUTURE", cls.contract, 11, Invoice.Status.ISSUED, 3000, due=date(2026, 12, 5),
        )
        cls.stale_issued = cls.make_invoice(
            "STALE-ISSUED", cls.second_contract, 11, Invoice.Status.ISSUED, 4000,
        )
        cls.make_invoice("DRAFT", cls.contract, 12, Invoice.Status.DRAFT, 9000, due=date(2026, 10, 1))
        cls.make_invoice("CANCELLED", cls.contract, 1, Invoice.Status.CANCELLED, 8000)
        cls.make_invoice("ZERO-BALANCE", cls.contract, 8, Invoice.Status.OVERDUE, 100, 100)
        cls.make_invoice(
            "FUTURE-STALE-OVERDUE", cls.contract, 7, Invoice.Status.OVERDUE, 200,
            due=date(2026, 12, 5),
        )
        cls.cash = cls.make_payment(cls.paid, 600, Payment.Method.CASH, 9, "CASH-REF")
        cls.transfer = cls.make_payment(cls.paid, 400, Payment.Method.TRANSFER, 10, "TRANSFER-REF")
        cls.other = cls.make_payment(cls.partial, 500, Payment.Method.OTHER, 11, "OTHER-REF")
        cls.void = cls.make_payment(cls.paid, 999, Payment.Method.CASH, 11, "VOID-REF", is_void=True)
        foreign_invoice = Invoice.objects.create(
            code="HIDDEN-INVOICE", contract=cls.foreign_contract, period=date(2042, 1, 1),
            issued_date=date(2042, 1, 1), due_date=date(2042, 1, 5),
            total_amount=99999, paid_amount=99999, status=Invoice.Status.PAID,
        )
        Payment.objects.create(
            invoice=foreign_invoice, amount=99999, method=Payment.Method.CASH,
            paid_at=timezone.make_aware(datetime(2042, 1, 3, 12)), received_by=cls.other_owner,
        )

    @classmethod
    def make_invoice(cls, code, contract, month, status, total, paid=0, due=None):
        return Invoice.objects.create(
            code=f"METRICS-{code}", contract=contract, period=date(2026, month, 1),
            issued_date=date(2026, month, 1), due_date=due or date(2026, month, 5),
            subtotal=total, total_amount=total, paid_amount=paid, status=status,
        )

    @classmethod
    def make_payment(cls, invoice, amount, method, month, reference, is_void=False):
        return Payment.objects.create(
            invoice=invoice, amount=amount, method=method, reference=reference, is_void=is_void,
            paid_at=timezone.make_aware(datetime(2026, month, 10, 12)), received_by=cls.owner,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        clock = patch("django.utils.timezone.localdate", return_value=date(2026, 11, 18))
        clock.start()
        self.addCleanup(clock.stop)

    def get_list(self, resource, **filters):
        response = self.client.get(reverse(resource), filters)
        self.assertEqual(response.status_code, 200)
        return response

    def test_invoice_cards_count_balances_and_due_dates_without_payment_join_duplication(self):
        metrics = self.get_list("invoices").context["financial_metrics"]
        self.assertEqual(metrics["total_count"], 8)
        self.assertEqual(metrics["paid_count"], 1)
        self.assertEqual(metrics["unpaid_count"], 4)
        self.assertEqual(metrics["unpaid_amount"], Decimal("8700"))
        self.assertEqual(metrics["overdue_count"], 2)
        self.assertEqual(metrics["overdue_amount"], Decimal("5500"))
        # Actual valid receipts, not paid_amount or a duplicated invoice aggregate.
        self.assertEqual(metrics["collected_amount"], Decimal("1500"))

    def test_payment_cards_exclude_void_amounts_from_every_method(self):
        metrics = self.get_list("payments").context["financial_metrics"]
        self.assertEqual(metrics["total_count"], 4)
        self.assertEqual(metrics["valid_count"], 3)
        self.assertEqual(metrics["void_count"], 1)
        self.assertEqual(metrics["collected_amount"], Decimal("1500"))
        self.assertEqual(metrics["cash_amount"], Decimal("600"))
        self.assertEqual(metrics["transfer_amount"], Decimal("400"))
        self.assertEqual(metrics["other_amount"], Decimal("500"))

    def test_invoice_cards_follow_combined_search_status_building_and_billing_period(self):
        response = self.get_list(
            "invoices", q="PARTIAL", status="partial", building=str(self.building.pk), year="2026", month="10",
        )
        metrics = response.context["financial_metrics"]
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual(metrics["total_count"], 1)
        self.assertEqual(metrics["unpaid_amount"], Decimal("1500"))
        self.assertEqual(metrics["overdue_count"], 1)
        # The receipt was paid in November, but belongs to the October invoice.
        self.assertEqual(metrics["collected_amount"], Decimal("500"))

    def test_payment_date_filter_uses_receipt_date_not_invoice_period(self):
        metrics = self.get_list("payments", year="2026", month="10").context["financial_metrics"]
        self.assertEqual(metrics["total_count"], 1)
        self.assertEqual(metrics["transfer_amount"], Decimal("400"))
        self.assertEqual(metrics["collected_amount"], Decimal("400"))
        november = self.get_list("payments", year="2026", month="11").context["financial_metrics"]
        self.assertEqual(november["total_count"], 2)
        self.assertEqual(november["valid_count"], 1)
        self.assertEqual(november["void_count"], 1)
        self.assertEqual(november["collected_amount"], Decimal("500"))

    def test_payment_cards_follow_method_search_void_and_building_filters(self):
        self.make_payment(self.stale_issued, 250, Payment.Method.CASH, 11, "SECOND-BUILDING")
        response = self.get_list(
            "payments", building=str(self.second_building.pk), method="cash", q="SECOND", void="valid",
        )
        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual(response.context["financial_metrics"]["collected_amount"], Decimal("250"))
        void_metrics = self.get_list("payments", void="void").context["financial_metrics"]
        self.assertEqual(void_metrics["total_count"], 1)
        self.assertEqual(void_metrics["void_count"], 1)
        self.assertEqual(void_metrics["valid_count"], 0)
        for key in ("collected_amount", "cash_amount", "transfer_amount", "other_amount"):
            self.assertEqual(void_metrics[key], Decimal("0"))

    def test_foreign_building_filter_cannot_expose_owner_data(self):
        for resource in ("invoices", "payments"):
            with self.subTest(resource=resource):
                response = self.get_list(resource, building=str(self.foreign_building.pk))
                self.assertEqual(response.context["paginator"].count, 0)
                self.assertTrue(all(value == 0 for value in response.context["financial_metrics"].values()))
                self.assertNotContains(response, "HIDDEN-INVOICE")

    def test_year_choices_are_scoped_before_filtering(self):
        for resource in ("invoices", "payments"):
            with self.subTest(resource=resource):
                response = self.get_list(resource, q="no-results", year="2026", month="11")
                self.assertIn(2026, response.context["year_choices"])
                self.assertNotIn(2042, response.context["year_choices"])

    def test_assigned_staff_cards_follow_building_permissions(self):
        self.client.force_login(self.staff)
        metrics = self.get_list("invoices").context["financial_metrics"]
        self.assertEqual(metrics["total_count"], 7)
        self.assertEqual(metrics["overdue_count"], 1)
        self.assertEqual(metrics["overdue_amount"], Decimal("1500"))
        self.make_payment(self.stale_issued, 250, Payment.Method.CASH, 11, "SECOND-BUILDING")
        self.assertEqual(self.get_list("payments").context["financial_metrics"]["total_count"], 4)

    def test_invoice_metrics_cover_all_pages(self):
        Invoice.objects.bulk_create([
            Invoice(
                code=f"METRICS-PAGE-{index}", contract=self.contract,
                period=date(2026, 1, 1), issued_date=date(2026, 1, 1), due_date=date(2026, 1, 5),
                status=Invoice.Status.CANCELLED, total_amount=10,
            ) for index in range(25)
        ])
        response = self.get_list("invoices", page="2")
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertLess(len(response.context["objects"]), 33)
        self.assertEqual(response.context["financial_metrics"]["total_count"], 33)
        self.assertEqual(response.context["financial_metrics"]["collected_amount"], Decimal("1500"))

    def test_payment_metrics_cover_all_pages(self):
        Payment.objects.bulk_create([
            Payment(invoice=self.paid, amount=10, method=Payment.Method.CASH,
                    paid_at=self.cash.paid_at, received_by=self.owner)
            for _ in range(25)
        ])
        response = self.get_list("payments", page="2")
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["financial_metrics"]["total_count"], 29)
        self.assertEqual(response.context["financial_metrics"]["collected_amount"], Decimal("1750"))

    def test_malformed_filters_do_not_error_or_leak_foreign_data(self):
        for resource, expected_count in (("invoices", 8), ("payments", 4)):
            for year, month in (("oops", "13"), ("10000", "0"), ("-2026", "-1")):
                with self.subTest(resource=resource, year=year, month=month):
                    response = self.get_list(
                        resource, year=year, month=month, building="invalid-uuid",
                        status="unknown", method="unknown", void="unknown",
                    )
                    self.assertEqual(response.context["financial_metrics"]["total_count"], expected_count)
                    self.assertEqual(response.context["selected_year"], "")
                    self.assertEqual(response.context["selected_month"], "")

    def test_empty_results_have_zero_metrics(self):
        for resource in ("invoices", "payments"):
            with self.subTest(resource=resource):
                response = self.get_list(resource, q="definitely-no-match")
                self.assertEqual(response.context["paginator"].count, 0)
                self.assertTrue(all(value == 0 for value in response.context["financial_metrics"].values()))

    def test_both_lists_render_metric_cards_and_period_filters(self):
        for resource, aria_label, labels in (
            ("invoices", "Chỉ số hóa đơn", ("Tổng hóa đơn", "Chưa thanh toán", "Quá hạn", "Đã thu")),
            ("payments", "Chỉ số thanh toán", ("Tổng giao dịch", "Thực thu", "Tiền mặt", "Chuyển khoản")),
        ):
            with self.subTest(resource=resource):
                response = self.get_list(resource, year="2026", month="11")
                self.assertContains(response, f'aria-label="{aria_label}"')
                for label in labels:
                    self.assertContains(response, label)
                self.assertContains(response, 'name="year"')
                self.assertContains(response, 'name="month"')
                self.assertEqual(response.context["selected_year"], "2026")
                self.assertEqual(response.context["selected_month"], "11")

    def test_pagination_preserves_financial_filters(self):
        Invoice.objects.bulk_create([
            Invoice(
                code=f"METRICS-PAGING-{index}", contract=self.contract,
                period=date(2026, 11, 1), issued_date=date(2026, 11, 1), due_date=date(2026, 11, 5),
                status=Invoice.Status.CANCELLED, total_amount=10,
            ) for index in range(25)
        ])
        Payment.objects.bulk_create([
            Payment(invoice=self.paid, amount=10, method=Payment.Method.CASH,
                    paid_at=self.other.paid_at, received_by=self.owner, reference="PAGING")
            for _ in range(25)
        ])
        for resource, extra in (
            ("invoices", {"status": "cancelled"}),
            ("payments", {"method": "cash", "void": "valid"}),
        ):
            with self.subTest(resource=resource):
                filters = {"q": "PAGING", "building": str(self.building.pk), "year": "2026", "month": "11", **extra}
                response = self.get_list(resource, **filters)
                self.assertEqual(response.context["paginator"].count, 25)
                links = [
                    parse_qs(urlsplit(unescape(href)).query)
                    for href in re.findall(r'href="([^"]+)"', response.content.decode())
                ]
                next_links = [params for params in links if params.get("page") == ["2"]]
                self.assertTrue(next_links, "The next page link is missing.")
                for params in next_links:
                    for key, value in filters.items():
                        self.assertEqual(params.get(key), [value], f"Pagination lost filter {key}.")
