"""Phase 2: replay the scenario timeline against a running server, through the app's real forms.

    uv run --with requests python -I e2e/rigour/load_entries.py http://127.0.0.1:8001 admin <password>

Run against an EMPTY database (migrate + seed_users only). Writes e2e/rigour/results.json: one row per
operation (ok / refused, the number it produced, the time it took), the id maps, and the stock the settles
added. A valid operation the app refuses is recorded as `unexpected_refusal` and the run goes on, so one
problem does not hide the next. Dependents of a failed complaint are skipped and counted.
"""

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from client import Client, options, text_of

HERE = Path(__file__).resolve().parent
BASE, USER, PASSWORD = sys.argv[1], sys.argv[2], sys.argv[3]
scen = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))
c = Client(BASE)
assert c.login(USER, PASSWORD), "login failed"

log, ids = [], {"loc": {}, "company": {}, "spare": {}, "item": {}, "site": {}, "tech": {}, "cmp": {}}
settle_effects = []  # (item code, location name, +qty) for pieces that came back as good stock
stats = {"ok": 0, "refused": 0, "skipped": 0}


def record(i, op, ok, ref="", msg="", ms=0.0, unexpected=False):
    stats["ok" if ok else "skipped" if msg.startswith("skipped") else "refused"] += 1
    log.append(
        {
            "i": i,
            "op": op["op"],
            "date": op.get("date", ""),
            "ok": ok,
            "ref": ref,
            "msg": msg,
            "ms": round(ms, 1),
            "unexpected_refusal": unexpected and not ok,
        }
    )
    if not ok:
        print(f"  ! #{i} {op['op']} {op.get('code') or op.get('key') or op.get('cmp') or ''}: {msg}")


def refresh_maps():
    page = c.get("/stock/in/").text
    ids["loc"] = options(page, "id_location")
    ids["company"] = options(page, "id_company")
    item_form = c.get("/items/new/").text
    ids["spare"] = options(item_form, "id_spare_type")
    ids["company"] = {**ids["company"], **options(item_form, "id_company")}
    ids["tech"] = options(c.get("/complaints/new/").text, "id_technicians")


def lines_for(kind, op):
    out = []
    for row in op["lines"]:
        code, qty = row[0], row[1]
        item = [("line_item", str(ids["item"][code])), ("line_qty", str(qty))]
        batch = row[2] if kind in ("in", "mark") and len(row) > 2 else ""
        pkd = row[3] if kind in ("in", "mark") and len(row) > 3 else ""
        fault = row[4] if kind == "mark" and len(row) > 4 else ""
        expected = str(row[2]) if kind == "adj" else ""
        out += item + [
            ("line_batch", batch),
            ("line_pkd", pkd),
            ("line_expected", expected),
            ("line_fault", fault),
        ]
    return out


def number_from(location):
    found = re.search(r"/(?:entries|complaints|defectives/batches)/([A-Z]+-\d+)/", location)
    return found.group(1) if found else location


def run_op(i, op):
    kind = op["op"]
    t0 = time.perf_counter()

    def done(result, ref="", ok=None):
        ok = result.saved if ok is None else ok
        record(
            i,
            op,
            ok,
            ref=ref if ok else "",
            msg="saved" if ok else result.message(),
            ms=(time.perf_counter() - t0) * 1000,
            unexpected=True,
        )
        return result

    if kind == "item":
        data = {
            "code": op["code"],
            "spare_type": ids["spare"][op["spare"]],
            "company": ids["company"][op["company"]],
            "description": "",
            "cat_ref": "",
            "fitting_type": "",
            "wattage_w": "",
            "current_ma": "",
            "unit": "NOS",
            "reorder_level": op["reorder"],
            "aliases": "",
            "is_active": "on",
        }
        r = c.post("/items/new/", data, token=False)
        if r.saved:
            ids["item"][op["code"]] = int(re.search(r"/items/(\d+)/", r.location).group(1))
        else:
            # The Excel really contains near-duplicates (EI08437 / EIO8437, ...-300 / ...-0300). The app's
            # look-alike guard refuses them and names the existing item; a user would use that one.
            twin = re.search(r"looks the same as (\S+?)\. Use that item", r.message())
            if twin and twin.group(1) in {code for code in ids["item"]}:
                ids["item"][op["code"]] = ids["item"][twin.group(1)]
                ids.setdefault("alias", {})[op["code"]] = twin.group(1)
                return record(
                    i,
                    op,
                    True,
                    ref=op["code"],
                    msg=f"look-alike of {twin.group(1)}: guard worked, existing item used",
                    ms=(time.perf_counter() - t0) * 1000,
                )
        done(r, ref=op["code"])
    elif kind == "site":
        r = c.post_json(
            "/sites/quick-create/",
            {
                "ns-name": op["name"],
                "ns-city": op["city"],
                "ns-contact_name": op["contact"],
                "ns-phone": op["phone"],
                "ns-address": "",
            },
            "/complaints/new/",
        )
        body = r.json()
        if body.get("ok"):
            ids["site"][op["name"]] = body["site"]["id"]
        record(
            i,
            op,
            body.get("ok", False),
            ref=op["name"],
            msg="saved" if body.get("ok") else body.get("error", "?"),
            ms=(time.perf_counter() - t0) * 1000,
            unexpected=True,
        )
    elif kind == "tech":
        r = c.post("/technicians/", {"name": op["name"], "phone": op["phone"]})
        done(r, ref=op["name"])
    elif kind in ("in", "out", "trf", "adj", "mark"):
        path = {
            "in": "/stock/in/",
            "out": "/stock/out/",
            "trf": "/stock/transfer/",
            "adj": "/stock/adjust/",
            "mark": "/defectives/mark/",
        }[kind]
        data = [("entry_date", op["date"]), ("location", ids["loc"][op["loc"]]), ("note", op.get("note", ""))]
        if kind == "in":
            data += [
                ("subtype", op["subtype"]),
                ("company", ids["company"].get(op.get("company", ""), "")),
                ("party", op.get("party", "")),
                ("ref", op.get("ref", "")),
            ]
        elif kind == "out":
            data += [("subtype", op["subtype"]), ("party", op["party"]), ("ref", op.get("ref", ""))]
        elif kind == "trf":
            data += [("to_location", ids["loc"][op["to"]])]
        elif kind == "adj":
            data += [("reason", op["reason"])]
        elif kind == "mark":
            data = [d for d in data if d[0] != "note"]
        r = c.post(path, data + lines_for(kind, op))
        done(r, ref=number_from(r.location) if r.saved else "")
    elif kind == "cmp":
        if op["site"] not in ids["site"]:
            return record(i, op, False, msg="skipped: site was not created")
        techs = [("technicians", ids["tech"][t]) for t in op["techs"]]
        data = [
            ("site", ids["site"][op["site"]]),
            ("contact_name", ""),
            ("phone", ""),
            ("company", ids["company"][op["company"]]),
            ("company_ref", op["company_ref"]),
            ("reported_on", op["date"]),
            ("qty_affected", op["qty"] or ""),
            ("fault", op["fault"]),
            ("priority", op["priority"]),
        ] + techs
        r = c.post("/complaints/new/", data)
        if r.saved:
            ids["cmp"][op["key"]] = number_from(r.location)
        done(r, ref=ids["cmp"].get(op["key"], ""))
    elif kind in ("visit", "status", "notcovered"):
        number = ids["cmp"].get(op["cmp"])
        if not number:
            return record(i, op, False, msg="skipped: complaint was not filed")
        if kind == "visit":
            data = [
                ("visit_date", op["date"]),
                ("work_done", op["work"]),
                ("location", ids["loc"][op["loc"]]),
                ("next_status", op["next"]),
            ] + [("technicians", ids["tech"][t]) for t in op["techs"]]
            for code, qty in op["parts"]:
                data += [("part_item", str(ids["item"][code])), ("part_qty", str(qty))]
            for code, qty, batch, pkd, fault in op["collected"]:
                data += [
                    ("col_item", str(ids["item"][code])),
                    ("col_qty", str(qty)),
                    ("col_batch", batch),
                    ("col_pkd", pkd),
                    ("col_fault", fault),
                ]
            r = c.post(f"/complaints/{number}/visit/", data)
            done(r, ref=number)
        elif kind == "status":
            r = c.post(
                f"/complaints/{number}/status/",
                {"to": op["to"], "note": ""},
                page_path=f"/complaints/{number}/",
            )
            done(r, ref=number, ok=r.saved)
        else:
            r = c.post(
                f"/complaints/{number}/not-covered/",
                {"reason": op["reason"], "note": op.get("note", "")},
                page_path=f"/complaints/{number}/",
            )
            done(r, ref=number, ok=r.saved)
    elif kind == "batch":
        run_batch(i, op, t0)
    else:
        raise SystemExit(f"unknown op {kind}")


def run_batch(i, op, t0):
    cid = ids["company"][op["company"]]
    page = c.get(f"/defectives/batches/new/?company={cid}").text
    rows = re.findall(r'name="tag" value="(DEF-\d+)".*?<span class="code">([^<]+)</span>', page, re.S)
    chosen = rows[: op["n"]]
    if not chosen:
        return record(i, op, False, msg="skipped: no pieces in store for this company")
    r = c.post(
        "/defectives/batches/new/",
        [("company", cid), ("note", f"Rigour batch {op['key']}")] + [("tag", t) for t, _ in chosen],
    )
    if not r.saved:
        return record(i, op, False, msg=r.message(), ms=(time.perf_counter() - t0) * 1000, unexpected=True)
    rb = number_from(r.location)
    item_of = {t: text_of(code) for t, code in chosen}
    problems = []
    d = c.post(
        f"/defectives/batches/{rb}/dispatch/",
        {"dispatched_on": op["dispatch"], "courier": op["courier"], "docket_no": op["docket"]},
        page_path=f"/defectives/batches/{rb}/",
    )
    if not d.saved:
        problems.append(f"dispatch: {d.message()}")
    tags = [t for t, _ in chosen]
    start = 0
    for outcome, share, loc in op["settle"] if not problems else []:
        count = max(1, round(share * len(tags)))
        group = tags[start : start + count]
        start += count
        if not group:
            continue
        when = date.fromisoformat(op["dispatch"])
        s = c.post(
            f"/defectives/batches/{rb}/settle/",
            [("outcome", outcome), ("settled_on", when.isoformat()), ("to_location", ids["loc"].get(loc, ""))]
            + [("tag", t) for t in group],
            page_path=f"/defectives/batches/{rb}/",
        )
        if not s.saved:
            problems.append(f"settle {outcome}: {s.message()}")
        elif outcome in ("REPLACED", "REPAIRED"):
            settle_effects.extend([item_of[t], loc, 1] for t in group)
    record(
        i,
        op,
        not problems,
        ref=rb,
        msg="; ".join(problems) or f"{rb}: {len(tags)} pieces",
        ms=(time.perf_counter() - t0) * 1000,
        unexpected=True,
    )


refresh_maps()
masters = [m for m in scen["masters"] if m["op"] == "item"]
sites = [dict(x, op="site") for x in scen["sites"]]
techs = [m for m in scen["masters"] if m["op"] == "tech"]
ops = masters + techs + sites + scen["timeline"]
started = time.time()
for n, op in enumerate(ops, start=1):
    run_op(n, op)
    if op["op"] == "tech" and op is techs[-1]:
        refresh_maps()  # the technician picker now has them
print(f"\n{len(ops)} operations in {time.time() - started:.0f}s: {stats}")
(HERE / "results.json").write_text(
    json.dumps(
        {
            "stats": stats,
            "log": log,
            "ids": ids,
            "settle_effects": settle_effects,
            "requests": c.requests_made,
        },
        indent=1,
    ),
    encoding="utf-8",
)
sys.exit(0 if not stats["refused"] else 1)
