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

    # 2b. Valid visit: 2 parts used + 2 defectives collected -> Material to check.
    fill_line(page, "v-parts", 0, "EIO6006", 2)
    fill_line(page, "v-defects", 0, "EIO6006", 2, ["LEDs dead", "B2502", "01-2026"])
    page.click(".choices label:has-text('Material to check')")
    shot(page, "a3-visit-form")
    page.click("text=Save visit")
    page.wait_for_url(f"**#cmp/view/{ticket}")
    assert state(page, "balance('EIO6006','Vizag Office','FRESH')") == fresh0 - 2
    assert state(page, "balance('EIO6006','Vizag Office','DEFECTIVE')") == def0 + 2
    tags = state(page, f"pieces.filter(p=>p.ticket==='{ticket}').map(p=>p.tag)")
    assert len(tags) == 2 and state(page, f"complaint('{ticket}').status") == "MATERIAL_TO_CHECK"
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

    # 3. Office: put the 2 pieces in a new return batch, print the Wipro list, mark sent.
    page.select_option("#who", "Office")
    page.goto(URL + "#def/pieces")
    page.fill("label:has-text('Search') input", ticket)
    page.locator("label:has-text('Search') input").dispatch_event("change")
    for t in tags:
        page.locator("tr", has_text=t).locator("input[type=checkbox]").check()
    page.click("text=New return batch (2)")
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

    # 4. Wipro result: one replaced (fresh +1, linked), one rejected -> batch settles.
    page.locator("tr", has_text=tags[0]).locator("input[type=checkbox]").check()
    page.click("text=Replacement received (1)")
    page.fill("#rp-dc", "6021")
    page.click("#dlg >> text=Save")
    assert state(page, "balance('EIO6006','Vizag Office','FRESH')") == fresh0 - 2 + 1
    assert state(page, f"piece('{tags[0]}').replacement") != ""
    page.locator("tr", has_text=tags[1]).locator("input[type=checkbox]").check()
    page.click("text=Rejected by Wipro (1)")
    page.fill("#rj-note", "Out of warranty")
    page.click("#dlg >> text=Save")
    assert state(page, f"batch('{bno}').status") == "SETTLED"
    invariant(page, "settled")
    shot(page, "a8-batch-settled")

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
