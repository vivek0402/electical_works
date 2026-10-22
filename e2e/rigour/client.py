"""A small HTTP client for the rigour tests: it logs in and posts the app's real forms, the same way a
browser does (CSRF token, the one-time `entry_token`, redirects). The server code path is the real one:
forms, validation, services and the token guard. Only the browser's JavaScript is left out (Playwright
covers that in ui_checks.py).

Needs `requests`:  uv run --with requests python -I ...
"""

import html as htmllib
import re
from dataclasses import dataclass

import requests

TOKEN = re.compile(r'name="entry_token"\s+value="([^"]*)"')
CSRF = re.compile(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"')
ALERT = re.compile(r'<div class="alert alert-(danger|warning|success)[^"]*"[^>]*>(.*?)</div>', re.S)


def text_of(fragment):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def options(page, select_id):
    """{option text: value} of <select id=...>."""
    block = re.search(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', page, re.S)
    if not block:
        return {}
    return {
        text_of(t): v
        for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>(.*?)</option>', block.group(1), re.S)
        if v
    }


@dataclass
class Result:
    status: int
    location: str
    html: str

    @property
    def saved(self):
        return self.status in (301, 302, 303) and bool(self.location)

    def errors(self):
        """The red messages on the page the server sent back (a refusal re-draws the form)."""
        found = [text_of(m.group(2)) for m in ALERT.finditer(self.html) if m.group(1) == "danger"]
        invalid = re.findall(r'class="invalid-feedback[^"]*"[^>]*>(.*?)</', self.html, re.S)
        return [e for e in found + [text_of(i) for i in invalid] if e]

    def message(self):
        if self.saved:
            return "saved"
        if self.status >= 400:
            return f"HTTP {self.status}"
        return " | ".join(dict.fromkeys(self.errors())) or "no redirect and no message"


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.requests_made = 0

    def get(self, path, **kw):
        self.requests_made += 1
        return self.s.get(self.base + path, allow_redirects=kw.pop("allow_redirects", True), timeout=60, **kw)

    def login(self, user, password):
        page = self.get("/login/").text
        csrf = CSRF.search(page).group(1)
        r = self.s.post(
            self.base + "/login/",
            data={"username": user, "password": password, "csrfmiddlewaretoken": csrf},
            headers={"Referer": self.base + "/login/"},
            allow_redirects=False,
            timeout=60,
        )
        return r.status_code in (301, 302)

    def form(self, path):
        """Open a page that holds a form; returns (html, csrf, entry_token)."""
        page = self.get(path).text
        csrf = CSRF.search(page)
        token = TOKEN.search(page)
        return (
            page,
            (csrf.group(1) if csrf else self.s.cookies.get("csrftoken", "")),
            (token.group(1) if token else ""),
        )

    def post(self, path, data, page_path=None, token=True):
        """Open `page_path` (default: `path`) for a fresh token, then post `data` (a list of pairs or dict)."""
        page, csrf, entry_token = self.form(page_path or path)
        pairs = list(data.items()) if isinstance(data, dict) else list(data)
        pairs.append(("csrfmiddlewaretoken", csrf))
        if token and entry_token:
            pairs.append(("entry_token", entry_token))
        self.requests_made += 1
        r = self.s.post(
            self.base + path,
            data=pairs,
            headers={"Referer": self.base + (page_path or path)},
            allow_redirects=False,
            timeout=120,
        )
        return Result(r.status_code, r.headers.get("Location", ""), r.text)

    def post_json(self, path, data, page_path):
        page, csrf, _ = self.form(page_path)
        self.requests_made += 1
        r = self.s.post(
            self.base + path,
            data={**data, "csrfmiddlewaretoken": csrf},
            headers={"Referer": self.base + page_path},
            allow_redirects=False,
            timeout=60,
        )
        return r
