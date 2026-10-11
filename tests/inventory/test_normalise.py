import pytest

from apps.inventory.normalise import normalise_code, search_key


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  lg26-048-0720 ", "LG26-048-0720"),
        ("`EIO6006", "EIO6006"),
        ("ISENSE  8BUTTON  SWITCH", "ISENSE 8BUTTON SWITCH"),
        ("15WATT (190Ma)", "15WATT (190MA)"),
        (None, ""),
    ],
)
def test_normalise_code(raw, expected):
    assert normalise_code(raw) == expected


@pytest.mark.parametrize(
    "a, b",
    [
        ("LG26-048-0720", "LG26-048-720"),
        ("R1103-092-PA", "RI103-092-PA"),
        ("EIO8437", "EI08437"),
        ("LL20-111-XXX-65NE3", "LL20-111-XXX-65-NE3"),
    ],
)
def test_lookalikes_share_key(a, b):
    assert search_key(a) == search_key(b)


@pytest.mark.parametrize("a, b", [("LG76-150-700", "LG76-150-700FH"), ("EUM-240S105D13", "EUM-240S105DB")])
def test_distinct_codes_keep_distinct_keys(a, b):
    assert search_key(a) != search_key(b)
