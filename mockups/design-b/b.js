/* Direction B (Bold and graphic): the five key screens. Fake data, no backend.
   Every screen reads in the same order: the main actions, then what needs attention, then related things grouped. */
(function () {
  "use strict";
  const stage = document.getElementById("stage");
  const ic = (n) => `<i class="ti ti-${n}" aria-hidden="true"></i>`;

  const WEEKS = [["11–17 Oct", 75, 6], ["18–24 Oct", 68, 15], ["25–31 Oct", 64, 27], ["1–7 Nov", 50, 18], ["8–14 Nov", 19, 27]];
  const PLACES = [["Vizag Office", "858 NOS · 679 MTR · 1 PKT"], ["Kartika Class", "50 MTR"], ["Svkml", "1 NOS"], ["TV Shop", "1 NOS"]];
  const ENTRIES = [
    ["OUT-0032", "12-11-2026", "Stock OUT", "3 items", "to technician Apparao", "Vizag Office", "Office"],
    ["IN-0033", "11-11-2026", "Stock IN", "2 items", "from Sri Sai Electricals", "Vizag Office", "Admin"],
    ["TRF-0007", "11-11-2026", "Transfer", "HV-BATTEN-20W × 1", "marked defective", "Vizag Office → Defective store", "Office"],
    ["ADJ-0003", "10-11-2026", "Adjustment", "CABLE TIE 200MM × 1", "physical count", "Vizag Office", "Admin"],
    ["OUT-0031", "10-11-2026", "Stock OUT", "3 items", "to Dr Reddys, Vizag", "Vizag Office", "Admin"],
  ];
  const COMPLAINTS = [
    ["CMP-0026", "14-11-2026", "BARC", "Visakhapatnam", "Havells", "MCB not resetting in pump house", 2, "", "", "Not attended", 0],
    ["CMP-0025", "13-11-2026", "Dr Reddys", "Visakhapatnam", "Wipro Lighting", "Well glass fittings tripping MCB", 3, "", "High", "Not attended", 1],
    ["CMP-0024", "12-11-2026", "Sanvira Industries", "Visakhapatnam", "Finolex Cables", "Wiring heating near main DB", 1, "", "Urgent", "Not attended", 2],
    ["CMP-0022", "09-11-2026", "Vaishaki Bio Marine", "Visakhapatnam", "Wipro Lighting", "Flood light lens cracked", 2, "Ramu", "", "Attended", 5],
    ["CMP-0020", "07-11-2026", "Master Minds", "Guntur", "Wipro Lighting", "Downlight LED module failed", 1, "Jagadeesh", "", "Resolved", 7],
    ["CMP-0010", "23-10-2026", "Sanvira Industries", "Visakhapatnam", "Wipro Lighting", "High bay drivers failing in store", 5, "Apparao", "", "Awaiting material", 22],
    ["CMP-0006", "15-10-2026", "NSL Textiles", "Guntur", "Wipro Lighting", "Street light poles not glowing", 4, "", "", "Not attended", 30],
  ];
  const STOCK = [
    ["15WATT (190MA)", "Driver", "LED driver 15W 190mA (generic)", "Wipro Lighting", [0, 0, 0, 23], 23, "NOS", false, 1],
    ["18WATT DRIVERS", "Driver", "LED driver 18W (generic)", "Wipro Lighting", [0, 0, 0, 29], 29, "NOS", false, 0],
    ["CABLE TIE 200MM", "Accessory", "Cable ties 200mm (pack of 100)", "Lakshmi Traders", [0, 0, 0, 1], 1, "PKT", true, 0],
    ["EI06006", "PCB / LED module", "LED module · LD80-171-XXX-60-XX", "Wipro Lighting", [0, 0, 1, 0], 1, "NOS", true, 2],
    ["EI09326", "PCB / LED module", "LED module · LL20-111-XXX-65AL", "Wipro Lighting", [0, 0, 0, 8], 8, "NOS", true, 3],
    ["FTS-KC-60-57K", "PCB / LED module", "LED PCB 5700K · LF20-102-060-57-G3", "Wipro Lighting", [0, 0, 0, 225], 225, "NOS", false, 4],
    ["FX-MODSW-6A", "Switch", "Modular switch 6A", "Finolex Cables", [0, 0, 0, 9], 9, "NOS", true, 3],
    ["HV-BATTEN-20W", "Complete fitting", "LED batten 20W", "Havells", [0, 0, 0, 5], 5, "NOS", false, 3],
  ];
  const ATTN = [
    ["alert", "alert-circle", 6, "Complaints nobody has attended", "Oldest: NSL Textiles, Guntur, 30 days ago", "Assign a technician", "Complaints", "list"],
    ["alert", "clock", 8, "Complaints open for more than 15 days", "Oldest: BARC, 35 days, resolved but not closed", "See them", "Complaints", "list"],
    ["alert", "alert-triangle", 6, "Items low on stock", "EI06006 and CABLE TIE 200MM are down to 1", "See what to order", "Stock", "stock"],
    ["wait", "hourglass", 5, "Defective pieces waiting on a company", "Wipro Lighting, batch RB-0001, sent 24 days ago", "Record their answer", "Defectives", ""],
  ];
  const TABS = [["Open", 20], ["Not attended", 6], ["Attended", 4], ["Material need to check", 4], ["Awaiting material", 2], ["Resolved", 4]];
  const PILL = { "Not attended": ["st-alert", "alert-circle"], "Attended": ["st-neutral", "tool"], "Awaiting material": ["st-wait", "hourglass"], "Resolved": ["st-ok", "circle-check"],
    "Urgent": ["st-alert", "urgent"], "High": ["st-wait", "arrow-up"], "Stock IN": ["k-in", "arrow-down-left"], "Stock OUT": ["k-out", "arrow-up-right"],
    "Transfer": ["st-neutral", "arrows-exchange"], "Adjustment": ["st-neutral", "adjustments-horizontal"], "Low": ["st-alert", "alert-triangle"] };
  const pill = (w) => { const [c, i] = PILL[w] || ["st-neutral", "point"]; return `<span class="pill ${c}">${ic(i)}${w}</span>`; };
  const days = (n) => `${n} day${n === 1 ? "" : "s"}`;
  const go = (s) => (s ? `href="#${s}"` : 'href="#" data-noop');
  const qty = (n) => (n ? n : `<span class="zero">0</span>`);
  const fld = (label, control, o = {}) => `<label class="fld ${o.cls || ""}"><span>${label}${o.req ? " <i>*</i>" : ""}</span>${control}${o.hint ? `<span class="hint ${o.need ? "need" : ""}">${o.hint}</span>` : ""}</label>`;
  const sel = (first, opts = [], cls = "") => `<select class="inp ${cls}"><option>${first}</option>${opts.map((o) => `<option>${o}</option>`).join("")}</select>`;
  const stockActs = `<a class="btn in" ${go("stock-in")}>${ic("arrow-down-left")}Stock IN</a><a class="btn out" ${go("")}>${ic("arrow-up-right")}Stock OUT</a>`;

  // ---------- shell: dark top bar, section tabs under the title ----------
  const NAV = [["Home", "home"], ["Stock", "stock"], ["Complaints", "list", 20], ["Defectives", ""], ["Reports", ""], ["Setup", ""]];
  const SUB = {
    Stock: [["Current stock", "stock"], ["Movements", ""], ["Low stock", "", 6], ["Items", ""]],
    Complaints: [["All complaints", "list"], ["Sites", ""], ["Technicians", ""]],
  };
  function shell(section, screen, hero, body) {
    const sub = SUB[section] && screen ? `<nav class="b-sub" aria-label="${section}">${SUB[section].map(([l, s, n]) => `<a ${go(s)} class="${s === screen ? "on" : ""}">${l}${n ? `<em>${n}</em>` : ""}</a>`).join("")}</nav>` : "";
    return `<div class="d dir-b"><div class="b-top"><nav class="b-nav" aria-label="Main"><div class="b-brand"><i class="ti ti-bulb"></i>SVKML</div>
      ${NAV.map(([l, s, n]) => `<a ${go(s)} class="${l === section ? "on" : ""}">${l}${n ? `<em>${n}</em>` : ""}</a>`).join("")}
      <div class="right"><a ${go("")} aria-label="Search">${ic("search")}</a><a ${go("stock")} aria-label="6 items low on stock">${ic("bell")}</a><a ${go("")}>Office</a></div></nav>
      <div class="b-hero">${hero}${sub}</div></div><main class="b-body">${body}</main></div>`;
  }

  // ---------- 1. Dashboard ----------
  const ages = `<div class="b-age">${[["0–2 days", 3], ["3–7 days", 4], ["8–15 days", 5], ["Over 15 days", 8, 1]].map(([l, n, late]) => `<div class="${late ? "late" : ""}"><span>${l}</span><i style="width:${n / 8 * 100}%"></i><b>${n}</b></div>`).join("")}</div>`;
  const home = () => shell("Home", "home", `<div><h1>Saturday, 14 November</h1><p>4 things need attention today.</p></div>
      <div class="acts wide">${stockActs}<a class="btn main" ${go("")}>${ic("plus")}New complaint</a><a class="btn main" ${go("")}>${ic("clipboard-check")}Record visit</a>
        <span class="sep"></span><a class="btn" ${go("")}>Transfer</a><a class="btn" ${go("")}>Adjust</a></div>`, `
    <div class="b-blocks">${ATTN.map(([cls, i, n, t, sub, btn, grp, to]) => `<a class="b-block attn ${grp === "Stock" ? "amber" : "card"} ${cls}" ${go(to)}><span class="lbl">${ic(i)} ${grp}</span><div class="fig">${n}</div><b>${t}</b><span class="cap">${sub}</span><span class="go">${btn} →</span></a>`).join("")}</div>
    <section class="card b-card"><h2>Stock <a ${go("stock")}>Current stock</a></h2><div class="b-stock">
      <a class="b-block in" ${go("")}><span class="lbl">Stock IN this week</span><div class="b-spark">${WEEKS.map((w) => `<i style="height:${w[1] / 0.75}%"></i>`).join("")}</div><div class="fig">19 <small>NOS</small></div><span class="cap">50 the week before</span></a>
      <a class="b-block out" ${go("")}><span class="lbl">Stock OUT this week</span><div class="b-spark">${WEEKS.map((w) => `<i style="height:${w[2] / 0.27}%"></i>`).join("")}</div><div class="fig">27 <small>NOS</small></div><span class="cap">18 the week before</span></a>
      <a class="b-block panel" ${go("stock")}><span class="lbl">In stock now</span><div class="fig">860 <small>NOS</small></div><span class="cap">plus 729 MTR · 1 PKT · 31 active items</span></a>
      <div class="b-block panel"><span class="lbl">By location</span><div class="b-locs">${PLACES.map(([n, q]) => `<a ${go("stock")}><b>${n}</b><span class="cap">${q}</span></a>`).join("")}</div></div>
    </div></section>
    <div class="b-two">
      <section class="card b-card"><h2>Complaints <a ${go("list")}>All complaints</a></h2>
        <div class="b-headline"><div class="fig">20</div><div><b>open</b><div class="cap">4 resolved, ready to close · 3 visited this week</div></div></div>
        <div class="b-seg" role="img" aria-label="Open complaints by status"><i style="flex:6;background:#d63939"></i><i style="flex:4;background:#475569"></i><i style="flex:4;background:#94a3b8"></i><i style="flex:2;background:#f5b301"></i><i style="flex:4;background:#2e9e4f"></i></div>
        <div class="legend wrap"><span><i style="background:#d63939"></i>6 not attended</span><span><i style="background:#475569"></i>4 attended</span><span><i style="background:#94a3b8"></i>4 material to check</span><span><i style="background:#f5b301"></i>2 awaiting material</span><span><i style="background:#2e9e4f"></i>4 resolved</span></div>
        <p class="cap" style="margin:22px 0 12px">Open complaints by age</p>${ages}</section>
      <section class="card b-card"><h2>Defective pieces <a ${go("")}>All pieces</a></h2><div class="b-flow">
        <a ${go("")}><b>47</b>in the Defective store</a><a ${go("")}><b>4</b>in a draft batch</a><a ${go("")} class="wait"><b>5</b>with companies, oldest 24 days</a><a ${go("")}><b>4</b>answered, last 90 days</a></div>
        <p class="cap" style="margin-top:14px">Defective pieces are never counted in stock.</p></section>
    </div>
    <section class="card b-card"><h2>Recent entries <a ${go("")}>All movements</a></h2><div class="scroll"><table class="t"><thead><tr><th>Entry</th><th>Date</th><th>Type</th><th>Items</th><th>Location</th><th>By</th></tr></thead>
      <tbody>${ENTRIES.map(([no, d, type, items, what, loc, by]) => `<tr><td><a class="code" ${go("")}>${no}</a></td><td>${d}</td><td>${pill(type)}</td><td>${items}<span class="sub">${what}</span></td><td>${loc}</td><td>${by}</td></tr>`).join("")}</tbody></table></div></section>`);

  // ---------- 2. Current stock ----------
  const stock = () => shell("Stock", "stock", `<div><h1>Current stock</h1><p>860 NOS in 4 locations. 6 items are low.</p></div>
      <div class="acts">${stockActs}<a class="btn" ${go("")}>Transfer</a><a class="btn" ${go("")}>Adjust</a></div>`, `
    <section class="card b-card">
      <div class="b-filters">${fld("Location", sel("All locations", ["Vizag Office", "Kartika Class", "Svkml", "TV Shop"]))}${fld("Spare type", sel("All types", ["Driver", "PCB / LED module", "Complete fitting"]))}${fld("Company", sel("All companies", ["Wipro Lighting", "Havells", "Finolex Cables"]))}
        ${fld("Search", `<input class="inp" type="search" placeholder="Code, old spelling, description, fitting">`, { cls: "grow" })}<label class="switch"><input type="checkbox">Only low stock</label></div>
      <div class="scroll"><table class="t"><thead>
        <tr class="grp"><th colspan="3"></th><th class="span" colspan="4">Good stock, by location</th><th></th><th class="def">Not counted</th></tr>
        <tr><th>Item</th><th>Description</th><th>Company</th><th class="num">Kartika Class</th><th class="num">Svkml</th><th class="num">TV Shop</th><th class="num">Vizag Office</th><th class="num">Total</th><th class="num def">Defective store</th></tr></thead>
        <tbody>${STOCK.map(([code, type, desc, co, per, total, unit, low, def]) => `<tr><td><a class="code" ${go("")}>${code}</a><span class="sub">${type}</span></td><td>${desc}</td><td>${co}</td>
          ${per.map((n) => `<td class="num">${qty(n)}</td>`).join("")}<td class="num tot">${low ? pill("Low") + " " : ""}${total} <span class="cap">${unit}</span></td><td class="num def">${def ? `<a ${go("")}>${def}</a>` : qty(0)}</td></tr>`).join("")}</tbody></table></div>
      <div class="b-foot"><span class="cap">Showing 1–8 of 31</span><a class="btn" ${go("")}>${ic("file-spreadsheet")}Export to Excel</a><nav class="pages" aria-label="Pages"><a class="on" ${go("")}>1</a><a ${go("")}>2</a><a ${go("")}>3</a><a ${go("")}>4</a></nav></div>
    </section>`);

  // ---------- 3. Stock IN form ----------
  const line = (i, item, q, unit, batch, pkd) => `<tr><td class="item" data-l="Item">${sel(item || "Type a code, old spelling or description…")}</td>
    <td data-l="Quantity"><div class="unit"><input class="inp" type="number" min="1" value="${q}" placeholder="0" aria-label="Quantity, line ${i}"><b>${unit}</b></div></td>
    <td data-l="Batch code"><input class="inp" value="${batch}" placeholder="e.g. B2405" aria-label="Batch code, line ${i}"></td><td data-l="PKD (packed)"><input class="inp" type="date" value="${pkd}" aria-label="Packed date, line ${i}"></td>
    <td><button class="rm" type="button" aria-label="Remove line ${i}">${ic("trash")}</button></td></tr>`;
  const stockIn = () => shell("Stock", "", `<div><a class="b-back" ${go("stock")}>${ic("chevron-left")}Current stock</a><h1>Stock IN</h1><p>Material received at a location.</p></div>`, `
    <form class="b-form" onsubmit="return false"><div class="b-steps">
      <section class="card b-card"><h2><span class="stepn">1</span>Where it came from</h2><div class="b-grid">
        <div class="fld wide"><span>Received from <i>*</i></span><div><div class="seg" role="radiogroup" aria-label="Received from"><label><input type="radio" name="s" checked><span>Supplier</span></label><label><input type="radio" name="s"><span>Returned unused from site</span></label><label><input type="radio" name="s"><span>Opening stock</span></label></div></div></div>
        ${fld("Supplier / company", sel("Choose…", ["Wipro Lighting", "Havells", "Sri Sai Electricals"], "need"), { req: 1, hint: "Required. Type a new name to add it.", need: 1 })}
        ${fld("DC / bill no.", `<input class="inp" placeholder="e.g. DC 4512">`)}${fld("Date", `<input class="inp" type="date" value="2026-11-14">`, { req: 1 })}
      </div></section>
      <section class="card b-card"><h2><span class="stepn">2</span>Where it goes</h2><div class="b-grid">
        ${fld("Into location", sel("Choose…", ["Vizag Office", "TV Shop", "Kartika Class"], "need"), { req: 1, hint: "Required.", need: 1 })}${fld("Remarks", `<input class="inp" placeholder="Optional">`, { cls: "wide2" })}
      </div></section>
      <section class="card b-card"><h2><span class="stepn">3</span>What was received</h2>
        <table class="t lines"><thead><tr><th>Item</th><th style="width:150px">Quantity</th><th style="width:150px">Batch code</th><th style="width:170px">PKD (packed)</th><th style="width:48px"></th></tr></thead>
          <tbody>${line(1, "EI09326 · LED module · LL20-111-XXX-65AL", 12, "NOS", "B2405", "2026-08-01")}${line(2, "", "", "—", "", "")}</tbody></table>
        <button class="add" type="button">${ic("plus")} Add another item</button></section>
    </div>
    <aside class="card b-card b-summary"><h2>Summary</h2><dl>
      <div><dt>Items</dt><dd class="total">1</dd></div><div><dt>Quantity</dt><dd class="total">12 NOS</dd></div>
      <div><dt>From</dt><dd class="need">Choose a supplier</dd></div><div><dt>Into</dt><dd class="need">Choose a location</dd></div><div><dt>Date</dt><dd>14-11-2026</dd></div></dl>
      <button class="btn in" type="submit">Save Stock IN</button><a class="cancel" ${go("stock")}>Cancel</a>
      <p class="cap" style="margin-top:14px">Nothing is saved until you press Save.</p></aside></form>`);

  // ---------- 4. Complaints list ----------
  const list = () => shell("Complaints", "list", `<div><h1>Complaints</h1><p>20 open. The oldest has waited 35 days.</p></div>
      <div class="acts"><a class="btn main" ${go("")}>${ic("plus")}New complaint</a><a class="btn" ${go("complaint")}>${ic("clipboard-check")}Record visit</a><a class="btn" ${go("")}>Export to Excel</a></div>`, `
    <div class="b-tiles">${TABS.map(([t, n], i) => `<a ${go("")} class="${i ? "" : "on"} ${t === "Not attended" ? "alert" : ""}"><b>${n}</b>${t}</a>`).join("")}</div>
    <section class="card b-card">
      <div class="b-filters">${fld("Company", sel("All companies", ["Wipro Lighting", "Havells"]))}${fld("City", sel("All cities", ["Visakhapatnam", "Guntur"]))}${fld("Technician", sel("Anyone", ["Ramu", "Apparao"]))}
        ${fld("Search", `<input class="inp" type="search" placeholder="Complaint no., company ref, site, fault">`, { cls: "grow" })}<label class="switch"><input type="checkbox">Over 15 days</label></div>
      <div class="scroll"><table class="t"><thead><tr><th>Complaint</th><th>Site</th><th>Fault</th><th>Technician</th><th>Status</th><th class="num">Open for</th></tr></thead>
        <tbody>${COMPLAINTS.map(([no, d, site, city, co, fault, n, tech, prio, st, age]) => `<tr><td><a class="code" ${go("complaint")}>${no}</a><span class="sub">${d}</span></td><td><b>${site}</b><span class="sub">${city}</span></td>
          <td>${prio ? pill(prio) + " " : ""}${fault}<span class="sub">${co} · ${n} fitting${n > 1 ? "s" : ""}</span></td><td>${tech || `<span class="cap">Not assigned</span>`}</td><td>${pill(st)}</td><td class="num">${days(age)}</td></tr>`).join("")}</tbody></table></div>
      <div class="b-foot"><span class="cap">Showing 1–7 of 20</span><nav class="pages" aria-label="Pages"><a class="on" ${go("")}>1</a><a ${go("")}>2</a><a ${go("")}>3</a></nav></div>
    </section>`);

  // ---------- 5. Complaint page ----------
  const complaint = () => shell("Complaints", "", `<div><a class="b-back" ${go("list")}>${ic("chevron-left")}All complaints</a><h1>CMP-0022 ${pill("Attended")}</h1><p>Vaishaki Bio Marine, Visakhapatnam. Reported 09-11-2026.</p></div>
      <div class="acts"><a class="btn main" ${go("")}>${ic("clipboard-check")}Record visit</a><a class="btn" ${go("")}>Change status</a><a class="btn" ${go("")}>Close as not covered</a></div>`, `
    <div class="b-tiles four"><div><b>5 days</b>open</div><div><b>Ramu</b>technician</div><div><b>1</b>visit so far</div><div><b>2</b>fittings affected</div></div>
    <div class="b-split">
      <div>
        <section class="card b-card"><h2>The fault</h2><p class="b-lead">Flood light lens cracked</p><dl class="b-facts">
          <div><dt>Company</dt><dd>Wipro Lighting</dd></div><div><dt>Company complaint no.</dt><dd class="code">WL/AP/25520</dd></div><div><dt>Priority</dt><dd>Normal</dd></div></dl></section>
        <section class="card b-card"><h2>Visits</h2><div class="scroll"><table class="t"><thead><tr><th>Visit</th><th>Technician</th><th>Work done</th><th>Parts given</th><th>Failed parts collected</th></tr></thead>
          <tbody><tr><td><span class="code">VIS-0019</span><span class="sub">10-11-2026</span></td><td>Ramu</td><td>Checked both fittings. Lens cracked on 2 flood lights, replacement lens needed.</td><td><span class="cap">None</span></td><td><span class="cap">None</span></td></tr></tbody></table></div></section>
      </div>
      <div>
        <section class="card b-card"><h2>Site and contact</h2><dl class="b-facts one">
          <div><dt>Site</dt><dd><a ${go("")}>Vaishaki Bio Marine</a>, Visakhapatnam</dd></div><div><dt>Contact</dt><dd>S. Prasad</dd></div><div><dt>Phone</dt><dd><a href="tel:9848012345">98480 12345</a></dd></div></dl></section>
        <section class="card b-card"><h2>Status history</h2><ol class="b-tl">
          <li class="now"><b>Attended</b><div class="cap">10-11-2026 · Office · visit VIS-0019</div></li><li><b>Not attended</b><div class="cap">09-11-2026 · Office · complaint filed</div></li></ol></section>
      </div>
    </div>`);

  // ---------- router ----------
  const VIEWS = { home: [home, "dashboard"], stock: [stock, "stock"], "stock-in": [stockIn, "stock-in"], list: [list, "complaints-list"], complaint: [complaint, "complaint"] };
  function draw() {
    const r = VIEWS[location.hash.slice(1)] ? location.hash.slice(1) : "home";
    stage.innerHTML = VIEWS[r][0]();
    document.querySelectorAll(".chrome a[href^='#']").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + r));
    document.getElementById("before").href = `../design-refresh/before/${VIEWS[r][1]}.png`;
    window.scrollTo(0, 0);
  }
  document.addEventListener("click", (e) => { if (e.target.closest("[data-noop]")) e.preventDefault(); });
  window.addEventListener("hashchange", draw);
  draw();
})();
