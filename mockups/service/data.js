/* Service mockup data layer: demo data (demo-data.json), the append-only stock ledger and its rules.
   Mirrors what the real app's services will enforce. Everything lives in memory.
   The Defective store (DB.defStore) is a ledger location like any other, but it is NOT in DB.locations,
   so entry-form pickers, good-stock totals and low stock never see it. */

let DB = null;
const seq = { IN: 0, OUT: 0, TRF: 0, ADJ: 0, REV: 0 };
const ME = "Office";

const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
const norm = s => String(s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").trim();
// Look-alike key: O/0, I/1, hyphens and spaces, leading zeros. EI08437 == EIO8437, LG26-048-720 == LG26-048-0720.
const key = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
  .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
const fmt = iso => iso ? iso.split("-").reverse().join("-") : "";        // 2026-10-11 -> 11-10-2026
const fmtMonth = ym => ym ? ym.split("-").reverse().join("-") : "";      // 2026-04 -> 04-2026
const today = () => DB.today;
const addDays = (iso, n) => { const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const sum = (a, f) => a.reduce((t, x) => t + f(x), 0);
const uniq = a => [...new Set(a)];

const KIND = { IN: "Stock IN", OUT: "Stock OUT", TRF: "Transfer", ADJ: "Adjustment", REV: "Undo" };
const IN_FROM = { SUPPLIER: "From supplier", RETURN: "Returned unused from site", OPENING: "Opening stock",
  REPLACEMENT: "Replacement / repaired piece from company", DEFECTIVE_COLLECTED: "Failed parts collected at site",
  DEFECTIVE_RETURNED: "Rejected piece back from company" };
const OUT_TO = { SITE: "Site / customer", TECH: "Technician", OTHER: "Other" };   // choices on the Stock OUT form
const OUT_WHAT = { SITE: "To site / customer", TECH: "To technician", OTHER: "To other",
  COMPLAINT: "Parts given at complaint visit", RETURN_TO_COMPANY: "Defectives returned to company" };
// Entries the defectives screens own: Undo is blocked for them (use the Defectives screens instead).
const isDefectiveEntry = e => ["DEFECTIVE_COLLECTED", "RETURN_TO_COMPANY", "REPLACEMENT", "DEFECTIVE_RETURNED"].includes(e.subtype)
  || e.lines.some(l => l.loc === DB.defStore);
const ADJ_REASONS = ["Physical count", "Damaged", "Lost", "Found", "Other"];

async function loadData() {
  DB = await (await fetch("demo-data.json")).json();
  for (const e of DB.entries) seq[e.kind] = Math.max(seq[e.kind], Number(e.no.split("-")[1]));
  initService();
}

/* ---------- items ---------- */
const item = code => DB.items.find(i => i.code === code);
const unitOf = code => (item(code) || {}).unit || "NOS";
function findByCode(text) {   // exact, other spelling, or look-alike match
  const t = norm(text), k = key(text);
  if (!t) return null;
  return DB.items.find(i => i.code === t) || DB.items.find(i => i.aliases.includes(t))
    || DB.items.find(i => key(i.code) === k || i.aliases.some(a => key(a) === k)) || null;
}
function saveItem(data, originalCode) {
  const code = norm(data.code);
  if (!code) return "Item code is required.";
  const clash = findByCode(code);
  if (clash && clash.code !== originalCode) return `${code} already exists (or looks the same as ${clash.code}).`;
  for (const a of data.aliases) {
    const c = findByCode(a);
    if (c && c.code !== originalCode && c.code !== code) return `Other spelling ${a} belongs to ${c.code}.`;
  }
  if (!data.type) return "Choose the spare type.";
  if (!data.unit) return "Choose the unit.";
  const rec = { ...data, code, aliases: data.aliases.map(norm).filter(a => a && a !== code) };
  if (originalCode) {
    const old = item(originalCode);
    if (originalCode !== code && DB.entries.some(e => e.lines.some(l => l.code === originalCode)))
      return "This item already has stock entries, so its code can't be changed. Add the new spelling under 'Other spellings'.";
    Object.assign(old, rec);
  } else DB.items.push({ ...rec, active: true });
  return null;
}

/* ---------- ledger ---------- */
function balance(code, loc) {
  let q = 0;
  for (const e of DB.entries) for (const l of e.lines) if (l.code === code && l.loc === loc) q += l.qty;
  return q;
}
const total = code => sum(DB.locations, l => balance(code, l));          // good stock only (Defective store excluded)
const defQty = code => balance(code, DB.defStore);                       // shown separately, never part of the total
const isLow = i => i.reorder > 0 && total(i.code) <= i.reorder;
const entry = no => DB.entries.find(e => e.no === no);
const byDateDesc = list => list.slice().sort((a, b) => b.date.localeCompare(a.date) || DB.entries.indexOf(b) - DB.entries.indexOf(a));
const undoneBy = no => DB.entries.find(e => e.reverses === no);

// Append an entry if no location goes below zero. Returns an error message, or null (and sets e.no).
function post(e) {
  const delta = {};
  for (const l of e.lines) { const k = l.code + "|" + l.loc; delta[k] = (delta[k] || 0) + l.qty; }
  for (const k in delta) {
    const [code, loc] = k.split("|"), have = balance(code, loc);
    if (have + delta[k] < 0) return `Only ${have} ${unitOf(code)} of ${code} at ${loc}.`;
  }
  e.no = `${e.kind}-${String(++seq[e.kind]).padStart(4, "0")}`;
  e.by = e.by || (typeof ROLE === "string" ? ROLE : ME);
  DB.entries.push(e);
  return null;
}
function undo(no, reason) {
  const orig = entry(no);
  if (orig.kind === "REV") return "An undo can't be undone. Make a new entry instead.";
  if (undoneBy(no)) return "This entry was already undone.";
  if (isDefectiveEntry(orig)) return "This entry belongs to the defective pieces. Use the Defectives screens instead of Undo.";
  if (!reason.trim()) return "Please give a reason.";
  const err = post({ kind: "REV", date: today(), reverses: no, note: reason, lines: orig.lines.map(l => ({ ...l, qty: -l.qty })) });
  return err ? err + " The stock has already been used, so this entry can't be undone." : null;
}
// Short, clear labels for Movements / entry detail. Service entries name the complaint or return batch they belong to.
const SVC_WHAT = { COMPLAINT: e => `Parts for complaint ${e.complaint}`, DEFECTIVE_COLLECTED: e => `Defective collected (${e.complaint})`,
  RETURN_TO_COMPANY: e => `Returned to company (${e.batch})`, REPLACEMENT: e => `Replacement from company (${e.batch})`,
  DEFECTIVE_RETURNED: e => `Rejected, back from company (${e.batch})` };
const entryWhat = e => SVC_WHAT[e.subtype] ? SVC_WHAT[e.subtype](e) : e.kind === "IN" ? IN_FROM[e.subtype] : e.kind === "OUT" ? OUT_WHAT[e.subtype]
  : e.kind === "TRF" ? (e.party === DB.defStore ? "Marked defective" : "Between locations")
  : e.kind === "ADJ" ? (e.lines.every(l => l.loc === DB.defStore) ? "Defective pieces scrapped" : e.reason) : `Undo of ${e.reverses}`;
// Link from a ledger entry back to the complaint or return batch it belongs to.
const entrySource = e => e.complaint ? `<a class="code" href="#complaint/${e.complaint}">${e.complaint}</a>`
  : e.batch ? `<a class="code" href="#batch/${e.batch}">${e.batch}</a>` : "";
const entryLocs = e => uniq(e.lines.map(l => l.loc)).join(" → ");
const entryQty = e => e.kind === "TRF" ? sum(e.lines.filter(l => l.qty > 0), l => l.qty) : sum(e.lines, l => Math.abs(l.qty));
