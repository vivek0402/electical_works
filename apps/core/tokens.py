"""One-time form tokens: a resubmitted form (double click, Back + Save) never saves twice.

Each page path holds one unspent token, reused while the person only reads (so opening other pages never
pushes it out). Saving spends it and remembers what it saved (an entry number or a URL) together with a
fingerprint of the action (path + posted fields). A second submit of the *same action* with that token is
sent to what was already saved. A *different* action with a spent token (Back, then act on another row) is
treated as expired: nothing is saved and the page comes back with a fresh token and what was typed.

Views use `guarded_post`; `page_token` puts the token on the page.
"""

import hashlib
import uuid
from dataclasses import dataclass

from django.core.exceptions import ValidationError

FIELD = "entry_token"  # the hidden input every saving form carries
TOKENS, PAGES, SAVED = "entry_tokens", "entry_token_pages", "entry_saved"
KEEP_TOKENS = 50  # unspent tokens kept: one per page path, least recently opened dropped first
KEEP_SAVED = 20
EXPIRED = "This form had expired, so nothing was saved. Check the details and save again."
NOT_FINGERPRINTED = {"csrfmiddlewaretoken", FIELD}


def page_token(session, path):
    """The unspent token for the page at `path`, reusing the one it already has. The token moves to the
    end of the list (most recently opened)."""
    tokens = list(session.get(TOKENS, []))
    pages = dict(session.get(PAGES, {}))
    token = pages.get(path)
    if token not in tokens:
        token = uuid.uuid4().hex
    tokens = [*(t for t in tokens if t != token), token][-KEEP_TOKENS:]
    pages = {p: t for p, t in pages.items() if t in tokens and p != path}
    pages[path] = token
    session[TOKENS], session[PAGES] = tokens, pages
    return token


def fingerprint(request):
    """The action a POST performs: its path and its fields (minus the CSRF and one-time tokens)."""
    items = sorted((k, v) for k, values in request.POST.lists() if k not in NOT_FINGERPRINTED for v in values)
    raw = repr((request.path, items)).encode()
    return hashlib.sha256(raw).hexdigest()


def spend_token(session, token, saved, action=""):
    session[TOKENS] = [t for t in session.get(TOKENS, []) if t != token]
    session[PAGES] = {p: t for p, t in session.get(PAGES, {}).items() if t != token}
    done = {**session.get(SAVED, {}), token: [saved, action]}
    session[SAVED] = dict(list(done.items())[-KEEP_SAVED:])


def already_saved(session, token, action=""):
    """What this token saved before (e.g. 'TRF-0004'), when `action` is the same action; else None."""
    if not token:
        return None
    done = session.get(SAVED, {}).get(token)
    if not done:
        return None
    saved, stored = done if isinstance(done, list) else (done, "")
    return saved if stored == action else None


def is_issued(session, token):
    return bool(token) and token in session.get(TOKENS, [])


@dataclass
class Guarded:
    saved: str | None = None  # what run() saved, or what the same action saved before (replayed)
    replayed: bool = False
    error: str | None = None  # EXPIRED or the refusal message; nothing was saved
    token: str = ""  # the token to put back on a re-rendered page ("" = issue a fresh one)


def guarded_post(request, run):
    """Run `run()` at most once per one-time token and action.

    `run()` saves and returns what to remember (an entry number or a URL), or raises ValidationError
    (StockError, DefectiveError, ...) whose message is shown; then nothing was saved and the token stays.
    """
    token, action = request.POST.get(FIELD, ""), fingerprint(request)
    done = already_saved(request.session, token, action)
    if done:
        return Guarded(saved=done, replayed=True, token=token)
    if not is_issued(request.session, token):
        return Guarded(error=EXPIRED)
    try:
        saved = run()
    except ValidationError as exc:
        return Guarded(error=exc.messages[0], token=token)
    spend_token(request.session, token, saved, action)
    return Guarded(saved=saved, token=token)
