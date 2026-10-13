"""One-time form tokens: a resubmitted form (double click, Back + Save) never saves twice.

Each page gets a fresh token. Saving spends it and remembers what it saved (an entry or complaint number),
so a second submit of the same token is sent to what was already saved instead of saving again.
"""

import uuid

TOKENS, SAVED, KEEP_TOKENS = "entry_tokens", "entry_saved", 20
EXPIRED = "This form had expired, so nothing was saved. Check the details and save again."


def new_token(session):
    token = uuid.uuid4().hex
    session[TOKENS] = [*session.get(TOKENS, []), token][-KEEP_TOKENS:]
    return token


def spend_token(session, token, saved):
    session[TOKENS] = [t for t in session.get(TOKENS, []) if t != token]
    done = {**session.get(SAVED, {}), token: saved}
    session[SAVED] = dict(list(done.items())[-KEEP_TOKENS:])


def already_saved(session, token):
    """What this token saved before (e.g. 'TRF-0004'), or None."""
    return session.get(SAVED, {}).get(token) if token else None


def is_issued(session, token):
    return bool(token) and token in session.get(TOKENS, [])
