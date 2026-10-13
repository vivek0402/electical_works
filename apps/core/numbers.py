"""Gap-free document numbers (DEF-0001, RB-0001, CMP-0001, VIS-0001), like stock entry numbers."""

from .models import Counter


def next_number(prefix):
    """The next number in a series, e.g. 'DEF-0042'.

    Call inside a transaction: the counter row stays locked until commit, so two saves never get the same
    number, and a save that fails gives its number back.
    """
    Counter.objects.get_or_create(prefix=prefix)
    counter = Counter.objects.select_for_update().get(prefix=prefix)
    counter.last += 1
    counter.save(update_fields=["last"])
    return f"{prefix}-{counter.last:04d}"
