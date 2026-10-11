/* System ② Defective Pieces Tracking: every failed part has its own tag and status, grouped into Wipro return batches. */

SUBNAV.def = () => [["#def", "Dashboard"], ["#def/record", "♻ Record defectives"], ["#def/pieces", "Pieces"],
  ["#def/batches", "Return batches"], ["#def/reports", "Reports"]];
const pieceLink = t => `<a class="code" href="#def/piece/${t}">${t}</a>`;
const batchLink = no => no ? `<a class="code" href="#def/batch/${no}">${no}</a>` : "";
const pieceAge = p => daysBetween(p.collectedOn, today());
const sentAge = b => b.sentOn ? daysBetween(b.sentOn, today()) : 0;

ROUTES.def = () => {
  const count = s => pieces.filter(p => p.status === s).length;
  const sent = batches.filter(b => b.status === "SENT");
  const oldest = sent.length ? Math.max(...sent.map(sentAge)) : 0;
  view().innerHTML = `${flashHtml()}<h1>② Defective pieces</h1>
    <div class="bigbtns">
      <a href="#def/record" role="button" class="btn-def">♻ Record defectives<small>Failed parts brought in</small></a>
      <a href="#def/pieces/status:AT_OFFICE" role="button" class="secondary">📦 New return batch<small>Pick pieces to send to Wipro</small></a>
      <a href="#def/batches" role="button" class="contrast">🚚 Return batches<small>Send · results · replacements</small></a>
      <a href="#def/reports" role="button" class="secondary outline">📊 Reports<small>Top failing parts</small></a>
    </div>
    <div class="tiles">
      ${["AT_SITE", "AT_OFFICE", "IN_RETURN_BATCH", "SENT_TO_WIPRO"].map(s => `<a href="#def/pieces/status:${s}"><article>
        <div class="num">${count(s)}</div>${pieceBadge(s)}${s === "SENT_TO_WIPRO" && oldest ? `<br><span class="muted">oldest batch ${oldest} days</span>` : ""}</article></a>`).join("")}
    </div>
    <div class="tiles" style="margin-top:1rem">
      ${["REPLACED", "REJECTED", "SCRAPPED"].map(s => `<a href="#def/pieces/status:${s}"><article><div class="num">${count(s)}</div>${pieceBadge(s)}</article></a>`).join("")}
      <a href="#def/pieces"><article><div class="num">${pieces.length}</div>pieces on record</article></a>
    </div>
    <h3 style="margin-top:2rem">Return batches in progress</h3>
    ${batchTable(batches.filter(b => b.status !== "SETTLED"))}`;
};

/* ------------------------------ Record defectives (bulk → N tagged pieces) ------------------------------ */
let defForm = null;
ROUTES["def/record"] = prefill => {
  const fresh = !defForm || prefill !== undefined;
  if (fresh) defForm = { where: "office", date: today(), loc: "Vizag Office", ticket: "", source: "", by: "Ramu" };
  const f = defForm;
  view().innerHTML = `<h1>♻ Record defective pieces</h1>
    <p class="muted">Each piece gets its own tag (e.g. DEF-${today().slice(8, 10)}${today().slice(3, 5)}-0001). Write it on the part.</p>
    <div class="choices">
      <label><input type="radio" name="where" ${f.where === "office" ? "checked" : ""} onchange="defForm.where='office'">
        <strong>Brought to the office</strong><small>Adds to defective stock now</small></label>
      <label><input type="radio" name="where" ${f.where === "site" ? "checked" : ""} onchange="defForm.where='site'">
        <strong>Known faulty, still at site</strong><small>Mark collected later</small></label>
    </div>
    <div class="fields">
      <label>Date <input value="${f.date}" onchange="defForm.date=this.value"></label>
      <label>Location <select onchange="defForm.loc=this.value">${opts(LOCATIONS, f.loc)}</select></label>
      <label>From complaint <select onchange="defForm.ticket=this.value"><option value="">— none —</option>
        ${opts(complaints.map(c => [c.ticket, `${c.ticket} · ${c.customer}`]), f.ticket)}</select></label>
      <label>…or customer / site <input value="${esc(f.source)}" placeholder="e.g. Dr Reddys, Vizag" onchange="defForm.source=this.value"></label>
      <label>Collected by <select onchange="defForm.by=this.value">${opts([...TECHNICIANS, "Office"], f.by)}</select></label>
    </div>
    <h3>Pieces</h3>
    ${lineEditor("def-lines", { reset: fresh, prefill, create: true, extra: ["fault", "batch", "pkd"] })}
    <div id="def-error"></div>
    <div class="actions" style="margin-top:1rem"><button class="btn-def" onclick="defSave()">Create pieces</button>
      <a href="#def" role="button" class="secondary outline">Cancel</a></div>
    <p class="muted">Batch code and PKD entered here apply to every piece on that line; you can change them per piece on the next screen.</p>`;
  edRender("def-lines");
};
function defSave() {
  const f = defForm, r = edCollect("def-lines");
  if (r.error) return formError("def-error", r.error);
  if (!f.ticket && !f.source.trim()) return formError("def-error", "Pick the complaint, or type the customer / site the pieces came from.");
  const c = complaint(f.ticket), made = [];
  for (const l of r.lines) {
    const res = collectPieces({ code: l.code, qty: l.qty, loc: f.loc, date: f.date, fault: l.fault, batchCode: l.batch, pkd: l.pkd,
      source: c ? `${c.customer} · ${c.ticket}` : f.source, ticket: f.ticket, atSite: f.where === "site", by: f.by });
    if (res.error) return formError("def-error", res.error);
    made.push(...res.pieces);
  }
  lastMade = made.map(p => p.tag); defForm = null;
  setFlash(`Created <strong>${made.length}</strong> piece(s)${f.where === "site" ? " (at site)" : " and added them to defective stock"}.`);
  go("#def/created");
}
let lastMade = [];
ROUTES["def/created"] = () => {
  const list = lastMade.map(piece);
  view().innerHTML = `${flashHtml()}<h1>New pieces</h1>
    <p class="muted">Fill in batch code / PKD per piece if they differ (Wipro warranty claims need them). Changes save as you type.</p>
    <div class="table-wrap"><table class="striped"><thead><tr><th>Tag</th><th>Item</th><th>Status</th><th>Fault</th><th>Batch code</th><th>PKD</th></tr></thead><tbody>
      ${list.map(p => `<tr><td>${pieceLink(p.tag)}</td><td>${codeLink(p.code)}</td><td>${pieceBadge(p.status)}</td><td>${esc(p.fault)}</td>
        <td><input value="${esc(p.batchCode)}" onchange="piece('${p.tag}').batchCode=this.value" style="margin:0;width:9rem"></td>
        <td><input value="${esc(p.pkd)}" placeholder="MM-YYYY" onchange="piece('${p.tag}').pkd=this.value" style="margin:0;width:8rem"></td></tr>`).join("")}
    </tbody></table></div>
    <div class="actions"><button class="secondary" onclick="window.print()">🖨 Print tags</button>
      <a href="#def/record" role="button" class="btn-def">Record more</a><a href="#def/pieces" role="button" class="secondary outline">All pieces</a></div>`;
};

/* ------------------------------ Pieces list with bulk actions ------------------------------ */
let pv = { status: "", code: "", loc: "", q: "", page: 1 }, sel = new Set();
ROUTES["def/pieces"] = arg => {
  if (arg !== undefined) { pv = { status: "", code: "", loc: "", q: "", page: 1 }; sel.clear();
    if (arg.startsWith("status:")) pv.status = arg.slice(7); else pv.code = arg; }
  const q = norm(pv.q);
  const list = pieces.filter(p => (!pv.status || p.status === pv.status) && (!pv.code || p.code === pv.code) && (!pv.loc || p.loc === pv.loc) &&
    (!q || p.tag.includes(q) || norm(p.source).includes(q) || p.code.includes(q) || norm(p.batchCode).includes(q))).slice().reverse();
  const per = 25, pages = Math.max(1, Math.ceil(list.length / per)); pv.page = Math.min(pv.page, pages);
  const shown = list.slice((pv.page - 1) * per, pv.page * per);
  const picked = [...sel].map(piece), st = s => picked.filter(p => p.status === s).length;
  const drafts = batches.filter(b => b.status === "DRAFT");
  view().innerHTML = `${flashHtml()}<h1>Defective pieces</h1>
    <div class="filters">
      <label>Status <select onchange="pv.status=this.value;pv.page=1;route()"><option value="">All statuses</option>${opts(Object.entries(PIECE_STATUS), pv.status)}</select></label>
      <label>Item <select onchange="pv.code=this.value;pv.page=1;route()"><option value="">All items</option>${opts(uniq(pieces.map(p => p.code)), pv.code)}</select></label>
      <label>Location <select onchange="pv.loc=this.value;route()"><option value="">All locations</option>${opts(LOCATIONS, pv.loc)}</select></label>
      <label>Search <input type="search" value="${esc(pv.q)}" placeholder="tag, customer, batch code" onchange="pv.q=this.value;route()"></label>
    </div>
    <article class="actions" id="bulk">
      <strong>${sel.size} selected</strong>
      ${st("AT_OFFICE") ? `<button class="btn-def small" onclick="bulkBatch()">📦 New return batch (${st("AT_OFFICE")})</button>
        ${drafts.map(b => `<button class="secondary small" onclick="bulkAddTo('${b.no}')">Add to ${b.no}</button>`).join("")}
        <button class="secondary outline small" onclick="bulkMove()">Move to…</button>` : ""}
      ${st("AT_SITE") ? `<button class="small" onclick="bulkCollected()">Mark collected (${st("AT_SITE")})</button>` : ""}
      ${st("AT_OFFICE") + st("REJECTED") ? `<button class="secondary outline small" onclick="bulkScrap()">Scrap…</button>` : ""}
      ${sel.size ? `<button class="secondary outline small" onclick="sel.clear();route()">Clear</button>` : `<span class="muted">Tick pieces to act on them.</span>`}
    </article>
    <p class="muted">${list.length} pieces</p>
    <div class="table-wrap"><table class="striped"><thead><tr>
      <th><input type="checkbox" title="Select all on this page" onchange="selAll(sel,[${shown.map(p => `'${p.tag}'`).join(",")}],this.checked)"></th>
      <th>Tag</th><th>Item</th><th>Status</th><th>Location</th><th>From</th><th>Batch code</th><th>PKD</th><th class="num">Age</th><th>Return batch</th></tr></thead><tbody>
      ${shown.map(p => `<tr class="${sel.has(p.tag) ? "sel" : ""}"><td><input type="checkbox" ${sel.has(p.tag) ? "checked" : ""}
          onchange="this.checked?sel.add('${p.tag}'):sel.delete('${p.tag}');route()"></td>
        <td>${pieceLink(p.tag)}</td><td>${codeLink(p.code)}</td><td>${pieceBadge(p.status)}</td><td>${p.loc}</td>
        <td>${p.ticket ? `<a href="#cmp/view/${p.ticket}">${esc(p.source)}</a>` : esc(p.source)}</td><td>${esc(p.batchCode)}</td><td>${esc(p.pkd)}</td>
        <td class="num">${pieceAge(p)} d</td><td>${batchLink(p.batch)}</td></tr>`).join("") || `<tr><td colspan="10">No pieces match.</td></tr>`}
    </tbody></table></div>
    <div class="actions" style="justify-content:center">
      <button class="secondary outline small" onclick="pv.page--;route()" ${pv.page <= 1 ? "disabled" : ""}>‹ Prev</button>
      <span>Page ${pv.page} of ${pages}</span>
      <button class="secondary outline small" onclick="pv.page++;route()" ${pv.page >= pages ? "disabled" : ""}>Next ›</button></div>`;
};
function bulkBatch() {
  const r = createBatch([...sel]); if (r.error) return alert(r.error);
  sel.clear(); setFlash(`Created ${r.batch.no} with ${r.batch.tags.length} pieces. Print the Wipro list, then mark it sent.`); go(`#def/batch/${r.batch.no}`);
}
function bulkAddTo(no) { const n = addToBatch(no, [...sel]); sel.clear(); setFlash(`Added ${n} piece(s) to ${no}.`); go(`#def/batch/${no}`); }
function bulkCollected() { const err = markCollected([...sel], today()); if (err) return alert(err); sel.clear(); setFlash("Pieces marked as collected and added to defective stock."); route(); }
function bulkMove() {
  openDlg(`<header><strong>Move ${sel.size} piece(s)</strong></header>
    <label>To location <select id="mv-to">${opts(LOCATIONS, "Svkml")}</select></label><div id="mv-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button onclick="doMove()">Move</button></footer>`);
}
function doMove() { const err = movePieces([...sel], document.getElementById("mv-to").value); if (err) return formError("mv-err", err);
  closeDlg(); sel.clear(); setFlash("Pieces moved; a defective transfer entry was added to the stock register."); route(); }
function bulkScrap() {
  openDlg(`<header><strong>Scrap ${sel.size} piece(s)?</strong></header><p>Only pieces at the office or rejected by Wipro are scrapped.</p>
    <label>Reason (required) <input id="sc-reason" placeholder="e.g. burnt, beyond repair"></label><div id="sc-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button onclick="doScrap()">Scrap</button></footer>`);
}
function doScrap() { const err = scrapPieces([...sel], document.getElementById("sc-reason").value); if (err) return formError("sc-err", err);
  closeDlg(); sel.clear(); setFlash("Pieces scrapped."); route(); }

/* ------------------------------ Piece detail + timeline ------------------------------ */
ROUTES["def/piece"] = tag => {
  const p = piece(tag);
  if (!p) { view().innerHTML = "<p>Piece not found.</p>"; return; }
  view().innerHTML = `${flashHtml()}<h1><span class="code">${p.tag}</span> ${pieceBadge(p.status)}</h1>
    <div class="fields">
      <p><strong>Item</strong><br>${codeLink(p.code)} · ${esc(item(p.code).desc)}</p>
      <p><strong>From</strong><br>${p.ticket ? `<a href="#cmp/view/${p.ticket}">${esc(p.source)}</a>` : esc(p.source)}</p>
      <p><strong>Location</strong><br>${p.loc}</p>
      <p><strong>Collected</strong><br>${p.collectedOn} by ${esc(p.collectedBy)}</p>
      <p><strong>Fault</strong><br>${esc(p.fault) || "—"}</p>
      <p><strong>Batch code / PKD</strong><br>${esc(p.batchCode) || "—"} / ${esc(p.pkd) || "—"}</p>
      <p><strong>Return batch</strong><br>${batchLink(p.batch) || "—"}</p>
      <p><strong>Wipro outcome</strong><br>${p.outcome ? pieceBadge(p.outcome) : "—"} ${esc(p.outcomeNote)}
        ${p.replacement ? `<br>replacement ${entryLink(p.replacement)}` : ""}</p>
    </div>
    <h3>History</h3>
    <ul class="timeline">${p.events.slice().reverse().map(e => `<li><strong>${e.date}</strong> · ${esc(e.by)}<br>
      ${e.from && e.from !== e.to ? `${PIECE_STATUS[e.from]} → ` : ""}${PIECE_STATUS[e.to]}${e.note ? ` <span class="muted">· ${esc(e.note)}</span>` : ""}</li>`).join("")}</ul>
    <p class="muted">Stock entries: ${p.entries.map(entryLink).join(", ") || "none"}</p>
    <a href="#def/pieces" role="button" class="secondary outline">← Pieces</a>`;
};

/* ------------------------------ Return batches ------------------------------ */
function batchTable(list) {
  if (!list.length) return `<p class="muted">None.</p>`;
  return `<div class="table-wrap"><table class="striped"><thead><tr><th>Batch</th><th>Status</th><th>Created</th><th>Sent</th>
    <th>Docket</th><th class="num">Pieces</th><th class="num">With Wipro</th><th class="num">Replaced</th><th class="num">Rejected</th></tr></thead><tbody>
    ${list.slice().reverse().map(b => { const ps = b.tags.map(piece), n = s => ps.filter(p => p.status === s).length;
      return `<tr><td>${batchLink(b.no)}</td><td><span class="badge s-${b.status}">${b.status}</span></td><td>${b.created}</td>
        <td>${b.sentOn ? `${b.sentOn} <span class="age ${batchAgeClass(sentAge(b))}">${sentAge(b)} d</span>` : ""}</td><td>${esc(b.docket)}</td>
        <td class="num">${ps.length}</td><td class="num">${n("SENT_TO_WIPRO")}</td><td class="num">${n("REPLACED")}</td><td class="num">${n("REJECTED")}</td></tr>`; }).join("")}
    </tbody></table></div>`;
}
ROUTES["def/batches"] = () => {
  view().innerHTML = `${flashHtml()}<h1>Return batches to Wipro</h1>
    <div class="actions" style="margin-bottom:1rem"><a href="#def/pieces/status:AT_OFFICE" role="button" class="btn-def">📦 New return batch</a></div>
    ${batchTable(batches)}
    <p class="muted">DRAFT: still at the office, being packed · SENT: with Wipro (age = days since sent) · SETTLED: every piece has Wipro's result.</p>`;
};
function showWiproList(no) {
  openDlg(`<header><strong>Wipro Defective List · ${no}</strong></header><div class="table-wrap">${wiproList(batch(no))}</div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Close</button><button onclick="window.print()">🖨 Print</button>
      <button onclick="alert('Real app: downloads the .xlsx in exactly this layout')">⬇ Excel</button></footer>`);
}
function selAll(set, tags, on) { tags.forEach(t => on ? set.add(t) : set.delete(t)); route(); }
const batchAgeClass = d => d <= 30 ? "age-0" : d <= 60 ? "age-1" : d <= 90 ? "age-2" : "age-3";
/* Wipro's sheet layout: one row per item + batch code. */
function wiproList(b) {
  const groups = Object.values(b.tags.map(piece).reduce((a, p) => { const k = p.code + "|" + p.batchCode;
    a[k] = a[k] || { code: p.code, batch: p.batchCode, qty: 0 }; a[k].qty++; return a; }, {}));
  const date = b.sentOn || today();
  return `<table class="xl"><tr class="title"><td colspan="6">Date : ${date}  Wipro Defective List · ${b.no}</td></tr>
    <tr class="title"><td colspan="6">DEFECTIVE MATERIAL IN VIZAG</td></tr>
    <tr><th>S.NO</th><th>FITTING CODE</th><th>BATCH CODE</th><th>DRIVER CODE</th><th>PCB CODE</th><th>QUANTITY</th></tr>
    ${groups.map((g, n) => { const c = ["", "", ""]; c[sheetCol(item(g.code).type)] = esc(g.code);
      return `<tr><td>${n + 1}</td><td>${c[0]}</td><td>${esc(g.batch)}</td><td>${c[1]}</td><td>${c[2]}</td><td>${g.qty} NOS</td></tr>`; }).join("")}
    <tr><td colspan="5"><strong>Total</strong></td><td><strong>${b.tags.length} NOS</strong></td></tr></table>`;
}
let bsel = new Set();
ROUTES["def/batch"] = no => {
  const b = batch(no);
  if (!b) { view().innerHTML = "<p>Batch not found.</p>"; return; }
  const ps = b.tags.map(piece);
  const sentPicked = [...bsel].filter(t => piece(t).status === "SENT_TO_WIPRO");
  view().innerHTML = `${flashHtml()}<h1><span class="code">${b.no}</span> <span class="badge s-${b.status}">${b.status}</span></h1>
    <p>Created ${b.created}${b.sentOn ? ` · sent ${b.sentOn} (docket ${esc(b.docket)}, ${sentAge(b)} days with Wipro) · ${entryLink(b.sentEntry)}` : ""}</p>
    <div class="actions" style="margin-bottom:1rem">
      <button class="secondary" onclick="showWiproList('${b.no}')">📄 Wipro list (print / Excel)</button>
      ${b.status === "DRAFT" ? `<a href="#def/pieces/status:AT_OFFICE" role="button" class="secondary outline">+ Add pieces</a>
        <button class="btn-def" onclick="askSend('${b.no}')">🚚 Mark as sent to Wipro</button>` : ""}
      ${b.status === "SENT" ? `<button class="btn-in" ${sentPicked.length ? "" : "disabled"} onclick="askReplace('${b.no}')">✓ Replacement received (${sentPicked.length})</button>
        <button class="secondary" ${sentPicked.length ? "" : "disabled"} onclick="askReject('${b.no}')">✗ Rejected by Wipro (${sentPicked.length})</button>` : ""}
    </div>
    ${b.status === "SENT" ? `<p class="muted">Tick the pieces Wipro has answered for, then record the result.</p>` : ""}
    <div class="table-wrap"><table class="striped"><thead><tr>${b.status === "SENT" ? `<th><input type="checkbox" title="Select all with Wipro" onchange="selAll(bsel,[${ps.filter(p => p.status === "SENT_TO_WIPRO").map(p => `'${p.tag}'`).join(",")}],this.checked)"></th>` : ""}
      <th>Tag</th><th>Item</th><th>Batch code</th><th>PKD</th><th>From</th><th>Status</th><th>Result</th>${b.status === "DRAFT" ? "<th></th>" : ""}</tr></thead><tbody>
      ${ps.map(p => `<tr class="${bsel.has(p.tag) ? "sel" : ""}">${b.status === "SENT" ? `<td>${p.status === "SENT_TO_WIPRO" ? `<input type="checkbox" ${bsel.has(p.tag) ? "checked" : ""}
          onchange="this.checked?bsel.add('${p.tag}'):bsel.delete('${p.tag}');route()">` : ""}</td>` : ""}
        <td>${pieceLink(p.tag)}</td><td>${codeLink(p.code)}</td><td>${esc(p.batchCode)}</td><td>${esc(p.pkd)}</td><td>${esc(p.source)}</td>
        <td>${pieceBadge(p.status)}</td><td>${p.replacement ? `replaced by ${entryLink(p.replacement)}` : esc(p.outcomeNote)}</td>
        ${b.status === "DRAFT" ? `<td><button class="small secondary outline" onclick="removeFromBatch('${b.no}','${p.tag}');route()">Remove</button></td>` : ""}</tr>`).join("")}
    </tbody></table></div>
    <a href="#def/batches" role="button" class="secondary outline">← Batches</a>`;
};
function askSend(no) {
  openDlg(`<header><strong>Send ${no} to Wipro</strong></header><p>${batch(no).tags.length} pieces leave defective stock.</p>
    <div class="fields"><label>Date sent <input id="sd-date" value="${today()}"></label><label>Docket / challan no. <input id="sd-docket"></label></div><div id="sd-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button class="btn-def" onclick="doSend('${no}')">Mark sent</button></footer>`);
}
function doSend(no) { const err = sendBatch(no, document.getElementById("sd-date").value, document.getElementById("sd-docket").value);
  if (err) return formError("sd-err", err); closeDlg(); setFlash(`${no} marked as sent. Stock register updated.`); route(); }
function askReplace(no) {
  openDlg(`<header><strong>Replacement received for ${[...bsel].length} piece(s)</strong></header>
    <p>Adds the replacements to <strong>fresh</strong> stock and links each piece to the receipt.</p>
    <div class="fields"><label>Received into <select id="rp-loc">${opts(LOCATIONS, "Vizag Office")}</select></label>
      <label>Date <input id="rp-date" value="${today()}"></label><label>Wipro DC no. <input id="rp-dc"></label></div><div id="rp-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button class="btn-in" onclick="doReplace()">Save</button></footer>`);
}
function doReplace() { const err = receiveReplacement([...bsel], document.getElementById("rp-loc").value, document.getElementById("rp-date").value, document.getElementById("rp-dc").value);
  if (err) return formError("rp-err", err); closeDlg(); bsel.clear(); setFlash("Replacement received into fresh stock."); route(); }
function askReject(no) {
  openDlg(`<header><strong>Rejected by Wipro: ${[...bsel].length} piece(s)</strong></header>
    <label>Wipro's reason <input id="rj-note" placeholder="e.g. physical damage, out of warranty"></label>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button onclick="doReject()">Save</button></footer>`);
}
function doReject() { rejectPieces([...bsel], document.getElementById("rj-note").value); closeDlg(); bsel.clear(); setFlash("Marked as rejected. You can scrap them from the pieces list."); route(); }

/* ------------------------------ Reports ------------------------------ */
ROUTES["def/reports"] = () => {
  const top = Object.entries(pieces.reduce((a, p) => (a[p.code] = (a[p.code] || 0) + 1, a), {})).sort((x, y) => y[1] - x[1]).slice(0, 8);
  const byCust = Object.entries(pieces.filter(p => p.ticket).reduce((a, p) => { const k = complaint(p.ticket).customer; a[k] = (a[k] || 0) + 1; return a; }, {})).sort((x, y) => y[1] - x[1]);
  const sent = pieces.filter(p => p.status === "SENT_TO_WIPRO").map(p => sentAge(batch(p.batch)));
  const buckets = [["0–30 days", d => d <= 30], ["31–60 days", d => d > 30 && d <= 60], ["61–90 days", d => d > 60 && d <= 90], ["> 90 days", d => d > 90]];
  const repl = pieces.filter(p => p.status === "REPLACED").map(p => daysBetween(batch(p.batch).sentOn, entry(p.replacement).date));
  const max = top.length ? top[0][1] : 1;
  view().innerHTML = `<h1>Defective reports</h1>
    <div class="fields">
      <article><h4>Top failing parts</h4><table>${top.map(([c, n]) => `<tr><td>${codeLink(c)}<br>
        <span style="display:block;height:.5rem;background:var(--def);width:${Math.round(100 * n / max)}%;border-radius:.25rem"></span></td><td class="num">${n} NOS</td></tr>`).join("")}</table></article>
      <article><h4>Pending with Wipro</h4><table>${buckets.map(([l, f]) => `<tr><td>${l}</td><td class="num">${sent.filter(f).length} NOS</td></tr>`).join("")}</table>
        <h4>Replacement turnaround</h4><p>${repl.length ? `<strong>${Math.round(sum(repl, x => x) / repl.length)} days</strong> average (sent → replacement received, ${repl.length} pieces)` : "No replacements yet."}</p></article>
      <article><h4>Defectives by customer</h4><table>${byCust.map(([c, n]) => `<tr><td>${esc(c)}</td><td class="num">${n}</td></tr>`).join("") || "<tr><td>None linked to complaints yet.</td></tr>"}</table></article>
    </div>
    <button class="secondary" onclick="alert('Real app: each report exports to Excel.')">⬇ Export to Excel</button>`;
};
