"""Every messy value below is copied from the client's sample sheets."""

import pytest

from apps.inventory.normalise import normalise_code, parse_qty, search_key


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("LG66-040-078-480IT", "LG66-040-078-480IT"),
        ("  lg26-048-0720 ", "LG26-048-0720"),
        ("`EIO6006", "EIO6006"),
        ("ISENSE  DALI CONTROLLER (WCS-IS-DA4)", "ISENSE DALI CONTROLLER (WCS-IS-DA4)"),
        ("15WATT (190Ma)", "15WATT (190MA)"),
        ("LH23M50C16*1", "LH23M50C16*1"),
        ("LH21-100/120-46-23-S2P", "LH21-100/120-46-23-S2P"),
        ("z", "Z"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalise_code(raw, expected):
    assert normalise_code(raw) == expected


@pytest.mark.parametrize(
    "a, b",
    [
        ("LG26-048-0720", "LG26-048-720"),
        ("LG30-018-054-300", "LG30-018-054-0300"),
        ("R1103-092-PA", "RI103-092-PA"),
        ("EIO8437", "EI08437"),
        ("LL20-111-XXX-65NE3", "LL20-111-XXX-65-NE3"),
        ("lg66-036-036-900s", "LG66-036-036-900S"),
    ],
)
def test_known_spelling_variants_share_a_search_key(a, b):
    assert search_key(a) == search_key(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("LG30-018-054-300", "LG75-018-054-300"),
        ("EIO8436", "EIO8436-57K"),
        ("LG76-150-700", "LG76-150-700FH"),
        ("EUM-240S105D13", "EUM-240S105DB"),  # fuzzy-tier only, never an exact match
    ],
)
def test_distinct_codes_keep_distinct_keys(a, b):
    assert search_key(a) != search_key(b)


def test_leading_zeros_only_dropped_from_all_digit_segments():
    assert search_key("LG83-072-103-0700") == "LG8372103700"
    assert search_key("LL20-111-XXX-065NE3") == "LL20111XXX065NE3"
    assert search_key("LG30-000-1") == "LG3001"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("22 NOS", 22),
        ("1NOS", 1),
        ("`7NOS", 7),
        ("103NOS", 103),
        ("250NOS", 250),
        ("5 nos", 5),
        ("12", 12),
        (12, 12),
        (12.0, 12),
        (12.5, None),
        ("", None),
        (None, None),
        ("Saturday", None),
        ("18nos not working", None),
    ],
)
def test_parse_qty(raw, expected):
    assert parse_qty(raw) == expected
