"""Automated walkthrough of the 3-system mockup (desktop + phone).

Run (with the mockup served on :8080 from the repo root):
    uv run --with playwright python mockups/walkthrough.py <screenshot-dir>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/mockups/app/index.html"
OUT = Path(sys.argv[1])
errors = []


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def state(page, js):
    return page.evaluate(js)


def invariant(page, step):
    bad = state(page, "checkInvariant()")
    assert bad == [], f"invariant broken after {step}: {bad}"


def fill_line(page, tbody, n, code, qty, extra=None):
    row = page.locator(f"#{tbody} tr").nth(n)
    row.locator("input[list=itemlist]").fill(code)
    row.locator("input[list=itemlist]").dispatch_event("change")
    page.wait_for_timeout(50)
    row = page.locator(f"#{tbody} tr").nth(n)
    row.locator(".qty-in").fill(str(qty))
    row.locator(".qty-in").dispatch_event("change")
    page.wait_for_timeout(50)
    for i, val in enumerate(extra or []):
        extras = "td[data-label] input:not(.qty-in):not([list])"
        inp = page.locator(f"#{tbody} tr").nth(n).locator(extras).nth(i)
        inp.fill(val)
        inp.dispatch_event("change")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(URL)
    invariant(page, "seed")
    shot(page, "a1-home")

    fresh0 = state(page, "balance('EIO6006','Vizag Office','FRESH')")
    def0 = state(page, "balance('EIO6006','Vizag Office','DEFECTIVE')")

    # 1. Office files a complaint (invalid phone warns, does not block) and assigns Ramu.
    page.goto(URL + "#cmp/new")
    page.fill("label:has-text('Customer') input", "Test Pharma Unit-1")
    page.locator("label:has-text('Customer') input").dispatch_event("change")
    page.fill("label:has-text('Contact phone') input", "12345")
    assert "Not a valid" in page.inner_text("#ph-warn")
    page.fill("textarea", "LED modules dead in QC lab")
    page.locator("textarea").dispatch_event("change")
    page.check("label:has-text('Ramu') input")
    page.click("text=File complaint")
    page.wait_for_url("**#cmp/view/CMP-2026-*")
    ticket = page.url.split("/")[-1]
    shot(page, "a2-complaint-filed")

    # 2. Ramu's view: the complaint is in "My complaints"; the defectives system is hidden.
    page.select_option("#who", "Ramu")
    page.wait_for_url("**#cmp/mine")
    assert ticket in page.inner_text("#view")
    page.goto(URL + "#def")
    page.wait_for_url("**#cmp/mine")

    # 2a. Over-issue on a visit is refused and saves nothing.
    pieces_before = state(page, "pieces.length")
    page.goto(f"{URL}#cmp/visit/{ticket}")
    page.fill("textarea", "Checked QC lab")
    page.locator("textarea").dispatch_event("change")
    fill_line(page, "v-parts", 0, "EIO6O06", 999)  # typo is resolved to EIO6006
    page.click("text=Save visit")
    assert "Only" in page.inner_text("#v-error")
    assert state(page, "pieces.length") == pieces_before

    # 2b. Valid visit: 2 parts used + 4 defectives collected -> Material to check.
    fill_line(page, "v-parts", 0, "EIO6006", 2)
    fill_line(page, "v-defects", 0, "EIO6006", 4, ["LEDs dead", "B2502", "01-2026"])
    page.click(".choices label:has-text('Material to check')")
    shot(page, "a3-visit-form")
    page.click("text=Save visit")
    page.wait_for_url(f"**#cmp/view/{ticket}")
    assert state(page, "balance('EIO6006','Vizag Office','FRESH')") == fresh0 - 2
    assert state(page, "balance('EIO6006','Vizag Office','DEFECTIVE')") == def0 + 4
    tags = state(page, f"pieces.filter(p=>p.ticket==='{ticket}').map(p=>p.tag)")
    assert len(tags) == 4 and state(page, f"complaint('{ticket}').status") == "MATERIAL_TO_CHECK"
    invariant(page, "visit")
    shot(page, "a4-complaint-after-visit")

    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.on("pageerror", lambda e: errors.append("phone: " + str(e)))
    phone.goto(URL)
    phone.select_option("#who", "Ramu")
    phone.wait_for_url("**#cmp/mine")
    phone.screenshot(path=str(OUT / "a5-phone-my-complaints.png"), full_page=True)
    phone.goto(f"{URL}#cmp/visit/CMP-2026-0007")
    phone.screenshot(path=str(OUT / "a6-phone-visit.png"), full_page=True)

    # 3. Office: put the 4 pieces in a new return batch, print the Wipro list, mark sent.
    page.select_option("#who", "Office")
    page.goto(URL + "#def/pieces")
    page.fill("label:has-text('Search') input", ticket)
    page.locator("label:has-text('Search') input").dispatch_event("change")
    for t in tags:
        page.locator("tr", has_text=t).locator("input[type=checkbox]").check()
    page.click("text=New return batch (4)")
    page.wait_for_url("**#def/batch/RB-*")
    bno = page.url.split("/")[-1]
    invariant(page, "batch draft")
    page.click("text=Wipro list (print / Excel)")
    wl = page.inner_text("#dlg")
    assert "Wipro Defective List" in wl and "PCB CODE" in wl and "EIO6006" in wl and "B2502" in wl
    shot(page, "a7-wipro-list")
    page.click("#dlg >> text=Close")
    page.click("text=Mark as sent to Wipro")
    page.fill("#sd-docket", "VZG/1011")
    page.click("#dlg >> text=Mark sent")
    assert state(page, "balance('EIO6006','Vizag Office','DEFECTIVE')") == def0
    assert state(page, f"batch('{bno}').status") == "SENT"
    invariant(page, "sent")

    # 4. Wipro answers in several ways and deliveries.
    # 4a. A Wipro delivery entered in Stock IN: 1 same item, 1 different item, 10 new stock.
    fresh_before = state(page, "balance('EIO6006','Vizag Office','FRESH')")
    fts_before = state(page, "balance('FTS-KC-60-57K','Vizag Office','FRESH')")
    page.goto(URL + "#stock/in")
    page.fill("label:has-text('DC / invoice no.') input", "7001")
    page.locator("label:has-text('DC / invoice no.') input").dispatch_event("change")
    fill_line(page, "st-lines", 0, "EIO6006", 1)
    page.click("text=+ Add another item")
    fill_line(page, "st-lines", 1, "EIO8437", 1)
    page.click("text=+ Add another item")
    fill_line(page, "st-lines", 2, "FTS-KC-60-57K", 10)
    page.click("text=Save Stock IN")
    page.wait_for_url("**#stock/entry/IN-*")
    rcpt = page.url.split("/")[-1]
    assert "Match to defectives" in page.inner_text("#view")
    page.click("text=Match to defectives →")
    page.wait_for_url(f"**#def/match/{rcpt}")
    # Over-match is refused: three pieces picked against one EIO6006 + one EIO8437.
    page.locator("tr", has_text=tags[0]).locator("select").select_option("EIO6006")
    page.locator("tr", has_text=tags[1]).locator("select").select_option("EIO8437")
    page.locator("tr", has_text=tags[2]).locator("select").select_option("EIO6006")
    page.click("text=Save matches (3)")
    assert "only 1" in page.inner_text("#mt-err")
    page.locator("tr", has_text=tags[2]).locator("select").select_option("")
    shot(page, "a8-match")
    page.click("text=Save matches (2)")
    page.wait_for_url(f"**#stock/entry/{rcpt}")
    assert state(page, f"piece('{tags[1]}').replacementCode") == "EIO8437"  # different item
    assert state(page, f"batch('{bno}').status") == "PARTLY_SETTLED"
    assert state(page, f"capacity('{rcpt}')['FTS-KC-60-57K']") == 10  # left as plain new stock
    assert state(page, "balance('FTS-KC-60-57K','Vizag Office','FRESH')") == fts_before + 10
    assert state(page, "balance('EIO6006','Vizag Office','FRESH')") == fresh_before + 1
    invariant(page, "match")

    # 4b. Repaired & returned (same piece back into fresh), then a credit note -> batch settles.
    page.goto(f"{URL}#def/batch/{bno}")
    page.locator("tr", has_text=tags[2]).locator("input[type=checkbox]").check()
    page.click("text=Repaired & returned (1)")
    page.fill("#dl-dc", "7003")
    page.click("#dlg >> text=Save")
    assert state(page, f"piece('{tags[2]}').status") == "REPAIRED"
    assert state(page, "balance('EIO6006','Vizag Office','FRESH')") == fresh_before + 2
    page.locator("tr", has_text=tags[3]).locator("input[type=checkbox]").check()
    page.click("text=Credit note (1)")
    page.fill("#dl-cn", "CN-9001")
    page.fill("#dl-amt", "500")
    page.click("#dlg >> text=Save")
    assert state(page, f"batch('{bno}').status") == "SETTLED"
    invariant(page, "settled")
    shot(page, "a9-batch-settled")

    # 4c. Seeded RB-2026-003: 15W driver replaced by a different item, plus extras on the DC.
    page.goto(URL + "#def/batch/RB-2026-003")
    pending = state(page, "batch('RB-2026-003').tags.filter(t=>piece(t).status==='SENT_TO_WIPRO')")
    lens_before = state(page, "balance('LENS','Vizag Office','FRESH')")
    page.locator("tr", has_text=pending[0]).locator("input[type=checkbox]").check()
    page.click("text=Replaced (1)")
    page.locator(".rp-code").fill("LG30-018-054-300")  # old spelling of a different item
    page.fill("#dl-dc", "7004")
    fill_line(page, "rp-extra", 0, "LENS", 3)
    shot(page, "a10-replace-dialog")
    page.click("#dlg >> text=Save")
    assert state(page, f"piece('{pending[0]}').replacementCode") == "LG30-018-054-0300"
    assert state(page, "balance('LENS','Vizag Office','FRESH')") == lens_before + 3
    assert state(page, "batch('RB-2026-003').status") == "PARTLY_SETTLED"
    invariant(page, "replace dialog")

    # 4d. Other supplier, counted in metres; an over-issue is refused in MTR.
    wire0 = state(page, "balance('WIRE 1.5 SQMM','Vizag Office','FRESH')")
    page.goto(URL + "#stock/in")
    page.click(".choices label:has-text('Received from other supplier')")
    page.fill(".fields input[list=suppliers]", "Sri Sai Electricals")
    page.locator(".fields input[list=suppliers]").dispatch_event("change")
    page.fill(".fields label:has-text('Supplier bill no.') input", "B-200")
    page.locator(".fields label:has-text('Supplier bill no.') input").dispatch_event("change")
    fill_line(page, "st-lines", 0, "WIRE 1.5 SQMM", 40)
    page.click("text=Save Stock IN")
    page.wait_for_url("**#stock/entry/IN-*")
    assert state(page, "balance('WIRE 1.5 SQMM','Vizag Office','FRESH')") == wire0 + 40
    page.goto(URL + "#stock/out")
    fill_line(page, "st-lines", 0, "WIRE 1.5 SQMM", 500)
    page.click("text=Save Stock OUT")
    err = page.inner_text("#st-error")
    assert f"Only {wire0 + 40} MTR of WIRE 1.5 SQMM" in err, err
    invariant(page, "wire")

    # 5. Close the complaint: refused without a reason, accepted with one.
    page.goto(f"{URL}#cmp/view/{ticket}")
    page.click("text=Close complaint…")
    page.click("#dlg >> text=Close complaint")
    assert "closure reason" in page.inner_text("#cl-err")
    page.select_option("#cl-reason", "Resolved")
    page.click("#dlg >> text=Close complaint")
    assert state(page, f"complaint('{ticket}').status") == "CLOSED"
    shot(page, "a9-complaint-closed")

    screens = [
        ("#def", "b1-def-dashboard"),
        ("#def/reports", "b2-def-reports"),
        ("#cmp", "b3-cmp-list"),
        ("#cmp/report", "b4-ap-pending"),
        (f"#def/piece/{tags[0]}", "b5-piece"),
        ("#stock", "b6-stock"),
        ("#stock/item/EIO6006", "b7-item"),
    ]
    for h, n in screens:
        page.goto(URL + h)
        page.wait_for_timeout(100)
        shot(page, n)
    invariant(page, "end")
    browser.close()

print("ticket", ticket, "batch", bno, "pieces", tags)
print("JS errors:", errors or "none")
print("walkthrough OK")
