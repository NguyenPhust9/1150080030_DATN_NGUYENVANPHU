import io
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.rentals.models import Building, Contract, ContractMember, Invoice, Room, Tenant
from apps.rentals.management.commands.allocate_demo_contracts import apply_contract_batch


class DemoContractAllocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("allocation-owner", role="owner")
        cls.buildings = [Building.objects.create(name=f"Building {i}", address="Test", owner=cls.owner) for i in range(5)]
        cls.rooms = []
        for i, building in enumerate(cls.buildings):
            for floor in range(1, 6):
                for slot in range(1, 6):
                    cls.rooms.append(Room.objects.create(building=building, floor=floor, number=f"{chr(65+i)}{floor}0{slot}",
                                                         monthly_rent=3200000+i*100000, deposit_amount=3000000))
        cls.tenants = [Tenant.objects.create(owner=cls.owner if i < 71 else None, full_name=f"Tenant {i}") for i in range(77)]
        cls.existing = []
        for i in range(3):
            room = cls.rooms[i*25]
            contract = Contract.objects.create(code=f"EXISTING-{i}", room=room, representative=cls.tenants[i],
                                               start_date=date(2026, 2, 1), end_date=date(2027, 2, 1),
                                               monthly_rent=room.monthly_rent, deposit_amount=room.deposit_amount, status="active")
            cls.existing.append(contract)
            room.status = "occupied"
            room.save()
        Room.objects.filter(pk=cls.rooms[26].pk).update(status="maintenance")
        Room.objects.filter(pk=cls.rooms[51].pk).update(status="reserved")

    def run_command(self, **overrides):
        output = io.StringIO()
        options = dict(owner_id=self.owner.pk, start_date=date(2026, 11, 18), end_date=date(2027, 11, 18),
                       min_vacant=5, seed="20261118", include_unowned=True, verbosity=0, stdout=output)
        options.update(overrides)
        call_command("allocate_demo_contracts", **options)
        return json.loads(output.getvalue().strip().splitlines()[-1])

    def test_dry_run_has_no_writes_and_retains_at_least_five_vacancies(self):
        before = list(Room.objects.order_by("pk").values())
        report = self.run_command()
        self.assertFalse(report["applied"])
        self.assertEqual(report["new_contracts"], 74)
        self.assertEqual(sum(b["available_after"] for b in report["buildings"]), 46)
        self.assertTrue(all(b["available_after"] >= 5 for b in report["buildings"]))
        self.assertEqual(report, self.run_command())
        self.assertEqual(Contract.objects.count(), 3)
        self.assertEqual(list(Room.objects.order_by("pk").values()), before)

    def test_apply_creates_valid_contracts_and_public_vacancies_without_invoices(self):
        before = list(Contract.objects.order_by("pk").values())
        with tempfile.TemporaryDirectory() as directory:
            report = self.run_command(apply=True, backup_dir=Path(directory))
            snapshot = json.loads(Path(report["backup"]).read_text(encoding="utf-8"))
            self.assertEqual(snapshot["state"], "committed")
            self.assertEqual(len(snapshot["new_contracts"]), 74)
            self.assertNotIn("full_name", snapshot["tenants_before"][0])
            second = self.run_command(apply=True, backup_dir=Path(directory))
            self.assertEqual(second["new_contracts"], 0)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        self.assertEqual(Contract.objects.filter(status="active").count(), 77)
        self.assertEqual(Contract.objects.values("room_id").distinct().count(), 77)
        self.assertEqual(Contract.objects.values("representative_id").distinct().count(), 77)
        self.assertEqual(list(Contract.objects.filter(pk__in=[c.pk for c in self.existing]).order_by("pk").values()), before)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Room.objects.filter(status="occupied").count(), 77)
        self.assertEqual(Room.objects.filter(status="available").count(), 46)
        self.assertEqual(Room.objects.filter(status="maintenance").count(), 1)
        self.assertEqual(Room.objects.filter(status="reserved").count(), 1)
        for contract in Contract.objects.exclude(pk__in=[c.pk for c in self.existing]).select_related("room", "representative"):
            self.assertNotIn("MAU", contract.code)
            self.assertEqual(contract.notes, "")
            self.assertEqual(contract.start_date, date(2026, 11, 18))
            self.assertEqual(contract.end_date, date(2027, 11, 18))
            self.assertEqual(contract.monthly_rent, contract.room.monthly_rent)
            self.assertEqual(contract.deposit_amount, contract.room.deposit_amount)
            self.assertEqual(contract.representative.owner_id, self.owner.pk)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["available_count"], 46)
        self.assertEqual(len(page.context["building_groups"]), 5)

    def test_other_owner_and_inactive_tenants_are_never_allocated(self):
        other = get_user_model().objects.create_user("other-allocation", role="owner")
        Tenant.objects.create(owner=other, full_name="Other owner tenant")
        Tenant.objects.create(owner=self.owner, full_name="Inactive tenant", is_active=False)
        self.assertEqual(self.run_command()["new_contracts"], 74)

    def test_unowned_tenants_require_explicit_inclusion(self):
        self.assertEqual(self.run_command(include_unowned=False)["new_contracts"], 68)

    def test_active_members_and_draft_representatives_are_not_assigned_again(self):
        ContractMember.objects.create(contract=self.existing[0], tenant=self.tenants[3], joined_date=date(2026, 2, 1))
        Contract.objects.create(code="DRAFT", room=self.rooms[2], representative=self.tenants[4],
                                start_date=date(2026, 11, 18), end_date=date(2027, 11, 18), monthly_rent=3000000, status="draft")
        self.assertEqual(self.run_command()["new_contracts"], 72)

    def test_room_with_existing_active_contract_is_not_reused_even_if_status_is_wrong(self):
        Room.objects.filter(pk=self.existing[0].room_id).update(status="available")
        report = self.run_command()
        an = next(row for row in report["buildings"] if row["building_id"] == str(self.buildings[0].pk))
        self.assertNotIn(self.existing[0].room.number, an["available_rooms"])

    def test_insufficient_capacity_aborts_without_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(CommandError):
            self.run_command(apply=True, min_vacant=24, backup_dir=Path(directory))
        self.assertEqual(Contract.objects.count(), 3)
        self.assertEqual(Room.objects.filter(status="occupied").count(), 3)

    def test_activation_failure_rolls_back_whole_batch(self):
        def fail_after_writes(*args, **kwargs):
            apply_contract_batch(*args, **kwargs)
            # Fail after contracts, rooms and tenant owners have all changed.
            self.assertEqual(Contract.objects.count(), 77)
            self.assertEqual(Room.objects.filter(status="occupied").count(), 77)
            self.assertFalse(Tenant.objects.filter(owner__isnull=True).exists())
            raise RuntimeError("Simulated write failure")

        owners_before = list(Tenant.objects.order_by("pk").values_list("id", "owner_id"))
        with tempfile.TemporaryDirectory() as directory:
            with patch("apps.rentals.management.commands.allocate_demo_contracts.apply_contract_batch", side_effect=fail_after_writes):
                with self.assertRaisesRegex(RuntimeError, "Simulated write failure"):
                    self.run_command(apply=True, backup_dir=Path(directory))
            backup = json.loads(next(Path(directory).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(backup["state"], "prepared")
        self.assertEqual(Contract.objects.count(), 3)
        self.assertEqual(Room.objects.filter(status="occupied").count(), 3)
        self.assertEqual(list(Tenant.objects.order_by("pk").values_list("id", "owner_id")), owners_before)

    def test_invalid_period_is_rejected(self):
        with self.assertRaises(CommandError):
            self.run_command(end_date=date(2026, 11, 17))

    def test_no_buildings_is_rejected(self):
        other = get_user_model().objects.create_user("no-buildings", role="owner")
        with self.assertRaises(CommandError):
            self.run_command(owner_id=other.pk)
