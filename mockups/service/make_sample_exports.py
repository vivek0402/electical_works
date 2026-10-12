"""Write the sample Excel exports from demo-data.json, in the style the real app will use.

Stock: Current stock (with the Defective store as its own, uncounted column), Stock movements, Item list, Low stock.
Service: Pending complaints, Complaint list, Defective list (grouped by company), Return-batch dispatch lists.

Run:  uv run --with xlsxwriter python mockups/service/make_sample_exports.py
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
DEF = DB["defStore"]
ITEMS = {i["code"]: i for i in DB["items"]}
KIND = {"IN": "Stock IN", "OUT": "Stock OUT", "TRF": "Transfer", "ADJ": "Adjustment", "REV": "Undo"}
IN_FROM = {"SUPPLIER": "From supplier", "RETURN": "Returned unused from site", "OPENING": "Opening stock"}
OUT_TO = {"SITE": "To site / customer", "TECH": "To technician", "OTHER": "To other"}
SVC_WHAT = {"COMPLAINT": "Parts for complaint {complaint}", "DEFECTIVE_COLLECTED": "Defective collected ({complaint})",
            "RETURN_TO_COMPANY": "Returned to company ({batch})", "REPLACEMENT": "Replacement from company ({batch})",
            "DEFECTIVE_RETURNED": "Rejected, back from company ({batch})"}
CSTATUS = {"NOT_ATTENDED": "Not attended", "ATTENDED": "Attended", "MATERIAL_CHECK": "Material need to check",
           "AWAITING_MATERIAL": "Awaiting material", "RESOLVED": "Resolved", "CLOSED": "Closed", "NOT_COVERED": "Not covered"}
OPEN = ["NOT_ATTENDED", "ATTENDED", "MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"]
OUTCOME = {"REPLACED": "Replaced", "REPAIRED": "Repaired", "REJECTED_RETURNED": "Rejected (returned)", "REJECTED_SCRAPPED": "Rejected (scrapped)"}
SITES = {s["id"]: s for s in DB["sites"]}

balance = defaultdict(int)
for e in DB["entries"]:
    for ln in e["lines"]:
        balance[(ln["code"], ln["loc"])] += ln["qty"]
total = {c: sum(balance[(c, loc)] for loc in LOCS) for c in ITEMS}
undone = {e["reverses"]: e["no"] for e in DB["entries"] if e.get("reverses")}


def fmt_d(iso):
    return date.fromisoformat(iso).strftime("%d-%m-%Y")


def is_low(i):
    return i["reorder"] > 0 and total[i["code"]] <= i["reorder"]


def report(filename, title, filters, columns, rows, low_col=None, widths=None):
    """One shared layout for every export.

    columns: list of (header, kind) with kind in text | code | int | date. rows: lists of values.
    low_col: index of a column whose rows get a red highlight when row[-1] is True (row[-1] is then dropped).
    """
    wb = xlsxwriter.Workbook(OUT / filename, {"strings_to_formulas": False})
    wb.set_properties({"title": title, "company": "SVKML Electrical Works", "author": "SVKML Stock"})
    ws = wb.add_worksheet(title[:31])
    f = {
        "company": wb.add_format({"bold": True, "font_size": 15, "font_color": "#0F2744"}),
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
    return date.fromisoformat(iso) if iso else None


def month(ym):
    return "-".join(reversed(ym.split("-"))) if ym else ""


def entry_what(e):
    if e.get("subtype") in SVC_WHAT:
        return SVC_WHAT[e["subtype"]].format(complaint=e.get("complaint"), batch=e.get("batch"))
    if e["kind"] == "IN":
        return IN_FROM.get(e.get("subtype"))
    if e["kind"] == "OUT":
        return OUT_TO.get(e.get("subtype"))
    if e["kind"] == "TRF":
        return "Marked defective" if e.get("party") == DEF else "Between locations"
    if e["kind"] == "ADJ":
        return "Defective pieces scrapped" if all(ln["loc"] == DEF for ln in e["lines"]) else e.get("reason")
    return f"Undo of {e['reverses']}"


# 1. Current stock
cols = [("Item code", "code"), ("Spare type", "text"), ("Description", "text"), ("Used in fitting (cat ref)", "code"),
        ("Fitting type", "text"), ("Company", "text")] + [(loc, "int") for loc in LOCS] + \
       [("Total", "int"), ("Unit", "text"), ("Reorder level", "int"), ("Status", "text"), ("Defective store (not counted)", "int")]
rows = [[i["code"], i["type"], i["desc"], i["catRef"] if i["catRef"] != i["code"] else "", i["fittingType"], i["company"]]
        + [balance[(i["code"], loc)] for loc in LOCS]
        + [total[i["code"]], i["unit"], i["reorder"], "LOW" if is_low(i) else "OK", balance[(i["code"], DEF)], is_low(i)]
        for i in DB["items"] if i["active"] and (total[i["code"]] != 0 or balance[(i["code"], DEF)] != 0)]
report("Current_Stock.xlsx", "Current Stock",
       "All locations · all types · all companies · Total = good stock only; the Defective store is listed separately",
       cols, rows, low_col=len(cols) - 2, widths={2: 30})

# 2. Stock movements (last 30 days)
start = date.fromordinal(TODAY.toordinal() - 30)
cols = [("Date", "date"), ("Entry no.", "code"), ("Type", "text"), ("Details", "text"), ("Item code", "code"),
        ("Description", "text"), ("Location", "text"), ("Qty in", "int"), ("Qty out", "int"), ("Unit", "text"),
        ("Supplier / issued to", "text"), ("DC / ref no.", "text"), ("Complaint", "code"), ("Return batch", "code"),
        ("Batch code", "text"), ("PKD", "text"),
        ("Entered by", "text"), ("Note", "text")]
rows = []
for e in DB["entries"]:
    if not (start <= d(e["date"]) <= TODAY):
        continue
    details = entry_what(e)
    for ln in e["lines"]:
        pkd = "-".join(reversed(ln["pkd"].split("-"))) if ln.get("pkd") else ""
        note = f"Undone by {undone[e['no']]}" if e["no"] in undone else e.get("note", "")
        rows.append([d(e["date"]), e["no"], KIND[e["kind"]], details, ln["code"], ITEMS[ln["code"]]["desc"], ln["loc"],
                     ln["qty"] if ln["qty"] > 0 else None, -ln["qty"] if ln["qty"] < 0 else None, ITEMS[ln["code"]]["unit"],
                     e.get("party", ""), e.get("ref", ""), e.get("complaint") or "", e.get("batch") or "",
                     ln.get("batch", ""), pkd, e["by"], note])
rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
report("Stock_Movements.xlsx", "Stock Movements",
       f"{start:%d-%m-%Y} to {TODAY:%d-%m-%Y} · all types · all locations", cols, rows, widths={5: 28, 10: 26, 17: 28})

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

# ---------- service exports ----------
EVENTS = defaultdict(list)
for ev in DB["complaintEvents"]:
    EVENTS[ev["complaint"]].append(ev)


def age(c):
    return (d(c["closedOn"]) or TODAY).toordinal() - d(c["reportedOn"]).toordinal()


def awaiting_days(c):
    tot, since = 0, None
    for ev in EVENTS[c["no"]]:
        if since and ev["to"] != "AWAITING_MATERIAL":
            tot += d(ev["at"]).toordinal() - since.toordinal()
            since = None
        if ev["to"] == "AWAITING_MATERIAL" and not since:
            since = d(ev["at"])
    if since:
        tot += (d(c["closedOn"]) or TODAY).toordinal() - since.toordinal()
    return tot


def last_visit(c):
    ds = [v["date"] for v in DB["visits"] if v["complaint"] == c["no"]]
    return d(max(ds)) if ds else None


def complaint_row(c):
    s = SITES[c["site"]]
    return [c["no"], d(c["reportedOn"]), s["name"], s["city"], c["contact"], c["phone"], c["company"], c["companyRef"],
            c["fault"], c["qty"], ", ".join(c["techs"]), c["priority"], CSTATUS[c["status"]], age(c), awaiting_days(c), last_visit(c)]


CCOLS = [("Complaint no.", "code"), ("Reported on", "date"), ("Site", "text"), ("City", "text"), ("Contact", "text"),
         ("Phone", "code"), ("Company", "text"), ("Company complaint no.", "code"), ("Fault", "text"), ("Qty affected", "int"),
         ("Technicians", "text"), ("Priority", "text"), ("Status", "text"), ("Age (days)", "int"),
         ("Days awaiting material", "int"), ("Last visit", "date")]

# 5. Pending complaints: every open complaint, oldest first; red age = open more than 15 days.
pending = sorted((c for c in DB["complaints"] if c["status"] in OPEN), key=lambda c: (c["reportedOn"], c["no"]))
report("Pending_Complaints.xlsx", "Pending Complaints",
       "Open complaints (Not attended, Attended, Material need to check, Awaiting material, Resolved) · all companies · all cities",
       CCOLS, [complaint_row(c) + [age(c) > 15] for c in pending], low_col=13, widths={2: 26, 8: 40})

# 6. Complaint list: everything, newest first.
allc = sorted(DB["complaints"], key=lambda c: (c["reportedOn"], c["no"]), reverse=True)
report("Complaint_List.xlsx", "Complaint List", "All statuses · all companies · all cities · all technicians",
       CCOLS + [("Closed on", "date"), ("Not covered reason", "text"), ("Visits", "int")],
       [complaint_row(c) + [d(c["closedOn"]), c["notCoveredReason"], sum(v["complaint"] == c["no"] for v in DB["visits"])]
        for c in allc], widths={2: 26, 8: 40})

# 7. Defective list: pieces physically in the Defective store, grouped by company, then item / batch / PKD.
groups = defaultdict(list)
for pc in DB["pieces"]:
    if pc["status"] in ("IN_STORE", "IN_BATCH"):
        groups[(pc["company"], pc["code"], pc["batch"], pc["pkd"])].append(pc)
rows = [[co, code, ITEMS[code]["desc"], batch, month(pkd), len(ps), sum(p["status"] == "IN_BATCH" for p in ps),
         ", ".join(p["tag"] for p in ps)] for (co, code, batch, pkd), ps in sorted(groups.items())]
report("Defective_List.xlsx", "Defective List",
       "Pieces in the Defective store (in store + in draft batches) · grouped by company", [
           ("Company", "text"), ("Item code", "code"), ("Description", "text"), ("Batch code", "code"), ("PKD", "text"),
           ("Qty in store", "int"), ("Of which in a draft batch", "int"), ("Tags", "code")], rows, widths={2: 28, 7: 40})

# 8. Return-batch dispatch lists, one per demo batch. It goes with the shipment.
for b in DB["batches"]:
    status = ("Draft (not dispatched yet)" if b["status"] == "DRAFT"
              else f"Dispatched {fmt_d(b['dispatchedOn'])} · {b['courier']} {b['docket']}")
    rows = []
    for ln in b["lines"]:
        pc = next(p for p in DB["pieces"] if p["tag"] == ln["tag"])
        cmp_ = next((c for c in DB["complaints"] if c["no"] == pc["complaint"]), None)
        rows.append([pc["tag"], pc["code"], ITEMS[pc["code"]]["desc"], pc["batch"], month(pc["pkd"]), pc["fault"],
                     pc["complaint"] or "Found in stock", cmp_["companyRef"] if cmp_ else "", d(pc["collectedOn"]),
                     OUTCOME.get(ln["outcome"], "")])
    report(f"Return_Batch_{b['no']}.xlsx", f"Return Batch {b['no']} · {b['company']}",
           f"{status} · {len(rows)} pieces" + (f" · {b['note']}" if b["note"] else ""), [
               ("Tag", "code"), ("Item code", "code"), ("Description", "text"), ("Batch code", "code"), ("PKD", "text"),
               ("Fault", "text"), ("Complaint", "code"), ("Company complaint no.", "code"), ("Collected on", "date"),
               ("Outcome", "text")], rows, widths={2: 28, 5: 30})

for p in sorted(OUT.glob("*.xlsx")):
    print(p.name, p.stat().st_size, "bytes")
