"""Generate demo-data.json for the stock mockup and the sample Excel exports.

Items are cleaned up from the client's sample sheets (real codes). Fitting links, quantities,
customers and history are invented for the demo. Run:  python make_demo_data.py
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(11)
TODAY = date(2026, 10, 11)
START = TODAY - timedelta(days=40)

LOCATIONS = ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"]
SPARE_TYPES = ["Driver", "PCB / LED module", "Lens", "Complete fitting", "Controller", "Switch",
               "Wire / cable", "Accessory", "Other"]
FITTING_TYPES = ["Flood light", "Linear / batten", "Street light", "High bay", "Downlight",
                 "Well glass", "Bulkhead", "Panel"]
UNITS = ["NOS", "MTR", "ROLL", "BOX", "PKT"]
COMPANIES = ["Wipro Lighting", "Finolex Cables", "Havells", "Sri Sai Electricals", "Lakshmi Traders"]
TECHNICIANS = ["Ramu", "Apparao"]
CUSTOMERS = ["Laurus Labs Unit-2, Vizag", "Dr Reddys, Vizag", "GMR Airport, Vizag", "BARC, Vizag",
             "IISER, Tirupati", "Nacin, Anantapur", "Punjab National Bank, Gudivada",
             "Siri Filling Station, Nellore", "Master Minds, Guntur"]
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
]

items = [dict(code=c, type=t, desc=d, catRef=cr, fittingType=ft, watt=w, ma=ma, company=co, unit=u,
              reorder=r, aliases=a, active=True) for c, t, d, cr, ft, w, ma, co, u, r, a in ITEMS]
balance = {}
entries = []
seq = {"IN": 0, "OUT": 0, "TRF": 0, "ADJ": 0, "REV": 0}


def bal(code, loc):
    return balance.get((code, loc), 0)


def post(kind, day, lines, **head):
    for ln in lines:
        assert bal(ln["code"], ln["loc"]) + ln["qty"] >= 0, (kind, ln)
    for ln in lines:
        balance[(ln["code"], ln["loc"])] = bal(ln["code"], ln["loc"]) + ln["qty"]
    seq[kind] += 1
    entry = {"no": f"{kind}-{seq[kind]:04d}", "kind": kind, "date": day.isoformat(),
             "by": head.pop("by", random.choice(USERS)), "lines": lines, **head}
    entries.append(entry)
    return entry


def line(code, loc, qty, batch="", pkd=""):
    return {"code": code, "loc": loc, "qty": qty, "batch": batch, "pkd": pkd}


# Opening count: everything at Vizag Office, a little buffer stock elsewhere.
opening = {"WIRE 1.5 SQMM": 300, "WIRE 2.5 SQMM": 200, "FTS-KC-60-57K": 220, "CABLE TIE 200MM": 6,
           "LG66-036-036-900S": 4, "EIO8437": 4, "WCS-IS-DA4": 1}  # last three start low on purpose
post("IN", START, [line(i["code"], "Vizag Office", opening.get(i["code"], random.randint(3, 40))) for i in items],
     subtype="OPENING", party="Opening stock (first count)", ref="Count sheet 01-09-2026", by="Admin")
post("IN", START, [line("LG76-200-700F", "TV Shop", 8), line("EIO6006", "TV Shop", 6), line("LENS", "Svkml", 10),
                   line("WIRE 1.5 SQMM", "Kartika Class", 50), line("LG30-018-054-0300", "Svkml", 12)],
     subtype="OPENING", party="Opening stock (first count)", ref="Count sheet 01-09-2026", by="Admin")

wipro = [i["code"] for i in items if i["company"] == "Wipro Lighting"]
day = START + timedelta(days=1)
dc = 4470
while day < TODAY:
    if day.weekday() == 6:  # Sunday
        day += timedelta(days=1)
        continue
    roll = random.random()
    if roll < 0.18:  # delivery from Wipro
        dc += random.randint(3, 20)
        codes = random.sample(wipro, random.randint(2, 4))
        post("IN", day, [line(c, "Vizag Office", random.randint(5, 25), f"B{random.randint(2401, 2609)}",
                              f"{random.randint(1, 9):02d}-2026") for c in codes],
             subtype="SUPPLIER", party="Wipro Lighting", ref=f"DC {dc}")
    elif roll < 0.25:  # other supplier
        post("IN", day, [line(random.choice(["WIRE 1.5 SQMM", "WIRE 2.5 SQMM"]), "Vizag Office", 100),
                         line("MCB 16A SP", "Vizag Office", 10)],
             subtype="SUPPLIER", party="Sri Sai Electricals", ref=f"Bill SS-{random.randint(100, 400)}")
    elif roll < 0.75:  # issue to site or technician
        loc = random.choice(["Vizag Office"] * 4 + ["TV Shop", "Svkml"])
        avail = [c for (c, l), q in balance.items() if l == loc and q > 0]
        codes = random.sample(avail, min(len(avail), random.randint(1, 3)))
        lines = [line(c, loc, -random.randint(1, min(bal(c, loc), 6 if c[:4] != "WIRE" else 40))) for c in codes]
        if random.random() < 0.7:
            post("OUT", day, lines, subtype="SITE", party=random.choice(CUSTOMERS), ref=f"Job {random.randint(100, 999)}")
        else:
            post("OUT", day, lines, subtype="TECH", party=random.choice(TECHNICIANS), ref="")
    elif roll < 0.85:  # transfer
        src, dst = "Vizag Office", random.choice(LOCATIONS[1:])
        avail = [c for (c, l), q in balance.items() if l == src and q > 4 and c[:4] != "WIRE"]
        c = random.choice(avail)
        q = random.randint(2, min(10, bal(c, src)))
        post("TRF", day, [line(c, src, -q), line(c, dst, q)], party=dst, note="Buffer stock")
    day += timedelta(days=1)

# Two count corrections and one undone mistake.
post("ADJ", TODAY - timedelta(days=6), [line("LENS", "Vizag Office", -2)], reason="Damaged",
     note="2 lenses cracked in storage", by="Admin")
post("ADJ", TODAY - timedelta(days=4), [line("CABLE TIE 200MM", "Vizag Office", 1)], reason="Physical count",
     note="Found 1 extra pack during count", by="Admin")
wrong = post("OUT", TODAY - timedelta(days=2), [line("EIO9326", "Vizag Office", -3)], subtype="SITE",
             party="Dr Reddys, Vizag", ref="Job 512")
post("REV", TODAY - timedelta(days=2), [dict(ln, qty=-ln["qty"]) for ln in wrong["lines"]],
     reverses=wrong["no"], note="Entered against the wrong job", by="Admin")

data = {"today": TODAY.isoformat(), "locations": LOCATIONS, "spareTypes": SPARE_TYPES,
        "fittingTypes": FITTING_TYPES, "units": UNITS, "companies": COMPANIES, "technicians": TECHNICIANS,
        "customers": CUSTOMERS, "items": items, "entries": entries}
out = Path(__file__).with_name("demo-data.json")
out.write_text(json.dumps(data, indent=1), encoding="utf-8")
print(f"{len(items)} items, {len(entries)} entries -> {out.name}")
