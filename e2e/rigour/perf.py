"""Phase 5: how fast are the pages on the loaded data, and do queries grow with the number of rows (N+1)?

    DATABASE_URL=postgresql://postgres:@127.0.0.1:52207/svkml_rigour uv run python e2e/rigour/perf.py

Uses Django's test client in-process (no network), so the times are the app's own: view + queries + template.
For every page: median of 5 timed requests, and the number of SQL queries. For list pages it also loads 10
rows and 50 rows: if the query count grows with the rows, there is an N+1 problem.
Flags: any page over 1.0 s, any list whose queries grow by more than 3 from 10 to 50 rows.
"""

import os
import statistics
import sys
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
sys.path.insert(0, os.getcwd())
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

c = Client(HTTP_HOST="127.0.0.1")
c.force_login(get_user_model().objects.get(username="admin"))


def q(sql):
    with connection.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


item = q(
    "select id from inventory_item order by (select count(*) from inventory_stockline l where l.item_id=inventory_item.id) desc limit 1"
)
entry = q("select number from inventory_stockentry where kind='IN' order by id limit 1")
cmp_ = q(
    "select c.number from complaints_complaint c join complaints_visit v on v.complaint_id=c.id group by c.number order by count(*) desc limit 1"
)
piece = q("select tag from defectives_defectivepiece order by id desc limit 1")
batch = q("select number from defectives_returnbatch order by id limit 1")
site = q("select id from complaints_site order by id limit 1")

LISTS = [
    "/stock/",
    "/movements/?date_from=2026-01-01&date_to=2026-10-22",
    "/low-stock/",
    "/items/",
    "/complaints/list/?tab=all",
    "/defectives/pieces/",
    "/defectives/batches/",
    "/sites/",
    "/technicians/",
]
SINGLES = [
    "/",
    "/complaints/",
    "/defectives/",
    f"/items/{item}/",
    f"/items/{item}/?date_from=2026-01-01&date_to=2026-10-22",
    f"/entries/{entry}/",
    f"/complaints/{cmp_}/",
    f"/complaints/{cmp_}/visit/",
    f"/defectives/pieces/{piece}/",
    f"/defectives/batches/{batch}/",
    f"/sites/{site}/",
    "/stock/in/",
    "/stock/out/",
    "/defectives/mark/",
    "/complaints/new/",
    "/defectives/batches/new/?company=1",
    "/search/?q=LG66",
    "/search/?q=CMP-0010",
    "/search/?q=Laurus",
    "/masters/",
]
EXPORTS = [
    "/items/export/",
    "/stock/export/",
    "/movements/export/?date_from=2026-01-01&date_to=2026-10-22",
    "/low-stock/export/",
    "/complaints/export/?tab=all",
    "/complaints/pending/export/",
    "/defectives/export/",
    f"/defectives/batches/{batch}/export/",
]


def measure(url, runs=5):
    times = []
    status = None
    for _ in range(runs):
        t0 = time.perf_counter()
        r = c.get(url)
        times.append((time.perf_counter() - t0) * 1000)
        status = r.status_code
    with CaptureQueriesContext(connection) as ctx:
        c.get(url)
    return statistics.median(times), len(ctx), status


flags = []
print(f"{'page':70} {'median ms':>9} {'queries':>8}  status")
for group, urls in (("LISTS", LISTS), ("PAGES", SINGLES), ("EXPORTS", EXPORTS)):
    print(f"--- {group}")
    for url in urls:
        ms, n, status = measure(url)
        mark = ""
        if status != 200:
            mark, _ = f"  <-- HTTP {status}", flags.append(f"{url}: HTTP {status}")
        elif ms > 1000:
            mark, _ = "  <-- SLOW (over 1 s)", flags.append(f"{url}: {ms:.0f} ms")
        print(f"{url[:70]:70} {ms:9.0f} {n:8d}  {status}{mark}")

print("--- N+1 check: queries at 10 rows vs 50 rows per page")
for url in LISTS:
    sep = "&" if "?" in url else "?"
    _, n10, _ = measure(f"{url}{sep}size=10", 1)
    _, n50, _ = measure(f"{url}{sep}size=50", 1)
    mark = ""
    if n50 - n10 > 3:
        mark, _ = "  <-- queries grow with rows", flags.append(f"{url}: {n10} -> {n50} queries")
    print(f"{url[:70]:70} {n10:4d} -> {n50:4d}{mark}")

print(
    f"\ndata size: {q('select count(*) from inventory_stockline')} ledger lines, {q('select count(*) from complaints_complaint')} complaints, {q('select count(*) from defectives_defectivepiece')} pieces"
)
print("PERFORMANCE: nothing flagged" if not flags else "FLAGGED: " + "; ".join(flags))
sys.exit(1 if flags else 0)
