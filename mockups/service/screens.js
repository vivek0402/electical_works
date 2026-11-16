/* Screens in the Tabler admin layout: dashboard, current stock, items, item card, movements, entry, low stock, masters.
   Good-stock figures (totals, low stock, KPIs, charts) use DB.locations only; the Defective store is shown separately. */

const filterCol = (w, html) => `<div class="col-12 col-sm-6 col-lg-${w}">${html}</div>`;
const fsel = (label, onchange, list, value, all) => `<label class="form-label small text-secondary mb-1">${label}</label>
  <select class="form-select" onchange="${onchange}">${all ? `<option value="">${all}</option>` : ""}${opt(list, value)}</select>`;
const fsearch = (value, onchange, ph) => `<label class="form-label small text-secondary mb-1">Search</label><div class="input-icon">
  <span class="input-icon-addon">${icon("search")}</span><input type="search" class="form-control" value="${esc(value)}" placeholder="${ph}" onchange="${onchange}"></div>`;
const fdate = (label, value, onchange) => `<label class="form-label small text-secondary mb-1">${label}</label>
  <input type="date" class="form-control" value="${value}" max="${today()}" onchange="${onchange}">`;
const matchItem = (i, text) => { const q = norm(text), k = key(text);
  return !q || [i.code, ...i.aliases, i.desc, i.catRef].join(" ").toUpperCase().includes(q) || (k.length > 2 && [i.code, ...i.aliases].some(c => key(c).includes(k))); };
const fittingHtml = i => i.catRef && i.catRef !== i.code ? `<span class="code">${esc(i.catRef)}</span><div class="text-secondary small">${esc(i.fittingType)}</div>` : esc(i.fittingType);

/* ---------- dashboard ---------- */
ROUTES.dash = () => {
  const low = DB.items.filter(i => i.active && isLow(i));
  const unitsAt = loc => { const t = {}; for (const i of DB.items) { const q = balance(i.code, loc); if (q) t[i.unit] = (t[i.unit] || 0) + q; } return t; };
  const nosTotal = sum(DB.locations, l => unitsAt(l).NOS || 0);
  const week = byDateDesc(DB.entries).filter(e => e.date > addDays(today(), -7));
  const openC = DB.complaints.filter(isOpen), notAtt = openC.filter(c => c.status === "NOT_ATTENDED").length;
  setHeader("Overview", "Stock dashboard", `<span class="text-secondary me-2 align-self-center">${icon("calendar")} ${fmt(today())}</span>`);
  const kpi = (ic, color, value, label, sub, href) => `<div class="col-sm-6 col-lg-3"><a class="card card-sm card-link" href="${href}"><div class="card-body"><div class="row align-items-center">
    <div class="col-auto"><span class="avatar kpi-${color}">${icon(ic)}</span></div>
    <div class="col"><div class="font-weight-medium fs-3">${value}</div><div class="text-secondary">${label}</div>${sub ? `<div class="small text-secondary">${sub}</div>` : ""}</div></div></div></a></div>`;
  view().innerHTML = `<div class="row row-deck row-cards">
    ${kpi("box", "brand", DB.items.filter(i => i.active).length, "Active items", `${DB.spareTypes.length} spare types`, "#items")}
    ${kpi("building-warehouse", "brand", nosTotal.toLocaleString("en-IN") + " NOS", "In stock (all locations)", "plus wire in MTR, ties in PKT", "#stock")}
    ${kpi("alert-triangle", low.length ? "alert" : "ok", low.length, "Low stock items", "at or below reorder level", "#low")}
    ${kpi("arrows-exchange", "brand", week.length, "Entries this week", `${DB.entries.filter(e => e.date === today()).length} today`, "#moves")}
    ${kpi("message-report", notAtt ? "alert" : "brand", openC.length, "Open complaints", notAtt ? `${notAtt} not attended yet` : "all attended", "#cdash")}
    ${kpi("recycle", "brand", DB.pieces.filter(p => p.status === "IN_STORE").length, "Defective pieces in store", "not counted in stock above", "#ddash")}
    ${kpi("truck-return", "brand", DB.pieces.filter(p => p.status === "SENT").length, "Pieces with companies", "sent, awaiting settlement", "#batches")}
    ${kpi("clipboard-check", "brand", DB.visits.filter(v => v.date > addDays(today(), -7)).length, "Visits this week", "recorded on complaints", "#complaints/open")}
    <div class="col-12"><div class="card"><div class="card-body"><div class="row g-2 quick">
      <div class="col-6 col-lg-3"><a href="#in" class="btn btn-in w-100 flex-column">${icon("package-import")} Stock IN<small>Material received</small></a></div>
      <div class="col-6 col-lg-3"><a href="#out" class="btn btn-out w-100 flex-column">${icon("package-export")} Stock OUT<small>Material issued</small></a></div>
      <div class="col-6 col-lg-3"><a href="#transfer" class="btn btn-quiet w-100 flex-column">${icon("arrows-exchange")} Transfer<small>Between locations</small></a></div>
      <div class="col-6 col-lg-3"><a href="#adjust" class="btn btn-quiet w-100 flex-column">${icon("adjustments-horizontal")} Adjust<small>Correct a count</small></a></div>
    </div></div></div></div>
    <div class="col-lg-8"><div class="card"><div class="card-header"><div><h3 class="card-title">Stock IN vs OUT</h3>
        <div class="card-subtitle">Quantity per week, last 5 weeks (items counted in NOS)</div></div>
        <div class="card-actions"><a href="#" class="btn btn-sm btn-outline-secondary" onclick="toggleChartTable();return false" id="chart-toggle">${icon("table")} View as table</a></div></div>
      <div class="card-body"><div id="chart-weekly" class="chart-box" role="img" aria-label="Bar chart of stock in and stock out per week"></div><div id="chart-table" hidden></div></div></div></div>
    <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Stock by location</h3></div>
      <div class="list-group list-group-flush">${DB.locations.map(l => { const t = unitsAt(l);
        return `<a href="#stock/${encodeURIComponent(l)}" class="list-group-item list-group-item-action d-flex align-items-center">
          <span class="avatar avatar-sm bg-secondary-lt me-3">${icon("map-pin")}</span><div class="flex-fill"><div class="fw-medium">${esc(l)}</div>
          <div class="text-secondary small">${Object.entries(t).map(([u, q]) => `${q.toLocaleString("en-IN")} ${u}`).join(" · ") || "Empty"}</div></div>${icon("chevron-right")}</a>`; }).join("")}</div></div></div>
    <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">Recent entries</h3>
      <div class="card-actions"><a href="#moves" class="btn btn-sm btn-outline-primary">All movements ${icon("arrow-right")}</a></div></div>
      ${dataTable("recent", { rows: byDateDesc(DB.entries).slice(0, 8), paging: false, columns: entryColumns(), rowClass: e => undoneBy(e.no) ? "undone" : "" })}</div></div>
  </div>`;
  setTimeout(drawWeeklyChart);
};
// Details text, with the complaint / return batch as a link instead of plain text.
const whatHtml = e => { const src = e.complaint || e.batch, w = esc(entryWhat(e));
  return src ? w.replace(src, entrySource(e)) : w; };
function entryColumns() {
  return [
    { key: "no", label: "Entry", html: e => entryLink(e.no) },
    { key: "date", label: "Date", cls: "nowrap", html: e => fmt(e.date) },
    { key: "kind", label: "Type", html: kindBadge },
    { key: "what", label: "Details", sort: entryWhat, html: whatHtml },
    { key: "items", label: "Items", nosort: true, html: e => { const codes = uniq(e.lines.map(l => l.code));
      return codes.length === 1 ? `<span class="code">${esc(codes[0])}</span> × ${entryQty(e)}` : `${codes.length} items`; } },
    { key: "loc", label: "Location", sort: entryLocs, html: e => esc(entryLocs(e)) },
    { key: "party", label: "Supplier / issued to", html: e => esc(e.party || "") },
    { key: "by", label: "By" },
  ];
}
/* Weekly IN vs OUT: grouped bars, two validated categorical slots (blue/orange), 4px rounded ends,
   2px surface gap, recessive grid, legend + shared tooltip, plus a table view. */
function weeklyData() {
  const weeks = [];
  for (let w = 4; w >= 0; w--) { const end = addDays(today(), -7 * w), start = addDays(end, -6); weeks.push({ start, end, in: 0, out: 0 }); }
  for (const e of DB.entries) if (e.kind === "IN" || e.kind === "OUT") for (const l of e.lines) {
    if (unitOf(l.code) !== "NOS" || l.loc === DB.defStore) continue;   // good stock only
    const wk = weeks.find(x => e.date >= x.start && e.date <= x.end);
    if (wk) { if (l.qty > 0) wk.in += l.qty; else wk.out -= l.qty; }
  }
  return weeks.map(w => ({ ...w, label: `${fmt(w.start).slice(0, 5)}–${fmt(w.end).slice(0, 5)}` }));
}
function drawWeeklyChart() {
  const el = document.getElementById("chart-weekly"); if (!el) return;
  const data = weeklyData();
  new ApexCharts(el, {
    chart: { type: "bar", height: 260, toolbar: { show: false }, fontFamily: "inherit", animations: { enabled: false } },
    series: [{ name: "Stock IN", data: data.map(d => d.in) }, { name: "Stock OUT", data: data.map(d => d.out) }],
    colors: ["#2a78d6", "#eb6834"], // CVD-validated categorical pair (chart marks; buttons use deeper AA shades)
    plotOptions: { bar: { columnWidth: "45%", borderRadius: 4, borderRadiusApplication: "end" } },
    stroke: { show: true, width: 2, colors: ["#ffffff"] },
    dataLabels: { enabled: false },
    grid: { borderColor: "#eef0f3", strokeDashArray: 4, padding: { left: 4, right: 4 } },
    xaxis: { categories: data.map(d => d.label), axisBorder: { show: false }, axisTicks: { show: false }, labels: { style: { colors: "#6b7280" } } },
    yaxis: { title: { text: "NOS", style: { color: "#6b7280", fontWeight: 500 } }, labels: { style: { colors: "#6b7280" } } },
    legend: { position: "top", horizontalAlign: "left", markers: { shape: "square", size: 7 }, labels: { colors: "#374151" } },
    tooltip: { shared: true, intersect: false, y: { formatter: v => `${v} NOS` } },
  }).render();
  document.getElementById("chart-table").innerHTML = `<table class="table table-sm"><thead><tr><th>Week</th><th class="num">Stock IN (NOS)</th><th class="num">Stock OUT (NOS)</th></tr></thead>
    <tbody>${data.map(d => `<tr><td>${d.label}</td><td class="num">${d.in}</td><td class="num">${d.out}</td></tr>`).join("")}</tbody></table>`;
}
function toggleChartTable() {
  const t = document.getElementById("chart-table"), c = document.getElementById("chart-weekly"), b = document.getElementById("chart-toggle");
  t.hidden = !t.hidden; c.hidden = !t.hidden;
  b.innerHTML = t.hidden ? `${icon("table")} View as table` : `${icon("chart-bar")} View as chart`;
}

/* ---------- current stock ---------- */
let sf = { loc: "", type: "", company: "", q: "", low: false };
ROUTES.stock = arg => {
  if (arg !== undefined) { sf = { loc: DB.locations.includes(arg) ? arg : "", type: "", company: "", q: "", low: false }; resetPage("stock"); }
  const rows = DB.items.filter(i => i.active && (!sf.type || i.type === sf.type) && (!sf.company || i.company === sf.company) && matchItem(i, sf.q)
    && (!sf.low || isLow(i)) && (sf.loc ? balance(i.code, sf.loc) !== 0 : total(i.code) !== 0 || defQty(i.code) !== 0 || sf.low));
  const locs = sf.loc ? [sf.loc] : DB.locations;
  const set = (k, v) => `sf.${k}=${v};resetPage('stock');route()`;
  setHeader("Reports", "Current stock", exportBtn("Current_Stock.xlsx"));
  view().innerHTML = `<div class="card"><div class="card-header"><div class="row g-2 w-100 align-items-end">
      ${filterCol(2, fsel("Location", set("loc", "this.value"), DB.locations, sf.loc, "All locations"))}
      ${filterCol(2, fsel("Spare type", set("type", "this.value"), DB.spareTypes, sf.type, "All types"))}
      ${filterCol(2, fsel("Company", set("company", "this.value"), DB.companies, sf.company, "All companies"))}
      ${filterCol(4, fsearch(sf.q, set("q", "this.value"), "Code, old spelling, description, fitting"))}
      ${filterCol(2, `<label class="form-check form-switch mb-2"><input class="form-check-input" type="checkbox" ${sf.low ? "checked" : ""}
        onchange="${set("low", "this.checked")}"><span class="form-check-label">Only low stock</span></label>`)}
    </div></div>
    ${dataTable("stock", { rows, sort: "code", columns: [
      { key: "code", label: "Item", html: i => `${codeLink(i.code)}<div class="small text-secondary">${esc(i.type)} · ${esc(i.desc)}</div>` },
      { key: "catRef", label: "Used in (fitting)", html: fittingHtml }, { key: "company", label: "Company" },
      ...locs.map(l => ({ key: "L:" + l, label: esc(l), num: true, sort: i => balance(i.code, l), html: i => qtyHtml(balance(i.code, l)) })),
      ...(sf.loc ? [] : [{ key: "total", label: "Total", num: true, sort: i => total(i.code),
        html: i => (isLow(i) ? `<span class="badge bg-red-lt">${total(i.code)}</span>` : `<b>${total(i.code)}</b>`) + ` <small class="text-secondary">${i.unit}</small>` }]),
      { key: "def", label: `<span class="def-head">Defective store<small>not counted</small></span>`, num: true, cls: "col-def", sort: i => defQty(i.code),
        html: i => defQty(i.code) ? `<a href="#pieces/item=${encodeURIComponent(i.code)}&status=IN_STORE" title="Open the pieces">${defQty(i.code)}</a>` : qtyHtml(0) }] })}
  </div><p class="text-secondary small mt-2">${icon("info-circle")} Red total = at or below the item's reorder level.
    The <b>Defective store</b> column shows failed pieces waiting to go back to the company. They are never part of the total.</p>`;
};

/* ---------- items ---------- */
let itf = { q: "", type: "", company: "", ftype: "", active: "1" };
ROUTES.items = () => {
  const rows = DB.items.filter(i => (!itf.type || i.type === itf.type) && (!itf.company || i.company === itf.company) && (!itf.ftype || i.fittingType === itf.ftype)
    && (itf.active === "" || String(+i.active) === itf.active) && matchItem(i, itf.q));
  const set = (k) => `itf.${k}=this.value;resetPage('items');route()`;
  setHeader("Setup", "Items", `<a href="#item-new" class="btn btn-primary">${icon("plus")} Add item</a>${exportBtn("Item_List.xlsx")}`);
  view().innerHTML = `<div class="card"><div class="card-header"><div class="row g-2 w-100 align-items-end">
      ${filterCol(4, fsearch(itf.q, set("q"), "Code, old spelling, description, fitting"))}
      ${filterCol(2, fsel("Spare type", set("type"), DB.spareTypes, itf.type, "All"))}
      ${filterCol(2, fsel("Company", set("company"), DB.companies, itf.company, "All"))}
      ${filterCol(2, fsel("Fitting type", set("ftype"), DB.fittingTypes, itf.ftype, "All"))}
      ${filterCol(2, fsel("Status", set("active"), [["1", "Active"], ["0", "Inactive"], ["", "All"]], itf.active))}
    </div></div>
    ${dataTable("items", { rows, sort: "code", columns: [
      { key: "code", label: "Item code", html: i => codeLink(i.code) + (i.aliases.length ? `<div class="text-secondary small">also: ${esc(i.aliases.join(", "))}</div>` : "") },
      { key: "type", label: "Spare type" }, { key: "desc", label: "Description" },
      { key: "catRef", label: "Product cat ref", html: fittingHtml }, { key: "watt", label: "W", num: true, html: i => i.watt ?? "" },
      { key: "company", label: "Company" }, { key: "unit", label: "Unit" }, { key: "reorder", label: "Reorder at", num: true },
      { key: "stock", label: "In stock", num: true, sort: i => total(i.code), html: i => isLow(i) ? `<span class="badge bg-red-lt">${total(i.code)}</span>` : total(i.code) },
      { key: "edit", label: "", nosort: true, html: i => `<a href="#item-edit/${encodeURIComponent(i.code)}" class="btn btn-sm btn-ghost-primary">${icon("edit")} Edit</a>` }] })}
  </div>`;
};
function itemFormScreen(code) {
  const it = code ? item(code) : null;
  if (code && !it) { setHeader("Setup", "Item not found"); view().innerHTML = ""; return; }
  setHeader("Setup · Items", it ? `Edit item <span class="code">${esc(it.code)}</span>` : `${icon("plus")} Add item`);
  view().innerHTML = `<form novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveItemPage(${it ? `'${esc(it.code)}'` : "null"})">
    <div class="card"><div class="card-body">${itemFields(it ? { ...it, originalCode: it.code } : {})}
      ${it ? `<label class="form-check form-switch mt-3"><input class="form-check-input" type="checkbox" id="it-active" ${it.active ? "checked" : ""}>
        <span class="form-check-label">Active (untick to hide from entry forms; history is kept)</span></label>` : ""}</div>
      <div class="card-footer d-flex"><div class="ms-auto btn-list"><a href="${it ? `#item/${encodeURIComponent(it.code)}` : "#items"}" class="btn btn-link link-secondary">Cancel</a>
        <button type="submit" class="btn btn-primary">${icon("device-floppy")} Save item</button></div></div></div>
    <div id="form-error" class="mt-3"></div></form>`;
}
ROUTES["item-new"] = () => itemFormScreen();
ROUTES["item-edit"] = itemFormScreen;
function saveItemPage(original) {
  const d = readItemFields(), err = saveItem(d, original || undefined);
  if (err) return formFail(err);
  if (original) item(norm(d.code)).active = field("it-active").checked;
  toastAfterNav(`Item <b>${esc(norm(d.code))}</b> saved.`);
  go(`#item/${encodeURIComponent(norm(d.code))}`);
}

/* ---------- item card ---------- */
let hf = { code: "" };
ROUTES.item = code => {
  const i = item(code);
  if (!i) { setHeader("Items", "Item not found"); view().innerHTML = ""; return; }
  if (hf.code !== code) { hf = { code, from: addDays(today(), -30), to: today(), loc: "" }; resetPage("hist"); }
  const run = {}, rows = [];
  for (const e of DB.entries) for (const l of e.lines) if (l.code === code) {
    run[l.loc] = (run[l.loc] || 0) + l.qty;
    if (e.date >= hf.from && e.date <= hf.to && (!hf.loc || l.loc === hf.loc)) rows.push({ e, l, after: run[l.loc], n: rows.length });
  }
  const fact = (k, v) => v ? `<div class="datagrid-item"><div class="datagrid-title">${k}</div><div class="datagrid-content">${v}</div></div>` : "";
  const set = k => `hf.${k}=this.value;resetPage('hist');route()`;
  setHeader(`${esc(i.type)} · ${esc(i.company)}`, `<span class="code">${esc(i.code)}</span> ${isLow(i) ? `<span class="badge bg-red-lt ms-2">Low stock</span>` : ""}`,
    `<a href="#in/${encodeURIComponent(code)}" class="btn btn-in">${icon("package-import")} Stock IN</a>
     <a href="#out/${encodeURIComponent(code)}" class="btn btn-out">${icon("package-export")} Stock OUT</a>
     <a href="#item-edit/${encodeURIComponent(code)}" class="btn btn-outline-secondary">${icon("edit")} Edit</a>`);
  view().innerHTML = `<div class="row row-cards">
    <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
      ${fact("Description", esc(i.desc))}${fact("Spare type", esc(i.type))}${fact("Used in fitting", i.catRef && i.catRef !== i.code ? `<span class="code">${esc(i.catRef)}</span>` : "")}
      ${fact("Fitting type", esc(i.fittingType))}${fact("Wattage", i.watt ? i.watt + " W" : "")}${fact("Current", i.ma ? i.ma + " mA" : "")}
      ${fact("Company", esc(i.company))}${fact("Unit", i.unit)}${fact("Reorder level", `${i.reorder} ${i.unit}`)}
      ${fact("Other spellings", esc(i.aliases.join(", ")))}${fact("Status", i.active ? `<span class="badge bg-green-lt">Active</span>` : `<span class="badge bg-secondary-lt">Inactive</span>`)}
    </div></div></div></div>
    <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">Stock by location</h3></div>
      <div class="list-group list-group-flush">${DB.locations.map(l => `<div class="list-group-item d-flex"><span>${esc(l)}</span>
        <span class="ms-auto fw-bold">${qtyHtml(balance(code, l))} <span class="text-secondary fw-normal">${i.unit}</span></span></div>`).join("")}
        <div class="list-group-item d-flex bg-light"><b>Total (good stock)</b><span class="ms-auto fw-bold">${total(code)} ${i.unit}</span></div></div>
      <div class="card-footer d-flex align-items-center">${icon("recycle", "me-2 text-secondary")}<span>Defective store: <b>${defQty(code)}</b> ${i.unit}
        <span class="d-block small text-secondary">Failed pieces, not counted above</span></span>
        ${defQty(code) ? `<a class="btn btn-sm btn-quiet ms-auto" href="#pieces/item=${encodeURIComponent(code)}&status=IN_STORE">${icon("tags")} Pieces</a>` : ""}</div></div></div>
    <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">Movement history</h3>
      <div class="card-actions">${exportBtn("Stock_Movements.xlsx", "Export history")}</div></div>
      <div class="card-body border-bottom py-3"><div class="row g-2">
        ${filterCol(3, fdate("From date", hf.from, set("from")))}${filterCol(3, fdate("To date", hf.to, set("to")))}
        ${filterCol(3, fsel("Location", set("loc"), [...DB.locations, DB.defStore], hf.loc, "All locations"))}</div></div>
      ${dataTable("hist", { rows, sort: "n", dir: "desc", empty: "No movements in this period.", rowClass: r => undoneBy(r.e.no) ? "undone" : "", columns: [
        { key: "n", label: "Date", cls: "nowrap", sort: r => r.n, html: r => fmt(r.e.date) },
        { key: "no", label: "Entry", sort: r => r.e.no, html: r => entryLink(r.e.no) }, { key: "kind", label: "Type", sort: r => r.e.kind, html: r => kindBadge(r.e) },
        { key: "loc", label: "Location", sort: r => r.l.loc, html: r => esc(r.l.loc) },
        { key: "in", label: "In", num: true, sort: r => r.l.qty, html: r => r.l.qty > 0 ? `<span class="qty-in">+${r.l.qty}</span>` : "" },
        { key: "out", label: "Out", num: true, sort: r => -r.l.qty, html: r => r.l.qty < 0 ? `<span class="qty-out">−${-r.l.qty}</span>` : "" },
        { key: "after", label: "Balance at location", num: true, html: r => `<b>${r.after}</b>` },
        { key: "party", label: "Supplier / issued to", sort: r => r.e.party || "", html: r => esc(r.e.party || r.e.reason || "") },
        { key: "ref", label: "Ref", sort: r => r.e.ref || "", html: r => esc(r.e.ref || "") }, { key: "by", label: "By", sort: r => r.e.by, html: r => esc(r.e.by) }] })}
    </div></div></div>`;
};

/* ---------- movements ---------- */
let mf = { from: "", to: "", kind: "", loc: "", q: "" };
ROUTES.moves = () => {
  if (!mf.from) mf = { ...mf, from: addDays(today(), -30), to: today() };
  const q = norm(mf.q), rows = [];
  byDateDesc(DB.entries).forEach((e, n) => {
    if (e.date < mf.from || e.date > mf.to || (mf.kind && e.kind !== mf.kind)) return;
    for (const l of e.lines) if ((!mf.loc || l.loc === mf.loc) && (!q || [l.code, e.party, e.ref, e.no, e.complaint, e.batch].join(" ").toUpperCase().includes(q))) rows.push({ e, l, n });
  });
  const set = k => `mf.${k}=this.value;resetPage('moves');route()`;
  setHeader("Reports", "Stock movements", exportBtn("Stock_Movements.xlsx"));
  view().innerHTML = `<div class="card"><div class="card-header"><div class="row g-2 w-100 align-items-end">
      ${filterCol(2, fdate("From date", mf.from, set("from")))}${filterCol(2, fdate("To date", mf.to, set("to")))}
      ${filterCol(2, fsel("Type", set("kind"), Object.entries(KIND), mf.kind, "All types"))}
      ${filterCol(2, fsel("Location", set("loc"), [...DB.locations, DB.defStore], mf.loc, "All locations"))}
      ${filterCol(4, fsearch(mf.q, set("q"), "Item, supplier, customer, ref, CMP / RB no."))}</div></div>
    ${dataTable("moves", { rows, sort: "date", dir: "asc", empty: "No movements in this period.", rowClass: r => undoneBy(r.e.no) ? "undone" : "", columns: [
      { key: "date", label: "Date", cls: "nowrap", sort: r => r.n, html: r => fmt(r.e.date) },
      { key: "no", label: "Entry", sort: r => r.e.no, html: r => entryLink(r.e.no) }, { key: "kind", label: "Type", sort: r => r.e.kind, html: r => kindBadge(r.e) },
      { key: "what", label: "Details", sort: r => entryWhat(r.e), html: r => whatHtml(r.e) },
      { key: "code", label: "Item", sort: r => r.l.code, html: r => `${codeLink(r.l.code)}<div class="small text-secondary">${esc(item(r.l.code).desc)}</div>` },
      { key: "loc", label: "Location", sort: r => r.l.loc, html: r => r.l.loc === DB.defStore ? `<span class="text-secondary">${icon("recycle")} ${esc(r.l.loc)}</span>` : esc(r.l.loc) },
      { key: "in", label: "In", num: true, sort: r => r.l.qty, html: r => r.l.qty > 0 ? `<span class="qty-in">+${r.l.qty}</span>` : "" },
      { key: "out", label: "Out", num: true, sort: r => -r.l.qty, html: r => r.l.qty < 0 ? `<span class="qty-out">−${-r.l.qty}</span>` : "" },
      { key: "unit", label: "Unit", nosort: true, html: r => unitOf(r.l.code) },
      { key: "party", label: "Supplier / issued to", sort: r => r.e.party || "", html: r => esc(r.e.party || r.e.reason || "") + (r.e.ref && !r.e.complaint && !r.e.batch ? `<div class="small text-secondary">${esc(r.e.ref)}</div>` : "") },
      { key: "by", label: "By", sort: r => r.e.by, html: r => esc(r.e.by) }] })}
  </div><p class="text-secondary small mt-2">${icon("info-circle")} Struck-through rows were undone; an "Undo" entry reverses them.
    Rows at the Defective store are failed pieces, not good stock.</p>`;
};

/* ---------- entry detail + undo ---------- */
ROUTES.entry = no => {
  const e = entry(no);
  if (!e) { setHeader("Movements", "Entry not found"); view().innerHTML = ""; return; }
  const u = undoneBy(no);
  const fact = (k, v) => v ? `<div class="datagrid-item"><div class="datagrid-title">${k}</div><div class="datagrid-content">${v}</div></div>` : "";
  setHeader(`${KIND[e.kind]} · ${esc(entryWhat(e))}`, `<span class="code">${e.no}</span> ${kindBadge(e)}`,
    `${e.complaint ? `<a href="#complaint/${e.complaint}" class="btn btn-quiet">${icon("message-report")} Complaint ${e.complaint}</a>` : ""}
     ${e.batch ? `<a href="#batch/${e.batch}" class="btn btn-quiet">${icon("truck-return")} Batch ${e.batch}</a>` : ""}
     ${!u && e.kind !== "REV" && !isDefectiveEntry(e) ? `<button class="btn btn-outline-danger" onclick="askUndo('${e.no}')">${icon("arrow-back-up")} Undo this entry</button>` : ""}
     <a href="#moves" class="btn btn-outline-secondary">${icon("history")} All movements</a>`);
  view().innerHTML = `${u ? `<div class="alert alert-warning">${icon("arrow-back-up")} Undone by ${entryLink(u.no)} on ${fmt(u.date)}: ${esc(u.note)}</div>` : ""}
    ${e.reverses ? `<div class="alert alert-info">This entry reverses ${entryLink(e.reverses)}.</div>` : ""}
    ${isDefectiveEntry(e) && !u ? `<div class="alert alert-info">${icon("info-circle")} This entry belongs to the defective pieces, so it can't be undone here. Use the
      ${e.batch ? `return batch <a href="#batch/${e.batch}">${e.batch}</a>` : `<a href="#pieces">Defectives screens</a>`} instead.</div>` : ""}
    <div class="row row-cards"><div class="col-12"><div class="card"><div class="card-body"><div class="datagrid">
      ${fact("Date", fmt(e.date))}${fact(e.kind === "IN" ? "Received from" : e.kind === "OUT" ? "Issued to" : e.kind === "TRF" ? "Moved to" : "", esc(e.party || ""))}
      ${fact("Location", esc(entryLocs(e)))}${fact("Complaint", e.complaint ? entrySource(e) : "")}${fact("Return batch", e.batch ? `<a class="code" href="#batch/${e.batch}">${e.batch}</a>` : "")}
      ${fact(e.batch ? "Docket / ref no." : "DC / ref no.", e.complaint ? "" : esc(e.ref || ""))}${fact("Reason", esc(e.reason || ""))}${fact("Remarks", esc(e.note || ""))}${fact("Entered by", esc(e.by))}
    </div></div></div></div>
    <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">Items</h3></div>
      ${dataTable("entry-lines", { rows: e.lines, paging: false, columns: [
        { key: "code", label: "Item code", html: l => codeLink(l.code) }, { key: "desc", label: "Description", sort: l => item(l.code).desc, html: l => esc(item(l.code).desc) },
        { key: "loc", label: "Location" },
        { key: "in", label: "In", num: true, sort: l => l.qty, html: l => l.qty > 0 ? `<span class="qty-in">+${l.qty}</span>` : "" },
        { key: "out", label: "Out", num: true, sort: l => -l.qty, html: l => l.qty < 0 ? `<span class="qty-out">−${-l.qty}</span>` : "" },
        { key: "unit", label: "Unit", nosort: true, html: l => unitOf(l.code) }, { key: "batch", label: "Batch code" }, { key: "pkd", label: "PKD", html: l => fmtMonth(l.pkd) }] })}
    </div></div>${entryPieces(e)}</div>
    <p class="text-secondary small mt-3">${icon("lock")} Entries are never edited or deleted. "Undo" adds an opposite entry with a reason, so the history always shows what happened.</p>`;
};
// Defective pieces created or moved by this entry (collection, mark defective, dispatch, settlement, scrap).
function entryPieces(e) {
  const tags = uniq([...DB.pieces.filter(p => p.entry === e.no).map(p => p.tag),
    ...DB.batches.flatMap(b => b.lines.filter(l => l.entry === e.no || b.dispatchEntry === e.no).map(l => l.tag))]);
  if (!tags.length) return "";
  return `<div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">${icon("tags")} Defective pieces</h3>
    <span class="badge bg-secondary-lt ms-2">${tags.length}</span></div><div class="card-body"><div class="d-flex flex-wrap gap-2">${tags.map(t => { const p = piece(t);
    return `<a class="chip chip-link" href="#piece/${t}"><span class="code">${t}</span> <span class="text-secondary">${esc(p.code)}</span> ${pBadge(p.status)}</a>`; }).join("")}</div></div></div></div>`;
}
function askUndo(no) {
  openModal(`<div class="modal-status bg-danger"></div><div class="modal-body text-center py-4">${icon("arrow-back-up")}
      <h3 class="mt-2">Undo ${no}?</h3><div class="text-secondary mb-3">This adds a new entry that reverses every line of ${no}.</div>
      <div class="text-start"><label class="form-label required" for="undo-reason">Reason</label>
      <input id="undo-reason" class="form-control" placeholder="e.g. Entered against the wrong job"><div id="undo-err" class="invalid-feedback d-block"></div></div></div>
    <div class="modal-footer"><div class="w-100"><div class="row"><div class="col"><button class="btn w-100" onclick="closeModal()">Keep it</button></div>
      <div class="col"><button class="btn btn-danger w-100" onclick="doUndo('${no}')">Undo entry</button></div></div></div></div>`, "modal-sm");
}
function doUndo(no) {
  const err = undo(no, field("undo-reason").value);
  if (err) { field("undo-err").textContent = err; field("undo-reason").classList.add("is-invalid"); return; }
  closeModal(); toastAfterNav(`${no} undone. A reversing entry was added.`); route();
}

/* ---------- low stock ---------- */
ROUTES.low = () => {
  const rows = DB.items.filter(i => i.active && isLow(i));
  setHeader("Reports", "Low stock", exportBtn("Low_Stock.xlsx"));
  view().innerHTML = `<div class="alert alert-${rows.length ? "warning" : "success"}">${icon(rows.length ? "alert-triangle" : "circle-check")}
      ${rows.length ? `${rows.length} items are at or below their reorder level (total across all locations).` : "Nothing is low."}</div>
    <div class="card">${dataTable("low", { rows, sort: "short", dir: "desc", columns: [
      { key: "code", label: "Item code", html: i => codeLink(i.code) }, { key: "type", label: "Spare type" }, { key: "desc", label: "Description" }, { key: "company", label: "Company" },
      ...DB.locations.map(l => ({ key: "L:" + l, label: esc(l), num: true, sort: i => balance(i.code, l), html: i => qtyHtml(balance(i.code, l)) })),
      { key: "total", label: "Total", num: true, sort: i => total(i.code), html: i => `<span class="badge bg-red-lt">${total(i.code)}</span>` },
      { key: "reorder", label: "Reorder at", num: true },
      { key: "short", label: "Short by", num: true, sort: i => i.reorder - total(i.code), html: i => `<b class="text-danger">${Math.max(0, i.reorder - total(i.code))}</b>` },
      { key: "unit", label: "Unit" },
      { key: "act", label: "", nosort: true, html: i => `<a href="#in/${encodeURIComponent(i.code)}" class="btn btn-sm btn-in">${icon("package-import")} Stock IN</a>` }] })}</div>`;
};

/* ---------- masters (read-only: new names are added from the forms where they are first needed) ---------- */
ROUTES.masters = () => {
  setHeader("Setup", "Masters", `<span class="badge bg-secondary-lt align-self-center">Read-only</span>`);
  const box = (title, ic, listKey, where, extra = "") => `<div class="col-md-6 col-xl-4"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon(ic)} ${title}</h3>
      <span class="badge bg-secondary-lt ms-auto">${DB[listKey].length}</span></div>
    <div class="list-group list-group-flush">${DB[listKey].map(x => `<div class="list-group-item">${esc(x)}</div>`).join("")}${extra}</div>
    <div class="card-footer text-secondary small">${icon("pencil-plus", "me-1")}New ones are added from ${where}.</div></div></div>`;
  view().innerHTML = `<div class="alert alert-info">${icon("info-circle", "me-2")}These lists fill up as you work. When a location, company or type is not in a
      dropdown yet, type it there and pick <b>＋ Add … as new</b>. It is saved for next time. Nothing can be added or removed on this page.</div>
    <div class="row row-cards">${box("Locations", "map-pin", "locations", "Stock IN (Into location), Transfer (To location) and Settle batch",
      `<div class="list-group-item d-flex align-items-center text-secondary">${icon("recycle", "me-2")}${esc(DB.defStore)}
        <span class="badge st st-done ms-auto" title="Only the defectives screens post here.">${icon("lock")}System</span></div>`)}
    ${box("Companies / suppliers", "building-store", "companies", "the item form, Stock IN (Supplier) and New complaint")}
    ${box("Fitting types", "bulb", "fittingTypes", "the item form")}${box("Spare types", "category", "spareTypes", "the item form")}
    <div class="col-md-6 col-xl-4"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("users")} Users</h3></div><div class="list-group list-group-flush">
      <div class="list-group-item"><span class="avatar avatar-xs bg-blue-lt me-2">AD</span> Admin <span class="text-secondary small d-block">Everything, incl. users</span></div>
      <div class="list-group-item"><span class="avatar avatar-xs bg-blue-lt me-2">OF</span> Office <span class="text-secondary small d-block">Stock IN / OUT / transfer / adjust, items, complaints, defectives</span></div>
    </div></div></div></div>`;
};

ROUTES.in = a => entryForm("in", a);
ROUTES.out = a => entryForm("out", a);
ROUTES.transfer = a => entryForm("trf", a);
ROUTES.adjust = a => entryForm("adj", a);
