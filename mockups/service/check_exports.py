"""Read the sample exports back and check the title rows, headers and row counts against demo-data.json.

Run:  uv run --with openpyxl python mockups/service/check_exports.py
"""

import json
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).parent
DB = json.loads((HERE / "demo-data.json").read_text(encoding="utf-8"))
OPEN = {"NOT_ATTENDED", "ATTENDED", "MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"}
bal = Counter()
for e in DB["entries"]:
    for ln in e["lines"]:
        bal[(ln["code"], ln["loc"])] += ln["qty"]
in_def = [p for p in DB["pieces"] if p["status"] in ("IN_STORE", "IN_BATCH")]
groups = {(p["company"], p["code"], p["batch"], p["pkd"]) for p in in_def}

EXPECT = {  # file: (title, first headers, expected data rows or None)
    "Current_Stock.xlsx": ("Current Stock", ["Item code", "Spare type"], None),
    "Stock_Movements.xlsx": ("Stock Movements", ["Date", "Entry no."], None),
    "Item_List.xlsx": ("Item List", ["Item code", "Other spellings"], len(DB["items"])),
    "Low_Stock.xlsx": ("Low Stock", ["Item code", "Spare type"], None),
    "Pending_Complaints.xlsx": ("Pending Complaints", ["Complaint no.", "Reported on", "Site"], sum(c["status"] in OPEN for c in DB["complaints"])),
    "Complaint_List.xlsx": ("Complaint List", ["Complaint no.", "Reported on", "Site"], len(DB["complaints"])),
    "Defective_List.xlsx": ("Defective List", ["Company", "Item code", "Description", "Batch code", "PKD", "Qty in store"], len(groups)),
    "Return_Batch_RB-0001.xlsx": ("Return Batch RB-0001", ["Tag", "Item code", "Description", "Batch code", "PKD", "Fault"],
                                  len(next(b for b in DB["batches"] if b["no"] == "RB-0001")["lines"])),
}
ok = True
for name, (title, heads, n) in EXPECT.items():
    ws = load_workbook(HERE / "exports" / name).active
    rows = list(ws.iter_rows(values_only=True))
    company, ttl, filters, gen, _, header, *data = rows
    data = [r for r in data if any(v is not None for v in r)]
    checks = [company[0] == "SVKML Electrical Works", str(ttl[0]).startswith(title), str(filters[0]).startswith("Filters: "),
              str(gen[0]).startswith("Generated on"), list(header[:len(heads)]) == heads, n is None or len(data) == n,
              f"· {len(data)} rows" in str(gen[0])]
    ok &= all(checks)
    print(f"{'OK ' if all(checks) else 'BAD'} {name:28} title={ttl[0]!r:40} rows={len(data):3} expected={n} header={list(header)[:6]}")
    if name == "Current_Stock.xlsx":
        h = list(header)
        assert "Defective store (not counted)" in h and h.index("Total") < h.index("Defective store (not counted)")
        for r in data:
            code = r[0]
            assert r[h.index("Total")] == sum(bal[(code, loc)] for loc in DB["locations"]), code   # good stock only
            assert (r[h.index("Defective store (not counted)")] or 0) == bal[(code, DB["defStore"])], code
        print("    Current stock: Total = good locations only; Defective column matches the ledger")
    if name == "Defective_List.xlsx":
        assert sum(r[5] for r in data) == len(in_def)
        cos = [r[0] for r in data]
        assert cos == sorted(cos), "not grouped by company"
        print(f"    Defective list: {len(in_def)} pieces in {len(set(cos))} company groups")
assert ok
print("exports OK")
