"""Phase 3b: simultaneous users. Several logged-in sessions post at the same instant.

    uv run --with requests --with "psycopg[binary]" python e2e/rigour/concurrency.py http://127.0.0.1:8001 admin <password>

Checks, each with many threads released together by a barrier:
  1. Last units: N people try to take the last 5 of an item at once. Exactly one may succeed; stock never negative.
  2. Document numbers: N simultaneous Stock INs and N complaints. Numbers must be unique and gap-free.
  3. Same visit parts: N visits all give the same scarce parts. Stock must never go negative.
  4. Double submit race: the SAME form (same token) posted twice at the same instant from one session.
     tasks/todo.md records this as a known limit; this measures whether it really saves twice.
"""

import re
import sys
import threading
from datetime import date

import psycopg
from client import Client

BASE, USER, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]
DB = "postgresql://postgres:@127.0.0.1:52207/svkml_rigour"
TODAY = date(2026, 10, 22).isoformat()
db = psycopg.connect(DB, autocommit=True)
N = 8
failures = []


def one(sql, *a):
    return db.execute(sql, a).fetchone()[0]


def check(name, ok, evidence=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {evidence}" if not ok and evidence else ""))
    if not ok:
        failures.append(name)


def sessions(n):
    out = []
    for _ in range(n):
        c = Client(BASE)
        assert c.login(USER, PASSWORD)
        out.append(c)
    return out


def post_form(c, path, data, csrf, token):
    pairs = list(data) + [("csrfmiddlewaretoken", csrf), ("entry_token", token)]
    r = c.s.post(
        BASE + path, data=pairs, headers={"Referer": BASE + path}, allow_redirects=False, timeout=120
    )
    return r.status_code, r.headers.get("Location", ""), r.status_code in (301, 302)


def race(clients, pages, make_post):
    """One thread per client. Each opens its form first (like a real user), waits at a barrier so all post at
    the same instant, then posts. make_post(i, client, csrf, token) -> (status, location, saved)."""
    barrier, results = threading.Barrier(len(clients)), [None] * len(clients)

    def go(i, c):
        page, csrf, token = c.form(pages[i])
        barrier.wait()
        results[i] = make_post(i, c, csrf, token)

    threads = [threading.Thread(target=go, args=(i, c)) for i, c in enumerate(clients)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


loc = {n: i for n, i in db.execute("select name, id from inventory_location").fetchall()}
comp = {n: i for n, i in db.execute("select name, id from inventory_company").fetchall()}
spare = {n: i for n, i in db.execute("select name, id from inventory_sparetype").fetchall()}
admin = Client(BASE)
admin.login(USER, PASSWORD)

LINE_TAIL = [("line_batch", ""), ("line_pkd", ""), ("line_expected", ""), ("line_fault", "")]


def stock_form(kind, item, qty, **extra):
    head = [("entry_date", TODAY), ("location", loc["Svkml"]), ("note", "")]
    return head + list(extra.items()) + [("line_item", item), ("line_qty", qty)] + LINE_TAIL


IN_EXTRA = {"subtype": "SUPPLIER", "company": comp["Wipro Lighting"], "party": "", "ref": ""}

# ---- fixture item with exactly 5 in stock ------------------------------------------------------------------
r = admin.post(
    "/items/new/",
    {
        "code": "RIG-RACE-1",
        "spare_type": spare["Driver"],
        "company": comp["Wipro Lighting"],
        "unit": "NOS",
        "reorder_level": 0,
        "is_active": "on",
    },
    token=False,
)
item = (
    int(re.search(r"/items/(\d+)/", r.location).group(1))
    if r.saved
    else one("select id from inventory_item where code='RIG-RACE-1'")
)
r = admin.post("/stock/in/", stock_form("in", item, 5, **IN_EXTRA))
assert r.saved, r.message()


def balance():
    return one(
        "select coalesce(sum(qty),0) from inventory_stockbalance where item_id=%s and location_id=%s",
        item,
        loc["Svkml"],
    )


# ---- 1. last units ------------------------------------------------------------------------------------------
OUT_EXTRA = {"subtype": "SITE", "party": "Race site", "ref": ""}
res = race(
    sessions(N),
    ["/stock/out/"] * N,
    lambda i, c, csrf, token: post_form(
        c, "/stock/out/", stock_form("out", item, 5, **OUT_EXTRA), csrf, token
    ),
)
wins = sum(1 for _, _, ok in res if ok)
check(
    f"{N} people take the last 5 at once: exactly 1 succeeds ({wins} did), stock is {balance()}",
    wins == 1 and balance() == 0,
    str(res),
)

# ---- 2. document numbers ---------------------------------------------------------------------------------------
res = race(
    sessions(N),
    ["/stock/in/"] * N,
    lambda i, c, csrf, token: post_form(
        c, "/stock/in/", stock_form("in", item, 1, **{**IN_EXTRA, "ref": "RACE-IN"}), csrf, token
    ),
)
saved = sum(1 for _, _, ok in res if ok)
nums = [
    int(n.split("-")[1])
    for (n,) in db.execute("select number from inventory_stockentry where kind='IN'").fetchall()
]
check(
    f"{N} simultaneous Stock INs: all {saved} saved, IN numbers unique and gap-free (max {max(nums)} of {len(nums)})",
    saved == N and sorted(nums) == list(range(1, len(nums) + 1)),
    str(res),
)

site = one("select id from complaints_site order by id limit 1")
cmp_form = [
    ("site", site),
    ("contact_name", ""),
    ("phone", ""),
    ("company", comp["Wipro Lighting"]),
    ("company_ref", ""),
    ("reported_on", "2026-10-21"),
    ("qty_affected", 1),
    ("fault", "Race complaint"),
    ("priority", "NORMAL"),
]
res = race(
    sessions(N),
    ["/complaints/new/"] * N,
    lambda i, c, csrf, token: post_form(c, "/complaints/new/", cmp_form, csrf, token),
)
saved = sum(1 for _, _, ok in res if ok)
nums = [int(n.split("-")[1]) for (n,) in db.execute("select number from complaints_complaint").fetchall()]
check(
    f"{N} simultaneous complaints: all {saved} saved, CMP numbers unique and gap-free (max {max(nums)} of {len(nums)})",
    saved == N and sorted(nums) == list(range(1, len(nums) + 1)),
    str(res),
)

# ---- 3. visits giving the same scarce parts ---------------------------------------------------------------------
assert admin.post("/stock/in/", stock_form("in", item, 3, **IN_EXTRA)).saved
have = balance()
open_cmp = [
    n
    for (n,) in db.execute(
        "select number from complaints_complaint where status='ATTENDED' order by id limit %s", (N,)
    ).fetchall()
]
tech = one("select id from complaints_technician order by id limit 1")


def visit_post(i, c, csrf, token):
    data = [
        ("visit_date", TODAY),
        ("technicians", tech),
        ("work_done", "race"),
        ("location", loc["Svkml"]),
        ("next_status", "ATTENDED"),
        ("part_item", item),
        ("part_qty", 2),
    ]
    return post_form(c, f"/complaints/{open_cmp[i]}/visit/", data, csrf, token)


outs = race(sessions(len(open_cmp)), [f"/complaints/{n}/visit/" for n in open_cmp], visit_post)
wins = sum(1 for _, _, ok in outs if ok)
check(
    f"{len(open_cmp)} visits each give 2 of the {have} left: at most {have // 2} succeed ({wins} did), stock is {balance()} (never negative)",
    wins <= have // 2 and balance() >= 0 and balance() == have - 2 * wins,
    str(outs),
)

# ---- 4. the same form posted twice at the same instant -----------------------------------------------------------
c = Client(BASE)
c.login(USER, PASSWORD)
data = stock_form("in", item, 1, **{**IN_EXTRA, "ref": "DOUBLE-SUBMIT"})
runs, counts = 6, []
for _ in range(runs):
    page, csrf, token = c.form("/stock/in/")
    barrier = threading.Barrier(2)

    def twice(barrier=barrier, csrf=csrf, token=token):
        barrier.wait()
        c.s.post(
            BASE + "/stock/in/",
            data=data + [("csrfmiddlewaretoken", csrf), ("entry_token", token)],
            headers={"Referer": BASE + "/stock/in/"},
            allow_redirects=False,
            timeout=120,
        )

    t = [threading.Thread(target=twice) for _ in range(2)]
    [x.start() for x in t]
    [x.join() for x in t]
    counts.append(one("select count(*) from inventory_stockentry where ref='DOUBLE-SUBMIT'"))
made = [b - a for a, b in zip([0, *counts], counts, strict=False)]
check(
    f"the same form (one token) posted twice at the same instant, {runs} times: saved {made} per run (must be 1 each)",
    all(m == 1 for m in made),
    "a truly simultaneous double submit saved twice: the known limit noted in tasks/todo.md",
)

print(
    f"\n{'ALL CONCURRENCY CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED: ' + '; '.join(failures)}"
)
sys.exit(1 if failures else 0)
