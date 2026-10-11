/* SVKML mockup core: fake data, the stock ledger, and the "services" all three systems share.
   Everything lives in memory; reloading the page resets it. Mirrors the rules the real app will enforce. */

/* ============================== Helpers ============================== */
const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const norm = s => (s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").trim();
const key = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
  .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
const pad = (n, w = 4) => String(n).padStart(w, "0");
const fmt = d => `${pad(d.getDate(), 2)}-${pad(d.getMonth() + 1, 2)}-${d.getFullYear()}`;
const today = () => fmt(new Date());
const parseDate = s => { const [d, m, y] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const daysBetween = (a, b) => Math.round((parseDate(b) - parseDate(a)) / 86400000);
const daysAgo = n => { const d = new Date(); d.setDate(d.getDate() - n); return fmt(d); };
const sum = (arr, f) => arr.reduce((a, x) => a + f(x), 0);
const uniq = arr => [...new Set(arr)];

/* ============================== Master data ============================== */
const LOCATIONS = ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"];
const TECHNICIANS = ["Ramu", "Apparao"];
const USERS = { Office: "OFFICE", Admin: "ADMIN", Ramu: "TECHNICIAN", Apparao: "TECHNICIAN" };
let ME = "Office";
const isTech = () => USERS[ME] === "TECHNICIAN";

const TYPE_LABEL = { FITTING: "Fitting", DRIVER: "Driver", PCB: "PCB / LED module", LENS: "Lens",
  CONTROLLER: "Controller", SWITCH: "Switch", ACCESSORY: "Accessory", OTHER: "Other" };
// Codes from the client's 25-5-2026 sample sheets. [code, type, description, reorder level, aliases]
const ITEMS = [
  ["LG78-150-700", "DRIVER", "150W driver 700mA", 5, ["EDC-150-S105SV-3007"]],
  ["LG76-150-700FH", "DRIVER", "150W driver 700mA FH", 10, []],
  ["LG76-200-700F", "DRIVER", "200W driver 700mA", 10, []],
  ["LG75-150-215-70E", "DRIVER", "150W driver", 5, []],
  ["LG83-072-103-0700", "DRIVER", "72W driver", 10, []],
  ["LG30-018-054-0300", "DRIVER", "18W driver 300mA", 10, ["LG30-018-054-300"]],
  ["LG26-048-0720", "DRIVER", "48W driver 720mA", 5, ["LG26-048-720"]],
  ["LG66-036-036-900S", "DRIVER", "36W driver 900mA", 5, []],
  ["LG66-040-078-480IT", "DRIVER", "40W driver 480mA", 5, []],
  ["15WATT (190MA)", "DRIVER", "15W driver 190mA (generic)", 10, ["15WATT DRIVERS"]],
  ["18WATT DRIVERS", "DRIVER", "18W driver (generic)", 10, []],
  ["R1103-092-PA", "DRIVER", "Driver (R1103)", 0, ["RI103-092-PA"]],
  ["EIO6006", "PCB", "LED module", 10, []],
  ["EIO9326", "PCB", "LED module", 10, []],
  ["EIO8437", "PCB", "LED module", 5, ["EI08437"]],
  ["WPWG-5050-15SIP", "PCB", "LED strip PCB", 5, []],
  ["FTS-KC-60-57K", "PCB", "LED PCB 5700K", 50, []],
  ["LF40-192-060-57-HE", "FITTING", "Flood light 192W", 2, []],
  ["LL20-111-XXX-65-NE3", "FITTING", "Linear fitting", 0, ["LL20-111-XXX-65NE3"]],
  ["LF20-102-060-57-G3", "FITTING", "Flood light 102W", 5, []],
  ["LENS", "LENS", "Lens (generic)", 0, []],
  ["BULCK HEAD", "ACCESSORY", "Bulkhead (generic)", 0, []],
  ["ISENSE DALI CONTROLLER (WCS-IS-DA4)", "CONTROLLER", "iSense DALI controller", 0, []],
].map(([code, type, desc, reorder, aliases]) => ({ code, type, desc, reorder, aliases }));
const item = code => ITEMS.find(i => i.code === code);

/* Item lookup: exact code, alias, look-alike spelling (O/0, I/1, hyphens, leading zeros), then near misses. */
function lev(a, b) {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
function lookup(text) {
  const t = norm(text), k = key(text);
  if (!t) return {};
  for (const i of ITEMS) {
    if (i.code === t) return { item: i };
    if (i.aliases.includes(t) || key(i.code) === k || i.aliases.some(a => key(a) === k)) return { item: i, via: t };
  }
  const suggest = ITEMS.map(i => ({ i, d: Math.min(lev(key(i.code), k), ...i.aliases.map(a => lev(key(a), k))) }))
    .filter(x => x.d <= 2 || key(x.i.code).includes(k) || (t.length > 2 && x.i.desc.toUpperCase().includes(t)))
    .sort((a, b) => a.d - b.d).slice(0, 3).map(x => x.i);
  return { suggest };
}

/* ============================== Stock ledger (append-only) ============================== */
const DOC = {
  RECEIVED_FROM_WIPRO: { dir: "IN", bucket: "FRESH", label: "Fresh received from Wipro", hint: "New spares arrived (DC / invoice)" },
  OPENING: { dir: "IN", bucket: "FRESH", label: "Opening count", hint: "First stock count (admin only)" },
  ISSUED_TO_COMPLAINT: { dir: "OUT", bucket: "FRESH", label: "Issued to site / complaint", hint: "Fresh spares taken for a repair" },
  SCRAPPED: { dir: "OUT", bucket: "FRESH", label: "Scrapped / written off", hint: "Damaged or lost (reason required)" },
  TRANSFER: { dir: "MOVE", bucket: "FRESH", label: "Transfer between locations", hint: "" },
  // Defective-bucket documents are created only by the Defective Pieces system:
  DEFECTIVE_COLLECTED: { dir: "IN", bucket: "DEFECTIVE", label: "Defective pieces collected", system: "def" },
  DEFECTIVE_OPENING: { dir: "IN", bucket: "DEFECTIVE", label: "Opening defective count", system: "def" },
  RETURNED_TO_WIPRO: { dir: "OUT", bucket: "DEFECTIVE", label: "Defectives sent to Wipro", system: "def" },
  DEFECTIVE_SCRAPPED: { dir: "OUT", bucket: "DEFECTIVE", label: "Defective pieces scrapped", system: "def" },
  DEFECTIVE_MOVED: { dir: "MOVE", bucket: "DEFECTIVE", label: "Defective pieces moved", system: "def" },
};
const PREFIX = { IN: "IN", OUT: "OUT", MOVE: "TRF", REV: "REV" };
let entries = [];
const seq = { IN: 0, OUT: 0, MOVE: 0, REV: 0 };

function balance(code, loc, bucket) {
  let q = 0;
  for (const e of entries) for (const l of e.lines) if (l.code === code && l.loc === loc && l.bucket === bucket) q += l.qty;
  return q;
}
const totalBalance = (code, bucket) => sum(LOCATIONS, l => balance(code, l, bucket));
const bucketName = b => b === "FRESH" ? "Fresh" : "Defective";

// Posts an entry only if no bucket goes negative. Returns an error message, or null and sets e.no.
function post(e) {
  const delta = {};
  for (const l of e.lines) { const k = `${l.code}|${l.loc}|${l.bucket}`; delta[k] = (delta[k] || 0) + l.qty; }
  for (const k in delta) {
    const [code, loc, bucket] = k.split("|"), have = balance(code, loc, bucket);
    if (have + delta[k] < 0) return `Only ${have} NOS of ${code} (${bucketName(bucket)}) at ${loc}.`;
  }
  const dir = e.reverses ? "REV" : DOC[e.type].dir;
  e.no = `${PREFIX[dir]}-${pad(++seq[dir])}`;
  e.by = e.by || ME;
  entries.push(e);
  return null;
}
const entry = no => entries.find(e => e.no === no);
const isReversed = e => entries.some(x => x.reverses === e.no);
function undo(no, reason) {
  const orig = entry(no);
  if (DOC[orig.type].system === "def") return "Defective entries are undone from the Defective Pieces system.";
  return post({ type: orig.type, date: today(), ref: orig.ref, party: orig.party, reverses: no, note: reason,
    lines: orig.lines.map(l => ({ ...l, qty: -l.qty })) });
}
const entryQty = e => e.lines.some(l => l.qty > 0) && e.lines.some(l => l.qty < 0) && !e.reverses
  ? sum(e.lines.filter(l => l.qty > 0), l => l.qty) : sum(e.lines, l => Math.abs(l.qty));

/* ============================== System 2: defective pieces ============================== */
const PIECE_STATUS = {
  AT_SITE: "At site", AT_OFFICE: "At office", IN_RETURN_BATCH: "In return batch", SENT_TO_WIPRO: "With Wipro",
  REPLACED: "Replaced", REJECTED: "Rejected by Wipro", SCRAPPED: "Scrapped" };
const PIECE_NEXT = {
  AT_SITE: ["AT_OFFICE"], AT_OFFICE: ["IN_RETURN_BATCH", "SCRAPPED"], IN_RETURN_BATCH: ["AT_OFFICE", "SENT_TO_WIPRO"],
  SENT_TO_WIPRO: ["REPLACED", "REJECTED"], REJECTED: ["SCRAPPED"], REPLACED: [], SCRAPPED: [] };
const IN_LEDGER = ["AT_OFFICE", "IN_RETURN_BATCH"]; // pieces physically in our DEFECTIVE stock
let pieces = [], batches = [];
const tagSeq = {};
const piece = tag => pieces.find(p => p.tag === tag);
const batch = no => batches.find(b => b.no === no);

function newTag(date) {
  const [, m, y] = date.split("-"), k = y.slice(2) + m;
  tagSeq[k] = (tagSeq[k] || 0) + 1;
  return `DEF-${k}-${pad(tagSeq[k])}`;
}
function move(p, to, note, date) {
  if (!PIECE_NEXT[p.status].includes(to)) throw new Error(`${p.tag}: cannot go from ${PIECE_STATUS[p.status]} to ${PIECE_STATUS[to]}.`);
  p.events.push({ date: date || today(), by: ME, from: p.status, to, note: note || "" });
  p.status = to;
}
// Group pieces into ledger lines: one line per item+location.
const linesFor = (list, sign, locOf = p => p.loc) => Object.values(list.reduce((acc, p) => {
  const k = p.code + "|" + locOf(p);
  acc[k] = acc[k] || { code: p.code, loc: locOf(p), bucket: "DEFECTIVE", qty: 0 };
  acc[k].qty += sign; return acc; }, {}));

/* Record N defective pieces of one item. atSite = known faulty but not yet collected (no stock effect). */
function collectPieces({ code, qty, loc, date, fault, batchCode, pkd, source, ticket, visit, atSite, opening, by }) {
  if (!item(code)) return { error: "Pick a known item." };
  if (!Number.isInteger(qty) || qty < 1) return { error: "Quantity must be a whole number above 0." };
  const made = Array.from({ length: qty }, () => ({
    tag: newTag(date), code, loc, status: atSite ? "AT_SITE" : "AT_OFFICE", batchCode: batchCode || "", pkd: pkd || "",
    fault: fault || "", source: source || "", ticket: ticket || "", visit: visit || "", collectedBy: by || ME,
    collectedOn: date, batch: "", outcome: "", outcomeNote: "", entries: [], replacement: "",
    events: [{ date, by: by || ME, from: "", to: atSite ? "AT_SITE" : "AT_OFFICE", note: opening ? "Opening stock" : (source || "") }] }));
  if (!atSite) {
    const e = { type: opening ? "DEFECTIVE_OPENING" : "DEFECTIVE_COLLECTED", date, party: source, ref: ticket,
      by: by || ME, lines: [{ code, loc, bucket: "DEFECTIVE", qty }] };
    const err = post(e); if (err) return { error: err };
    made.forEach(p => p.entries.push(e.no));
  }
  pieces.push(...made);
  return { pieces: made };
}
function markCollected(tags, date) {
  const list = tags.map(piece).filter(p => p.status === "AT_SITE");
  if (!list.length) return "No 'at site' pieces selected.";
  const e = { type: "DEFECTIVE_COLLECTED", date, party: "Collected from site", lines: linesFor(list, +1) };
  const err = post(e); if (err) return err;
  list.forEach(p => { move(p, "AT_OFFICE", "Brought to office", date); p.entries.push(e.no); });
  return null;
}
function movePieces(tags, to) {
  const list = tags.map(piece).filter(p => p.status === "AT_OFFICE" && p.loc !== to);
  if (!list.length) return "Pick pieces that are at the office (and not already at " + to + ").";
  const e = { type: "DEFECTIVE_MOVED", date: today(), note: `Moved to ${to}`,
    lines: [...linesFor(list, -1), ...linesFor(list, +1, () => to)] };
  const err = post(e); if (err) return err;
  list.forEach(p => { p.events.push({ date: today(), by: ME, from: p.status, to: p.status, note: `Moved ${p.loc} → ${to}` }); p.loc = to; p.entries.push(e.no); });
  return null;
}
function scrapPieces(tags, reason) {
  if (!reason.trim()) return "Please give a reason for scrapping.";
  const list = tags.map(piece).filter(p => ["AT_OFFICE", "REJECTED"].includes(p.status));
  if (!list.length) return "Only pieces at the office or rejected by Wipro can be scrapped.";
  const inStock = list.filter(p => p.status === "AT_OFFICE");
  if (inStock.length) {
    const e = { type: "DEFECTIVE_SCRAPPED", date: today(), note: reason, lines: linesFor(inStock, -1) };
    const err = post(e); if (err) return err;
    inStock.forEach(p => p.entries.push(e.no));
  }
  list.forEach(p => move(p, "SCRAPPED", reason));
  settleBatches();
  return null;
}

/* Return batches: DRAFT → SENT → SETTLED (when every piece has a Wipro outcome). */
function createBatch(tags, date = today()) {
  const list = tags.map(piece).filter(p => p.status === "AT_OFFICE");
  if (!list.length) return { error: "Tick pieces that are at the office." };
  const b = { no: `RB-${date.slice(6)}-${pad(batches.length + 1, 3)}`, created: date, status: "DRAFT",
    sentOn: "", docket: "", sentEntry: "", tags: list.map(p => p.tag) };
  list.forEach(p => { move(p, "IN_RETURN_BATCH", `Added to ${b.no}`, date); p.batch = b.no; });
  batches.push(b);
  return { batch: b };
}
function addToBatch(no, tags) {
  const b = batch(no), list = tags.map(piece).filter(p => p.status === "AT_OFFICE");
  list.forEach(p => { move(p, "IN_RETURN_BATCH", `Added to ${b.no}`); p.batch = b.no; b.tags.push(p.tag); });
  return list.length;
}
function removeFromBatch(no, tag) {
  const b = batch(no), p = piece(tag);
  move(p, "AT_OFFICE", `Removed from ${no}`); p.batch = ""; b.tags = b.tags.filter(t => t !== tag);
}
function sendBatch(no, date, docket) {
  const b = batch(no), list = b.tags.map(piece);
  if (!list.length) return "The batch is empty.";
  if (!docket.trim()) return "Enter the docket / challan number.";
  const e = { type: "RETURNED_TO_WIPRO", date, ref: `${no} · ${docket}`, lines: linesFor(list, -1) };
  const err = post(e); if (err) return err;
  list.forEach(p => { move(p, "SENT_TO_WIPRO", `Sent in ${no} (${docket})`, date); p.entries.push(e.no); });
  Object.assign(b, { status: "SENT", sentOn: date, docket, sentEntry: e.no });
  return null;
}
function rejectPieces(tags, note) {
  const list = tags.map(piece).filter(p => p.status === "SENT_TO_WIPRO");
  if (!list.length) return "Tick pieces that are with Wipro.";
  list.forEach(p => { move(p, "REJECTED", note || "Rejected by Wipro"); p.outcome = "REJECTED"; p.outcomeNote = note; });
  settleBatches(); return null;
}
/* Replacement received: one FRESH receipt settles many pieces, and each piece links to it. */
function receiveReplacement(tags, loc, date, dc) {
  const list = tags.map(piece).filter(p => p.status === "SENT_TO_WIPRO");
  if (!list.length) return "Tick pieces that are with Wipro.";
  if (!dc.trim()) return "Enter Wipro's DC number for the replacement.";
  const fresh = Object.values(list.reduce((a, p) => { a[p.code] = a[p.code] || { code: p.code, loc, bucket: "FRESH", qty: 0 }; a[p.code].qty++; return a; }, {}));
  const e = { type: "RECEIVED_FROM_WIPRO", date, ref: `Wipro DC ${dc}`, party: `Replacement for ${uniq(list.map(p => p.batch)).join(", ")}`, lines: fresh };
  const err = post(e); if (err) return err;
  list.forEach(p => { move(p, "REPLACED", `Replacement received (${e.no})`, date); p.outcome = "REPLACED"; p.replacement = e.no; });
  settleBatches(); return null;
}
function settleBatches() {
  for (const b of batches) if (b.status === "SENT" && b.tags.every(t => ["REPLACED", "REJECTED", "SCRAPPED"].includes(piece(t).status))) b.status = "SETTLED";
}
/* Invariant the real app enforces: DEFECTIVE stock == pieces at office + in a draft batch. */
function checkInvariant() {
  const bad = [];
  for (const i of ITEMS) for (const loc of LOCATIONS) {
    const ledger = balance(i.code, loc, "DEFECTIVE");
    const count = pieces.filter(p => p.code === i.code && p.loc === loc && IN_LEDGER.includes(p.status)).length;
    if (ledger !== count) bad.push(`${i.code} @ ${loc}: ledger ${ledger} vs pieces ${count}`);
  }
  return bad;
}

/* ============================== System 3: complaints ============================== */
const CMP_STATUS = { NOT_ATTENDED: "Not attended", ATTENDED: "Attended", MATERIAL_TO_CHECK: "Material to check",
  AWAITING_MATERIAL: "Awaiting material", RESOLVED: "Resolved", CLOSED: "Closed" };
const CMP_NEXT = {
  NOT_ATTENDED: ["CLOSED"], // leaving NOT_ATTENDED otherwise happens by logging a visit
  ATTENDED: ["MATERIAL_TO_CHECK", "AWAITING_MATERIAL", "RESOLVED", "CLOSED"],
  MATERIAL_TO_CHECK: ["ATTENDED", "AWAITING_MATERIAL", "RESOLVED", "CLOSED"],
  AWAITING_MATERIAL: ["ATTENDED", "MATERIAL_TO_CHECK", "RESOLVED", "CLOSED"],
  RESOLVED: ["ATTENDED", "CLOSED"], CLOSED: ["ATTENDED"] };
const CLOSE_REASONS = ["Resolved", "Not a Wipro product", "Customer cancelled", "Other"];
let complaints = [];
let cmpSeq = 0;
const complaint = t => complaints.find(c => c.ticket === t);

function fileComplaint(f) {
  const c = { ticket: `CMP-2026-${pad(++cmpSeq)}`, status: "NOT_ATTENDED", visits: [], closure: "", closeNote: "",
    legacy: "", events: [{ date: f.received, by: ME, from: "", to: "NOT_ATTENDED", note: "Complaint filed" }], ...f };
  complaints.push(c);
  return c;
}
function setStatus(c, to, { reason = "", note = "", date } = {}) {
  if (!CMP_NEXT[c.status].includes(to)) return `Cannot move from ${CMP_STATUS[c.status]} to ${CMP_STATUS[to]}.`;
  if (to === "RESOLVED" && !c.visits.length) return "Log at least one visit before marking resolved.";
  if (to === "CLOSED" && !reason) return "Choose a closure reason.";
  c.events.push({ date: date || today(), by: ME, from: c.status, to, note: to === "CLOSED" ? `${reason}${note ? ": " + note : ""}` : note });
  c.status = to;
  if (to === "CLOSED") { c.closure = reason; c.closeNote = note; } else if (c.closure) { c.closure = ""; c.closeNote = ""; }
  return null;
}
/* A visit: check stock for every part first, then issue parts, collect defectives and move the status, all or nothing. */
function addVisit(c, { date, techs, work, loc, parts, defects, next }) {
  if (!techs.length) return "Tick at least one technician.";
  for (const p of parts) {
    const have = balance(p.code, loc, "FRESH");
    if (p.qty > have) return `Only ${have} NOS of ${p.code} (Fresh) at ${loc}. Nothing was saved.`;
  }
  if (next && next !== c.status && !(c.status === "NOT_ATTENDED" ? ["ATTENDED", "MATERIAL_TO_CHECK", "AWAITING_MATERIAL", "RESOLVED"] : CMP_NEXT[c.status]).includes(next))
    return `Cannot move from ${CMP_STATUS[c.status]} to ${CMP_STATUS[next]}.`;
  const v = { no: c.visits.length + 1, date, techs, work, loc, issueEntry: "", tags: [] };
  const party = `${c.customer} · ${c.ticket}`;
  if (parts.length) {
    const e = { type: "ISSUED_TO_COMPLAINT", date, party, ref: c.ticket, by: techs[0], lines: parts.map(p => ({ code: p.code, loc, bucket: "FRESH", qty: -p.qty })) };
    const err = post(e); if (err) return err;
    v.issueEntry = e.no;
  }
  for (const d of defects) {
    const r = collectPieces({ code: d.code, qty: d.qty, loc, date, fault: d.fault, batchCode: d.batchCode, pkd: d.pkd,
      source: party, ticket: c.ticket, visit: v.no, by: techs[0] });
    if (r.error) return r.error;
    v.tags.push(...r.pieces.map(p => p.tag));
  }
  c.visits.push(v);
  c.techs = uniq([...c.techs, ...techs]);
  const target = next || (c.status === "NOT_ATTENDED" ? "ATTENDED" : c.status);
  if (target !== c.status) {
    c.events.push({ date, by: ME, from: c.status, to: target, note: `Visit ${v.no}` });
    c.status = target;
  }
  return null;
}
/* Ageing: days since received, not counting days spent AWAITING_MATERIAL (clock paused). Closed: frozen at close. */
function ageDays(c) {
  const end = c.status === "CLOSED" ? c.events.filter(e => e.to === "CLOSED").at(-1).date : today();
  let paused = 0, since = null;
  for (const e of c.events) {
    if (e.to === "AWAITING_MATERIAL") since = e.date;
    else if (since && e.from === "AWAITING_MATERIAL") { paused += daysBetween(since, e.date); since = null; }
  }
  if (since) paused += daysBetween(since, end);
  return Math.max(0, daysBetween(c.received, end) - paused);
}
const ageClass = d => d <= 2 ? "age-0" : d <= 7 ? "age-1" : d <= 15 ? "age-2" : "age-3";
const phoneOk = p => /^(\+91)?[6-9]\d{9}$/.test(p.replace(/[\s-]/g, "")) || /^0\d{9,10}$/.test(p.replace(/[\s-]/g, ""));

/* ============================== Seed: realistic history from the sample sheets ============================== */
(function seed() {
  const V = "Vizag Office", L = (code, qty, loc = V) => ({ code, loc, bucket: "FRESH", qty });
  ME = "Admin";
  post({ type: "OPENING", date: "25-05-2026", ref: "Sheet 25-5-2026", note: "Imported from Excel", lines: [
    L("LG78-150-700", 20), L("LG76-150-700FH", 42), L("LG76-200-700F", 57), L("LG75-150-215-70E", 18), L("LG83-072-103-0700", 41),
    L("LG30-018-054-0300", 29), L("LG26-048-0720", 4), L("LG66-036-036-900S", 12), L("LG66-040-078-480IT", 3),
    L("15WATT (190MA)", 25), L("EIO6006", 18), L("EIO9326", 33), L("EIO8437", 9), L("WPWG-5050-15SIP", 4),
    L("FTS-KC-60-57K", 250), L("LF40-192-060-57-HE", 3), L("LL20-111-XXX-65-NE3", 1), L("LF20-102-060-57-G3", 20), L("BULCK HEAD", 12)] });
  // Opening defectives become individual tagged pieces (as the importer will do).
  for (const [code, qty] of [["LG66-040-078-480IT", 20], ["18WATT DRIVERS", 12], ["15WATT (190MA)", 10], ["LG30-018-054-0300", 8],
    ["EIO9326", 6], ["WPWG-5050-15SIP", 5], ["LENS", 4], ["LG26-048-0720", 3], ["R1103-092-PA", 2], ["ISENSE DALI CONTROLLER (WCS-IS-DA4)", 2]])
    collectPieces({ code, qty, loc: V, date: "25-05-2026", source: "Opening stock (Excel 25-5-2026)", opening: true, by: "Admin" });
  ME = "Office";
  post({ type: "RECEIVED_FROM_WIPRO", date: "02-06-2026", ref: "Wipro DC 4471",
    lines: [{ ...L("EIO6006", 20), batch: "B2405", pkd: "04-2026" }, { ...L("LG26-048-0720", 10), batch: "B2311", pkd: "03-2026" }] });
  post({ type: "TRANSFER", date: "05-06-2026", note: "Buffer stock for TV Shop", lines: [L("LG76-200-700F", -10), L("LG76-200-700F", 10, "TV Shop")] });

  // A return batch already with Wipro, and an older one settled.
  const old = createBatch(pieces.filter(p => p.code === "LG66-040-078-480IT").slice(0, 6).map(p => p.tag), "12-06-2026").batch;
  sendBatch(old.no, "15-06-2026", "VZG/0615");
  receiveReplacement(old.tags.slice(0, 4), V, "20-07-2026", "5590");
  rejectPieces(old.tags.slice(4), "Physical damage, not covered");
  const open = createBatch(pieces.filter(p => p.code === "18WATT DRIVERS").slice(0, 8).map(p => p.tag), daysAgo(43)).batch;
  sendBatch(open.no, daysAgo(40), "VZG/0902");

  // Complaints from AP_Pending_Compliants_details.xlsx (phone numbers replaced with fake ones).
  const rows = [
    ["Punjab National Bank", "Gudivada", "", "9800000001", "15W drivers 18 NOS not working", 18, 30, "CLOSED", [], "Closed (sheet said 'not Attended')"],
    ["NSL Textiles", "Guntur", "Jadeesh", "980000002", "Material at office", 0, 21, "NOT_ATTENDED", [], "Phone in sheet had 9 digits"],
    ["Vaishaki Bio Marine", "Vizag", "R Apparao", "98000", "Fittings not working", 0, 25, "MATERIAL_TO_CHECK", [["Ramu", 19]], "Phone in sheet had 5 digits"],
    ["Sanvira Industries", "Vizag", "Srinuvas", "9800000004", "Drivers failing", 0, 12, "MATERIAL_TO_CHECK", [["Ramu", 9]], "Status cell said 'Saturday'"],
    ["Barc", "Vizag", "Chenna Keshavalu", "9800000005", "Linear fittings flickering", 0, 28, "MATERIAL_TO_CHECK", [["Ramu", 24], ["Apparao", 24]], ""],
    ["Laurus Labs Unit-2", "Vizag", "Murthy", "9800000006", "LED modules failed in production block", 6, 16, "MATERIAL_TO_CHECK", [["Ramu", 14]], ""],
    ["Laurus Labs Unit-4", "Vizag", "Bujji Babu", "9800000007", "Drivers not working", 0, 3, "NOT_ATTENDED", [], ""],
    ["Sri Kathyayani Filling Station", "Nellore", "", "9800000008", "Linear 7 not working", 7, 40, "CLOSED:Not a Wipro product", [], ""],
    ["GMR Air port", "Vizag", "Srinuvas", "9800000009", "Flood lights off on apron", 0, 9, "MATERIAL_TO_CHECK", [["Ramu", 7]], "Sheet had technician but no visit date"],
    ["Siri Filling Station", "Nellore", "Ganesh", "9800000010", "18 drivers not working, linear fittings", 18, 6, "NOT_ATTENDED", [], ""],
    ["Dr Reddys", "Vizag", "Chandra Mouli", "9800000011", "Bay lights failing", 0, 1, "NOT_ATTENDED", [], ""],
    ["Anna Olea", "Nellore", "Vishnu", "9800000012", "Material need to check", 0, 35, "CLOSED", [["Apparao", 30]], ""],
    ["IISER", "Tirupati", "", "", "Lab lights not working", 0, 18, "MATERIAL_TO_CHECK", [["Apparao", 15]], "No contact in sheet"],
    ["IIT", "Tirupati", "", "", "Corridor fittings failing", 0, 17, "AWAITING_MATERIAL", [["Apparao", 15]], "No contact in sheet"],
    ["Master Minds", "Guntur", "Sindhu", "9800000015", "Classroom panels", 0, 33, "CLOSED", [["Ramu", 31]], ""],
    ["Nacin", "Anantapur", "Mahesh", "9800000016", "Street lights", 0, 11, "ATTENDED", [["Apparao", 8]], ""],
    ["IOCL Office Holiday Home", "Tirupati", "Naidu", "9800000017", "Material at office", 0, 26, "CLOSED", [["Apparao", 22]], ""],
    ["VN Energies", "Vijayawada", "Rama Krishna", "9800000018", "Petrol pump canopy lights", 0, 38, "CLOSED", [], "Closed (sheet said 'not Attended')"],
  ];
  for (const [customer, city, contact, phone, fault, qty, ago, status, visits, legacy] of rows) {
    const c = fileComplaint({ wipro: "", customer, city, contact, phone, fault, qty, received: daysAgo(ago),
      priority: ago > 25 ? "High" : "Normal", techs: uniq(visits.map(v => v[0])), legacy });
    for (const [tech, vAgo] of visits) {
      const parts = customer === "Laurus Labs Unit-2" ? [{ code: "EIO6006", qty: 6 }] : [];
      const defects = customer === "Laurus Labs Unit-2" ? [{ code: "EIO6006", qty: 6, fault: "LEDs dead", batchCode: "B2201", pkd: "11-2025" }]
        : customer === "Barc" && tech === "Ramu" ? [{ code: "LG30-018-054-0300", qty: 4, fault: "No output" }] : [];
      addVisit(c, { date: daysAgo(vAgo), techs: [tech], work: "Inspected fittings; faulty parts noted", loc: V, parts, defects, next: null });
    }
    const [st, reason] = status.split(":");
    if (st === "CLOSED") setStatus(c, "CLOSED", { reason: reason || "Resolved", date: daysAgo(Math.max(0, ago - 5)) });
    else if (st !== c.status && st !== "NOT_ATTENDED") setStatus(c, st, { date: daysAgo(Math.max(0, ago - 3)) });
  }
})();
