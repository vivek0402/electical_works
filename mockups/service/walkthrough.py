"""Automated walkthrough of the stock mockup (Tabler admin layout), desktop + phone.

Fails on any JS error or broken rule. Run with the repo root served on :8080:
    uv run --with playwright python mockups/stock/walkthrough.py <screenshot-dir>
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8080/mockups/stock/index.html"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
errors = []


def shot(page, name):
    page.wait_for_timeout(250)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def js(page, expr):
    return page.evaluate(expr)


def row(page, n):
    return page.locator("#lines tbody tr").nth(n)


def pick_item(page, n, text, create=False):
    """Type into the searchable item select on line n; pick the first match (or 'create')."""
    r = row(page, n)
    r.locator(".ts-control").click()
    r.locator(".ts-control input").fill(text)
    page.wait_for_timeout(150)
    dd = page.locator(".ts-dropdown:visible")
    (dd.locator(".create") if create else dd.locator(".option").first).click()


def qty(page, n, value, cls=".qty"):
    row(page, n).locator(cls).fill(str(value))
    row(page, n).locator(cls).dispatch_event("input")


def save(page, label):
    page.click(f"button:has-text('{label}')")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_selector("#chart-weekly .apexcharts-canvas")
    shot(page, "01-dashboard")

    # Global search: an old spelling finds the item; Enter opens it.
    page.fill("#gsearch", "ei08437")
    page.locator("#gsearch").dispatch_event("input")
    assert "EIO8437" in page.inner_text("#gresults")
    shot(page, "02-global-search")
    page.press("#gsearch", "Enter")
    page.wait_for_url("**#item/EIO8437")

    # 1. Stock IN: old spelling resolves; an unknown code is created in a modal.
    before = js(page, "balance('EIO8437','Vizag Office')")
    page.goto(URL + "#in")
    page.fill("#f-ref", "DC 5012")
    pick_item(page, 0, "ei08437")
    qty(page, 0, 5)
    row(page, 0).locator(".batch").fill("B2510")
    row(page, 0).locator(".pkd").fill("2026-09")
    page.click("button:has-text('Add another item')")
    pick_item(page, 1, "LG99-200-700X", create=True)
    page.wait_for_selector("#modal.show")
    page.select_option("#it-type", "Driver")
    page.fill("#it-desc", "LED driver 200W (new model)")
    page.click("#modal >> text=Create item")
    page.wait_for_selector("#modal", state="hidden")
    qty(page, 1, 3)
    shot(page, "03-stock-in-form")
    save(page, "Save Stock IN")
    page.wait_for_url("**#entry/IN-*")
    assert js(page, "balance('EIO8437','Vizag Office')") == before + 5
    assert js(page, "balance('LG99-200-700X','Vizag Office')") == 3
    shot(page, "04-entry-saved")

    # 2. Stock OUT: over-issue shows a live error and is refused; a valid issue saves.
    have = js(page, "balance('EIO6006','Vizag Office')")
    page.goto(URL + "#out")
    page.fill("#f-site", "Dr Reddys, Vizag")
    pick_item(page, 0, "EIO6O06")  # look-alike typo (letter O)
    qty(page, 0, have + 50)
    assert "Only" in row(page, 0).locator(".err").inner_text()
    shot(page, "05-stock-out-over-issue")
    save(page, "Save Stock OUT")
    assert "Only" in page.inner_text("#form-error")
    assert js(page, "balance('EIO6006','Vizag Office')") == have
    qty(page, 0, 2)
    save(page, "Save Stock OUT")
    page.wait_for_url("**#entry/OUT-*")
    out_no = page.url.split("/")[-1]
    assert js(page, "balance('EIO6006','Vizag Office')") == have - 2

    # 3. Transfer: same From/To refused; Vizag Office -> Svkml works.
    sv0 = js(page, "balance('LG78-150-700','Svkml')")
    page.goto(URL + "#transfer")
    page.select_option("#f-dest", "Vizag Office")
    pick_item(page, 0, "LG78-150-700")
    qty(page, 0, 2)
    save(page, "Save Transfer stock")
    assert "different" in page.inner_text("#form-error")
    page.select_option("#f-dest", "Svkml")
    save(page, "Save Transfer stock")
    page.wait_for_url("**#entry/TRF-*")
    assert js(page, "balance('LG78-150-700','Svkml')") == sv0 + 2

    # 4. Adjust: needs a reason; shows the difference; corrects stock.
    lens = js(page, "balance('LENS','Vizag Office')")
    page.goto(URL + "#adjust")
    pick_item(page, 0, "lens")
    qty(page, 0, lens - 1, ".counted")
    assert "-1" in row(page, 0).locator(".diff").inner_text()
    save(page, "Save Adjust stock count")
    assert "reason" in page.inner_text("#form-error")
    page.select_option("#f-reason", "Damaged")
    page.fill("#f-note", "1 lens cracked")
    shot(page, "06-adjust")
    save(page, "Save Adjust stock count")
    page.wait_for_url("**#entry/ADJ-*")
    assert js(page, "balance('LENS','Vizag Office')") == lens - 1

    # 5. Undo the Stock OUT: reason required; stock comes back.
    page.goto(f"{URL}#entry/{out_no}")
    page.click("button:has-text('Undo this entry')")
    page.wait_for_selector("#modal.show")
    page.click("#modal >> text=Undo entry")
    assert "reason" in page.inner_text("#undo-err")
    page.fill("#undo-reason", "Entered against the wrong job")
    page.click("#modal >> text=Undo entry")
    page.wait_for_selector("#modal", state="hidden")
    assert js(page, "balance('EIO6006','Vizag Office')") == have
    assert "undone by" in page.inner_text("#view").lower()
    shot(page, "07-entry-undone")

    # 6. Items: look-alike duplicate refused; new item saves.
    page.goto(URL + "#item-new")
    page.fill("#it-code", "lg30-018-054-300")
    page.locator("#it-code").dispatch_event("input")
    assert re.search("already exists|Looks like", page.inner_text("#it-code-hint"))
    page.select_option("#it-type", "Driver")
    save(page, "Save item")
    assert "already exists" in page.inner_text("#form-error")
    page.fill("#it-code", "MCB 32A DP")
    page.locator("#it-code").dispatch_event("input")
    page.select_option("#it-type", "Accessory")
    page.fill("#it-desc", "MCB 32A double pole")
    page.select_option("#it-company", "Havells")
    page.fill("#it-reorder", "4")
    shot(page, "08-item-form")
    save(page, "Save item")
    page.wait_for_url("**#item/MCB%2032A%20DP")

    # 7. Tables: sort, paging, filters; item card date range.
    page.goto(URL + "#stock")
    page.click("#dt-stock th:has-text('Total')")
    page.click("#dt-stock th:has-text('Total')")  # descending
    totals = [int(t) for t in page.locator("#dt-stock tbody tr td:nth-last-child(2)").all_inner_texts()]
    assert totals == sorted(totals, reverse=True), totals
    assert "Showing 1–10 of" in page.inner_text("#dt-stock")
    page.click("#dt-stock .pagination >> text=2")
    assert "Showing 11–20 of" in page.inner_text("#dt-stock")
    shot(page, "09-current-stock")
    page.locator(".card-header select").first.select_option("Svkml")
    assert "LG78-150-700" in page.inner_text("#dt-stock")
    page.goto(URL + "#item/EIO6006")
    page.locator("label:has-text('From date') + input").fill("2026-09-01")
    page.locator("label:has-text('From date') + input").dispatch_event("change")
    shot(page, "10-item-card")
    page.goto(URL + "#moves")
    assert "Showing 1–10 of" in page.inner_text("#dt-moves")
    shot(page, "11-movements")
    for h, n in [("#low", "12-low-stock"), ("#items", "13-items"), ("#masters", "14-masters")]:
        page.goto(URL + h)
        shot(page, n)
    for f in ["Current_Stock", "Stock_Movements", "Item_List", "Low_Stock"]:
        r = page.request.get(f"http://127.0.0.1:8080/mockups/stock/exports/{f}.xlsx")
        assert r.status == 200 and r.body()[:2] == b"PK", f

    # Phone: menu collapses behind the toggler; forms stack.
    phone = browser.new_page(viewport={"width": 390, "height": 844})
    phone.on("pageerror", lambda e: errors.append("phone: " + str(e)))
    phone.goto(URL)
    phone.wait_for_selector("#chart-weekly .apexcharts-canvas")
    phone.screenshot(path=str(OUT / "15-phone-dashboard.png"), full_page=True)
    assert not phone.locator("#sidebar-menu").is_visible()
    phone.click(".navbar-toggler")
    phone.wait_for_selector("#sidebar-menu.show")
    phone.screenshot(path=str(OUT / "16-phone-menu.png"))
    phone.click("#sidebar-menu >> text=Stock OUT")
    phone.wait_for_url("**#out")
    pick_item(phone, 0, "EIO6006")
    qty(phone, 0, 2)
    phone.screenshot(path=str(OUT / "17-phone-stock-out.png"), full_page=True)
    browser.close()

print("JS errors:", errors or "none")
assert not errors
print("walkthrough OK")
