"""Pure functions that clean the messy codes and quantities found in the client's Excel sheets.

`search_key` has a SQL twin in `models.search_key_expression`; tests keep the two in lockstep.
"""

import re

# Leading zeros of an all-digit segment: "LG26-048-0720" -> "LG26-48-720".
LEADING_ZEROS = r"(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)"
NON_ALNUM = r"[^A-Z0-9]"
# Letters commonly confused with digits when codes are typed by hand.
LOOKALIKES = str.maketrans({"O": "0", "I": "1"})

_QTY = re.compile(r"^\s*(\d+)\s*(?:NOS?\.?|PCS)?\s*$", re.IGNORECASE)


def normalise_code(raw) -> str:
    """Canonical stored form of an item code: upper-case, trimmed, no stray symbols.

    Keeps meaningful punctuation (-, /, *, parentheses) and single inner spaces for
    generic names like "ISENSE 8BUTTON SWITCH".
    """
    if raw is None:
        return ""
    code = str(raw).upper().replace("`", "").replace("'", "").replace('"', "")
    code = re.sub(r"\s+", " ", code).strip(" .,;:")
    return code


def search_key(code: str) -> str:
    """Fuzzy-match key: O->0, I->1, leading zeros dropped per numeric segment, symbols removed.

    Two codes with the same key are probably the same part (e.g. EIO8437 / EI08437,
    LG26-048-0720 / LG26-048-720, LL20-111-XXX-65NE3 / LL20-111-XXX-65-NE3).
    Used for duplicate detection and search only; never as an identity.
    """
    key = normalise_code(code).translate(LOOKALIKES)
    key = re.sub(LEADING_ZEROS, r"\1\2", key)
    return re.sub(NON_ALNUM, "", key)


def parse_qty(raw) -> int | None:
    """Parse "22 NOS", "1NOS", "`7NOS", 5 or 5.0 into an int. Returns None if not a whole count."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw) if raw.is_integer() else None
    match = _QTY.match(str(raw).replace("`", ""))
    return int(match.group(1)) if match else None
