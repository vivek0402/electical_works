"""End-to-end walkthrough against a running dev server with demo data (ports mockups/stock/walkthrough.py).

    uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office <password>

Each run creates (then undoes the stock of) a new item TEST-<timestamp>, so it can be re-run.
Screenshots go to e2e/screen-<width>.png.
Exit code 0 = every step passed and the browser logged no JS errors.
"""

import re
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE, USER, PASSWORD = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
OUT = Path(__file__).resolve().parent
errors = []
NEW = f"TEST-{int(time.time())}"  # a fresh item code per run


def watch(page):
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))


def login(page):
    page.goto(f"{BASE}/login/")
    page.fill("#id_username", USER)
    page.fill("#id_password", PASSWORD)
    page.click("button[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("Stock dashboard")


def pick_item(page, text, create=False, row=0):
    """Type into the item picker on a line; pick the first match (or 'Create new item')."""
    line = page.locator(".lines-table tbody tr").nth(row)
    line.locator(".ts-control").click()
    line.locator(".ts-control input").fill(text)
    dropdown = line.locator(".ts-dropdown")
    target = dropdown.locator(".create") if create else dropdown.locator(".option").first
    expect(target).to_be_visible()  # Tom Select filters ~300 ms after typing
    target.click()


def server_error(page):
    return page.locator("#form-error")


def run(page):
    watch(page)
    login(page)
    expect(page.locator("#chart-weekly .apexcharts-canvas, #chart-weekly svg").first).to_be_visible()

    # Global search: an old spelling (I/1, O/0 look-alike) finds the item; Enter opens it.
    page.fill("#gsearch", "ei08437")
    expect(page.locator("#gresults [role=option]").first).to_contain_text("EIO8437")
    page.press("#gsearch", "Enter")
    expect(page.locator(".page-title")).to_contain_text("EIO8437")

    # Stock IN with a brand-new item created from the picker.
    page.goto(f"{BASE}/stock/in/")
    expect(page.locator("#id_company option:checked")).to_have_text("Wipro Lighting")
    page.fill("#id_ref", "DC 5012")
    pick_item(page, NEW, create=True)
    modal = page.locator("#new-item-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#id_qi-code")).to_have_value(NEW)
    modal.locator("#id_qi-spare_type-ts-control").click()
    modal.locator("#id_qi-spare_type-ts-control").fill("Driver")
    option = modal.locator(".ts-dropdown .option", has_text=re.compile(r"^Driver$"))
    expect(option).to_be_visible()
    option.click()
    page.fill("#id_qi-description", "Walkthrough test driver")
    page.click("#new-item-form button[type=submit]")
    expect(modal).to_be_hidden()
    expect(page.locator(".lines-table .ts-control .item").first).to_have_text(NEW)
    page.locator("input[name=line_qty]").first.fill("5")
    page.click("button.btn-in[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("IN-")
    in_no = page.locator(".page-title .code").inner_text()

    # Stock OUT: an over-issue shows a live error and the form refuses to post it.
    page.goto(f"{BASE}/stock/out/")
    pick_item(page, NEW)
    page.locator("input[name=line_qty]").first.fill("99")
    expect(page.locator(".err").first).to_contain_text("Only 5 NOS available")
    page.click("button.btn-out[type=submit]")
    expect(server_error(page)).to_contain_text("Fix the highlighted quantities")
    expect(page).to_have_url(re.compile(r"/stock/out/$"))

    # Transfer: the same From/To location is refused by the server; a real transfer saves.
    page.goto(f"{BASE}/stock/transfer/")
    page.select_option("#id_to_location", label="Vizag Office")
    pick_item(page, "LG78-150-700")
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("#entry-form button[type=submit]")
    expect(page.locator("body")).to_contain_text("must be different")
    page.select_option("#id_to_location", label="Svkml")
    pick_item(page, "LG78-150-700")  # make sure the line survived the round trip
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("#entry-form button[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("TRF-")

    # Adjust: the difference shows live; reason and note are required.
    page.goto(f"{BASE}/stock/adjust/")
    pick_item(page, "LENS")
    system = int(page.locator(".lines-table .avail b").first.inner_text())
    page.locator("input[name=line_qty]").first.fill(str(system - 1))
    expect(page.locator(".lines-table .diff").first).to_contain_text("-1")
    page.click("#entry-form button[type=submit]")
    expect(server_error(page)).to_contain_text(re.compile("reason|note"))
    page.select_option("#id_reason", label="Damaged")
    page.fill("#id_note", "1 lens cracked (walkthrough)")
    if not page.locator(".lines-table .ts-control .item").count():
        pick_item(page, "LENS")
    page.locator("input[name=line_qty]").first.fill(str(system - 1))
    page.click("#entry-form button[type=submit]")
    expect(page.locator(".page-title")).to_contain_text("ADJ-")

    # Current stock: sort + export.
    page.goto(f"{BASE}/stock/?sort=total&dir=desc")
    expect(page.locator("table")).to_be_visible()
    with page.expect_download() as dl:
        page.click("text=Export to Excel")
    assert dl.value.suggested_filename.startswith("Current_Stock_"), dl.value.suggested_filename

    # Undo the IN we made: reason required, then a REV entry.
    page.goto(f"{BASE}/movements/?q={NEW}")
    page.locator("a.code", has_text=re.compile(r"^IN-")).first.click()
    expect(page.locator(".page-title")).to_contain_text(in_no)
    page.click("text=Undo this entry")
    expect(page.locator("#undo-modal")).to_be_visible()
    page.fill("#undo-reason", "walkthrough cleanup")
    page.click("#undo-submit")
    expect(page.locator(".page-title")).to_contain_text("REV-")
    expect(page.locator("body")).to_contain_text(f"{in_no} undone by")


def phone(page):
    """Phone width: log in, open the off-canvas menu, open a list screen."""
    watch(page)
    login(page)
    page.click(".navbar-toggler")
    expect(page.get_by_role("link", name="Stock IN").first).to_be_visible()
    page.goto(f"{BASE}/stock/")
    expect(page.locator("table")).to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for size in ({"width": 1366, "height": 860}, {"width": 390, "height": 844}):
        page = browser.new_page(viewport=size)
        if size["width"] > 500:
            run(page)
        else:
            phone(page)
        page.screenshot(path=str(OUT / f"screen-{size['width']}.png"), full_page=True)
        page.close()
    browser.close()

print("JS errors:", errors or "none")
sys.exit(1 if errors else 0)
