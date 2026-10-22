"""Build the rigour-test timeline from the legacy Excel files (read-only) -> e2e/rigour/scenarios.json.

    uv run --with openpyxl python -I e2e/rigour/build_scenarios.py

The Excel files hold only patterns (about 70 stock rows per list, 19 complaints), so this script turns them
into about 100 entries of each kind with a seeded random generator: the same run gives the same file.
While generating, it simulates the stock itself (`stock[code][location]`), so every operation marked valid
really is valid, and `expected_stock` is an independent answer the audit compares with the app's numbers.

Operation kinds (see load_entries.py): item, site, tech, in, out, trf, adj, mark, cmp, visit, status,
notcovered, batch. `messy` lists what the Excel rows do that a form must refuse or clean.
"""

import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent.parent / "data" / "legacy"
OUT = HERE / "scenarios.json"
rng = random.Random(2026)

LOCATIONS = ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"]
LOC_WEIGHTS = [55, 20, 15, 10]
START, END = date(2026, 1, 5), date(2026, 10, 20)
TODAY = date(
    2026, 10, 22
)  # a new batch is dated today by the app, so it can only be dispatched today  # the app refuses future dates; today is 2026-10-22
SUPPLIERS = ["Wipro Lighting", "Havells", "Finolex Cables", "Lakshmi Traders", "Sri Sai Electricals"]
TECHS = [
    ("Ramu", "9848012345"),
    ("Apparao", "9848023456"),
    ("Srinuvas", "8790022266"),
    ("Jagadeesh", "9963945021"),
    ("Venkat", "9988776655"),
    ("Suresh", "9090909090"),
]
CITIES = ["Visakhapatnam", "Guntur", "Nellore", "Tirupati", "Vijayawada", "Anantapur", "Gudivada"]


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def qty_of(text):
    """'22 NOS' -> 22, '`7NOS' -> 7, 'QUANTITY' -> None."""
    found = re.search(r"\d+", str(text or ""))
    return int(found.group()) if found else None


def read_stock_sheets():
    """(fresh rows, defective rows) as (code, spare_type, qty) with the raw quantity text kept for messy ones."""
    wb = openpyxl.load_workbook(LEGACY / "25-5-2026_Vizag_Fresh__Defective_list.xlsx", data_only=True)
    sheets = list(wb)
    defective_sheet = next(ws for ws in sheets if "Defective" in ws.title)
    fresh_sheet = next(ws for ws in sheets if "Fresh" in ws.title)

    def rows(ws, fitting, driver, pcb, qty):
        out = []
        for r in ws.iter_rows(min_row=3, values_only=True):
            for col, kind in ((fitting, "Complete fitting"), (driver, "Driver"), (pcb, "PCB / LED module")):
                code = clean(r[col])
                if code:
                    if code.upper() == "LENS":
                        kind = "Lens"
                    out.append((code, kind, qty_of(r[qty]), clean(r[qty])))
                    break
        return out

    fresh = rows(fresh_sheet, 1, 4, 5, 6)
    defective = rows(defective_sheet, 1, 3, 4, 5)
    return [r for r in fresh if r[2]], [r for r in defective if r[2]], fresh + defective


def read_complaints():
    ws = openpyxl.load_workbook(LEGACY / "AP_Pending_Compliants_details.xlsx", data_only=True).active
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(r):
            continue
        out.append(
            {
                "name": clean(r[2]),
                "city": clean(r[3]),
                "status_a": clean(r[4]),
                "contact": clean(r[5]),
                "phone": clean(r[6]),
                "status_b": clean(r[7]).lower(),
                "visit_text": clean(r[8]),
                "remarks": clean(r[9]),
            }
        )
    return out


def tidy_name(name):
    words = name.split()
    return " ".join(w if w.isupper() and len(w) > 1 else w.capitalize() for w in words)


def visit_date_from(text):
    """'ramu 02/02/26', 'Ramu 23.1.2026', 'Ramu/Apparao/17.1.26' -> a date, or None."""
    found = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", text)
    if not found:
        return None
    d, m, y = (int(x) for x in found.groups())
    y += 2000 if y < 100 else 0
    try:
        return date(y, m, d)
    except ValueError:
        return None


def main():
    fresh, defective, everything = read_stock_sheets()
    complaints_xl = read_complaints()

    # ---- items: one per distinct code (case and spaces ignored, as the app does) -------------------------
    items, seen = {}, set()
    for code, kind, _, _ in everything:
        key = re.sub(r"\s+", "", code).upper()
        if key in seen:
            continue
        seen.add(key)
        items[code] = {
            "op": "item",
            "code": code,
            "spare": kind,
            "company": "Wipro Lighting",
            "reorder": rng.choice([0, 0, 3, 5, 10]),
        }
    codes = list(items)
    drivers = [c for c in codes if items[c]["spare"] == "Driver"]
    stock = {c: {loc: 0 for loc in LOCATIONS} for c in codes}  # the generator's own model of good stock
    pieces_in_store = 0
    events = []  # (date, seq, op)

    def add(day, op):
        events.append((day, len(events), op))

    def have(code, loc):
        return stock[code][loc]

    def day_between(a, b):
        return a + timedelta(days=rng.randint(0, max(0, (b - a).days)))

    # ---- masters --------------------------------------------------------------------------------------------
    masters = [items[c] for c in codes] + [{"op": "tech", "name": n, "phone": p} for n, p in TECHS]

    # sites: Excel sites first, then a few more, so complaints have somewhere to be filed
    sites = {}
    for row in complaints_xl:
        name = tidy_name(row["name"])
        key = name.lower()
        if key in sites:
            continue
        phone = row["phone"] if re.fullmatch(r"[6-9]\d{9}", row["phone"]) else ""
        sites[key] = {
            "op": "site",
            "name": name,
            "city": tidy_name(row["city"]) or "Visakhapatnam",
            "contact": row["contact"].replace(";", " ").title(),
            "phone": phone,
        }
    for nm in [
        "Sunrise Apartments Block B",
        "Lakshmi Textile Mills",
        "Hotel Bay View",
        "Andhra Cement Works",
        "Sai Ram Hospital",
        "Kalyani Jewellers",
        "Port Trust Colony",
        "Greenfield School",
    ]:
        sites[nm.lower()] = {
            "op": "site",
            "name": nm,
            "city": rng.choice(CITIES),
            "contact": rng.choice(["Mr Rao", "Mrs Devi", "Reception", "Manager"]),
            "phone": "9" + "".join(rng.choice("0123456789") for _ in range(9)),
        }
    site_list = list(sites.values())

    # ---- opening stock: every Fresh-list row, grouped 3 to an entry, per location ---------------------------
    pending = {loc: [] for loc in LOCATIONS}
    for code, _kind, qty, _ in fresh:
        pending[rng.choices(LOCATIONS, LOC_WEIGHTS)[0]].append((code, qty))
    for loc, rows in pending.items():
        merged = {}
        for code, qty in rows:
            merged[code] = merged.get(code, 0) + qty
        rows = list(merged.items())
        for k in range(0, len(rows), 3):
            chunk = rows[k : k + 3]
            for code, qty in chunk:
                stock[code][loc] += qty
            add(
                START + timedelta(days=rng.randint(0, 6)),
                {
                    "op": "in",
                    "loc": loc,
                    "subtype": "OPENING",
                    "lines": [[c, q, "", ""] for c, q in chunk],
                    "note": "Opening count (from Fresh list)",
                },
            )

    # ---- supplier deliveries: first for the Defective-list items (so pieces can be marked), then random ----
    first_def = {}
    for code, _kind, qty, _ in defective:
        first_def[code] = first_def.get(code, 0) + min(qty, 2)
    def_rows = list(first_def.items())
    for k in range(0, len(def_rows), 4):
        chunk = def_rows[k : k + 4]
        day = START + timedelta(days=rng.randint(7, 14))
        for code, need in chunk:
            stock[code]["Vizag Office"] += need + 3
        add(
            day,
            {
                "op": "in",
                "loc": "Vizag Office",
                "subtype": "SUPPLIER",
                "company": rng.choice(SUPPLIERS[:3]),
                "ref": f"DC-{rng.randint(10000, 99999)}",
                "lines": [
                    [c, n + 3, f"B{rng.randint(2300, 2610)}", f"2025-{rng.randint(1, 12):02d}"]
                    for c, n in chunk
                ],
            },
        )
    for _ in range(14):
        day = day_between(START + timedelta(days=15), END - timedelta(days=30))
        loc = rng.choices(LOCATIONS, LOC_WEIGHTS)[0]
        lines = []
        for code in rng.sample(codes, rng.randint(1, 4)):
            q = rng.choice([10, 20, 25, 40, 50, 100, 150])
            stock[code][loc] += q
            lines.append([code, q, f"B{rng.randint(2300, 2610)}", f"2026-{rng.randint(1, 9):02d}"])
        add(
            day,
            {
                "op": "in",
                "loc": loc,
                "subtype": "SUPPLIER",
                "company": rng.choice(SUPPLIERS),
                "ref": rng.choice(
                    [
                        f"DC-{rng.randint(10000, 99999)}",
                        f"INV/2026/{rng.randint(100, 999)}",
                        f"BILL {rng.randint(1000, 9999)}",
                    ]
                ),
                "lines": lines,
            },
        )

    # ---- complaints ------------------------------------------------------------------------------------------
    plan = []  # (reported_on, op dict, outcome, excel row or None)
    for row in complaints_xl:
        name = tidy_name(row["name"])
        status = row["status_b"]
        closed = row["status_a"].lower().startswith("closed")
        notwipro = "not wipro" in row["status_a"].lower()
        vday = visit_date_from(row["visit_text"])
        outcome = (
            "not_covered"
            if notwipro
            else "closed"
            if closed
            else "material"
            if "material" in row["remarks"].lower() and status == "attended"
            else "attended"
            if status == "attended"
            else "open"
        )
        reported = (
            (vday - timedelta(days=rng.randint(2, 10)))
            if vday
            else day_between(date(2026, 1, 5), date(2026, 4, 30))
        )
        fault = row["remarks"] or "Lights not working"
        plan.append(
            (
                reported,
                {
                    "site": name,
                    "company": "Havells" if "kathyayani" in name.lower() else "Wipro Lighting",
                    "fault": fault,
                    "qty": qty_of(fault),
                    "excel": True,
                },
                outcome,
                vday,
            )
        )
    sites_used = [s["name"] for s in site_list]
    faults = [
        "{n} linear fittings flickering",
        "{n} {c} drivers not working",
        "{n} lights not working on the 2nd floor",
        "{n} panels dim",
        "PCB burnt in {n} fittings",
        "{n} street lights off at night",
    ]
    while len(plan) < 100:
        reported = day_between(date(2026, 2, 1), date(2026, 10, 10))
        n = rng.randint(1, 20)
        fault = rng.choice(faults).format(n=n, c=rng.choice(drivers) if drivers else "LED")
        outcome = rng.choices(
            ["open", "attended", "material", "resolved", "closed", "not_covered"], [22, 18, 14, 20, 18, 8]
        )[0]
        plan.append(
            (
                reported,
                {
                    "site": rng.choice(sites_used),
                    "company": rng.choice(["Wipro Lighting"] * 6 + ["Havells", "Finolex Cables"]),
                    "fault": fault[:200],
                    "qty": n,
                    "excel": False,
                },
                outcome,
                None,
            )
        )
    plan.sort(key=lambda p: p[0])

    # a visit is placed on the timeline in date order, taking parts only where the model has them
    for k, (reported, c, outcome, vday) in enumerate(plan):
        key = f"C{k + 1:03d}"
        add(
            reported,
            {
                "op": "cmp",
                "key": key,
                "site": c["site"],
                "company": c["company"],
                "company_ref": rng.choice(["", "", f"WL-{rng.randint(70000, 79999)}"]),
                "date": reported.isoformat(),
                "qty": c["qty"],
                "fault": c["fault"],
                "priority": rng.choices(["NORMAL", "HIGH", "URGENT"], [8, 3, 1])[0],
                "techs": [rng.choice(TECHS)[0]] if rng.random() < 0.4 else [],
            },
        )
        visits_n = {
            "open": 0,
            "attended": 1,
            "material": 1,
            "resolved": rng.choice([1, 2]),
            "closed": rng.choice([1, 2]),
            "not_covered": 0,
        }[outcome]
        last = reported
        for v in range(visits_n):
            day = vday if (vday and v == 0) else min(END, last + timedelta(days=rng.randint(1, 12)))
            day = max(day, last)
            final = v == visits_n - 1
            next_status = (
                {
                    "attended": "ATTENDED",
                    "material": "MATERIAL_CHECK",
                    "resolved": "RESOLVED",
                    "closed": "RESOLVED",
                }[outcome]
                if final
                else rng.choice(["ATTENDED", "AWAITING_MATERIAL"])
            )
            loc = rng.choice(["Vizag Office", "Vizag Office", "Svkml"])
            parts, collected = [], []
            for code in rng.sample(drivers, min(len(drivers), rng.randint(0, 2))):
                give = rng.randint(1, 6)
                if have(code, loc) >= give:
                    stock[code][loc] -= give
                    parts.append([code, give])
                    back = rng.randint(0, give)
                    if back:
                        pieces_in_store += back
                        collected.append(
                            [
                                code,
                                back,
                                f"B{rng.randint(2300, 2610)}",
                                f"2025-{rng.randint(1, 12):02d}",
                                rng.choice(["No output", "Burnt", "Flickering", "Dead on arrival"]),
                            ]
                        )
            add(
                day,
                {
                    "op": "visit",
                    "cmp": key,
                    "date": day.isoformat(),
                    "techs": rng.sample([t[0] for t in TECHS], rng.randint(1, 2)),
                    "loc": loc,
                    "work": rng.choice(
                        [
                            "Replaced faulty drivers",
                            "Checked supply and fittings",
                            "Inspected, material needed",
                            "Changed PCBs",
                        ]
                    ),
                    "next": next_status,
                    "parts": parts,
                    "collected": collected,
                },
            )
            last = day
        if outcome == "closed":
            add(last, {"op": "status", "cmp": key, "to": "CLOSED"})
        elif outcome == "not_covered":
            add(
                last,
                {
                    "op": "notcovered",
                    "cmp": key,
                    "reason": rng.choice(["NOT_OURS", "OUT_OF_WARRANTY", "CANCELLED", "OTHER"]),
                    "note": rng.choice(
                        [
                            "Customer says product is not ours",
                            "Out of warranty per DC date",
                            "Site cancelled the request",
                        ]
                    ),
                },
            )

    # ---- Mark defective for the Defective-list rows -----------------------------------------------------------
    mark_rows = [(c, min(q, 2)) for c, _, q, _ in defective]
    merged = {}
    for c, q in mark_rows:
        merged[c] = merged.get(c, 0) + q
    mark_rows = list(merged.items())
    for k in range(0, len(mark_rows), 3):
        chunk = mark_rows[k : k + 3]
        day = START + timedelta(days=rng.randint(15, 60))
        lines = []
        for code, q in chunk:
            stock[code]["Vizag Office"] -= q
            pieces_in_store += q
            lines.append(
                [
                    code,
                    q,
                    f"B{rng.randint(2300, 2610)}",
                    f"2025-{rng.randint(1, 12):02d}",
                    rng.choice(["Dead on arrival", "No output", "Cracked housing", "Buzzing noise"]),
                ]
            )
        add(day, {"op": "mark", "loc": "Vizag Office", "date": day.isoformat(), "lines": lines})

    # ---- OUT, transfer, adjust, return-IN: random but always valid against the model ---------------------------
    # these are generated last but dated through the year, so sort first and replay the model in date order
    # (the model above was built in generation order; to stay valid, give each a date after the stock exists)
    rich_after = START + timedelta(days=75)  # by then the opening and supplier stock above is in
    for _ in range(26):
        day = day_between(rich_after, END)
        loc = rng.choices(LOCATIONS, LOC_WEIGHTS)[0]
        avail = [c for c in codes if have(c, loc) >= 3]
        if not avail:
            continue
        lines = []
        for code in rng.sample(avail, min(len(avail), rng.randint(1, 3))):
            q = rng.randint(1, min(8, have(code, loc)))
            stock[code][loc] -= q
            lines.append([code, q])
        target = rng.choices(["SITE", "TECH", "OTHER"], [6, 3, 1])[0]
        party = (
            rng.choice(sites_used)
            if target == "SITE"
            else rng.choice(TECHS)[0]
            if target == "TECH"
            else rng.choice(["Local electrician", "Walk-in buyer", "Contractor"])
        )
        add(
            day,
            {
                "op": "out",
                "loc": loc,
                "date": day.isoformat(),
                "subtype": target,
                "party": party,
                "ref": rng.choice(["", f"JOB-2026-{rng.randint(100, 400)}"]),
                "lines": lines,
            },
        )
    for _ in range(12):
        day = day_between(rich_after, END)
        src, dst = rng.sample(LOCATIONS, 2)
        avail = [c for c in codes if have(c, src) >= 4]
        if not avail:
            continue
        lines = []
        for code in rng.sample(avail, min(len(avail), rng.randint(1, 3))):
            q = rng.randint(1, min(10, have(code, src)))
            stock[code][src] -= q
            stock[code][dst] += q
            lines.append([code, q])
        add(
            day,
            {
                "op": "trf",
                "loc": src,
                "to": dst,
                "date": day.isoformat(),
                "lines": lines,
                "note": rng.choice(["Restock van store", "Rebalance shops", ""]),
            },
        )
    for _ in range(10):
        day = day_between(rich_after, END)
        loc = rng.choices(LOCATIONS, LOC_WEIGHTS)[0]
        avail = [c for c in codes if have(c, loc) >= 5]
        if not avail:
            continue
        code = rng.choice(avail)
        counted = max(0, have(code, loc) + rng.choice([-3, -2, -1, 1, 2]))
        reason = "FOUND" if counted > have(code, loc) else rng.choice(["DAMAGED", "LOST", "COUNT"])
        stock[code][loc] = counted
        add(
            day,
            {
                "op": "adj",
                "loc": loc,
                "date": day.isoformat(),
                "reason": reason,
                "note": f"Stock count: {reason.lower()}",
                "lines": [[code, counted]],
            },
        )
    for _ in range(5):
        day = day_between(rich_after, END)
        loc = rng.choices(LOCATIONS, LOC_WEIGHTS)[0]
        code = rng.choice(codes)
        q = rng.randint(1, 5)
        stock[code][loc] += q
        add(
            day,
            {
                "op": "in",
                "loc": loc,
                "subtype": "RETURN",
                "party": rng.choice(sites_used),
                "ref": "",
                "lines": [[code, q, "", ""]],
            },
        )

    # ---- return batches near the end ------------------------------------------------------------------------
    for k in range(10):
        day = date(2026, 7, 1) + timedelta(days=k * 8)
        add(
            day,
            {
                "op": "batch",
                "key": f"B{k + 1:02d}",
                "date": day.isoformat(),
                "company": "Wipro Lighting",
                "n": rng.randint(3, 10),
                "courier": rng.choice(["Blue Dart", "DTDC", "Professional Couriers", "VRL"]),
                "docket": f"{rng.choice(['BD', 'DT', 'PC'])}{rng.randint(100000, 999999)}",
                "dispatch": TODAY.isoformat(),
                "settle": [
                    ["REPLACED", 0.4, rng.choice(["Vizag Office", "Svkml"])],
                    ["REPAIRED", 0.2, "Vizag Office"],
                    ["REJECTED_SCRAPPED", 0.2, ""],
                    ["REJECTED_RETURNED", 0.2, ""],
                ]
                if k < 6
                else [],
            },
        )

    # ---- put it in date order. Stock is checked per day, so sort stably, masters first --------------------------
    events.sort(key=lambda e: (e[0], e[1]))
    # the generation order let some OUTs use stock whose IN is dated later; re-simulate in date order and drop
    # or trim anything that is not valid at its date, so "expected valid" stays true
    live = {c: {loc: 0 for loc in LOCATIONS} for c in codes}
    ordered, dropped = [], 0
    for day, _, op in events:
        kind = op["op"]
        if kind in ("in", "trf", "out", "adj", "mark", "visit"):
            loc = op.get("loc")
            if kind == "in":
                for code, q, *_ in op["lines"]:
                    live[code][loc] += q
            elif kind in ("out", "mark", "trf", "visit"):
                rows = op["lines"] if kind != "visit" else op["parts"]
                ok = [(c, q) for c, q, *_ in rows if live[c][loc] >= q]
                for code, q in ok:
                    live[code][loc] -= q
                    if kind == "trf":
                        live[code][op["to"]] += q
                if len(ok) != len(rows):
                    dropped += len(rows) - len(ok)
                    if kind == "visit":
                        keep = {c for c, _ in ok}
                        op["parts"] = [p for p in op["parts"] if p[0] in keep]
                        op["collected"] = [c for c in op["collected"] if c[0] in keep]
                    else:
                        op["lines"] = [r for r in op["lines"] if r[0] in {c for c, _ in ok}]
                    if kind != "visit" and not op["lines"]:
                        continue
            elif kind == "adj":
                code, counted = op["lines"][0][:2]
                if counted == live[code][loc]:  # nothing to adjust once earlier steps landed in date order
                    continue
                op["lines"] = [[code, counted, live[code][loc]]]  # what the user saw: the system quantity
                live[code][loc] = counted
        op.setdefault("date", day.isoformat())
        ordered.append(op)

    messy = [
        {
            "what": "quantity text from the Excel sheet",
            "values": ["22 NOS", "1NOS", "`7NOS", "7 nos", "٣"],
            "expect": "refused",
        },
        {
            "what": "phones from the complaint sheet",
            "values": ["996394502", "88410", "8790022266", "9866832284"],
            "expect": "9 and 5 digit refused; 10 digit accepted",
        },
        {
            "what": "site names as typed in Excel",
            "values": ["Iocl  Office Holiday Home", "laurus labs-unit-4", "Chenna Keshava;lu"],
            "expect": "accepted, spaces tidied",
        },
        {
            "what": "status words in the wrong column",
            "values": ["Saturday", "Closed Not wipro product", "   "],
            "expect": "not a valid status",
        },
    ]
    summary = {
        k: sum(1 for o in ordered if o["op"] == k)
        for k in ("in", "out", "trf", "adj", "mark", "cmp", "visit", "status", "notcovered", "batch")
    }
    summary["items"], summary["sites"], summary["pieces_marked_or_collected"] = (
        len(items),
        len(site_list),
        pieces_in_store,
    )
    OUT.write_text(
        json.dumps(
            {
                "masters": masters,
                "sites": site_list,
                "timeline": ordered,
                "messy": messy,
                "summary": summary,
                "model_dropped_lines": dropped,
                "expected_good_stock_before_settles": live,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=1))
    print("lines dropped when re-simulating in date order:", dropped)


if __name__ == "__main__":
    main()
