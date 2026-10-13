import pytest

from apps.complaints.phones import normalise_phone


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+91 98765 43210", "9876543210"),
        ("919876543210", "9876543210"),
        ("098765 43210", "9876543210"),
        ("9876543210", "9876543210"),
        ("0891-2345678", "08912345678"),
        ("08912345678", "08912345678"),
        ("(0891) 234 5678", "08912345678"),
        ("0891.234.5678", "08912345678"),
        ("", ""),
        (None, ""),
        ("  - ", ""),
    ],
)
def test_normalise_accepts(text, expected):
    assert normalise_phone(text) == expected


@pytest.mark.parametrize(
    "text", ["12345", "1234567890", "98765 4321", "abc", "00912345678", "0891-23456789012"]
)
def test_normalise_refuses_junk_with_the_landline_message(text):
    with pytest.raises(ValueError, match="mobile number or an STD landline like 0891-2345678"):
        normalise_phone(text)


def test_landline_refused_when_mobile_only():
    with pytest.raises(ValueError, match=r"^Phone must be a 10-digit mobile number\.$"):
        normalise_phone("0891-2345678", allow_landline=False)


def test_mobile_only_still_cleans_mobiles():
    assert normalise_phone("+91 98765 43210", allow_landline=False) == "9876543210"
    assert normalise_phone("098765 43210", allow_landline=False) == "9876543210"
