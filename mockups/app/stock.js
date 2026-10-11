/* System ① Stock Management: Stock IN / OUT / Transfer / Undo, current stock, item card, register. */

SUBNAV.stock = () => isTech()
  ? [["#stock/list", "Current stock"], ["#stock/register", "Register"]]
  : [["#stock", "Dashboard"], ["#stock/in", "⬇ Stock IN"], ["#stock/out", "⬆ Stock OUT"], ["#stock/transfer", "⇄ Transfer"],
     ["#stock/list", "Current stock"], ["#stock/register", "Register"]];

const entryBadge = e => e.reverses ? `<span class="badge b-REV">UNDO</span>`
  : `<span class="badge b-${DOC[e.type].dir}">${DOC[e.type].dir === "MOVE" ? "TRANSFER" : DOC[e.type].dir}</span>`;
const entryWhat = e => e.reverses ? `Undo of ${e.reverses}` : DOC[e.type].label;
const ENTRY_HEAD = `<tr><th>Entry</th><th>Date</th><th>What</th><th>Location</th><th class="num">Lines</th>
  <th class="num">Qty</th><th>Ref / party</th><th>By</th></tr>`;
const entryRows = list => list.map(e => `<tr class="${isReversed(e) ? "reversed" : ""}">
  <td>${entryLink(e.no)}</td><td>${e.date}</td><td>${entryBadge(e)} ${esc(entryWhat(e))}
  ${DOC[e.type].system ? ` <span class="muted">(defective)</span>` : ""}</td>
  <td>${esc(uniq(e.lines.map(l => l.loc)).join(" → "))}</td><td class="num">${e.lines.length}</td>
  <td class="num">${entryQty(e)} NOS</td><td>${esc(e.party || e.ref || "")}</td><td>${esc(e.by)}</td></tr>`).join("");

ROUTES.stock = () => {
  if (isTech()) return go("#stock/list");
  const low = ITEMS.filter(i => i.reorder > 0 && totalBalance(i.code, "FRESH") <= i.reorder);
  view().innerHTML = `${flashHtml()}<h1>① Stock</h1>
    <div class="bigbtns">
      <a href="#stock/in" role="button" class="btn-in">⬇ Stock IN<small>Receive fresh from Wipro</small></a>
      <a href="#stock/out" role="button" class="btn-out">⬆ Stock OUT<small>Issue to site · scrap</small></a>
      <a href="#stock/transfer" role="button" class="secondary">⇄ Transfer<small>Between locations</small></a>
      <a href="#stock/list" role="button" class="contrast">📋 Current stock<small>Fresh · defective · low</small></a>
    </div>
    <div class="tiles">
      <a href="#stock/list"><article><div class="num">${sum(ITEMS, i => totalBalance(i.code, "FRESH"))}</div>NOS fresh in stock</article></a>
      <a href="#stock/list/DEFECTIVE"><article><div class="num">${sum(ITEMS, i => totalBalance(i.code, "DEFECTIVE"))}</div>NOS defective at office</article></a>
      <a href="#stock/list/low"><article><div class="num ${low.length ? "bad" : ""}">${low.length}</div>items at / below reorder level</article></a>
      <a href="#stock/register"><article><div class="num">${entries.filter(e => e.date === today()).length}</div>entries today</article></a>
    </div>
    <h3 style="margin-top:2rem">Recent entries</h3>
    <div class="table-wrap"><table class="striped"><thead>${ENTRY_HEAD}</thead><tbody>${entryRows(entries.slice(-6).reverse())}</tbody></table></div>
    <a href="#stock/register">See all entries →</a>`;
};

/* ------------------------------ Stock IN / OUT / Transfer form ------------------------------ */
let stForm = null;
function stockForm(mode, prefill) {
  if (isTech()) return go("#stock/list");
  const fresh = !stForm || stForm.mode !== mode || prefill !== undefined;
  if (fresh) stForm = { mode, type: { in: "RECEIVED_FROM_WIPRO", out: "ISSUED_TO_COMPLAINT", transfer: "TRANSFER" }[mode],
    date: today(), loc: "Vizag Office", to: "TV Shop", ref: "", party: "", note: "" };
  const f = stForm, d = DOC[f.type], isIn = d.dir === "IN", isOut = d.dir === "OUT", isMove = d.dir === "MOVE";
  const choices = isMove ? "" : Object.entries(DOC).filter(([, x]) => x.dir === d.dir && !x.system).map(([t, x]) =>
    `<label><input type="radio" name="type" value="${t}" ${t === f.type ? "checked" : ""} onchange="stSet('type',this.value)">
      <strong>${x.label}</strong><small>${x.hint}</small></label>`).join("");
  const refLabel = { RECEIVED_FROM_WIPRO: "Wipro DC / invoice no.", OPENING: "Reference (e.g. count sheet)" }[f.type];
  const openCmp = complaints.filter(c => c.status !== "CLOSED");
  view().innerHTML = `
    <h1>${isIn ? "⬇ Stock IN" : isOut ? "⬆ Stock OUT" : "⇄ Transfer"} <span class="muted">(fresh stock)</span></h1>
    ${choices ? `<p class="muted">What are you doing?</p><div class="choices">${choices}</div>` : ""}
    <div class="fields">
      <label>Date <input value="${f.date}" onchange="stSet('date',this.value,true)" placeholder="DD-MM-YYYY"></label>
      <label>${isIn ? "Into location" : "From location"} <select onchange="stSet('loc',this.value)">${opts(LOCATIONS, f.loc)}</select></label>
      ${isMove ? `<label>To location <select onchange="stSet('to',this.value)">${opts(LOCATIONS, f.to)}</select></label>` : ""}
      ${refLabel ? `<label>${refLabel} <input value="${esc(f.ref)}" onchange="stSet('ref',this.value,true)"></label>` : ""}
      ${f.type === "ISSUED_TO_COMPLAINT" ? `<label>For complaint (optional) <select onchange="stSet('party',this.value,true)">
        <option value="">— not for a complaint —</option>${opts(openCmp.map(c => [c.ticket, `${c.ticket} · ${c.customer}`]), f.party)}</select></label>` : ""}
      ${f.type === "SCRAPPED" || isMove ? `<label>${f.type === "SCRAPPED" ? "Reason (required)" : "Note"}
        <input value="${esc(f.note)}" onchange="stSet('note',this.value,true)"></label>` : ""}
    </div>
    <h3>Items</h3>
    ${lineEditor("st-lines", { reset: fresh, prefill, create: isIn, extra: isIn ? ["batch", "pkd"] : [],
      avail: isIn ? null : () => ({ loc: stForm.loc, bucket: "FRESH" }) })}
    <div id="st-error"></div>
    <div class="actions" style="margin-top:1rem">
      <button class="${isIn ? "btn-in" : isOut ? "btn-out" : ""}" onclick="stSave()">Save ${isIn ? "Stock IN" : isOut ? "Stock OUT" : "transfer"}</button>
      <a href="#stock" role="button" class="secondary outline">Cancel</a>
    </div>
    <article class="muted" style="margin-top:1.5rem">♻ <strong>Defective parts?</strong> Failed parts are tracked piece by piece in
      <a href="#def/record">② Defective pieces → Record defectives</a>. Returns to Wipro happen there too, so defective stock is never typed in twice.</article>`;
  edRender("st-lines");
}
function stSet(k, v, quiet) { stForm[k] = v; if (!quiet) { stockForm(stForm.mode); } }
function stSave() {
  const f = stForm, d = DOC[f.type];
  if (!/^\d{2}-\d{2}-\d{4}$/.test(f.date)) return formError("st-error", "Date must be DD-MM-YYYY.");
  if (f.type === "SCRAPPED" && !f.note.trim()) return formError("st-error", "Please give a reason for scrapping.");
  if (d.dir === "MOVE" && f.loc === f.to) return formError("st-error", "Choose two different locations.");
  const r = edCollect("st-lines"); if (r.error) return formError("st-error", r.error);
  const lines = r.lines.flatMap(l => {
    const base = { code: l.code, bucket: "FRESH", batch: l.batch, pkd: l.pkd };
    return d.dir === "IN" ? [{ ...base, loc: f.loc, qty: l.qty }] : d.dir === "OUT" ? [{ ...base, loc: f.loc, qty: -l.qty }]
      : [{ ...base, loc: f.loc, qty: -l.qty }, { ...base, loc: f.to, qty: l.qty }];
  });
  const c = complaint(f.party);
  const e = { type: f.type, date: f.date, ref: f.ref || (c ? c.ticket : ""), party: c ? `${c.customer} · ${c.ticket}` : "", note: f.note, lines };
  const err = post(e); if (err) return formError("st-error", err + " Nothing was saved.");
  setFlash(`Saved <strong>${e.no}</strong>: ${r.lines.length} line(s), ${entryQty(e)} NOS. Stock updated.`);
  stForm = null; go(`#stock/entry/${e.no}`);
}
ROUTES["stock/in"] = a => stockForm("in", a);
ROUTES["stock/out"] = a => stockForm("out", a);
ROUTES["stock/transfer"] = a => stockForm("transfer", a);

/* ------------------------------ Entry detail + undo ------------------------------ */
ROUTES["stock/entry"] = no => {
  const e = entry(no);
  if (!e) { view().innerHTML = "<p>Entry not found.</p>"; return; }
  const undoneBy = entries.find(x => x.reverses === e.no), linked = pieces.filter(p => p.entries.includes(e.no) || p.replacement === e.no);
  view().innerHTML = `${flashHtml()}
    <h1><span class="code">${e.no}</span> ${entryBadge(e)}</h1>
    <p><strong>${esc(entryWhat(e))}</strong> · ${e.date} · by ${esc(e.by)}${e.ref ? ` · Ref: ${esc(e.ref)}` : ""}
      ${e.party ? ` · ${esc(e.party)}` : ""}${e.note ? `<br><span class="muted">${esc(e.note)}</span>` : ""}</p>
    ${undoneBy ? `<article class="flash err">Undone by ${entryLink(undoneBy.no)}. Both stay on record.</article>` : ""}
    ${e.reverses ? `<p class="muted">Cancels ${entryLink(e.reverses)}.</p>` : ""}
    <div class="table-wrap"><table class="striped"><thead><tr><th>Item</th><th>Location</th><th>Stock</th>
      <th class="num">IN</th><th class="num">OUT</th><th>Batch</th><th>PKD</th></tr></thead><tbody>
      ${e.lines.map(l => `<tr><td>${codeLink(l.code)}</td><td>${l.loc}</td><td>${bucketName(l.bucket)}</td>
        <td class="num good">${l.qty > 0 ? l.qty : ""}</td><td class="num bad">${l.qty < 0 ? -l.qty : ""}</td>
        <td>${esc(l.batch || "")}</td><td>${esc(l.pkd || "")}</td></tr>`).join("")}</tbody></table></div>
    ${linked.length ? `<p>♻ Linked defective pieces: ${linked.slice(0, 12).map(p => `<a class="code" href="#def/piece/${p.tag}">${p.tag}</a>`).join(", ")}
      ${linked.length > 12 ? `and ${linked.length - 12} more` : ""}</p>` : ""}
    <div class="actions">
      <a href="#stock/register" role="button" class="secondary outline">← Register</a>
      ${!undoneBy && !e.reverses && !DOC[e.type].system && !isTech() ? `<button class="secondary" onclick="askUndo('${e.no}')">Undo this entry…</button>` : ""}
    </div>
    <p class="muted">Entries are never edited or deleted. Undo adds an opposite entry.
      ${DOC[e.type].system ? "This is a defective-piece entry: it is managed in ② Defective pieces." : ""}</p>`;
};
function askUndo(no) {
  openDlg(`<header><strong>Undo ${no}?</strong></header><p>This adds a new entry that reverses every line of ${no}.</p>
    <label>Reason (required) <input id="undo-reason" placeholder="e.g. wrong item entered"></label><div id="undo-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Keep it</button><button onclick="doUndo('${no}')">Undo entry</button></footer>`);
}
function doUndo(no) {
  const reason = document.getElementById("undo-reason").value.trim();
  if (!reason) return formError("undo-err", "Please give a reason.");
  const err = undo(no, reason);
  if (err) return formError("undo-err", err + " Cannot undo: that stock has already been used.");
  closeDlg(); setFlash(`${no} undone. A reversing entry was added.`); route();
}

/* ------------------------------ Current stock lists ------------------------------ */
let stockView = { bucket: "FRESH", loc: "", q: "", low: false };
const sheetCol = t => t === "DRIVER" ? 1 : t === "PCB" ? 2 : 0; // FITTING CODE | DRIVER CODE | PCB CODE
ROUTES["stock/list"] = arg => {
  if (arg === "DEFECTIVE") stockView = { ...stockView, bucket: "DEFECTIVE", low: false };
  if (arg === "low") stockView = { ...stockView, bucket: "FRESH", low: true };
  if (arg === "FRESH") stockView = { ...stockView, bucket: "FRESH", low: false };
  const s = stockView, q = key(s.q);
  let rows = [];
  if (s.low) rows = ITEMS.filter(i => i.reorder > 0).map(i => ({ i, loc: "All", q: totalBalance(i.code, "FRESH") })).filter(r => r.q <= r.i.reorder);
  else for (const i of ITEMS) for (const loc of LOCATIONS) {
    const qty = balance(i.code, loc, s.bucket);
    if (qty > 0 && (!s.loc || loc === s.loc) && (!q || key(i.code).includes(q) || i.aliases.some(a => key(a).includes(q)) || i.desc.toUpperCase().includes(s.q.toUpperCase())))
      rows.push({ i, loc, q: qty });
  }
  const tab = (label, on, a) => `<button class="${on ? "" : "secondary"}" onclick="go('#stock/list/${a}')">${label}</button>`;
  view().innerHTML = `<h1>Current stock</h1>
    <div class="tabs">${tab("Fresh List", s.bucket === "FRESH" && !s.low, "FRESH")}${tab("Defective List", s.bucket === "DEFECTIVE", "DEFECTIVE")}${tab("Low stock", s.low, "low")}</div>
    <div class="filters">
      <label>Location <select onchange="stockView.loc=this.value;route()" ${s.low ? "disabled" : ""}><option value="">All locations</option>${opts(LOCATIONS, s.loc)}</select></label>
      <label>Search <input type="search" value="${esc(s.q)}" placeholder="code, old spelling or description" onchange="stockView.q=this.value;route()"></label>
      <button class="secondary" onclick="exportPreview()">⬇ Export to Excel</button>
    </div>
    <p class="muted">${rows.length} rows · ${sum(rows, r => r.q)} NOS ${s.low ? "· items at or below reorder level (all locations)" : ""}
      ${s.bucket === "DEFECTIVE" ? "· each defective is tracked as a piece in ② Defective pieces" : ""}</p>
    <div class="table-wrap"><table class="striped"><thead><tr><th>S.NO</th><th>FITTING CODE</th><th>DRIVER CODE</th><th>PCB CODE</th>
      <th class="num">QUANTITY</th><th>${s.low ? "REORDER AT" : "LOCATION"}</th><th></th></tr></thead><tbody>
      ${rows.map((r, n) => { const cells = ["", "", ""]; cells[sheetCol(r.i.type)] = codeLink(r.i.code);
        const low = s.bucket === "FRESH" && r.i.reorder > 0 && r.q <= r.i.reorder;
        return `<tr><td>${n + 1}</td>${cells.map(c => `<td>${c}</td>`).join("")}<td class="num ${low ? "bad" : ""}">${r.q} NOS</td>
          <td>${s.low ? r.i.reorder + " NOS" : r.loc}</td><td>${s.bucket === "DEFECTIVE"
            ? `<a href="#def/pieces/${encodeURIComponent(r.i.code)}" class="small">Pieces</a>`
            : isTech() ? "" : `<a href="#stock/out/${encodeURIComponent(r.i.code)}">OUT</a> · <a href="#stock/in/${encodeURIComponent(r.i.code)}">IN</a>`}</td></tr>`;
      }).join("") || `<tr><td colspan="7">Nothing here.</td></tr>`}</tbody></table></div>`;
};
function exportPreview() {
  const s = stockView, def = s.bucket === "DEFECTIVE";
  const rows = ITEMS.map(i => ({ i, q: s.loc ? balance(i.code, s.loc, s.bucket) : totalBalance(i.code, s.bucket) })).filter(r => r.q > 0).slice(0, 8);
  const head = def ? ["S.NO", "FITTING CODE", "BATCH CODE", "DRIVER CODE", "PCB CODE", "QUANTITY"] : ["S.NO", "FITTING CODE", "BATCH CODE", "PKDT", "DRIVER CODE", "PCB CODE", "QUANTITY"];
  const body = rows.map((r, n) => { const c = ["", "", ""]; c[sheetCol(r.i.type)] = esc(r.i.code);
    return `<tr><td>${n + 1}</td><td>${c[0]}</td><td></td>${def ? "" : "<td></td>"}<td>${c[1]}</td><td>${c[2]}</td><td>${r.q}NOS</td></tr>`; }).join("");
  openDlg(`<header><strong>Excel export preview</strong></header>
    <p class="muted">Downloads <code>${def ? "Defective" : "Fresh"}_List_${s.loc || "All"}_${today()}.xlsx</code> in your sheet layout.</p>
    <div class="table-wrap"><table class="xl"><tr class="title"><td colspan="${head.length}">${def ? "Date : " + today() + "  Defective List" : (s.loc || "All locations") + " Fresh List · " + today()}</td></tr>
      <tr>${head.map(h => `<th>${h}</th>`).join("")}</tr>${body}</table></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Close</button><button onclick="alert('Real app: downloads the .xlsx')">Download .xlsx</button></footer>`);
}

/* ------------------------------ Item card ------------------------------ */
ROUTES["stock/item"] = code => {
  const i = item(code);
  if (!i) { view().innerHTML = "<p>Item not found.</p>"; return; }
  const run = {}, hist = [];
  for (const e of entries) for (const l of e.lines) if (l.code === code) {
    const k = l.loc + "|" + l.bucket; run[k] = (run[k] || 0) + l.qty; hist.push({ e, l, after: run[k] });
  }
  const byStatus = Object.keys(PIECE_STATUS).map(s => [s, pieces.filter(p => p.code === code && p.status === s).length]).filter(x => x[1]);
  view().innerHTML = `<h1 class="code">${esc(i.code)}</h1>
    <p>${esc(TYPE_LABEL[i.type])} · ${esc(i.desc)} · Brand Wipro · Reorder at ${i.reorder} NOS
      ${i.aliases.length ? `<br><span class="muted">Also written as: ${i.aliases.map(esc).join(", ")}</span>` : ""}</p>
    ${isTech() ? "" : `<div class="actions" style="margin-bottom:1rem">
      <a href="#stock/in/${encodeURIComponent(code)}" role="button" class="btn-in">⬇ Stock IN</a>
      <a href="#stock/out/${encodeURIComponent(code)}" role="button" class="btn-out">⬆ Stock OUT</a></div>`}
    <div class="table-wrap"><table><thead><tr><th>Location</th><th class="num">Fresh</th><th class="num">Defective</th></tr></thead><tbody>
      ${LOCATIONS.map(l => `<tr><td>${l}</td><td class="num">${balance(code, l, "FRESH")}</td><td class="num">${balance(code, l, "DEFECTIVE")}</td></tr>`).join("")}
      <tr><th>Total</th><th class="num">${totalBalance(code, "FRESH")}</th><th class="num">${totalBalance(code, "DEFECTIVE")}</th></tr></tbody></table></div>
    ${byStatus.length ? `<p>♻ Defective pieces: ${byStatus.map(([s, n]) => `${pieceBadge(s)} ${n}`).join(" &nbsp; ")}
      ${isTech() ? "" : ` · <a href="#def/pieces/${encodeURIComponent(code)}">see pieces →</a>`}</p>` : ""}
    <h3>History</h3>
    <div class="table-wrap"><table class="striped"><thead><tr><th>Date</th><th>Entry</th><th>What</th><th>Location</th><th>Stock</th>
      <th class="num">IN</th><th class="num">OUT</th><th class="num">Balance</th><th>Ref / party</th><th>By</th></tr></thead><tbody>
      ${hist.reverse().map(({ e, l, after }) => `<tr><td>${e.date}</td><td>${entryLink(e.no)}</td><td>${entryBadge(e)} ${esc(entryWhat(e))}</td>
        <td>${l.loc}</td><td>${bucketName(l.bucket)}</td><td class="num good">${l.qty > 0 ? l.qty : ""}</td>
        <td class="num bad">${l.qty < 0 ? -l.qty : ""}</td><td class="num"><strong>${after}</strong></td>
        <td>${esc(e.party || e.ref || "")}</td><td>${esc(e.by)}</td></tr>`).join("")}</tbody></table></div>
    <p class="muted">Balance = stock left at that location, in that stock type, after the entry.</p>`;
};

/* ------------------------------ Register ------------------------------ */
let regView = { dir: "", loc: "", q: "" };
ROUTES["stock/register"] = () => {
  const s = regView, q = norm(s.q);
  const list = entries.filter(e => (!s.dir || (e.reverses ? "REV" : DOC[e.type].dir) === s.dir) && (!s.loc || e.lines.some(l => l.loc === s.loc)) &&
    (!q || e.no.includes(q) || norm(e.ref).includes(q) || norm(e.party).includes(q) || e.lines.some(l => l.code.includes(q)))).slice().reverse();
  view().innerHTML = `<h1>Register <span class="muted">(every stock entry)</span></h1>
    <div class="filters">
      <label>Show <select onchange="regView.dir=this.value;route()">${opts([["", "All entries"], ["IN", "Stock IN"], ["OUT", "Stock OUT"], ["MOVE", "Transfers"], ["REV", "Undos"]], s.dir)}</select></label>
      <label>Location <select onchange="regView.loc=this.value;route()"><option value="">All locations</option>${opts(LOCATIONS, s.loc)}</select></label>
      <label>Search <input type="search" value="${esc(s.q)}" placeholder="entry no, DC no, customer, item" onchange="regView.q=this.value;route()"></label>
    </div>
    <div class="table-wrap"><table class="striped"><thead>${ENTRY_HEAD}</thead><tbody>${entryRows(list)}</tbody></table></div>
    <p class="muted">Struck-through rows were undone. "(defective)" entries come from ② Defective pieces.</p>`;
};
