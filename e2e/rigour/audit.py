"""Phase 4: prove the numbers. Read-only SQL against the rigour database, plus the app's own cache check.

    uv run --with "psycopg[binary]" python e2e/rigour/audit.py [postgres url]

Compares the app with an INDEPENDENT answer: the stock model that build_scenarios.py kept while it generated
the timeline (plus the pieces that came back as good stock when batches were settled). Exit 0 = every check
passed. Each check prints PASS or FAIL with the evidence.
"""

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

HERE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
MODEL = "--no-model" not in sys.argv  # after the scenario tests there is extra data the model does not know
URL = ARGS[0] if ARGS else "postgresql://postgres:@127.0.0.1:52207/svkml_rigour"
scen = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
res = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
db = psycopg.connect(URL)
failures = []


def q(sql, *args):
    return db.execute(sql, args).fetchall()


def check(name, ok, evidence=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n        {evidence}" if evidence and not ok else ""))
    if not ok:
        failures.append(name)


def model_check(*args, **kwargs):
    """A check against the independent model; skipped with --no-model (extra data from later tests)."""
    if MODEL:
        check(*args, **kwargs)


# ---- 1. the app's own cache check ------------------------------------------------------------------------
out = subprocess.run(
    ["uv", "run", "python", "manage.py", "rebuild_stock_balances"],
    cwd=HERE.parent.parent,
    env={**__import__("os").environ, "DATABASE_URL": URL},
    capture_output=True,
    text=True,
)
check(
    "rebuild_stock_balances says 'Cache matches ledger.'",
    "Cache matches ledger" in out.stdout,
    out.stdout[-300:] + out.stderr[-300:],
)

# ---- 2. ledger sum equals the cached balance, per item and location -----------------------------------------
rows = q(
    """select coalesce(l.item_id, b.item_id), coalesce(l.location_id, b.location_id), coalesce(l.s,0), coalesce(b.qty,0)
       from (select item_id, location_id, sum(qty) s from inventory_stockline group by 1,2) l
       full join inventory_stockbalance b on b.item_id=l.item_id and b.location_id=l.location_id
       where coalesce(l.s,0) <> coalesce(b.qty,0)"""
)
check("every cached balance equals the sum of its ledger lines", not rows, str(rows[:5]))

# ---- 3. nothing negative ---------------------------------------------------------------------------------
neg = q("select item_id, location_id, qty from inventory_stockbalance where qty < 0")
check("no negative balance anywhere", not neg, str(neg[:5]))

# ---- 4. app stock equals the independent model -----------------------------------------------------------
store = q("select id from inventory_location where is_defective_store")[0][0]
loc_name = dict(q("select id, name from inventory_location"))
item_code = dict(q("select id, code from inventory_item"))
alias = res["ids"].get("alias", {})  # an Excel near-duplicate that the guard merged into an existing item
canon = lambda code: re.sub(r"\s+", "", alias.get(code, code)).upper()  # noqa: E731  (the app upper-cases codes)
expected = defaultdict(int)
for code, per_loc in scen["expected_good_stock_before_settles"].items():
    for loc, qty in per_loc.items():
        expected[(canon(code), loc)] += qty
for code, loc, qty in res["settle_effects"]:
    expected[(canon(code), loc)] += qty
actual = defaultdict(int)
for item_id, loc_id, qty in q(
    "select item_id, location_id, qty from inventory_stockbalance where location_id <> %s", store
):
    actual[(re.sub(r"\s+", "", item_code[item_id]).upper(), loc_name[loc_id])] += qty
diffs = [
    (k, expected.get(k, 0), actual.get(k, 0))
    for k in sorted(set(expected) | set(actual))
    if expected.get(k, 0) != actual.get(k, 0)
]
model_check(
    f"good stock matches the independent model for all {len(set(expected) | set(actual))} item/location cells",
    not diffs,
    "(item, location), model, app: " + str(diffs[:8]),
)

# ---- 5. Defective store equals the pieces in store ---------------------------------------------------------
in_store = Counter(
    dict(q("select item_id, count(*) from defectives_defectivepiece where status='IN_STORE' group by 1"))
)
held = {
    i: qty
    for i, qty in q("select item_id, qty from inventory_stockbalance where location_id=%s and qty<>0", store)
}
bad = {
    i: (held.get(i, 0), in_store.get(i, 0))
    for i in set(held) | set(in_store)
    if held.get(i, 0) != in_store.get(i, 0)
}
check(
    "Defective store quantity equals pieces IN_STORE, per item",
    not bad,
    f"item: (store qty, pieces) {dict(list(bad.items())[:5])}",
)

# ---- 6. piece counts equal what the timeline created ------------------------------------------------------
expect_pieces = sum(q_ for op in scen["timeline"] if op["op"] == "mark" for _, q_, *_ in op["lines"]) + sum(
    c[1] for op in scen["timeline"] if op["op"] == "visit" for c in op["collected"]
)
(n_pieces,) = q("select count(*) from defectives_defectivepiece")[0]
model_check(
    f"{expect_pieces} pieces were created (marked + collected)",
    n_pieces == expect_pieces,
    f"app has {n_pieces}",
)


# ---- 7. document numbers: no gaps, no duplicates -----------------------------------------------------------
def gap_free(label, values):
    groups = defaultdict(list)
    for v in values:
        m = re.fullmatch(r"([A-Z]+)-(\d+)", v)
        groups[m.group(1)].append(int(m.group(2)))
    for prefix, nums in groups.items():
        ok = sorted(nums) == list(range(1, len(nums) + 1))
        check(
            f"{label} {prefix}: {len(nums)} numbers, 1..{len(nums)} with no gap or duplicate",
            ok,
            f"max {max(nums)}, count {len(nums)}",
        )


gap_free("stock entry", [r[0] for r in q("select number from inventory_stockentry")])
gap_free("complaint", [r[0] for r in q("select number from complaints_complaint")])
gap_free("visit", [r[0] for r in q("select number from complaints_visit")])
gap_free("return batch", [r[0] for r in q("select number from defectives_returnbatch")])
gap_free("defective tag", [r[0] for r in q("select tag from defectives_defectivepiece")])

# ---- 8. pieces and batches agree ---------------------------------------------------------------------------
bad = q(
    "select tag, status from defectives_defectivepiece where (status='IN_STORE' and return_batch_id is not null) or (status in ('IN_BATCH','SENT') and return_batch_id is null)"
)
check("a piece is in a batch exactly when its status says so", not bad, str(bad[:5]))
(replaced_or_repaired,) = q(
    "select count(*) from defectives_batchline where outcome in ('REPLACED','REPAIRED')"
)[0]
model_check(
    f"stock added by settles ({len(res['settle_effects'])}) equals pieces answered Replaced/Repaired",
    replaced_or_repaired == len(res["settle_effects"]),
    f"batchlines {replaced_or_repaired}",
)
dup = q("select piece_id, count(*) from defectives_batchline where outcome='' group by 1 having count(*)>1")
check("no piece is waiting for an answer in two batches", not dup, str(dup[:5]))

# ---- 9. complaints: dates and statuses make sense ------------------------------------------------------------
bad = q(
    "select c.number, v.number from complaints_visit v join complaints_complaint c on c.id=v.complaint_id where v.visit_date < c.reported_on"
)
check("no visit is dated before its complaint was reported", not bad, str(bad[:5]))
bad = q(
    "select number, status from complaints_complaint where status in ('CLOSED','NOT_COVERED') and closed_on is null"
)
check("every closed / not-covered complaint has a closed date", not bad, str(bad[:5]))

print(
    f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED: ' + '; '.join(failures)}"
)
sys.exit(1 if failures else 0)
