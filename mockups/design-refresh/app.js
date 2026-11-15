/* Design refresh mock: five real screens redrawn with one type scale and one card. Fake data, no backend. */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const view = $("#view");

  // ---------- small builders ----------
  const PILL = {
    "Not attended": ["st-alert", "alert-circle"], "Attended": ["st-neutral", "tool"], "Material need to check": ["st-neutral", "zoom-question"],
    "Awaiting material": ["st-wait", "hourglass"], "Resolved": ["st-ok", "circle-check"], "Closed": ["st-done", "lock"],
    "Urgent": ["st-alert", "urgent"], "High": ["st-wait", "arrow-up"], "Low": ["st-alert", "alert-triangle"],
    "Stock IN": ["k-in", "arrow-down-left"], "Stock OUT": ["k-out", "arrow-up-right"], "Transfer": ["st-neutral", "arrows-exchange"],
    "Adjustment": ["st-neutral", "adjustments-horizontal"], "Undo": ["st-alert", "arrow-back-up"], "Undone": ["st-done", "arrow-back-up"],
  };
  const pill = (word) => { const [c, i] = PILL[word] || ["st-neutral", "point"]; return `<span class="pill ${c}"><i class="ti ti-${i}" aria-hidden="true"></i>${word}</span>`; };
  const head = (title, o = {}) => `<div class="ph"><div>${o.crumb ? `<a class="crumb" href="${o.crumb[1]}"><i class="ti ti-chevron-left"></i> ${o.crumb[0]}</a>` : ""}
      <h1>${title}</h1>${o.meta ? `<div class="meta">${o.meta}</div>` : ""}</div>${o.actions ? `<div class="actions">${o.actions}</div>` : ""}</div>`;
  const cardHead = (title, o = {}) => `<div class="card-head"><h2>${title}</h2>${o.more ? `<a class="more" href="${o.more[1]}">${o.more[0]} <i class="ti ti-arrow-right"></i></a>` : ""}${o.caption ? `<div class="caption">${o.caption}</div>` : ""}</div>`;
  const stat = (label, fig, note, href, cls = "") => `<a class="stat ${cls}" href="${href}"><dl class="m-0"><dt>${label}</dt><dd class="fig">${fig}</dd><dd class="note">${note}</dd></dl></a>`;
  const th = (label, o = {}) => `<th class="${o.num ? "num " : ""}${o.cls || ""}">${o.sort === false ? label : `<a href="#" data-noop>${label}${o.sorted ? ` <i class="ti ti-arrow-${o.sorted}" aria-label="sorted"></i>` : ""}</a>`}${o.sub ? `<span class="sub">${o.sub}</span>` : ""}</th>`;
  const qty = (n) => (n ? n : `<span class="zero">0</span>`);
  const foot = (text, pages) => `<div class="card-foot"><span class="caption">${text}</span><nav class="pager" aria-label="Pages">${pages.map((p) => p === "…" ? `<span class="caption">…</span>` : `<a href="#" data-noop class="${p === 1 ? "on" : ""}">${p}</a>`).join("")}<a href="#" data-noop aria-label="Next page"><i class="ti ti-chevron-right"></i></a></nav></div>`;
  const select = (label, first, opts = []) => `<div class="field"><label>${label}</label><select class="form-select"><option>${first}</option>${opts.map((o) => `<option>${o}</option>`).join("")}</select></div>`;

  // ---------- sidebar ----------
  const NAV = [
    ["Overview", [["Dashboard", "layout-dashboard", "#dashboard"]]],
    ["Stock", [["Stock IN", "package-import", "#stock-in", "nav-in"], ["Stock OUT", "package-export", null, "nav-out"], ["Transfer", "arrows-exchange"], ["Adjust count", "adjustments-horizontal"]]],
    ["Reports", [["Current stock", "building-warehouse", "#stock"], ["Movements", "history"], ["Low stock", "alert-triangle", null, "", "6", true]]],
    ["Complaints", [["Dashboard", "message-report"], ["All complaints", "list-details", "#complaints", "", "20"], ["New complaint", "plus"], ["Sites", "building"], ["Technicians", "users"]]],
    ["Defectives", [["Dashboard", "recycle"], ["Pieces", "box", null, "", "47"], ["Mark defective", "alert-circle"], ["Return batches", "truck-return"]]],
    ["Setup", [["Items", "box"], ["Masters", "settings"]]],
    ["This mock", [["Style rules", "ruler-2", "#guide"]]],
  ];
  function drawNav(route) {
    $("#nav").innerHTML = NAV.map(([title, items]) => `<li class="nav-section">${title}</li>` + items.map(([label, icon, href, cls, count, alert]) =>
      `<li class="nav-item"><a class="nav-link${href === "#" + route || (route === "complaint" && href === "#complaints") ? " active" : ""}" href="${href || "#"}"${href ? "" : " data-noop"}>
        <span class="nav-link-icon ${cls || ""}"><i class="ti ti-${icon}"></i></span><span class="nav-link-title">${label}</span>${count ? `<span class="nav-count${alert ? " is-alert" : ""}">${count}</span>` : ""}</a></li>`).join("")).join("");
  }

  // ---------- screens ----------
  const ENTRIES = [
    ["REV-0001", "12-11-2026", "Undo", "Undo of OUT-0033", "EI09326 × 3", "Vizag Office", "Dr Reddys, Vizag", "Admin"],
    ["OUT-0033", "12-11-2026", "Stock OUT", "To site / customer", "EI09326 × 3", "Vizag Office", "Dr Reddys, Vizag", "Office", true],
    ["OUT-0032", "12-11-2026", "Stock OUT", "To technician", "3 items", "Vizag Office", "Apparao", "Office"],
    ["IN-0033", "11-11-2026", "Stock IN", "From supplier", "2 items", "Vizag Office", "Sri Sai Electricals", "Admin"],
    ["TRF-0007", "11-11-2026", "Transfer", "Marked defective", "HV-BATTEN-20W × 1", "Vizag Office → Defective store", "", "Office"],
    ["ADJ-0003", "10-11-2026", "Adjustment", "Physical count", "CABLE TIE 200MM × 1", "Vizag Office", "", "Admin"],
    ["OUT-0031", "10-11-2026", "Stock OUT", "To site / customer", "3 items", "Vizag Office", "Dr Reddys, Vizag", "Admin"],
  ];
  function dashboard() {
    view.innerHTML = head("Dashboard", { meta: "Saturday, 14-11-2026" }) + `<div class="stack">
      <div class="quick">
        <a class="btn btn-in" href="#stock-in"><div><i class="ti ti-package-import"></i>Stock IN</div><span>Material received</span></a>
        <a class="btn btn-out" href="#" data-noop><div><i class="ti ti-package-export"></i>Stock OUT</div><span>Material issued</span></a>
        <a class="btn btn-quiet" href="#" data-noop><div><i class="ti ti-arrows-exchange"></i>Transfer</div><span>Between locations</span></a>
        <a class="btn btn-quiet" href="#" data-noop><div><i class="ti ti-adjustments-horizontal"></i>Adjust</div><span>Correct a count</span></a>
      </div>
      <section class="card">${cardHead("Stock")}<div class="stats">
        ${stat("Active items", "31", "in the item list", "#stock")}
        ${stat("In stock, all locations", `860 <small>NOS</small>`, "plus 729 MTR · 1 PKT", "#stock")}
        ${stat("Low stock", `<i class="ti ti-alert-triangle" aria-hidden="true"></i> 6`, "at or below reorder level", "#stock", "is-alert")}
        ${stat("Movements, last 7 days", "27", "none today", "#dashboard")}
      </div></section>
      <section class="card">${cardHead("Service")}<div class="stats">
        ${stat("Open complaints", "20", `<i class="ti ti-alert-circle" aria-hidden="true"></i> 6 not attended yet`, "#complaints", "is-alert-note")}
        ${stat("Complaints visited, last 7 days", "3", "3 visits recorded", "#complaints")}
        ${stat("Defective pieces in store", "47", "not counted in stock", "#dashboard")}
        ${stat("Pieces with companies", "5", `<i class="ti ti-hourglass" aria-hidden="true"></i> awaiting their answer`, "#dashboard", "is-wait")}
      </div></section>
      <div class="cols">
        <section class="card">${cardHead("Stock IN and OUT", { caption: "Quantity per week (week ending), last 5 weeks, items counted in NOS", more: ["Table view", "#dashboard"] })}<div id="chart" class="chart-box" role="img" aria-label="Bar chart of stock in and stock out per week"></div></section>
        <section class="card">${cardHead("Stock by location")}<ul class="rows">
          ${[["Vizag Office", "858 NOS · 679 MTR · 1 PKT"], ["Kartika Class", "50 MTR"], ["Svkml", "1 NOS"], ["TV Shop", "1 NOS"]].map(([n, q]) => `<li><a href="#stock"><b>${n}</b><span class="qty">${q}</span><i class="ti ti-chevron-right" aria-hidden="true"></i></a></li>`).join("")}
        </ul></section>
      </div>
      <section class="card">${cardHead("Recent entries", { more: ["All movements", "#dashboard"] })}<div class="table-responsive mt-2"><table class="table">
        <thead><tr>${["Entry", "Date", "Type", "Details", "Items", "Location", "Supplier / issued to", "By"].map((h) => th(h, { sort: false })).join("")}</tr></thead>
        <tbody>${ENTRIES.map(([no, d, type, det, items, loc, party, by, undone]) => `<tr class="${undone ? "undone" : ""}">
          <td><a class="code" href="#" data-noop>${no}</a></td><td class="text-nowrap"><span class="strike">${d}</span></td><td>${pill(type)}${undone ? " " + pill("Undone") : ""}</td>
          <td><span class="strike">${det}</span></td><td class="nowrap"><span class="strike">${items.replace(/^(\S+( \S+)*) × /, '<span class="code">$1</span> × ')}</span></td><td><span class="strike">${loc}</span></td><td><span class="strike">${party || `<span class="zero">–</span>`}</span></td><td>${by}</td></tr>`).join("")}</tbody>
      </table></div></section></div>`;
    new ApexCharts($("#chart"), {
      chart: { type: "bar", height: 250, toolbar: { show: false }, animations: { enabled: false }, fontFamily: "inherit" },
      series: [{ name: "Stock IN", data: [75, 68, 64, 50, 19] }, { name: "Stock OUT", data: [6, 15, 27, 18, 27] }],
      colors: ["#2a78d6", "#eb6834"], plotOptions: { bar: { columnWidth: "45%", borderRadius: 2 } }, dataLabels: { enabled: false },
      xaxis: { categories: innerWidth < 576 ? ["17 Oct", "24 Oct", "31 Oct", "7 Nov", "14 Nov"] : ["11–17 Oct", "18–24 Oct", "25–31 Oct", "1–7 Nov", "8–14 Nov"], axisTicks: { show: false }, labels: { style: { fontSize: "12px", colors: "#5b6b80" } } },
      yaxis: { labels: { style: { fontSize: "12px", colors: "#5b6b80" } } }, grid: { borderColor: "#e3e7ee", strokeDashArray: 3 },
      legend: { position: "top", horizontalAlign: "left", fontSize: "12px", markers: { size: 5 } }, tooltip: { style: { fontSize: "12px" } },
    }).render();
  }

  const STOCK = [
    ["15WATT (190MA)", "Driver", "LED driver 15W 190mA (generic)", "", "Wipro Lighting", [0, 0, 0, 23], 23, "NOS", false, 1],
    ["18WATT DRIVERS", "Driver", "LED driver 18W (generic)", "", "Wipro Lighting", [0, 0, 0, 29], 29, "NOS", false, 0],
    ["BULKHEAD 12W", "Complete fitting", "Bulkhead fitting 12W", "Bulkhead", "Wipro Lighting", [0, 0, 0, 21], 21, "NOS", false, 0],
    ["CABLE TIE 200MM", "Accessory", "Cable ties 200mm (pack of 100)", "", "Lakshmi Traders", [0, 0, 0, 1], 1, "PKT", true, 0],
    ["EI06006", "PCB / LED module", "LED module", "LD80-171-XXX-60-XX · Downlight", "Wipro Lighting", [0, 0, 1, 0], 1, "NOS", true, 2],
    ["EI08437", "PCB / LED module", "LED module", "LD81-171-XXX-60-XX · Downlight", "Wipro Lighting", [0, 0, 0, 23], 23, "NOS", false, 1],
    ["EI09326", "PCB / LED module", "LED module", "LL20-111-XXX-65AL · Linear / batten", "Wipro Lighting", [0, 0, 0, 8], 8, "NOS", true, 3],
    ["FTS-KC-60-57K", "PCB / LED module", "LED PCB 5700K", "LF20-102-060-57-G3 · Flood light", "Wipro Lighting", [0, 0, 0, 225], 225, "NOS", false, 4],
    ["FX-MODSW-6A", "Switch", "Modular switch 6A", "", "Finolex Cables", [0, 0, 0, 9], 9, "NOS", true, 3],
    ["HV-BATTEN-20W", "Complete fitting", "LED batten 20W", "Linear / batten", "Havells", [0, 0, 0, 5], 5, "NOS", false, 3],
  ];
  function stock() {
    view.innerHTML = head("Current stock", { actions: `<a class="btn btn-quiet" href="#" data-noop><i class="ti ti-file-spreadsheet"></i>Export to Excel</a>` }) + `<section class="card">
      <form class="filters">${select("Location", "All locations", ["Vizag Office", "Kartika Class", "Svkml", "TV Shop"])}${select("Spare type", "All types", ["Driver", "PCB / LED module", "Complete fitting"])}${select("Company", "All companies", ["Wipro Lighting", "Havells", "Finolex Cables"])}
        <div class="field grow"><label for="q1">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span><input id="q1" type="search" class="form-control" placeholder="Code, old spelling, description, fitting"></div></div>
        <label class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox"><span class="form-check-label">Only low stock</span></label></form>
      <div class="table-responsive"><table class="table"><thead><tr>${th("Item", { sorted: "up" })}${th("Description")}${th("Company")}
        ${["Kartika Class", "Svkml", "TV Shop", "Vizag Office"].map((l) => th(l, { num: true })).join("")}${th("Total", { num: true })}${th("Defective store", { num: true, cls: "col-def", sub: "not counted" })}</tr></thead>
        <tbody>${STOCK.map(([code, type, desc, sub, co, per, total, unit, low, def]) => `<tr><td><a class="code" href="#" data-noop>${code}</a><span class="sub">${type}</span></td>
          <td>${desc}${sub ? `<span class="sub">${sub}</span>` : ""}</td><td>${co}</td>${per.map((n) => `<td class="num">${qty(n)}</td>`).join("")}
          <td class="num">${low ? pill("Low") + " " : ""}<b>${total}</b> <span class="caption">${unit}</span></td><td class="num col-def">${def ? `<a href="#" data-noop>${def}</a>` : qty(0)}</td></tr>`).join("")}</tbody></table></div>
      ${foot("Showing 1–10 of 31", [1, 2, "…", 4])}</section>`;
  }

  const COMPLAINTS = [
    ["CMP-0026", "14-11-2026", "BARC", "Visakhapatnam", "Havells", "", "MCB not resetting in pump house", 2, "", "Normal", "Not attended", 0],
    ["CMP-0025", "13-11-2026", "Dr Reddys", "Visakhapatnam", "Wipro Lighting", "", "Well glass fittings tripping MCB", 3, "", "High", "Not attended", 1],
    ["CMP-0024", "12-11-2026", "Sanvira Industries", "Visakhapatnam", "Finolex Cables", "", "Wiring heating near main DB", 1, "", "Urgent", "Not attended", 2],
    ["CMP-0023", "11-11-2026", "Laurus Labs Unit-4", "Visakhapatnam", "Wipro Lighting", "", "Downlights dim in QC lab", 6, "", "Normal", "Not attended", 3],
    ["CMP-0022", "09-11-2026", "Vaishaki Bio Marine", "Visakhapatnam", "Wipro Lighting", "WL/AP/25520", "Flood light lens cracked", 2, "Ramu", "Normal", "Attended", 5],
    ["CMP-0021", "08-11-2026", "Laurus Labs Unit-2", "Visakhapatnam", "Finolex Cables", "", "Modular switches burnt in admin block", 3, "Ramu", "Normal", "Attended", 6],
    ["CMP-0020", "07-11-2026", "Master Minds", "Guntur", "Wipro Lighting", "WL/AP/25488", "Downlight LED module failed", 1, "Jagadeesh", "Normal", "Resolved", 7],
    ["CMP-0019", "05-11-2026", "VN Energies", "Vijayawada", "Sri Sai Electricals", "SSE-1182", "Petrol pump canopy lights not working", 4, "Apparao", "Normal", "Resolved", 9],
    ["CMP-0018", "04-11-2026", "IIT", "Tirupati", "Wipro Lighting", "WL/AP/25455", "Linear fittings LED module burnt", 8, "Srinuvas", "Normal", "Attended", 10],
    ["CMP-0017", "03-11-2026", "Dr Reddys", "Visakhapatnam", "Havells", "HV-C-78020", "LED battens failed in canteen", 4, "Ramu", "Normal", "Material need to check", 11],
  ];
  function complaints() {
    const tabs = [["Open", 20], ["Not attended", 6], ["Attended", 4], ["Material need to check", 4], ["Awaiting material", 2], ["Resolved", 4], ["Closed", 5], ["Not covered", 1], ["All", 26]];
    view.innerHTML = head("All complaints", { actions: `<a class="btn btn-quiet" href="#" data-noop><i class="ti ti-file-spreadsheet"></i>Export to Excel</a><a class="btn btn-primary" href="#" data-noop><i class="ti ti-plus"></i>New complaint</a>` }) + `<section class="card">
      <nav class="tabs" aria-label="Status">${tabs.map(([t, n], i) => `<a href="#" data-noop class="${i ? "" : "on"}">${t}<i>${n}</i></a>`).join("")}</nav>
      <form class="filters">${select("Company", "All companies", ["Wipro Lighting", "Havells"])}${select("City", "All cities", ["Visakhapatnam", "Guntur"])}${select("Technician", "Anyone", ["Ramu", "Apparao"])}${select("Age", "Any age", ["Over 15 days"])}
        <div class="field grow"><label for="q2">Search</label><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span><input id="q2" type="search" class="form-control" placeholder="Complaint no., company ref, site, fault"></div></div></form>
      <div class="table-responsive"><table class="table"><thead><tr>${th("Complaint")}${th("Reported", { sorted: "down" })}${th("Site")}${th("Company")}${th("Fault", { sort: false })}${th("Technician")}${th("Status")}${th("Open for", { num: true })}</tr></thead>
        <tbody>${COMPLAINTS.map(([no, d, site, city, co, ref, fault, n, tech, prio, st, age]) => `<tr><td><a class="code" href="#complaint">${no}</a></td><td class="text-nowrap">${d}</td>
          <td><a href="#" data-noop>${site}</a><span class="sub">${city}</span></td><td>${co}${ref ? `<span class="sub">${ref}</span>` : ""}</td>
          <td>${prio !== "Normal" ? pill(prio) + " " : ""}${fault}<span class="sub">${n} fitting${n > 1 ? "s" : ""} affected</span></td>
          <td class="nowrap">${tech || `<span class="muted">Not assigned</span>`}</td><td>${pill(st)}</td><td class="num">${age} day${age === 1 ? "" : "s"}</td></tr>`).join("")}</tbody></table></div>
      ${foot("Showing 1–10 of 20", [1, 2])}</section>`;
  }

  function stockIn() {
    view.innerHTML = head("Stock IN", { meta: "Material received at a location" }) + `<form class="card" onsubmit="return false">
      <div class="card-sec card-pad"><h2 class="mb-3" style="font-size:var(--t-title)">Details</h2><div class="fields">
        <div class="field wide"><label class="req">Received from</label><div class="seg" role="radiogroup">
          <label><input type="radio" name="sub" checked><span>Supplier</span></label><label><input type="radio" name="sub"><span>Returned unused from site</span></label><label><input type="radio" name="sub"><span>Opening stock</span></label></div></div>
        <div class="field"><label class="req" for="d1">Date</label><input id="d1" type="date" class="form-control" value="2026-11-14"></div>
        <div class="field"><label class="req" for="s1">Supplier / company</label><select id="s1" class="form-select"><option>Choose…</option><option>Wipro Lighting</option><option>Havells</option></select><div class="hint">Type a new name to add it</div></div>
        <div class="field"><label class="req" for="l1">Into location</label><select id="l1" class="form-select"><option>Choose…</option><option>Vizag Office</option><option>TV Shop</option></select></div>
        <div class="field"><label for="r1">DC / bill no.</label><input id="r1" class="form-control" placeholder="e.g. DC 4512"></div>
        <div class="field wide"><label for="n1">Remarks</label><input id="n1" class="form-control" placeholder="Optional"></div>
      </div></div>
      <div class="card-sec card-pad"><h2 class="mb-2" style="font-size:var(--t-title)">Items</h2>
        <table class="table lines"><thead><tr><th class="c-n" style="width:2rem">#</th><th>Item</th><th style="width:9rem">Quantity</th><th style="width:11rem">Batch code</th><th style="width:11rem">PKD (packed)</th><th style="width:2.5rem"></th></tr></thead>
          <tbody>${[["EI09326 · LED module · LL20-111-XXX-65AL", 12, "B2405", "2026-08-01"], ["", "", "", ""]].map(([item, q, b, pkd], i) => `<tr><td class="c-n muted">${i + 1}</td>
            <td class="c-item" data-label="Item"><select class="form-select"><option>${item || "Type code, old spelling or description…"}</option></select></td>
            <td data-label="Quantity"><div class="input-group"><input type="number" min="1" class="form-control" value="${q}" placeholder="0"><span class="input-group-text caption">${item ? "NOS" : "—"}</span></div></td>
            <td data-label="Batch code"><input class="form-control" value="${b}" placeholder="e.g. B2405"></td><td data-label="PKD (packed)"><input type="date" class="form-control" value="${pkd}"></td>
            <td><button type="button" class="icon-btn" aria-label="Remove line ${i + 1}"><i class="ti ti-trash"></i></button></td></tr>`).join("")}</tbody></table>
        <button type="button" class="btn btn-text mt-2"><i class="ti ti-plus"></i>Add another item</button></div>
      <div class="card-foot"><span class="caption">1 item · 12 NOS</span><div class="ms-auto d-flex gap-2"><a class="btn btn-quiet" href="#dashboard">Cancel</a><button class="btn btn-in" type="submit">Save Stock IN</button></div></div>
    </form>`;
  }

  function complaint() {
    view.innerHTML = head(`<span class="code">CMP-0022</span> ${pill("Attended")}`, { crumb: ["All complaints", "#complaints"], meta: "Reported 09-11-2026 · open for 5 days · Wipro Lighting",
      actions: `<button class="btn btn-quiet" type="button">Close as not covered</button><button class="btn btn-quiet" type="button">Change status</button><button class="btn btn-primary" type="button"><i class="ti ti-clipboard-check"></i>Record visit</button>` }) + `<div class="stack"><div class="cols">
      <section class="card">${cardHead("Details")}<div class="card-pad"><dl class="facts">
        <div><dt>Site</dt><dd><a href="#" data-noop>Vaishaki Bio Marine</a></dd></div><div><dt>City</dt><dd>Visakhapatnam</dd></div><div><dt>Priority</dt><dd>Normal</dd></div>
        <div><dt>Contact</dt><dd>S. Prasad</dd></div><div><dt>Phone</dt><dd><a href="tel:9848012345">98480 12345</a></dd></div><div><dt>Technician</dt><dd>Ramu</dd></div>
        <div><dt>Company</dt><dd>Wipro Lighting</dd></div><div><dt>Company complaint no.</dt><dd class="code">WL/AP/25520</dd></div><div><dt>Fittings affected</dt><dd>2</dd></div>
        <div class="wide"><dt>Fault</dt><dd>Flood light lens cracked</dd></div></dl></div></section>
      <section class="card">${cardHead("Status history")}<div class="card-pad"><ol class="tl">
        <li class="now"><b>Attended</b><div class="caption">10-11-2026 · Office · visit VIS-0019</div></li>
        <li><b>Not attended</b><div class="caption">09-11-2026 · Office · complaint filed</div></li></ol></div></section></div>
      <section class="card">${cardHead("Visits")}<div class="table-responsive mt-2"><table class="table"><thead><tr>${["Visit", "Technician", "Work done", "Parts given", "Failed parts collected", "Status after"].map((h) => th(h, { sort: false })).join("")}</tr></thead>
        <tbody><tr><td><span class="code">VIS-0019</span><span class="sub">10-11-2026</span></td><td>Ramu</td><td>Checked both fittings. Lens cracked on 2 flood lights, replacement lens needed.</td>
          <td><span class="zero">–</span></td><td><span class="zero">–</span></td><td>${pill("Attended")}</td></tr></tbody></table></div></section></div>`;
  }

  function guide() {
    const row = (name, use, style, sample) => `<tr><td>${name}<br>${use}</td><td style="${style}">${sample}</td></tr>`;
    view.innerHTML = head("Style rules", { meta: "What every screen follows after the refresh. This page becomes the Typography and Layout sections of DESIGN.md." }) + `<div class="stack">
      <section class="card">${cardHead("One type scale", { caption: "Five sizes and two weights. Today the app renders 12 sizes and 4 weights." })}<div class="card-pad"><table class="spec">
        ${row("Figure · 28px", "dashboard numbers", "font-size:var(--t-figure);font-weight:600", "860 NOS")}
        ${row("Page · 20px", "page title, once per page", "font-size:var(--t-page);font-weight:600", "Current stock")}
        ${row("Title · 16px", "card titles, big buttons", "font-size:var(--t-title);font-weight:600", "Recent entries")}
        ${row("Body · 14px", "tables, forms, menus", "", "LED driver 15W 190mA (generic) · <b>strong for emphasis</b> · <span class='code'>EI09326</span> codes in monospace")}
        ${row("Caption · 12px", "labels, table headings, hints", "font-size:var(--t-caption);color:var(--muted)", "Reported 09-11-2026 · open for 5 days")}
      </table></div></section>
      <section class="card">${cardHead("One card", { caption: "White, hairline border, 8px corners, no shadow, 20px inset. Title in 16px, optional link on the right. Nothing else counts as a card." })}
        <div class="card-pad">Tables, forms, numbers and charts all sit in this same card. Sections inside a card are split by a hairline, not by a second card style, tinted band or icon.</div></section>
      <section class="card">${cardHead("Buttons and status", { caption: "One filled button per page. Colour only where it means something, always with an icon or a word." })}<div class="card-pad stack">
        <div class="swatches"><button class="btn btn-primary" type="button">Main action</button><button class="btn btn-in" type="button">Stock IN</button><button class="btn btn-out" type="button">Stock OUT</button><button class="btn btn-quiet" type="button">Everything else</button><button class="btn btn-text" type="button">Link action <i class="ti ti-arrow-right"></i></button></div>
        <div class="swatches">${["Not attended", "Awaiting material", "Resolved", "Attended", "Closed", "Stock IN", "Stock OUT", "Low"].map(pill).join("")}</div></div></section>
      <section class="card">${cardHead("What was removed")}<div class="card-pad"><table class="ba"><thead><tr><th></th><th>Today</th><th>After</th></tr></thead><tbody>
        <tr><td>Dashboard numbers</td><td>8 separate tiles, each with an icon in a tinted circle</td><td>2 cards of 4 plain numbers. On a phone: 2 short grids instead of 8 stacked tiles</td></tr>
        <tr><td>Type</td><td>12 sizes, 4 weights, capital-letter table headings</td><td>5 sizes, 2 weights, normal-case headings</td></tr>
        <tr><td>Cards</td><td>6 looks: tile, header-with-line, filter header, grey footer, chips, tinted panel</td><td>1 card</td></tr>
        <tr><td>Icons</td><td>On some page titles, every card title, every list row</td><td>Only in the menu, on buttons and inside status pills</td></tr>
        <tr><td>Page heading</td><td>Section word above every title (“REPORTS”), repeating the menu</td><td>Title only. Detail pages get a “back to list” link instead</td></tr>
        <tr><td>Buttons</td><td>Up to 3 outlined or filled buttons competing; “Record visit” shown twice</td><td>One filled button, the rest quiet, no repeats</td></tr>
        <tr><td>Complaint page</td><td>3 chips + 10 capital-letter labels</td><td>One line under the title + a 3-column fact grid</td></tr>
        <tr><td>Tables</td><td>Striped rows, footnotes explaining colours</td><td>Hairlines only. Low stock says “Low” in the row, so the footnote goes</td></tr>
        <tr><td>Complaints list</td><td>9 columns; Priority says “Normal” on most rows</td><td>8 columns. High / Urgent shows as a pill beside the fault; Normal shows nothing. Sorting by priority becomes a filter (your call)</td></tr>
        <tr><td>Unchanged</td><td colspan="2">Navy &amp; Amber palette, IN blue / OUT orange, status pill tints, the menu, every form field, large quick-action buttons, how every screen works</td></tr>
      </tbody></table></div></section></div>`;
  }

  // ---------- router + mock controls ----------
  const ROUTES = { dashboard: [dashboard, "dashboard.png"], stock: [stock, "stock.png"], complaints: [complaints, "complaints-list.png"], "stock-in": [stockIn, "stock-in.png"], complaint: [complaint, "complaint.png"], guide: [guide, null] };
  function go() {
    const route = ROUTES[location.hash.slice(1)] ? location.hash.slice(1) : "dashboard";
    drawNav(route); ROUTES[route][0](); window.scrollTo(0, 0);
    $("#show-before").hidden = !ROUTES[route][1]; $("#show-before").dataset.img = ROUTES[route][1] || "";
    const menu = $("#sidebar-menu"); if (menu.classList.contains("show")) menu.classList.remove("show");
  }
  window.addEventListener("hashchange", go);
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-noop]"); if (!a) return;
    e.preventDefault(); document.querySelectorAll(".toast-note").forEach((n) => n.remove());
    const note = Object.assign(document.createElement("div"), { className: "toast-note", textContent: "Not drawn in this mock. It will follow the same rules." });
    note.setAttribute("role", "status"); document.body.append(note); setTimeout(() => note.remove(), 2200);
  });
  document.querySelectorAll("[data-font]").forEach((b) => b.addEventListener("click", () => {
    document.body.classList.toggle("font-plex", b.dataset.font === "plex");
    document.querySelectorAll("[data-font]").forEach((x) => x.classList.toggle("on", x === b));
    try { localStorage.setItem("refresh-font", b.dataset.font); } catch (_) { /* private window */ }
  }));
  try { if (localStorage.getItem("refresh-font") === "plex") $('[data-font="plex"]').click(); } catch (_) { /* private window */ }
  $("#show-before").addEventListener("click", (e) => { $("#before-img").src = "before/" + e.currentTarget.dataset.img; $("#before-dialog").showModal(); });
  $("#before-close").addEventListener("click", () => $("#before-dialog").close());
  go();
})();
