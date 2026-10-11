import pytest
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, ItemAlias, SpareType
from apps.inventory.services import ItemError, Line, find_item_by_code, post_entry, save_item, search_items
from tests.factories import loc, make_user

pytestmark = pytest.mark.django_db


def data(**over):
    base = {
        "code": "EIO8437",
        "spare_type": SpareType.objects.get(name="PCB / LED module"),
        "description": "LED module",
        "cat_ref": "ld81-171-xxx-60-xx",
        "fitting_type": None,
        "wattage_w": None,
        "current_ma": None,
        "company": Company.objects.get(name="Wipro Lighting"),
        "unit": "NOS",
        "reorder_level": 5,
        "aliases": ["ei08437"],
        "is_active": True,
    }
    base.update(over)
    return base


def test_save_item_normalises_and_stores_aliases():
    item = save_item(data=data(code=" eio8437 "))
    assert item.code == "EIO8437" and item.cat_ref == "LD81-171-XXX-60-XX" and item.search_key == "E108437"
    assert list(item.aliases.values_list("alias", flat=True)) == ["EI08437"]


def test_find_by_code_exact_alias_and_lookalike():
    item = save_item(data=data())
    assert find_item_by_code("eio8437") == item
    assert find_item_by_code("EI08437") == item  # stored alias
    assert find_item_by_code("EI0-8437") == item  # look-alike key
    assert find_item_by_code("NOPE") is None


def test_duplicate_and_lookalike_refused():
    save_item(data=data())
    with pytest.raises(ItemError, match="already exists"):
        save_item(data=data(code="EIO8437", aliases=[]))
    with pytest.raises(ItemError, match="looks the same as EIO8437"):
        save_item(data=data(code="EI0-8437", aliases=[]))


def test_alias_belonging_to_other_item_refused():
    save_item(data=data())
    with pytest.raises(ItemError, match="belongs to EIO8437"):
        save_item(data=data(code="EIO6006", aliases=["EI08437"]))


def test_lookalike_alias_of_other_items_code_or_alias_refused():
    save_item(data=data())
    # look-alike of the other item's code (not an exact match)
    with pytest.raises(ItemError, match="belongs to EIO8437"):
        save_item(data=data(code="EIO6006", aliases=["EI0-8437"]))
    # look-alike of the other item's stored alias
    with pytest.raises(ItemError, match="belongs to EIO8437"):
        save_item(data=data(code="EIO6006", aliases=["EI0 8437"]))
    # same check when editing an existing item
    other = save_item(data=data(code="EIO6006", aliases=[]))
    with pytest.raises(ItemError, match="belongs to EIO8437"):
        save_item(item=other, data=data(code="EIO6006", aliases=["EIO 8437"]))
    assert not ItemAlias.objects.filter(item=other).exists()


def test_symbols_only_code_or_alias_refused_with_friendly_error():
    with pytest.raises(ItemError, match="letter or number"):
        save_item(data=data(code="---", aliases=[]))
    with pytest.raises(ItemError, match="letter or number"):
        save_item(data=data(aliases=["//"]))


def test_edit_keeps_own_code_and_replaces_aliases():
    item = save_item(data=data())
    item = save_item(item=item, data=data(description="LED module 9W", aliases=["EIO-8437-X"]))
    assert item.description == "LED module 9W"
    assert list(ItemAlias.objects.values_list("alias", flat=True)) == ["EIO-8437-X"]


def test_code_change_blocked_once_used():
    item = save_item(data=data())
    post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        lines=[Line(item, loc(), 1)],
        user=make_user("u1", "OFFICE"),
    )
    with pytest.raises(ItemError, match="can't be changed"):
        save_item(item=item, data=data(code="EIO8438"))


def test_required_fields():
    with pytest.raises(ItemError, match="Item code is required"):
        save_item(data=data(code="  "))


def test_search_items_by_code_alias_desc_and_cat_ref():
    item = save_item(data=data())
    for q in ["8437", "ei08437", "led mod", "LD81-171", "EIO8437"]:
        assert item in search_items(q), q
    assert search_items("zzz") == []
