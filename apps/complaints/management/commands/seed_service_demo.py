"""Load the approved service demo (apps/complaints/demo/service-demo.json, a copy of the mockup's
mockups/service/demo-data.json): items, the shared stock ledger, sites, technicians, complaints with visits,
defective pieces and return batches, across several companies.

Everything is replayed through the real services in the order the demo happened, so entries, pieces, events
and numbers are what the app itself records. Dates are shifted so the demo's "today" is today. Within one day:
complaints are filed first; then every action that posts to the ledger, in ledger order (plain stock entries,
visits, mark defective, scrap, dispatch, settlement); then status changes and visits that posted nothing;
then new return batches and "rejected (scrapped)" answers, which post nothing either. Sites and technicians
the demo hides are hidden last (the services refuse hidden ones for new complaints and visits).

The demo brings its own stock history, so it loads into an empty system instead of seed_stock_demo.

The app copy differs from the mockup's file in one place: the mockup answered RB-0001's two Replaced pieces
with one entry each, while the real settle posts one entry per call and the replay settles each
(batch, outcome, date, location) group with one call. The copy has those two merged into IN-0024 and the later
IN numbers moved down by one.
"""

import json
from datetime import date
from functools import partial
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.roles import ADMIN, OFFICE
from apps.complaints import services as complaints
from apps.complaints.models import Complaint, NotCoveredReason, Priority, Site, Status, Technician
from apps.defectives import services as defectives
from apps.defectives.models import DefectivePiece, Outcome, ReturnBatch, ScrapReason
from apps.inventory.management.commands.seed_stock_demo import REASONS, _user, load_masters_and_items
from apps.inventory.models import EntryKind, InSource, ServiceSubtype, StockEntry
from apps.inventory.services import Line, post_entry, undo_entry

DEMO = Path(__file__).resolve().parents[2] / "demo" / "service-demo.json"
REASON_VALUES = {label: value for value, label in NotCoveredReason.choices}
PRIORITY_VALUES = {label: value for value, label in Priority.choices}
SETTLEMENT_SUBTYPES = (ServiceSubtype.REPLACEMENT, ServiceSubtype.DEFECTIVE_RETURNED)  # answers that post


def load_demo():
    return json.loads(DEMO.read_text(encoding="utf-8"))


def _month(text):
    """'2026-03' -> date(2026, 3, 1); '' -> None."""
    return date(int(text[:4]), int(text[5:7]), 1) if text else None


class Replay:
    def __init__(self, db, users):
        self.db, self.users = db, users
        self.shift = timezone.localdate() - date.fromisoformat(db["today"])
        self.places, self.companies, self.items = load_masters_and_items(db)
        self.by_no = {e["no"]: e for e in db["entries"]}
        self.demo_pieces = {p["tag"]: p for p in db["pieces"]}
        self.sites, self.techs, self.complaints, self.batches, self.entries = {}, {}, {}, {}, {}

    def day(self, iso):
        return date.fromisoformat(iso) + self.shift

    def check(self, posted, demo_no):
        if posted.number != demo_no:
            raise CommandError(f"Demo entry {demo_no} was numbered {posted.number}. Is the ledger empty?")
        self.entries[demo_no] = posted

    def load_people(self):
        for s in self.db["sites"]:
            self.sites[s["id"]] = complaints.save_site(
                data={
                    "name": s["name"],
                    "city": s["city"],
                    "contact_name": s["contact"],
                    "phone": s["phone"],
                    "address": s["address"],
                }
            )
        for t in self.db["techs"]:
            self.techs[t["name"]] = complaints.save_technician(name=t["name"], phone=t["phone"])

    def hide_people(self):
        """Hide what the demo hides, last of all: hidden sites and technicians can't take new work."""
        for s in self.db["sites"]:
            if not s.get("active", True):
                complaints.set_active(self.sites[s["id"]], active=False)
        for t in self.db["techs"]:
            if not t.get("active", True):
                complaints.set_active(self.techs[t["name"]], active=False)

    def actions(self):
        """Every demo action as (date, phase, kind, order, callable), in the order the demo made them."""
        db = self.db
        index = {e["no"]: n for n, e in enumerate(db["entries"])}
        in_visits = {no for v in db["visits"] for no in (v["outEntry"], v["collectEntry"]) if no}
        acts = [(c["reportedOn"], 0, 0, n, partial(self.file, c)) for n, c in enumerate(db["complaints"])]
        for n, v in enumerate(db["visits"]):
            posted = [index[no] for no in (v["outEntry"], v["collectEntry"]) if no]
            if posted:
                acts.append((v["date"], 1, 0, min(posted), partial(self.visit, v)))
            else:
                acts.append((v["date"], 2, 1, n, partial(self.visit, v)))
        for e in db["entries"]:
            if e["no"] not in in_visits:
                acts.append((e["date"], 1, 0, index[e["no"]], partial(self.entry, e)))
        for n, ev in enumerate(db["complaintEvents"]):
            if ev["from"] is not None and not ev["note"].startswith("Visit VIS-"):
                acts.append((ev["at"], 2, 0, n, partial(self.status, ev)))
        for n, b in enumerate(db["batches"]):
            acts.append((b["createdOn"], 3, 0, n, partial(self.create_batch, b)))
            for (outcome, settled_on, _), lines in self.groups(b).items():
                if outcome == Outcome.REJECTED_SCRAPPED:  # posts nothing, so it has no place in the ledger
                    acts.append((settled_on, 3, 1, n, partial(self.settle, b, lines, self.users["Office"])))
        return sorted(acts, key=lambda a: a[:4])

    @staticmethod
    def groups(b):
        """A batch's answered lines grouped by (outcome, date, location): one settle call each."""
        found = {}
        for line in b["lines"]:
            if line["outcome"]:
                found.setdefault((line["outcome"], line["settledOn"], line["toLoc"]), []).append(line)
        return found

    # ---------------------------------------------------------------- complaints

    def file(self, c):
        made = complaints.file_complaint(
            site=self.sites[c["site"]],
            company=self.companies[c["company"]],
            fault=c["fault"],
            reported_on=self.day(c["reportedOn"]),
            user=self.users["Office"],
            company_ref=c["companyRef"],
            qty_affected=c["qty"],
            priority=PRIORITY_VALUES[c["priority"]],
            technicians=[self.techs[t] for t in c["techs"]],
            contact_name=c["contact"],
            phone=c["phone"],
        )
        if made.number != c["no"]:
            raise CommandError(f"Demo complaint {c['no']} was numbered {made.number}.")
        self.complaints[c["no"]] = made

    def status(self, ev):
        complaint, at = self.complaints[ev["complaint"]], self.day(ev["at"])
        if ev["from"] == Status.CLOSED and ev["to"] == Status.ATTENDED:  # a reopen: Admin only
            complaints.reopen(complaint=complaint, user=self.users["Admin"], note=ev["note"], at=at)
            return
        complaints.change_status(
            complaint=complaint,
            to=ev["to"],
            user=self.users[ev["by"]],
            note=ev["note"],
            reason=REASON_VALUES.get(ev.get("reason", ""), ""),
            at=at,
        )

    def visit(self, v):
        out = self.by_no[v["outEntry"]] if v["outEntry"] else None
        col = self.by_no[v["collectEntry"]] if v["collectEntry"] else None
        parts = [(self.items[ln["code"]], -ln["qty"]) for ln in out["lines"]] if out else []
        collected, tags = [], list(v["tags"])
        for ln in col["lines"] if col else []:
            fault = self.demo_pieces[tags[0]]["fault"]
            tags = tags[ln["qty"] :]
            collected.append(
                (self.items[ln["code"]], ln["qty"], ln.get("batch", ""), _month(ln.get("pkd", "")), fault)
            )
        made = complaints.record_visit(
            complaint=self.complaints[v["complaint"]],
            visit_date=self.day(v["date"]),
            technicians=[self.techs[t] for t in v["techs"]],
            work_done=v["work"],
            next_status=v["nextStatus"],
            user=self.users["Office"],
            location=self.places[out["lines"][0]["loc"]] if out else None,
            parts=parts,
            collected=collected,
        )
        if made.number != v["no"]:
            raise CommandError(f"Demo visit {v['no']} was numbered {made.number}.")
        if out:
            self.check(made.out_entry, out["no"])
        if col:
            self.check(made.collect_entry, col["no"])
        tagged = sorted(made.pieces.values_list("tag", flat=True))
        if tagged != sorted(v["tags"]):
            raise CommandError(
                f"Demo visit {v['no']} tagged {', '.join(tagged) or 'nothing'}; the demo says "
                f"{', '.join(v['tags']) or 'nothing'}."
            )

    # ---------------------------------------------------------------- ledger entries outside visits

    def entry(self, e):
        user, when, store = self.users[e["by"]], self.day(e["date"]), self.db["defStore"]
        if e["kind"] == EntryKind.TRF and e.get("party") == store:
            good = next(ln for ln in e["lines"] if ln["qty"] < 0)
            fault = e["note"].split(": ", 1)[1] if ": " in e["note"] else e["note"]
            posted, pieces = defectives.mark_defective(
                location=self.places[good["loc"]],
                lines=[(self.items[good["code"]], -good["qty"], fault)],
                entry_date=when,
                user=user,
            )
            # A demo piece's "entry" is its latest entry (a scrap overwrites it), so match on how it arrived.
            demo_tags = sorted(
                p["tag"]
                for p in self.db["pieces"]
                if (p["source"], p["code"], p["collectedOn"]) == ("FOUND_IN_STOCK", good["code"], e["date"])
            )
            if sorted(p.tag for p in pieces) != demo_tags:
                raise CommandError(
                    f"Demo entry {e['no']} tagged {', '.join(p.tag for p in pieces)}; "
                    f"the demo says {', '.join(demo_tags)}."
                )
        elif e["kind"] == EntryKind.ADJ and all(ln["loc"] == store for ln in e["lines"]):
            head, why = e["note"].split(": ", 1)
            tags = head.removeprefix("Scrapped ").split(", ")
            posted = defectives.scrap(
                pieces=list(DefectivePiece.objects.filter(tag__in=tags)),
                reason=ScrapReason.NOT_WORTH,
                note=why,
                user=user,
                entry_date=when,
            )
        elif e.get("subtype") == ServiceSubtype.RETURN_TO_COMPANY:
            b = next(b for b in self.db["batches"] if b["dispatchEntry"] == e["no"])
            posted = defectives.dispatch(
                batch=self.batches[b["no"]],
                dispatched_on=when,
                courier=b["courier"],
                docket_no=b["docket"],
                user=user,
            )
        elif e.get("subtype") in SETTLEMENT_SUBTYPES:
            b = next(b for b in self.db["batches"] if any(ln["entry"] == e["no"] for ln in b["lines"]))
            [posted] = self.settle(b, [ln for ln in b["lines"] if ln["entry"] == e["no"]], user)
        elif e["kind"] == EntryKind.REV:
            posted = undo_entry(
                entry=self.entries[e["reverses"]], reason=e["note"], user=user, entry_date=when
            )
        else:
            subtype = e.get("subtype") or ""
            posted = post_entry(
                kind=e["kind"],
                entry_date=when,
                lines=[
                    Line(
                        self.items[ln["code"]],
                        self.places[ln["loc"]],
                        ln["qty"],
                        ln.get("batch", ""),
                        _month(ln.get("pkd", "")),
                    )
                    for ln in e["lines"]
                ],
                user=user,
                subtype=subtype,
                party=e.get("party", ""),
                company=self.companies.get(e.get("party")) if subtype == InSource.SUPPLIER else None,
                ref=e.get("ref", ""),
                reason=REASONS[e["reason"]] if e["kind"] == EntryKind.ADJ else "",
                note=e.get("note", ""),
            )
        self.check(posted, e["no"])

    # ---------------------------------------------------------------- return batches

    def create_batch(self, b):
        made = defectives.create_batch(
            company=self.companies[b["company"]],
            user=self.users["Office"],
            pieces=list(DefectivePiece.objects.filter(tag__in=[ln["tag"] for ln in b["lines"]])),
            note=b["note"],
            created_on=self.day(b["createdOn"]),
        )
        if made.number != b["no"]:
            raise CommandError(f"Demo batch {b['no']} was numbered {made.number}.")
        self.batches[b["no"]] = made

    def settle(self, b, lines, user):
        """One settle call (at most one entry) for lines of one batch with one outcome, date and place."""
        [(outcome, settled_on, to_loc)] = {(ln["outcome"], ln["settledOn"], ln["toLoc"]) for ln in lines}
        return defectives.settle(
            batch=self.batches[b["no"]],
            pieces=list(DefectivePiece.objects.filter(tag__in=[ln["tag"] for ln in lines])),
            outcome=outcome,
            settled_on=self.day(settled_on),
            to_location=self.places[to_loc] if to_loc else None,
            user=user,
        )

    def verify(self):
        """The replay must end exactly where the demo ended."""
        for c in self.db["complaints"]:
            status = Complaint.objects.get(number=c["no"]).status
            if status != c["status"]:
                raise CommandError(f"{c['no']} ended {status}; the demo says {c['status']}.")
        for p in self.db["pieces"]:
            piece = DefectivePiece.objects.select_related("item").get(tag=p["tag"])
            if (piece.status, piece.item.code) != (p["status"], p["code"]):
                raise CommandError(
                    f"{p['tag']} ended {piece.status} ({piece.item.code}); "
                    f"the demo says {p['status']} ({p['code']})."
                )
        posted, expected = StockEntry.objects.count(), len(self.db["entries"])
        if posted != expected:
            raise CommandError(f"The replay posted {posted} entries; the demo has {expected}.")


class Command(BaseCommand):
    help = (
        "Load the service demo: stock history, complaints, visits, defective pieces and return batches "
        "(empty system only, instead of seed_stock_demo, and only with DEBUG or --force)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Load demo data even when DEBUG is off.")

    @transaction.atomic
    def handle(self, *args, force=False, **options):
        if not settings.DEBUG and not force:
            raise CommandError("Demo data is for development. Pass --force to load it anyway.")
        if Complaint.objects.exists() or DefectivePiece.objects.exists() or ReturnBatch.objects.exists():
            raise CommandError(
                "The database already has complaints or defective pieces. "
                "Demo data is only for an empty system."
            )
        if Site.objects.exists() or Technician.objects.exists():
            raise CommandError(
                "The database already has sites or technicians. Demo data is only for an empty system."
            )
        if StockEntry.objects.exists():
            raise CommandError(
                "The database already has stock entries. The service demo brings its own stock history, so "
                "load it into an empty ledger instead of seed_stock_demo. "
                "Demo data is only for an empty system."
            )
        db = load_demo()
        replay = Replay(db, {"Admin": _user(ADMIN), "Office": _user(OFFICE)})
        replay.load_people()
        for *_, action in replay.actions():
            action()
        replay.hide_people()
        replay.verify()
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(db['items'])} items, {len(db['entries'])} entries, {len(db['sites'])} sites, "
                f"{len(db['techs'])} technicians, {len(db['complaints'])} complaints, "
                f"{len(db['visits'])} visits, {len(db['pieces'])} defective pieces, "
                f"{len(db['batches'])} return batches."
            )
        )
