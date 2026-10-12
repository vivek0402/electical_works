"""Generate demo-data.json for the service mockup: stock + complaints + defective pieces, one shared ledger.

Items are cleaned up from the client's sample sheets (real codes). Sites, contacts and complaint faults come from
the AP pending complaints sheet; defective codes from the Vizag defective list. Quantities, dates and history are
invented. Every ledger effect goes through post(), which refuses to let any location go below zero, and all
activity is generated day by day so the ledger is in date order. Run:  python make_demo_data.py
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(11)
TODAY = date(2026, 10, 12)
START = TODAY - timedelta(days=40)

LOCATIONS = ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"]  # good-stock locations only
DEF_STORE = "Defective store"  # flagged is_defective_store in the real app; never in entry-form pickers
SPARE_TYPES = ["Driver", "PCB / LED module", "Lens", "Complete fitting", "Controller", "Switch",
               "Wire / cable", "Accessory", "Other"]
FITTING_TYPES = ["Flood light", "Linear / batten", "Street light", "High bay", "Downlight",
                 "Well glass", "Bulkhead", "Panel"]
UNITS = ["NOS", "MTR", "ROLL", "BOX", "PKT"]
COMPANIES = ["Wipro Lighting", "Havells", "Finolex Cables", "Sri Sai Electricals", "Lakshmi Traders"]
TECHNICIANS = ["Ramu", "Apparao", "Srinuvas", "Jagadeesh"]
CUSTOMERS = ["Laurus Labs Unit-2, Vizag", "Dr Reddys, Vizag", "GMR Airport, Vizag", "BARC, Vizag",
             "IISER, Tirupati", "NACIN, Anantapur", "Punjab National Bank, Gudivada",
             "Siri Filling Station, Nellore", "Master Minds, Guntur"]
COURIERS = ["DTDC", "Professional Couriers", "ST Courier", "VRL Logistics", "By hand"]
NOT_COVERED_REASONS = ["Not our product", "Out of warranty", "Customer cancelled", "Other"]
USERS = ["Office", "Admin"]

# code, spare type, description, product cat ref (fitting), fitting type, W, mA, company, unit,
# reorder level, other spellings
ITEMS = [
    ("LG78-150-700", "Driver", "LED driver 150W 700mA", "LF40-192-060-57-HE", "Flood light", 150, 700, "Wipro Lighting", "NOS", 5, ["EDC-150-S105SV-3007"]),
    ("LG76-150-700FH", "Driver", "LED driver 150W 700mA (FH)", "LR22-781-XXX-57-XX", "Street light", 150, 700, "Wipro Lighting", "NOS", 10, []),
    ("LG76-200-700F", "Driver", "LED driver 200W 700mA", "LF40-502-060-57-HE2", "Flood light", 200, 700, "Wipro Lighting", "NOS", 10, []),
    ("LG75-150-215-70E", "Driver", "LED driver 150W", "LR40-272-060-7-XX", "High bay", 150, None, "Wipro Lighting", "NOS", 5, []),
    ("LG83-072-103-0700", "Driver", "LED driver 72W 700mA", "LF20-102-060-57-G3", "Flood light", 72, 700, "Wipro Lighting", "NOS", 10, []),
    ("LG30-018-054-0300", "Driver", "LED driver 18W 300mA", "LL20-111-XXX-65AL", "Linear / batten", 18, 300, "Wipro Lighting", "NOS", 10, ["LG30-018-054-300"]),
    ("LG26-048-0720", "Driver", "LED driver 48W 720mA", "LD80-171-XXX-60-XX", "Downlight", 48, 720, "Wipro Lighting", "NOS", 5, ["LG26-048-720"]),
    ("LG66-036-036-900S", "Driver", "LED driver 36W 900mA", "LR08-132-XXX-57-XX", "Street light", 36, 900, "Wipro Lighting", "NOS", 5, []),
    ("LG66-040-078-480IT", "Driver", "LED driver 40W 480mA", "LW07-141-XXX57G1", "Well glass", 40, 480, "Wipro Lighting", "NOS", 5, []),
    ("15WATT (190MA)", "Driver", "LED driver 15W 190mA (generic)", "", "", 15, 190, "Wipro Lighting", "NOS", 10, ["15WATT DRIVERS"]),
    ("18WATT DRIVERS", "Driver", "LED driver 18W (generic)", "", "", 18, None, "Wipro Lighting", "NOS", 10, []),
    ("EIO6006", "PCB / LED module", "LED module", "LD80-171-XXX-60-XX", "Downlight", None, None, "Wipro Lighting", "NOS", 10, []),
    ("EIO9326", "PCB / LED module", "LED module", "LL20-111-XXX-65AL", "Linear / batten", None, None, "Wipro Lighting", "NOS", 10, []),
    ("EIO8437", "PCB / LED module", "LED module", "LD81-171-XXX-60-XX", "Downlight", None, None, "Wipro Lighting", "NOS", 5, ["EI08437"]),
    ("WPWG-5050-15SIP", "PCB / LED module", "LED strip PCB", "LL20-281-XXX-65AL1", "Linear / batten", None, None, "Wipro Lighting", "NOS", 5, []),
    ("FTS-KC-60-57K", "PCB / LED module", "LED PCB 5700K", "LF20-102-060-57-G3", "Flood light", None, None, "Wipro Lighting", "NOS", 50, []),
    ("LH21-200-180-30S6P", "PCB / LED module", "LED module 6P", "LR40-272-060-7-XX", "High bay", None, None, "Wipro Lighting", "NOS", 5, []),
    ("LF40-192-060-57-HE", "Complete fitting", "Flood light 192W", "LF40-192-060-57-HE", "Flood light", 192, None, "Wipro Lighting", "NOS", 2, []),
    ("LL20-111-XXX-65-NE3", "Complete fitting", "Linear fitting", "LL20-111-XXX-65-NE3", "Linear / batten", None, None, "Wipro Lighting", "NOS", 0, ["LL20-111-XXX-65NE3"]),
    ("LF20-102-060-57-G3", "Complete fitting", "Flood light 102W", "LF20-102-060-57-G3", "Flood light", 102, None, "Wipro Lighting", "NOS", 5, []),
    ("BULKHEAD 12W", "Complete fitting", "Bulkhead fitting 12W", "", "Bulkhead", 12, None, "Wipro Lighting", "NOS", 5, ["BULCK HEAD"]),
    ("LENS", "Lens", "Lens (generic)", "", "", None, None, "Wipro Lighting", "NOS", 10, []),
    ("WCS-IS-DA4", "Controller", "iSense DALI controller", "", "", None, None, "Wipro Lighting", "NOS", 2, ["ISENSE DALI CONTROLLER"]),
    ("ISENSE 8BUTTON SWITCH", "Switch", "iSense 8-button switch", "", "", None, None, "Wipro Lighting", "NOS", 2, []),
    ("WIRE 1.5 SQMM", "Wire / cable", "Copper wire 1.5 sq.mm", "", "", None, None, "Finolex Cables", "MTR", 100, []),
    ("WIRE 2.5 SQMM", "Wire / cable", "Copper wire 2.5 sq.mm", "", "", None, None, "Finolex Cables", "MTR", 100, []),
    ("MCB 16A SP", "Accessory", "MCB 16A single pole", "", "", None, None, "Havells", "NOS", 5, []),
    ("CABLE TIE 200MM", "Accessory", "Cable ties 200mm (pack of 100)", "", "", None, None, "Lakshmi Traders", "PKT", 3, []),
    # Added for the service demo: non-Wipro products that fail at sites.
    ("HV-BATTEN-20W", "Complete fitting", "LED batten 20W", "", "Linear / batten", 20, None, "Havells", "NOS", 3, []),
    ("FX-MODSW-6A", "Switch", "Modular switch 6A", "", "", None, None, "Finolex Cables", "NOS", 10, []),
    ("SSE-DRV-24W", "Driver", "LED driver 24W 500mA", "", "", 24, 500, "Sri Sai Electricals", "NOS", 5, []),
]

items = [dict(code=c, type=t, desc=d, catRef=cr, fittingType=ft, watt=w, ma=ma, company=co, unit=u,
              reorder=r, aliases=a, active=True) for c, t, d, cr, ft, w, ma, co, u, r, a in ITEMS]
ITEM = {i["code"]: i for i in items}
balance = {}
entries = []
seq = {"IN": 0, "OUT": 0, "TRF": 0, "ADJ": 0, "REV": 0}


def bal(code, loc):
    return balance.get((code, loc), 0)


def post(kind, day, lines, **head):
    delta = {}
    for ln in lines:
        delta[(ln["code"], ln["loc"])] = delta.get((ln["code"], ln["loc"]), 0) + ln["qty"]
    for k, q in delta.items():
        assert bal(*k) + q >= 0, (kind, k, bal(*k), q)
    for k, q in delta.items():
        balance[k] = bal(*k) + q
    seq[kind] += 1
    entry = {"no": f"{kind}-{seq[kind]:04d}", "kind": kind, "date": day.isoformat(),
             "by": head.pop("by", random.choice(USERS)), "lines": lines, **head}
    entries.append(entry)
    return entry


def line(code, loc, qty, batch="", pkd=""):
    return {"code": code, "loc": loc, "qty": qty, "batch": batch, "pkd": pkd}


# ---------------------------------------------------------------- service masters
# Sites from the AP pending complaints sheet, cleaned up: title case, proper city names, contacts tidied.
# Phones are kept where the sheet had a valid 10-digit mobile number; short or missing ones are filled in.
SITE_ROWS = [
    ("Punjab National Bank", "Gudivada", "Branch manager", "9866832284"),
    ("NSL Textiles", "Guntur", "Jagadeesh", ""),
    ("Vaishaki Bio Marine", "Visakhapatnam", "R. Apparao", ""),
    ("Sanvira Industries", "Visakhapatnam", "Srinuvas", "8790022266"),
    ("BARC", "Visakhapatnam", "Chenna Keshavulu", "9849669594"),
    ("Laurus Labs Unit-2", "Visakhapatnam", "Murthy", "9908127999"),
    ("Laurus Labs Unit-4", "Visakhapatnam", "Bujji Babu", "8008885869"),
    ("Sri Kathyayani Filling Station", "Nellore", "Station manager", "8886737502"),
    ("GMR Airport", "Visakhapatnam", "Srinuvas", "7288002455"),
    ("Siri Filling Station", "Nellore", "Ganesh", "9490399389"),
    ("Dr Reddys", "Visakhapatnam", "Chandra Mouli", "9912190903"),
    ("Anna Olea", "Nellore", "Vishnu", "9059599595"),
    ("IISER", "Tirupati", "Estate office", ""),
    ("IIT", "Tirupati", "Estate office", ""),
    ("Master Minds", "Guntur", "Sindhu", "9154152894"),
    ("NACIN", "Anantapur", "Mahesh", "8885344504"),
    ("IOCL Holiday Home", "Tirupati", "Naidu", "7981018599"),
    ("VN Energies", "Vijayawada", "Rama Krishna", "7989445116"),
]
sites = []
for n, (name, city, contact, phone) in enumerate(SITE_ROWS, 1):
    sites.append({"id": n, "name": name, "city": city, "contact": contact,
                  "phone": phone or f"9{random.randint(100000000, 999999999)}", "address": "", "active": True})
SITE = {s["name"]: s for s in sites}
techs = [{"name": t, "phone": f"9{random.randint(100000000, 999999999)}", "active": True} for t in TECHNICIANS]

complaints, cevents, visits, pieces, pevents, batches = [], [], [], [], [], []
cseq, vseq, tseq, bseq = [0], [0], [0], [0]
OPEN = {"NOT_ATTENDED", "ATTENDED", "MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"}
TRANSITIONS = {  # same dict as data.js / the real app's complaints.services
    "NOT_ATTENDED": ["ATTENDED", "NOT_COVERED"],
    "ATTENDED": ["MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED", "NOT_COVERED"],
    "MATERIAL_CHECK": ["ATTENDED", "AWAITING_MATERIAL", "RESOLVED", "NOT_COVERED"],
    "AWAITING_MATERIAL": ["ATTENDED", "MATERIAL_CHECK", "RESOLVED", "NOT_COVERED"],
    "RESOLVED": ["CLOSED", "ATTENDED", "NOT_COVERED"],
    "CLOSED": [],
    "NOT_COVERED": [],
}


def file_complaint(day, site, company, fault, qty, priority, techs_, ref=""):
    cseq[0] += 1
    s = SITE[site]
    c = {"no": f"CMP-{cseq[0]:04d}", "site": s["id"], "company": company, "companyRef": ref, "fault": fault,
         "qty": qty, "reportedOn": day.isoformat(), "priority": priority, "techs": techs_, "status": "NOT_ATTENDED",
         "contact": s["contact"], "phone": s["phone"], "notCoveredReason": "", "closedOn": None}
    complaints.append(c)
    cevents.append({"complaint": c["no"], "from": None, "to": "NOT_ATTENDED", "at": day.isoformat(), "by": "Office",
                    "note": "Complaint filed"})
    return c


def change_status(c, to, day, note="", reason=""):
    assert to in TRANSITIONS[c["status"]], (c["no"], c["status"], to)
    cevents.append({"complaint": c["no"], "from": c["status"], "to": to, "at": day.isoformat(), "by": "Office",
                    "note": note, **({"reason": reason} if reason else {})})
    c["status"] = to
    if to in ("CLOSED", "NOT_COVERED"):
        c["closedOn"] = day.isoformat()
    if reason:
        c["notCoveredReason"] = reason


def new_piece(day, code, batch, pkd, fault, source, complaint=None, visit=None, entry=None):
    tseq[0] += 1
    p = {"tag": f"DEF-{tseq[0]:04d}", "code": code, "company": ITEM[code]["company"], "batch": batch, "pkd": pkd,
         "fault": fault, "source": source, "complaint": complaint, "visit": visit, "collectedOn": day.isoformat(),
         "status": "IN_STORE", "batchNo": None, "outcome": None, "settledOn": None, "entry": entry}
    pieces.append(p)
    pevents.append({"tag": p["tag"], "from": None, "to": "IN_STORE", "at": day.isoformat(), "by": "Office",
                    "note": f"Collected at site ({complaint})" if complaint else "Marked defective from stock"})
    return p


def record_visit(c, day, techs_, work, parts=(), collected=(), next_status=None, loc="Vizag Office"):
    vseq[0] += 1
    vno = f"VIS-{vseq[0]:04d}"
    site = next(s for s in sites if s["id"] == c["site"])
    party = f"{site['name']}, {site['city']}"
    given = [(code, min(q, bal(code, loc))) for code, q in parts]
    given = [(code, q) for code, q in given if q > 0]
    out = post("OUT", day, [line(code, loc, -q) for code, q in given], subtype="COMPLAINT", party=party,
               ref=c["no"], complaint=c["no"], by="Office") if given else None
    col = None
    tags = []
    if collected:
        col = post("IN", day, [line(code, DEF_STORE, q, b, pkd) for code, q, b, pkd, _ in collected],
                   subtype="DEFECTIVE_COLLECTED", party=party, ref=c["no"], complaint=c["no"], by="Office")
        for code, q, b, pkd, fault in collected:
            for _ in range(q):
                tags.append(new_piece(day, code, b, pkd, fault, "SITE_VISIT", c["no"], vno, col["no"])["tag"])
    v = {"no": vno, "complaint": c["no"], "date": day.isoformat(), "techs": techs_, "work": work,
         "nextStatus": next_status or c["status"], "outEntry": out["no"] if out else None,
         "collectEntry": col["no"] if col else None, "tags": tags}
    visits.append(v)
    if c["status"] == "NOT_ATTENDED":
        change_status(c, "ATTENDED", day, f"Visit {vno}")
    if next_status and next_status != c["status"]:
        change_status(c, next_status, day, f"Visit {vno}")
    return v


def mark_defective(day, loc, code, qty, fault):
    qty = min(qty, bal(code, loc))
    if qty <= 0:
        return []
    e = post("TRF", day, [line(code, loc, -qty), line(code, DEF_STORE, qty)], party=DEF_STORE,
             note=f"Marked defective: {fault}", by="Office")
    return [new_piece(day, code, "", "", fault, "FOUND_IN_STOCK", entry=e["no"])["tag"] for _ in range(qty)]


def piece(tag):
    return next(p for p in pieces if p["tag"] == tag)


def create_batch(company, day, tags, note=""):
    bseq[0] += 1
    b = {"no": f"RB-{bseq[0]:04d}", "company": company, "createdOn": day.isoformat(), "status": "DRAFT",
         "dispatchedOn": None, "docket": "", "courier": "", "note": note, "dispatchEntry": None, "lines": []}
    batches.append(b)
    for t in tags:
        p = piece(t)
        assert p["status"] == "IN_STORE" and p["company"] == company
        p["status"], p["batchNo"] = "IN_BATCH", b["no"]
        b["lines"].append({"tag": t, "outcome": None, "settledOn": None, "toLoc": None, "entry": None})
        pevents.append({"tag": t, "from": "IN_STORE", "to": "IN_BATCH", "at": day.isoformat(), "by": "Office",
                        "note": f"Added to {b['no']}"})
    return b


def dispatch(b, day, docket, courier):
    assert b["lines"]
    codes = {}
    for ln in b["lines"]:
        codes[piece(ln["tag"])["code"]] = codes.get(piece(ln["tag"])["code"], 0) + 1
    e = post("OUT", day, [line(c, DEF_STORE, -q) for c, q in codes.items()], subtype="RETURN_TO_COMPANY",
             party=b["company"], ref=docket, batch=b["no"], by="Office")
    b.update(status="DISPATCHED", dispatchedOn=day.isoformat(), docket=docket, courier=courier, dispatchEntry=e["no"])
    for ln in b["lines"]:
        piece(ln["tag"])["status"] = "SENT"
        pevents.append({"tag": ln["tag"], "from": "IN_BATCH", "to": "SENT", "at": day.isoformat(), "by": "Office",
                        "note": f"Dispatched with {b['no']} ({courier} {docket})"})


def settle(b, tags, outcome, day, to_loc=None):
    for t in tags:
        p, ln = piece(t), next(x for x in b["lines"] if x["tag"] == t)
        assert p["status"] == "SENT"
        e = None
        if outcome in ("REPLACED", "REPAIRED"):
            e = post("IN", day, [line(p["code"], to_loc, 1)], subtype="REPLACEMENT", party=b["company"],
                     ref=b["no"], batch=b["no"], note=f"{outcome.title()} for {t}", by="Office")
        elif outcome == "REJECTED_RETURNED":
            e = post("IN", day, [line(p["code"], DEF_STORE, 1)], subtype="DEFECTIVE_RETURNED", party=b["company"],
                     ref=b["no"], batch=b["no"], note=f"Rejected by company, {t} sent back", by="Office")
        ln.update(outcome=outcome, settledOn=day.isoformat(), toLoc=to_loc, entry=e["no"] if e else None)
        p["outcome"], p["settledOn"] = outcome, day.isoformat()
        new = "IN_STORE" if outcome == "REJECTED_RETURNED" else "SETTLED"
        pevents.append({"tag": t, "from": "SENT", "to": new, "at": day.isoformat(), "by": "Office",
                        "note": f"{b['no']}: {outcome.replace('_', ' ').capitalize()}"})
        p["status"] = new
        if new == "IN_STORE":
            p["batchNo"] = None


def scrap(tags, day, reason):
    codes = {}
    for t in tags:
        codes[piece(t)["code"]] = codes.get(piece(t)["code"], 0) + 1
    e = post("ADJ", day, [line(c, DEF_STORE, -q) for c, q in codes.items()], reason="Damaged",
             note=f"Scrapped {', '.join(tags)}: {reason}", by="Office")
    for t in tags:
        p = piece(t)
        pevents.append({"tag": t, "from": p["status"], "to": "SCRAPPED", "at": day.isoformat(), "by": "Office",
                        "note": reason})
        p["status"], p["outcome"], p["settledOn"], p["entry"] = "SCRAPPED", None, day.isoformat(), e["no"]


def in_store(company, n, codes=None):
    got = [p["tag"] for p in pieces if p["status"] == "IN_STORE" and p["company"] == company
           and (codes is None or p["code"] in codes)]
    return got[:n]


def b(prefix="B"):
    return f"{prefix}{random.randint(2401, 2609)}"


def pkd():
    return f"{random.choice([2025, 2026])}-{random.randint(1, 9):02d}"


# ---------------------------------------------------------------- complaints script
# (site, company, fault, qty affected, reported days ago, priority, technicians, company ref, steps)
# steps: (days after reported, action, args). Actions: visit(work, parts, collected, next) | status(to, note, reason)
W, H, F, S = "Wipro Lighting", "Havells", "Finolex Cables", "Sri Sai Electricals"
COMPLAINTS = [
    ("Punjab National Bank", W, "15W drivers not working in 18 fittings", 18, 48, "High", ["Apparao"], "WL/AP/24871", [
        (9, "visit", ("Checked all 18 fittings; 4 drivers dead, taken for testing", [], [("15WATT (190MA)", 4, "fault: no output")], "MATERIAL_CHECK")),
        (10, "status", ("AWAITING_MATERIAL", "Drivers not in stock, ordered", "")),
        (28, "visit", ("Fitted 4 new drivers, all fittings working", [("15WATT (190MA)", 4)], [], "RESOLVED")),
        (30, "status", ("CLOSED", "Customer confirmed on phone", "")),
    ]),
    ("NSL Textiles", W, "Material at office, 6 fittings to be replaced", 6, 30, "Normal", ["Jagadeesh"], "", []),
    ("Vaishaki Bio Marine", W, "Flood lights not glowing in yard", 3, 26, "Normal", ["Ramu"], "WL/AP/25102", [
        (2, "visit", ("2 flood light drivers failed, brought to office for checking", [], [("LG78-150-700", 2, "no output")], "MATERIAL_CHECK")),
    ]),
    ("Sanvira Industries", W, "Linear fittings flickering on 2nd floor", 5, 22, "Normal", ["Ramu"], "WL/AP/25177", [
        (1, "visit", ("3 drivers flickering, removed", [], [("LG30-018-054-0300", 3, "flickering")], "MATERIAL_CHECK")),
        (4, "status", ("AWAITING_MATERIAL", "Waiting for 18W drivers from the company", "")),
    ]),
    ("BARC", W, "High bay lights failed in shed 3", 4, 35, "Urgent", ["Ramu", "Apparao"], "WL/AP/24990", [
        (2, "visit", ("Removed 2 drivers and 1 LED module from high bays", [], [("LG75-150-215-70E", 2, "burnt smell"), ("LH21-200-180-30S6P", 1, "LEDs dark")], "MATERIAL_CHECK")),
        (5, "status", ("AWAITING_MATERIAL", "Spares requested", "")),
        (23, "visit", ("Fitted replacement drivers and module; shed 3 fully lit", [("LG75-150-215-70E", 2), ("LH21-200-180-30S6P", 1)], [], "RESOLVED")),
    ]),
    ("Laurus Labs Unit-2", W, "Street lights not working near main gate", 2, 20, "High", ["Ramu"], "WL/AP/25230", [
        (1, "visit", ("Both drivers dead, removed for return", [], [("LG76-150-700FH", 2, "no output")], "MATERIAL_CHECK")),
        (4, "status", ("AWAITING_MATERIAL", "FH drivers on order", "")),
    ]),
    ("Laurus Labs Unit-4", W, "Downlights dim in QC lab", 6, 3, "Normal", [], "", []),
    ("Sri Kathyayani Filling Station", W, "7 linear fittings not working", 7, 25, "Normal", ["Jagadeesh"], "", [
        (2, "status", ("NOT_COVERED", "Fittings are another brand, not supplied by us", "Not our product")),
    ]),
    ("GMR Airport", W, "Flood light drivers failed on apron", 4, 16, "Urgent", ["Srinuvas", "Ramu"], "WL/AP/25311", [
        (1, "visit", ("Replaced 2 drivers; 2 more fittings to check at night", [("LG76-200-700F", 2)], [("LG76-200-700F", 2, "no output")], "ATTENDED")),
    ]),
    ("Siri Filling Station", W, "18W drivers not working in linear fittings", 6, 12, "Normal", ["Jagadeesh"], "WL/AP/25402", []),
    ("Dr Reddys", W, "Well glass fittings tripping MCB", 3, 1, "High", [], "", []),
    ("Anna Olea", W, "Bulkhead fittings not working in plant", 4, 38, "Normal", ["Jagadeesh"], "WL/AP/24935", [
        (2, "visit", ("Replaced 2 bulkheads from stock", [("BULKHEAD 12W", 2)], [("BULKHEAD 12W", 2, "water ingress")], "RESOLVED")),
        (8, "status", ("CLOSED", "Customer signed job card", "")),
    ]),
    ("IISER", W, "iSense DALI controller not responding", 1, 28, "High", ["Srinuvas"], "WL/AP/25066", [
        (2, "visit", ("Controller dead, brought to office", [], [("WCS-IS-DA4", 1, "no power")], "MATERIAL_CHECK")),
    ]),
    ("IIT", W, "Linear fittings LED module burnt", 8, 10, "Normal", ["Srinuvas"], "WL/AP/25455", [
        (2, "visit", ("Changed 3 LED modules, 5 fittings still to check", [("EIO9326", 3)], [("EIO9326", 3, "LEDs burnt")], "ATTENDED")),
    ]),
    ("Master Minds", W, "Panel lights not glowing in 2 classrooms", 2, 33, "Normal", ["Jagadeesh"], "WL/AP/25012", [
        (2, "visit", ("Changed 2 LED modules", [("EIO6006", 2)], [("EIO6006", 2, "no light")], "RESOLVED")),
        (6, "status", ("CLOSED", "", "")),
    ]),
    ("NACIN", W, "Street light drivers failed on campus road", 5, 18, "Normal", ["Jagadeesh", "Apparao"], "WL/AP/25270", [
        (3, "visit", ("2 drivers removed for checking", [], [("LG66-036-036-900S", 2, "intermittent")], "MATERIAL_CHECK")),
    ]),
    ("IOCL Holiday Home", W, "Material at office, downlights to be fitted", 2, 40, "Normal", ["Srinuvas"], "", [
        (3, "visit", ("Site checked, drivers needed", [], [], "ATTENDED")),
        (15, "visit", ("Fitted 2 drivers, old ones collected", [("LG26-048-0720", 2)], [("LG26-048-0720", 2, "no output")], "RESOLVED")),
        (16, "status", ("CLOSED", "", "")),
    ]),
    ("VN Energies", S, "Petrol pump canopy lights not working", 4, 9, "Normal", ["Apparao"], "SSE-1182", [
        (2, "visit", ("Changed 2 drivers", [("SSE-DRV-24W", 2)], [("SSE-DRV-24W", 2, "no output")], "RESOLVED")),
    ]),
    ("GMR Airport", H, "MCBs tripping in terminal DB", 3, 14, "High", ["Srinuvas"], "HV-C-77812", [
        (1, "visit", ("Changed 3 MCBs", [("MCB 16A SP", 3)], [("MCB 16A SP", 3, "trips at low load")], "RESOLVED")),
    ]),
    ("Dr Reddys", H, "LED battens failed in canteen", 4, 11, "Normal", ["Ramu"], "HV-C-78020", [
        (1, "visit", ("2 battens removed for checking", [], [("HV-BATTEN-20W", 2, "no light")], "MATERIAL_CHECK")),
    ]),
    ("Laurus Labs Unit-2", F, "Modular switches burnt in admin block", 3, 6, "Normal", ["Ramu"], "", [
        (1, "visit", ("Changed 3 switches", [("FX-MODSW-6A", 3)], [("FX-MODSW-6A", 3, "burnt contacts")], "ATTENDED")),
    ]),
    ("Sanvira Industries", F, "Wiring heating near main DB", 1, 2, "Urgent", [], "", []),
    ("BARC", H, "MCB not resetting in pump house", 2, 0, "Normal", [], "", []),
    ("Vaishaki Bio Marine", W, "Flood light lens cracked", 2, 5, "Normal", ["Ramu"], "WL/AP/25520", [
        (1, "visit", ("Changed 2 lenses", [("LENS", 2)], [("LENS", 2, "cracked")], "ATTENDED")),
    ]),
    ("Master Minds", W, "Downlight LED module failed", 1, 7, "Normal", ["Jagadeesh"], "WL/AP/25488", [
        (1, "visit", ("Changed LED module", [("EIO8437", 1)], [("EIO8437", 1, "no light")], "RESOLVED")),
    ]),
    ("IISER", S, "Corridor light drivers failing", 2, 17, "Normal", ["Srinuvas"], "SSE-1160", [
        (1, "visit", ("Changed 2 drivers", [("SSE-DRV-24W", 2)], [("SSE-DRV-24W", 2, "no output")], "RESOLVED")),
        (3, "status", ("CLOSED", "", "")),
    ]),
]

schedule = {}  # date -> list of callables, run in order


def at(day, fn):
    schedule.setdefault(day, []).append(fn)


for site, co, fault, qty, ago, prio, tlist, ref, steps in sorted(COMPLAINTS, key=lambda c: -c[4]):
    rep = TODAY - timedelta(days=ago)
    holder = {}
    at(rep, lambda site=site, co=co, fault=fault, qty=qty, rep=rep, prio=prio, tlist=tlist, ref=ref, holder=holder:
       holder.setdefault("c", file_complaint(rep, site, co, fault, qty, prio, tlist, ref)))
    for off, action, args in steps:
        day = rep + timedelta(days=off)
        assert START < day <= TODAY, (site, off)
        if action == "visit":
            work, parts, collected, nxt = args
            col = [(code, q, b(), pkd(), f) for code, q, f in collected]
            at(day, lambda holder=holder, day=day, work=work, parts=parts, col=col, nxt=nxt, tlist=tlist:
               record_visit(holder["c"], day, tlist or ["Ramu"], work, parts, col, nxt))
        else:
            to, note, reason = args
            at(day, lambda holder=holder, day=day, to=to, note=note, reason=reason:
               change_status(holder["c"], to, day, note, reason))

# Defectives found in stock, return batches, settlement and scrapping.
d = lambda n: TODAY - timedelta(days=n)  # noqa: E731
at(d(35), lambda: mark_defective(d(35), "Vizag Office", "LG30-018-054-0300", 3, "Dead on arrival from last delivery"))
at(d(32), lambda: mark_defective(d(32), "Vizag Office", "FTS-KC-60-57K", 5, "LEDs dead, found during count"))
at(d(28), lambda: mark_defective(d(28), "Vizag Office", "MCB 16A SP", 2, "Does not latch"))
at(d(20), lambda: mark_defective(d(20), "Vizag Office", "WPWG-5050-15SIP", 3, "Strip cut, half dark"))
at(d(15), lambda: scrap(in_store(W, 1, {"FTS-KC-60-57K"}), d(15), "Physically broken, not worth returning"))
at(d(9), lambda: mark_defective(d(9), "Vizag Office", "LG83-072-103-0700", 2, "No output on bench test"))
at(d(3), lambda: mark_defective(d(3), "TV Shop", "LG76-200-700F", 1, "Burnt smell"))
at(d(3), lambda: mark_defective(d(3), "Vizag Office", "HV-BATTEN-20W", 1, "Cracked diffuser, LEDs off"))
RB = {}
at(d(26), lambda: RB.setdefault(1, create_batch(W, d(26), in_store(W, 4, {"15WATT (190MA)"}) + in_store(W, 2, {"BULKHEAD 12W"}),
                                                "Drivers from PNB and bulkheads from Anna Olea")))
at(d(24), lambda: dispatch(RB[1], d(24), "D51243817", "DTDC"))
at(d(10), lambda: settle(RB[1], [ln["tag"] for ln in RB[1]["lines"][:2]], "REPLACED", d(10), "Vizag Office"))
at(d(10), lambda: settle(RB[1], [RB[1]["lines"][2]["tag"]], "REPAIRED", d(10), "Vizag Office"))
at(d(10), lambda: settle(RB[1], [RB[1]["lines"][3]["tag"]], "REJECTED_RETURNED", d(10)))
at(d(9), lambda: RB.setdefault(2, create_batch(H, d(9), in_store(H, 3, {"MCB 16A SP"}), "MCBs for warranty claim")))
at(d(6), lambda: dispatch(RB[2], d(6), "PC-7781203", "Professional Couriers"))
at(d(2), lambda: RB.setdefault(3, create_batch(W, d(2), in_store(W, 2, {"LG78-150-700"}) + in_store(W, 2, {"LG30-018-054-0300"}),
                                               "Next Wipro return")))

# ---------------------------------------------------------------- stock history, day by day
opening = {"WIRE 1.5 SQMM": 300, "WIRE 2.5 SQMM": 200, "FTS-KC-60-57K": 220, "CABLE TIE 200MM": 6,
           "LG66-036-036-900S": 4, "EIO8437": 4, "WCS-IS-DA4": 1, "MCB 16A SP": 14, "FX-MODSW-6A": 12,
           "SSE-DRV-24W": 10, "15WATT (190MA)": 24, "BULKHEAD 12W": 12, "HV-BATTEN-20W": 6}
post("IN", START, [line(i["code"], "Vizag Office", opening.get(i["code"], random.randint(3, 40))) for i in items],
     subtype="OPENING", party="Opening stock (first count)", ref="Count sheet 02-09-2026", by="Admin")
post("IN", START, [line("LG76-200-700F", "TV Shop", 8), line("EIO6006", "TV Shop", 6), line("LENS", "Svkml", 10),
                   line("WIRE 1.5 SQMM", "Kartika Class", 50), line("LG30-018-054-0300", "Svkml", 12)],
     subtype="OPENING", party="Opening stock (first count)", ref="Count sheet 02-09-2026", by="Admin")
for day0 in sorted(k for k in schedule if k <= START):  # complaints filed before the ledger starts
    for fn in schedule[day0]:
        fn()

RESERVED = {"15WATT (190MA)", "BULKHEAD 12W", "MCB 16A SP", "FX-MODSW-6A", "SSE-DRV-24W", "HV-BATTEN-20W", "EIO8437"}
wipro = [i["code"] for i in items if i["company"] == W]
day = START + timedelta(days=1)
dc = 4470
while day <= TODAY:
    for fn in schedule.get(day, []):
        fn()
    if day == TODAY or day.weekday() == 6:  # Sunday, or today (nothing random yet)
        day += timedelta(days=1)
        continue
    roll = random.random()
    if roll < 0.18:  # delivery from the company
        dc += random.randint(3, 20)
        codes = random.sample(wipro, random.randint(2, 4))
        post("IN", day, [line(c, "Vizag Office", random.randint(5, 25), b(), pkd()) for c in codes],
             subtype="SUPPLIER", party=W, ref=f"DC {dc}")
    elif roll < 0.25:  # other supplier
        post("IN", day, [line(random.choice(["WIRE 1.5 SQMM", "WIRE 2.5 SQMM"]), "Vizag Office", 100),
                         line("MCB 16A SP", "Vizag Office", 10)],
             subtype="SUPPLIER", party=S, ref=f"Bill SS-{random.randint(100, 400)}")
    elif roll < 0.72:  # issue to site or technician
        loc = random.choice(["Vizag Office"] * 4 + ["TV Shop", "Svkml"])
        avail = [c for (c, lc), q in balance.items() if lc == loc and q > 0 and c not in RESERVED]
        codes = random.sample(avail, min(len(avail), random.randint(1, 3)))
        lines = [line(c, loc, -random.randint(1, min(bal(c, loc), 6 if c[:4] != "WIRE" else 40))) for c in codes]
        if random.random() < 0.7:
            post("OUT", day, lines, subtype="SITE", party=random.choice(CUSTOMERS), ref=f"Job {random.randint(100, 999)}")
        else:
            post("OUT", day, lines, subtype="TECH", party=random.choice(TECHNICIANS), ref="")
    elif roll < 0.82:  # transfer
        src, dst = "Vizag Office", random.choice(LOCATIONS[1:])
        avail = [c for (c, lc), q in balance.items() if lc == src and q > 4 and c[:4] != "WIRE" and c not in RESERVED]
        c = random.choice(avail)
        q = random.randint(2, min(10, bal(c, src)))
        post("TRF", day, [line(c, src, -q), line(c, dst, q)], party=dst, note="Buffer stock")
    if day == TODAY - timedelta(days=6):
        post("ADJ", day, [line("LENS", "Vizag Office", -2)], reason="Damaged", note="2 lenses cracked in storage", by="Admin")
    if day == TODAY - timedelta(days=4):
        post("ADJ", day, [line("CABLE TIE 200MM", "Vizag Office", 1)], reason="Physical count",
             note="Found 1 extra pack during count", by="Admin")
    if day == TODAY - timedelta(days=2):
        wrong = post("OUT", day, [line("EIO9326", "Vizag Office", -min(3, bal("EIO9326", "Vizag Office")))],
                     subtype="SITE", party="Dr Reddys, Vizag", ref="Job 512")
        post("REV", day, [dict(ln, qty=-ln["qty"]) for ln in wrong["lines"]], reverses=wrong["no"],
             note="Entered against the wrong job", by="Admin")
    day += timedelta(days=1)

assert all(q >= 0 for q in balance.values())
store = sum(1 for p in pieces if p["status"] in ("IN_STORE", "IN_BATCH"))  # physically in the store
assert store == sum(q for (c, lc), q in balance.items() if lc == DEF_STORE), "pieces in store must match the ledger"

data = {"today": TODAY.isoformat(), "locations": LOCATIONS, "defStore": DEF_STORE, "spareTypes": SPARE_TYPES,
        "fittingTypes": FITTING_TYPES, "units": UNITS, "companies": COMPANIES, "technicians": TECHNICIANS,
        "customers": CUSTOMERS, "couriers": COURIERS, "notCoveredReasons": NOT_COVERED_REASONS,
        "config": {"defaultCompany": W},
        "items": items, "entries": entries, "sites": sites, "techs": techs, "complaints": complaints,
        "complaintEvents": cevents, "visits": visits, "pieces": pieces, "pieceEvents": pevents, "batches": batches}
out = Path(__file__).with_name("demo-data.json")
out.write_text(json.dumps(data, indent=1), encoding="utf-8")
by_status = {}
for c in complaints:
    by_status[c["status"]] = by_status.get(c["status"], 0) + 1
print(f"{len(items)} items, {len(entries)} entries, {len(sites)} sites, {len(complaints)} complaints {by_status}, "
      f"{len(visits)} visits, {len(pieces)} pieces ({store} in store), {len(batches)} batches -> {out.name}")
