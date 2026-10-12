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


def test_db_conflict_becomes_item_error(monkeypatch):
    first = save_item(data=data())
    ItemAlias.objects.create(item=first, alias="TAKEN1")
    monkeypatch.setattr("apps.inventory.services.find_item_by_code", lambda *a, **k: None)
    with pytest.raises(ItemError, match="already exists"):
        save_item(data=data(code="OTHER1", aliases=["TAKEN1"]))


def test_missing_key_raises_keyerror():
    d = data()
    del d["aliases"]
    with pytest.raises(KeyError):
        save_item(data=d)


def test_too_long_code_or_alias_refused():
    with pytest.raises(ItemError, match=r"Item code is too long \(max 80 characters\)"):
        save_item(data=data(code="A" * 81, aliases=[]))
    with pytest.raises(ItemError, match=r"Other spelling .* is too long \(max 80 characters\)"):
        save_item(data=data(aliases=["B" * 81]))


def test_inactive_lookalike_hint():
    save_item(data=data(is_active=False))
    with pytest.raises(ItemError, match=r"looks the same as EIO8437.*inactive; reactivate it"):
        save_item(data=data(code="EI0-8437", aliases=[]))


def test_rename_unused_item_and_rename_to_own_alias():
    item = save_item(data=data())
    item = save_item(item=item, data=data(code="EIO9999", aliases=[]))
    assert item.code == "EIO9999"
    item = save_item(item=item, data=data(code="EIO9999", aliases=["OLD-9999"]))
    item = save_item(item=item, data=data(code="OLD-9999", aliases=["EIO9999"]))
    assert item.code == "OLD-9999"
    assert list(item.aliases.values_list("alias", flat=True)) == ["EIO9999"]
    item = save_item(item=item, data=data(code="EIO9999", aliases=["OLD-9999"]))
    assert item.code == "EIO9999"


def test_search_ranks_exact_first_and_returns_once(django_assert_num_queries):
    for n in range(10):
        save_item(data=data(code=f"AB10{n}", description="", cat_ref="", aliases=[]))
    target = save_item(data=data(code="AB1", description="", cat_ref="", aliases=["AB1-X", "AB1-Y"]))
    hits = search_items("ab1")
    assert hits[0] == target
    assert [i.code for i in hits[1:3]] == ["AB100", "AB101"]
    both = save_item(data=data(code="ZZ55", description="", cat_ref="", aliases=["ZZ55-A", "ZZ55-B"]))
    assert search_items("zz55") == [both]
    with django_assert_num_queries(2):  # one query + one aliases prefetch
        search_items("zz55")


def test_search_active_only():
    save_item(data=data(code="QQ77", is_active=False, aliases=[]))
    assert len(search_items("QQ77")) == 1
    assert search_items("QQ77", active_only=True) == []


def test_deactivating_item_with_stock_refused():
    user = make_user("clerk_d", "OFFICE")
    item = save_item(data=data())
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, loc(), 3)], user=user)
    with pytest.raises(ItemError) as err:
        save_item(item=item, data=data(is_active=False))
    assert err.value.message == "EIO8437 still holds stock. Issue or adjust it to zero first."
    item.refresh_from_db()
    assert item.is_active


def test_deactivating_item_with_zero_stock_allowed():
    user = make_user("clerk_z", "OFFICE")
    item = save_item(data=data())
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, loc(), 3)], user=user)
    post_entry(kind=EntryKind.OUT, entry_date=timezone.localdate(), lines=[Line(item, loc(), -3)], user=user)
    assert not save_item(item=item, data=data(is_active=False)).is_active


def test_unit_change_refused_once_item_has_entries():
    user = make_user("clerk_u", "OFFICE")
    item = save_item(data=data())
    assert save_item(item=item, data=data(unit="BOX")).unit == "BOX"  # no entries yet: allowed
    post_entry(kind=EntryKind.IN, entry_date=timezone.localdate(), lines=[Line(item, loc(), 3)], user=user)
    with pytest.raises(
        ItemError, match="The unit can't be changed because EIO8437 already has stock entries"
    ):
        save_item(item=item, data=data(unit="NOS"))
    item.refresh_from_db()
    assert item.unit == "BOX"
