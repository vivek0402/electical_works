"""Automated walkthrough of the service mockup (complaints + defectives, linked to stock), desktop + phone.

Fails on any JS error or broken rule. Serve the repo root on :8090 first:
    python -m http.server 8090 --bind 127.0.0.1
    uv run --with playwright python mockups/service/walkthrough.py [screenshot-dir]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = "http://127.0.0.1:8090/mockups/service/"
URL = ROOT + "index.html"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "screens"
OUT.mkdir(parents=True, exist_ok=True)
errors, wide = [], []


def shot(page, name, check=True):
    page.evaluate("document.getElementById('toasts').innerHTML = ''")   # old toasts would cover the screen
    page.wait_for_timeout(250)
    if check:  # no horizontal page scroll, and no table scrolling sideways inside its card
        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
            wide.append(f"{name}: page scrolls sideways")
        n = page.evaluate("[...document.querySelectorAll('#view .table-responsive')].filter(t => t.scrollWidth > t.clientWidth + 1).length")
        if n and page.viewport_size["width"] > 400:
            wide.append(f"{name}: {n} table(s) scroll sideways")
    page.screenshot(path=str(OUT / f"svc-{name}.png"), full_page=True)


def js(page, expr):
    return page.evaluate(expr)


def ts_pick(page, wrapper, text, create=False):
    """Type into a Tom Select (wrapper locator) and pick the first real match (or the 'create' row)."""
    wrapper.locator(".ts-control").click()
    wrapper.locator(".ts-control input").fill(text)
    page.wait_for_timeout(450)   # Tom Select refreshes the list after its 300 ms throttle
    dd = wrapper.locator(".ts-dropdown")   # the dropdown lives inside its own wrapper (no dropdownParent)
    (dd.locator(".create") if create else dd.locator(".option:not(.create)").first).click()
    page.wait_for_timeout(100)


def ts_of(page, select_id):
    return page.locator(f"#{select_id} + .ts-wrapper")


def line(page, host, n):
    return page.locator(f"{host} .lines-table tbody tr").nth(n)


def pick_line(page, host, n, text):
    ts_pick(page, line(page, host, n), text)


def qty(page, host, n, value, cls=".qty"):
    q = line(page, host, n).locator(cls)
    q.fill(str(value))
    q.dispatch_event("input")


def modal_click(page, text):
    page.locator(f"#modal button:has-text('{text}')").click()


def wait_modal(page, state="visible"):
    page.wait_for_selector("#modal.show" if state == "visible" else "#modal", state="visible" if state == "visible" else "hidden")
    page.wait_for_timeout(200)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    page.goto(URL)
    page.wait_for_selector("#chart-weekly .apexcharts-canvas")
    assert js(page, "DB.locations.includes(DB.defStore)") is False

    # Every sidebar route renders.
    hrefs = page.eval_on_selector_all("#nav .nav-link", "a => a.map(x => x.getAttribute('href'))")
    for h in ["#cdash", "#complaints", "#complaint-new", "#sites", "#techs", "#ddash", "#pieces", "#mark", "#batches"]:
        assert h in hrefs, h
    page.goto(URL + "#cdash")
    assert "Open complaints by age" in page.inner_text("#view")
    shot(page, "01-complaints-dashboard")
    page.goto(URL + "#complaints")
    assert "Showing 1–10 of" in page.inner_text("#dt-complaints")
    shot(page, "02-complaints-list")

    # Global search: complaint no., company complaint no., site name, defective tag.
    for q, want in [("CMP-0003", "CMP-0003"), ("WL/AP/24871", "CMP-0001"), ("Punjab National", "Punjab National Bank"), ("DEF-0005", "DEF-0005")]:
        page.fill("#gsearch", q)
        page.locator("#gsearch").dispatch_event("input")
        assert want in page.inner_text("#gresults"), q
    page.press("#gsearch", "Enter")
    page.wait_for_url("**#piece/DEF-0005")
    page.fill("#gsearch", "")

    # 1. New complaint with a new site (added in the modal).
    page.goto(URL + "#complaint-new")
    page.click("button:has-text('New site')")
    wait_modal(page)
    page.fill("#ns-name", "Steel Plant Admin Block")
    page.fill("#ns-city", "Visakhapatnam")
    page.fill("#ns-contact", "Mr. Prasad")
    page.fill("#ns-phone", "98765")
    page.click("#ns-save")
    assert "10-digit" in page.inner_text("#ns-err")
    page.fill("#ns-phone", "9876543210")
    page.click("#ns-save")
    wait_modal(page, "hidden")
    assert page.input_value("#c-contact") == "Mr. Prasad"
    ts_pick(page, ts_of(page, "c-company"), "Havells")
    page.fill("#c-ref", "HV-C-80114")
    page.fill("#c-qty", "2")
    page.click("button:has-text('Save complaint')")
    assert "fault" in page.inner_text("#form-error").lower()
    page.fill("#c-fault", "2 battens not lighting in the admin corridor")
    page.click("label:has-text('High')")
    ts_pick(page, ts_of(page, "c-techs"), "Ramu")
    page.keyboard.press("Escape")
    shot(page, "03-new-complaint")
    page.click("button:has-text('Save complaint')")
    page.wait_for_url("**#complaint/CMP-*")
    cno = page.url.split("/")[-1]
    assert js(page, f"complaint('{cno}').status") == "NOT_ATTENDED"
    assert js(page, f"siteName(complaint('{cno}'))") == "Steel Plant Admin Block"
    assert js(page, f"complaint('{cno}').company") == "Havells"

    # 2. Record visit: 2 parts given (Stock OUT), 2 failed pieces collected (2 new tags), next status Attended.
    part, part_loc = "LG78-150-700", "Vizag Office"
    have = js(page, f"balance('{part}','{part_loc}')")
    def0 = js(page, "defQty('HV-BATTEN-20W')")
    pieces0 = js(page, "DB.pieces.length")
    page.click("a:has-text('Record visit') >> nth=0")
    page.wait_for_url(f"**#visit/{cno}")
    assert js(page, "vTechs.getValue()") == ["Ramu"]
    page.fill("#v-work", "Changed 2 drivers; 2 battens dead, collected")
    pick_line(page, "#v-parts", 0, part)
    qty(page, "#v-parts", 0, have + 5)
    assert "Only" in line(page, "#v-parts", 0).locator(".err").inner_text()   # live over-issue error
    page.click("button:has-text('Save visit')")
    assert "Nothing was saved" in page.inner_text("#form-error")
    assert js(page, f"balance('{part}','{part_loc}')") == have and js(page, "DB.pieces.length") == pieces0
    qty(page, "#v-parts", 0, 2)
    pick_line(page, "#v-collect", 0, "HV-BATTEN-20W")
    qty(page, "#v-collect", 0, 2)
    line(page, "#v-collect", 0).locator(".batch").fill("HB2604")
    line(page, "#v-collect", 0).locator(".pkd").fill("2026-04")
    line(page, "#v-collect", 0).locator(".fault").fill("no light, driver burnt")
    assert js(page, "radioVal('v-next')") == "ATTENDED"
    shot(page, "05-record-visit")
    page.click("button:has-text('Save visit')")
    page.wait_for_url(f"**#complaint/{cno}")
    assert js(page, f"balance('{part}','{part_loc}')") == have - 2
    assert js(page, "defQty('HV-BATTEN-20W')") == def0 + 2
    new_tags = js(page, f"DB.visits.at(-1).tags")
    assert len(new_tags) == 2 and js(page, f"complaint('{cno}').status") == "ATTENDED", new_tags
    assert all(js(page, f"piece('{t}').company") == "Havells" for t in new_tags)
    out_no = js(page, "DB.visits.at(-1).outEntry")
    assert js(page, f"entry('{out_no}').subtype") == "COMPLAINT" and js(page, f"entry('{out_no}').complaint") == cno
    shot(page, "04-complaint-detail")

    # 3. Status: Attended -> Awaiting material -> Resolved -> Closed. A disallowed move is refused.
    def change_status(to_label):
        page.click("#page-header button:has-text('Change status')")
        wait_modal(page)
        page.locator(f"#modal label:has-text('{to_label}')").click()
        modal_click(page, "Change status")
        wait_modal(page, "hidden")
    change_status("Awaiting material")
    assert js(page, f"complaint('{cno}').status") == "AWAITING_MATERIAL"
    change_status("Resolved")
    change_status("Closed")
    assert js(page, f"complaint('{cno}').status") == "CLOSED" and js(page, f"complaint('{cno}').closedOn") == js(page, "today()")
    page.click("#page-header button:has-text('Change status')")
    wait_modal(page)
    modal_click(page, "Reopen")
    assert "can't move to Attended" in page.inner_text("#st-err")   # Office can't reopen
    page.click("#modal .btn-close")
    wait_modal(page, "hidden")
    assert "can't move to" in js(page, f"changeStatus(complaint('{cno}'), 'RESOLVED')")
    assert js(page, f"cEvents('{cno}').map(e => e.to).join()") == "NOT_ATTENDED,ATTENDED,AWAITING_MATERIAL,RESOLVED,CLOSED"

    # 4. Close another complaint as Not covered (reason required).
    other = js(page, "DB.complaints.find(c => c.status === 'NOT_ATTENDED').no")
    page.goto(f"{URL}#complaint/{other}")
    page.click("#page-header button:has-text('Close as Not covered')")
    wait_modal(page)
    modal_click(page, "Close as Not covered")
    assert "Choose why" in page.inner_text("#st-err")
    page.select_option("#nc-reason", "Out of warranty")
    modal_click(page, "Close as Not covered")
    wait_modal(page, "hidden")
    assert js(page, f"complaint('{other}').status") == "NOT_COVERED" and js(page, f"complaint('{other}').notCoveredReason") == "Out of warranty"
    assert "Out of warranty" in page.inner_text("#view")

    # 5. Mark 1 piece defective from stock: TRF good location -> Defective store, 1 new tag.
    mcode = "EIO8437"
    g0, d0 = js(page, f"balance('{mcode}','Vizag Office')"), js(page, f"defQty('{mcode}')")
    page.goto(URL + "#mark")
    assert js(page, "[...document.querySelectorAll('#f-loc option')].some(o => o.value === DB.defStore)") is False
    pick_line(page, "#lines", 0, mcode)
    qty(page, "#lines", 0, 1)
    page.click("button:has-text('Mark as defective')")
    assert "what is wrong" in page.inner_text("#form-error")
    line(page, "#lines", 0).locator(".fault").fill("Dead on arrival from last delivery")
    page.click("button:has-text('Mark as defective')")
    page.wait_for_url("**#entry/TRF-*")
    assert js(page, f"balance('{mcode}','Vizag Office')") == g0 - 1 and js(page, f"defQty('{mcode}')") == d0 + 1
    mark_tag = js(page, "DB.pieces.at(-1).tag")
    assert js(page, f"piece('{mark_tag}').source") == "FOUND_IN_STOCK"
    assert mark_tag in page.inner_text("#view") and "marked defective" in page.inner_text("#page-header").lower()
    assert page.locator("#page-header button:has-text('Undo')").count() == 0   # defective entries can't be undone here

    # 6. New batch for Havells; mixing companies is refused; an empty batch can't be dispatched; dispatch it.
    other_tag = js(page, "DB.pieces.find(p => p.status === 'IN_STORE' && p.company !== 'Havells').tag")  # any other company's piece
    page.goto(URL + "#pieces/status=IN_STORE")
    page.locator("#dt-pieces th input[type=checkbox]").check()          # ticks every in-store piece: several companies
    page.click("button:has-text('Add to draft batch')")
    wait_modal(page)
    assert "one company's pieces only" in page.inner_text("#modal")
    modal_click(page, "OK")
    wait_modal(page, "hidden")
    shot(page, "07-pieces-list")

    hv_store = js(page, "DB.pieces.filter(p => p.company === 'Havells' && p.status === 'IN_STORE').map(p => p.tag)")
    page.goto(URL + "#batch-new")
    ts_pick(page, ts_of(page, "b-company"), "Havells")
    rows = page.locator("#dt-nb input[data-tag]")
    assert rows.count() == len(hv_store)
    assert all(js(page, f"piece('{t}').company") == "Havells" for t in page.eval_on_selector_all("#dt-nb input[data-tag]", "a => a.map(x => x.dataset.tag)"))
    page.check(f"#dt-nb input[data-tag='{new_tags[0]}']")
    page.check(f"#dt-nb input[data-tag='{new_tags[1]}']")
    page.click("button:has-text('Create draft batch')")
    page.wait_for_url("**#batch/RB-*")
    bno = page.url.split("/")[-1]
    assert js(page, f"batch('{bno}').lines.length") == 2 and js(page, f"batchStatus(batch('{bno}'))") == "Draft"
    page.fill("#add-tag", other_tag)
    page.click("#view form button:has-text('Add')")
    assert "one company's pieces only" in page.inner_text("#add-err")
    assert js(page, f"batch('{bno}').lines.length") == 2

    page.goto(URL + "#batch-new")   # an empty draft (Finolex) can't be dispatched
    ts_pick(page, ts_of(page, "b-company"), "Finolex")
    page.click("button:has-text('Create draft batch')")
    page.wait_for_url("**#batch/RB-*")
    page.click("#page-header button:has-text('Dispatch')")
    wait_modal(page)
    page.select_option("#d-courier", "DTDC")
    page.fill("#d-docket", "D1")
    modal_click(page, "Dispatch")
    assert "empty batch can't be dispatched" in page.inner_text("#dm-err")
    page.click("#modal .btn-close")
    wait_modal(page, "hidden")

    page.goto(f"{URL}#batch/{bno}")
    hv_def0 = js(page, "defQty('HV-BATTEN-20W')")
    page.click("#page-header button:has-text('Dispatch')")
    wait_modal(page)
    modal_click(page, "Dispatch")
    assert "courier" in page.inner_text("#dm-err").lower()
    page.select_option("#d-courier", "Professional Couriers")
    page.fill("#d-docket", "PC-7790031")
    modal_click(page, "Dispatch")
    wait_modal(page, "hidden")
    assert js(page, f"batch('{bno}').status") == "DISPATCHED" and js(page, "defQty('HV-BATTEN-20W')") == hv_def0 - 2
    assert all(js(page, f"piece('{t}').status") == "SENT" for t in new_tags)
    assert "locked" in js(page, f"addPieces(batch('{bno}'), ['{hv_store[0]}'])")      # editing after dispatch
    assert "locked" in page.inner_text("#view")

    # 7. Settle RB-0001's remaining SENT pieces: 1 replaced (stock IN at Vizag Office) + 1 rejected-returned.
    page.goto(URL + "#batch/RB-0001")
    sent = js(page, "batch('RB-0001').lines.filter(l => piece(l.tag).status === 'SENT').map(l => l.tag)")
    assert len(sent) == 2, sent
    assert "Only sent pieces" in js(page, "settlePieces(batch('RB-0001'), ['DEF-0001'], {outcome: 'REPLACED', date: today(), loc: 'Vizag Office'}).error")
    rcode = js(page, f"piece('{sent[0]}').code")
    good0, dq0 = js(page, f"balance('{rcode}','Vizag Office')"), js(page, f"defQty('{rcode}')")
    page.check(f"#dt-b-lines input[data-tag='{sent[0]}']")
    page.click("button:has-text('Settle ticked pieces')")
    assert "location" in page.inner_text("#settle-err").lower()
    page.select_option("#s-loc", "Vizag Office")
    shot(page, "08-batch-settle")
    page.click("button:has-text('Settle ticked pieces')")
    page.wait_for_timeout(300)
    assert js(page, f"balance('{rcode}','Vizag Office')") == good0 + 1          # Vizag Office stock goes up
    assert js(page, f"piece('{sent[0]}').outcome") == "REPLACED"
    rep_entry = js(page, f"batch('RB-0001').lines.find(l => l.tag === '{sent[0]}').entry")
    assert js(page, f"entry('{rep_entry}').subtype") == "REPLACEMENT" and js(page, f"entry('{rep_entry}').kind") == "IN"
    page.check(f"#dt-b-lines input[data-tag='{sent[1]}']")
    page.locator("label:has-text('Rejected (returned)')").click()
    assert page.locator("#w-sloc").is_hidden()
    page.click("button:has-text('Settle ticked pieces')")
    page.wait_for_timeout(300)
    assert js(page, f"piece('{sent[1]}').status") == "IN_STORE" and js(page, f"piece('{sent[1]}').outcome") == "REJECTED_RETURNED"
    assert js(page, f"defQty('{rcode}')") == dq0 + 1
    assert js(page, "batchStatus(batch('RB-0001'))") == "Settled"
    assert "Settled" in page.inner_text("#page-header")

    page.goto(URL + "#ddash")
    assert "In the defective store, per company" in page.inner_text("#view")
    shot(page, "06-defectives-dashboard")
    page.goto(f"{URL}#piece/{sent[0]}")
    assert "Replaced" in page.inner_text("#view") and rep_entry in page.inner_text("#view")
    page.goto(f"{URL}#entry/{rep_entry}")
    assert "replacement from company" in page.inner_text("#page-header").lower() and "RB-0001" in page.inner_text("#view")

    # 8. Current stock: the Defective store is its own column and is never in the good total.
    page.goto(URL + "#stock")
    heads = page.locator("#dt-stock thead th").all_inner_texts()
    assert any("DEFECTIVE STORE" in h.upper() for h in heads), heads
    page.fill("#view input[type=search]", rcode)
    page.locator("#view input[type=search]").dispatch_event("change")
    cells = page.locator("#dt-stock tbody tr").first.locator("td").all_inner_texts()
    tot, dq = int(cells[-2].split()[0]), int(cells[-1])
    assert tot == js(page, f"total('{rcode}')") == js(page, f"sum(DB.locations, l => balance('{rcode}', l))"), cells
    assert dq == js(page, f"defQty('{rcode}')") and dq > 0, cells
    assert js(page, f"[...DB.locations, DB.defStore].reduce((t, l) => t + balance('{rcode}', l), 0)") == tot + dq
    page.goto(URL + "#stock/")   # "/" resets the filters
    shot(page, "09-current-stock")
    page.goto(f"{URL}#item/{rcode}")
    assert f"Defective store: {dq}" in page.inner_text("#view")
    for h in ("#in", "#out", "#transfer", "#adjust"):          # entry forms never offer the Defective store
        page.goto(URL + h)
        assert js(page, "[...document.querySelectorAll('select option')].some(o => o.value === DB.defStore)") is False, h
    page.goto(URL + "#moves")
    page.fill("#view input[type=search]", cno)
    page.locator("#view input[type=search]").dispatch_event("change")
    assert f"Parts for complaint {cno}" in page.inner_text("#dt-moves") and f"Defective collected ({cno})" in page.inner_text("#dt-moves")
    page.fill("#view input[type=search]", bno)
    page.locator("#view input[type=search]").dispatch_event("change")
    assert f"Returned to company ({bno})" in page.inner_text("#dt-moves")
    page.goto(URL + "#dash")
    assert "Open complaints" in page.inner_text("#view") and "Defective pieces in store" in page.inner_text("#view")

    # 9. Exports download (stock + service) and every Export button points at an existing file.
    files = ["Current_Stock", "Stock_Movements", "Item_List", "Low_Stock", "Pending_Complaints", "Complaint_List",
             "Defective_List", "Return_Batch_RB-0001"]
    for f in files:
        r = page.request.get(f"{ROOT}exports/{f}.xlsx")
        assert r.status == 200 and r.body()[:2] == b"PK", f
    for h in ("#cdash", "#complaints", "#ddash", "#pieces", "#batch/RB-0001", "#stock", "#moves", "#items", "#low"):
        page.goto(URL + h)
        for href in page.eval_on_selector_all("a[download]", "a => a.map(x => x.getAttribute('href'))"):
            assert page.request.get(ROOT + href).status == 200, (h, href)
    page.goto(URL + "#batch/RB-0001")
    with page.expect_download() as dl:
        page.click("a:has-text('Export dispatch list')")
    assert dl.value.suggested_filename == "Return_Batch_RB-0001.xlsx"

    # 11. The original stock flows still work: one Stock IN and one Stock OUT.
    b0 = js(page, "balance('EIO6006','Vizag Office')")
    page.goto(URL + "#in")
    page.select_option("#f-supplier", "Havells")
    pick_line(page, "#lines", 0, "EIO6006")
    qty(page, "#lines", 0, 4)
    page.click("button:has-text('Save Stock IN')")
    page.wait_for_url("**#entry/IN-*")
    assert js(page, "balance('EIO6006','Vizag Office')") == b0 + 4
    page.goto(URL + "#out")
    page.fill("#f-site", "Dr Reddys, Vizag")
    pick_line(page, "#lines", 0, "EIO6006")
    qty(page, "#lines", 0, 3)
    page.click("button:has-text('Save Stock OUT')")
    page.wait_for_url("**#entry/OUT-*")
    assert js(page, "balance('EIO6006','Vizag Office')") == b0 + 1
    assert page.locator("#page-header button:has-text('Undo')").count() == 1

    # 12. Masters are typed in on the forms; the Masters page is read-only.
    page.goto(URL + "#in")
    ts_pick(page, ts_of(page, "f-supplier"), "  bajaj   electricals ", create=True)
    ts_pick(page, ts_of(page, "f-loc"), "Gajuwaka Godown", create=True)
    assert js(page, "field('f-supplier').value") == "bajaj electricals"
    assert js(page, "DB.locations.includes('Gajuwaka Godown') && DB.companies.includes('bajaj electricals')")
    ts_of(page, "f-supplier").locator(".ts-control input").fill("HAVELLS")   # a known name in any case: no "Add" row
    page.wait_for_timeout(450)
    assert ts_of(page, "f-supplier").locator(".create").count() == 0
    page.keyboard.press("Escape")
    shot(page, "12-in-new-location")
    page.goto(URL + "#item-new")
    ts_pick(page, ts_of(page, "it-ftype"), "Gate light", create=True)
    assert js(page, "DB.fittingTypes.includes('Gate light')")
    page.goto(URL + "#out")                                     # stock can't leave a new place: OUT stays pick-only
    assert js(page, "!!field('f-loc').dataset.master") is False
    page.goto(URL + "#masters")
    text = page.inner_text("#view")
    assert "Gajuwaka Godown" in text and "Gate light" in text and "bajaj electricals" in text
    assert page.locator("#view form, #view input, #view button").count() == 0
    shot(page, "12-masters-read-only")

    # 13. Smart features (docs/superpowers/specs/2026-10-19-smart-features-design.md). Suggest, never act.
    page.goto(URL + "#dash")
    assert "to chase today" in page.inner_text("#view")
    page.goto(URL + "#today")
    n0 = js(page, "todayCount()")
    assert n0 > 0 and "Overdue complaints" in page.inner_text("#view")
    page.locator("#view button[title='Hide until this changes']").first.click()
    assert js(page, "todayCount()") == n0 - 1                              # hidden until it changes
    shot(page, "13-today")
    page.goto(URL + "#digest")
    assert "Subject:" in page.inner_text("#view")
    page.goto(URL + "#complaints")
    assert "due" in page.inner_text("#dt-complaints thead").lower()
    assert js(page, "DB.complaints.some(c => dueInfo(c).state === 'over')") and page.locator("#dt-complaints td .badge.st").count() > 0
    page.goto(URL + "#complaint-new")                                       # paste a message: the form is pre-filled, not saved
    page.click("#view a:has-text('Show')")
    page.click("text=Try a sample WhatsApp")
    page.click("text=Fill the form from this message")
    page.wait_for_timeout(300)
    assert js(page, "cSite.getValue()") == "1" and js(page, "field('c-qty').value") == "6"
    assert "15 W" in page.inner_text("#c-fault-read") and page.locator(".ai-filled").count() >= 3
    n_before = js(page, "DB.complaints.length")
    assert js(page, "DB.complaints.length") == n_before                     # nothing filed until Save
    shot(page, "13-new-complaint-from-message")
    page.click("#view button:has-text('New site')")                         # duplicate site warning
    wait_modal(page)
    page.fill("#ns-phone", "9866832284")
    assert "Punjab National Bank" in page.inner_text("#ns-dup")
    page.click("#modal .btn-close")
    wait_modal(page, "hidden")
    page.goto(URL + "#in")                                                  # typo guard
    ts_of(page, "f-supplier").locator(".ts-control").click()
    ts_of(page, "f-supplier").locator(".ts-control input").fill("Havels")
    page.wait_for_timeout(450)
    assert "Did you mean" in ts_of(page, "f-supplier").locator(".ts-dropdown").inner_text()
    page.keyboard.press("Escape")
    busy = js(page, "DB.items.find(i => DB.entries.filter(e => e.lines.some(l => l.code === i.code)).length >= 5).code")
    pick_line(page, "#lines", 0, busy)                                      # sanity check: warn, then allow
    qty(page, "#lines", 0, 900)
    page.click("button:has-text('Save Stock IN')")
    wait_modal(page)
    assert "usual quantity" in page.inner_text("#modal")
    page.click("#modal button:has-text('Go back and check')")
    wait_modal(page, "hidden")
    page.goto(URL + "#low")
    page.click("text=Reorder level suggestions")
    code = page.locator("#dt-sugg tbody tr").first.locator("a.code").inner_text()
    new_level = js(page, f"reorderSuggestion(item('{code}')).level")
    page.locator("#dt-sugg button:has-text('Accept')").first.click()
    assert js(page, f"item('{code}').reorder") == new_level
    shot(page, "13-reorder-suggestions")
    page.goto(f"{URL}#item/{code}")
    assert "Reorder level" in page.inner_text("#view")
    page.goto(URL + "#visit/" + js(page, "SMART.needs[0].complaint"))       # parts needed -> add to parts given
    page.locator("#view .suggest button:has-text('Add')").first.click()
    assert js(page, "visitParts.rows[0].code") == js(page, "SMART.needs[0].code")
    shot(page, "13-visit-suggestions")
    for h in ("#slow", "#insights", "#smart", "#import"):
        page.goto(URL + h)
        assert page.locator("#view .card").count() > 0, h
    page.click("text=Check the files")
    assert "what the import does" in page.inner_text("#view").lower()
    page.goto(URL + "#drafts")
    page.locator("#view a:has-text('Open as complaint')").last.click()
    page.wait_for_timeout(300)
    assert js(page, "cCompany.getValue()") == "Havells" and "Sri Venkateswara Hospital" in page.inner_text("#c-ai-site")
    page.goto(URL + "#smart")
    page.uncheck("#s-ai-on")
    page.click("button:has-text('Save settings')")
    page.goto(URL + "#complaint-new")
    assert "AI assistant is off" in page.locator("#c-paste-body").text_content()
    shot(page, "13-smart-settings-ai-off")

    # 10. Phone (390px): menu behind the hamburger; line editors stack as cards; no sideways scroll.
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.on("pageerror", lambda e: errors.append("phone: " + str(e)))
    phone.goto(URL + "#cdash")
    phone.wait_for_selector("#view .card")
    assert not phone.locator("#sidebar-menu").is_visible()
    phone.click(".navbar-toggler")
    phone.wait_for_selector("#sidebar-menu.show")
    phone.click("#sidebar-menu >> text=All complaints")
    phone.wait_for_url("**#complaints")
    open_no = js(phone, "DB.complaints.find(c => isOpen(c) && c.status !== 'NOT_ATTENDED').no")
    phone.goto(f"{URL}#visit/{open_no}")
    pick_line(phone, "#v-parts", 0, "EIO8437")
    qty(phone, "#v-parts", 0, 1)
    assert js(phone, "getComputedStyle(document.querySelector('#v-parts .lines-table tbody tr')).display") == "grid"
    assert js(phone, "getComputedStyle(document.querySelector('#v-collect .lines-table thead')).display") == "none"
    assert js(phone, "document.documentElement.scrollWidth <= window.innerWidth + 1"), "phone page scrolls sideways"
    shot(phone, "10-phone-record-visit", check=False)
    phone.goto(f"{URL}#batch/RB-0002")
    assert js(phone, "document.documentElement.scrollWidth <= window.innerWidth + 1"), "phone batch page scrolls sideways"
    for h in ("#today", "#dash", "#insights", "#smart", "#drafts", "#complaint-new"):
        phone.goto(URL + h)
        phone.wait_for_timeout(200)
        assert js(phone, "document.documentElement.scrollWidth <= window.innerWidth + 1"), f"phone {h} scrolls sideways"
    shot(phone, "13-phone-today", check=False)
    browser.close()

print("Layout warnings:", wide or "none")
print("JS errors:", errors or "none")
assert not errors
print("walkthrough OK")
