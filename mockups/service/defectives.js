/* Defectives screens: dashboard, pieces list (+ bulk add-to-batch / scrap), piece card, mark defective from stock,
   return batches list, new batch, batch detail (add / remove pieces, dispatch, settle). Every write goes through the
   service functions in service.js, which post to the shared stock ledger. */

const SCRAP_REASONS = ["Not worth returning", "Burnt / physically damaged", "Rejected by the company", "Other"];
const batchLink = no => no ? `<a class="code" href="#batch/${no}">${no}</a>` : "";
const itemCell = code => `${codeLink(code)}<div class="small text-secondary">${esc((item(code) || {}).desc || "")}</div>`;
const sourceHtml = p => p.source === "SITE_VISIT" && p.complaint
  ? `${cLink(p.complaint)}<div class="small text-secondary">${esc(siteName(complaint(p.complaint)))}</div>`
  : `<span class="text-secondary">${icon("building-warehouse")} Stock</span>`;
const batchPkd = p => [p.batch, fmtMonth(p.pkd)].filter(Boolean).join(" · ") || `<span class="text-secondary">—</span>`;
const waitDays = b => daysBetween(b.dispatchedOn, today());
// The sample dispatch lists (make_sample_exports.py) exist for the demo batches only.
const batchExport = b => (DB.demoBatches || []).includes(b.no) ? exportBtn(`Return_Batch_${b.no}.xlsx`, "Export dispatch list")
  : `<button type="button" class="btn btn-outline-success" onclick="toast('Mockup: sample dispatch lists exist for the demo batches only. The real app makes one for every batch.')">${icon("file-spreadsheet")} Export dispatch list</button>`;
const inlineErr = (id, msg) => { field(id).innerHTML = msg ? `<div class="alert alert-danger mb-0 mt-3" role="alert"><div class="d-flex gap-2">${icon("alert-circle")}<div>${esc(msg)}</div></div></div>` : ""; };
const checkbox = (on, attrs, label) => `<input type="checkbox" class="form-check-input m-0" ${on ? "checked" : ""} ${attrs} aria-label="${label}">`;

/* ---------- dashboard ---------- */
ROUTES.ddash = () => {
  const P = DB.pieces, by = (list, f) => { const t = {}; for (const x of list) t[f(x)] = (t[f(x)] || 0) + 1; return t; };
  const inStore = P.filter(p => p.status === "IN_STORE"), inBatch = P.filter(p => p.status === "IN_BATCH"), sent = P.filter(p => p.status === "SENT");
  const since = addDays(today(), -90), settled = P.filter(p => p.outcome && p.settledOn >= since);
  setHeader("Defectives", "Defectives dashboard", `<a href="#mark" class="btn btn-quiet">${icon("alert-octagon")} Mark defective</a>
    <a href="#batch-new" class="btn btn-primary">${icon("plus")} New return batch</a>${exportBtn("Defective_List.xlsx", "Defective list")}`);
  const companies = DB.companies.filter(c => P.some(p => p.company === c));
  const storeRows = companies.map(c => ({ company: c, store: inStore.filter(p => p.company === c).length, batch: inBatch.filter(p => p.company === c).length }))
    .filter(r => r.store + r.batch);
  const sentRows = companies.map(c => {
    const bs = DB.batches.filter(b => b.company === c && b.status === "DISPATCHED" && b.lines.some(l => piece(l.tag).status === "SENT"))
      .sort((a, b) => a.dispatchedOn.localeCompare(b.dispatchedOn));
    return { company: c, n: sent.filter(p => p.company === c).length, batches: bs, oldest: bs[0] };
  }).filter(r => r.n);
  const oc = by(settled, p => p.outcome);
  const oldest = inStore.slice().sort((a, b) => a.collectedOn.localeCompare(b.collectedOn) || a.tag.localeCompare(b.tag)).slice(0, 6);
  view().innerHTML = `<div class="row row-deck row-cards">
    ${kpiTile("building-warehouse", "brand", inStore.length, "Pieces in store", "not yet in a batch", "#pieces/status=IN_STORE", "col-6 col-lg-3")}
    ${kpiTile("packages", "brand", inBatch.length, "In draft batches", `${DB.batches.filter(b => b.status === "DRAFT").length} draft batch(es)`, "#batches/status=Draft", "col-6 col-lg-3")}
    ${kpiTile("truck", sent.length ? "wait" : "brand", sent.length, "Sent, awaiting settlement", "with the companies", "#pieces/status=SENT", "col-6 col-lg-3")}
    ${kpiTile("circle-check", "brand", settled.length, "Answered by companies", "last 90 days", "#batches", "col-6 col-lg-3")}
    <div class="col-lg-5"><div class="card"><div class="card-header"><div><h3 class="card-title">${icon("building-warehouse")} In the defective store, per company</h3>
      <div class="card-subtitle">Physical pieces waiting to go back</div></div></div>
      ${dataTable("d-store", { rows: storeRows, paging: false, sort: "store", dir: "desc", empty: "The defective store is empty.", columns: [
        { key: "company", label: "Company", html: r => `<a href="#pieces/company=${encodeURIComponent(r.company)}&status=IN_STORE">${esc(r.company)}</a>` },
        { key: "store", label: "In store", num: true, html: r => `<b>${r.store}</b>` },
        { key: "batch", label: "In draft batch", num: true, html: r => qtyHtml(r.batch) },
        { key: "total", label: "Total", num: true, sort: r => r.store + r.batch, html: r => r.store + r.batch }] })}</div></div>
    <div class="col-lg-7"><div class="card"><div class="card-header"><div><h3 class="card-title">${icon("truck")} Sent, awaiting settlement</h3>
      <div class="card-subtitle">Red = the oldest batch has waited more than 30 days</div></div></div>
      ${dataTable("d-sent", { rows: sentRows, paging: false, sort: "wait", dir: "desc", empty: "Nothing is waiting on a company.", columns: [
        { key: "company", label: "Company", html: r => `<a href="#pieces/company=${encodeURIComponent(r.company)}&status=SENT">${esc(r.company)}</a>` },
        { key: "n", label: "Pieces", num: true, html: r => `<b>${r.n}</b>` },
        { key: "batches", label: "Batches", sort: r => r.batches.length, html: r => r.batches.map(b => batchLink(b.no)).join(", ") },
        { key: "disp", label: "Oldest dispatched", sort: r => r.oldest.dispatchedOn, html: r => fmt(r.oldest.dispatchedOn) },
        { key: "wait", label: "Waiting", num: true, sort: r => waitDays(r.oldest),
          html: r => waitDays(r.oldest) > 30 ? `<span class="badge st st-alert">${icon("alert-triangle")}${waitDays(r.oldest)} days</span>` : `${waitDays(r.oldest)} days` }] })}</div></div>
    <div class="col-lg-5"><div class="card"><div class="card-header"><div><h3 class="card-title">${icon("chart-bar")} Outcomes, last 90 days</h3>
      <div class="card-subtitle">${settled.length} pieces answered by the companies</div></div></div>
      <div class="list-group list-group-flush">${Object.keys(OUTCOME).map(o => { const n = oc[o] || 0, max = Math.max(1, settled.length);
        return `<a class="list-group-item list-group-item-action py-2" href="#pieces/outcome=${o}"><div class="d-flex align-items-center gap-2 mb-1">${oBadge(o)}
          <span class="ms-auto fw-bold num">${n}</span></div><div class="progress progress-sm"><div class="progress-bar ${o.startsWith("REJECTED") ? "bg-red" : "bar-brand"}" style="width:${n / max * 100}%"></div></div></a>`; }).join("")}</div></div></div>
    <div class="col-lg-7"><div class="card"><div class="card-header"><h3 class="card-title">${icon("clock")} Longest in store</h3>
      <div class="card-actions"><a href="#pieces/status=IN_STORE" class="btn btn-sm btn-outline-primary">All in store ${icon("arrow-right")}</a></div></div>
      ${dataTable("d-oldest", { rows: oldest, paging: false, sort: "age", dir: "desc", empty: "Nothing in store.", columns: [
        { key: "tag", label: "Tag", html: p => tagLink(p.tag) }, { key: "code", label: "Item", html: p => itemCell(p.code) },
        { key: "company", label: "Company" }, { key: "source", label: "Source", sort: p => p.complaint || "", html: sourceHtml },
        { key: "age", label: "In store", num: true, sort: p => daysBetween(p.collectedOn, today()), html: p => `${daysBetween(p.collectedOn, today())} days` }] })}</div></div>
  </div>`;
};

/* ---------- pieces list ---------- */
const PF0 = { company: "", item: "", status: "", source: "", outcome: "", from: "", to: "", q: "" };
let pf = { ...PF0 };
const pSel = new Set();
ROUTES.pieces = arg => {
  if (arg !== undefined) {
    pf = { ...PF0 }; pSel.clear(); resetPage("pieces");
    for (const kv of arg.split("&")) { const [k, v] = kv.split("="); if (k in pf) pf[k] = v; }
  }
  const q = pf.q.trim().toUpperCase();
  const rows = DB.pieces.filter(p => (!pf.company || p.company === pf.company) && (!pf.item || p.code === pf.item) && (!pf.status || p.status === pf.status)
    && (!pf.source || p.source === pf.source) && (!pf.outcome || p.outcome === pf.outcome) && (!pf.from || p.collectedOn >= pf.from) && (!pf.to || p.collectedOn <= pf.to)
    && (!q || [p.tag, p.batch, p.complaint, p.batchNo, p.fault].join(" ").toUpperCase().includes(q)));
  for (const t of [...pSel]) if (!rows.some(p => p.tag === t)) pSel.delete(t);
  window._pRows = rows;
  const set = k => `pf.${k}=this.value;resetPage('pieces');route()`;
  const selectable = rows.filter(p => p.status === "IN_STORE");
  setHeader("Defectives", "Defective pieces", `<a href="#mark" class="btn btn-quiet">${icon("alert-octagon")} Mark defective</a>${exportBtn("Defective_List.xlsx")}`);
  view().innerHTML = `<div class="card">
    <div class="card-body border-bottom py-3"><div class="row g-2 align-items-end">
      ${filterCol(2, fsel("Company", set("company"), DB.companies, pf.company, "All companies"))}
      ${filterCol(3, `<label class="form-label small text-secondary mb-1" for="pf-item">Item</label><select id="pf-item" class="form-select"><option value="">All items</option>${opt(uniq(DB.pieces.map(p => p.code)).sort(), pf.item)}</select>`)}
      ${filterCol(2, fsel("Status", set("status"), Object.entries(PSTATUS), pf.status, "Any status"))}
      ${filterCol(2, fsel("Source", set("source"), Object.entries(SOURCE), pf.source, "Any source"))}
      ${filterCol(3, fsearch(pf.q, set("q"), "Tag, batch code, CMP / RB no., fault"))}
      ${filterCol(2, fdate("Collected from", pf.from, set("from")))}${filterCol(2, fdate("Collected to", pf.to, set("to")))}
      ${pf.outcome ? filterCol(3, `<div class="pb-2">Outcome: ${oBadge(pf.outcome)} <a href="#" onclick="pf.outcome='';route();return false" class="ms-1 small">clear</a></div>`) : ""}
      <div class="col-auto ms-auto pb-1"><a href="#pieces/" class="btn btn-link link-secondary px-0" onclick="go('#pieces/');return false">${icon("filter-off")} Clear filters</a></div>
    </div></div>
    <div id="bulk-bar"></div>
    ${dataTable("pieces", { rows, sort: "tag", dir: "desc", empty: "No pieces match these filters.", columns: [
      { key: "sel", label: checkbox(selectable.length && selectable.every(p => pSel.has(p.tag)), `onclick="pSelectAll(this.checked)" ${selectable.length ? "" : "disabled"}`, "Tick all pieces in store"),
        nosort: true, cls: "c-check", html: p => p.status === "IN_STORE" ? checkbox(pSel.has(p.tag), `data-tag="${p.tag}" onchange="pToggle('${p.tag}',this.checked)"`, `Tick ${p.tag}`)
          : `<span class="text-secondary" title="Only pieces in store can be batched or scrapped">${icon("lock")}</span>` },
      { key: "tag", label: "Tag", html: p => tagLink(p.tag) },
      { key: "code", label: "Item", html: p => itemCell(p.code) },
      { key: "company", label: "Company" },
      { key: "source", label: "Source", sort: p => p.complaint || "~", html: sourceHtml },
      { key: "collected", label: "Collected", cls: "nowrap", sort: p => p.collectedOn + p.tag, html: p => fmt(p.collectedOn) },
      { key: "bpkd", label: "Batch · PKD", cls: "nowrap", sort: p => p.batch, html: batchPkd },
      { key: "status", label: "Status", sort: p => Object.keys(PSTATUS).indexOf(p.status), html: p => pBadge(p.status) + (p.outcome ? `<div class="mt-1">${oBadge(p.outcome)}</div>` : "") },
      { key: "rb", label: "Return batch", sort: p => p.batchNo || "", html: p => batchLink(p.batchNo) || `<span class="text-secondary">—</span>` }] })}
  </div><p class="text-secondary small mt-2">${icon("info-circle")} Tick pieces that are in store to add them to a draft return batch or scrap them.
    Pieces in a batch, sent or settled are locked (${icon("lock")}).</p>`;
  pRenderBulk();
  new TomSelect("#pf-item", { maxOptions: 100, closeAfterSelect: true, allowEmptyOption: true,
    onChange: v => { pf.item = v; resetPage("pieces"); setTimeout(route); } });
};
function pToggle(tag, on) { on ? pSel.add(tag) : pSel.delete(tag); pRenderBulk(); }
function pSelectAll(on) {
  for (const p of window._pRows) if (p.status === "IN_STORE") on ? pSel.add(p.tag) : pSel.delete(p.tag);
  document.querySelectorAll("#dt-pieces input[data-tag]").forEach(c => c.checked = pSel.has(c.dataset.tag));
  pRenderBulk();
}
function pRenderBulk() {
  const el = field("bulk-bar"); if (!el) return;
  const tags = [...pSel], cos = uniq(tags.map(t => piece(t).company));
  el.innerHTML = tags.length ? `<div class="bulk-bar px-3 py-2 d-flex flex-wrap align-items-center gap-2">
      <b>${tags.length} piece${tags.length > 1 ? "s" : ""} ticked</b><span class="text-secondary">· ${esc(cos.join(", "))}</span>
      <div class="ms-auto btn-list"><button type="button" class="btn btn-sm btn-primary" onclick="askAddToBatch()">${icon("packages")} Add to draft batch…</button>
        <button type="button" class="btn btn-sm btn-quiet" onclick="askScrap()">${icon("trash")} Scrap…</button>
        <button type="button" class="btn btn-sm btn-link link-secondary" onclick="pSel.clear();route()">Clear</button></div></div>` : "";
}
function pModal(title, body, footer) {
  openModal(`<div class="modal-header"><h5 class="modal-title">${title}</h5><button type="button" class="btn-close" aria-label="Close" onclick="closeModal()"></button></div>
    <div class="modal-body">${body}<div id="pm-err"></div></div><div class="modal-footer">${footer}</div>`);
}
function askAddToBatch() {
  const tags = [...pSel], cos = uniq(tags.map(t => piece(t).company));
  if (cos.length > 1) {
    pModal(`${icon("packages")} Add to draft batch`, `<div class="alert alert-danger mb-0" role="alert"><div class="d-flex gap-2">${icon("alert-circle")}<div>
      The ticked pieces belong to ${cos.length} companies (${esc(cos.join(", "))}). A return batch holds one company's pieces only.
      Filter the list by company, or untick the others.</div></div></div>`,
      `<button type="button" class="btn btn-quiet ms-auto" onclick="closeModal()">OK</button>`);
    return;
  }
  const co = cos[0], drafts = DB.batches.filter(b => b.status === "DRAFT" && b.company === co);
  pModal(`${icon("packages")} Add ${tags.length} piece${tags.length > 1 ? "s" : ""} to a draft batch`,
    `<p class="text-secondary">Company: <b>${esc(co)}</b>. Only draft batches for ${esc(co)} are offered.</p>
    <div class="form-selectgroup form-selectgroup-boxes d-flex flex-column gap-2">${[...drafts.map(b => [b.no, `<span class="code">${b.no}</span>
      <span class="text-secondary ms-2">created ${fmt(b.createdOn)} · ${b.lines.length} piece(s)${b.note ? " · " + esc(b.note) : ""}</span>`]),
      ["__new", `${icon("plus")} New batch for ${esc(co)}`]].map(([v, l], i) => `<label class="form-selectgroup-item flex-fill">
      <input type="radio" name="bm-batch" value="${v}" class="form-selectgroup-input" ${i === 0 ? "checked" : ""}>
      <div class="form-selectgroup-label d-flex align-items-center p-2 text-start"><span class="form-selectgroup-check me-2"></span><span>${l}</span></div></label>`).join("")}</div>`,
    `<button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
     <button type="button" class="btn btn-primary ms-auto" onclick="doAddToBatch('${esc(co)}')">${icon("check")} Add to batch</button>`);
}
function doAddToBatch(co) {
  const tags = [...pSel], v = radioVal("bm-batch");
  let no;
  if (v === "__new") { const r = createBatch(co, tags); if (r.error) return inlineErr("pm-err", r.error); no = r.batch.no; }
  else { const err = addPieces(batch(v), tags); if (err) return inlineErr("pm-err", err); no = v; }
  pSel.clear(); closeModal();
  toastAfterNav(`${tags.length} piece(s) added to <b>${no}</b>.`); go(`#batch/${no}`);
}
function askScrap() {
  const tags = [...pSel];
  pModal(`${icon("trash")} Scrap ${tags.length} piece${tags.length > 1 ? "s" : ""}`,
    `<p class="text-secondary">Use this when a piece isn't worth sending back. It leaves the Defective store with an adjustment (Damaged) and can't be batched again.</p>
    <div class="dl-tags mb-3">${tags.map(t => `<span class="chip"><span class="code">${t}</span> <span class="text-secondary">${esc(piece(t).code)}</span></span>`).join("")}</div>
    <label class="form-label required" for="sc-reason">Reason</label><select id="sc-reason" class="form-select"><option value="">Choose…</option>${opt(SCRAP_REASONS)}</select>
    <label class="form-label mt-3" for="sc-note">Note</label><textarea id="sc-note" class="form-control" rows="2" placeholder="Required when the reason is Other"></textarea>`,
    `<button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
     <button type="button" class="btn btn-danger ms-auto" onclick="doScrap()">${icon("trash")} Scrap pieces</button>`);
}
function doScrap() {
  const tags = [...pSel], reason = field("sc-reason").value, note = field("sc-note").value.trim();
  if (reason === "Other" && !note) return inlineErr("pm-err", "Write a note when the reason is Other.");
  const err = scrapPieces(tags, reason, note);
  if (err) return inlineErr("pm-err", err);
  pSel.clear(); closeModal(); toastAfterNav(`${tags.length} piece(s) scrapped: ${tags.join(", ")}.`); route();
}

/* ---------- piece card ---------- */
ROUTES.piece = tag => {
  const p = piece(tag);
  if (!p) { setHeader("Defectives", "Piece not found"); view().innerHTML = ""; return; }
  const it = item(p.code), b = p.batchNo && batch(p.batchNo), v = p.visit && visit(p.visit);
  const line = DB.batches.flatMap(x => x.lines.map(l => ({ ...l, b: x }))).filter(l => l.tag === tag).at(-1);
  setHeader(`Defective piece · ${esc(p.company)}`, `<span class="code">${p.tag}</span> ${pBadge(p.status)} ${oBadge(p.outcome)}`,
    (p.status === "IN_STORE" ? `<button class="btn btn-primary" onclick="pSel.clear();pSel.add('${tag}');askAddToBatch()">${icon("packages")} Add to draft batch…</button>
      <button class="btn btn-quiet" onclick="pSel.clear();pSel.add('${tag}');askScrap()">${icon("trash")} Scrap…</button>` : "")
    + (b ? `<a href="#batch/${b.no}" class="btn btn-quiet">${icon("truck-return")} Batch ${b.no}</a>` : ""));
  const ev = pEvents(tag).slice().reverse();
  view().innerHTML = `<div class="row row-cards">
    <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
      ${factRow("Item", `${codeLink(p.code)}<div class="small text-secondary">${esc(it.type)} · ${esc(it.desc)}</div>`)}
      ${factRow("Company", esc(p.company))}
      ${factRow("Source", p.source === "SITE_VISIT" ? `Site visit · ${cLink(p.complaint)}${v ? ` <span class="text-secondary">(${v.no}, ${fmt(v.date)})</span>` : ""}
        <div class="small text-secondary">${esc(siteName(complaint(p.complaint)))}, ${esc(siteCity(complaint(p.complaint)))}</div>` : `${icon("building-warehouse")} Found in stock`)}
      ${factRow("Collected on", fmt(p.collectedOn))}${factRow("Batch code", p.batch ? `<span class="code">${esc(p.batch)}</span>` : "—")}${factRow("PKD (packed)", fmtMonth(p.pkd) || "—")}
      ${factRow("Fault", esc(p.fault) || "—")}${factRow("Return batch", b ? `${batchLink(b.no)} ${bBadge(b)}` : "—")}
      ${factRow("Outcome", p.outcome ? oBadge(p.outcome) + (p.settledOn ? ` <span class="text-secondary small">on ${fmt(p.settledOn)}</span>` : "") : "—")}
      ${factRow("Replacement went into", line && line.toLoc ? esc(line.toLoc) : "")}
      ${factRow("Ledger entries", [p.entry && entry(p.entry) ? entryLink(p.entry) : "", line && line.b.dispatchEntry ? entryLink(line.b.dispatchEntry) : "", line && line.entry ? entryLink(line.entry) : ""].filter(Boolean).join(" · ") || "—")}
    </div></div></div></div>
    <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">${icon("timeline")} History</h3></div>
      <div class="card-body"><ul class="tl">${ev.map(e => `<li class="tl-item"><span class="tl-dot ${PSTYLE[e.to][0]}">${icon(PSTYLE[e.to][1])}</span>
        <div class="tl-body"><div class="fw-medium">${e.from ? `${PSTATUS[e.from]} → ` : ""}${PSTATUS[e.to]}</div>
        <div class="small text-secondary">${fmt(e.at)} · ${esc(e.by)}</div>${e.note ? `<div class="small">${esc(e.note)}</div>` : ""}</div></li>`).join("")}</ul></div></div></div>
  </div>`;
};

/* ---------- mark defective from stock ---------- */
let markLines = null;
ROUTES.mark = code => {
  setHeader("Defectives", `${icon("alert-octagon")} Mark defective from stock`);
  view().innerHTML = `<form id="mark-form" novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveMark()">
    <div class="card mb-3"><div class="card-header"><h3 class="card-title">${icon("file-description")} Details</h3>
      <div class="card-subtitle ms-2 text-secondary">A piece in good stock turned out faulty</div></div><div class="card-body"><div class="row g-3">
      ${dateField()}${locField("Found at location", "markLines.refreshAll()")}
      <div class="col-12 col-md-6 d-flex align-items-end"><div class="text-secondary small">${icon("info-circle")} Moves the pieces out of good stock into the
        <b>${esc(DB.defStore)}</b> (a transfer) and gives each piece its own tag. Quantity 2 = 2 tags.</div></div>
    </div></div></div>
    <div class="card"><div class="card-header"><h3 class="card-title">${icon("list-details")} Faulty pieces</h3></div>
      <div class="card-body"><div id="lines"></div></div>
      <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span id="lines-summary" class="text-secondary"></span>
        <div class="ms-auto btn-list"><a href="#ddash" class="btn btn-link link-secondary">Cancel</a>
          <button type="submit" class="btn btn-primary">${icon("device-floppy")} Mark as defective</button></div></div></div>
    <div id="form-error" class="mt-3"></div></form>`;
  markLines = new Lines(field("lines"), "mark", () => field("f-loc").value, { addLabel: "Add another item" });
  markLines.add(code && item(code) ? code : undefined);
};
function saveMark() {
  const r = markLines.collect();
  if (r.error) return formFail(r.error);
  const res = markDefective({ date: field("f-date").value, loc: field("f-loc").value, lines: r.lines });
  if (res.error) return formFail(res.error, res.focus);
  toastAfterNav(`<b>${res.entry.no}</b> saved. New defective tag${res.tags.length > 1 ? "s" : ""}: <b>${res.tags.join(", ")}</b>.`);
  go(`#entry/${res.entry.no}`);
}

/* ---------- return batches ---------- */
let bf = { company: "", status: "" };
ROUTES.batches = arg => {
  if (arg !== undefined) { bf = { company: "", status: "" }; for (const kv of arg.split("&")) { const [k, v] = kv.split("="); if (k in bf) bf[k] = v; } resetPage("batches"); }
  const rows = DB.batches.filter(b => (!bf.company || b.company === bf.company) && (!bf.status || batchStatus(b) === bf.status));
  const set = k => `bf.${k}=this.value;resetPage('batches');route()`;
  const settledN = b => b.lines.filter(l => l.outcome).length;
  setHeader("Defectives", "Return batches", `<a href="#batch-new" class="btn btn-primary">${icon("plus")} New batch</a>`);
  view().innerHTML = `<div class="card"><div class="card-body border-bottom py-3"><div class="row g-2 align-items-end">
      ${filterCol(3, fsel("Company", set("company"), DB.companies, bf.company, "All companies"))}
      ${filterCol(3, fsel("Status", set("status"), Object.keys(BSTYLE), bf.status, "Any status"))}</div></div>
    ${dataTable("batches", { rows, sort: "no", dir: "desc", empty: "No return batches match.", columns: [
      { key: "no", label: "Batch", html: b => batchLink(b.no) }, { key: "company", label: "Company" },
      { key: "created", label: "Created", sort: b => b.createdOn, html: b => fmt(b.createdOn) },
      { key: "status", label: "Status", sort: batchStatus, html: bBadge },
      { key: "pieces", label: "Pieces", num: true, sort: b => b.lines.length, html: b => b.lines.length },
      { key: "settled", label: "Settled", num: true, sort: settledN, html: b => b.status === "DRAFT" ? `<span class="text-secondary">—</span>` : `${settledN(b)} / ${b.lines.length}` },
      { key: "disp", label: "Dispatched", sort: b => b.dispatchedOn || "", html: b => b.dispatchedOn ? `${fmt(b.dispatchedOn)}<div class="small text-secondary">${esc(b.courier)} · <span class="code">${esc(b.docket)}</span></div>` : `<span class="text-secondary">Not yet</span>` },
      { key: "wait", label: "Waiting", num: true, sort: b => b.dispatchedOn && batchStatus(b) !== "Settled" ? waitDays(b) : -1,
        html: b => !b.dispatchedOn || batchStatus(b) === "Settled" ? "" : waitDays(b) > 30 ? `<span class="badge st st-alert">${icon("alert-triangle")}${waitDays(b)} days</span>` : `${waitDays(b)} days` },
      { key: "note", label: "Note", cls: "cell-wrap", html: b => `<span class="text-secondary">${esc(b.note)}</span>` }] })}
  </div><p class="text-secondary small mt-2">${icon("info-circle")} A batch holds one company's pieces. "Partly settled" and "Settled" come from the pieces' outcomes.</p>`;
};

/* ---------- new batch ---------- */
let nbCompany = null;
const nbSel = new Set();
ROUTES["batch-new"] = co => {
  nbSel.clear();
  setHeader("Defectives · Return batches", `${icon("plus")} New return batch`);
  view().innerHTML = `<form novalidate onsubmit="event.preventDefault();saveNewBatch()">
    <div class="card mb-3"><div class="card-body"><div class="row g-3">
      ${fcol(4, lbl("b-company", "Company the pieces go back to") + `<select id="b-company"><option value="">Choose…</option>${opt(DB.companies.filter(c => DB.pieces.some(p => p.company === c && p.status === "IN_STORE")))}</select>
        <small class="form-hint">Only companies with pieces in store are listed.</small>`)}
      ${fcol(8, lbl("b-note", "Note", false) + `<input id="b-note" class="form-control" placeholder="e.g. Drivers from the bank sites">`)}
    </div></div></div>
    <div class="card"><div class="card-header"><h3 class="card-title">${icon("tags")} Pieces in store</h3><div class="card-subtitle ms-2 text-secondary" id="nb-sub">Choose the company first</div></div>
      <div id="nb-pieces"><div class="card-body text-secondary">Only that company's pieces in store are offered.</div></div>
      <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span class="text-secondary" id="nb-count"></span>
        <div class="ms-auto btn-list"><a href="#batches" class="btn btn-link link-secondary">Cancel</a>
          <button type="submit" class="btn btn-primary">${icon("device-floppy")} Create draft batch</button></div></div></div>
    <div id="form-error" class="mt-3"></div></form>`;
  nbCompany = new TomSelect("#b-company", { maxOptions: 50, closeAfterSelect: true, onChange: nbRender });
  if (co) nbCompany.setValue(co);
};
function nbRender() {
  const co = nbCompany.getValue(); nbSel.clear(); clearFormError();
  const rows = DB.pieces.filter(p => p.company === co && p.status === "IN_STORE");
  field("nb-sub").textContent = co ? `${rows.length} ${esc(co)} piece(s) in store` : "Choose the company first";
  field("nb-pieces").innerHTML = co ? dataTable("nb", { rows, sort: "tag", paging: false, empty: `No ${esc(co)} pieces in store.`, columns: [
    { key: "sel", label: checkbox(false, `onclick="nbAll(this.checked)" id="nb-all"`, "Tick all"), nosort: true, cls: "c-check",
      html: p => checkbox(false, `data-tag="${p.tag}" onchange="nbToggle('${p.tag}',this.checked)"`, `Tick ${p.tag}`) },
    { key: "tag", label: "Tag", html: p => tagLink(p.tag) }, { key: "code", label: "Item", html: p => itemCell(p.code) },
    { key: "source", label: "Source", sort: p => p.complaint || "~", html: sourceHtml }, { key: "bpkd", label: "Batch · PKD", cls: "nowrap", sort: p => p.batch, html: batchPkd },
    { key: "fault", label: "Fault", cls: "cell-wrap" }, { key: "collected", label: "Collected", sort: p => p.collectedOn, html: p => fmt(p.collectedOn) }] })
    : `<div class="card-body text-secondary">Only that company's pieces in store are offered.</div>`;
  if (co) dtRender("nb");
  nbCount();
}
function nbToggle(tag, on) { on ? nbSel.add(tag) : nbSel.delete(tag); nbCount(); }
function nbAll(on) { document.querySelectorAll("#dt-nb input[data-tag]").forEach(c => { c.checked = on; nbToggle(c.dataset.tag, on); }); }
const nbCount = () => { field("nb-count").textContent = nbSel.size ? `${nbSel.size} piece(s) ticked` : "You can also create an empty draft and add pieces later."; };
function saveNewBatch() {
  const r = createBatch(nbCompany.getValue(), [...nbSel], field("b-note").value);
  if (r.error) { formFail(r.error); if (r.focus === "b-company") nbCompany.focus(); return; }
  toastAfterNav(`Draft batch <b>${r.batch.no}</b> created for ${esc(r.batch.company)} with ${r.batch.lines.length} piece(s).`);
  go(`#batch/${r.batch.no}`);
}

/* ---------- batch detail ---------- */
const bSel = new Set();
let bSelFor = "";
ROUTES.batch = no => {
  const b = batch(no);
  if (!b) { setHeader("Return batches", "Batch not found"); view().innerHTML = ""; return; }
  if (bSelFor !== no) { bSel.clear(); bSelFor = no; }
  const draft = b.status === "DRAFT", rows = b.lines.map(l => ({ ...l, p: piece(l.tag) }));
  const sentRows = rows.filter(r => r.p.status === "SENT");
  for (const t of [...bSel]) if (!sentRows.some(r => r.tag === t)) bSel.delete(t);
  setHeader(`Return batch · ${esc(b.company)}`, `<span class="code">${b.no}</span> ${bBadge(b)}`,
    (draft ? `<button class="btn btn-out" onclick="askDispatch('${b.no}')">${icon("truck")} Dispatch…</button>` : "") + batchExport(b));
  const settled = rows.filter(r => r.outcome).length;
  view().innerHTML = `<div class="row row-cards">
    <div class="col-12"><div class="d-flex flex-wrap gap-2">
      <span class="chip">${icon("building-store")} ${esc(b.company)}</span>
      <span class="chip">${icon("calendar")} Created ${fmt(b.createdOn)}</span>
      <span class="chip">${icon("tags")} <b>${rows.length}</b> piece(s)</span>
      ${b.dispatchedOn ? `<span class="chip">${icon("truck")} Dispatched ${fmt(b.dispatchedOn)} · ${esc(b.courier)} <span class="code">${esc(b.docket)}</span></span>
        <span class="chip ${sentRows.length ? "chip-wait" : ""}">${icon("progress-check")} Settled <b>${settled}</b> of ${rows.length}</span>
        ${sentRows.length ? `<span class="chip ${waitDays(b) > 30 ? "chip-alert" : ""}">${icon("clock")} Waiting <b>${waitDays(b)}</b> days</span>` : ""}
        <a class="chip chip-link" href="#entry/${b.dispatchEntry}">${icon("package-export", "text-out")} ${b.dispatchEntry}</a>` : ""}
      ${b.note ? `<span class="chip">${icon("note")} ${esc(b.note)}</span>` : ""}</div></div>
    ${draft ? batchDraftCards(b, rows) : batchSentCards(b, rows, sentRows)}
  </div>`;
  if (!draft && sentRows.length) settleOutcomeChanged();
};
function batchDraftCards(b, rows) {
  const avail = DB.pieces.filter(p => p.company === b.company && p.status === "IN_STORE");
  window._addSel = new Set();
  return `<div class="col-12"><div class="alert alert-info mb-0">${icon("pencil")} <b>Draft.</b> Add or remove ${esc(b.company)} pieces, then <b>Dispatch</b>.
      Dispatching posts a Stock OUT from the ${esc(DB.defStore)} and locks the batch.</div></div>
    <div class="col-lg-7"><div class="card"><div class="card-header"><h3 class="card-title">${icon("packages")} In this batch</h3><span class="badge bg-secondary-lt ms-2">${rows.length}</span></div>
      ${dataTable("b-lines", { rows, sort: "tag", paging: false, empty: "No pieces yet. Add some from the right.", columns: [
        { key: "tag", label: "Tag", html: r => tagLink(r.tag) }, { key: "code", label: "Item", sort: r => r.p.code, html: r => itemCell(r.p.code) },
        { key: "bpkd", label: "Batch · PKD", cls: "nowrap", sort: r => r.p.batch, html: r => batchPkd(r.p) }, { key: "fault", label: "Fault", cls: "cell-wrap", sort: r => r.p.fault, html: r => esc(r.p.fault) },
        { key: "rm", label: "", nosort: true, html: r => `<button type="button" class="btn btn-sm btn-icon btn-quiet" title="Remove ${r.tag} from the batch" aria-label="Remove ${r.tag}" onclick="doRemovePiece('${b.no}','${r.tag}')">${icon("x")}</button>` }] })}
      <div id="b-err" class="px-3 pb-3"></div></div></div>
    <div class="col-lg-5"><div class="card"><div class="card-header"><h3 class="card-title">${icon("plus")} Add pieces</h3></div>
      <div class="card-body border-bottom"><label class="form-label" for="add-tag">Type or scan a tag</label>
        <form class="input-group" novalidate onsubmit="event.preventDefault();addByTag('${b.no}')"><input id="add-tag" class="form-control code" placeholder="e.g. DEF-0042" autocomplete="off"
          oninput="field('add-err').innerHTML=''"><button class="btn btn-primary">${icon("plus")} Add</button></form><div id="add-err"></div></div>
      ${dataTable("b-avail", { rows: avail, sort: "tag", size: 10, empty: `No other ${esc(b.company)} pieces in store.`, columns: [
        { key: "sel", label: "", nosort: true, cls: "c-check", html: p => checkbox(_addSel.has(p.tag), `data-tag="${p.tag}" onchange="this.checked?_addSel.add('${p.tag}'):_addSel.delete('${p.tag}')"`, `Tick ${p.tag}`) },
        { key: "tag", label: "Tag", html: p => tagLink(p.tag) }, { key: "code", label: "Item", html: p => itemCell(p.code) },
        { key: "source", label: "Source", sort: p => p.complaint || "~", html: sourceHtml }] })}
      <div class="card-footer d-flex"><span class="text-secondary small align-self-center">Only ${esc(b.company)} pieces in store are listed.</span>
        <button type="button" class="btn btn-quiet ms-auto" onclick="addTicked('${b.no}')">${icon("check")} Add ticked</button></div></div></div>`;
}
function batchSentCards(b, rows, sentRows) {
  return `<div class="col-12"><div class="alert alert-secondary mb-0">${icon("lock")} Dispatched on ${fmt(b.dispatchedOn)}, so this batch is locked: pieces can't be added or removed.
      Settle each piece when the company answers.</div></div>
    <div class="col-12"><div class="card">
      <div class="card-header"><h3 class="card-title">${icon("tags")} Pieces</h3><span class="badge bg-secondary-lt ms-2">${rows.length}</span>
        <div class="card-subtitle ms-2 text-secondary">${sentRows.length ? `${sentRows.length} still with ${esc(b.company)}. Tick the ones they answered for.` : "All pieces are settled."}</div></div>
      ${dataTable("b-lines", { rows, sort: "tag", paging: false, columns: [
        { key: "sel", label: sentRows.length ? checkbox(sentRows.every(r => bSel.has(r.tag)), `onclick="bSelectAll(this.checked)"`, "Tick all sent pieces") : "", nosort: true, cls: "c-check",
          html: r => r.p.status === "SENT" ? checkbox(bSel.has(r.tag), `data-tag="${r.tag}" onchange="bToggle('${r.tag}',this.checked)"`, `Tick ${r.tag}`)
            : `<span class="text-secondary" title="Already settled">${icon("lock")}</span>` },
        { key: "tag", label: "Tag", html: r => tagLink(r.tag) }, { key: "code", label: "Item", sort: r => r.p.code, html: r => itemCell(r.p.code) },
        { key: "bpkd", label: "Batch · PKD", cls: "nowrap", sort: r => r.p.batch, html: r => batchPkd(r.p) },
        { key: "fault", label: "Fault", cls: "cell-wrap", sort: r => r.p.fault, html: r => esc(r.p.fault) },
        { key: "source", label: "Source", sort: r => r.p.complaint || "~", html: r => sourceHtml(r.p) },
        { key: "outcome", label: "Outcome", sort: r => r.outcome || "", html: r => r.outcome ? oBadge(r.outcome) + `<div class="small text-secondary mt-1">${fmt(r.settledOn)}${r.toLoc ? ` → ${esc(r.toLoc)}` : ""}</div>`
          : pBadge(r.p.status) },
        { key: "entry", label: "Entry", sort: r => r.entry || "", html: r => r.entry ? entryLink(r.entry) : "" }] })}
      ${sentRows.length ? `<div class="card-body settle-panel border-top"><h4 class="mb-3">${icon("gavel")} Settle ticked pieces <span class="text-secondary fw-normal" id="settle-count"></span></h4>
        <div class="row g-3 align-items-start">
          ${fcol(12, lbl("", "Company's answer") + selectgroup("s-outcome", [["REPLACED", "Replaced", "replace"], ["REPAIRED", "Repaired", "tool"],
            ["REJECTED_RETURNED", "Rejected (returned)", "arrow-back"], ["REJECTED_SCRAPPED", "Rejected (scrapped)", "trash"]], "REPLACED", "settleOutcomeChanged()"))}
          ${fcol(3, lbl("s-date", "Date answered") + `<input id="s-date" type="date" class="form-control" value="${today()}" min="${b.dispatchedOn}" max="${today()}">`)}
          ${fcol(3, lbl("s-loc", "Goes into location") + `<select id="s-loc" class="form-select" onchange="field('settle-err').innerHTML=''"><option value="">Choose…</option>${opt(DB.locations)}</select>`, "w-sloc")}
          <div class="col-12 col-md-6"><div class="text-secondary small pt-md-4" id="settle-hint"></div></div>
        </div>
        <div class="d-flex mt-3"><button type="button" class="btn btn-primary ms-auto" onclick="doSettle('${b.no}')">${icon("check")} Settle ticked pieces</button></div>
        <div id="settle-err"></div></div>` : ""}
    </div></div>`;
}
function settleOutcomeChanged() {
  const o = radioVal("s-outcome"), good = o === "REPLACED" || o === "REPAIRED";
  if (field("settle-err")) field("settle-err").innerHTML = "";
  field("w-sloc").hidden = !good;
  field("settle-hint").innerHTML = icon("info-circle") + " " + {
    REPLACED: "Posts a <b>Stock IN</b> (replacement from company) into the chosen good-stock location, so its stock goes up.",
    REPAIRED: "Posts a <b>Stock IN</b> (repaired piece back from company) into the chosen good-stock location.",
    REJECTED_RETURNED: `The company sent the piece back. It returns to the <b>${esc(DB.defStore)}</b>; you can batch it again or scrap it.`,
    REJECTED_SCRAPPED: "The company kept and scrapped it. Nothing is posted: the piece already left with the dispatch.",
  }[o];
  field("settle-count").textContent = bSel.size ? `(${bSel.size} ticked)` : "";
}
function bToggle(tag, on) { on ? bSel.add(tag) : bSel.delete(tag); settleOutcomeChanged(); field("settle-err").innerHTML = ""; }
function bSelectAll(on) { document.querySelectorAll("#dt-b-lines input[data-tag]").forEach(c => { c.checked = on; on ? bSel.add(c.dataset.tag) : bSel.delete(c.dataset.tag); }); settleOutcomeChanged(); }
function doSettle(no) {
  const b = batch(no), o = radioVal("s-outcome"), tags = [...bSel];
  const r = settlePieces(b, tags, { outcome: o, date: field("s-date").value, loc: field("s-loc").value });
  if (r.error) { inlineErr("settle-err", r.error); if (r.focus) field(r.focus).focus(); return; }
  bSel.clear();
  toastAfterNav(`${tags.length} piece(s) settled as <b>${OUTCOME[o]}</b>.${r.entries.length ? ` Entries: ${r.entries.join(", ")}.` : ""}`);
  route();
}
function addByTag(no) {
  const t = field("add-tag").value.trim().toUpperCase().replace(/^DEF-?(\d+)$/, (m, n) => `DEF-${n.padStart(4, "0")}`);
  if (!t) return inlineErr("add-err", "Type a tag, e.g. DEF-0042.");
  if (!piece(t)) return inlineErr("add-err", `There is no piece tagged ${t}.`);
  const err = addPieces(batch(no), [t]);
  if (err) return inlineErr("add-err", err);
  toastAfterNav(`${t} added to <b>${no}</b>.`); route();
}
function addTicked(no) {
  const tags = [...window._addSel];
  const err = addPieces(batch(no), tags);
  if (err) return inlineErr("add-err", err);
  toastAfterNav(`${tags.length} piece(s) added to <b>${no}</b>.`); route();
}
function doRemovePiece(no, tag) {
  const err = removePiece(batch(no), tag);
  if (err) return inlineErr("b-err", err);
  toastAfterNav(`${tag} removed from ${no}. It is back in store.`); route();
}
function askDispatch(no) {
  const b = batch(no);
  openModal(`<div class="modal-header"><h5 class="modal-title">${icon("truck")} Dispatch ${b.no} to ${esc(b.company)}</h5>
      <button type="button" class="btn-close" aria-label="Close" onclick="closeModal()"></button></div>
    <div class="modal-body"><p class="text-secondary">${b.lines.length} piece(s). This posts a Stock OUT from the ${esc(DB.defStore)} and locks the batch.</p>
      <div class="row g-3">
      ${fcol(4, lbl("d-date", "Dispatch date") + `<input id="d-date" type="date" class="form-control" value="${today()}" min="${b.createdOn}" max="${today()}">`)}
      ${fcol(4, lbl("d-courier", "Courier") + `<select id="d-courier" class="form-select"><option value="">Choose…</option>${opt(DB.couriers)}</select>`)}
      ${fcol(4, lbl("d-docket", "Docket / LR no.") + `<input id="d-docket" class="form-control code" placeholder="e.g. D51243817">`)}
      </div><div id="dm-err"></div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
      <button type="button" class="btn btn-out ms-auto" onclick="doDispatch('${b.no}')">${icon("truck")} Dispatch</button></div>`, "modal-lg");
}
function doDispatch(no) {
  const b = batch(no), r = dispatchBatch(b, { date: field("d-date").value, docket: field("d-docket").value, courier: field("d-courier").value });
  if (r.error) { inlineErr("dm-err", r.error); if (r.focus) field(r.focus).focus(); return; }
  closeModal(); toastAfterNav(`${no} dispatched. Stock OUT <b>${r.entry.no}</b> posted from the ${esc(DB.defStore)}.`); route();
}
