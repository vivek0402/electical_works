import pytest
from django.db import IntegrityError, transaction

from apps.inventory.models import Company, FittingType, Item, Location, SpareType

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
    Item.objects.create(code="LG78-150-700", search_key="LG78150700", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="lg78-150-701", search_key="x", spare_type=st, company=co)
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="LG78-150-700", search_key="y", spare_type=st, company=co)
