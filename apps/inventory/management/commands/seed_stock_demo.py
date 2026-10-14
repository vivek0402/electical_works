"""Load the approved demo items and ~5 weeks of stock history.

Dates are shifted so the demo's "today" is today.
"""

import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import ADMIN, OFFICE
from apps.inventory.models import (
    AdjustReason,
    Company,
    EntryKind,
    FittingType,
    InSource,
    Location,
    SpareType,
    StockEntry,
)
from apps.inventory.services import Line, post_entry, save_item, undo_entry

DEMO = Path(__file__).resolve().parents[2] / "demo" / "demo-data.json"
REASONS = {label: value for value, label in AdjustReason.choices}


def _user(role):
    users = get_user_model().objects.order_by("id")
    found = users.filter(groups__name=role).first()
    if found is None and role == ADMIN:
        found = users.filter(is_superuser=True).first()
    if found is None:
        raise CommandError(f"No {role} user. Run `manage.py seed_users` first.")
    return found


def _masters(model, names):
    """{name: row}, creating any that are missing (names are unique regardless of case)."""
    rows = {}
    for name in names:
        rows[name] = model.objects.filter(name__iexact=name).first() or model.objects.create(name=name)
    return rows


def load_masters_and_items(db):
    """(places, companies, items) from a demo file: masters created if missing, items saved through save_item.

    Shared by seed_stock_demo and seed_service_demo. `items` is {code: Item}.
    """
    places = _masters(Location, db["locations"])
    spare_types = _masters(SpareType, db["spareTypes"])
    fitting_types = _masters(FittingType, db["fittingTypes"])
    companies = _masters(Company, db["companies"])
    items = {}
    for d in db["items"]:
        items[d["code"]] = save_item(
            data={
                "code": d["code"],
                "spare_type": spare_types[d["type"]],
                "company": companies[d["company"]],
                "description": d["desc"],
                "cat_ref": d["catRef"],
                "fitting_type": fitting_types[d["fittingType"]] if d["fittingType"] else None,
                "wattage_w": d["watt"],
                "current_ma": d["ma"],
                "unit": d["unit"],
                "reorder_level": d["reorder"],
                "aliases": d["aliases"],
                "is_active": d["active"],
            }
        )
    return places, companies, items


class Command(BaseCommand):
    help = "Load demo items and stock history (only into an empty ledger, and only with DEBUG or --force)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Load demo data even when DEBUG is off.")

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Demo data is for development. Pass --force to load it anyway.")
        if StockEntry.objects.exists():
            raise CommandError(
                "The database already has stock entries. Demo data is only for an empty system."
            )
        db = json.loads(DEMO.read_text(encoding="utf-8"))
        users = {"Admin": _user(ADMIN), "Office": _user(OFFICE)}
        shift = timezone.localdate() - date.fromisoformat(db["today"])
        places, companies, items = load_masters_and_items(db)

        # Post in the file's order: that is the order the entries were made in the demo, so every
        # entry gets the same number as in the file (late corrections like OUT-0018 are back-dated).
        posted = {}
        for e in db["entries"]:
            when, user = date.fromisoformat(e["date"]) + shift, users[e["by"]]
            if e["kind"] == EntryKind.REV:
                if e["reverses"] not in posted:
                    raise CommandError(f"{e['no']} comes before {e['reverses']}, the entry it undoes.")
                entry = undo_entry(entry=posted[e["reverses"]], reason=e["note"], user=user, entry_date=when)
            else:
                # PKD in the demo file is "MM-YYYY" (packed month); it is stored as the 1st of that month.
                lines = [
                    Line(
                        items[ln["code"]],
                        places[ln["loc"]],
                        ln["qty"],
                        ln.get("batch", ""),
                        date(int(ln["pkd"][3:]), int(ln["pkd"][:2]), 1) if ln.get("pkd") else None,
                    )
                    for ln in e["lines"]
                ]
                subtype = e.get("subtype", "")
                entry = post_entry(
                    kind=e["kind"],
                    entry_date=when,
                    lines=lines,
                    user=user,
                    subtype=subtype,
                    party=e.get("party", ""),
                    company=companies[e["party"]] if subtype == InSource.SUPPLIER else None,
                    ref=e.get("ref", ""),
                    reason=REASONS[e["reason"]] if e["kind"] == EntryKind.ADJ else "",
                    note=e.get("note", ""),
                )
            if entry.number != e["no"]:
                raise CommandError(f"Demo entry {e['no']} was numbered {entry.number}. Is the ledger empty?")
            posted[e["no"]] = entry
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(items)} items, {len(posted)} entries."))
