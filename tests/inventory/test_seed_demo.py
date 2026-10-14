import io
import json
from pathlib import Path
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db.models import Max
from django.utils import timezone

from apps.inventory.management.commands import seed_stock_demo
from apps.inventory.models import Item, StockEntry
from apps.inventory.services import balance_drift
from tests.factories import make_item

pytestmark = pytest.mark.django_db

DEMO = Path(__file__).resolve().parents[2] / "apps" / "inventory" / "demo" / "demo-data.json"


def seed(**kwargs):
    call_command("seed_stock_demo", force=True, stdout=kwargs.pop("stdout", io.StringIO()), **kwargs)


def test_seed_demo_loads_items_and_history(admin_user, office_user):
    out = io.StringIO()
    seed(stdout=out)
    assert Item.objects.count() == 28 and StockEntry.objects.count() == 35
    assert StockEntry.objects.filter(kind="REV").exists() and balance_drift() == []
    assert "28 items, 35 entries" in out.getvalue()


def test_seed_demo_keeps_the_demo_entry_numbers(admin_user, office_user):
    seed()
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    posted = {e.number: e for e in StockEntry.objects.all()}
    assert set(posted) == {e["no"] for e in demo["entries"]}
    for e in demo["entries"]:
        assert posted[e["no"]].kind == e["kind"]
        if e["kind"] != "REV":
            assert (posted[e["no"]].party, posted[e["no"]].ref) == (e.get("party", ""), e.get("ref", ""))
    rev = StockEntry.objects.get(number="REV-0001")
    assert rev.reverses.number == "OUT-0018"


def test_seed_demo_dates_are_never_in_the_future(admin_user, office_user):
    seed()
    newest = StockEntry.objects.aggregate(newest=Max("entry_date"))["newest"]
    assert newest is not None and newest <= timezone.localdate()


def test_seed_demo_refuses_second_run(admin_user, office_user):
    seed()
    with pytest.raises(CommandError, match="already has stock entries"):
        seed()


def test_seed_demo_refuses_without_force_when_debug_is_off(settings, admin_user, office_user):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="Pass --force to load it anyway"):
        call_command("seed_stock_demo", stdout=io.StringIO())
    assert StockEntry.objects.count() == 0


def test_seed_demo_runs_without_force_when_debug_is_on(settings, admin_user, office_user):
    settings.DEBUG = True
    call_command("seed_stock_demo", stdout=io.StringIO())
    assert StockEntry.objects.count() == 35


def test_seed_demo_refuses_a_system_with_items(admin_user, office_user):
    """Demo items must not mix with a real item master."""
    make_item("REAL-ITEM-1")
    with pytest.raises(CommandError, match="already has items"):
        seed()
    assert StockEntry.objects.count() == 0 and Item.objects.count() == 1


def test_seed_demo_needs_users(db):
    with pytest.raises(CommandError, match="Run `manage.py seed_users` first"):
        seed()
    assert Item.objects.count() == 0


def test_seed_demo_rolls_back_everything_on_failure(admin_user, office_user):
    real = seed_stock_demo.post_entry
    calls = []

    def fail_on_tenth(**kwargs):
        calls.append(1)
        if len(calls) == 10:
            raise RuntimeError("boom")
        return real(**kwargs)

    with (
        mock.patch.object(seed_stock_demo, "post_entry", side_effect=fail_on_tenth),
        pytest.raises(RuntimeError, match="boom"),
    ):
        seed()
    assert Item.objects.count() == 0 and StockEntry.objects.count() == 0
