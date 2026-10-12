/* Service data layer: sites, technicians, complaints (+ events, visits), defective pieces (+ events), return batches.
   These functions mirror the real app's services (complaints.services, defectives.services): they are the only
   write path, they check every rule, and every stock effect goes through post() on the shared ledger. */

const CSTATUS = { NOT_ATTENDED: "Not attended", ATTENDED: "Attended", MATERIAL_CHECK: "Material need to check",
  AWAITING_MATERIAL: "Awaiting material", RESOLVED: "Resolved", CLOSED: "Closed", NOT_COVERED: "Not covered" };
// Colour + icon + word. Red = needs attention, yellow = waiting, green = done well, grey = neutral / finished.
const CSTYLE = { NOT_ATTENDED: ["st-alert", "alert-circle"], ATTENDED: ["st-neutral", "tool"], MATERIAL_CHECK: ["st-neutral", "zoom-question"],
  AWAITING_MATERIAL: ["st-wait", "hourglass"], RESOLVED: ["st-ok", "circle-check"], CLOSED: ["st-done", "lock"], NOT_COVERED: ["st-done", "ban"] };
const OPEN_STATUSES = ["NOT_ATTENDED", "ATTENDED", "MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"];
const TRANSITIONS = {   // same dict as the real app; NOT_COVERED has its own action (needs a reason)
  NOT_ATTENDED: ["ATTENDED", "NOT_COVERED"],
  ATTENDED: ["MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED", "NOT_COVERED"],
  MATERIAL_CHECK: ["ATTENDED", "AWAITING_MATERIAL", "RESOLVED", "NOT_COVERED"],
  AWAITING_MATERIAL: ["ATTENDED", "MATERIAL_CHECK", "RESOLVED", "NOT_COVERED"],
  RESOLVED: ["CLOSED", "ATTENDED", "NOT_COVERED"],
  CLOSED: [],          // only Admin can reopen (moves it to Attended)
  NOT_COVERED: [],
};
const PRIORITIES = ["Normal", "High", "Urgent"];
const PSTATUS = { IN_STORE: "In store", IN_BATCH: "In draft batch", SENT: "Sent to company", SETTLED: "Settled", SCRAPPED: "Scrapped" };
const PSTYLE = { IN_STORE: ["st-neutral", "building-warehouse"], IN_BATCH: ["st-neutral", "packages"], SENT: ["st-wait", "truck"],
  SETTLED: ["st-ok", "circle-check"], SCRAPPED: ["st-done", "trash"] };
const OUTCOME = { REPLACED: "Replaced", REPAIRED: "Repaired", REJECTED_RETURNED: "Rejected (returned)", REJECTED_SCRAPPED: "Rejected (scrapped)" };
const OSTYLE = { REPLACED: ["st-ok", "replace"], REPAIRED: ["st-ok", "tool"], REJECTED_RETURNED: ["st-alert", "arrow-back"], REJECTED_SCRAPPED: ["st-alert", "trash"] };
const SOURCE = { SITE_VISIT: "Site visit", FOUND_IN_STOCK: "Found in stock" };
const BSTYLE = { Draft: ["st-neutral", "pencil"], Dispatched: ["st-wait", "truck"], "Partly settled": ["st-wait", "progress-check"], Settled: ["st-ok", "circle-check"] };
let ROLE = "Office";   // mockup role switch (user menu): Admin may reopen closed complaints
const svcSeq = { CMP: 0, VIS: 0, DEF: 0, RB: 0, site: 0 };

function initService() {
  const n = s => Number(String(s).split("-")[1]);
  for (const c of DB.complaints) svcSeq.CMP = Math.max(svcSeq.CMP, n(c.no));
  for (const v of DB.visits) svcSeq.VIS = Math.max(svcSeq.VIS, n(v.no));
  for (const p of DB.pieces) svcSeq.DEF = Math.max(svcSeq.DEF, n(p.tag));
  for (const b of DB.batches) svcSeq.RB = Math.max(svcSeq.RB, n(b.no));
  svcSeq.site = Math.max(0, ...DB.sites.map(s => s.id));
}
const nextNo = (k, pfx) => `${pfx}-${String(++svcSeq[k]).padStart(4, "0")}`;
const badge = ([cls, ic], word) => `<span class="badge st ${cls}">${icon(ic)}${esc(word)}</span>`;
const cBadge = s => badge(CSTYLE[s], CSTATUS[s]);
const pBadge = s => badge(PSTYLE[s], PSTATUS[s]);
const oBadge = o => o ? badge(OSTYLE[o], OUTCOME[o]) : "";
const bBadge = b => badge(BSTYLE[batchStatus(b)], batchStatus(b));
const prioBadge = p => p === "Urgent" ? `<span class="badge st st-alert">${icon("urgent")}Urgent</span>`
  : p === "High" ? `<span class="badge st st-wait">${icon("arrow-up")}High</span>` : `<span class="text-secondary">Normal</span>`;

/* ---------- lookups ---------- */
const complaint = no => DB.complaints.find(c => c.no === no);
const site = id => DB.sites.find(s => s.id === Number(id));
const siteName = c => { const s = site(c.site); return s ? s.name : "?"; };
const siteCity = c => { const s = site(c.site); return s ? s.city : ""; };
const piece = tag => DB.pieces.find(p => p.tag === tag);
const batch = no => DB.batches.find(b => b.no === no);
const visit = no => DB.visits.find(v => v.no === no);
const isOpen = c => OPEN_STATUSES.includes(c.status);
const daysBetween = (a, b) => Math.round((new Date(b + "T00:00:00") - new Date(a + "T00:00:00")) / 86400000);
const ageDays = c => daysBetween(c.reportedOn, c.closedOn || today());
const AGE_BUCKETS = [["0-2", "0–2 days", 0, 2], ["3-7", "3–7 days", 3, 7], ["8-15", "8–15 days", 8, 15], ["15+", "Over 15 days", 16, 1e9]];
const ageBucket = d => AGE_BUCKETS.find(b => d >= b[2] && d <= b[3])[0];
const cEvents = no => DB.complaintEvents.filter(e => e.complaint === no);
const pEvents = tag => DB.pieceEvents.filter(e => e.tag === tag);
const cities = () => uniq(DB.sites.map(s => s.city)).sort();
const activeTechs = () => DB.techs.filter(t => t.active).map(t => t.name);
// Days awaiting material = the sum of the intervals spent in AWAITING_MATERIAL (the paused-SLA clock).
function awaitingDays(c) {
  let total = 0, since = null;
  for (const e of cEvents(c.no)) {
    if (since && e.to !== "AWAITING_MATERIAL") { total += daysBetween(since, e.at); since = null; }
    if (e.to === "AWAITING_MATERIAL" && !since) since = e.at;
  }
  if (since) total += daysBetween(since, c.closedOn || today());
  return total;
}
// Derived, never stored: Draft / Dispatched / Partly settled / Settled.
function batchStatus(b) {
  if (b.status === "DRAFT") return "Draft";
  const done = b.lines.filter(l => l.outcome).length;
  return done === 0 ? "Dispatched" : done < b.lines.length ? "Partly settled" : "Settled";
}
const inStoreCount = () => DB.pieces.filter(p => p.status === "IN_STORE" || p.status === "IN_BATCH").length;

/* ---------- sites + technicians ---------- */
function saveSite(d) {
  const name = d.name.trim().replace(/\s+/g, " ");
  if (!name) return { error: "Enter the site name." };
  if (!d.city.trim()) return { error: "Enter the city." };
  if (DB.sites.some(s => s.name.toLowerCase() === name.toLowerCase() && s.city.toLowerCase() === d.city.trim().toLowerCase()))
    return { error: `${name}, ${d.city.trim()} already exists. Pick it from the list.` };
  if (d.phone && !/^[6-9]\d{9}$/.test(d.phone.replace(/\s/g, ""))) return { error: "Phone must be a 10-digit mobile number." };
  const s = { id: ++svcSeq.site, name, city: d.city.trim(), contact: d.contact.trim(), phone: d.phone.replace(/\s/g, ""), address: (d.address || "").trim(), active: true };
  DB.sites.push(s);
  return { site: s };
}
function saveTech(name, phone) {
  name = name.trim();
  if (!name) return "Enter the technician's name.";
  if (DB.techs.some(t => t.name.toLowerCase() === name.toLowerCase())) return `${name} is already in the list.`;
  if (phone && !/^[6-9]\d{9}$/.test(phone)) return "Phone must be a 10-digit mobile number.";
  DB.techs.push({ name, phone, active: true }); DB.technicians.push(name);
  return null;
}

/* ---------- complaints ---------- */
function logC(c, from, to, at, note = "", reason = "") {
  DB.complaintEvents.push({ complaint: c.no, from, to, at, by: ROLE, note, ...(reason ? { reason } : {}) });
}
function fileComplaint(d) {
  if (!d.site) return { error: "Choose the site.", focus: "site" };
  if (!d.company) return { error: "Choose the company whose product failed.", focus: "company" };
  if (!d.fault.trim()) return { error: "Describe the fault.", focus: "c-fault" };
  if (!d.reportedOn) return { error: "Choose the date the complaint was reported.", focus: "c-date" };
  if (d.reportedOn > today()) return { error: "The reported date can't be in the future.", focus: "c-date" };
  if (d.qty !== null && (!Number.isInteger(d.qty) || d.qty < 1)) return { error: "Quantity affected must be a whole number of 1 or more.", focus: "c-qty" };
  const c = { no: nextNo("CMP", "CMP"), site: d.site, company: d.company, companyRef: d.companyRef.trim(), fault: d.fault.trim(), qty: d.qty,
    reportedOn: d.reportedOn, priority: d.priority, techs: d.techs, status: "NOT_ATTENDED", contact: d.contact.trim(), phone: d.phone.trim(),
    notCoveredReason: "", closedOn: null };
  DB.complaints.push(c);
  logC(c, null, "NOT_ATTENDED", today(), "Complaint filed");
  return { complaint: c };
}
// Checked against TRANSITIONS; a move that isn't allowed returns a friendly message and changes nothing.
function changeStatus(c, to, note = "", reason = "") {
  if (c.status === "CLOSED" && to === "ATTENDED") {
    if (ROLE !== "Admin") return "A closed complaint can't move to Attended. Only Admin can reopen it.";
    if (!note.trim()) return "Write why the complaint is being reopened.";
    logC(c, c.status, to, today(), "Reopened: " + note.trim()); c.status = to; c.closedOn = null; return null;
  }
  if (c.status === to) return `This complaint is already ${CSTATUS[to]}.`;
  if (!TRANSITIONS[c.status].includes(to))
    return `A complaint that is ${CSTATUS[c.status]} can't move to ${CSTATUS[to]}.` + (TRANSITIONS[c.status].length ? ` Allowed: ${TRANSITIONS[c.status].map(s => CSTATUS[s]).join(", ")}.` : "");
  if (to === "NOT_COVERED") {
    if (!reason) return "Choose why the complaint is not covered.";
    if (reason === "Other" && !note.trim()) return "Write a note when the reason is Other.";
  }
  logC(c, c.status, to, today(), note.trim(), reason);
  c.status = to;
  if (to === "CLOSED" || to === "NOT_COVERED") c.closedOn = today();
  if (reason) c.notCoveredReason = reason;
  return null;
}
// Statuses a visit can leave the complaint in. A first visit always passes through Attended.
function visitNextOptions(c) {
  const work = ["ATTENDED", "MATERIAL_CHECK", "AWAITING_MATERIAL", "RESOLVED"];
  if (c.status === "NOT_ATTENDED") return work;
  return work.filter(s => s === c.status || TRANSITIONS[c.status].includes(s));
}
function newPiece(d) {
  const p = { tag: nextNo("DEF", "DEF"), code: d.code, company: item(d.code).company, batch: d.batch || "", pkd: d.pkd || "", fault: d.fault || "",
    source: d.source, complaint: d.complaint || null, visit: d.visit || null, collectedOn: d.date, status: "IN_STORE", batchNo: null,
    outcome: null, settledOn: null, entry: d.entry };
  DB.pieces.push(p);
  logP(p.tag, null, "IN_STORE", d.date, d.complaint ? `Collected at site (${d.complaint})` : "Marked defective from stock");
  return p;
}
const logP = (tag, from, to, at, note) => DB.pieceEvents.push({ tag, from, to, at, by: ROLE, note });
/* One transaction: parts OUT (subtype COMPLAINT) + collection IN at the Defective store + one piece per collected unit
   + status change. If the parts OUT would over-issue, nothing at all is saved. */
function recordVisit(c, d) {
  if (!isOpen(c)) return { error: `This complaint is ${CSTATUS[c.status]}, so visits can't be added.` };
  if (!d.date) return { error: "Choose the visit date.", focus: "v-date" };
  if (d.date > today()) return { error: "The visit date can't be in the future.", focus: "v-date" };
  if (d.date < c.reportedOn) return { error: `The visit can't be before the complaint was reported (${fmt(c.reportedOn)}).`, focus: "v-date" };
  if (!d.techs.length) return { error: "Choose who attended.", focus: "v-techs" };
  if (!d.work.trim()) return { error: "Write what work was done.", focus: "v-work" };
  if (!visitNextOptions(c).includes(d.next)) return { error: `A complaint that is ${CSTATUS[c.status]} can't move to ${CSTATUS[d.next]}.` };
  const s = site(c.site), party = `${s.name}, ${s.city}`, vno = `VIS-${String(svcSeq.VIS + 1).padStart(4, "0")}`;
  let out = null, col = null;
  if (d.parts.length) {
    out = { kind: "OUT", subtype: "COMPLAINT", date: d.date, party, ref: c.no, complaint: c.no, note: `Visit ${vno}`,
      lines: d.parts.map(l => ({ code: l.code, loc: d.loc, qty: -l.qty })) };
    const err = post(out);
    if (err) return { error: `Parts given: ${err} Nothing was saved.` };
  }
  svcSeq.VIS++;
  const tags = [];
  if (d.collected.length) {
    col = { kind: "IN", subtype: "DEFECTIVE_COLLECTED", date: d.date, party, ref: c.no, complaint: c.no, note: `Visit ${vno}`,
      lines: d.collected.map(l => ({ code: l.code, loc: DB.defStore, qty: l.qty, batch: l.batch, pkd: l.pkd })) };
    post(col);
    for (const l of d.collected) for (let i = 0; i < l.qty; i++)
      tags.push(newPiece({ ...l, date: d.date, source: "SITE_VISIT", complaint: c.no, visit: vno, entry: col.no }).tag);
  }
  DB.visits.push({ no: vno, complaint: c.no, date: d.date, techs: d.techs, work: d.work.trim(), nextStatus: d.next,
    outEntry: out ? out.no : null, collectEntry: col ? col.no : null, tags });
  for (const t of d.techs) if (!c.techs.includes(t)) c.techs.push(t);
  if (c.status === "NOT_ATTENDED") { logC(c, c.status, "ATTENDED", d.date, `Visit ${vno}`); c.status = "ATTENDED"; }
  if (d.next !== c.status) { logC(c, c.status, d.next, d.date, `Visit ${vno}`); c.status = d.next; }
  return { visit: vno, tags, out, col };
}

/* ---------- defective pieces ---------- */
// TRF from a good location to the Defective store, then one tagged piece per unit.
function markDefective(d) {
  if (!d.date) return { error: "Choose the date.", focus: "f-date" };
  if (d.date > today()) return { error: "The date can't be in the future.", focus: "f-date" };
  const missing = d.lines.findIndex(l => !l.fault.trim());
  if (missing >= 0) return { error: `Line ${missing + 1}: write what is wrong with the piece.` };
  const e = { kind: "TRF", date: d.date, party: DB.defStore, note: "Marked defective",
    lines: d.lines.flatMap(l => [{ code: l.code, loc: d.loc, qty: -l.qty }, { code: l.code, loc: DB.defStore, qty: l.qty }]) };
  const err = post(e);
  if (err) return { error: err + " Nothing was saved." };
  const tags = [];
  for (const l of d.lines) for (let i = 0; i < l.qty; i++)
    tags.push(newPiece({ code: l.code, fault: l.fault.trim(), date: d.date, source: "FOUND_IN_STOCK", entry: e.no }).tag);
  return { tags, entry: e };
}
function addPieces(b, tags) {
  if (b.status !== "DRAFT") return `${b.no} was dispatched on ${fmt(b.dispatchedOn)}, so it is locked. Start a new batch.`;
  if (!tags.length) return "Tick at least one piece.";
  for (const t of tags) {
    const p = piece(t);
    if (p.company !== b.company) return `${b.no} is for ${b.company}, but ${t} is a ${p.company} piece. A batch holds one company's pieces only.`;
    if (p.status !== "IN_STORE") return `${t} is ${PSTATUS[p.status].toLowerCase()}${p.batchNo ? ` (${p.batchNo})` : ""}. Only pieces in store can be added.`;
  }
  for (const t of tags) {
    const p = piece(t);
    p.status = "IN_BATCH"; p.batchNo = b.no;
    b.lines.push({ tag: t, outcome: null, settledOn: null, toLoc: null, entry: null });
    logP(t, "IN_STORE", "IN_BATCH", today(), `Added to ${b.no}`);
  }
  return null;
}
function createBatch(company, tags, note = "") {
  if (!company) return { error: "Choose the company the pieces go back to.", focus: "b-company" };
  const odd = tags.map(piece).find(p => p.company !== company);
  if (odd) return { error: `${odd.tag} is a ${odd.company} piece. A batch holds one company's pieces only.` };
  const b = { no: nextNo("RB", "RB"), company, createdOn: today(), status: "DRAFT", dispatchedOn: null, docket: "", courier: "", note: note.trim(),
    dispatchEntry: null, lines: [] };
  DB.batches.push(b);
  if (tags.length) addPieces(b, tags);
  return { batch: b };
}
function removePiece(b, tag) {
  if (b.status !== "DRAFT") return `${b.no} is dispatched and locked.`;
  const p = piece(tag);
  b.lines = b.lines.filter(l => l.tag !== tag);
  p.status = "IN_STORE"; p.batchNo = null;
  logP(tag, "IN_BATCH", "IN_STORE", today(), `Removed from ${b.no}`);
  return null;
}
// Locks the batch and posts one OUT (RETURN_TO_COMPANY) from the Defective store.
function dispatchBatch(b, d) {
  if (b.status !== "DRAFT") return { error: `${b.no} was already dispatched.` };
  if (!b.lines.length) return { error: "An empty batch can't be dispatched. Add pieces first." };
  if (!d.date) return { error: "Choose the dispatch date.", focus: "d-date" };
  if (d.date > today()) return { error: "The dispatch date can't be in the future.", focus: "d-date" };
  if (!d.courier) return { error: "Choose the courier.", focus: "d-courier" };
  if (!d.docket.trim()) return { error: "Enter the docket / LR number.", focus: "d-docket" };
  const q = {};
  for (const l of b.lines) { const c = piece(l.tag).code; q[c] = (q[c] || 0) + 1; }
  const e = { kind: "OUT", subtype: "RETURN_TO_COMPANY", date: d.date, party: b.company, ref: d.docket.trim(), batch: b.no,
    note: `${d.courier} ${d.docket.trim()}`, lines: Object.entries(q).map(([code, n]) => ({ code, loc: DB.defStore, qty: -n })) };
  const err = post(e);
  if (err) return { error: err };
  Object.assign(b, { status: "DISPATCHED", dispatchedOn: d.date, docket: d.docket.trim(), courier: d.courier, dispatchEntry: e.no });
  for (const l of b.lines) { piece(l.tag).status = "SENT"; logP(l.tag, "IN_BATCH", "SENT", d.date, `Dispatched with ${b.no} (${d.courier} ${d.docket.trim()})`); }
  return { entry: e };
}
/* Per-piece settlement. REPLACED / REPAIRED: stock IN (REPLACEMENT) to a good location. REJECTED_RETURNED: IN back to the
   Defective store, piece back in store. REJECTED_SCRAPPED: nothing to post (it already left with the dispatch OUT). */
function settlePieces(b, tags, d) {
  if (b.status !== "DISPATCHED") return { error: "Only a dispatched batch can be settled." };
  if (!tags.length) return { error: "Tick the pieces the company has answered for." };
  if (!d.outcome) return { error: "Choose the outcome." };
  if (!d.date) return { error: "Choose the settlement date.", focus: "s-date" };
  if (d.date > today()) return { error: "The date can't be in the future.", focus: "s-date" };
  if (d.date < b.dispatchedOn) return { error: `The date can't be before the batch was dispatched (${fmt(b.dispatchedOn)}).`, focus: "s-date" };
  const good = d.outcome === "REPLACED" || d.outcome === "REPAIRED";
  if (good && !DB.locations.includes(d.loc)) return { error: "Choose the good-stock location the replacement pieces go into.", focus: "s-loc" };
  for (const t of tags) if (piece(t).status !== "SENT") return { error: `${t} is not waiting on the company (it is ${PSTATUS[piece(t).status].toLowerCase()}). Only sent pieces can be settled.` };
  const entries = [];
  for (const t of tags) {
    const p = piece(t), l = b.lines.find(x => x.tag === t);
    let e = null;
    if (good) e = { kind: "IN", subtype: "REPLACEMENT", date: d.date, party: b.company, ref: b.no, batch: b.no, note: `${OUTCOME[d.outcome]} for ${t}`,
      lines: [{ code: p.code, loc: d.loc, qty: 1, batch: "", pkd: "" }] };
    if (d.outcome === "REJECTED_RETURNED") e = { kind: "IN", subtype: "DEFECTIVE_RETURNED", date: d.date, party: b.company, ref: b.no, batch: b.no,
      note: `Rejected by company, ${t} sent back`, lines: [{ code: p.code, loc: DB.defStore, qty: 1, batch: p.batch, pkd: p.pkd }] };
    if (e) { post(e); entries.push(e.no); }
    Object.assign(l, { outcome: d.outcome, settledOn: d.date, toLoc: good ? d.loc : null, entry: e ? e.no : null });
    const to = d.outcome === "REJECTED_RETURNED" ? "IN_STORE" : "SETTLED";
    logP(t, "SENT", to, d.date, `${b.no}: ${OUTCOME[d.outcome]}${good ? ` → ${d.loc}` : ""}`);
    Object.assign(p, { status: to, outcome: d.outcome, settledOn: d.date, batchNo: to === "IN_STORE" ? null : p.batchNo });
  }
  return { entries };
}
// ADJ (Damaged) −1 per piece at the Defective store.
function scrapPieces(tags, reason, note) {
  if (!tags.length) return "Tick at least one piece.";
  if (!reason) return "Choose why the pieces are scrapped.";
  for (const t of tags) { const p = piece(t);
    if (p.status !== "IN_STORE") return `${t} is ${PSTATUS[p.status].toLowerCase()}${p.batchNo ? ` (${p.batchNo})` : ""}. Only pieces in store can be scrapped${p.status === "IN_BATCH" ? "; remove it from the batch first" : ""}.`; }
  const q = {};
  for (const t of tags) { const c = piece(t).code; q[c] = (q[c] || 0) + 1; }
  const e = { kind: "ADJ", date: today(), reason: "Damaged", note: `Scrapped ${tags.join(", ")}: ${reason}${note ? " · " + note : ""}`,
    lines: Object.entries(q).map(([code, n]) => ({ code, loc: DB.defStore, qty: -n })) };
  const err = post(e);
  if (err) return err;
  for (const t of tags) { const p = piece(t); logP(t, "IN_STORE", "SCRAPPED", today(), reason); Object.assign(p, { status: "SCRAPPED", settledOn: today(), entry: e.no }); }
  return null;
}
