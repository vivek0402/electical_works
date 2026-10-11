import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import Company, FittingType, Item, ItemAlias, Location, SpareType

pytestmark = pytest.mark.django_db


def test_masters_seeded():
    assert set(Location.objects.values_list("name", flat=True)) == {
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
