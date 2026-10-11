"""Automated walkthrough of the stock mockup (desktop + phone). Fails on any JS error or broken rule.

Run with the repo root served on :8080:
    uv run --with playwright python mockups/stock/walkthrough.py <screenshot-dir>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/mockups/stock/index.html"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
errors = []


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def js(page, expr):
    return page.evaluate(expr)


def pick_item(page, line_no, text, create=False):
    """Type into the searchable item select on line N and choose the first match (or 'create')."""
    line = page.locator("#lines .line").nth(line_no)
    line.locator(".ts-control").click()
    line.locator(".ts-control input").fill(text)
    page.wait_for_timeout(150)
    dropdown = line.locator(".ts-dropdown")
    (dropdown.locator(".create") if create else dropdown.locator(".option").first).click()


def qty(page, line_no, value, cls=".qty"):
    page.locator("#lines .line").nth(line_no).locator(cls).fill(str(value))


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(URL)
    page.wait_for_selector(".big-actions")
    shot(page, "01-dashboard")

    # 1. Stock IN: old spelling resolves to the real item; an unknown code is created on the spot.
    before = js(page, "balance('EIO8437','Vizag Office')")
    page.goto(URL + "#in")
    page.fill("#f-ref", "DC 5012")
    pick_item(page, 0, "ei08437")
    qty(page, 0, 5)
    page.locator("#lines .line").nth(0).locator(".batch").fill("B2510")
    page.locator("#lines .line").nth(0).locator(".pkd").fill("2026-09")
    page.click("text=＋ Add another item")
    pick_item(page, 1, "LG99-200-700X", create=True)
    page.select_option("#it-type", "Driver")
    page.fill("#it-desc", "LED driver 200W (new model)")
    page.click("#dlg >> text=Create item")
    qty(page, 1, 3)
    shot(page, "02-stock-in-form")
    page.click("button:has-text('Save Stock IN')")
    page.wait_for_url("**#entry/IN-*")
    assert js(page, "balance('EIO8437','Vizag Office')") == before + 5
    assert js(page, "balance('LG99-200-700X','Vizag Office')") == 3
    shot(page, "03-entry-saved")

    # 2. Stock OUT: over-issue shows a live error and is refused; a valid issue saves.
    have = js(page, "balance('EIO6006','Vizag Office')")
    page.goto(URL + "#out")
    page.fill("#f-site", "Dr Reddys, Vizag")
    pick_item(page, 0, "EIO6O06")  # look-alike typo (letter O)
    qty(page, 0, have + 50)
    assert "Only" in page.locator("#lines .line small.err").first.inner_text()
    shot(page, "04-stock-out-over-issue")
    page.click("button:has-text('Save Stock OUT')")
    assert "Only" in page.inner_text("#form-error")
    assert js(page, "balance('EIO6006','Vizag Office')") == have
    qty(page, 0, 2)
    page.click("button:has-text('Save Stock OUT')")
    page.wait_for_url("**#entry/OUT-*")
    out_no = page.url.split("/")[-1]
    assert js(page, "balance('EIO6006','Vizag Office')") == have - 2

    # 3. Transfer: same From/To refused; Vizag Office -> Svkml works.
    tv0 = js(page, "balance('LG78-150-700','Svkml')")
    page.goto(URL + "#transfer")
    page.select_option("#f-dest", "Vizag Office")
    pick_item(page, 0, "LG78-150-700")
    qty(page, 0, 2)
    page.click("button:has-text('Save Transfer stock')")
    assert "different" in page.inner_text("#form-error")
    page.select_option("#f-dest", "Svkml")
    page.click("button:has-text('Save Transfer stock')")
    page.wait_for_url("**#entry/TRF-*")
    assert js(page, "balance('LG78-150-700','Svkml')") == tv0 + 2

    # 4. Adjust: needs a reason; counted qty shows the difference and corrects stock.
    lens = js(page, "balance('LENS','Vizag Office')")
    page.goto(URL + "#adjust")
    pick_item(page, 0, "lens")
    qty(page, 0, lens - 1, ".counted")
    page.locator("#lines .counted").dispatch_event("input")
    assert "-1" in page.locator("#lines .diff").inner_text()
    page.click("button:has-text('Save Adjust stock count')")
    assert "reason" in page.inner_text("#form-error")
    page.select_option("#f-reason", "Damaged")
    page.fill("#f-note", "1 lens cracked")
    shot(page, "05-adjust")
    page.click("button:has-text('Save Adjust stock count')")
    page.wait_for_url("**#entry/ADJ-*")
    assert js(page, "balance('LENS','Vizag Office')") == lens - 1

    # 5. Undo the Stock OUT: needs a reason; stock comes back; entry shows as undone.
    page.goto(f"{URL}#entry/{out_no}")
    page.click("text=↶ Undo this entry")
    page.click("#dlg >> text=Undo entry")
    assert "reason" in page.inner_text("#undo-err")
    page.fill("#undo-reason", "Entered against the wrong job")
    page.click("#dlg >> text=Undo entry")
    assert js(page, "balance('EIO6006','Vizag Office')") == have
    assert "undone by" in page.inner_text("#view")

    # 6. Items: a look-alike duplicate is refused; a new item saves.
    page.goto(URL + "#item-new")
    page.fill("#it-code", "lg30-018-054-300")
    page.locator("#it-code").dispatch_event("input")
    assert "already exists" in page.inner_text("#it-code-hint") or "Looks like" in page.inner_text("#it-code-hint")
    page.select_option("#it-type", "Driver")
    page.click("button:has-text('Save item')")
    assert "already exists" in page.inner_text("#form-error")
    page.fill("#it-code", "MCB 32A DP")
    page.select_option("#it-type", "Accessory")
    page.fill("#it-desc", "MCB 32A double pole")
    page.select_option("#it-company", "Havells")
    page.fill("#it-reorder", "4")
    shot(page, "06-item-form")
    page.click("button:has-text('Save item')")
    page.wait_for_url("**#item/MCB%2032A%20DP")

    # 7. Lists, filters, item card date range, exports.
    page.goto(URL + "#stock")
    shot(page, "07-current-stock")
    page.select_option("label:has-text('Location') select", "Svkml")
    assert "LG78-150-700" in page.inner_text("table")
    page.goto(URL + "#item/EIO6006")
    page.fill("label:has-text('From date') input", "2026-09-01")
    page.locator("label:has-text('From date') input").dispatch_event("change")
    shot(page, "08-item-card")
    page.goto(URL + "#moves")
    shot(page, "09-movements")
    page.goto(URL + "#low")
    shot(page, "10-low-stock")
    page.goto(URL + "#items")
    shot(page, "11-items")
    page.goto(URL + "#masters")
    shot(page, "12-masters")
    for f in ["Current_Stock", "Stock_Movements", "Item_List", "Low_Stock"]:
        r = page.request.get(f"http://127.0.0.1:8080/mockups/stock/exports/{f}.xlsx")
        assert r.status == 200 and r.body()[:2] == b"PK", f

    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.on("pageerror", lambda e: errors.append("phone: " + str(e)))
    phone.goto(URL)
    phone.wait_for_selector(".big-actions")
    phone.screenshot(path=str(OUT / "13-phone-dashboard.png"), full_page=True)
    phone.goto(URL + "#out")
    phone.wait_for_selector("#lines .line")
    phone.screenshot(path=str(OUT / "14-phone-stock-out.png"), full_page=True)
    browser.close()

print("JS errors:", errors or "none")
assert not errors
print("walkthrough OK")
