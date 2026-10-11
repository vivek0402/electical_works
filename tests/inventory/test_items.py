import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inventory.models import Item, ItemType
from apps.inventory.normalise import search_key
from apps.inventory.services import add_alias, create_item

pytestmark = pytest.mark.django_db

SAMPLE_CODES = [
    "LG26-048-0720",
    "LG26-048-720",
    "LG30-018-054-0300",
    "RI103-092-PA",
    "EI08437",
    "EIO8437",
    "LL20-111-XXX-65-NE3",
    "LH21-100/120-46-23-S2P",
    "ISENSE DALI CONTROLLER (WCS-IS-DA4)",
    "15WATT (190MA)",
    "LH23M50C16*1",
    "LG30-000-1",
]


def test_sql_search_key_matches_python():
    for code in SAMPLE_CODES:
        Item.objects.create(code=code)
    for item in Item.objects.all():
        assert item.search_key == search_key(item.code), item.code


def test_db_rejects_unnormalised_code():
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(code="lg26-048-0720")


def test_create_item_normalises_and_rejects_duplicates():
    item = create_item(code=" eio6006 ", item_type=ItemType.PCB)
    assert item.code == "EIO6006"
    assert item.brand == "Wipro" and item.unit == "NOS"
    with pytest.raises(ValidationError, match="already exists"):
        create_item(code="EIO6006")


def test_alias_rules():
    item = create_item(code="EIO8437", item_type=ItemType.PCB)
    alias = add_alias(item=item, alias="ei08437")
    assert alias.alias == "EI08437"
    assert add_alias(item=item, alias="EI08437") == alias  # idempotent
    with pytest.raises(ValidationError, match="already an alias"):
        create_item(code="EI08437")
    other = create_item(code="EIO6006")
    with pytest.raises(ValidationError, match="already an alias of EIO8437"):
        add_alias(item=other, alias="EI08437")
    with pytest.raises(ValidationError, match="already an item code"):
        add_alias(item=item, alias="EIO6006")
