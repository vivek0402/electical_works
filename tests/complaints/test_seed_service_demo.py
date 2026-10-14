import io
import json
from datetime import date
from pathlib import Path
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db.models import Max, Sum
from django.utils import timezone

from apps.complaints.management.commands import seed_service_demo
from apps.complaints.models import Complaint, Site, Status, Technician, Visit
from apps.defectives import selectors
from apps.defectives.models import BatchLine, DefectivePiece, PieceStatus, ReturnBatch
from apps.inventory.models import Item, StockBalance, StockEntry
from apps.inventory.services import balance_drift
from tests.factories import make_item

pytestmark = pytest.mark.django_db
DEMO = Path(__file__).resolve().parents[2] / "apps" / "complaints" / "demo" / "service-demo.json"


def demo():
    return json.loads(DEMO.read_text(encoding="utf-8"))


def seed(**kwargs):
    call_command("seed_service_demo", force=True, stdout=kwargs.pop("stdout", io.StringIO()), **kwargs)


def test_seed_loads_the_whole_demo(admin_user, office_user):
    """One seed, every read-only check (a full replay takes a few seconds, so it runs once here)."""
    out = io.StringIO()
    seed(stdout=out)
    db = demo()

    # Everything loaded, and the ledger and its cache agree.
    assert set(StockEntry.objects.values_list("number", flat=True)) == {e["no"] for e in db["entries"]}
    assert Complaint.objects.count() == len(db["complaints"]) and Visit.objects.count() == len(db["visits"])
    assert DefectivePiece.objects.count() == len(db["pieces"])
    assert ReturnBatch.objects.count() == len(db["batches"])
    assert Site.objects.count() == len(db["sites"]) and Technician.objects.count() == len(db["techs"])
    assert f"{len(db['complaints'])} complaints" in out.getvalue() and balance_drift() == []

    # The demo's numbers and links.
    for v in db["visits"]:
        visit = Visit.objects.select_related("out_entry", "collect_entry", "complaint").get(number=v["no"])
        assert visit.complaint.number == v["complaint"]
        assert getattr(visit.out_entry, "number", None) == v["outEntry"]
        assert getattr(visit.collect_entry, "number", None) == v["collectEntry"]
        assert sorted(visit.pieces.values_list("tag", flat=True)) == sorted(v["tags"])
    for b in db["batches"]:
        batch = ReturnBatch.objects.get(number=b["no"])
        assert getattr(batch.dispatch_entry, "number", None) == b["dispatchEntry"]
        lines = {
            ln.piece.tag: ln for ln in BatchLine.objects.filter(batch=batch).select_related("piece", "entry")
        }
        assert set(lines) == {ln["tag"] for ln in b["lines"]}
        for ln in b["lines"]:
            assert lines[ln["tag"]].outcome == (ln["outcome"] or "")
            assert getattr(lines[ln["tag"]].entry, "number", None) == ln["entry"]

    # RB-0001's two Replaced pieces were answered together: one replacement entry for both.
    replaced = BatchLine.objects.filter(batch__number="RB-0001", outcome="REPLACED").select_related("entry")
    assert len(replaced) == 2 and len({ln.entry.number for ln in replaced}) == 1
    assert replaced[0].entry.lines.get().qty == 2

    # The demo story.
    assert {c.number: c.status for c in Complaint.objects.all()} == {
        c["no"]: c["status"] for c in db["complaints"]
    }
    assert {p.tag: p.status for p in DefectivePiece.objects.all()} == {
        p["tag"]: p["status"] for p in db["pieces"]
    }
    assert Complaint.objects.filter(status=Status.NOT_COVERED).exists()
    assert Complaint.objects.filter(status=Status.AWAITING_MATERIAL).exists()
    labels = {
        b.number: selectors.batch_label(b, b.n_lines, b.n_settled) for b in selectors.batches_with_counts()
    }
    assert labels == {"RB-0001": "Partly settled", "RB-0002": "Dispatched", "RB-0003": "Draft"}
    in_store = DefectivePiece.objects.filter(status__in=[PieceStatus.IN_STORE, PieceStatus.IN_BATCH]).count()
    store_qty = StockBalance.objects.filter(location__is_defective_store=True).aggregate(t=Sum("qty"))["t"]
    assert store_qty == in_store
    # order_by() drops Meta.ordering, which would otherwise join the DISTINCT and count every complaint
    assert Complaint.objects.order_by().values("company").distinct().count() >= 3  # several companies

    # Shifted so the demo's "today" is today, never in the future.
    shift = timezone.localdate() - date.fromisoformat(db["today"])
    newest = max(date.fromisoformat(c["reportedOn"]) for c in db["complaints"])
    assert Complaint.objects.aggregate(m=Max("reported_on"))["m"] == newest + shift
    assert StockEntry.objects.aggregate(m=Max("entry_date"))["m"] <= timezone.localdate()

    # A second run is refused.
    with pytest.raises(CommandError, match="only for an empty system"):
        seed()


def test_seed_replays_a_reopen_and_a_rejected_scrapped_answer(admin_user, office_user):
    """Two paths the demo file doesn't use: an Admin reopen and a "rejected (scrapped)" answer."""
    db = demo()
    db["complaintEvents"].append(
        {
            "complaint": "CMP-0001",
            "from": "CLOSED",
            "to": "ATTENDED",
            "at": "2026-10-01",
            "by": "Office",
            "note": "Customer called again",
        }
    )
    next(c for c in db["complaints"] if c["no"] == "CMP-0001")["status"] = "ATTENDED"
    rb2 = next(b for b in db["batches"] if b["no"] == "RB-0002")
    next(ln for ln in rb2["lines"] if ln["tag"] == "DEF-0020").update(
        outcome="REJECTED_SCRAPPED", settledOn="2026-10-08"
    )
    next(p for p in db["pieces"] if p["tag"] == "DEF-0020")["status"] = "SETTLED"
    with mock.patch.object(seed_service_demo, "load_demo", return_value=db):
        seed()
    reopened = Complaint.objects.get(number="CMP-0001")
    last = reopened.events.order_by("-id").first()
    assert reopened.status == Status.ATTENDED and last.by == admin_user
    assert "Customer called again" in last.note
    answer = BatchLine.objects.get(batch__number="RB-0002", piece__tag="DEF-0020")
    assert answer.outcome == "REJECTED_SCRAPPED" and answer.entry is None
    assert DefectivePiece.objects.get(tag="DEF-0020").status == PieceStatus.SETTLED
    assert balance_drift() == []


def test_seed_refuses_missing_demo_pieces(admin_user, office_user):
    db = demo()
    next(b for b in db["batches"] if b["no"] == "RB-0003")["lines"].append(
        {"tag": "DEF-9999", "outcome": None, "settledOn": None, "toLoc": None, "entry": None}
    )
    with (
        mock.patch.object(seed_service_demo, "load_demo", return_value=db),
        pytest.raises(CommandError, match="Replaying batch RB-0003: Demo pieces missing: DEF-9999"),
    ):
        seed()
    assert not Complaint.objects.exists()


def test_seed_refuses_a_system_with_items(admin_user, office_user):
    """Demo items must not mix with a real item master."""
    make_item("REAL-ITEM-1")
    with pytest.raises(CommandError, match="already has items"):
        seed()
    assert not Site.objects.exists()


def test_seed_names_a_failing_item_load(admin_user, office_user):
    with (
        mock.patch.object(seed_service_demo, "load_masters_and_items", side_effect=ValueError("bad item")),
        pytest.raises(CommandError, match="Replaying the demo items and masters: bad item"),
    ):
        seed()


def test_seed_refuses_after_the_stock_demo(admin_user, office_user):
    """The service demo brings its own stock history; on top of another ledger its numbers can't match."""
    call_command("seed_stock_demo", force=True, stdout=io.StringIO())
    with pytest.raises(CommandError, match="instead of seed_stock_demo"):
        seed()
    assert not Complaint.objects.exists() and not DefectivePiece.objects.exists()


def test_seed_needs_force_without_debug(settings, admin_user, office_user):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="Pass --force"):
        call_command("seed_service_demo", stdout=io.StringIO())
    assert not StockEntry.objects.exists()


def test_seed_rolls_back_everything_on_failure(admin_user, office_user):
    real = seed_service_demo.complaints.record_visit
    calls = []

    def fail_on_fifth(**kwargs):
        calls.append(1)
        if len(calls) == 5:
            raise RuntimeError("boom")
        return real(**kwargs)

    with (
        mock.patch.object(seed_service_demo.complaints, "record_visit", side_effect=fail_on_fifth),
        pytest.raises(CommandError, match=r"Replaying visit VIS-\d{4}: boom"),
    ):
        seed()
    assert not Item.objects.exists() and not StockEntry.objects.exists() and not Complaint.objects.exists()


def test_seed_names_a_number_that_diverged(admin_user, office_user):
    """If the replay ever numbers something differently from the demo file, it stops and says which."""
    db = demo()
    db["complaints"][0]["no"] = "CMP-0099"  # the first complaint filed comes out as CMP-0001
    with (
        mock.patch.object(seed_service_demo, "load_demo", return_value=db),
        pytest.raises(CommandError, match="Demo complaint CMP-0099 was numbered CMP-0001"),
    ):
        seed()
    assert not Complaint.objects.exists()
