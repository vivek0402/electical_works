import threading
import time

import pytest
from django.db import connection, transaction

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


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_people_never_get_the_same_number():
    """Both start on a series nobody has used yet (no counter row), then keep taking numbers."""
    barrier, taken, errors = threading.Barrier(2), [], []

    def take():
        try:
            barrier.wait()
            for _ in range(5):
                with transaction.atomic():
                    taken.append(next_number("VIS"))
                    time.sleep(0.02)  # hold the lock so the other person has to wait
        except Exception as exc:  # recorded so a failure can be diagnosed
            errors.append(repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=take) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert sorted(taken) == [f"VIS-{n:04d}" for n in range(1, 11)]
    assert Counter.objects.get(prefix="VIS").last == 10
