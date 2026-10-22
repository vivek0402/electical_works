"""Phase 3: business-rule, messy-input and permission scenarios, run on top of the loaded rigour data.

    uv run --with requests --with "psycopg[binary]" python e2e/rigour/scenario_matrix.py \
        http://127.0.0.1:8001 admin office <password>

Every case has an expected verdict written BEFORE it runs:
  saved    the database must change
  refused  nothing may change (checked with a before/after snapshot of the database, not just the page)
  observe  a judgement call: the result is recorded for the report, only a server error (HTTP 5xx) fails it
  status:N the HTTP status must be N (permissions)
Any HTTP 5xx fails any case. Results go to e2e/rigour/matrix-results.json.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

import psycopg
import requests
from client import Client, text_of

HERE = Path(__file__).resolve().parent
BASE, ADMIN, OFFICE, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
DB = sys.argv[5] if len(sys.argv) > 5 else "postgresql://postgres:@127.0.0.1:52207/svkml_rigour"
TODAY = date(2026, 10, 22).isoformat()
db = psycopg.connect(DB, autocommit=True)
admin, office, anon = Client(BASE), Client(BASE), Client(BASE)
assert admin.login(ADMIN, PASSWORD) and office.login(OFFICE, PASSWORD), "login failed"


def q(sql, *a):
    return db.execute(sql, a).fetchall()


def state():
    """One value that changes whenever anything a user can save changes."""
    parts = [
        f"(select count(*) from {t})"
        for t in (
            "inventory_stockentry",
            "inventory_stockline",
            "inventory_item",
            "complaints_complaint",
            "complaints_visit",
            "complaints_site",
            "complaints_technician",
            "defectives_defectivepiece",
            "defectives_returnbatch",
            "defectives_batchline",
        )
    ]
    parts += [
        f"(select md5(coalesce(string_agg(id::text||status, ',' order by id),'')) from {t})"
        for t in ("complaints_complaint", "defectives_defectivepiece", "defectives_returnbatch")
    ]
    parts += [
        "(select coalesce(sum(qty),0) from inventory_stockbalance)",
        "(select count(*) from complaints_site where is_active)",
    ]
    return db.execute("select " + ", ".join(parts)).fetchone()


def one(sql, *a):
    r = q(sql, *a)
    return r[0][0] if r else None


loc = dict((n, i) for i, n in q("select id, name from inventory_location"))
comp = dict((n, i) for i, n in q("select id, name from inventory_company"))
spare = dict((n, i) for i, n in q("select id, name from inventory_sparetype"))


def make_item(code, company="Wipro Lighting"):
    r = admin.post(
        "/items/new/",
        {
            "code": code,
            "spare_type": spare["Driver"],
            "company": comp[company],
            "unit": "NOS",
            "reorder_level": 0,
            "is_active": "on",
        },
        token=False,
    )
    return (
        int(re.search(r"/items/(\d+)/", r.location).group(1))
        if r.saved
        else one("select id from inventory_item where upper(code)=upper(%s)", code)
    )


def lines(rows):
    out = []
    for r in rows:
        r = list(r) + [""] * (6 - len(r))
        out += [
            ("line_item", str(r[0])),
            ("line_qty", str(r[1])),
            ("line_batch", r[2]),
            ("line_pkd", r[3]),
            ("line_expected", str(r[4])),
            ("line_fault", r[5]),
        ]
    return out


def entry(client, path, rows, date_=TODAY, where="Svkml", **extra):
    data = (
        [("entry_date", date_), ("location", loc[where]), ("note", extra.pop("note", ""))]
        + list(extra.items())
        + lines(rows)
    )
    return client.post(path, data)


def stock_in(rows, client=None, **kw):
    kw.setdefault("subtype", "SUPPLIER")
    kw.setdefault("company", comp["Wipro Lighting"])
    return entry(client or admin, "/stock/in/", rows, **kw)


def stock_out(rows, client=None, **kw):
    kw.setdefault("subtype", "SITE")
    kw.setdefault("party", "Rigour Site")
    return entry(client or admin, "/stock/out/", rows, **kw)


def follow(client, result):
    """After a redirect that carries a flash message, fetch it, so the report can quote the refusal."""
    if result.saved:
        page = client.get(
            result.location if result.location.startswith("/") else result.location.replace(BASE, "")
        ).text
        bad = re.findall(r'<div class="alert alert-(?:danger|warning)[^"]*"[^>]*>(.*?)</div>', page, re.S)
        return " | ".join(text_of(b) for b in bad)
    return result.message()


# ---- fixtures: a clean item for exact-quantity rules ------------------------------------------------------------
FIX = make_item("RIG-FIXTURE-A")
HAV = make_item("RIG-HAVELLS-1", "Havells")
assert stock_in([(FIX, 10, "B1", "2026-01")]).saved, "fixture IN failed"
assert stock_in([(HAV, 3, "H1", "2026-01")], company=comp["Havells"]).saved
mk = entry(admin, "/defectives/mark/", [(HAV, 1, "H1", "2026-01", "", "Rigour: dead")], where="Svkml")
assert mk.saved, mk.message()
HAV_TAG = one("select tag from defectives_defectivepiece where item_id=%s order by id desc limit 1", HAV)
WIPRO_TAG = one(
    "select tag from defectives_defectivepiece p join inventory_company c on c.id=p.company_id where p.status='IN_STORE' and c.name='Wipro Lighting' order by p.id limit 1"
)
OPEN_CMP = one("select number from complaints_complaint where status='ATTENDED' order by id limit 1")
CLOSED_CMP = one("select number from complaints_complaint where status='CLOSED' order by id limit 1")
NOT_ATT = one("select number from complaints_complaint where status='NOT_ATTENDED' order by id limit 1")
SITE_ID = one("select id from complaints_site order by id limit 1")
SITE_NAME = one("select name from complaints_site order by id limit 1")
TECH_ID = one("select id from complaints_technician order by id limit 1")
RICH = q(
    "select i.id, i.code from inventory_stockbalance b join inventory_item i on i.id=b.item_id join inventory_location l on l.id=b.location_id where l.name='Vizag Office' and b.qty>=10 order by b.qty desc limit 1"
)[0]
RICH_ID, RICH_CODE = RICH
RICH_QTY = one(
    "select qty from inventory_stockbalance where item_id=%s and location_id=%s", RICH_ID, loc["Vizag Office"]
)

results = []


def case(area, name, expect, fn, note=""):
    before = state()
    try:
        out = fn()
    except Exception as exc:  # a crash in the harness is reported, never hidden
        results.append(
            {
                "area": area,
                "name": name,
                "expect": expect,
                "verdict": "ERROR",
                "pass": False,
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
        print(f"ERROR  [{area}] {name}: {exc}")
        return None
    after = state()
    changed = before != after
    status, detail = None, ""
    if isinstance(out, tuple):
        status, detail, _ = out
    else:
        detail = getattr(out, "message", lambda: "")() if out is not None else ""
        status = getattr(out, "status", None)
    verdict = "saved" if changed else "refused"
    if expect.startswith("status:"):
        ok, verdict = status == int(expect[7:]), f"HTTP {status}"
    elif expect == "observe":
        ok = status is None or status < 500
    else:
        ok = verdict == expect
    silent = (
        expect == "refused"
        and verdict == "refused"
        and (not detail or detail.startswith("no redirect and no message"))
    )
    if silent:
        ok, verdict = False, "refused SILENTLY (no message shown to the user)"
    if status is not None and status >= 500:
        ok, verdict = False, f"HTTP {status}"
    results.append(
        {
            "area": area,
            "name": name,
            "expect": expect,
            "verdict": verdict,
            "pass": ok,
            "detail": detail[:240],
            "note": note,
        }
    )
    print(
        f"{'PASS' if ok else 'FAIL'}  [{area}] {name}  -> {verdict}"
        + (f"  ({detail[:110]})" if detail and (not ok or expect in ("refused", "observe")) else "")
    )
    return out


def refused(area, name, fn, **kw):
    return case(area, name, "refused", lambda: _msg(fn), **kw)


def _msg(fn):
    r = fn()
    return (r.status, follow(admin, r) if r.saved else r.message(), r)


# =========================== STOCK IN: what the Excel sheets put in a quantity box =========================
A = "Stock IN"
for text, why in [
    ("22 NOS", "the Excel quantity text"),
    ("1NOS", "Excel, no space"),
    ("`7NOS", "Excel typo with a backtick"),
    ("0", "zero"),
    ("-5", "negative"),
    ("2.5", "decimal"),
    ("1e3", "scientific notation"),
    (" ", "blank space"),
    ("٣", "Arabic digit"),
    ("1000001", "over the 1,000,000 limit"),
    ("99999999999999999999", "20 digits"),
    ("12abc", "digits then letters"),
]:
    refused(A, f"quantity {text!r} ({why})", lambda t=text: stock_in([(FIX, t)]))
refused(A, "no item lines at all", lambda: stock_in([]))
refused(A, "an item that does not exist (id 999999)", lambda: stock_in([(999999, 1)]))
refused(A, "date in the future", lambda: stock_in([(FIX, 1)], date_="2099-01-01"))
refused(A, "date missing", lambda: stock_in([(FIX, 1)], date_=""))
refused(A, "date is not a date", lambda: stock_in([(FIX, 1)], date_="31-02-2026"))
refused(A, "supplier not chosen", lambda: stock_in([(FIX, 1)], company=""))
refused(A, "PKD written as a word, not YYYY-MM", lambda: stock_in([(FIX, 1, "B1", "May 2026")]))
refused(A, "PKD month 13", lambda: stock_in([(FIX, 1, "B1", "2026-13")]))
refused(A, "DC / bill number over 60 characters", lambda: stock_in([(FIX, 1)], ref="D" * 61))
case(
    A,
    "a valid IN is saved (control)",
    "saved",
    lambda: _msg(lambda: stock_in([(FIX, 2, "B2", "2026-02")], ref="DC 5012")),
)
case(
    A,
    "very long remarks (5,000 characters)",
    "observe",
    lambda: _msg(lambda: stock_in([(FIX, 1)], note="x" * 5000)),
    note="a judgement call: should remarks be capped?",
)
case(
    A,
    "name with HTML and an Excel formula in it is saved as text",
    "saved",
    lambda: _msg(
        lambda: stock_in([(FIX, 1)], ref='=HYPERLINK("http://x","y")', note="<script>alert(1)</script>")
    ),
)


def replay_once():
    page, csrf, token = admin.form("/stock/in/")
    data = (
        [
            ("entry_date", TODAY),
            ("location", loc["Svkml"]),
            ("note", "replay"),
            ("subtype", "SUPPLIER"),
            ("company", comp["Wipro Lighting"]),
            ("party", ""),
            ("ref", "REPLAY"),
        ]
        + lines([(FIX, 1)])
        + [("csrfmiddlewaretoken", csrf), ("entry_token", token)]
    )
    n0 = one("select count(*) from inventory_stockentry")
    for _ in range(2):
        admin.s.post(
            BASE + "/stock/in/", data=data, headers={"Referer": BASE + "/stock/in/"}, allow_redirects=False
        )
    n1 = one("select count(*) from inventory_stockentry")
    return (200, f"{n1 - n0} entry saved from 2 identical posts", type("R", (), {"status": 200})())


case(A, "the same form posted twice (double click) saves exactly once", "saved", replay_once)
assert one("select count(*) from inventory_stockentry where ref='REPLAY'") == 1, (
    "double-click saved more than once"
)


def no_token():
    page, csrf, token = admin.form("/stock/in/")
    data = (
        [
            ("entry_date", TODAY),
            ("location", loc["Svkml"]),
            ("subtype", "SUPPLIER"),
            ("company", comp["Wipro Lighting"]),
        ]
        + lines([(FIX, 1)])
        + [("csrfmiddlewaretoken", csrf)]
    )
    r = admin.s.post(
        BASE + "/stock/in/", data=data, headers={"Referer": BASE + "/stock/in/"}, allow_redirects=False
    )
    from client import Result

    res = Result(r.status_code, r.headers.get("Location", ""), r.text)
    return (r.status_code, res.message(), res)


case(A, "a form sent without its one-time token is refused as expired", "refused", no_token)

# =========================== STOCK OUT / TRANSFER / ADJUST =================================================
B = "Stock rules"
have = one("select qty from inventory_stockbalance where item_id=%s and location_id=%s", FIX, loc["Svkml"])
refused(
    B, f"OUT of {have + 1} when only {have} are there (oversell by 1)", lambda: stock_out([(FIX, have + 1)])
)
refused(
    B, "OUT from a location that holds none of the item", lambda: stock_out([(FIX, 1)], where="Kartika Class")
)
refused(B, "OUT with nobody named", lambda: stock_out([(FIX, 1)], party=""))
refused(
    B,
    "OUT dated before the item was ever received (2026-01-01)",
    lambda: stock_out([(FIX, 1)], date_="2026-01-01"),
)
refused(
    B,
    "OUT with the same item on two lines that together exceed stock",
    lambda: stock_out([(FIX, have), (FIX, 1)]),
)
case(
    B,
    f"OUT of exactly {have} (everything) is allowed",
    "saved",
    lambda: _msg(lambda: stock_out([(FIX, have)])),
)
refused(B, "OUT of 1 more once it is empty", lambda: stock_out([(FIX, 1)]))
refused(
    B,
    "Transfer to the same location",
    lambda: entry(admin, "/stock/transfer/", [(FIX, 1)], where="Svkml", to_location=loc["Svkml"]),
)
refused(
    B,
    "Transfer more than is available",
    lambda: entry(
        admin, "/stock/transfer/", [(RICH_ID, RICH_QTY + 1)], where="Vizag Office", to_location=loc["Svkml"]
    ),
)
case(
    B,
    "a valid Transfer is saved",
    "saved",
    lambda: _msg(
        lambda: entry(
            admin, "/stock/transfer/", [(RICH_ID, 1)], where="Vizag Office", to_location=loc["Svkml"]
        )
    ),
)
refused(
    B,
    "Adjust with no reason",
    lambda: entry(
        admin,
        "/stock/adjust/",
        [(RICH_ID, RICH_QTY, "", "", RICH_QTY)],
        where="Vizag Office",
        reason="",
        note="x",
    ),
)
refused(
    B,
    "Adjust with no note",
    lambda: entry(
        admin,
        "/stock/adjust/",
        [(RICH_ID, RICH_QTY - 1, "", "", RICH_QTY)],
        where="Vizag Office",
        reason="DAMAGED",
        note="",
    ),
)
refused(
    B,
    "Adjust to the quantity already held",
    lambda: entry(
        admin,
        "/stock/adjust/",
        [(RICH_ID, RICH_QTY - 1, "", "", RICH_QTY - 1)],
        where="Vizag Office",
        reason="COUNT",
        note="same",
    ),
)
refused(
    B,
    "Adjust where the page was stale (system count changed)",
    lambda: entry(
        admin,
        "/stock/adjust/",
        [(RICH_ID, 1, "", "", RICH_QTY + 50)],
        where="Vizag Office",
        reason="COUNT",
        note="stale",
    ),
)
refused(
    B,
    "Adjust to a negative count",
    lambda: entry(
        admin,
        "/stock/adjust/",
        [(RICH_ID, -1, "", "", RICH_QTY - 1)],
        where="Vizag Office",
        reason="LOST",
        note="neg",
    ),
)
now = one(
    "select qty from inventory_stockbalance where item_id=%s and location_id=%s", RICH_ID, loc["Vizag Office"]
)
case(
    B,
    "a valid Adjust is saved",
    "saved",
    lambda: _msg(
        lambda: entry(
            admin,
            "/stock/adjust/",
            [(RICH_ID, now - 1, "", "", now)],
            where="Vizag Office",
            reason="DAMAGED",
            note="one cracked",
        )
    ),
)

# =========================== UNDO =============================================================================
C = "Undo"
IN_NO = one(
    "select number from inventory_stockentry where kind='IN' and ref='DC 5012' order by id desc limit 1"
)
OUT_NO = one(
    "select number from inventory_stockentry where kind='OUT' and party='Rigour Site' order by id desc limit 1"
)


def undo(number, reason):
    r = admin.post(
        f"/entries/{number}/undo/", {"reason": reason}, page_path=f"/entries/{number}/", token=False
    )
    return (r.status, follow(admin, r), r)


case(C, "Undo with no reason", "refused", lambda: undo(OUT_NO, ""))
case(C, "Undo an OUT with a reason", "saved", lambda: undo(OUT_NO, "Rigour: wrong site"))
case(C, "Undo the same OUT a second time", "refused", lambda: undo(OUT_NO, "again"))
rev = one("select number from inventory_stockentry where reverses_id is not null order by id desc limit 1")
case(C, "Undo a reversal entry", "refused", lambda: undo(rev, "undo the undo"))
VIS_OUT = one(
    "select out_entry.number from complaints_visit v join inventory_stockentry out_entry on out_entry.id=v.out_entry_id order by v.id limit 1"
)
case(
    C,
    "Undo an entry that belongs to a complaint visit (must use Undo parts given)",
    "refused",
    lambda: undo(VIS_OUT, "wrong place"),
)
MARK_NO = one(
    "select number from inventory_stockentry where subtype in ('MARK_DEFECTIVE') order by id limit 1"
)
case(
    C,
    "Undo a Mark-defective entry (pieces own it)",
    "refused",
    lambda: undo(MARK_NO, "wrong place") if MARK_NO else (200, "no such entry", None),
)
case(
    C,
    "Undo an entry that does not exist",
    "status:404",
    lambda: (
        admin.post("/entries/IN-9999/undo/", {"reason": "x"}, page_path="/stock/in/", token=False).status,
        "",
        None,
    ),
)

# =========================== SITES / TECHNICIANS / PHONES (the Excel's messy contacts) ==========================
D = "Sites & phones"


def site(name, phone="", city="Vizag", contact="Rigour"):
    r = admin.post_json(
        "/sites/quick-create/",
        {"ns-name": name, "ns-city": city, "ns-contact_name": contact, "ns-phone": phone, "ns-address": ""},
        "/complaints/new/",
    )
    body = r.json()
    return (
        r.status_code,
        body.get("error", "saved") if not body.get("ok") else "saved",
        type("R", (), {"status": r.status_code})(),
    )


for phone, why in [
    ("996394502", "9 digits, from the Excel"),
    ("88410", "5 digits, from the Excel"),
    ("98765abcde", "letters"),
    ("0000000000", "all zeros"),
    ("12345678901234567890", "20 digits"),
]:
    case(D, f"site phone {phone!r} ({why})", "refused", lambda p=phone: site(f"Rigour Site {p}", p))
for phone, why in [
    ("8790022266", "10-digit mobile, from the Excel"),
    ("0891-2745566", "STD landline"),
    ("+91 98765 43211", "with +91 and spaces"),
    ("", "no phone"),
]:
    case(
        D, f"site phone {phone!r} ({why})", "saved", lambda p=phone: site(f"Rigour Site ok {p or 'blank'}", p)
    )
case(
    D,
    "site name with a semicolon, as in 'Chenna Keshava;lu'",
    "observe",
    lambda: site("Rigour Keshava;lu Works", "9848099999", contact="Chenna Keshava;lu"),
)
case(
    D,
    "site name with double spaces and odd case ('Iocl  Office Holiday Home')",
    "observe",
    lambda: site("Iocl  Office Holiday Home"),
)
case(
    D,
    "the same site again with other spacing and case",
    "refused",
    lambda: site("iocl office   holiday home"),
)
case(D, "site name left empty", "refused", lambda: site(""))
case(D, "site name of 121 characters", "refused", lambda: site("S" * 121))
case(
    D,
    "technician with a landline (technicians take mobiles only)",
    "refused",
    lambda: admin.post("/technicians/", {"name": "Rigour Tech L", "phone": "0891-2745566"}),
)
case(
    D,
    "technician with a valid mobile",
    "saved",
    lambda: _msg(lambda: admin.post("/technicians/", {"name": "Rigour Tech M", "phone": "9123456780"})),
)
case(
    D,
    "technician name already in use (other case)",
    "refused",
    lambda: _msg(lambda: admin.post("/technicians/", {"name": "RAMU", "phone": "9123456781"})),
)

# =========================== COMPLAINTS =======================================================================
E = "Complaints"


def new_complaint(**over):
    d = {
        "site": SITE_ID,
        "contact_name": "",
        "phone": "",
        "company": comp["Wipro Lighting"],
        "company_ref": "",
        "reported_on": "2026-10-20",
        "qty_affected": 3,
        "fault": "Rigour: lights off",
        "priority": "NORMAL",
    }
    d.update(over)
    return admin.post("/complaints/new/", list(d.items()))


refused(E, "complaint reported in the future", lambda: new_complaint(reported_on="2099-01-01"))
refused(E, "complaint with quantity 0", lambda: new_complaint(qty_affected=0))
refused(E, "complaint with quantity 'abc'", lambda: new_complaint(qty_affected="abc"))
refused(E, "complaint with no fault described", lambda: new_complaint(fault=""))
refused(E, "complaint with no site", lambda: new_complaint(site=""))
refused(E, "complaint for a site that does not exist", lambda: new_complaint(site=999999))
refused(E, "complaint with a 9-digit phone typed over the site's", lambda: new_complaint(phone="996394502"))
refused(E, "company's complaint number over 60 characters", lambda: new_complaint(company_ref="W" * 61))
refused(E, "invalid priority", lambda: new_complaint(priority="SUPERURGENT"))
case(E, "valid complaint (control)", "saved", lambda: _msg(lambda: new_complaint(fault="Rigour: valid")))
case(
    E,
    "an identical second complaint (same site, same fault, same day)",
    "observe",
    lambda: _msg(lambda: new_complaint(fault="Rigour: valid")),
    note="the Excel lists the same site many times; is a duplicate warning wanted?",
)
case(
    E,
    "fault text of 10,000 characters",
    "observe",
    lambda: _msg(lambda: new_complaint(fault="f" * 10000)),
    note="is there a limit?",
)
NEW_CMP = one("select number from complaints_complaint order by id desc limit 1")
STAMP_REPORTED = one("select reported_on from complaints_complaint where number=%s", OPEN_CMP)


def visit(number, **over):
    d = {
        "visit_date": TODAY,
        "work_done": "Rigour visit",
        "location": loc["Vizag Office"],
        "next_status": "ATTENDED",
        "technicians": TECH_ID,
    }
    d.update(over)
    rows = d.pop("rows", [])
    pairs = [(k, v) for k, v in d.items()] + rows
    return admin.post(f"/complaints/{number}/visit/", pairs)


refused(E, "visit dated before the complaint was reported", lambda: visit(OPEN_CMP, visit_date="2000-01-01"))
refused(E, "visit dated in the future", lambda: visit(OPEN_CMP, visit_date="2099-01-01"))
refused(E, "visit with no technician", lambda: visit(OPEN_CMP, technicians=""))
refused(E, "visit with no work described", lambda: visit(OPEN_CMP, work_done=""))
refused(
    E,
    "visit giving more parts than exist",
    lambda: visit(OPEN_CMP, rows=[("part_item", RICH_ID), ("part_qty", 99999)]),
)
refused(
    E,
    "visit that closes the complaint (a visit may not close)",
    lambda: visit(OPEN_CMP, next_status="CLOSED"),
)
refused(E, "visit on a closed complaint", lambda: visit(CLOSED_CMP))
case(
    E,
    "visit collecting a failed part with no fault written",
    "observe",
    lambda: _msg(
        lambda: visit(
            OPEN_CMP,
            rows=[
                ("col_item", RICH_ID),
                ("col_qty", 1),
                ("col_batch", "B1"),
                ("col_pkd", "2026-01"),
                ("col_fault", ""),
            ],
        )
    ),
    note="Mark defective requires a fault; a part collected at a visit does not. The dispatch list to the company shows the fault per piece.",
)
case(
    E,
    "visit with parts and a collected part (control)",
    "saved",
    lambda: _msg(
        lambda: visit(
            OPEN_CMP,
            rows=[
                ("part_item", RICH_ID),
                ("part_qty", 1),
                ("col_item", RICH_ID),
                ("col_qty", 1),
                ("col_batch", "RIGB1"),
                ("col_pkd", "2026-01"),
                ("col_fault", "Rigour: burnt"),
            ],
        )
    ),
)
case(
    E,
    "collecting more failed parts than parts given",
    "observe",
    lambda: _msg(
        lambda: visit(
            OPEN_CMP,
            rows=[
                ("part_item", RICH_ID),
                ("part_qty", 1),
                ("col_item", RICH_ID),
                ("col_qty", 5),
                ("col_batch", "RIGB2"),
                ("col_pkd", "2026-01"),
                ("col_fault", "Rigour: five came back"),
            ],
        )
    ),
    note="a technician may bring back more than he was given",
)


def status(number, to, note="", client=None):
    c = client or admin
    r = c.post(f"/complaints/{number}/status/", {"to": to, "note": note}, page_path=f"/complaints/{number}/")
    return (r.status, follow(c, r), r)


case(E, "status jump Not attended -> Resolved", "refused", lambda: status(NOT_ATT, "RESOLVED"))
case(E, "status jump Not attended -> Closed", "refused", lambda: status(NOT_ATT, "CLOSED"))
case(E, "status that does not exist", "refused", lambda: status(NOT_ATT, "SATURDAY"))
case(
    E,
    "'Closed Not wipro product' typed as a status",
    "refused",
    lambda: status(NOT_ATT, "Closed Not wipro product"),
)
case(
    E,
    "move a Closed complaint to Attended as Office (reopen is Admin only)",
    "refused",
    lambda: status(CLOSED_CMP, "ATTENDED", client=office),
)
case(
    E,
    "move a Closed complaint to Attended as Admin (reopen)",
    "saved",
    lambda: status(CLOSED_CMP, "ATTENDED", "Rigour: reopened"),
)
case(E, "valid move Not attended -> Attended", "saved", lambda: status(NOT_ATT, "ATTENDED"))


def not_covered(number, reason, note="", client=None):
    c = client or admin
    r = c.post(
        f"/complaints/{number}/not-covered/",
        {"reason": reason, "note": note},
        page_path=f"/complaints/{number}/",
    )
    return (r.status, follow(c, r), r)


case(E, "Not covered with reason Other and no note", "refused", lambda: not_covered(NEW_CMP, "OTHER", ""))
case(E, "Not covered with an unknown reason", "refused", lambda: not_covered(NEW_CMP, "BECAUSE", ""))
case(
    E,
    "Not covered with a proper reason",
    "saved",
    lambda: not_covered(NEW_CMP, "OUT_OF_WARRANTY", "Rigour: out of warranty"),
)
case(
    E,
    "Not covered again on an already closed complaint",
    "refused",
    lambda: not_covered(NEW_CMP, "CANCELLED", "again"),
)
case(
    E,
    "status change on a complaint that does not exist",
    "status:404",
    lambda: (
        admin.post(
            "/complaints/CMP-9999/status/", {"to": "ATTENDED"}, page_path="/complaints/", token=False
        ).status,
        "",
        None,
    ),
)

# =========================== HIDDEN MASTERS ======================================================================
F = "Hidden masters"
H_SITE = one("select id from complaints_site where name like 'Rigour Site ok blank'")


def toggle(pk, active, client=None):
    c = client or admin
    r = c.post(f"/sites/{pk}/toggle/", {"active": active}, page_path=f"/sites/{pk}/")
    return (r.status, follow(c, r), r)


case(F, "Office hides a site (Admin only)", "status:403", lambda: (toggle(H_SITE, "0", office)[0], "", None))
case(F, "Admin hides a site", "saved", lambda: toggle(H_SITE, "0"))
refused(F, "file a complaint at the hidden site", lambda: new_complaint(site=H_SITE))
case(
    F,
    "toggle with a missing 'active' field",
    "refused",
    lambda: (lambda r: (r.status, follow(admin, r), r))(
        admin.post(f"/sites/{H_SITE}/toggle/", {}, page_path=f"/sites/{H_SITE}/")
    ),
)
case(F, "Admin shows the site again", "saved", lambda: toggle(H_SITE, "1"))

# =========================== DEFECTIVES ===========================================================================
G = "Defectives"
refused(
    G,
    "Mark defective more than is in stock",
    lambda: entry(admin, "/defectives/mark/", [(FIX, 99999, "", "", "", "x")], where="Svkml"),
)
refused(
    G,
    "Mark defective with no fault written",
    lambda: entry(admin, "/defectives/mark/", [(RICH_ID, 1, "", "", "", "")], where="Vizag Office"),
)
refused(
    G,
    "Mark defective with a 201-character fault",
    lambda: entry(admin, "/defectives/mark/", [(RICH_ID, 1, "", "", "", "f" * 201)], where="Vizag Office"),
)
case(
    G,
    "Mark defective, valid (control)",
    "saved",
    lambda: _msg(
        lambda: entry(
            admin,
            "/defectives/mark/",
            [(RICH_ID, 1, "RIGB3", "2026-01", "", "Rigour: cracked")],
            where="Vizag Office",
        )
    ),
)


def new_batch(company, tags, note=""):
    return admin.post(
        "/defectives/batches/new/", [("company", comp[company]), ("note", note)] + [("tag", t) for t in tags]
    )


refused(G, "batch for Wipro that includes a Havells piece", lambda: new_batch("Wipro Lighting", [HAV_TAG]))
refused(G, "batch with a piece tag that does not exist", lambda: new_batch("Wipro Lighting", ["DEF-9999"]))
refused(G, "batch note over 200 characters", lambda: new_batch("Wipro Lighting", [WIPRO_TAG], "n" * 201))
case(G, "empty draft batch for a company (allowed)", "saved", lambda: _msg(lambda: new_batch("Havells", [])))
EMPTY_RB = one("select number from defectives_returnbatch order by id desc limit 1")


def dispatch(rb, **over):
    d = {"dispatched_on": TODAY, "courier": "Blue Dart", "docket_no": "RIG123"}
    d.update(over)
    return admin.post(f"/defectives/batches/{rb}/dispatch/", d, page_path=f"/defectives/batches/{rb}/")


refused(G, "dispatch an empty batch", lambda: dispatch(EMPTY_RB))
case(
    G,
    "add a Havells piece to the empty Havells batch",
    "saved",
    lambda: (lambda r: (r.status, r.message(), r))(
        admin.post(
            f"/defectives/batches/{EMPTY_RB}/add/",
            {"tag_text": HAV_TAG},
            page_path=f"/defectives/batches/{EMPTY_RB}/",
        )
    ),
)
refused(G, "dispatch with no courier", lambda: dispatch(EMPTY_RB, courier=""))
refused(G, "dispatch with no docket number", lambda: dispatch(EMPTY_RB, docket_no=""))
refused(G, "courier over 60 characters", lambda: dispatch(EMPTY_RB, courier="C" * 61))
refused(G, "docket over 40 characters", lambda: dispatch(EMPTY_RB, docket_no="D" * 41))
refused(G, "dispatch dated in the future", lambda: dispatch(EMPTY_RB, dispatched_on="2099-01-01"))
refused(
    G, "dispatch dated before the batch was created", lambda: dispatch(EMPTY_RB, dispatched_on="2026-01-01")
)
refused(
    G,
    "settle a batch that has not been dispatched",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/settle/",
        [("outcome", "REPLACED"), ("settled_on", TODAY), ("to_location", loc["Svkml"]), ("tag", HAV_TAG)],
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
case(
    G,
    "dispatch the Havells batch (control)",
    "saved",
    lambda: (lambda r: (r.status, follow(admin, r), r))(dispatch(EMPTY_RB)),
)
case(
    G,
    "dispatch it a second time",
    "refused",
    lambda: (lambda r: (r.status, follow(admin, r), r))(dispatch(EMPTY_RB)),
)
refused(
    G,
    "remove a piece from a dispatched batch",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/remove/",
        {"tag": HAV_TAG},
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
refused(
    G,
    "settle with no outcome chosen",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/settle/",
        [("outcome", ""), ("settled_on", TODAY), ("tag", HAV_TAG)],
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
refused(
    G,
    "settle as Replaced without saying where the stock goes",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/settle/",
        [("outcome", "REPLACED"), ("settled_on", TODAY), ("to_location", ""), ("tag", HAV_TAG)],
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
refused(
    G,
    "settle dated before the dispatch",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/settle/",
        [
            ("outcome", "REPLACED"),
            ("settled_on", "2026-01-01"),
            ("to_location", loc["Svkml"]),
            ("tag", HAV_TAG),
        ],
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
case(
    G,
    "settle the Havells piece as Replaced (control)",
    "saved",
    lambda: (lambda r: (r.status, follow(admin, r), r))(
        admin.post(
            f"/defectives/batches/{EMPTY_RB}/settle/",
            [("outcome", "REPLACED"), ("settled_on", TODAY), ("to_location", loc["Svkml"]), ("tag", HAV_TAG)],
            page_path=f"/defectives/batches/{EMPTY_RB}/",
        )
    ),
)
refused(
    G,
    "settle the same piece a second time",
    lambda: admin.post(
        f"/defectives/batches/{EMPTY_RB}/settle/",
        [("outcome", "REPAIRED"), ("settled_on", TODAY), ("to_location", loc["Svkml"]), ("tag", HAV_TAG)],
        page_path=f"/defectives/batches/{EMPTY_RB}/",
    ),
)
SCRAP_TAG = one("select tag from defectives_defectivepiece where status='IN_STORE' order by id desc limit 1")


def scrap(tag, reason, note=""):
    r = admin.post(
        "/defectives/pieces/bulk/",
        [("action", "scrap"), ("reason", reason), ("note", note), ("tag", tag)],
        page_path="/defectives/pieces/",
    )
    return (r.status, follow(admin, r), r)


case(G, "scrap a piece with no reason", "refused", lambda: scrap(SCRAP_TAG, ""))
case(G, "scrap with an unknown reason", "refused", lambda: scrap(SCRAP_TAG, "FUN"))
case(G, "scrap with reason Other and no note", "refused", lambda: scrap(SCRAP_TAG, "OTHER", ""))
case(G, "scrap a piece correctly", "saved", lambda: scrap(SCRAP_TAG, "BURNT", "Rigour: burnt"))
case(G, "scrap the same piece again", "refused", lambda: scrap(SCRAP_TAG, "BURNT", "again"))
case(
    G,
    "bulk action with nothing ticked",
    "refused",
    lambda: (lambda r: (r.status, follow(admin, r), r))(
        admin.post(
            "/defectives/pieces/bulk/",
            [("action", "scrap"), ("reason", "BURNT")],
            page_path="/defectives/pieces/",
        )
    ),
)


def _anon_post():
    """An anonymous POST must be turned away (to login, or 403 when it has no CSRF token) and save nothing."""
    before = state()
    r = anon.s.post(BASE + "/stock/in/", data={"entry_date": TODAY}, allow_redirects=False)
    return (302 if r.status_code in (302, 403) and state() == before else 999, f"HTTP {r.status_code}", None)


# =========================== PERMISSIONS / SECURITY ================================================================
P = "Permissions & security"
case(
    P,
    "anonymous visitor opens Stock IN",
    "status:302",
    lambda: (anon.get("/stock/in/", allow_redirects=False).status_code, "", None),
)
case(
    P,
    "anonymous visitor posts a Stock IN: sent to login, nothing saved",
    "status:302",
    lambda: _anon_post(),
)
for url in ("/masters/", "/admin/"):
    code = office.get(url, allow_redirects=False).status_code
    ok = code in (302, 403, 404)
    results.append(
        {
            "area": P,
            "name": f"Office user opens {url} (Admin only): refused",
            "expect": "403, 404 or redirect",
            "verdict": f"HTTP {code}",
            "pass": ok,
            "detail": "",
        }
    )
    print(f"{'PASS' if ok else 'FAIL'}  [{P}] Office opens {url} -> {code}")
case(
    P,
    "Office opens /masters/ gets 403",
    "status:403",
    lambda: (office.get("/masters/", allow_redirects=False).status_code, "", None),
)
case(
    P,
    "Office posts a Stock IN (Office may enter stock)",
    "saved",
    lambda: _msg(lambda: stock_in([(FIX, 1)], client=office)),
)


def csrf_missing():
    page, csrf, token = admin.form("/stock/in/")
    r = admin.s.post(
        BASE + "/stock/in/",
        data=[
            ("entry_date", TODAY),
            ("location", loc["Svkml"]),
            ("subtype", "SUPPLIER"),
            ("company", comp["Wipro Lighting"]),
            ("entry_token", token),
        ]
        + lines([(FIX, 1)]),
        allow_redirects=False,
    )
    return (r.status_code, "", None)


case(P, "a POST with no CSRF token is rejected", "status:403", csrf_missing)
case(
    P,
    "GET on a POST-only address (/sites/quick-create/)",
    "status:405",
    lambda: (admin.get("/sites/quick-create/", allow_redirects=False).status_code, "", None),
)


def _login_next(target):
    """Log in with a hostile ?next= and report where the app sends the user."""
    s = requests.Session()
    page = s.get(f"{BASE}/login/", params={"next": target}).text
    csrf = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', page).group(1)
    r = s.post(
        f"{BASE}/login/",
        data={"username": OFFICE, "password": PASSWORD, "csrfmiddlewaretoken": csrf, "next": target},
        headers={"Referer": f"{BASE}/login/"},
        allow_redirects=False,
    )
    where = r.headers.get("Location", "")
    return (200 if where.startswith("/") and not where.startswith("//") else 999, f"sent to {where!r}", None)


for hostile in ("//evil.example/x", "https://evil.example/", r"/\evil.example", "javascript:alert(1)"):
    case(P, f"login with next={hostile!r} stays on this site", "status:200", lambda t=hostile: _login_next(t))
case(P, "login with a genuine next=/stock/ is honoured", "status:200", lambda: _login_next("/stock/"))
case(
    P,
    "wrong password is refused",
    "observe",
    lambda: (200, "login ok" if Client(BASE).login(ADMIN, "wrong-password") else "login refused", None),
)
XSS_NO = one(
    "select number from inventory_stockentry where note like '%%<script>%%' order by id desc limit 1"
)
page = admin.get(f"/entries/{XSS_NO}/").text
ok = "<script>alert(1)</script>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
results.append(
    {
        "area": P,
        "name": "text typed as <script> is shown as text on the entry page, never run",
        "expect": "escaped",
        "verdict": "escaped" if ok else "RAW HTML",
        "pass": ok,
        "detail": XSS_NO,
    }
)
print(f"{'PASS' if ok else 'FAIL'}  [{P}] <script> typed in remarks is escaped on {XSS_NO}")

# =========================== PAGES NEVER CRASH ON ODD QUERIES =====================================================
Q = "Pages & odd queries"
pages = [
    "/",
    "/stock/",
    "/movements/",
    "/low-stock/",
    "/items/",
    "/complaints/",
    "/complaints/list/",
    "/sites/",
    "/technicians/",
    "/defectives/",
    "/defectives/pieces/",
    "/defectives/batches/",
]
odd = [
    "?page=999999",
    "?page=abc",
    "?page=-1",
    "?sort=zzz&dir=sideways",
    "?q=%00",
    "?q=" + "a" * 3000,
    "?date_from=not-a-date",
    "?date_to=2099-99-99",
    "?status=NOPE",
    "?location=abc",
    "?item=999999999999999999999",
]
bad = []
for p in pages:
    for o in odd:
        r = admin.s.get(BASE + p + o, allow_redirects=True, timeout=60)
        if r.status_code >= 500:
            bad.append(f"{p}{o[:40]} -> {r.status_code}")
results.append(
    {
        "area": Q,
        "name": f"{len(pages) * len(odd)} odd query strings on {len(pages)} list pages: no server error",
        "expect": "status<500",
        "verdict": "ok" if not bad else "server errors",
        "pass": not bad,
        "detail": "; ".join(bad[:8]),
    }
)
print(
    f"{'PASS' if not bad else 'FAIL'}  [{Q}] {len(pages) * len(odd)} odd query strings on {len(pages)} pages"
    + (f"  ({bad[:5]})" if bad else "")
)
for path in (
    "/items/999999/",
    "/entries/NOPE-1/",
    "/complaints/NOPE/",
    "/defectives/pieces/NOPE/",
    "/defectives/batches/NOPE/",
    "/sites/999999/",
):
    s = admin.s.get(BASE + path, allow_redirects=False, timeout=60).status_code
    results.append(
        {
            "area": Q,
            "name": f"unknown address {path}",
            "expect": "status:404",
            "verdict": f"HTTP {s}",
            "pass": s == 404,
            "detail": "",
        }
    )
    print(f"{'PASS' if s == 404 else 'FAIL'}  [{Q}] unknown address {path} -> {s}")

# =========================== TEXT TYPED LIKE A FORMULA STAYS TEXT IN EXCEL ==========================================
import io  # noqa: E402

import openpyxl  # noqa: E402

X = "Excel export"
xl = admin.s.get(BASE + "/movements/export/?date_from=2026-01-01&date_to=2026-10-22", timeout=120)
sheet = openpyxl.load_workbook(io.BytesIO(xl.content)).active
found = [
    c for row in sheet.iter_rows() for c in row if isinstance(c.value, str) and "HYPERLINK" in c.value.upper()
]
ok = bool(found) and all(c.data_type != "f" for c in found)
results.append(
    {
        "area": X,
        "name": "'=HYPERLINK(...)' typed as a DC number is in the movements export as text, not a formula",
        "expect": "text",
        "verdict": "text"
        if ok
        else f"not found or a formula: {[(c.coordinate, c.data_type) for c in found][:3]}",
        "pass": ok,
        "detail": "",
    }
)
print(f"{'PASS' if ok else 'FAIL'}  [{X}] a typed formula is stored as text ({len(found)} cell(s) found)")

failed = [r for r in results if not r["pass"]]
(HERE / "matrix-results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
print(f"\n{len(results)} cases: {len(results) - len(failed)} as expected, {len(failed)} differ")
for r in failed:
    print(
        f"  DIFFERS [{r['area']}] {r['name']}: expected {r['expect']}, got {r['verdict']}  {r['detail'][:150]}"
    )
sys.exit(1 if failed else 0)
