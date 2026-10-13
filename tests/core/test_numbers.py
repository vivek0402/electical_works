import pytest
from django.db import transaction

from apps.core.models import Counter
from apps.core.numbers import next_number

pytestmark = pytest.mark.django_db


def test_series_count_up_independently():
    with transaction.atomic():
        assert [next_number("DEF"), next_number("DEF"), next_number("RB")] == [
            "DEF-0001",
            "DEF-0002",
            "RB-0001",
        ]
    assert Counter.objects.get(prefix="DEF").last == 2


def test_a_rolled_back_number_is_used_again():
    with pytest.raises(RuntimeError), transaction.atomic():
        next_number("CMP")
        raise RuntimeError("the save failed")
    with transaction.atomic():
        assert next_number("CMP") == "CMP-0001"
