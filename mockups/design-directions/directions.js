/* Three design directions for SVKML Service, each drawn on the same two screens with the same fake data. */
(function () {
  "use strict";
  const stage = document.getElementById("stage");
  const ic = (n) => `<i class="ti ti-${n}" aria-hidden="true"></i>`;

  // ---------- one set of demo data for all three ----------
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
  const TABS = [["Open", 20], ["Not attended", 6], ["Attended", 4], ["Material need to check", 4], ["Awaiting material", 2], ["Resolved", 4]];
  const PILL = { "Not attended": ["st-alert", "alert-circle"], "Attended": ["st-neutral", "tool"], "Awaiting material": ["st-wait", "hourglass"], "Resolved": ["st-ok", "circle-check"],
    "Urgent": ["st-alert", "urgent"], "High": ["st-wait", "arrow-up"], "Stock IN": ["k-in", "arrow-down-left"], "Stock OUT": ["k-out", "arrow-up-right"],
    "Transfer": ["st-neutral", "arrows-exchange"], "Adjustment": ["st-neutral", "adjustments-horizontal"], "Low": ["st-alert", "alert-triangle"] };
  const pill = (w) => { const [c, i] = PILL[w] || ["st-neutral", "point"]; return `<span class="pill ${c}">${ic(i)}${w}</span>`; };
  const days = (n) => `${n} day${n === 1 ? "" : "s"}`;
  const bars = (labels) => `<div class="bars" role="img" aria-label="Stock in and stock out per week, last 5 weeks">${WEEKS.map(([w, i, o]) =>
    `<div class="wk"><div class="pair"><i class="in" style="height:${i / 0.8}%" title="Stock IN ${i}">${labels ? `<b>${i}</b>` : ""}</i><i class="out" style="height:${o / 0.8}%" title="Stock OUT ${o}">${labels ? `<b>${o}</b>` : ""}</i></div><span>${w}</span></div>`).join("")}</div>`;
  const legend = `<div class="legend"><span><i style="background:#2a78d6"></i>Stock IN</span><span><i style="background:#eb6834"></i>Stock OUT</span></div>`;
  const entryRows = () => ENTRIES.map(([no, d, type, items, what, loc, by]) => `<tr><td><a class="code" href="#">${no}</a></td><td class="num" style="text-align:left">${d}</td><td>${pill(type)}</td><td>${items}<span class="sub">${what}</span></td><td>${loc}</td><td>${by}</td></tr>`).join("");
  const complaintRows = () => COMPLAINTS.map(([no, d, site, city, co, fault, n, tech, prio, st, age]) => `<tr><td><a class="code" href="#">${no}</a><span class="sub">${d}</span></td><td><b>${site}</b><span class="sub">${city}</span></td>
    <td>${prio ? pill(prio) + " " : ""}${fault}<span class="sub">${co} · ${n} fitting${n > 1 ? "s" : ""}</span></td><td>${tech || `<span class="cap">Not assigned</span>`}</td><td>${pill(st)}</td><td class="num">${days(age)}</td></tr>`).join("");
  const complaintTable = () => `<div class="scroll"><table class="t"><thead><tr><th>Complaint</th><th>Site</th><th>Fault</th><th>Technician</th><th>Status</th><th class="num">Open for</th></tr></thead><tbody>${complaintRows()}</tbody></table></div>`;

  // =========================== A · Light and airy ===========================
  const A_NAV = [["", [["Dashboard", "layout-dashboard", "home"]]], ["Stock", [["Stock IN", "arrow-down-left"], ["Stock OUT", "arrow-up-right"], ["Transfer", "arrows-exchange"], ["Current stock", "building-warehouse"], ["Movements", "history"], ["Low stock", "alert-triangle", "", 6]]],
    ["Complaints", [["All complaints", "message-report", "list", 20], ["Sites", "building"], ["Technicians", "users"]]], ["Defectives", [["Pieces", "recycle", "", 47], ["Return batches", "truck-return"]]], ["Setup", [["Items", "box"], ["Masters", "settings"]]]];
  function shellA(screen, body) {
    return `<div class="d dir-a"><div class="a-shell"><aside class="a-side"><div class="a-brand"><i class="ti ti-bulb"></i><b>SVKML Service</b></div>
      <div class="a-search">${ic("search")}Search<kbd>/</kbd></div>
      ${A_NAV.map(([g, items]) => (g ? `<h3>${g}</h3>` : "") + items.map(([l, i, s, n]) => `<a href="#" ${s ? `data-screen="${s}"` : ""} class="${s === screen ? "on" : ""}">${ic(i)}${l}${n ? `<em>${n}</em>` : ""}</a>`).join("")).join("")}
      </aside><main class="a-main">${body}</main></div></div>`;
  }
  const ATTN = [
    ["alert", "alert-circle", 6, "Complaints nobody has attended", "Oldest: NSL Textiles, Guntur, 30 days ago", "Assign a technician", "Complaints"],
    ["alert", "clock", 8, "Complaints open for more than 15 days", "Oldest: BARC, 35 days, resolved but not closed", "See them", "Complaints"],
    ["alert", "alert-triangle", 6, "Items low on stock", "EI06006 and CABLE TIE 200MM are down to 1", "See what to order", "Stock"],
    ["wait", "hourglass", 5, "Defective pieces waiting on a company", "Wipro Lighting, batch RB-0001, sent 24 days ago", "Record their answer", "Defectives"],
    ["ok", "circle-check", 4, "Resolved complaints ready to close", "Close them once the site has confirmed", "Close them", "Complaints"],
  ];
  const AGES = [["0–2 days", 3], ["3–7 days", 4], ["8–15 days", 5], ["Over 15 days", 8, 1]];
  const ages = (cls) => `<div class="${cls}">${AGES.map(([l, n, late]) => `<div class="${late ? "late" : ""}"><span>${l}</span><i style="width:${n / 8 * 100}%"></i><b>${n}</b></div>`).join("")}</div>`;
  const stA = (l, f, n, warn) => `<a href="#"><div class="cap">${l}</div><div class="fig ${warn ? "warn" : ""}">${f}</div><div class="cap">${n}</div></a>`;
  const homeA = () => shellA("home", `
    <header class="a-head"><div><h1>Dashboard</h1><p class="cap">Saturday, 14 November 2026</p></div></header>
    <div class="a-actions">
      <div class="grp"><span class="cap">Stock</span><div><a class="btn in" href="#">${ic("arrow-down-left")}Stock IN</a><a class="btn out" href="#">${ic("arrow-up-right")}Stock OUT</a><a class="btn" href="#">Transfer</a><a class="btn" href="#">Adjust</a></div></div>
      <div class="grp"><span class="cap">Complaints</span><div><a class="btn main" href="#">${ic("plus")}New complaint</a><a class="btn" href="#">Record visit</a></div></div>
    </div>
    <section class="a-sec a-group"><h2>Needs attention <span class="cap">5 things, most urgent first</span></h2><div class="a-attn">
      ${ATTN.map(([cls, i, n, t, sub, btn, grp]) => `<a href="#" class="${cls}"><b class="n">${n}</b><span><b>${t}</b><span class="cap"> · ${grp}</span><span class="cap" style="display:block">${sub}</span></span><span class="go">${btn} →</span></a>`).join("")}</div></section>
    <section class="a-sec a-group"><h2>Stock <a href="#">Current stock →</a></h2>
      <div class="a-stats">${stA("In stock", "860 NOS", "plus 729 MTR · 1 PKT")}${stA("Low stock", "6", "at or below reorder level", true)}${stA("Active items", "31", "in the item list")}${stA("Movements, 7 days", "27", "none today")}</div>
      <div class="a-two"><div><p class="cap">Stock IN and OUT, NOS per week</p>${bars(false)}<div style="margin-top:12px">${legend}</div></div>
        <div><p class="cap">By location</p><div class="a-rows">${PLACES.map(([n, q]) => `<a href="#"><b>${n}</b><span>${q}</span></a>`).join("")}</div></div></div></section>
    <div class="a-pair">
      <section class="a-sec a-group"><h2>Complaints <a href="#" data-screen="list">All complaints →</a></h2>
        <div class="a-stats">${stA("Open", "20", "4 resolved, to be closed")}${stA("Not attended", "6", "no technician yet", true)}${stA("Visited, 7 days", "3", "3 visits recorded")}</div>
        <p class="cap" style="margin-bottom:12px">Open complaints by age</p>${ages("ages")}</section>
      <section class="a-sec a-group"><h2>Defective pieces <a href="#">All pieces →</a></h2>
        <div class="a-stats">${stA("In store", "47", "waiting to go back")}${stA("In draft batch", "4", "1 batch")}${stA("With companies", "5", "oldest 24 days")}${stA("Answered", "4", "last 90 days")}</div>
        <p class="cap">Defective pieces are never counted in stock.</p></section>
    </div>
    <section class="a-sec"><h2>Recent entries <a href="#">All movements →</a></h2><div class="scroll"><table class="t"><thead><tr><th>Entry</th><th>Date</th><th>Type</th><th>Items</th><th>Location</th><th>By</th></tr></thead><tbody>${entryRows()}</tbody></table></div></section>`);
  const listA = () => shellA("list", `
    <header class="a-head"><div><h1>Complaints</h1><p class="cap">20 open · 6 not attended yet</p></div><div class="acts"><a class="btn" href="#">Export to Excel</a><a class="btn main" href="#">${ic("plus")}New complaint</a></div></header>
    <nav class="a-tabs">${TABS.map(([t, n], i) => `<a href="#" class="${i ? "" : "on"}">${t}<em>${n}</em></a>`).join("")}</nav>
    <div class="a-filters">${["Company", "City", "Technician", "Age"].map((f) => `<button class="btn" type="button">${f} ${ic("chevron-down")}</button>`).join("")}</div>
    ${complaintTable()}`);

  // =========================== B · Bold and graphic ===========================
  function shellB(screen, hero, body) {
    const nav = [["Home", "home"], ["Stock", ""], ["Complaints", "list", 20], ["Defectives", ""], ["Reports", ""], ["Setup", ""]];
    return `<div class="d dir-b"><div class="b-top"><nav class="b-nav"><div class="b-brand"><i class="ti ti-bulb"></i>SVKML</div>
      ${nav.map(([l, s, n]) => `<a href="#" ${s ? `data-screen="${s}"` : ""} class="${s === screen ? "on" : ""}">${l}${n ? `<em>${n}</em>` : ""}</a>`).join("")}
      <div class="right"><a href="#" aria-label="Search">${ic("search")}</a><a href="#" aria-label="6 items low on stock">${ic("bell")}</a><a href="#">Office</a></div></nav>
      <div class="b-hero">${hero}</div></div><main class="b-body">${body}</main></div>`;
  }
  const attnB = ([cls, i, n, t, sub, btn, grp]) => `<a class="b-block attn ${cls === "alert" && grp === "Stock" ? "amber" : "card"} ${cls}" href="#" ${grp === "Complaints" ? 'data-screen="list"' : ""}><span class="lbl">${ic(i)} ${grp}</span><div class="fig">${n}</div><b>${t}</b><span class="cap">${sub}</span><span class="go">${btn} →</span></a>`;
  const homeB = () => shellB("home", `<div><h1>Saturday, 14 November</h1><p>5 things need attention today.</p></div>
      <div class="acts wide"><a class="btn in" href="#">${ic("arrow-down-left")}Stock IN</a><a class="btn out" href="#">${ic("arrow-up-right")}Stock OUT</a><a class="btn main" href="#">${ic("plus")}New complaint</a><a class="btn main" href="#">${ic("clipboard-check")}Record visit</a>
        <span class="sep"></span><a class="btn" href="#">Transfer</a><a class="btn" href="#">Adjust</a></div>`, `
    <div class="b-blocks">${ATTN.slice(0, 4).map(attnB).join("")}</div>
    <section class="card b-card"><h2>Stock <a href="#">Current stock</a></h2><div class="b-stock">
      <a class="b-block in" href="#"><span class="lbl">Stock IN this week</span><div class="b-spark">${WEEKS.map((w) => `<i style="height:${w[1] / 0.75}%"></i>`).join("")}</div><div class="fig">19 <small>NOS</small></div><span class="cap">50 the week before</span></a>
      <a class="b-block out" href="#"><span class="lbl">Stock OUT this week</span><div class="b-spark">${WEEKS.map((w) => `<i style="height:${w[2] / 0.27}%"></i>`).join("")}</div><div class="fig">27 <small>NOS</small></div><span class="cap">18 the week before</span></a>
      <a class="b-block panel" href="#"><span class="lbl">In stock now</span><div class="fig">860 <small>NOS</small></div><span class="cap">plus 729 MTR · 1 PKT · 31 active items</span></a>
      <div class="b-block panel"><span class="lbl">By location</span><div class="b-locs">${PLACES.map(([n, q]) => `<a href="#"><b>${n}</b><span class="cap">${q}</span></a>`).join("")}</div></div>
    </div></section>
    <div class="b-two">
      <section class="card b-card"><h2>Complaints <a href="#" data-screen="list">All complaints</a></h2>
        <div class="b-headline"><div class="fig">20</div><div><b>open</b><div class="cap">4 resolved, ready to close · 3 visited this week</div></div></div>
        <div class="b-seg" role="img" aria-label="Open complaints by status"><i style="flex:6;background:#d63939"></i><i style="flex:4;background:#475569"></i><i style="flex:4;background:#94a3b8"></i><i style="flex:2;background:#f5b301"></i><i style="flex:4;background:#2e9e4f"></i></div>
        <div class="legend wrap"><span><i style="background:#d63939"></i>6 not attended</span><span><i style="background:#475569"></i>4 attended</span><span><i style="background:#94a3b8"></i>4 material to check</span><span><i style="background:#f5b301"></i>2 awaiting material</span><span><i style="background:#2e9e4f"></i>4 resolved</span></div>
        <p class="cap" style="margin:22px 0 12px">Open complaints by age</p>${ages("b-age")}</section>
      <section class="card b-card"><h2>Defective pieces <a href="#">All pieces</a></h2><div class="b-flow">
        <a href="#"><b>47</b>in the Defective store</a><a href="#"><b>4</b>in a draft batch</a><a href="#" class="wait"><b>5</b>with companies, oldest 24 days</a><a href="#"><b>4</b>answered, last 90 days</a></div>
        <p class="cap" style="margin-top:14px">Defective pieces are never counted in stock.</p></section>
    </div>
    <section class="card b-card"><h2>Recent entries <a href="#">All movements</a></h2><div class="scroll"><table class="t"><thead><tr><th>Entry</th><th>Date</th><th>Type</th><th>Items</th><th>Location</th><th>By</th></tr></thead><tbody>${entryRows()}</tbody></table></div></section>`);
  const listB = () => shellB("list", `<div><h1>Complaints</h1><p>20 open. The oldest has waited 35 days.</p></div><div class="acts"><a class="btn" href="#">Export to Excel</a><a class="btn main" href="#">${ic("plus")}New complaint</a></div>`, `
    <div class="b-tiles">${TABS.map(([t, n], i) => `<a href="#" class="${i ? "" : "on"} ${t === "Not attended" ? "alert" : ""}"><b>${n}</b>${t}</a>`).join("")}</div>
    <section class="card b-card">${complaintTable()}</section>`);

  // =========================== C · Task-first ===========================
  function shellC(screen, body) {
    const nav = [["Today", "sun", "home"], ["Stock", "building-warehouse", ""], ["Complaints", "message-report", "list", 6], ["Defectives", "recycle", ""], ["Reports", "file-spreadsheet", ""], ["Setup", "settings", ""]];
    const link = ([l, i, s, n]) => `<a href="#" ${s ? `data-screen="${s}"` : ""} class="${s === screen ? "on" : ""}">${ic(i)}${l}${n ? `<em>${n}</em>` : ""}</a>`;
    return `<div class="d dir-c"><div class="c-shell"><aside class="c-side"><div class="c-brand"><i class="ti ti-bulb"></i>SVKML</div>${nav.map(link).join("")}
      <div class="who"><b>Office</b><div class="cap">Office staff</div></div></aside><main class="c-main">${body}</main></div>
      <nav class="c-tabbar">${nav.slice(0, 5).map(([l, i, s]) => `<a href="#" ${s ? `data-screen="${s}"` : ""} class="${s === screen ? "on" : ""}">${ic(i)}${l}</a>`).join("")}</nav></div>`;
  }
  const task = ([cls, icon, n, title, sub, btn, grp], main) => `<div class="c-task ${cls}"><div class="n">${ic(icon)}${n}</div><div><span class="cap">${grp}</span><b style="display:block">${title}</b><div class="cap">${sub}</div></div><a class="btn ${main ? "main" : ""}" href="#" data-screen="list">${btn}</a></div>`;
  const glance = (title, rows) => `<section class="c-sec"><h2>${title}</h2><div class="card c-glance">${rows.map(([l, v, cls]) => `<a href="#" class="${cls || ""}">${l}<b>${v}</b></a>`).join("")}</div></section>`;
  const homeC = () => shellC("home", `
    <header class="c-head"><div><h1>Today</h1><p class="cap">Saturday, 14 November 2026</p></div><div class="c-find">${ic("search")}Find an item, complaint or site</div></header>
    <div class="c-actgroups">
      <div><p class="c-grp">Stock</p><div class="c-acts">
        <a class="c-act in" href="#">${ic("package-import")}<b>Stock IN</b><span class="cap">Material received</span></a>
        <a class="c-act out" href="#">${ic("package-export")}<b>Stock OUT</b><span class="cap">Material issued</span></a></div>
        <p class="cap c-also">Also: <a href="#">Transfer between locations</a> · <a href="#">Correct a count</a></p></div>
      <div><p class="c-grp">Complaints</p><div class="c-acts">
        <a class="c-act" href="#">${ic("message-plus")}<b>New complaint</b><span class="cap">A site has reported a fault</span></a>
        <a class="c-act" href="#">${ic("clipboard-check")}<b>Record a visit</b><span class="cap">A technician went to a site</span></a></div>
        <p class="cap c-also">Also: <a href="#">Mark a piece defective</a> · <a href="#">New return batch</a></p></div>
    </div>
    <div class="c-two">
      <section class="c-sec"><h2>Needs attention <span class="cap">5 things, most urgent first</span></h2><div class="card">${ATTN.map((t, i) => task(t, i === 0)).join("")}</div></section>
      <div style="display:grid;gap:24px">
        ${glance("Stock", [["In stock", "860 NOS"], ["Low stock", "6 items", "warn"], ["Entries this week", "27"], ...PLACES.map(([n, q]) => [n, q, "light"])])}
        ${glance("Complaints", [["Open", "20"], ["Nobody has attended", "6", "warn"], ["Open more than 15 days", "8", "warn"], ["Visits this week", "3"]])}
        ${glance("Defective pieces", [["In the Defective store", "47"], ["In a draft batch", "4"], ["With companies", "5"]])}
      </div>
    </div>
    <section class="c-sec"><h2>Saved recently</h2><ul class="card c-log">${ENTRIES.map(([no, d, type, items, what, loc, by]) => `<li>${pill(type)}<b>${items}</b><span>${what}</span><span class="cap">${loc}</span><span class="cap when">${d} · ${by} · <a href="#">${no}</a></span></li>`).join("")}</ul></section>`);
  const listC = () => shellC("list", `
    <header class="c-head"><div><h1>Complaints</h1><p class="cap">20 open · 6 nobody has attended</p></div><a class="btn main" href="#" style="margin-left:auto">${ic("plus")}New complaint</a></header>
    <div class="c-chips">${TABS.map(([t, n], i) => `<a href="#" class="${i ? "" : "on"}">${t} <b>${n}</b></a>`).join("")}</div>
    <div class="c-find" style="margin:0;width:100%">${ic("search")}Find by complaint number, site or fault</div>
    <div class="card">${COMPLAINTS.map(([no, d, site, city, co, fault, n, tech, prio, st, age]) => `<article class="c-row"><div><h3>${site} ${pill(st)}${prio ? " " + pill(prio) : ""}</h3><p>${fault}</p>
      <div class="meta"><span>${no}</span><span>${city}</span><span>${co} · ${n} fitting${n > 1 ? "s" : ""}</span><span>${tech ? "Technician: " + tech : "No technician yet"}</span></div></div>
      <div class="side"><div class="age ${age > 15 ? "late" : ""}"><b>${days(age)}</b><span class="cap">since ${d}</span></div><a class="btn" href="#">${st === "Not attended" ? "Assign" : st === "Resolved" ? "Close" : "Record visit"}</a></div></article>`).join("")}</div>`);

  // ---------- router ----------
  const VIEWS = { a: { home: homeA, list: listA }, b: { home: homeB, list: listB }, c: { home: homeC, list: listC } };
  const SHOTS = { home: "dashboard.png", list: "complaints-list.png" };
  function draw() {
    const [dir = "today", screen = "home"] = location.hash.slice(1).split("/");
    const d = VIEWS[dir] ? dir : "today", s = SHOTS[screen] ? screen : "home";
    stage.innerHTML = d === "today" ? `<div class="today-view"><p>The app as it is now, for comparison.</p><img src="../design-refresh/before/${SHOTS[s]}" alt="Screenshot of the current app"></div>` : VIEWS[d][s]();
    document.querySelectorAll(".chrome [data-dir]").forEach((a) => { a.classList.toggle("on", a.dataset.dir === d); a.href = `#${a.dataset.dir}/${s}`; });
    document.querySelectorAll(".chrome [data-screen]").forEach((a) => a.classList.toggle("on", a.dataset.screen === s));
    window.scrollTo(0, 0);
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a, button"); if (!a || a.matches(".chrome [data-dir]")) return;
    e.preventDefault();
    if (a.dataset.screen) location.hash = `${(location.hash.slice(1).split("/")[0]) || "today"}/${a.dataset.screen}`;
  });
  window.addEventListener("hashchange", draw);
  if (!location.hash) location.hash = "a/home"; else draw();
})();
