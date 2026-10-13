"""Gap-free document numbers (DEF-0001, RB-0001, CMP-0001, VIS-0001), like stock entry numbers."""

from .models import Counter


def next_numbers(prefix, n):
    """The next `n` numbers in a series, e.g. ['DEF-0042', 'DEF-0043'], for one counter update.

    Call inside a transaction: the counter row stays locked until commit, so two saves never get the same
    number, and a save that fails gives its numbers back.
    """
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n must be a whole number, 1 or more.")
    Counter.objects.get_or_create(prefix=prefix)
    counter = Counter.objects.select_for_update().get(prefix=prefix)
    first = counter.last + 1
    counter.last += n
    counter.save(update_fields=["last"])
    return [f"{prefix}-{number:04d}" for number in range(first, counter.last + 1)]


def next_number(prefix):
    """The next number in a series, e.g. 'DEF-0042'. See next_numbers."""
    return next_numbers(prefix, 1)[0]
