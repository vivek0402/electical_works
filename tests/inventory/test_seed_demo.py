import io
import json
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.inventory.models import Item, StockEntry
from apps.inventory.services import balance_drift

pytestmark = pytest.mark.django_db

DEMO = Path(__file__).resolve().parents[2] / "apps" / "inventory" / "demo" / "demo-data.json"


def test_seed_demo_loads_items_and_history(admin_user, office_user):
    out = io.StringIO()
    call_command("seed_stock_demo", stdout=out)
    assert Item.objects.count() == 28 and StockEntry.objects.count() == 35
    assert StockEntry.objects.filter(kind="REV").exists() and balance_drift() == []
    assert "28 items, 35 entries" in out.getvalue()


def test_seed_demo_keeps_the_demo_entry_numbers(admin_user, office_user):
    call_command("seed_stock_demo", stdout=io.StringIO())
    demo = json.loads(DEMO.read_text(encoding="utf-8"))
    posted = {e.number: e for e in StockEntry.objects.all()}
    assert set(posted) == {e["no"] for e in demo["entries"]}
    for e in demo["entries"]:
        assert posted[e["no"]].kind == e["kind"]
        if e["kind"] != "REV":
            assert (posted[e["no"]].party, posted[e["no"]].ref) == (e.get("party", ""), e.get("ref", ""))
    rev = StockEntry.objects.get(number="REV-0001")
    assert rev.reverses.number == "OUT-0018"


def test_seed_demo_refuses_second_run(admin_user, office_user):
    call_command("seed_stock_demo", stdout=io.StringIO())
    with pytest.raises(Exception, match="already has stock entries"):
        call_command("seed_stock_demo", stdout=io.StringIO())
