/* Screens: dashboard, current stock, items (+ add/edit), item card, movements, entry detail, low stock, masters. */

const view = () => document.getElementById("view");
let flash = null;
const setFlash = msg => { flash = msg; };
const flashHtml = () => { if (!flash) return ""; const f = flash; flash = null; return `<div class="flash" role="status">${f}</div>`; };
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
function openDlg(html) { document.getElementById("dlg-body").innerHTML = html; document.getElementById("dlg").showModal(); }
function closeDlg() { document.getElementById("dlg").close(); }
const pill = e => `<span class="pill k-${e.kind}">${KIND[e.kind]}</span>`;
const codeLink = c => `<a class="code" href="#item/${encodeURIComponent(c)}">${esc(c)}</a>`;
const entryLink = no => `<a class="code" href="#entry/${no}">${no}</a>`;
const qtyCell = (q, i, cls = "") => `<td class="num ${cls}">${q === 0 ? `<span class="zero">0</span>` : q}</td>`;
// Mockup: Export buttons download the sample files made by make_sample_exports.py from the same demo data.
const exportBtn = (file, label = "⬇ Export to Excel") =>
  `<a role="button" class="secondary" href="exports/${file}" download title="Downloads a neatly formatted .xlsx (sample file in this mockup)">${label}</a>`;

/* ---------- dashboard ---------- */
function screenDash() {
  const low = DB.items.filter(i => i.active && isLow(i));
  const todayN = DB.entries.filter(e => e.date === today()).length;
  const units = loc => { const t = {}; for (const i of DB.items) { const q = balance(i.code, loc); if (q) t[i.unit] = (t[i.unit] || 0) + q; }
    return Object.entries(t).map(([u, q]) => `${q} ${u}`).join(" · ") || "0"; };
  view().innerHTML = `${flashHtml()}<div class="page-head"><h1>Stock dashboard</h1><span class="muted">${fmt(today())}</span></div>
    <div class="big-actions">
      <a href="#in" role="button" class="btn-in">⬇ Stock IN<small>Material received</small></a>
      <a href="#out" role="button" class="btn-out">⬆ Stock OUT<small>Material issued</small></a>
      <a href="#transfer" role="button" class="b-move">⇄ Transfer<small>Between locations</small></a>
      <a href="#adjust" role="button" class="b-adj">± Adjust<small>Correct a count</small></a>
    </div>
    <div class="tiles">
      ${DB.locations.map(l => `<a class="tile" href="#stock/${encodeURIComponent(l)}"><div class="lbl">${esc(l)}</div><div class="num">${units(l)}</div></a>`).join("")}
      <a class="tile ${low.length ? "warn" : ""}" href="#low"><div class="lbl">Low stock</div><div class="num">${low.length}</div><div class="lbl">items at or below reorder level</div></a>
      <a class="tile" href="#moves"><div class="lbl">Entries today</div><div class="num">${todayN}</div></a>
    </div>
    <section class="card"><div class="page-head"><h2>Recent entries</h2><a href="#moves">All movements →</a></div>${entriesTable(byDateDesc(DB.entries).slice(0, 8))}</section>`;
}
function entriesTable(list) {
  return `<div class="table-wrap"><table class="data striped"><thead><tr><th>Entry</th><th>Date</th><th>Type</th><th>Details</th><th>Items</th>
    <th>Location</th><th>Supplier / issued to</th><th>By</th></tr></thead><tbody>
    ${list.map(e => `<tr class="${undoneBy(e.no) ? "undone" : ""}"><td>${entryLink(e.no)}</td><td class="nowrap">${fmt(e.date)}</td><td>${pill(e)}</td><td>${esc(entryWhat(e))}</td>
      <td>${e.lines.length === 1 || e.kind === "TRF" && e.lines.length === 2 ? `<span class="code">${esc(e.lines[0].code)}</span> × ${Math.abs(e.lines[0].qty)}` : `${uniq(e.lines.map(l => l.code)).length} items`}</td>
      <td>${esc(entryLocs(e))}</td><td>${esc(e.party || "")}</td><td>${esc(e.by)}</td></tr>`).join("") || `<tr><td colspan="8">No entries.</td></tr>`}</tbody></table></div>`;
}

/* ---------- current stock ---------- */
let sf = { loc: "", type: "", company: "", q: "", low: false };
function screenStock(arg) {
  if (arg !== undefined) sf = { loc: DB.locations.includes(arg) ? arg : "", type: "", company: "", q: "", low: false };
  const q = norm(sf.q), k = key(sf.q);
  const items = DB.items.filter(i => i.active && (!sf.type || i.type === sf.type) && (!sf.company || i.company === sf.company)
    && (!q || [i.code, ...i.aliases, i.desc, i.catRef].join(" ").toUpperCase().includes(q) || [i.code, ...i.aliases].some(c => key(c).includes(k)))
    && (!sf.low || isLow(i)) && (sf.loc ? balance(i.code, sf.loc) !== 0 : total(i.code) !== 0 || sf.low));
  const locs = sf.loc ? [sf.loc] : DB.locations;
  view().innerHTML = `<div class="page-head"><h1>Current stock</h1>${exportBtn("Current_Stock.xlsx")}</div>
    <section class="card"><div class="filters">
      <label>Location<select onchange="sf.loc=this.value;route()"><option value="">All locations</option>${opt(DB.locations, sf.loc)}</select></label>
      <label>Spare type<select onchange="sf.type=this.value;route()"><option value="">All types</option>${opt(DB.spareTypes, sf.type)}</select></label>
      <label>Company<select onchange="sf.company=this.value;route()"><option value="">All companies</option>${opt(DB.companies, sf.company)}</select></label>
      <label>Search<input type="search" value="${esc(sf.q)}" placeholder="Code, old spelling, fitting…" onchange="sf.q=this.value;route()"></label>
      <label class="check"><input type="checkbox" ${sf.low ? "checked" : ""} onchange="sf.low=this.checked;route()"> Only low stock</label>
    </div></section>
    <section class="card"><p class="muted">${items.length} items</p><div class="table-wrap"><table class="data striped"><thead><tr>
      <th>Item code</th><th>Spare type</th><th>Description</th><th>Used in (fitting)</th><th>Company</th>
      ${locs.map(l => `<th class="num">${esc(l)}</th>`).join("")}${sf.loc ? "" : `<th class="num">Total</th>`}<th>Unit</th></tr></thead><tbody>
      ${items.map(i => `<tr><td>${codeLink(i.code)}</td><td>${esc(i.type)}</td><td>${esc(i.desc)}</td>
        <td>${i.catRef && i.catRef !== i.code ? `<span class="code">${esc(i.catRef)}</span><br><span class="muted">${esc(i.fittingType)}</span>` : esc(i.fittingType)}</td><td>${esc(i.company)}</td>
        ${locs.map(l => qtyCell(balance(i.code, l))).join("")}${sf.loc ? "" : qtyCell(total(i.code), i, isLow(i) ? "low" : "")}<td>${i.unit}</td></tr>`).join("")
        || `<tr><td colspan="12">Nothing matches these filters.</td></tr>`}</tbody></table></div>
      <p class="muted">Red total = at or below the reorder level.</p></section>`;
}

/* ---------- items ---------- */
let itf = { q: "", type: "", company: "", ftype: "", active: "1" };
function screenItems() {
  const q = norm(itf.q), k = key(itf.q);
  const list = DB.items.filter(i => (!itf.type || i.type === itf.type) && (!itf.company || i.company === itf.company) && (!itf.ftype || i.fittingType === itf.ftype)
    && (itf.active === "" || String(+i.active) === itf.active)
    && (!q || [i.code, ...i.aliases, i.desc, i.catRef].join(" ").toUpperCase().includes(q) || [i.code, ...i.aliases].some(c => key(c).includes(k))));
  view().innerHTML = `${flashHtml()}<div class="page-head"><h1>Items</h1><div class="form-actions" style="margin:0">
      <a href="#item-new" role="button">＋ Add item</a>${exportBtn("Item_List.xlsx")}</div></div>
    <section class="card"><div class="filters">
      <label>Search<input type="search" value="${esc(itf.q)}" placeholder="Code, old spelling, description, fitting" onchange="itf.q=this.value;route()"></label>
      <label>Spare type<select onchange="itf.type=this.value;route()"><option value="">All</option>${opt(DB.spareTypes, itf.type)}</select></label>
      <label>Company<select onchange="itf.company=this.value;route()"><option value="">All</option>${opt(DB.companies, itf.company)}</select></label>
      <label>Fitting type<select onchange="itf.ftype=this.value;route()"><option value="">All</option>${opt(DB.fittingTypes, itf.ftype)}</select></label>
      <label>Status<select onchange="itf.active=this.value;route()">${opt([["1", "Active"], ["0", "Inactive"], ["", "All"]], itf.active)}</select></label>
    </div></section>
    <section class="card"><p class="muted">${list.length} items</p><div class="table-wrap"><table class="data striped"><thead><tr>
      <th>Item code</th><th>Spare type</th><th>Description</th><th>Product cat ref</th><th>Fitting type</th><th class="num">W</th>
      <th>Company</th><th>Unit</th><th class="num">Reorder at</th><th class="num">In stock</th><th></th></tr></thead><tbody>
      ${list.map(i => `<tr><td>${codeLink(i.code)}${i.aliases.length ? `<br><span class="muted">also: ${esc(i.aliases.join(", "))}</span>` : ""}</td>
        <td>${esc(i.type)}</td><td>${esc(i.desc)}</td><td class="code">${esc(i.catRef)}</td><td>${esc(i.fittingType)}</td><td class="num">${i.watt ?? ""}</td>
        <td>${esc(i.company)}</td><td>${i.unit}</td><td class="num">${i.reorder}</td>${qtyCell(total(i.code), i, isLow(i) ? "low" : "")}
        <td><a href="#item-edit/${encodeURIComponent(i.code)}">Edit</a></td></tr>`).join("")}</tbody></table></div></section>`;
}
function screenItemForm(code) {
  const it = code ? item(code) : null;
  if (code && !it) { view().innerHTML = "<p>Item not found.</p>"; return; }
  view().innerHTML = `<div class="page-head"><h1>${it ? `Edit item <span class="code">${esc(it.code)}</span>` : "＋ Add item"}</h1></div>
    <form novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveItemPage(${it ? `'${esc(it.code)}'` : "null"})">
      <section class="card">${itemFields(it ? { ...it, originalCode: it.code } : {})}
        ${it ? `<label><input type="checkbox" id="it-active" role="switch" ${it.active ? "checked" : ""}> Active (untick to hide from entry forms; history is kept)</label>` : ""}</section>
      <div id="form-error"></div>
      <div class="form-actions"><button type="submit">Save item</button><a href="${it ? `#item/${encodeURIComponent(it.code)}` : "#items"}" role="button" class="secondary outline">Cancel</a></div>
    </form>`;
}
function saveItemPage(original) {
  const d = readItemFields(), err = saveItem(d, original || undefined);
  if (err) { field("form-error").innerHTML = `<div class="flash bad" role="alert">${esc(err)}</div>`; return; }
  if (original) item(norm(d.code)).active = field("it-active").checked;
  setFlash(`Item <b>${esc(norm(d.code))}</b> saved.`);
  go(`#item/${encodeURIComponent(norm(d.code))}`);
}

/* ---------- item card with date-range history ---------- */
let hf = { from: "", to: "", loc: "" };
function screenItem(code) {
  const i = item(code);
  if (!i) { view().innerHTML = "<p>Item not found.</p>"; return; }
  if (hf.code !== code) hf = { code, from: addDays(today(), -30), to: today(), loc: "" };
  const run = {}, rows = [];
  for (const e of DB.entries) for (const l of e.lines) if (l.code === code) {
    run[l.loc] = (run[l.loc] || 0) + l.qty;
    if (e.date >= hf.from && e.date <= hf.to && (!hf.loc || l.loc === hf.loc)) rows.push({ e, l, after: run[l.loc] });
  }
  const fact = (k, v) => v ? `<div><dt>${k}</dt><dd>${v}</dd></div>` : "";
  view().innerHTML = `${flashHtml()}<div class="page-head"><div><h1 class="code">${esc(i.code)}</h1><span class="muted">${esc(i.type)} · ${esc(i.desc)}</span></div>
      <div class="form-actions" style="margin:0"><a href="#in/${encodeURIComponent(code)}" role="button" class="btn-in">⬇ Stock IN</a>
      <a href="#out/${encodeURIComponent(code)}" role="button" class="btn-out">⬆ Stock OUT</a>
      <a href="#item-edit/${encodeURIComponent(code)}" role="button" class="secondary outline">Edit item</a></div></div>
    <section class="card"><dl class="facts">${fact("Spare type", esc(i.type))}${fact("Used in fitting", i.catRef && i.catRef !== i.code ? `<span class="code">${esc(i.catRef)}</span>` : "")}
      ${fact("Fitting type", esc(i.fittingType))}${fact("Wattage", i.watt ? i.watt + " W" : "")}${fact("Current", i.ma ? i.ma + " mA" : "")}
      ${fact("Company", esc(i.company))}${fact("Unit", i.unit)}${fact("Reorder level", `${i.reorder} ${i.unit}`)}
      ${fact("Other spellings", esc(i.aliases.join(", ")))}${fact("Status", i.active ? "Active" : "Inactive")}</dl></section>
    <section class="card"><h2>Stock by location</h2><div class="table-wrap"><table class="data"><thead><tr>${DB.locations.map(l => `<th class="num">${esc(l)}</th>`).join("")}
      <th class="num">Total</th></tr></thead><tbody><tr>${DB.locations.map(l => qtyCell(balance(code, l))).join("")}${qtyCell(total(code), i, isLow(i) ? "low" : "")}</tr></tbody></table></div></section>
    <section class="card"><div class="page-head"><h2>Movement history</h2>${exportBtn("Stock_Movements.xlsx", "⬇ Export history")}</div>
      <div class="filters">
        <label>From date<input type="date" value="${hf.from}" max="${today()}" onchange="hf.from=this.value;route()"></label>
        <label>To date<input type="date" value="${hf.to}" max="${today()}" onchange="hf.to=this.value;route()"></label>
        <label>Location<select onchange="hf.loc=this.value;route()"><option value="">All locations</option>${opt(DB.locations, hf.loc)}</select></label>
      </div>
      <div class="table-wrap"><table class="data striped"><thead><tr><th>Date</th><th>Entry</th><th>Type</th><th>Location</th><th class="num">In</th><th class="num">Out</th>
        <th class="num">Balance at location</th><th>Supplier / issued to</th><th>Ref</th><th>By</th></tr></thead><tbody>
        ${rows.reverse().map(({ e, l, after }) => `<tr class="${undoneBy(e.no) ? "undone" : ""}"><td class="nowrap">${fmt(e.date)}</td><td>${entryLink(e.no)}</td><td>${pill(e)}</td><td>${esc(l.loc)}</td>
          <td class="num ok">${l.qty > 0 ? l.qty : ""}</td><td class="num low">${l.qty < 0 ? -l.qty : ""}</td><td class="num"><b>${after}</b></td>
          <td>${esc(e.party || e.reason || "")}</td><td>${esc(e.ref || "")}</td><td>${esc(e.by)}</td></tr>`).join("") || `<tr><td colspan="10">No movements in this period.</td></tr>`}
      </tbody></table></div></section>`;
}

/* ---------- movements register ---------- */
let mf = { from: "", to: "", kind: "", loc: "", q: "" };
function screenMoves() {
  if (!mf.from) mf = { ...mf, from: addDays(today(), -30), to: today() };
  const q = norm(mf.q);
  const rows = [];
  for (const e of byDateDesc(DB.entries).reverse()) {
    if (e.date < mf.from || e.date > mf.to || (mf.kind && e.kind !== mf.kind)) continue;
    for (const l of e.lines) {
      if ((mf.loc && l.loc !== mf.loc) || (q && ![l.code, e.party, e.ref, e.no].join(" ").toUpperCase().includes(q))) continue;
      rows.push({ e, l });
    }
  }
  view().innerHTML = `<div class="page-head"><h1>Stock movements</h1>${exportBtn("Stock_Movements.xlsx")}</div>
    <section class="card"><div class="filters">
      <label>From date<input type="date" value="${mf.from}" max="${today()}" onchange="mf.from=this.value;route()"></label>
      <label>To date<input type="date" value="${mf.to}" max="${today()}" onchange="mf.to=this.value;route()"></label>
      <label>Type<select onchange="mf.kind=this.value;route()"><option value="">All types</option>${opt(Object.entries(KIND), mf.kind)}</select></label>
      <label>Location<select onchange="mf.loc=this.value;route()"><option value="">All locations</option>${opt(DB.locations, mf.loc)}</select></label>
      <label>Search<input type="search" value="${esc(mf.q)}" placeholder="Item, supplier, customer, ref" onchange="mf.q=this.value;route()"></label>
    </div></section>
    <section class="card"><p class="muted">${rows.length} lines from ${fmt(mf.from)} to ${fmt(mf.to)}</p><div class="table-wrap"><table class="data striped"><thead><tr>
      <th>Date</th><th>Entry</th><th>Type</th><th>Item code</th><th>Description</th><th>Location</th><th class="num">In</th><th class="num">Out</th><th>Unit</th>
      <th>Supplier / issued to</th><th>Ref</th><th>By</th></tr></thead><tbody>
      ${rows.reverse().map(({ e, l }) => `<tr class="${undoneBy(e.no) ? "undone" : ""}"><td class="nowrap">${fmt(e.date)}</td><td>${entryLink(e.no)}</td><td>${pill(e)}</td><td>${codeLink(l.code)}</td>
        <td>${esc(item(l.code).desc)}</td><td>${esc(l.loc)}</td><td class="num ok">${l.qty > 0 ? l.qty : ""}</td><td class="num low">${l.qty < 0 ? -l.qty : ""}</td>
        <td>${unitOf(l.code)}</td><td>${esc(e.party || e.reason || "")}</td><td>${esc(e.ref || "")}</td><td>${esc(e.by)}</td></tr>`).join("") || `<tr><td colspan="12">No movements in this period.</td></tr>`}
    </tbody></table></div><p class="muted">Struck-through rows were undone (an "Undo" entry reverses them).</p></section>`;
}

/* ---------- entry detail + undo ---------- */
function screenEntry(no) {
  const e = entry(no);
  if (!e) { view().innerHTML = "<p>Entry not found.</p>"; return; }
  const u = undoneBy(no);
  const fact = (k, v) => v ? `<div><dt>${k}</dt><dd>${v}</dd></div>` : "";
  view().innerHTML = `${flashHtml()}<div class="page-head"><div><h1><span class="code">${e.no}</span> ${pill(e)}</h1><span class="muted">${esc(entryWhat(e))}</span></div>
      <div class="form-actions" style="margin:0">${!u && e.kind !== "REV" ? `<button class="secondary outline" onclick="askUndo('${e.no}')">↶ Undo this entry</button>` : ""}
      <a href="#moves" role="button" class="secondary outline">All movements</a></div></div>
    ${u ? `<div class="flash bad">This entry was undone by ${entryLink(u.no)} on ${fmt(u.date)}: ${esc(u.note)}</div>` : ""}
    ${e.reverses ? `<div class="flash">This entry reverses ${entryLink(e.reverses)}.</div>` : ""}
    <section class="card"><dl class="facts">${fact("Date", fmt(e.date))}${fact(e.kind === "IN" ? "Received from" : e.kind === "OUT" ? "Issued to" : e.kind === "TRF" ? "To" : "", esc(e.party || ""))}
      ${fact("Location", esc(entryLocs(e)))}${fact("DC / ref no.", esc(e.ref || ""))}${fact("Reason", esc(e.reason || ""))}${fact("Remarks / note", esc(e.note || ""))}${fact("Entered by", esc(e.by))}</dl></section>
    <section class="card"><h2>Items</h2><div class="table-wrap"><table class="data striped"><thead><tr><th>Item code</th><th>Description</th><th>Location</th>
      <th class="num">In</th><th class="num">Out</th><th>Unit</th><th>Batch code</th><th>PKD</th></tr></thead><tbody>
      ${e.lines.map(l => `<tr><td>${codeLink(l.code)}</td><td>${esc(item(l.code).desc)}</td><td>${esc(l.loc)}</td><td class="num ok">${l.qty > 0 ? l.qty : ""}</td>
        <td class="num low">${l.qty < 0 ? -l.qty : ""}</td><td>${unitOf(l.code)}</td><td>${esc(l.batch || "")}</td><td>${fmtMonth(l.pkd)}</td></tr>`).join("")}</tbody></table></div></section>
    <p class="muted">Entries are never edited or deleted. "Undo" adds an opposite entry with a reason, so the history always shows what happened.</p>`;
}
function askUndo(no) {
  openDlg(`<header><strong>Undo ${no}?</strong></header><p>This adds a new entry that reverses every line of ${no}.</p>
    <label>Reason <span class="req">*</span><input id="undo-reason" placeholder="e.g. Entered against the wrong job"></label><p id="undo-err" class="err"></p>
    <footer><button class="secondary" onclick="closeDlg()">Keep it</button><button onclick="doUndo('${no}')">Undo entry</button></footer>`);
}
function doUndo(no) {
  const err = undo(no, document.getElementById("undo-reason").value);
  if (err) { document.getElementById("undo-err").textContent = err; return; }
  closeDlg(); setFlash(`${no} undone. A reversing entry was added.`); route();
}

/* ---------- low stock ---------- */
function screenLow() {
  const list = DB.items.filter(i => i.active && isLow(i));
  view().innerHTML = `<div class="page-head"><h1>Low stock</h1>${exportBtn("Low_Stock.xlsx")}</div>
    <section class="card"><p class="muted">${list.length} items are at or below their reorder level (total across all locations).</p><div class="table-wrap"><table class="data striped"><thead><tr>
      <th>Item code</th><th>Spare type</th><th>Description</th><th>Company</th>${DB.locations.map(l => `<th class="num">${esc(l)}</th>`).join("")}
      <th class="num">Total</th><th class="num">Reorder at</th><th class="num">Short by</th><th>Unit</th><th></th></tr></thead><tbody>
      ${list.map(i => `<tr><td>${codeLink(i.code)}</td><td>${esc(i.type)}</td><td>${esc(i.desc)}</td><td>${esc(i.company)}</td>${DB.locations.map(l => qtyCell(balance(i.code, l))).join("")}
        ${qtyCell(total(i.code), i, "low")}<td class="num">${i.reorder}</td><td class="num low">${Math.max(0, i.reorder - total(i.code))}</td><td>${i.unit}</td>
        <td><a href="#in/${encodeURIComponent(i.code)}">Stock IN</a></td></tr>`).join("") || `<tr><td colspan="12">Nothing is low. 🎉</td></tr>`}</tbody></table></div></section>`;
}

/* ---------- masters ---------- */
function screenMasters() {
  const box = (title, listKey, ph) => `<section class="card"><h2>${title}</h2><div class="chips">${DB[listKey].map(x => `<span class="chip">${esc(x)}</span>`).join("")}</div>
    <form class="inline-add" style="margin-top:1rem" onsubmit="event.preventDefault();addMaster('${listKey}',this.v)"><input name="v" placeholder="${ph}" required><button>Add</button></form></section>`;
  view().innerHTML = `${flashHtml()}<div class="page-head"><h1>Masters</h1><span class="muted">Admin only in the real app</span></div>
    <div class="masters">${box("Locations", "locations", "New location")}${box("Companies / suppliers", "companies", "New company")}
      ${box("Fitting types", "fittingTypes", "New fitting type")}${box("Spare types", "spareTypes", "New spare type")}
      <section class="card"><h2>Users</h2><table class="data"><tbody><tr><td>Admin</td><td>Admin: everything, incl. masters and users</td></tr>
        <tr><td>Office</td><td>Office staff: stock IN / OUT / transfer / adjust, items</td></tr></tbody></table></section></div>`;
}
function addMaster(listKey, input) {
  const v = input.value.trim();
  if (DB[listKey].some(x => x.toLowerCase() === v.toLowerCase())) { alert(`${v} already exists.`); return; }
  DB[listKey].push(v); setFlash(`Added ${esc(v)}.`); route();
}

/* ---------- router ---------- */
const ROUTES = { dash: screenDash, in: a => entryForm("in", a), out: a => entryForm("out", a), transfer: a => entryForm("trf", a), adjust: a => entryForm("adj", a),
  stock: screenStock, items: screenItems, "item-new": () => screenItemForm(), "item-edit": screenItemForm, item: screenItem,
  moves: screenMoves, entry: screenEntry, low: screenLow, masters: screenMasters };
function route() {
  const [name, ...rest] = (location.hash.slice(1) || "dash").split("/");
  const arg = rest.length ? decodeURIComponent(rest.join("/")) : undefined;
  const navName = { "item-new": "items", "item-edit": "items", item: "items", entry: "moves" }[name] || name;
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.getAttribute("href") === "#" + navName));
  document.body.classList.remove("menu-open");
  (ROUTES[name] || screenDash)(arg);
  window.scrollTo(0, 0);
}
loadData().then(() => { window.addEventListener("hashchange", route); route(); });
