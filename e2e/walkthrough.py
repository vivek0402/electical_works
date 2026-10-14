"""End-to-end walkthrough against a running dev server with demo data (ports mockups/stock/walkthrough.py).

    uv run --with playwright==1.63.0 python e2e/walkthrough.py http://127.0.0.1:8000 office [password]

The password comes from argv, or from the E2E_PASSWORD environment variable.

Re-runnable on a freshly seeded svkml_demo (`seed_service_demo`), and again on top of an earlier run. Each
run creates a new item TEST-<timestamp>, new complaints and a new return batch; demo pieces and batches are
only read. It undoes the stock entries it can (the Stock IN, the transfer, the adjustment and the visit's
parts given), so the demo items' stock ends where it started. Left behind on purpose, per run:
  - item TEST-<timestamp> with 1 NOS at Vizag Office: the replacement the company sent for its marked piece
    (settled as Replaced, which posts a Stock IN that can't be undone);
  - two TEST-<timestamp> defective pieces: one marked from stock, one collected at the visit. Both go in a new
    return batch for Wipro Lighting that is dispatched and settled: the first Replaced, the second Rejected
    (returned), so it is back in the Defective store;
  - two complaints at the first demo site: one moved Awaiting material, Resolved, Closed; one closed as Not
    covered. Closed complaints don't count as open anywhere;
  - the entry/undo pairs, which stay on record by design.

Screenshots go to e2e/screen-<width>.png, plus e2e/screen-390-complaint.png and e2e/screen-390-visit.png.
If a step fails, e2e/screen-<width>-FAIL.png is saved, and the failing step and any JS errors are printed.
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
COMPANY, OTHER = "Wipro Lighting", "Havells"  # the new item's company; a company with demo pieces in store
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


def ts_pick(page, select_id, text):
    """Type into a Tom Select box (not a line's item picker) and pick the first match."""
    page.locator(f"#{select_id} + .ts-wrapper .ts-control").click()  # its input is tiny once a value is set
    page.locator(f"#{select_id}-ts-control").fill(text)
    option = page.locator(f"#{select_id}-ts-dropdown .option", has_text=text).first
    expect(option).to_be_visible()
    option.click()


def success_text(page):
    alert = page.locator(".alert-success").first
    expect(alert).to_be_visible()
    return alert.inner_text()


def download(page, url, link_text, prefix):
    """Open `url`, click the export link, check the file name."""
    page.goto(url)
    with page.expect_download() as dl:
        page.locator("a", has_text=link_text).first.click()
    name = dl.value.suggested_filename
    check(name.startswith(prefix) and name.endswith(".xlsx"), f"unexpected export file name {name!r}")


def stock_row(page, code):
    """Current stock for one item: ({location: qty}, total, defective store)."""
    page.goto(f"{BASE}/stock/?q={code}")
    heads = [
        h.inner_text().strip().splitlines()[0].strip().upper() for h in page.locator("table thead th").all()
    ]
    row = page.locator("table tbody tr", has=page.locator("a.code", has_text=re.compile(rf"^{code}$")))
    expect(row).to_have_count(1)
    cells = [c.inner_text().strip() for c in row.locator("td").all()]
    check("TOTAL" in heads and "DEFECTIVE STORE" in heads, f"stock columns are {heads}")  # CSS upper-cases
    by_head = dict(zip(heads, cells, strict=True))

    def num(text):  # "5 NOS", "—" for none
        found = re.match(r"-?\d+", text)
        return int(found.group(0)) if found else 0

    places = {h: num(by_head[h]) for h in heads[3 : heads.index("TOTAL")]}
    return places, num(by_head["TOTAL"]), num(by_head["DEFECTIVE STORE"])


def search(page, text, expected):
    """Global search: the dropdown lists `expected`; clicking it opens its page."""
    page.fill("#gsearch", text)
    option = page.locator("#gresults [role=option]", has_text=expected).first
    expect(option).to_be_visible()
    option.click()
    expect(page.locator(".page-title")).to_contain_text(expected)


def change_status(page, label):
    modal = page.locator("#status-modal")
    if not page.locator("#status-modal[data-show-on-load]").count():  # else it opens by itself (last error)
        page.locator(".page-header button", has_text="Change status").click()
    expect(modal).to_be_visible()
    modal.locator(".form-selectgroup-label", has_text=label).click()
    modal.locator("button[type=submit]").click()
    expect(page.locator(".alert-success").first).to_be_visible()
    expect(page.locator(".page-title")).to_contain_text(label)


def no_side_scroll(page, what):
    width = page.evaluate("document.documentElement.scrollWidth")
    check(width <= page.viewport_size["width"], f"{what} scrolls sideways on a phone ({width}px wide)")


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

    step("Mark defective: over-quantity is blocked live; 1 piece saves and gets a DEF tag")
    page.goto(
        f"{BASE}/stock/in/"
    )  # one extra piece to mark, so the clean-up undo of the IN above still balances
    pick_item(page, NEW)
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("button.btn-in[type=submit]")
    entry_number(page, "IN")
    page.goto(f"{BASE}/defectives/mark/")
    expect(page.locator("#id_location option", has_text="Defective store")).to_have_count(0)
    pick_item(page, NEW)
    have = int(page.locator(".lines-table .avail b").first.inner_text())
    page.locator("input[name=line_fault]").first.fill("Dead on arrival (walkthrough)")
    page.locator("input[name=line_qty]").first.fill(str(have + 1))
    expect(page.locator(".err").first).to_contain_text(f"Only {have} NOS available")
    page.click("form[data-lines-form] button[type=submit]")
    expect(page.locator("#form-error")).to_contain_text("Fix the highlighted lines")
    expect(page).to_have_url(re.compile(r"/defectives/mark/$"))
    page.locator("input[name=line_qty]").first.fill("1")
    page.click("form[data-lines-form] button[type=submit]")
    entry_number(page, "TRF")
    expect(page.locator(".alert-success").first).to_contain_text(
        re.compile(r"New defective tag: DEF-\d{4}\.")
    )
    marked = re.search(r"DEF-\d{4}", success_text(page)).group(0)

    step("file a complaint, then Record visit: 1 part given, 1 failed part collected")
    page.goto(f"{BASE}/complaints/new/")
    page.locator("#id_site-ts-control").click()
    site = page.locator("#id_site-ts-dropdown .option").first
    expect(site).to_be_visible()
    site.click()
    page.fill("#id_fault", "Walkthrough: 1 driver dead")
    page.click("#complaint-form button[type=submit]")
    expect(page).to_have_url(re.compile(r"/complaints/CMP-\d{4}/$"))
    cmp_no = page.locator(".page-title .code").inner_text().strip()
    page.locator(".page-header").get_by_role("link", name="Record visit").click()
    expect(page).to_have_url(re.compile(rf"/complaints/{cmp_no}/visit/$"))
    expect(page.locator("#id_location option", has_text="Defective store")).to_have_count(0)
    page.locator("#id_technicians-ts-control").click()
    tech = page.locator("#id_technicians-ts-dropdown .option").first
    expect(tech).to_be_visible()
    tech.click()
    page.keyboard.press("Escape")
    page.fill("#id_work_done", "Changed 1 driver (walkthrough)")
    pick_item(page, NEW, row=0)  # Parts given
    have = int(page.locator(".lines-table .avail b").first.inner_text())
    page.locator("input[name=part_qty]").fill(str(have + 1))
    expect(page.locator(".err").first).to_contain_text(f"Only {have} NOS available")
    page.click("form[data-lines-form] button[type=submit]")
    expect(page.locator("#form-error")).to_contain_text("Fix the highlighted lines")
    page.locator("input[name=part_qty]").fill("1")
    pick_item(page, NEW, row=1)  # Failed parts collected
    page.locator("input[name=col_qty]").fill("1")
    page.locator("input[name=col_batch]").fill("B2405")
    page.locator("input[name=col_pkd]").fill("2026-03")
    page.locator("input[name=col_fault]").fill("No output (walkthrough)")
    page.locator(".form-selectgroup-label", has_text="Material need to check").click()
    page.click("form[data-lines-form] button[type=submit]")
    expect(page).to_have_url(re.compile(rf"/complaints/{cmp_no}/$"))
    expect(page.locator(".alert-success").first).to_contain_text(
        re.compile(r"Visit VIS-\d{4} saved\. Parts given: OUT-\d{4}\. New defective tags: DEF-\d{4}\.")
    )
    collected = re.search(r"DEF-\d{4}", success_text(page)).group(0)
    row = page.locator("table.card-table tbody tr").first
    expect(row.locator("a.code", has_text=re.compile(r"^OUT-\d{4}$"))).to_be_visible()
    expect(row.locator("a.code", has_text=collected)).to_be_visible()

    step(f"clean-up: undo the parts given on {cmp_no}")
    row.get_by_role("button", name="Undo parts given").click()
    undo_modal = page.locator(".modal.show")
    expect(undo_modal).to_be_visible()
    undo_modal.locator("input[name=reason]").fill("walkthrough cleanup")
    undo_modal.locator("button[type=submit]").click()
    expect(page.locator(".alert-success").first).to_contain_text("The parts are back in stock.")

    complaint_status_flow(page, cmp_no)
    not_covered(page)
    search_service(page, cmp_no, collected)
    stock_columns(page)
    return_batch(page, marked, collected)
    service_exports(page)

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
    page.locator(
        "a.code", has_text=re.compile(rf"^{in_no}$")
    ).first.click()  # the item has two INs (see Mark)
    undo(page, in_no, "walkthrough cleanup")


def complaint_status_flow(page, cmp_no):
    step(f"{cmp_no}: a move the rules don't allow is refused")
    page.locator(".page-header button", has_text="Change status").click()
    modal = page.locator("#status-modal")
    expect(modal).to_be_visible()
    # the dialog offers only allowed moves, so post a disallowed one the way a stale or edited form would
    modal.locator("input[name=to]").first.evaluate("(r) => { r.value = 'CLOSED'; r.checked = true; }")
    modal.locator("button[type=submit]").click()
    expect(page.locator("#status-modal .alert-danger")).to_contain_text(
        "A complaint that is Material need to check can't move to Closed."
    )
    expect(page.locator(".page-title")).to_contain_text("Material need to check")

    step(f"{cmp_no}: Awaiting material, then Resolved, then Closed")
    for label in ("Awaiting material", "Resolved", "Closed"):
        change_status(page, label)
    expect(page.locator(".page-header")).not_to_contain_text("Record visit")


def not_covered(page):
    step("file another complaint and close it as Not covered")
    page.goto(f"{BASE}/complaints/new/")
    page.locator("#id_site-ts-control").click()
    site = page.locator("#id_site-ts-dropdown .option").first
    expect(site).to_be_visible()
    site.click()
    page.fill("#id_fault", "Walkthrough: customer will call back")
    page.click("#complaint-form button[type=submit]")
    expect(page).to_have_url(re.compile(r"/complaints/CMP-\d{4}/$"))
    page.click("text=Close as Not covered")
    expect(page.locator("#nc-modal")).to_be_visible()
    page.select_option("#nc-reason", label="Customer cancelled")
    page.click("#nc-modal button[type=submit]")
    expect(page.locator(".alert-success").first).to_contain_text("closed as Not covered")
    expect(page.locator(".page-title")).to_contain_text("Not covered")


def search_service(page, cmp_no, tag):
    step(f"global search finds {cmp_no} and {tag}")
    search(page, cmp_no.lower(), cmp_no)
    search(page, tag.lower(), tag)


def stock_columns(page):
    step(f"current stock shows the Defective store column for {NEW}; the total leaves it out")
    places, total, defective = stock_row(page, NEW)
    check(defective == 2, f"{NEW} should have 2 pieces in the Defective store, has {defective}")
    check("DEFECTIVE STORE" not in places, f"the Defective store is a stock column: {list(places)}")
    check(total == sum(places.values()) == 5, f"{NEW} total {total}, locations {places}: expected 5 good")


def return_batch(page, marked, collected):
    step(f"new return batch for {COMPANY} with {marked} and {collected}; a {OTHER} piece is refused")
    page.goto(f"{BASE}/defectives/batches/new/")
    ts_pick(page, "b-company", OTHER)
    page.wait_for_url(re.compile(r"company=\d+"))
    other_tag = page.locator("input[name=tag]").first.get_attribute("value")
    check(bool(other_tag), f"no {OTHER} piece in store; re-seed the demo data")
    ts_pick(page, "b-company", COMPANY)
    expect(page.locator(f"input[name=tag][value='{marked}']")).to_be_visible()
    for tag in (marked, collected):
        page.check(f"input[name=tag][value='{tag}']")
    page.fill("#b-note", "Walkthrough batch")
    page.locator("button", has_text="Create draft batch").click()
    rb_no = entry_number(page, "RB")
    page.fill("#add-tag", other_tag)
    page.locator("#add-tag ~ button[type=submit]").click()
    expect(page.locator("#add-err")).to_contain_text(f"{other_tag} is a {OTHER} piece")
    expect(page.locator(".page-title")).to_contain_text("Draft")

    step(f"dispatch {rb_no}")
    page.locator("button", has_text="Dispatch…").click()
    expect(page.locator("#dispatch-modal")).to_be_visible()
    page.fill("#d-courier", "DTDC")
    page.fill("#d-docket", f"WT{int(time.time())}")
    page.click("#dispatch-modal button[type=submit]")
    check(f"{rb_no} dispatched" in success_text(page), "the batch was not dispatched")
    expect(page.locator(".page-title")).to_contain_text("Dispatched")

    step(f"settle {marked} as Replaced (its Stock IN raises good stock), {collected} as Rejected (returned)")
    before = stock_row(page, NEW)[1]
    page.goto(f"{BASE}/defectives/batches/{rb_no}/")
    page.check(f"input[name=tag][value='{marked}']")
    page.locator(".form-selectgroup-label", has_text="Replaced").click()
    page.select_option("#s-loc", label="Vizag Office")
    page.locator("button[type=submit]", has_text="Settle ticked pieces").click()
    check("settled as Replaced" in success_text(page), "the replacement was not settled")
    expect(page.locator(".page-title")).to_contain_text("Partly settled")
    page.check(f"input[name=tag][value='{collected}']")
    page.locator(".form-selectgroup-label", has_text="Rejected (returned)").click()
    page.locator("button[type=submit]", has_text="Settle ticked pieces").click()
    check("Rejected (returned)" in success_text(page), "the rejection was not settled")
    expect(page.locator(".page-title")).to_contain_text("Settled")
    download(page, f"{BASE}/defectives/batches/{rb_no}/", "Export dispatch list", f"Return_Batch_{rb_no}_")
    after, defective = stock_row(page, NEW)[1:]
    check(after == before + 1, f"good stock of {NEW} went {before} -> {after}, expected +1")
    check(defective == 1, f"the rejected piece should be back in the Defective store ({defective})")


def service_exports(page):
    step("download the pending complaints and defective list reports")
    download(page, f"{BASE}/complaints/", "Pending complaints", "Pending_Complaints_")
    download(page, f"{BASE}/defectives/", "Defective list", "Defective_List_")


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

    step("an open complaint and its Record visit page on a phone")
    page.goto(f"{BASE}/complaints/list/")
    page.locator("a.code", has_text=re.compile(r"^CMP-\d{4}$")).first.click()
    expect(page.locator(".page-title")).to_contain_text("CMP-")
    record = page.locator(".page-header").get_by_role("link", name="Record visit")
    expect(record).to_be_visible()
    no_side_scroll(page, "the complaint page")
    page.screenshot(path=str(OUT / "screen-390-complaint.png"), full_page=True)
    record.click()
    expect(page).to_have_url(re.compile(r"/complaints/CMP-\d{4}/visit/$"))
    expect(page.locator("#id_work_done")).to_be_visible()
    no_side_scroll(page, "the visit page")
    page.screenshot(path=str(OUT / "screen-390-visit.png"), full_page=True)


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
