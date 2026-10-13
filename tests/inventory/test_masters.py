from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import Company, FittingType, Item, ItemAlias, Location, SpareType

pytestmark = pytest.mark.django_db


def test_masters_seeded():
    assert set(Location.objects.good().values_list("name", flat=True)) == {
        "Vizag Office",
        "Svkml",
        "TV Shop",
        "Kartika Class",
    }
    assert Company.objects.filter(name="Wipro Lighting").exists()
    assert SpareType.objects.filter(name="Driver").exists()
    assert FittingType.objects.filter(name="Flood light").exists()


def test_item_code_must_be_upper_and_unique():
    st, co = SpareType.objects.get(name="Driver"), Company.objects.get(name="Wipro Lighting")
    Item.objects.create(code="LG78-150-700", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="lg78-150-700", spare_type=st, company=co)  # normalised -> duplicate
    # the database itself refuses a lower-case code when save() is bypassed
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.bulk_create([Item(code="lg78-150-701", search_key="x", spare_type=st, company=co)])


def test_search_key_recomputed_on_save():
    st, co = SpareType.objects.get(name="Driver"), Company.objects.get(name="Wipro Lighting")
    item = Item.objects.create(code=" lg78-150-0700 ", search_key="junk", spare_type=st, company=co)
    assert item.code == "LG78-150-0700"
    assert item.search_key == "LG781507" + "00"
    alias = ItemAlias.objects.create(item=item, alias="lg78-150-700x")
    assert alias.alias == "LG78-150-700X"
    assert alias.search_key == "LG78150700X"


def test_symbols_only_code_rejected():
    st, co = SpareType.objects.get(name="Driver"), Company.objects.get(name="Wipro Lighting")
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="---", spare_type=st, company=co)
    item = Item.objects.create(code="AB-1", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        ItemAlias.objects.create(item=item, alias="---")


def test_master_names_unique_case_insensitive_and_trimmed():
    with pytest.raises(IntegrityError), transaction.atomic():
        Company.objects.create(name="havells")
    with pytest.raises(IntegrityError), transaction.atomic():
        Company.objects.create(name="  Wipro   Lighting ")
    assert Company.objects.create(name="  New   Co ").name == "New Co"
    assert Company._meta.verbose_name_plural == "companies"


# ---- admin masters page ----


def test_office_cannot_open_masters(office_client):
    assert office_client.get("/masters/").status_code == 403


def test_admin_adds_location_and_company(admin_client):
    assert admin_client.get("/masters/").status_code == 200
    r = admin_client.post("/masters/", {"kind": "location", "name": "  Gajuwaka Store "})
    assert r.status_code == 302 and Location.objects.filter(name="Gajuwaka Store").exists()
    admin_client.post("/masters/", {"kind": "company", "name": "Bajaj"})
    assert Company.objects.filter(name="Bajaj").exists()


def test_duplicate_name_refused(admin_client):
    html = admin_client.post(
        "/masters/", {"kind": "location", "name": "vizag office"}, follow=True
    ).content.decode()
    assert "already exists" in html and Location.objects.filter(name__iexact="vizag office").count() == 1


def test_concurrent_duplicate_gets_friendly_message(admin_client):
    with mock.patch.object(Location.objects, "create", side_effect=IntegrityError):
        html = admin_client.post(
            "/masters/", {"kind": "location", "name": "Brand New"}, follow=True
        ).content.decode()
    assert "already exists" in html


def test_unknown_kind_and_blank_name(admin_client):
    html = admin_client.post("/masters/", {"kind": "nope", "name": "x"}, follow=True).content.decode()
    assert "Unknown list" in html
    html = admin_client.post("/masters/", {"kind": "location", "name": "   "}, follow=True).content.decode()
    assert "Type a name" in html


def test_name_too_long_refused(admin_client):
    html = admin_client.post(
        "/masters/", {"kind": "location", "name": "x" * 81}, follow=True
    ).content.decode()
    assert "too long" in html and not Location.objects.filter(name__startswith="xxxx").exists()


def test_toggle_active(admin_client):
    place = Location.objects.get(name="TV Shop")
    admin_client.post("/masters/toggle/", {"kind": "location", "pk": place.pk})
    place.refresh_from_db()
    assert place.is_active is False
    admin_client.post("/masters/toggle/", {"kind": "location", "pk": place.pk})
    place.refresh_from_db()
    assert place.is_active is True


def test_toggle_bad_pk_is_harmless(admin_client):
    r = admin_client.post("/masters/toggle/", {"kind": "location", "pk": "abc"}, follow=True)
    assert "Nothing to change" in r.content.decode()


def test_cannot_hide_location_holding_stock(admin_client, office_user):
    from django.utils import timezone

    from apps.inventory.models import EntryKind
    from apps.inventory.services import Line, post_entry
    from tests.factories import loc, make_item

    place = loc()
    post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        lines=[Line(make_item("HLD1"), place, 3)],
        user=office_user,
    )
    html = admin_client.post(
        "/masters/toggle/", {"kind": "location", "pk": place.pk}, follow=True
    ).content.decode()
    place.refresh_from_db()
    assert place.is_active and "still holds stock" in html


def test_dashboard_card_keeps_hidden_location_with_stock():
    from apps.inventory import selectors
    from apps.inventory.models import StockBalance
    from tests.factories import loc, make_item

    place = loc()
    StockBalance.objects.create(item=make_item("HLD2"), location=place, qty=4)
    Location.objects.filter(pk=place.pk).update(is_active=False)  # hidden although it holds stock
    shown = {p.pk: totals for p, totals in selectors.location_unit_totals()}
    assert shown[place.pk] == {"NOS": 4}
    StockBalance.objects.all().delete()
    assert place.pk not in {p.pk for p, _ in selectors.location_unit_totals()}


def test_cannot_hide_last_active_location_or_company(admin_client):
    Location.objects.exclude(name="TV Shop").update(is_active=False)
    place = Location.objects.get(name="TV Shop")
    html = admin_client.post(
        "/masters/toggle/", {"kind": "location", "pk": place.pk}, follow=True
    ).content.decode()
    place.refresh_from_db()
    assert place.is_active and "At least one location must stay active" in html
    Company.objects.exclude(name="Havells").update(is_active=False)
    co = Company.objects.get(name="Havells")
    html = admin_client.post(
        "/masters/toggle/", {"kind": "company", "pk": co.pk}, follow=True
    ).content.decode()
    co.refresh_from_db()
    assert co.is_active and "At least one company must stay active" in html


def test_cannot_hide_default_company(admin_client):
    co = Company.objects.get(name="Wipro Lighting")
    html = admin_client.post(
        "/masters/toggle/", {"kind": "company", "pk": co.pk}, follow=True
    ).content.decode()
    co.refresh_from_db()
    assert co.is_active and "default supplier" in html


def test_office_cannot_toggle(office_client):
    place = Location.objects.get(name="TV Shop")
    assert office_client.post("/masters/toggle/", {"kind": "location", "pk": place.pk}).status_code == 403
    place.refresh_from_db()
    assert place.is_active is True
