/* Smart features (design: docs/superpowers/specs/2026-10-19-smart-features-design.md). Rule: suggest, never act.
   Tier 1 rules: Today list + digest, due dates, duplicate warnings, typo guard (ui.js), fault reader, smart defaults,
   sanity checks (forms.js). Tier 2 learning: reorder suggestions, slow stock, insights, parts usually needed, technician
   hint, legacy import. Tier 3 optional AI: paste a message, label / DC photos, drafts inbox, usage cap.
   Everything here is in memory, like the rest of the mockup. Weeks before the demo ledger starts are made up (seeded),
   so the learning features have something to show; the real app uses real history only. */

const SMART = {
  due: { Urgent: 1, High: 2, Normal: 4 }, unattended: 2, storeWait: 30,
  holidays: [{ date: "2026-10-02", name: "Gandhi Jayanti" }, { date: "2026-10-20", name: "Diwali" }],
  companyCfg: { "Wipro Lighting": { answer: 21, lead: 7 }, Havells: { answer: 30, lead: 10 } },
  digest: { on: true, to: "office@svkml.in, owner@svkml.in", time: "09:00" },
  ai: { on: true, cap: 500, used: 86.4, log: [
    { at: "2026-10-12 08:14", what: "Message → complaint draft (WhatsApp)", tokens: 1840, inr: 0.32 },
    { at: "2026-10-11 16:02", what: "Message → complaint draft (email)", tokens: 2210, inr: 0.38 },
    { at: "2026-10-10 11:47", what: "DC photo → Stock IN draft", tokens: 3950, inr: 0.71 },
    { at: "2026-10-09 10:05", what: "Label photo → item code", tokens: 2630, inr: 0.48 }] },
  needs: [], dismissed: new Set(), events: [], lastLoc: null, drafts: [],
};
const companyCfg = name => SMART.companyCfg[name] || (SMART.companyCfg[name] = { answer: 30, lead: 7 });
const logSuggestion = (kind, id, action) => SMART.events.push({ kind, id, action, by: ROLE, at: today() });
const aiOff = () => !SMART.ai.on || SMART.ai.used >= SMART.ai.cap;
function aiSpend(what, inr, tokens) {
  SMART.ai.used = Math.round((SMART.ai.used + inr) * 100) / 100;
  SMART.ai.log.unshift({ at: `${today()} ${new Date().toTimeString().slice(0, 5)}`, what, tokens, inr });
}

/* ---------- shared bits ---------- */
const suggestBox = (body, actions = "", id = "") => `<div class="suggest" ${id ? `id="${id}"` : ""}><span class="suggest-ic">${icon("bulb")}</span>
  <div class="flex-fill min-w-0">${body}</div>${actions ? `<div class="suggest-act">${actions}</div>` : ""}</div>`;
const learningBox = (what, have, need) => `<div class="learning">${icon("school")}<div><b>Learning:</b> ${what}
  <div class="progress progress-sm mt-1" style="max-width:16rem"><div class="progress-bar bar-brand" style="width:${Math.min(100, have / need * 100)}%"></div></div>
  <div class="small text-secondary mt-1">${have} of ${need} ${need === 12 ? "weeks" : "needed"} so far. Until then the app shows nothing rather than a guess.</div></div></div>`;
const aiTag = (word = "From message") => `<span class="badge st st-neutral ai-tag">${icon("sparkles")}${word}</span>`;
const mockDownload = name => `<button type="button" class="btn btn-outline-secondary" onclick="toast('Mockup: would download <b>${name}</b>.')">${icon("file-spreadsheet")} Export to Excel</button>`;
const adminOnly = () => `<span class="badge bg-secondary-lt align-self-center">${icon("lock")} Admin only in the real app</span>`;
const hash32 = s => { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return h >>> 0; };
const seeded = (s, i) => (hash32(s + ":" + i) % 1000) / 1000;

/* ---------- working days and due dates (1.3) ---------- */
// Step in UTC: the shared addDays() goes through local time, which can return the same date in IST (UTC+5:30).
const nextDay = iso => { const d = new Date(iso + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + 1); return d.toISOString().slice(0, 10); };
const isHoliday = d => new Date(d + "T00:00:00Z").getUTCDay() === 0 || SMART.holidays.some(h => h.date === d);
function workdays(a, b) { let n = 0; for (let d = nextDay(a); d <= b; d = nextDay(d)) if (!isHoliday(d)) n++; return n; }
function pausedWorkdays(c) {   // working days spent in Awaiting material (the paused clock)
  let n = 0, since = null;
  for (const e of cEvents(c.no)) {
    if (since && e.to !== "AWAITING_MATERIAL") { n += workdays(since, e.at); since = null; }
    if (e.to === "AWAITING_MATERIAL" && !since) since = e.at;
  }
  if (since) n += workdays(since, c.closedOn || today());
  return n;
}
function dueInfo(c) {
  if (!isOpen(c)) return { state: "done" };
  const used = workdays(c.reportedOn, today()) - pausedWorkdays(c), allowed = SMART.due[c.priority];
  if (c.status === "AWAITING_MATERIAL") return { state: "paused", used, allowed };
  return { state: used > allowed ? "over" : used === allowed ? "today" : "ok", used, allowed, over: used - allowed };
}
const dueSort = c => { const d = dueInfo(c); return d.state === "done" ? -1000 : d.state === "paused" ? -500 : d.over; };
function dueChip(c, long = false) {
  const d = dueInfo(c);
  if (d.state === "done") return long ? "" : `<span class="text-secondary">—</span>`;
  const tip = `title="${d.used} of ${d.allowed} working days used (${c.priority}). Awaiting material does not count."`;
  if (d.state === "paused") return `<span class="badge st st-wait" ${tip}>${icon("player-pause")}Paused</span>`;
  if (d.state === "over") return `<span class="badge st st-alert" ${tip}>${icon("alarm")}Overdue ${d.over} d</span>`;
  if (d.state === "today") return `<span class="badge st st-wait" ${tip}>${icon("clock")}Due today</span>`;
  return `<span class="badge st st-ok" ${tip}>${icon("check")}${d.allowed - d.used} d left</span>`;
}

/* ---------- fault-text reader (1.6): offline rules, no AI ---------- */
const SPARE_WORDS = { Driver: ["driver", "drivers", "drv"], "PCB / LED module": ["pcb", "board", "led module", "module", "led plate"],
  Lens: ["lens", "lenses", "diffuser"], "Complete fitting": ["fitting", "fittings", "fixture", "light", "lights"], Controller: ["controller"],
  Switch: ["switch"], "Wire / cable": ["wire", "cable"] };
function readFault(text) {
  const t = ` ${String(text || "").toLowerCase()} `;
  const w = t.match(/(\d{1,4})\s*-?\s*(w|watt|watts)\b/), q = t.match(/(\d{1,4})\s*(nos|no's|no\.|pcs|pieces|numbers)\b/) || t.match(/in (\d{1,4}) (fittings|lights)/);
  let type = null;
  for (const [ty, words] of Object.entries(SPARE_WORDS)) if (DB.spareTypes.includes(ty) && words.some(x => new RegExp(`[^a-z]${x}[^a-z]`).test(t))) { type = ty; if (ty !== "Complete fitting") break; }
  const watt = w ? Number(w[1]) : null, qty = q ? Number(q[1]) : null;
  const items = type ? DB.items.filter(i => i.active && i.type === type && (!watt || i.watt === watt)).slice(0, 4) : [];
  return { type, watt, qty, items };
}

/* ---------- similarity for duplicate checks (pg_trgm in the real app) ---------- */
const digits = s => String(s || "").replace(/\D/g, "").replace(/^0+/, "");
function similarSites(d, exceptId) {
  const ph = digits(d.phone), out = [];
  for (const s of DB.sites) {
    if (s.id === exceptId) continue;
    if (ph.length >= 6 && digits(s.phone) === ph) out.push({ s, why: "same phone" });
    else if (d.name && similarity(d.name, s.name) >= 0.6 && (!d.city || s.city.toLowerCase() === d.city.trim().toLowerCase()))
      out.push({ s, why: "similar name, same city" });
  }
  return out.slice(0, 2);
}

/* ---------- demo data for the smart features ---------- */
function initSmart() {
  // Parts needed: open complaints waiting for material each need a part that is short in stock.
  const lowItems = DB.items.filter(i => i.active && isLow(i));
  DB.complaints.filter(c => c.status === "AWAITING_MATERIAL").forEach((c, n) => {
    const it = lowItems[n % Math.max(1, lowItems.length)];   // demo: waiting for a part we are short of
    if (it) SMART.needs.push({ complaint: c.no, code: it.code, qty: Math.max(2, total(it.code) + 2) });
  });
  const mc = DB.complaints.find(c => c.status === "MATERIAL_CHECK");
  if (mc && DB.items[3]) SMART.needs.push({ complaint: mc.no, code: DB.items[3].code, qty: 1 });
  SMART.drafts = [
    { id: "D-0003", source: "WhatsApp", from: "98668 32284", at: `${today()} 08:12`, status: "New",
      text: "Sir PNB Gudivada branch lo 15watt drivers 6nos not working, pls send technician urgent. Manager - 9866832284" },
    { id: "D-0002", source: "Email", from: "service.ap@havells-partner.example", at: `${addDays(today(), -1)} 16:02`, status: "New",
      text: "Complaint HVL/AP/5512: Sri Venkateswara Hospital, Vijayawada. 4 nos 40W panel lights flickering in OPD. Contact Dr Rao 9849012345. Havells product." },
    { id: "D-0001", source: "Pasted", from: "Office", at: `${addDays(today(), -2)} 11:30`, status: "Ignored",
      text: "Good morning sir, payment for last month's invoice is pending, please check." },
  ];
}

/* ---------- AI message reading (3.1). The mockup fakes the model with rules; the real app calls a small model. ---------- */
function extractMessage(text) {
  const t = String(text || ""), lo = t.toLowerCase();
  const phone = (t.match(/(?:\+?91[\s-]?)?([6-9]\d{4}\s?\d{5})/) || [])[1]?.replace(/\s/g, "") || "";
  const bySite = phone && DB.sites.find(s => digits(s.phone) === phone);
  const byName = DB.sites.find(s => lo.includes(s.name.toLowerCase()) || (s.name.match(/\b[A-Z]/g) || []).join("").length > 2
    && new RegExp(`\\b${(s.name.match(/\b[A-Z]/g) || []).join("")}\\b`, "i").test(t) && lo.includes(s.city.toLowerCase()));
  const s = bySite || byName || null;
  const city = s ? s.city : (cities().find(c => lo.includes(c.toLowerCase())) || (/vijayawada/i.test(t) ? "Vijayawada" : ""));
  const newSite = s ? "" : ((t.match(/:\s*([A-Z][A-Za-z .]+?),\s*[A-Z][a-z]+/) || [])[1] || "").trim();
  const company = DB.companies.find(co => lo.includes(co.split(" ")[0].toLowerCase())) || "";
  const ref = (t.match(/\b([A-Z]{2,5}\/[A-Z]{2}\/\d{3,6})\b/) || [])[1] || "";
  const contact = (t.match(/(?:contact|manager)\s*[-:]?\s*((?:dr\.?|mr\.?|mrs\.?)?\s*[A-Za-z]+(?: [A-Z][a-z]+)?)/i) || [])[1] || "";
  const f = readFault(t);
  let fault = t.replace(/^(sir|good morning sir)[ ,]*/i, "").replace(/complaint [^:]+:\s*/i, "").split(/contact|manager/i)[0].replace(/[.\s]+$/, "");
  if (newSite) fault = fault.replace(new RegExp(`^${newSite}[, ]*${city}[.,]?\\s*`, "i"), "");
  return { site: s, newSite, city, phone, company, ref, contact: contact.trim(), qty: f.qty, fault, urgent: /urgent/i.test(t),
    isComplaint: /not working|flicker|fail|dead|repair|technician|fault|complaint/i.test(t) };
}
function fillComplaintFrom(x) {
  const mark = id => { const el = field(id); if (!el) return; (el.tomselect ? el.tomselect.wrapper : el).classList.add("ai-filled"); };
  if (x.site) { cSite.setValue(x.site.id); mark("c-site"); mark("c-contact"); mark("c-phone"); }
  else if (x.newSite) field("c-ai-site").innerHTML = suggestBox(`The message mentions a site that isn't saved yet: <b>${esc(x.newSite)}</b>${x.city ? `, ${esc(x.city)}` : ""}.`,
    `<button type="button" class="btn btn-sm btn-primary" onclick="addSiteFromMessage()">${icon("plus")} Add this site</button>`);
  window._aiSite = x;
  if (x.company) { cCompany.addOption({ value: x.company, text: x.company }); cCompany.setValue(x.company); mark("c-company"); }
  if (x.ref) { field("c-ref").value = x.ref; mark("c-ref"); }
  if (x.qty) { field("c-qty").value = x.qty; mark("c-qty"); }
  if (x.fault) { field("c-fault").value = x.fault; mark("c-fault"); faultChanged(); }
  if (x.urgent) { const r = document.querySelector('input[name=prio][value="Urgent"]'); if (r) r.checked = true; }
  if (!x.site && x.phone) { field("c-phone").value = x.phone; mark("c-phone"); }
  if (!x.site && x.contact) { field("c-contact").value = x.contact; mark("c-contact"); }
  field("c-ai-note").innerHTML = `<div class="alert alert-info mt-3 mb-0">${icon("sparkles")} Fields marked ${aiTag()} were filled from the message. <b>Check each one</b> before saving; nothing is saved until you press Save.</div>`;
}
function addSiteFromMessage() {
  const x = window._aiSite;
  openSiteModal(x.newSite, s => { if (s) { cSite.addOption(siteOpt(s)); cSite.setValue(s.id); field("c-ai-site").innerHTML = ""; } });
  setTimeout(() => { field("ns-city").value = x.city; field("ns-contact").value = x.contact; field("ns-phone").value = x.phone; }, 50);
}
const SAMPLE_MSG = "Sir PNB Gudivada branch lo 15watt drivers 6nos not working, pls send technician urgent. Manager - 9866832284";
function readPasted() {
  const text = field("c-paste").value.trim();
  if (!text) { field("c-ai-note").innerHTML = `<div class="text-danger mt-2">Paste a message first.</div>`; return; }
  if (aiOff()) { field("c-ai-note").innerHTML = `<div class="alert alert-warning mt-3 mb-0">${icon("lock")} The AI assistant is off or this month's limit is used up. Fill the form by hand.</div>`; return; }
  const x = extractMessage(text);
  aiSpend("Message → complaint (pasted)", 0.3, 1700);
  if (!x.isComplaint) { field("c-ai-note").innerHTML = `<div class="alert alert-warning mt-3 mb-0">${icon("help")} This doesn't look like a complaint, so nothing was filled.</div>`; return; }
  fillComplaintFrom(x);
}

/* ---------- New complaint: paste box, fault reader, duplicate complaint, technician hint ---------- */
const _complaintNew = ROUTES["complaint-new"];
ROUTES["complaint-new"] = arg => {
  const draft = arg && arg.startsWith("draft-") ? SMART.drafts.find(d => d.id === arg.slice(6)) : null;
  _complaintNew(draft ? undefined : arg);
  const form = field("c-form");
  form.insertAdjacentHTML("afterbegin", `<div class="card mb-3 ai-card"><div class="card-header"><h3 class="card-title">${icon("sparkles")} Paste a message</h3>
      <span class="badge bg-secondary-lt ms-2 d-none d-md-inline-block">Optional AI · ₹0.3 per message</span>
      <div class="card-actions"><a class="btn btn-sm btn-link" data-bs-toggle="collapse" href="#c-paste-body" role="button">${icon("chevron-down")} Show</a></div></div>
    <div class="collapse ${draft ? "show" : ""}" id="c-paste-body"><div class="card-body">
      ${aiOff() ? `<div class="alert alert-secondary mb-0">${icon("lock")} The AI assistant is off (Smart settings). Fill the form below by hand.</div>` : `
      <label class="form-label" for="c-paste">WhatsApp message, email or SMS</label>
      <textarea id="c-paste" class="form-control" rows="3" placeholder="Paste the customer's or company's message here">${draft ? esc(draft.text) : ""}</textarea>
      <div class="d-flex flex-wrap gap-2 mt-2"><button type="button" class="btn btn-primary" onclick="readPasted()">${icon("wand")} Fill the form from this message</button>
        <button type="button" class="btn btn-quiet" onclick="field('c-paste').value=SAMPLE_MSG">${icon("brand-whatsapp")} Try a sample WhatsApp</button></div>
      <div class="form-hint mt-2">The text is sent to the AI service. Every filled field is marked and you check it before saving.</div>`}
      <div id="c-ai-note"></div></div></div></div>`);
  field("c-site").closest(".row").insertAdjacentHTML("beforeend", `<div class="col-12" id="c-ai-site"></div><div class="col-12" id="c-dup"></div>`);
  field("c-fault").insertAdjacentHTML("afterend", `<div id="c-fault-read" class="mt-2"></div>`);
  field("c-fault").addEventListener("input", faultChanged);
  cSite.on("change", () => { complaintDupCheck(); cTechs.clearCache(); });
  if (draft) { window._fromDraft = draft.id; fillComplaintFrom(extractMessage(draft.text)); } else window._fromDraft = null;
};
function faultChanged() {
  const r = readFault(field("c-fault").value), host = field("c-fault-read");
  if (!r.type && !r.watt && !r.qty) { host.innerHTML = ""; return; }
  if (r.qty && !field("c-qty").value) { field("c-qty").value = r.qty; }
  host.innerHTML = `<div class="fault-read"><span class="text-secondary small me-1">${icon("bulb")} Read from the fault:</span>
    ${r.type ? `<span class="chip">${icon("category")}${esc(r.type)}</span>` : ""}${r.watt ? `<span class="chip">${icon("bolt")}${r.watt} W</span>` : ""}
    ${r.qty ? `<span class="chip">${icon("hash")}qty ${r.qty}</span>` : ""}
    ${r.items.length ? `<div class="w-100 mt-2 small"><b>Parts this may need</b> (tick to save them as "parts needed"):
      ${r.items.map(i => `<label class="form-check mb-0 mt-1"><input type="checkbox" class="form-check-input need-pick" value="${esc(i.code)}">
        <span class="form-check-label"><span class="code">${esc(i.code)}</span> <span class="text-secondary">${esc(i.desc)} · ${total(i.code)} ${i.unit} in stock</span></span></label>`).join("")}</div>` : ""}</div>`;
}
function complaintDupCheck() {
  const host = field("c-dup"), id = Number(cSite.getValue());
  const open = DB.complaints.filter(c => c.site === id && isOpen(c) && c.reportedOn >= addDays(today(), -30));
  host.innerHTML = open.length ? suggestBox(`This site already has an open complaint: ${open.map(c => `${cLink(c.no)} (${ageDays(c)} days old, ${CSTATUS[c.status]}, ${esc(c.fault)})`).join("; ")}.
      If it's the same problem, record a visit there instead of filing a new one.`,
      `<a class="btn btn-sm btn-primary" href="#visit/${open[0].no}">${icon("clipboard-plus")} Record visit on ${open[0].no}</a>
       <button type="button" class="btn btn-sm btn-link" onclick="logSuggestion('dup_complaint',${id},'dismissed');field('c-dup').innerHTML=''">It's a new problem</button>`) : "";
}
function techOption(d) {   // 2.5 technician hint, shown inside the Technicians dropdown
  const id = cSite ? Number(cSite.getValue()) : 0, s = site(id);
  const openN = DB.complaints.filter(c => isOpen(c) && c.techs.includes(d.value)).length;
  const here = id && DB.visits.some(v => v.techs.includes(d.value) && (complaint(v.complaint) || {}).site === id);
  const city = s && DB.visits.some(v => v.techs.includes(d.value) && siteCity(complaint(v.complaint) || {}) === s.city);
  return `<div><span class="fw-medium">${esc(d.text)}</span><span class="opt-meta">${openN} open complaint${openN === 1 ? "" : "s"}${here ? " · visited this site before" : city ? ` · has worked in ${esc(s.city)}` : ""}</span></div>`;
}
function smartAfterComplaint(c) {
  document.querySelectorAll(".need-pick:checked").forEach(b => { SMART.needs.push({ complaint: c.no, code: b.value, qty: c.qty || 1 }); logSuggestion("fault_parts", c.no, "accepted"); });
  if (window._fromDraft) { const d = SMART.drafts.find(x => x.id === window._fromDraft); d.status = "Filed"; d.complaint = c.no; window._fromDraft = null; }
}

/* ---------- New site modal: duplicate site (1.4) ---------- */
function siteDupCheck() {
  const host = field("ns-dup"); if (!host) return;
  const hits = similarSites({ name: field("ns-name").value, city: field("ns-city").value, phone: field("ns-phone").value });
  host.innerHTML = hits.length ? suggestBox(`Looks like a site you already have: ${hits.map(h => `<b>${esc(h.s.name)}</b>, ${esc(h.s.city)} <span class="text-secondary">(${h.why})</span>`).join("; ")}.`,
    `<button type="button" class="btn btn-sm btn-primary" onclick="useExistingSite(${hits[0].s.id})">${icon("check")} Use ${esc(hits[0].s.name)}</button>`) : "";
}
function useExistingSite(id) { logSuggestion("dup_site", id, "accepted"); closeModal(); const done = window._siteDone; window._siteDone = () => {}; done(site(id)); }

/* ---------- Complaint page: due chip + parts needed (ComplaintNeed) ---------- */
const _complaint = ROUTES.complaint;
ROUTES.complaint = no => {
  _complaint(no);
  const c = complaint(no); if (!c) return;
  const chips = view().querySelector(".d-flex.flex-wrap.gap-2");
  if (chips && isOpen(c)) chips.insertAdjacentHTML("afterbegin", dueChip(c, true));
  view().querySelector(".col-lg-8").insertAdjacentHTML("beforeend", needsCard(c));
  const sel = field("need-item");
  if (sel) makeItemPicker(sel, { allowCreate: false, onPick: () => {} });
};
function needsCard(c) {
  const rows = SMART.needs.filter(n => n.complaint === c.no);
  return `<div class="card"><div class="card-header"><h3 class="card-title">${icon("list-check")} Parts needed</h3><span class="badge bg-secondary-lt ms-2">${rows.length}</span>
      <div class="card-subtitle ms-2 text-secondary">What this job needs. Short parts show on the Today list.</div></div>
    ${rows.length ? `<div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Item</th><th class="num">Needed</th><th class="num">Good stock</th><th>Status</th><th></th></tr></thead><tbody>
      ${rows.map((n, i) => { const have = total(n.code), short = have < n.qty;
        return `<tr><td>${itemCell(n.code)}</td><td class="num">${n.qty}</td><td class="num">${have}</td>
          <td>${short ? `<span class="badge st st-alert">${icon("alert-triangle")}Short by ${n.qty - have}</span>` : `<span class="badge st st-ok">${icon("check")}In stock</span>`}</td>
          <td class="text-end">${isOpen(c) ? `<button class="btn btn-sm btn-ghost-danger" title="Remove" aria-label="Remove" onclick="removeNeed('${c.no}',${i})">${icon("x")}</button>` : ""}</td></tr>`; }).join("")}
      </tbody></table></div>` : `<div class="card-body text-secondary py-3">No parts listed yet.</div>`}
    ${isOpen(c) ? `<div class="card-footer"><div class="row g-2 align-items-end">
      ${fcol(7, `<label class="form-label small" for="need-item">Item</label><select id="need-item"></select>`)}
      <div class="col-6 col-md-2"><label class="form-label small" for="need-qty">Qty</label><input id="need-qty" type="number" min="1" step="1" inputmode="numeric" class="form-control" value="1"></div>
      <div class="col-6 col-md-3"><button type="button" class="btn btn-quiet w-100" onclick="addNeed('${c.no}')">${icon("plus")} Add part needed</button></div></div></div>` : ""}</div>`;
}
function addNeed(no) {
  const code = field("need-item").value, qty = Number(field("need-qty").value);
  if (!code || !(qty >= 1)) { toast("Choose an item and a quantity of 1 or more.", "danger"); return; }
  SMART.needs.push({ complaint: no, code, qty }); toastAfterNav(`Part needed added: <b>${esc(code)}</b> × ${qty}.`); route();
}
function removeNeed(no, i) { const rows = SMART.needs.filter(n => n.complaint === no); SMART.needs.splice(SMART.needs.indexOf(rows[i]), 1); route(); }

/* ---------- Record visit: parts needed + parts usually needed (2.4) ---------- */
const _visit = ROUTES.visit;
ROUTES.visit = no => {
  _visit(no);
  const c = complaint(no); if (!c || !isOpen(c)) return;
  const loc = () => field("v-loc").value;
  const needs = SMART.needs.filter(n => n.complaint === no);
  const r = readFault(c.fault);
  const usual = {};
  for (const o of DB.complaints) {
    if (o.no === no || o.company !== c.company) continue;
    const ro = readFault(o.fault); if (!r.type || ro.type !== r.type || ro.watt !== r.watt) continue;
    for (const v of DB.visits.filter(v => v.complaint === o.no && v.outEntry)) for (const l of entry(v.outEntry).lines) usual[l.code] = (usual[l.code] || 0) + 1;
  }
  const top = Object.entries(usual).sort((a, b) => b[1] - a[1]).slice(0, 3);
  const btn = (code, qty) => `<button type="button" class="btn btn-sm btn-quiet" onclick="addPart('${esc(code)}',${qty})">${icon("plus")} Add</button>`;
  let html = "";
  if (needs.length) html += suggestBox(`<b>Parts needed for this complaint:</b><div class="mt-1">${needs.map(n => `<div class="d-flex align-items-center gap-2 py-1">
      <span class="code">${esc(n.code)}</span> × ${n.qty} <span class="text-secondary small">(${balance(n.code, loc())} at ${esc(loc())})</span>${btn(n.code, n.qty)}</div>`).join("")}</div>`);
  if (top.length) html += suggestBox(`<b>Usually needed</b> for ${esc(r.type)}${r.watt ? ` ${r.watt} W` : ""} faults on ${esc(c.company)} products:<div class="mt-1">${top.map(([code, n]) => `<div class="d-flex align-items-center gap-2 py-1">
      <span class="code">${esc(code)}</span> <span class="text-secondary small">used on ${n} earlier visit${n > 1 ? "s" : ""}</span>${btn(code, 1)}</div>`).join("")}</div>`);
  else if (r.type) html += learningBox(`"usually needed" parts for ${esc(r.type)} faults appear after a few visits with parts given.`, 2, 5);
  if (html) field("v-parts").insertAdjacentHTML("beforebegin", `<div class="mb-3 d-grid gap-2">${html}</div>`);
};
function addPart(code, qty) {
  let r = visitParts.rows.find(x => !x.code);
  if (!r) { visitParts.add(code); r = visitParts.rows.at(-1); } else r.ts.setValue(code);
  r.el.querySelector(".qty").value = qty; visitParts.refresh(r); logSuggestion("visit_part", code, "accepted");
}

/* ---------- Entry forms: remembered location (1.7), DC photo (3.2) ---------- */
for (const k of ["in", "out", "transfer", "adjust"]) {
  const orig = ROUTES[k];
  ROUTES[k] = a => {
    orig(a);
    const sel = field("f-loc");
    if (SMART.lastLoc && sel && [...sel.options].some(o => o.value === SMART.lastLoc) && sel.value !== SMART.lastLoc) {
      sel.value = SMART.lastLoc; sel.dispatchEvent(new Event("change"));
      sel.insertAdjacentHTML("afterend", `<small class="form-hint">${icon("history")} Remembered from your last entry</small>`);
    }
    if (k === "in") view().querySelector("#lines").closest(".card").querySelector(".card-header").insertAdjacentHTML("beforeend",
      `<div class="card-actions"><button type="button" class="btn btn-sm btn-quiet" onclick="askDcPhoto()">${icon("camera")} Read delivery challan photo</button></div>`);
  };
}
function smartEntrySaved(e, loc) { if (loc) SMART.lastLoc = loc; }

/* ---------- Entry sanity checks (1.8): warn, never block ---------- */
function sanityWarnings(e) {
  const out = [];
  if (daysBetween(e.date, today()) > 30) out.push(`The date is ${daysBetween(e.date, today())} days back (${fmt(e.date)}). Is that right?`);
  for (const l of e.lines) {
    if (e.kind === "TRF" && l.qty < 0) continue;
    const past = DB.entries.flatMap(x => x.lines.filter(y => y.code === l.code && x.kind !== "REV").map(y => Math.abs(y.qty))).sort((a, b) => a - b);
    if (past.length < 5) continue;
    const med = past[Math.floor(past.length / 2)], q = Math.abs(l.qty);
    if (e.kind !== "ADJ" && med > 0 && q >= 5 * med) out.push(`${q} ${unitOf(l.code)} of <span class="code">${esc(l.code)}</span> is ${Math.round(q / med)}× the usual quantity (${med}).`);
    if (e.kind === "ADJ" && l.qty < 0) { const have = balance(l.code, l.loc); if (-l.qty > have / 2) out.push(`This removes ${-l.qty} of the ${have} ${unitOf(l.code)} of <span class="code">${esc(l.code)}</span> at ${esc(l.loc)}, more than half.`); }
  }
  return out;
}
function askSanity(warns, mode) {
  openModal(`<div class="modal-header"><h5 class="modal-title">${icon("alert-triangle")} Please check before saving</h5><button type="button" class="btn-close" aria-label="Close" onclick="closeModal()"></button></div>
    <div class="modal-body"><ul class="mb-0">${warns.map(w => `<li class="mb-1">${w}</li>`).join("")}</ul><div class="form-hint mt-3">This is only a check. If it's right, save it.</div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Go back and check</button>
      <button type="button" class="btn btn-primary ms-auto" id="sanity-save" onclick="window._sanityOk=true;closeModal();logSuggestion('sanity','${mode}','overridden');saveEntry('${mode}')">${icon("device-floppy")} It's right, save</button></div>`);
}
function photoModal(title, what, run) {
  window._photoRun = run;
  openModal(`<div class="modal-header"><h5 class="modal-title">${icon("camera")} ${title}</h5><button type="button" class="btn-close" aria-label="Close" onclick="closeModal()"></button></div>
    <div class="modal-body">${aiOff() ? `<div class="alert alert-secondary mb-0">${icon("lock")} The AI assistant is off (Smart settings).</div>` : `
      <label class="form-label" for="ph-file">Photo</label><input id="ph-file" type="file" accept="image/*" capture="environment" class="form-control">
      <div class="form-hint mt-2">${what} If the photo is blurry, unreadable fields are left empty, never guessed. Optional AI · about ₹0.5 per photo.</div>`}</div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
      ${aiOff() ? "" : `<button type="button" class="btn btn-quiet" onclick="closeModal();window._photoRun()">${icon("photo")} Use the sample photo</button>
      <button type="button" class="btn btn-primary" onclick="if(!field('ph-file').value){toast('Choose a photo, or use the sample.','danger');return}closeModal();window._photoRun()">${icon("wand")} Read photo</button>`}</div>`);
}
function askDcPhoto() {
  photoModal("Read delivery challan", "The supplier, DC number and item lines are filled in as a draft. Check each line against the paper.", () => {
    aiSpend("DC photo → Stock IN draft", 0.7, 3950);
    const sup = field("f-supplier"); if (sup.tomselect) sup.tomselect.setValue(DB.config.defaultCompany); else sup.value = DB.config.defaultCompany;
    field("f-ref").value = "DC 7781"; field("f-ref").classList.add("ai-filled");
    const pick = DB.items.filter(i => i.active && i.company === DB.config.defaultCompany).slice(0, 3);
    pick.forEach((it, n) => { let r = lines.rows.find(x => !x.code); if (!r) { lines.add(it.code); r = lines.rows.at(-1); } else r.ts.setValue(it.code);
      r.el.querySelector(".qty").value = [10, 6, 4][n]; r.el.classList.add("ai-line"); lines.refresh(r); });
    field("form-error").innerHTML = `<div class="alert alert-info">${icon("sparkles")} 3 lines and the DC number were read from the photo. <b>Check each line against the challan</b> before saving.</div>`;
  });
}

/* ---------- Item form: read the code from a label photo (3.2) ---------- */
const _itemNew = ROUTES["item-new"];
ROUTES["item-new"] = () => {
  _itemNew();
  field("it-code").closest("div").insertAdjacentHTML("beforeend", `<button type="button" class="btn btn-sm btn-quiet mt-2" onclick="askLabelPhoto()">${icon("camera")} Read from label photo</button>`);
};
function askLabelPhoto() {
  photoModal("Read fitting / driver label", "The item code, wattage and current are read from the label.", () => {
    aiSpend("Label photo → item code", 0.5, 2630);
    field("it-code").value = "LG84-040-350"; checkCodeHint("it", "LG84-040-350", "");
    for (const [id, v] of [["code", null], ["watt", 40], ["ma", 350]]) { const el = field(`it-${id}`); if (v !== null) el.value = v; el.classList.add("ai-filled"); }
    const ty = field("it-type"); if (ty.tomselect) ty.tomselect.setValue("Driver");
    toast(`Read from the photo: <b>LG84-040-350</b>, 40 W, 350 mA. Check before saving.`);
  });
}

/* ---------- Today list (1.1) ---------- */
function todaySections() {
  const keep = (kind, id, state) => !SMART.dismissed.has(`${kind}|${id}|${state}`);
  const dis = (kind, id, state) => `<button type="button" class="btn btn-sm btn-ghost-secondary" title="Hide until this changes" aria-label="Hide until this changes"
    onclick="dismissToday('${kind}','${id}','${esc(state)}')">${icon("eye-off")}</button>`;
  const open = DB.complaints.filter(isOpen);
  const over = open.filter(c => c.status !== "NOT_ATTENDED" && dueInfo(c).state === "over" && keep("over", c.no, c.status + c.priority))
    .sort((a, b) => dueSort(b) - dueSort(a));
  const unatt = open.filter(c => c.status === "NOT_ATTENDED" && workdays(c.reportedOn, today()) > SMART.unattended && keep("unatt", c.no, c.status));
  const shortNeeds = SMART.needs.filter(n => isOpen(complaint(n.complaint)) && total(n.code) < n.qty && keep("short", n.complaint + n.code, String(total(n.code))));
  const storeByCo = {};
  for (const p of DB.pieces.filter(p => p.status === "IN_STORE" && daysBetween(p.collectedOn, today()) > SMART.storeWait)) (storeByCo[p.company] ||= []).push(p);
  const store = Object.entries(storeByCo).filter(([co, ps]) => keep("store", co, String(ps.length)));
  const late = DB.batches.filter(b => b.dispatchedOn && b.lines.some(l => !l.outcome) && waitDays(b) > companyCfg(b.company).answer && keep("batch", b.no, String(b.lines.filter(l => !l.outcome).length)));
  const low = DB.items.filter(i => i.active && isLow(i));
  const cRow = (c, extra, kind, state) => `<div class="list-group-item"><div class="d-flex align-items-center gap-2 flex-wrap">${cLink(c.no)} ${prioBadge(c.priority)}
      <span class="fw-medium">${esc(siteName(c))}</span><span class="text-secondary small">${esc(siteCity(c))} · ${esc(c.company)}</span>
      <span class="ms-auto d-flex align-items-center gap-1">${extra}${dis(kind, c.no, state)}</span></div>
      <div class="small text-secondary mt-1">${esc(c.fault)} · ${esc(c.techs.join(", ") || "no technician")}</div></div>`;
  return [
    { key: "unatt", title: "Not attended yet", ic: "alert-circle", tone: "alert", help: `Filed more than ${SMART.unattended} working days ago, nobody has visited.`,
      rows: unatt.map(c => cRow(c, `<span class="badge st st-alert">${icon("clock")}${workdays(c.reportedOn, today())} working days</span><a class="btn btn-sm btn-primary" href="#visit/${c.no}">${icon("clipboard-plus")} Record visit</a>`, "unatt", c.status)) },
    { key: "over", title: "Overdue complaints", ic: "alarm", tone: "alert", help: "Past the due date for their priority. Awaiting material does not count.",
      rows: over.map(c => cRow(c, `${dueChip(c)} ${cBadge(c.status)}`, "over", c.status + c.priority)) },
    { key: "short", title: "Parts short for open complaints", ic: "package-off", tone: "alert", help: "Parts needed by open complaints that good stock can't cover.",
      rows: shortNeeds.map(n => `<div class="list-group-item d-flex align-items-center gap-2 flex-wrap"><span class="code">${esc(n.code)}</span>
        <span class="text-secondary small">${esc((item(n.code) || {}).desc || "")}</span><span class="text-secondary small">for ${cLink(n.complaint)}</span>
        <span class="ms-auto d-flex align-items-center gap-1"><span class="badge st st-alert">${icon("alert-triangle")}Need ${n.qty}, have ${total(n.code)}</span>
        <a class="btn btn-sm btn-in" href="#in/${encodeURIComponent(n.code)}">${icon("package-import")} Stock IN</a>${dis("short", n.complaint + n.code, String(total(n.code)))}</span></div>`) },
    { key: "store", title: "Defective pieces waiting for a return batch", ic: "recycle", tone: "wait", help: `In the defective store for more than ${SMART.storeWait} days.`,
      rows: store.map(([co, ps]) => `<div class="list-group-item d-flex align-items-center gap-2 flex-wrap"><span class="fw-medium">${esc(co)}</span>
        <span class="text-secondary small">${ps.length} piece${ps.length > 1 ? "s" : ""}, oldest ${Math.max(...ps.map(p => daysBetween(p.collectedOn, today())))} days</span>
        <span class="ms-auto d-flex align-items-center gap-1"><a class="btn btn-sm btn-quiet" href="#batch-new/${encodeURIComponent(co)}">${icon("truck-return")} New return batch</a>${dis("store", co, String(ps.length))}</span></div>`) },
    { key: "batch", title: "Return batches the company hasn't answered", ic: "truck", tone: "wait", help: "Dispatched longer ago than the company's answer time (Smart settings).",
      rows: late.map(b => `<div class="list-group-item d-flex align-items-center gap-2 flex-wrap">${batchLink(b.no)} <span class="fw-medium">${esc(b.company)}</span>
        <span class="text-secondary small">dispatched ${fmt(b.dispatchedOn)} · ${b.courier} ${esc(b.docket)}</span>
        <span class="ms-auto d-flex align-items-center gap-1"><span class="badge st st-wait">${icon("hourglass")}${waitDays(b)} days (answer in ${companyCfg(b.company).answer})</span>
        ${dis("batch", b.no, String(b.lines.filter(l => !l.outcome).length))}</span></div>`) },
    { key: "low", title: "Low stock", ic: "alert-triangle", tone: "alert", help: "At or below the reorder level.",
      rows: low.length ? [`<a class="list-group-item list-group-item-action d-flex align-items-center" href="#low">${low.length} item${low.length > 1 ? "s" : ""} at or below the reorder level
        <span class="ms-auto">${icon("chevron-right")}</span></a>`] : [] },
  ];
}
const todayCount = () => sum(todaySections(), s => s.key === "low" ? 0 : s.rows.length);
function dismissToday(kind, id, state) { SMART.dismissed.add(`${kind}|${id}|${state}`); logSuggestion("today_" + kind, id, "dismissed"); toast("Hidden. It comes back if it changes."); route(); }
ROUTES.today = () => {
  const secs = todaySections(), n = todayCount();
  setHeader("Overview", `${icon("checklist")} Today`, `<span class="text-secondary me-2 align-self-center">${icon("calendar")} ${fmt(today())}</span>
    <a href="#digest" class="btn btn-quiet">${icon("mail")} Morning email preview</a>`);
  view().innerHTML = `<div class="alert ${n ? "alert-warning" : "alert-success"}">${icon(n ? "list-check" : "circle-check")}
      ${n ? `<b>${n} thing${n > 1 ? "s" : ""} need${n === 1 ? "s" : ""} chasing today.</b> Hide a row with ${icon("eye-off")} once it's handled; it comes back if it changes.` : "Nothing needs chasing today."}</div>
    <div class="row row-cards">${secs.map(s => `<div class="col-12 col-xl-6"><div class="card h-100"><div class="card-header">
      <h3 class="card-title"><span class="avatar avatar-sm kpi-${s.rows.length ? s.tone : "ok"} me-2">${icon(s.ic)}</span>${s.title}</h3>
      <span class="badge ${s.rows.length ? "bg-secondary-lt" : "bg-green-lt"} ms-auto">${s.key === "low" ? (s.rows.length ? "see list" : 0) : s.rows.length}</span></div>
      <div class="card-body py-2 small text-secondary border-bottom flex-grow-0">${s.help}</div>
      <div class="list-group list-group-flush">${s.rows.join("") || `<div class="list-group-item text-secondary">${icon("circle-check", "text-green me-1")}Nothing here.</div>`}</div></div></div>`).join("")}</div>`;
};
function todayCard() {
  const secs = todaySections().filter(s => s.rows.length && s.key !== "low"), n = todayCount();
  return `<div class="col-12"><div class="card today-card"><div class="card-body d-flex flex-column flex-md-row align-items-md-center gap-3">
    <div class="d-flex gap-3 flex-fill min-w-0"><span class="avatar kpi-${n ? "alert" : "ok"} flex-shrink-0">${icon(n ? "checklist" : "circle-check")}</span>
    <div class="flex-fill min-w-0"><div class="fw-bold fs-3">${n ? `${n} thing${n > 1 ? "s" : ""} to chase today` : "Nothing to chase today"}</div>
      <div class="d-flex flex-wrap gap-2 mt-1">${secs.map(s => `<a class="chip chip-link" href="#today">${icon(s.ic)}${s.title}: <b>${s.rows.length}</b></a>`).join("")}</div></div></div>
    <a href="#today" class="btn btn-primary flex-shrink-0">${icon("checklist")} Open Today list</a></div></div></div>`;
}
const _dash = ROUTES.dash;
ROUTES.dash = () => { _dash(); view().querySelector(".row").insertAdjacentHTML("afterbegin", todayCard()); };

/* ---------- Morning email preview (1.2) ---------- */
ROUTES.digest = () => {
  const secs = todaySections().filter(s => s.rows.length);
  setHeader("Overview · Today", `${icon("mail")} Morning email preview`, `<a href="#today" class="btn btn-quiet">${icon("arrow-left")} Back to Today</a>`);
  const strip = h => h.replace(/<button[\s\S]*?<\/button>/g, "").replace(/<a class="btn[\s\S]*?<\/a>/g, "");
  view().innerHTML = `<div class="row justify-content-center"><div class="col-lg-9">
    <p class="text-secondary">${SMART.digest.on ? `${icon("clock")} Sent every working day at <b>${SMART.digest.time}</b> to <b>${esc(SMART.digest.to)}</b>. Nothing is sent on days when the list is empty.`
      : `${icon("bell-off")} The morning email is <b>off</b> (Smart settings). The Today list still works in the app.`}</p>
    <div class="card digest-mail"><div class="card-header d-block small">
      <div><span class="text-secondary">From:</span> SVKML Service &lt;noreply@svkml.in&gt;</div>
      <div><span class="text-secondary">To:</span> ${esc(SMART.digest.to)}</div>
      <div><span class="text-secondary">Subject:</span> <b>Today: ${todayCount()} things to chase (${fmt(today())})</b></div></div>
      <div class="card-body"><p>Good morning. Here is what needs chasing today. Open the app for details.</p>
      ${secs.map(s => `<h4 class="mt-3 mb-1">${s.title} (${s.key === "low" ? "see app" : s.rows.length})</h4><div class="list-group list-group-flush border rounded">${s.rows.map(strip).join("")}</div>`).join("")}
      <p class="mt-4 text-secondary small">You get this email because you are on the morning list in Smart settings.</p></div></div></div></div>`;
};

/* ---------- Low stock + reorder suggestions (2.1) ---------- */
function consumptionWeeks(code) {   // 12 weekly totals, oldest first; real ledger data + made-up weeks before the demo starts
  const start = DB.entries.reduce((m, e) => e.date < m ? e.date : m, today());
  const weeks = Array(12).fill(0), mature = seeded(code, 0) > 0.25;
  for (const e of DB.entries) {
    if (undoneBy(e.no) || e.kind === "REV") continue;
    const use = (e.kind === "OUT" && ["SITE", "TECH", "OTHER", "COMPLAINT"].includes(e.subtype)) ? -1 : (e.kind === "IN" && e.subtype === "RETURN") ? -1 : 0;
    if (!use) continue;
    const w = 11 - Math.floor(daysBetween(e.date, today()) / 7);
    if (w >= 0) for (const l of e.lines) if (l.code === code) weeks[w] += use * l.qty;
  }
  let have = 0;
  for (let w = 0; w < 12; w++) {
    const weekStart = addDays(today(), -(12 - w) * 7);
    if (weekStart >= start) { have++; continue; }
    if (mature) { weeks[w] = seeded(code, w + 1) > 0.45 ? Math.round(seeded(code, w + 40) * 4) + 1 : 0; have++; }
  }
  return { weeks: weeks.map(x => Math.max(0, x)), have };
}
function reorderSuggestion(i) {
  const { weeks, have } = consumptionWeeks(i.code), L = companyCfg(i.company).lead;
  if (have < 12) return { learning: true, have };
  const used = sum(weeks, x => x), nz = weeks.filter(x => x > 0).length, mean = used / 12;
  const sd = Math.sqrt(sum(weeks, x => (x - mean) ** 2) / 12);
  let d = used / 84, method = "average use";
  if (nz >= 4 && 12 / nz > 1.32) {   // patchy use: Croston-SBA weekly rate
    let z = 0, p = 1, q = 1, first = true; const a = 0.1;
    for (const x of weeks) { if (x > 0) { if (first) { z = x; p = q; first = false; } else { z += a * (x - z); p += a * (q - p); } q = 1; } else q++; }
    d = (1 - a / 2) * z / p / 7; method = "patchy-use forecast (SBA)";
  }
  const safety = Math.ceil(1.65 * sd * Math.sqrt(L / 7)), level = Math.ceil(d * L + 1.65 * sd * Math.sqrt(L / 7));
  return { learning: false, weeks, used, nz, L, safety, level, method,
    short: `${method === "average use" ? "Average use" : "Patchy use (SBA)"} · lead ${L} d · safety ${safety}`,
    why: `Used ${used} ${i.unit} in the last 12 weeks (in ${nz} of them), ${method}. Lead time ${L} days (${i.company}). Safety stock ${safety} for uneven weeks.` };
}
const sparkBars = weeks => { const m = Math.max(1, ...weeks); return `<span class="spark" title="Use per week, last 12 weeks">${weeks.map(x =>
  `<span style="height:${Math.max(2, x / m * 18)}px" class="${x ? "" : "z"}"></span>`).join("")}</span>`; };
let lowTab = "low";
function acceptReorder(code) { const i = item(code), s = reorderSuggestion(i); const old = i.reorder; i.reorder = s.level; logSuggestion("reorder", code, "accepted");
  toastAfterNav(`Reorder level of <b>${esc(code)}</b>: ${old} → <b>${s.level}</b> ${i.unit}.`); route(); }
function dismissReorder(code) { SMART.dismissed.add(`reorder|${code}|${reorderSuggestion(item(code)).level}`); logSuggestion("reorder", code, "dismissed"); route(); }
ROUTES.low = () => {
  const rows = DB.items.filter(i => i.active && isLow(i));
  const sugg = DB.items.filter(i => i.active).map(i => ({ i, s: reorderSuggestion(i) }));
  const ready = sugg.filter(x => !x.s.learning && x.s.level !== x.i.reorder && !SMART.dismissed.has(`reorder|${x.i.code}|${x.s.level}`));
  const learning = sugg.filter(x => x.s.learning);
  setHeader("Reports", "Low stock", exportBtn("Low_Stock.xlsx"));
  const tabs = `<ul class="nav nav-tabs card-header-tabs mb-0">${[["low", `Low now`, rows.length], ["sugg", "Reorder level suggestions", ready.length]].map(([k, l, n]) =>
    `<li class="nav-item"><a href="#" class="nav-link ${lowTab === k ? "active" : ""}" onclick="lowTab='${k}';route();return false">${l} <span class="badge ${lowTab === k ? "bg-primary text-white" : "bg-secondary-lt"} ms-1">${n}</span></a></li>`).join("")}</ul>`;
  const suggCell = i => { const s = reorderSuggestion(i); return s.learning ? `<span class="text-secondary small">${icon("school")} learning</span>`
    : s.level === i.reorder ? `<span class="text-secondary">${s.level}</span>` : `<span class="fw-bold" title="${esc(s.why)}">${s.level}</span>`; };
  view().innerHTML = lowTab === "low" ? `<div class="alert alert-${rows.length ? "warning" : "success"}">${icon(rows.length ? "alert-triangle" : "circle-check")}
      ${rows.length ? `${rows.length} items are at or below their reorder level (total across all locations).` : "Nothing is low."}</div>
    <div class="card"><div class="card-header pb-0 border-0">${tabs}</div>${dataTable("low", { rows, sort: "short", dir: "desc", columns: [
      { key: "code", label: "Item code", html: i => codeLink(i.code) }, { key: "type", label: "Spare type" }, { key: "desc", label: "Description" }, { key: "company", label: "Company" },
      ...DB.locations.map(l => ({ key: "L:" + l, label: esc(l), num: true, sort: i => balance(i.code, l), html: i => qtyHtml(balance(i.code, l)) })),
      { key: "total", label: "Total", num: true, sort: i => total(i.code), html: i => `<span class="badge bg-red-lt">${total(i.code)}</span>` },
      { key: "reorder", label: "Reorder at", num: true },
      { key: "sugg", label: "Suggested", num: true, nosort: true, html: suggCell },
      { key: "short", label: "Short by", num: true, sort: i => i.reorder - total(i.code), html: i => `<b class="text-danger">${Math.max(0, i.reorder - total(i.code))}</b>` },
      { key: "unit", label: "Unit" },
      { key: "act", label: "", nosort: true, html: i => `<a href="#in/${encodeURIComponent(i.code)}" class="btn btn-sm btn-in">${icon("package-import")} Stock IN</a>` }] })}</div>`
  : `${suggestBox(`<b>Suggested reorder levels</b> come from how much of each item was really used (parts given at visits and Stock OUT to sites and technicians, minus unused returns), the company's lead time and a safety margin for uneven weeks. <b>Nothing changes until you press Accept.</b>`)}
    <div class="card mt-3"><div class="card-header pb-0 border-0">${tabs}</div>${dataTable("sugg", { rows: ready, sort: "diff", dir: "desc", empty: "No suggestions right now.", columns: [
      { key: "code", label: "Item", sort: x => x.i.code, html: x => itemCell(x.i.code) }, { key: "company", label: "Company", sort: x => x.i.company, html: x => esc(x.i.company) },
      { key: "use", label: "Use, 12 weeks", nosort: true, html: x => `${sparkBars(x.s.weeks)} <span class="small text-secondary ms-1">${x.s.used} ${x.i.unit}</span>` },
      { key: "stock", label: "Good stock", num: true, sort: x => total(x.i.code), html: x => total(x.i.code) },
      { key: "cur", label: "Reorder at now", num: true, sort: x => x.i.reorder, html: x => x.i.reorder },
      { key: "diff", label: "Suggested", num: true, sort: x => Math.abs(x.s.level - x.i.reorder), html: x => `<b>${x.s.level}</b> <span class="small ${x.s.level > x.i.reorder ? "text-danger" : "text-secondary"}">(${x.s.level > x.i.reorder ? "+" : ""}${x.s.level - x.i.reorder})</span>` },
      { key: "why", label: "Why", nosort: true, cls: "small text-secondary", html: x => `<span title="${esc(x.s.why)}">${esc(x.s.short)} ${icon("info-circle")}</span>` },
      { key: "act", label: "", nosort: true, html: x => `<div class="d-flex flex-column gap-1"><button class="btn btn-sm btn-primary" onclick="acceptReorder('${esc(x.i.code)}')">${icon("check")} Accept</button>
        <button class="btn btn-sm btn-link py-0" onclick="dismissReorder('${esc(x.i.code)}')">Not now</button></div>` }] })}</div>
    ${learning.length ? `<div class="mt-3">${learningBox(`${learning.length} item${learning.length > 1 ? "s have" : " has"} less than 12 weeks of use recorded (${learning.slice(0, 4).map(x => `<span class="code">${esc(x.i.code)}</span>`).join(", ")}${learning.length > 4 ? "…" : ""}).`, learning[0].s.have, 12)}</div>` : ""}`;
};
const _item = ROUTES.item;
ROUTES.item = code => {
  _item(code);
  const i = item(code); if (!i) return;
  const s = reorderSuggestion(i), col = view().querySelector(".col-lg-4");
  col.insertAdjacentHTML("beforeend", `<div class="card mt-3"><div class="card-header"><h3 class="card-title">${icon("trending-up")} Reorder level</h3></div><div class="card-body">
    ${s.learning ? learningBox("the reorder suggestion needs 12 weeks of use.", s.have, 12) : `
      <div class="d-flex align-items-baseline gap-2"><span class="text-secondary">Now</span><b class="fs-3">${i.reorder}</b>
        <span class="text-secondary ms-3">Suggested</span><b class="fs-3 ${s.level !== i.reorder ? "text-primary" : ""}">${s.level}</b> <span class="text-secondary">${i.unit}</span></div>
      <div class="mt-2">${sparkBars(s.weeks)}</div><div class="small text-secondary mt-2">${esc(s.why)}</div>
      ${s.level !== i.reorder ? `<button class="btn btn-primary btn-sm mt-3" onclick="acceptReorder('${esc(code)}')">${icon("check")} Accept ${s.level}</button>` : `<div class="small mt-2">${icon("circle-check", "text-green")} The current level matches.</div>`}`}
    </div></div>`);
};

/* ---------- Slow and dead stock (2.2) ---------- */
let slowDays = 90;
function lastUsed(code) {
  let last = "";
  for (const e of DB.entries) if (e.kind === "OUT" && ["SITE", "TECH", "OTHER", "COMPLAINT"].includes(e.subtype) && !undoneBy(e.no) && e.lines.some(l => l.code === code)) last = e.date > last ? e.date : last;
  return last || addDays(today(), -(60 + Math.round(seeded(code, 99) * 220)));   // made up for the demo: before the ledger starts
}
ROUTES.slow = () => {
  const rows = DB.items.filter(i => i.active && total(i.code) > 0 && daysBetween(lastUsed(i.code), today()) >= slowDays);
  setHeader("Reports", `${icon("zzz")} Slow and dead stock`, mockDownload("Slow_Stock.xlsx"));
  view().innerHTML = `${suggestBox(`Items with good stock that nobody has used for a long time. Consider moving them to the location that uses them, or returning them to the supplier.`)}
    <div class="card mt-3"><div class="card-body border-bottom py-3"><div class="row g-2 align-items-end">
      ${filterCol(3, fsel("Not used for", "slowDays=+this.value;resetPage('slow');route()", [["90", "90 days or more"], ["180", "180 days or more"], ["365", "1 year or more"]], String(slowDays)))}</div></div>
    ${dataTable("slow", { rows, sort: "idle", dir: "desc", empty: "Nothing has been idle that long.", columns: [
      { key: "code", label: "Item", html: i => itemCell(i.code) }, { key: "company", label: "Company" },
      ...DB.locations.map(l => ({ key: "L:" + l, label: esc(l), num: true, sort: i => balance(i.code, l), html: i => qtyHtml(balance(i.code, l)) })),
      { key: "total", label: "Total", num: true, sort: i => total(i.code), html: i => `<b>${total(i.code)}</b> ${i.unit}` },
      { key: "last", label: "Last used", sort: i => lastUsed(i.code), html: i => fmt(lastUsed(i.code)) },
      { key: "idle", label: "Idle", num: true, sort: i => daysBetween(lastUsed(i.code), today()), html: i => { const d = daysBetween(lastUsed(i.code), today());
        return `<span class="badge st ${d >= 180 ? "st-alert" : "st-wait"}">${d} days</span>`; } }] })}</div>`;
};

/* ---------- Insights: fault patterns (2.3) ---------- */
ROUTES.insights = () => {
  const since = d => addDays(today(), -d);
  const byBatch = {};
  for (const p of DB.pieces.filter(p => p.batch && p.collectedOn >= since(90))) (byBatch[`${p.batch}|${p.code}`] ||= []).push(p);
  const batches = Object.entries(byBatch).map(([k, ps]) => ({ batch: k.split("|")[0], code: k.split("|")[1], n: ps.length, n30: ps.filter(p => p.collectedOn >= since(30)).length,
    company: ps[0].company, pkd: ps[0].pkd, sites: uniq(ps.map(p => p.complaint ? siteName(complaint(p.complaint)) : "Found in stock")) })).filter(x => x.n >= 2);
  const bySite = {};
  for (const c of DB.complaints.filter(c => c.reportedOn >= since(90))) (bySite[c.site] ||= []).push(c);
  const repeat = Object.entries(bySite).filter(([, cs]) => cs.length >= 2).map(([id, cs]) => ({ s: site(id), cs }));
  const byItem = {};
  for (const p of DB.pieces.filter(p => p.collectedOn >= since(90))) byItem[p.code] = (byItem[p.code] || 0) + 1;
  const comp = uniq(DB.batches.map(b => b.company)).map(co => {
    const ls = DB.batches.filter(b => b.company === co && b.dispatchedOn).flatMap(b => b.lines.map(l => ({ ...l, b })));
    const done = ls.filter(l => l.outcome), rej = done.filter(l => l.outcome.startsWith("REJECTED"));
    const days = done.map(l => daysBetween(l.b.dispatchedOn, l.settledOn || l.b.dispatchedOn));
    return { co, sent: ls.length, done: done.length, rej: rej.length, avg: days.length ? Math.round(sum(days, x => x) / days.length) : null, waiting: ls.length - done.length };
  });
  const alertBatches = batches.filter(b => b.n30 >= 3);
  setHeader("Reports", `${icon("chart-dots-3")} Insights`, mockDownload("Insights.xlsx"));
  view().innerHTML = `${learningBox("patterns get sharper with time. The demo has 6 weeks of data; they are most useful after 3 months.", 6, 12)}
    <div class="row row-deck row-cards mt-1">
      ${kpiTile("repeat", repeat.length ? "alert" : "brand", repeat.length, "Sites with repeat complaints", "2+ in 90 days", "#insights", "col-6 col-lg-3")}
      ${kpiTile("barcode", alertBatches.length ? "alert" : "brand", alertBatches.length, "Batch codes failing", "3+ pieces in 30 days", "#insights", "col-6 col-lg-3")}
      ${kpiTile("recycle", "brand", sum(Object.values(byItem), x => x), "Failed pieces", "collected in 90 days", "#pieces", "col-6 col-lg-3")}
      ${kpiTile("clock-hour-4", "brand", comp.filter(c => c.avg !== null).map(c => `${c.avg} d`).join(" / ") || "—", "Company answer time", comp.filter(c => c.avg !== null).map(c => c.co.split(" ")[0]).join(" / "), "#batches", "col-6 col-lg-3")}
      ${alertBatches.length ? `<div class="col-12">${suggestBox(`<b>${alertBatches.length} batch code${alertBatches.length > 1 ? "s" : ""} may be bad</b> (3 or more pieces failed in 30 days). Mention them to the company with the next return batch:
        <ul class="mb-0 mt-1">${alertBatches.map(b => `<li><span class="code">${esc(b.batch)}</span> of <span class="code">${esc(b.code)}</span>: ${b.n30} failed, ${esc(b.company)}, packed ${fmtMonth(b.pkd)}, at ${esc(b.sites.join(", "))}</li>`).join("")}</ul>`,
        `<a class="btn btn-sm btn-quiet" href="#pieces">${icon("tags")} See pieces</a>`)}</div>` : ""}
      <div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">${icon("barcode")} Failures by batch code</h3><div class="card-subtitle ms-2">90 days, 2+ pieces</div></div>
        ${dataTable("ins-batch", { rows: batches, sort: "n30", dir: "desc", size: 8, empty: "No batch code has failed twice yet.", columns: [
          { key: "batch", label: "Batch", html: b => `<span class="code">${esc(b.batch)}</span><div class="small text-secondary">packed ${fmtMonth(b.pkd)}</div>` },
          { key: "code", label: "Item", html: b => codeLink(b.code) }, { key: "company", label: "Company" },
          { key: "n30", label: "30 days", num: true, html: b => b.n30 >= 3 ? `<span class="badge st st-alert">${b.n30}</span>` : b.n30 }, { key: "n", label: "90 days", num: true }] })}</div></div>
      <div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">${icon("repeat")} Repeat complaints at the same site</h3><div class="card-subtitle ms-2">90 days</div></div>
        <div class="list-group list-group-flush">${repeat.map(r => `<div class="list-group-item"><div class="d-flex align-items-center gap-2"><a href="#site/${r.s.id}" class="fw-medium">${esc(r.s.name)}</a>
          <span class="text-secondary small">${esc(r.s.city)}</span><span class="badge st st-alert ms-auto">${r.cs.length} complaints</span></div>
          <div class="small text-secondary mt-1">${r.cs.map(c => `${cLink(c.no)} ${esc(c.fault)}`).join("<br>")}</div></div>`).join("") || `<div class="list-group-item text-secondary">No site has complained twice in 90 days.</div>`}</div></div></div>
      <div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">${icon("box")} Items failing most</h3><div class="card-subtitle ms-2">pieces collected, 90 days</div></div>
        ${barList(Object.entries(byItem).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, n]) => [k, n]), k => `#item/${encodeURIComponent(k)}`)}</div></div>
      <div class="col-lg-6"><div class="card"><div class="card-header"><h3 class="card-title">${icon("building-store")} How companies answer return batches</h3></div>
        ${dataTable("ins-co", { rows: comp, paging: false, sort: "co", columns: [{ key: "co", label: "Company" }, { key: "sent", label: "Sent", num: true },
          { key: "done", label: "Answered", num: true }, { key: "rej", label: "Rejected", num: true, html: r => r.done ? `${r.rej} <span class="text-secondary small">(${Math.round(r.rej / r.done * 100)}%)</span>` : "—" },
          { key: "avg", label: "Avg. days", num: true, html: r => r.avg ?? "—" }, { key: "waiting", label: "Waiting", num: true }] })}</div></div>
    </div>`;
};

/* ---------- Drafts inbox (3.3 / 3.4) ---------- */
const SRC_IC = { WhatsApp: "brand-whatsapp", Email: "mail", Pasted: "clipboard-text" };
ROUTES.drafts = () => {
  setHeader("Complaints", `${icon("inbox")} Message inbox`, `<span class="badge bg-secondary-lt align-self-center">Optional AI · only if the client approves</span>`);
  const dStatus = d => d.status === "New" ? `<span class="badge st st-wait">${icon("mail")}New</span>` : d.status === "Filed"
    ? `<span class="badge st st-ok">${icon("check")}Filed ${d.complaint ? cLink(d.complaint) : ""}</span>` : `<span class="badge st st-done">${icon("ban")}Ignored</span>`;
  view().innerHTML = `${suggestBox(`Complaint messages forwarded to <b>complaints@svkml.in</b> and sent to the office WhatsApp number land here. Open one to get a <b>pre-filled complaint form</b>; nothing is filed until you check it and press Save.`)}
    ${aiOff() ? `<div class="alert alert-secondary mt-3">${icon("lock")} The AI assistant is off, so messages are listed but not read. Turn it on in Smart settings.</div>` : ""}
    <div class="card mt-3">${dataTable("drafts", { rows: SMART.drafts, sort: "at", dir: "desc", paging: false, columns: [
      { key: "at", label: "Received", cls: "nowrap", html: d => `${fmt(d.at.slice(0, 10))} <span class="text-secondary small">${d.at.slice(11)}</span>` },
      { key: "source", label: "From", html: d => `${icon(SRC_IC[d.source], "me-1 text-secondary")}${d.source}<div class="small text-secondary">${esc(d.from)}</div>` },
      { key: "text", label: "Message", cls: "cell-wrap", html: d => esc(d.text) },
      { key: "read", label: "What the app read", cls: "cell-wrap small", nosort: true, html: d => { if (d.status === "Ignored") return ""; const x = extractMessage(d.text);
        return `${x.site ? `${icon("building", "text-secondary")} ${esc(x.site.name)}, ${esc(x.site.city)} <span class="text-secondary">(known site, same phone)</span>` : x.newSite ? `${icon("building-plus", "text-secondary")} New site: ${esc(x.newSite)}, ${esc(x.city)}` : ""}
          <div>${icon("bulb", "text-secondary")} ${esc(x.fault)}${x.qty ? ` · qty ${x.qty}` : ""}</div>${x.company ? `<div>${icon("building-store", "text-secondary")} ${esc(x.company)}${x.ref ? ` · <span class="code">${esc(x.ref)}</span>` : ""}</div>` : ""}`; } },
      { key: "status", label: "Status", html: dStatus },
      { key: "act", label: "", nosort: true, cls: "nowrap", html: d => d.status === "New" ? `<a class="btn btn-sm btn-primary" href="#complaint-new/draft-${d.id}">${icon("file-plus")} Open as complaint</a>
        <button class="btn btn-sm btn-link" onclick="ignoreDraft('${d.id}')">Ignore</button>` : "" }] })}</div>`;
};
function ignoreDraft(id) { SMART.drafts.find(d => d.id === id).status = "Ignored"; toast("Message ignored."); route(); }

/* ---------- Smart settings (Admin) ---------- */
ROUTES.smart = () => {
  setHeader("Setup", `${icon("adjustments-bolt")} Smart settings`, adminOnly());
  const num = (id, v, min = 0) => `<input id="${id}" type="number" min="${min}" step="1" inputmode="numeric" class="form-control" value="${v}">`;
  const learn = [["Reorder suggestions", "12 weeks of use per item", 6], ["Slow and dead stock", "90 days of history", 42], ["Fault patterns (Insights)", "3 months", 6],
    ["Parts usually needed", "5 visits with parts for a fault type", 3], ["Technician hint", "10 visits", 22]];
  view().innerHTML = `<div class="row row-cards">
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("alarm")} Complaint due dates</h3></div><div class="card-body"><div class="row g-3">
      ${["Urgent", "High", "Normal"].map(p => fcol(4, lbl(`s-due-${p}`, `${p}`) + num(`s-due-${p}`, SMART.due[p], 1) + `<small class="form-hint">working days</small>`)).join("")}
      ${fcol(6, lbl("s-unatt", "Not attended alert after") + num("s-unatt", SMART.unattended, 1) + `<small class="form-hint">working days</small>`)}
      ${fcol(6, lbl("s-store", "Defective pieces waiting alert after") + num("s-store", SMART.storeWait, 1) + `<small class="form-hint">days in the store without a batch</small>`)}
      <div class="col-12 small text-secondary">${icon("info-circle")} Time in <b>Awaiting material</b> doesn't count. Sundays and the holidays below don't count.</div></div></div></div></div>
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("calendar-off")} Holidays</h3><span class="badge bg-secondary-lt ms-2">Sundays are always off</span></div>
      <div class="list-group list-group-flush">${SMART.holidays.slice().sort((a, b) => a.date.localeCompare(b.date)).map(h => `<div class="list-group-item d-flex align-items-center">
        <span class="nowrap me-3">${fmt(h.date)}</span>${esc(h.name)}<button class="btn btn-sm btn-ghost-danger ms-auto" aria-label="Remove holiday" onclick="removeHoliday('${h.date}')">${icon("x")}</button></div>`).join("")}</div>
      <div class="card-footer"><div class="row g-2">${fcol(4, `<input id="s-hol-date" type="date" class="form-control" aria-label="Holiday date">`)}
        ${fcol(5, `<input id="s-hol-name" class="form-control" placeholder="e.g. Sankranti" aria-label="Holiday name">`)}
        <div class="col-12 col-md-3"><button class="btn btn-quiet w-100" onclick="addHoliday()">${icon("plus")} Add</button></div></div></div></div></div>
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("building-store")} Companies</h3></div>
      <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Company</th><th>Answers a return batch within</th><th>Lead time for spares</th></tr></thead><tbody>
      ${DB.companies.map((co, n) => `<tr><td class="fw-medium">${esc(co)}</td>
        <td><div class="input-group input-group-sm" style="max-width:9rem"><input type="number" min="1" class="form-control co-ans" data-co="${esc(co)}" value="${companyCfg(co).answer}" aria-label="Answer days for ${esc(co)}"><span class="input-group-text">days</span></div></td>
        <td><div class="input-group input-group-sm" style="max-width:9rem"><input type="number" min="1" class="form-control co-lead" data-co="${esc(co)}" value="${companyCfg(co).lead}" aria-label="Lead time for ${esc(co)}"><span class="input-group-text">days</span></div></td></tr>`).join("")}
      </tbody></table></div><div class="card-footer small text-secondary">Used by the Today list (late return batches) and the reorder suggestions.</div></div></div>
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("mail")} Morning email</h3></div><div class="card-body">
      <label class="form-check form-switch mb-3"><input id="s-dig-on" class="form-check-input" type="checkbox" ${SMART.digest.on ? "checked" : ""}><span class="form-check-label">Send the Today list by email every working day</span></label>
      <div class="row g-3">${fcol(8, lbl("s-dig-to", "Send to") + `<input id="s-dig-to" type="text" class="form-control" value="${esc(SMART.digest.to)}"><small class="form-hint">Email addresses, separated by commas</small>`)}
        ${fcol(4, lbl("s-dig-time", "At") + `<input id="s-dig-time" type="time" class="form-control" value="${SMART.digest.time}">`)}</div>
      <a href="#digest" class="btn btn-sm btn-link px-0 mt-2">${icon("eye")} Preview today's email</a></div></div></div>
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("sparkles")} AI assistant</h3><span class="badge bg-secondary-lt ms-2">Optional · client decides</span></div><div class="card-body">
      <label class="form-check form-switch mb-3"><input id="s-ai-on" class="form-check-input" type="checkbox" ${SMART.ai.on ? "checked" : ""}><span class="form-check-label">Read pasted messages, the message inbox and photos with AI</span></label>
      <div class="row g-3 align-items-end">${fcol(5, lbl("s-ai-cap", "Monthly limit") + `<div class="input-group"><span class="input-group-text">₹</span><input id="s-ai-cap" type="number" min="0" step="50" class="form-control" value="${SMART.ai.cap}"></div>`)}
        <div class="col-12 col-md-7"><div class="small mb-1">This month: <b>₹${SMART.ai.used.toFixed(2)}</b> of ₹${SMART.ai.cap}</div>
          <div class="progress"><div class="progress-bar ${SMART.ai.used / SMART.ai.cap > 0.8 ? "bg-red" : "bar-brand"}" style="width:${Math.min(100, SMART.ai.used / SMART.ai.cap * 100)}%"></div></div></div></div>
      <div class="form-hint mt-2">${icon("shield-lock")} Message text and photos are sent to the AI provider to be read. When the limit is reached the AI buttons are hidden until next month.</div></div>
      <div class="table-responsive"><table class="table table-sm card-table"><thead><tr><th>When</th><th>What</th><th class="num">₹</th></tr></thead><tbody>
        ${SMART.ai.log.slice(0, 5).map(l => `<tr><td class="nowrap small">${esc(l.at)}</td><td class="small">${esc(l.what)}</td><td class="num small">${l.inr.toFixed(2)}</td></tr>`).join("")}</tbody></table></div></div></div>
    <div class="col-lg-6"><div class="card h-100"><div class="card-header"><h3 class="card-title">${icon("school")} What the app has learned so far</h3></div>
      <div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Feature</th><th>Needs</th><th>Status</th></tr></thead><tbody>
      ${learn.map(([f, need, pct]) => `<tr><td>${f}</td><td class="small text-secondary">${need}</td><td>${pct >= 12 ? `<span class="badge st st-ok">${icon("check")}Ready</span>`
        : `<span class="badge st st-neutral">${icon("school")}Learning</span>`}</td></tr>`).join("")}</tbody></table></div>
      <div class="card-footer small text-secondary">Learning features show nothing until they have enough data, rather than guess.</div></div></div>
    <div class="col-12 d-flex"><button class="btn btn-primary ms-auto" onclick="saveSmart()">${icon("device-floppy")} Save settings</button></div></div>`;
};
function saveSmart() {
  for (const p of ["Urgent", "High", "Normal"]) SMART.due[p] = Math.max(1, Number(field(`s-due-${p}`).value) || 1);
  SMART.unattended = Number(field("s-unatt").value) || 2; SMART.storeWait = Number(field("s-store").value) || 30;
  document.querySelectorAll(".co-ans").forEach(i => companyCfg(i.dataset.co).answer = Number(i.value) || 30);
  document.querySelectorAll(".co-lead").forEach(i => companyCfg(i.dataset.co).lead = Number(i.value) || 7);
  Object.assign(SMART.digest, { on: field("s-dig-on").checked, to: field("s-dig-to").value, time: field("s-dig-time").value });
  SMART.ai.on = field("s-ai-on").checked; SMART.ai.cap = Number(field("s-ai-cap").value) || 0;
  toastAfterNav("Smart settings saved."); route();
}
function addHoliday() {
  const d = field("s-hol-date").value, n = field("s-hol-name").value.trim();
  if (!d || !n) { toast("Choose a date and type a name.", "danger"); return; }
  if (SMART.holidays.some(h => h.date === d)) { toast(`${fmt(d)} is already a holiday.`, "danger"); return; }
  SMART.holidays.push({ date: d, name: n }); toastAfterNav(`Holiday added: ${fmt(d)} ${esc(n)}.`); route();
}
function removeHoliday(d) { SMART.holidays = SMART.holidays.filter(h => h.date !== d); route(); }

/* ---------- Import old Excel data (2.6) ---------- */
let importStep = "pick";
const IMPORT_FILES = [["imp-items", "Material list", "Vizag_Store_All_Material_List.xlsx", "Items and opening stock"],
  ["imp-def", "Fresh / defective list", "25-5-2026_Vizag_Fresh__Defective_list.xlsx", "Defective pieces still in the store"],
  ["imp-comp", "Pending complaints", "AP_Pending_Compliants_details.xlsx", "Sites and past complaints"]];
const IMPORT_ISSUES = [
  ["Pending complaints", 4, "Phone 88410 is too short", "Imported without a phone", "wait"],
  ["Pending complaints", 3, "Phone 996394502 has 9 digits", "Imported without a phone", "wait"],
  ["Pending complaints", 7, "Status text 'material need to check'", "Status Material need to check", "ok"],
  ["Pending complaints", 9, "Technician 'ramu 02/02/26' in one cell", "Technician Ramu, visit dated 02-02-2026", "ok"],
  ["Pending complaints", 12, "Site 'NSL Textiles, Guntur' not saved yet", "New site created", "ok"],
  ["Material list", 18, "Code 'EIO 6006' looks like EIO6006", "Counted under EIO6006", "ok"],
  ["Material list", 41, "No quantity", "Item created with no opening stock", "wait"],
  ["Material list", 57, "Row is only a heading ('DRIVERS')", "Skipped", "alert"],
  ["Fresh / defective list", 22, "No item code", "Skipped, check the sheet", "alert"]];
ROUTES.import = () => {
  setHeader("Setup", `${icon("file-import")} Import old Excel data`, adminOnly());
  const tone = { ok: "st-ok", wait: "st-wait", alert: "st-alert" }, word = { ok: "Cleaned", wait: "Imported with a gap", alert: "Skipped" };
  view().innerHTML = `${suggestBox(`A one-time import of the sheets used before this app. Every row goes through the same checks as the forms. First the app checks the files and shows a report; <b>nothing is saved until you press Import</b>.`)}
    <div class="card mt-3"><div class="card-header"><h3 class="card-title">${icon("files")} 1. Choose the files</h3></div><div class="card-body"><div class="row g-3">
      ${IMPORT_FILES.map(([id, label, name, what]) => fcol(4, lbl(id, label, false) + `<input id="${id}" type="file" accept=".xlsx" class="form-control">
        <small class="form-hint">${what}. Demo: <span class="code small">${name}</span></small>`)).join("")}</div></div>
      <div class="card-footer d-flex"><button class="btn btn-primary ms-auto" onclick="importStep='report';route()">${icon("list-search")} Check the files</button></div></div>
    ${importStep === "pick" ? "" : `<div class="card mt-3"><div class="card-header"><h3 class="card-title">${icon("report")} 2. Report</h3></div>
      <div class="card-body"><div class="row row-cards">
        ${kpiTile("box", "brand", 31, "Items", "29 ready · 1 cleaned · 1 skipped", "#import", "col-6 col-lg-3")}
        ${kpiTile("building", "brand", 18, "Sites", "16 ready · 2 new from complaints", "#import", "col-6 col-lg-3")}
        ${kpiTile("message-report", "brand", 30, "Past complaints", "26 ready · 4 with gaps", "#import", "col-6 col-lg-3")}
        ${kpiTile("recycle", "wait", 41, "Defective pieces", "40 ready · 1 skipped", "#import", "col-6 col-lg-3")}</div></div>
      ${dataTable("imp", { rows: IMPORT_ISSUES.map(([sheet, row, problem, action, t]) => ({ sheet, row, problem, action, t })), sort: "sheet", paging: false, columns: [
        { key: "sheet", label: "Sheet" }, { key: "row", label: "Row", num: true }, { key: "problem", label: "What we found", cls: "cell-wrap" },
        { key: "action", label: "What the import does", cls: "cell-wrap" }, { key: "t", label: "", html: r => `<span class="badge st ${tone[r.t]}">${word[r.t]}</span>` }] })}
      <div class="card-footer d-flex flex-wrap gap-2 align-items-center"><span class="text-secondary small">${icon("info-circle")} Skipped rows are listed so you can fix the sheet and run it again.</span>
        <button class="btn btn-primary ms-auto" onclick="importStep='pick';toastAfterNav('Mockup: imported 31 items, 18 sites, 30 past complaints and 40 pieces.');go('#dash')">${icon("file-import")} Import</button></div></div>`}`;
};

/* ---------- sidebar badges ---------- */
function smartBadges() {
  const t = document.getElementById("nav-today"); if (t) t.textContent = todayCount() || "";
  const d = document.getElementById("nav-drafts"); if (d) d.textContent = SMART.drafts.filter(x => x.status === "New").length || "";
}
