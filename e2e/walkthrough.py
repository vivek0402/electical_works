"""End-to-end walkthrough against a running dev server with demo data (ports mockups/stock/walkthrough.py).

    uv run --with playwright python e2e/walkthrough.py http://127.0.0.1:8000 office [password]

The password comes from argv, or from the E2E_PASSWORD environment variable.

Re-runnable: each run creates a new item TEST-<timestamp>, then undoes everything it posted (the Stock IN,
the transfer and the adjustment), so stock levels end where they started. Only the new item and the
entry/undo pairs stay on record.

Screenshots go to e2e/screen-<width>.png. If a step fails, e2e/screen-<width>-FAIL.png is saved, and the
failing step and any JS errors are printed.
Exit code 0 = every step passed and the browser logged no JS errors.
"""

import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

if len(sys.argv) < 3 or (len(sys.argv) < 4 and not os.environ.get("E2E_PASSWORD")):
    print(__doc__)
    print("Usage: python e2e/walkthrough.py <base-url> <username> [password]  (or set E2E_PASSWORD)")
    sys.exit(2)
BASE, USER = sys.argv[1].rstrip("/"), sys.argv[2]
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else os.environ["E2E_PASSWORD"]
OUT = Path(__file__).resolve().parent
NEW = f"TEST-{int(time.time())}"  # a fresh item code per run
errors = []
current = {"step": "start"}


class WalkthroughError(Exception):
    """A check failed."""


def step(label):
    current["step"] = label
    print(f"- {label}")


def check(condition, message):
    if not condition:
        raise WalkthroughError(message)


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


def entry_number(page, prefix):
    expect(page.locator(".page-title")).to_contain_text(f"{prefix}-")
    return page.locator(".page-title .code").inner_text().strip()


def undo(page, number, reason):
    """Undo an entry from its detail page (the page must already be open)."""
    expect(page.locator(".page-title")).to_contain_text(number)
    page.click("text=Undo this entry")
    expect(page.locator("#undo-modal")).to_be_visible()
    page.fill("#undo-reason", reason)
    page.click("#undo-submit")
    entry_number(page, "REV")
    expect(page.locator("body")).to_contain_text(f"{number} undone by")


def run(page):
    watch(page)
    step("log in (desktop)")
    login(page)
    expect(page.locator("#chart-weekly .apexcharts-canvas, #chart-weekly svg").first).to_be_visible()

    step("global search finds an old spelling; Enter opens the item")
    page.fill("#gsearch", "ei08437")
    expect(page.locator("#gresults [role=option]").first).to_contain_text("EIO8437")
    page.press("#gsearch", "Enter")
    expect(page.locator(".page-title")).to_contain_text("EIO8437")

    step(f"Stock IN with new item {NEW} created from the picker")
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
    in_no = entry_number(page, "IN")

    step("Stock OUT over-issue is flagged live and not posted")
    page.goto(f"{BASE}/stock/out/")
    pick_item(page, NEW)
    page.locator("input[name=line_qty]").first.fill("99")
    expect(page.locator(".err").first).to_contain_text("Only 5 NOS available")
    page.click("button.btn-out[type=submit]")
    expect(page.locator("#form-error")).to_contain_text("Fix the highlighted quantities")
    expect(page).to_have_url(re.compile(r"/stock/out/$"))

    step("transfer to the same location is refused; a real transfer saves")
    page.goto(f"{BASE}/stock/transfer/")
    page.select_option("#id_to_location", label="Vizag Office")
    pick_item(page, "LG78-150-700")
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("#entry-form button[type=submit]")
    expect(page.locator("body")).to_contain_text("must be different")
    page.select_option("#id_to_location", label="Svkml")
    pick_item(page, "LG78-150-700")
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("#entry-form button[type=submit]")
    trf_no = entry_number(page, "TRF")

    step("adjustment shows the difference live and needs a reason and note")
    page.goto(f"{BASE}/stock/adjust/")
    pick_item(page, "LENS")
    system = int(page.locator(".lines-table .avail b").first.inner_text())
    check(system > 0, f"LENS has no stock at the default location ({system}); re-seed the demo data")
    page.locator("input[name=line_qty]").first.fill(str(system - 1))
    expect(page.locator(".lines-table .diff").first).to_contain_text("-1")
    page.click("#entry-form button[type=submit]")
    expect(page.locator("#form-error")).to_contain_text(re.compile("reason|note"))
    page.select_option("#id_reason", label="Damaged")
    page.fill("#id_note", "1 lens cracked (walkthrough)")
    if not page.locator(".lines-table .ts-control .item").count():
        pick_item(page, "LENS")
    page.locator("input[name=line_qty]").first.fill(str(system - 1))
    page.click("#entry-form button[type=submit]")
    adj_no = entry_number(page, "ADJ")

    step("current stock sorts and exports to Excel")
    page.goto(f"{BASE}/stock/?sort=total&dir=desc")
    expect(page.locator("table")).to_be_visible()
    with page.expect_download() as dl:
        page.click("text=Export to Excel")
    name = dl.value.suggested_filename
    check(
        name.startswith("Current_Stock_") and name.endswith(".xlsx"), f"unexpected export file name {name!r}"
    )

    step(f"clean-up: undo {adj_no} and {trf_no}")
    for number in (adj_no, trf_no):
        page.goto(f"{BASE}/entries/{number}/")
        undo(page, number, "walkthrough cleanup")

    step(f"clean-up: find {in_no} in movements and undo it")
    page.goto(f"{BASE}/movements/?q={NEW}")
    page.locator("a.code", has_text=re.compile(r"^IN-")).first.click()
    undo(page, in_no, "walkthrough cleanup")


def phone(page):
    """Phone width: log in, open the off-canvas menu, open a list screen."""
    watch(page)
    step("log in (phone) and open the menu")
    login(page)
    page.click(".navbar-toggler")
    expect(page.get_by_role("link", name="Stock IN").first).to_be_visible()
    step("current stock on a phone")
    page.goto(f"{BASE}/stock/")
    expect(page.locator("table")).to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch()
    for size in ({"width": 1366, "height": 860}, {"width": 390, "height": 844}):
        page = browser.new_page(viewport=size)
        try:
            if size["width"] > 500:
                run(page)
            else:
                phone(page)
        except Exception as exc:  # report any failure (Playwright timeout, failed check) the same way
            shot = OUT / f"screen-{size['width']}-FAIL.png"
            page.screenshot(path=str(shot), full_page=True)
            print(f"FAILED at step: {current['step']}\n{type(exc).__name__}: {exc}")
            print(f"Screenshot: {shot}")
            print("JS errors:", errors or "none")
            browser.close()
            sys.exit(1)
        page.screenshot(path=str(OUT / f"screen-{size['width']}.png"), full_page=True)
        page.close()
    browser.close()

print("JS errors:", errors or "none")
sys.exit(1 if errors else 0)
