"""Write the four sample Excel exports from demo-data.json, in the style the real app will use.

Run:  uv run --with xlsxwriter python make_sample_exports.py
"""

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import xlsxwriter

HERE = Path(__file__).parent
DB = json.loads((HERE / "demo-data.json").read_text(encoding="utf-8"))
OUT = HERE / "exports"
OUT.mkdir(exist_ok=True)
TODAY = date.fromisoformat(DB["today"])
GENERATED = datetime(TODAY.year, TODAY.month, TODAY.day, 14, 5)
LOCS = DB["locations"]
ITEMS = {i["code"]: i for i in DB["items"]}
KIND = {"IN": "Stock IN", "OUT": "Stock OUT", "TRF": "Transfer", "ADJ": "Adjustment", "REV": "Undo"}
IN_FROM = {"SUPPLIER": "From supplier", "RETURN": "Returned unused from site", "OPENING": "Opening stock"}
OUT_TO = {"SITE": "To site / customer", "TECH": "To technician", "OTHER": "To other"}

balance = defaultdict(int)
for e in DB["entries"]:
    for ln in e["lines"]:
        balance[(ln["code"], ln["loc"])] += ln["qty"]
total = {c: sum(balance[(c, loc)] for loc in LOCS) for c in ITEMS}
undone = {e["reverses"]: e["no"] for e in DB["entries"] if e.get("reverses")}


def is_low(i):
    return i["reorder"] > 0 and total[i["code"]] <= i["reorder"]


def report(filename, title, filters, columns, rows, low_col=None, widths=None):
    """One shared layout for every export.

    columns: list of (header, kind) with kind in text | code | int | date. rows: lists of values.
    low_col: index of a column whose rows get a red highlight when row[-1] is True (row[-1] is then dropped).
    """
    wb = xlsxwriter.Workbook(OUT / filename)
    wb.set_properties({"title": title, "company": "SVKML Electrical Works", "author": "SVKML Stock"})
    ws = wb.add_worksheet(title[:31])
    f = {
        "company": wb.add_format({"bold": True, "font_size": 15, "font_color": "#0F3B5F"}),
        "title": wb.add_format({"bold": True, "font_size": 12}),
        "meta": wb.add_format({"italic": True, "font_color": "#555555", "font_size": 9}),
        "text": wb.add_format({"valign": "top", "text_wrap": False}),
        "code": wb.add_format({"font_name": "Consolas", "num_format": "@"}),
        "int": wb.add_format({"num_format": "#,##0;-#,##0;\"–\""}),
        "date": wb.add_format({"num_format": "dd-mm-yyyy", "align": "left"}),
        "low": wb.add_format({"bg_color": "#FDE2E2", "font_color": "#9B1C1C", "bold": True}),
    }
    last_col = len(columns) - 1
    head = 5
    flags = [r.pop() for r in rows] if low_col is not None else []
    data = [[datetime.combine(v, datetime.min.time()) if isinstance(v, date) and not isinstance(v, datetime) else v
             for v in r] for r in rows]
    ws.add_table(head, 0, head + max(len(data), 1), last_col, {
        "data": data or [["(no rows)"] + [None] * last_col],
        "style": "Table Style Medium 2",
        "columns": [{"header": h, "format": f[k]} for h, k in columns],
    })
    if low_col is not None:
        for n, flag in enumerate(flags):
            if flag:
                ws.write(head + 1 + n, low_col, data[n][low_col], f["low"])
    ws.freeze_panes(head + 1, 1)
    ws.autofit(max_width=280)  # pixels (~40 characters); runs before the title rows so they don't widen column A
    ws.merge_range(0, 0, 0, last_col, "SVKML Electrical Works", f["company"])
    ws.merge_range(1, 0, 1, last_col, title, f["title"])
    ws.merge_range(2, 0, 2, last_col, "Filters: " + filters, f["meta"])
    ws.merge_range(3, 0, 3, last_col, f"Generated on {GENERATED:%d-%m-%Y %H:%M} by Office · {len(data)} rows", f["meta"])
    for col, w in (widths or {}).items():
        ws.set_column(col, col, w)
    ws.set_row(head, 30)
    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.repeat_rows(head)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.set_header(f"&L&8SVKML Electrical Works&R&8{title}")
    ws.set_footer("&L&8Generated &D &T&R&8Page &P of &N")
    wb.close()
    return OUT / filename


def d(iso):
    return date.fromisoformat(iso)


# 1. Current stock
cols = [("Item code", "code"), ("Spare type", "text"), ("Description", "text"), ("Used in fitting (cat ref)", "code"),
        ("Fitting type", "text"), ("Company", "text")] + [(loc, "int") for loc in LOCS] + \
       [("Total", "int"), ("Unit", "text"), ("Reorder level", "int"), ("Status", "text")]
rows = [[i["code"], i["type"], i["desc"], i["catRef"] if i["catRef"] != i["code"] else "", i["fittingType"], i["company"]]
        + [balance[(i["code"], loc)] for loc in LOCS]
        + [total[i["code"]], i["unit"], i["reorder"], "LOW" if is_low(i) else "OK", is_low(i)]
        for i in DB["items"] if i["active"] and total[i["code"]] != 0]
report("Current_Stock.xlsx", "Current Stock", "All locations · all types · all companies", cols, rows,
       low_col=len(cols) - 1, widths={2: 30})

# 2. Stock movements (last 30 days)
start = date.fromordinal(TODAY.toordinal() - 30)
cols = [("Date", "date"), ("Entry no.", "code"), ("Type", "text"), ("Details", "text"), ("Item code", "code"),
        ("Description", "text"), ("Location", "text"), ("Qty in", "int"), ("Qty out", "int"), ("Unit", "text"),
        ("Supplier / issued to", "text"), ("DC / ref no.", "text"), ("Batch code", "text"), ("PKD", "text"),
        ("Entered by", "text"), ("Note", "text")]
rows = []
for e in DB["entries"]:
    if not (start <= d(e["date"]) <= TODAY):
        continue
    details = (IN_FROM.get(e.get("subtype")) if e["kind"] == "IN" else OUT_TO.get(e.get("subtype")) if e["kind"] == "OUT"
               else "Between locations" if e["kind"] == "TRF" else e.get("reason") if e["kind"] == "ADJ" else f"Undo of {e['reverses']}")
    for ln in e["lines"]:
        pkd = "-".join(reversed(ln["pkd"].split("-"))) if ln.get("pkd") else ""
        note = f"Undone by {undone[e['no']]}" if e["no"] in undone else e.get("note", "")
        rows.append([d(e["date"]), e["no"], KIND[e["kind"]], details, ln["code"], ITEMS[ln["code"]]["desc"], ln["loc"],
                     ln["qty"] if ln["qty"] > 0 else None, -ln["qty"] if ln["qty"] < 0 else None, ITEMS[ln["code"]]["unit"],
                     e.get("party", ""), e.get("ref", ""), ln.get("batch", ""), pkd, e["by"], note])
rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
report("Stock_Movements.xlsx", "Stock Movements",
       f"{start:%d-%m-%Y} to {TODAY:%d-%m-%Y} · all types · all locations", cols, rows, widths={5: 28, 10: 26, 15: 28})

# 3. Item list
cols = [("Item code", "code"), ("Other spellings", "code"), ("Spare type", "text"), ("Description", "text"),
        ("Product cat ref", "code"), ("Fitting type", "text"), ("Wattage (W)", "int"), ("Current (mA)", "int"),
        ("Company", "text"), ("Unit", "text"), ("Reorder level", "int"), ("Status", "text")]
rows = [[i["code"], ", ".join(i["aliases"]), i["type"], i["desc"], i["catRef"], i["fittingType"], i["watt"], i["ma"],
         i["company"], i["unit"], i["reorder"], "Active" if i["active"] else "Inactive"] for i in DB["items"]]
report("Item_List.xlsx", "Item List", "All items", cols, rows, widths={3: 30})

# 4. Low stock
cols = [("Item code", "code"), ("Spare type", "text"), ("Description", "text"), ("Company", "text")] + \
       [(loc, "int") for loc in LOCS] + [("Total", "int"), ("Reorder level", "int"), ("Short by", "int"), ("Unit", "text")]
rows = [[i["code"], i["type"], i["desc"], i["company"]] + [balance[(i["code"], loc)] for loc in LOCS]
        + [total[i["code"]], i["reorder"], max(0, i["reorder"] - total[i["code"]]), i["unit"], True]
        for i in DB["items"] if i["active"] and is_low(i)]
report("Low_Stock.xlsx", "Low Stock", "Items at or below their reorder level (total across all locations)", cols, rows,
       low_col=4 + len(LOCS), widths={2: 30})

for p in sorted(OUT.glob("*.xlsx")):
    print(p.name, p.stat().st_size, "bytes")
