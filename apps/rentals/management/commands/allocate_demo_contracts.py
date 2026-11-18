"""Allocate explicitly requested tenancies without resetting existing data.

Dry-run by default. An apply follows the contract activation rules in one batch,
with an atomic transaction and a local audit snapshot; no invoices are generated.
"""
import json
import random
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.rentals.models import Building, Contract, ContractMember, Invoice, Room, Tenant


def allocation_plan(owner_id, start_date, end_date, minimum, seed, include_unowned=False, lock=False):
    if start_date >= end_date:
        raise CommandError("The end date must be after the start date.")
    if minimum < 0:
        raise CommandError("The minimum vacancy must not be negative.")
    buildings_query = Building.objects.filter(owner_id=owner_id, is_active=True).order_by("pk")
    if lock:
        buildings_query = buildings_query.select_for_update()
    buildings = list(buildings_query)
    if not buildings:
        raise CommandError("No active buildings found for this owner.")
    rooms_query = Room.objects.filter(building__in=buildings).order_by("building_id", "pk")
    tenant_scope = Q(owner_id=owner_id)
    if include_unowned:
        tenant_scope |= Q(owner__isnull=True)
    tenants_query = Tenant.objects.filter(tenant_scope, is_active=True).order_by("pk")
    if lock:
        rooms_query = rooms_query.select_for_update()
        tenants_query = tenants_query.select_for_update()
    rooms, tenants = list(rooms_query), list(tenants_query)
    # Protect every existing active/draft commitment, even if its dates are
    # stale. Expiring or cancelling someone else's tenancy is never implicit.
    commitments = Contract.objects.filter(status__in=[Contract.Status.ACTIVE, Contract.Status.DRAFT])
    used_tenants = set(commitments.values_list("representative_id", flat=True))
    used_tenants.update(ContractMember.objects.filter(
        contract__in=commitments,
    ).filter(Q(left_date__isnull=True) | Q(left_date__gte=start_date)).values_list("tenant_id", flat=True))
    used_rooms = set(commitments.values_list("room_id", flat=True))
    candidates = [tenant for tenant in tenants if tenant.id not in used_tenants]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    pools, reserved = {}, {}
    occupied_counts = Counter(room.building_id for room in rooms if room.id in used_rooms or room.status == Room.Status.OCCUPIED)
    for building in buildings:
        available = [room for room in rooms if room.building_id == building.id and room.status == Room.Status.AVAILABLE and room.id not in used_rooms and room.max_occupants >= 1]
        if len(available) < minimum:
            raise CommandError(f"Building {building.id} has only {len(available)} eligible vacant rooms; preserving {minimum} is impossible without changing existing tenancies.")
        rng.shuffle(available)
        reserved[building.id] = available[:minimum]
        pools[building.id] = available[minimum:]
    if len(candidates) > sum(len(pool) for pool in pools.values()):
        raise CommandError("Not enough available rooms for one room per tenant while preserving the requested vacancy.")
    assignments = []
    for tenant in candidates:
        choices = [key for key, pool in pools.items() if pool]
        least_occupied = min(occupied_counts[key] for key in choices)
        key = rng.choice([key for key in choices if occupied_counts[key] == least_occupied])
        room = pools[key].pop()
        assignments.append((tenant, room))
        occupied_counts[key] += 1
    assigned_rooms = {room.id for _, room in assignments}
    summaries = []
    for building in buildings:
        building_rooms = [room for room in rooms if room.building_id == building.id]
        vacancies = [room for room in building_rooms if room.status == Room.Status.AVAILABLE and room.id not in used_rooms and room.id not in assigned_rooms]
        summaries.append({
            "building_id": str(building.id), "building": building.name, "rooms": len(building_rooms),
            "new_contracts": sum(room.building_id == building.id for _, room in assignments),
            "occupied_after": occupied_counts[building.id], "available_after": len(vacancies),
            "reserved_vacant_rooms": sorted(room.number for room in reserved[building.id]),
            "available_rooms": sorted(room.number for room in vacancies),
        })
    return {"assignments": assignments, "rooms": rooms, "tenants": tenants, "buildings": buildings,
            "report": {"owner_id": str(owner_id), "start_date": str(start_date), "end_date": str(end_date),
                       "seed": seed, "minimum_vacant_per_building": minimum, "new_contracts": len(assignments),
                       "already_assigned_tenants": sum(tenant.id in used_tenants for tenant in tenants), "buildings": summaries}}


def apply_contract_batch(records, owner_id, start_date, end_date):
    """Called only after planning with locked rooms/tenants, inside atomic().

    Match activate_contract's room/owner updates without per-row FK and
    constraint queries, which make a remote-database transaction too long.
    """
    room_ids = [record["room_id"] for record in records]
    tenant_ids = [record["representative_id"] for record in records]
    commitments = Contract.objects.filter(status__in=[Contract.Status.ACTIVE, Contract.Status.DRAFT])
    if commitments.filter(Q(room_id__in=room_ids) | Q(representative_id__in=tenant_ids)).exists():
        raise CommandError("A selected room or tenant already has a contract; rolling back.")
    if ContractMember.objects.filter(contract__in=commitments, tenant_id__in=tenant_ids).filter(
        Q(left_date__isnull=True) | Q(left_date__gte=start_date)
    ).exists():
        raise CommandError("A selected tenant already belongs to a contract; rolling back.")
    contracts = []
    for record in records:
        contract = Contract(
            **record, start_date=start_date, end_date=end_date,
            status=Contract.Status.ACTIVE, billing_day=1, due_day=5,
            notes="",
        )
        # Related rows were read and locked by allocation_plan. Validate scalar
        # fields locally; the database enforces FK/unique/check constraints.
        contract.clean_fields(exclude={"room", "representative"})
        if contract.monthly_rent < 0 or contract.deposit_amount < 0:
            raise CommandError("Rent and deposit must not be negative.")
        contracts.append(contract)
    Contract.objects.bulk_create(contracts, batch_size=100)
    updated = Room.objects.filter(pk__in=room_ids, status=Room.Status.AVAILABLE).update(status=Room.Status.OCCUPIED)
    if updated != len(records):
        raise CommandError("Selected room availability changed; rolling back.")
    Tenant.objects.filter(pk__in=tenant_ids, owner__isnull=True).update(owner_id=owner_id)


class Command(BaseCommand):
    help = "Plan or create contracts for unassigned tenants, preserving vacant rooms and existing contracts."

    def add_arguments(self, parser):
        parser.add_argument("--owner-id", type=uuid.UUID, required=True)
        parser.add_argument("--start-date", type=date.fromisoformat, required=True)
        parser.add_argument("--end-date", type=date.fromisoformat, required=True)
        parser.add_argument("--seed", required=True)
        parser.add_argument("--min-vacant", type=int, default=5)
        parser.add_argument("--include-unowned", action="store_true", help="Explicitly include tenants with no owner or active/draft tenancy.")
        parser.add_argument("--apply", action="store_true", help="Commit the allocation. Without this flag only report a plan.")
        parser.add_argument("--backup-dir", type=Path, default=Path(settings.BASE_DIR) / "tmp" / "contract-backups")

    def handle(self, *args, **options):
        backup_path = None
        with transaction.atomic():
            plan = allocation_plan(options["owner_id"], options["start_date"], options["end_date"],
                                   options["min_vacant"], options["seed"], options["include_unowned"], lock=options["apply"])
            report = plan["report"]
            report["applied"] = False
            if options["apply"] and plan["assignments"]:
                contracts_before = list(Contract.objects.filter(room__building__in=plan["buildings"]).order_by("pk").values())
                invoices_before = list(Invoice.objects.filter(contract__room__building__in=plan["buildings"]).order_by("pk").values())
                records = []
                for tenant, room in plan["assignments"]:
                    contract_id = uuid.uuid4()
                    records.append({"id": str(contract_id), "code": f"HD-{options['start_date']:%Y%m%d}-{contract_id.hex[:10].upper()}",
                                    "room_id": str(room.id), "representative_id": str(tenant.id),
                                    "monthly_rent": str(room.monthly_rent), "deposit_amount": str(room.deposit_amount)})
                snapshot = {
                    "state": "prepared", "prepared_at": timezone.now().isoformat(), "plan": report,
                    "new_contracts": records, "contracts_before": contracts_before, "invoices_before": invoices_before,
                    "rooms_before": [{"id": str(room.id), "status": room.status, "updated_at": room.updated_at} for _, room in plan["assignments"]],
                    "tenants_before": [{"id": str(tenant.id), "owner_id": str(tenant.owner_id) if tenant.owner_id else None, "updated_at": tenant.updated_at} for tenant, _ in plan["assignments"]],
                }
                directory = options["backup_dir"]
                directory.mkdir(parents=True, exist_ok=True)
                backup_path = directory / f"allocation-{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.json"
                # Save before the first database write. Excludes tenant names,
                # identity documents, contact details, users and credentials.
                with backup_path.open("x", encoding="utf-8") as output:
                    json.dump(snapshot, output, ensure_ascii=False, indent=2, default=str)
                apply_contract_batch(records, options["owner_id"], options["start_date"], options["end_date"])
                if list(Contract.objects.filter(id__in=[row["id"] for row in contracts_before]).order_by("pk").values()) != contracts_before:
                    raise CommandError("Existing contracts changed unexpectedly; rolling back.")
                if list(Invoice.objects.filter(contract__room__building__in=plan["buildings"]).order_by("pk").values()) != invoices_before:
                    raise CommandError("Invoices changed unexpectedly; rolling back.")
                for building in plan["buildings"]:
                    if Room.objects.filter(building=building, status=Room.Status.AVAILABLE).count() < options["min_vacant"]:
                        raise CommandError("Minimum vacancy was not preserved; rolling back.")
                report["applied"] = True
            elif options["apply"]:
                report["applied"] = True
        # Record completion only after the transaction actually committed.
        if backup_path:
            snapshot["state"] = "committed"
            snapshot["committed_at"] = timezone.now().isoformat()
            with backup_path.open("w", encoding="utf-8") as output:
                json.dump(snapshot, output, ensure_ascii=False, indent=2, default=str)
            report["backup"] = str(backup_path)
        self.stdout.write(json.dumps(report, ensure_ascii=True))
