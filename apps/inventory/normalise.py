"""Pure helpers to clean item codes typed in many ways (old spellings, typos)."""

import re

LEADING_ZEROS = re.compile(r"(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)")
NON_ALNUM = re.compile(r"[^A-Z0-9]")
LOOKALIKES = str.maketrans({"O": "0", "I": "1"})


def normalise_code(raw) -> str:
    """Stored form of a code: upper-case, trimmed, single spaces, no quote/backtick junk."""
    if raw is None:
        return ""
    code = str(raw).upper().replace("`", "").replace("'", "").replace('"', "")
    return re.sub(r"\s+", " ", code).strip(" .,;:")


def search_key(code) -> str:
    """Look-alike key: O->0, I->1, leading zeros dropped per number, symbols removed.

    EIO8437 == EI08437, LG26-048-0720 == LG26-048-720. Used for duplicate detection and search only.
    """
    key = normalise_code(code).translate(LOOKALIKES)
    key = LEADING_ZEROS.sub(r"\1\2", key)
    return NON_ALNUM.sub("", key)
