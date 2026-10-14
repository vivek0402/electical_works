"""Phone numbers for sites, complaints and technicians.

Sites and complaints take a 10-digit mobile or an STD landline (0 + area code + number, 10 or 11 digits);
technicians take a mobile only. The same patterns are DB CheckConstraints in models.py.
"""

import re

MOBILE_REGEX = r"^[6-9][0-9]{9}$"
MOBILE_OR_LANDLINE_REGEX = r"^([6-9][0-9]{9}|0[1-9][0-9]{8,9})$"
PHONE_MAX = 11  # an STD landline with its leading 0

MOBILE_ERROR = "Phone must be a 10-digit mobile number."
MOBILE_OR_LANDLINE_ERROR = "Phone must be a 10-digit mobile number or an STD landline like 0891-2345678."

_SEPARATORS = re.compile(r"[\s\-().]")


def normalise_phone(text, allow_landline=True):
    """The phone as stored: digits only, no country code, mobiles without a leading 0. Blank stays blank.

    '+91 98765 43210' -> '9876543210', '098765 43210' -> '9876543210', '0891-2345678' -> '08912345678'.
    Raises ValueError (message safe to show) if it isn't a mobile (or, with allow_landline, an STD landline).
    """
    error = MOBILE_OR_LANDLINE_ERROR if allow_landline else MOBILE_ERROR
    phone = _SEPARATORS.sub("", text or "")
    if not phone:
        return ""
    if phone.startswith("+91"):
        phone = phone[3:]
    elif phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    # A 0 typed in front of a mobile. Only "09..." is read that way: "0" + 6, 7 or 8 starts an STD code
    # (0891-2345678 is Vizag), and no STD code starts with 9.
    if len(phone) == 11 and phone.startswith("09"):
        phone = phone[1:]
    if not re.fullmatch(MOBILE_OR_LANDLINE_REGEX if allow_landline else MOBILE_REGEX, phone):
        raise ValueError(error)
    return phone


# Two-digit STD codes (Delhi, Pune, Mumbai, Kolkata, Hyderabad, Chennai, Ahmedabad, Bengaluru). Other
# codes are shown as three digits (0891-2345678 for Visakhapatnam); the digits are the same either way.
METRO_STD = {"11", "20", "22", "33", "40", "44", "79", "80"}


def format_phone(phone):
    """A stored phone for reading: '9876543210' -> '98765 43210', '08912345678' -> '0891-2345678',
    '01123456789' -> '011-23456789'. Anything else (blank, an old value) is returned unchanged."""
    phone = phone or ""
    if re.fullmatch(MOBILE_REGEX, phone):
        return f"{phone[:5]} {phone[5:]}"
    if re.fullmatch(MOBILE_OR_LANDLINE_REGEX, phone):  # a landline: 0 + STD code + number
        cut = 3 if phone[1:3] in METRO_STD else 4
        return f"{phone[:cut]}-{phone[cut:]}"
    return phone
