"""Phase 4b: what the screens say must match the lists and the Excel files behind them.

    uv run --with requests --with openpyxl python e2e/rigour/consistency.py http://127.0.0.1:8001 admin <password>

1. Every dashboard tile that is a count must equal the 'of N' total of the list it links to.
2. Every Excel export must have as many data rows as the list it exports (same filter).
(That text typed like a formula stays text in Excel is checked in scenario_matrix.py, which creates it.)
"""

import html as htmllib
import io
import re
import sys

import openpyxl
from client import Client, text_of

BASE, USER, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]
c = Client(BASE)
assert c.login(USER, PASSWORD)
failures = []


def check(name, ok, evidence=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {evidence}" if not ok and evidence else ""))
    if not ok:
        failures.append(name)


def list_total(path):
    page = text_of(c.get(path).text)
    m = re.search(r"of (\d+)\b", page[page.find("Showing") :]) if "Showing" in page else None
    return int(m.group(1)) if m else None


TILE = re.compile(
    r'<a [^>]*href="([^"]+)"[^>]*class="[^"]*(?:card|kpi|tile|stat)[^"]*"[^>]*>(.*?)</a>|<a [^>]*class="[^"]*(?:card|kpi|tile|stat)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
# These tiles show a different thing from the list's row count (a sum of quantities, or lines not entries)
# Findings reported to the user and waiting for a decision. They are printed as KNOWN, never hidden; delete the
# entry when the tile is fixed so that it is checked again.
KNOWN_OPEN = {
    "Answered by companies": "F3: the tile counts answered pieces but opens the batches list (a different unit)",
}
NOT_A_ROW_COUNT = ("In stock (all locations)",)

print("== dashboard tiles against the lists they open ==")
for page in ("/", "/complaints/", "/defectives/"):
    for m in TILE.finditer(c.get(page).text):
        href = htmllib.unescape(m.group(1) or m.group(3))
        body = text_of(m.group(2) or m.group(4))
        number = re.match(r"(\d[\d,]*)", body)
        if not number or any(s in body for s in NOT_A_ROW_COUNT):
            continue
        n, total = int(number.group(1).replace(",", "")), list_total(href)
        known = next((why for key, why in KNOWN_OPEN.items() if key in body), None)
        if known and n != total:
            print(f"KNOWN {page} tile '{body[:42]}' = {n}; its list shows {total}
        open finding: {known}")
            continue
        check(
            f"{page} tile '{body[:42]}' = {n}; its list ({href[:60]}) shows {total}",
            n == total,
            f"tile {n} vs list {total}",
        )

print("\n== menu badges against their lists ==")
side = c.get("/").text
for m in re.finditer(
    r'<a class="nav-link[^"]*"\s+href="([^"]+)".*?<span class="nav-link-title">([^<]+)</span>\s*(?:<span class="badge[^>]*>(\d+)</span>)?',
    side,
    re.S,
):
    href, label, badge = htmllib.unescape(m.group(1)), m.group(2).strip(), m.group(3)
    if badge:
        total = list_total(href)
        check(
            f"menu '{label}' badge {badge} = its list's {total}",
            total is not None and int(badge) == total,
            f"{href}",
        )

print("\n== Excel exports against the lists ==")


def sheet_rows(path):
    r = c.s.get(BASE + path, timeout=120)
    assert r.status_code == 200 and "spreadsheet" in r.headers.get("Content-Type", ""), (
        f"{path}: {r.status_code} {r.headers.get('Content-Type')}"
    )
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    rows = [[cell.value for cell in row] for row in ws.iter_rows()]
    header = next(i for i, row in enumerate(rows) if sum(v is not None for v in row) >= 3)
    data = [row for row in rows[header + 1 :] if any(v not in (None, "") for v in row)]
    return rows[header], data, ws


PAIRS = [
    ("/items/", "/items/export/"),
    ("/stock/", "/stock/export/"),
    ("/low-stock/", "/low-stock/export/"),
    (
        "/movements/?date_from=2026-01-01&date_to=2026-10-22",
        "/movements/export/?date_from=2026-01-01&date_to=2026-10-22",
    ),
    ("/complaints/list/?tab=all", "/complaints/export/?tab=all"),
    ("/complaints/list/?tab=NOT_ATTENDED", "/complaints/export/?tab=NOT_ATTENDED"),
    ("/complaints/list/?tab=finished", "/complaints/export/?tab=finished"),
]
for list_path, export_path in PAIRS:
    total = list_total(list_path)
    try:
        header, data, _ = sheet_rows(export_path)
    except Exception as exc:
        check(f"export {export_path}", False, str(exc))
        continue
    check(
        f"export {export_path}: {len(data)} data rows = list total {total}",
        len(data) == total,
        f"headers {header[:6]}",
    )
# the defective list export is a summary (one row per company / item / batch / PKD with a quantity column)
header, data, _ = sheet_rows("/defectives/export/")
qty_col = next(i for i, h in enumerate(header) if h and "qty" in str(h).lower())
in_store = list_total("/defectives/pieces/?status=IN_STORE")
check(
    f"defective list export: quantities add up to {sum(r[qty_col] or 0 for r in data)}; pieces in store = {in_store}",
    sum(r[qty_col] or 0 for r in data) == in_store,
)

# each return batch's dispatch list has one row per piece in the batch
batch_numbers = sorted(set(re.findall(r"RB-\d{4}", c.get("/defectives/batches/?size=50").text)))
for rb in batch_numbers:
    page = c.get(f"/defectives/batches/{rb}/").text
    pieces = len(set(re.findall(r'href="/defectives/pieces/(DEF-\d+)/"', page)))
    _, rows, _ = sheet_rows(f"/defectives/batches/{rb}/export/")
    check(f"dispatch list {rb}: {len(rows)} rows = {pieces} pieces on its page", len(rows) == pieces)

header, data, _ = sheet_rows("/complaints/pending/export/")
open_total = list_total("/complaints/list/")
check(
    f"pending-complaints export: {len(data)} rows = open complaints list {open_total}",
    len(data) == open_total,
)

print(
    f"\n{'ALL CONSISTENCY CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED: ' + '; '.join(failures)}"
)
sys.exit(1 if failures else 0)
