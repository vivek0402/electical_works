/* Complaints screens: dashboard, list, new complaint (+ new site modal), complaint detail (timeline, visits, status
   actions), record visit, sites, site card, technicians. */

const kpiTile = (ic, color, value, label, sub, href, cls = "col-6 col-md-4 col-xl-2") => `<div class="${cls}"><a class="card card-sm card-link h-100" href="${href}">
  <div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar kpi-${color}">${icon(ic)}</span>
  <div class="min-w-0"><div class="font-weight-medium fs-2 lh-1">${value}</div><div class="text-secondary small mt-1">${label}</div>${sub ? `<div class="small text-secondary">${sub}</div>` : ""}</div></div></div></a></div>`;
const factRow = (k, v) => v ? `<div class="datagrid-item"><div class="datagrid-title">${k}</div><div class="datagrid-content">${v}</div></div>` : "";
const cLink = no => `<a class="code" href="#complaint/${no}">${no}</a>`;
const tagLink = t => `<a class="code" href="#piece/${t}">${t}</a>`;
const siteLink = c => { const s = site(c.site); return s ? `<a href="#site/${s.id}">${esc(s.name)}</a>` : "?"; };
// Lateness is shown by the Due chip (smart.js: due date per priority, paused while awaiting material); age is plain days.
const ageHtml = c => `${ageDays(c)} d`;
// Bar list: one hue (brand blue), value labels, red only when the row means "needs attention".
const barList = (rows, href) => { const max = Math.max(1, ...rows.map(r => r[1]));
  return `<div class="list-group list-group-flush">${rows.map(([label, n, alert, key]) => `<a class="list-group-item list-group-item-action py-2" href="${href(key ?? label)}">
    <div class="d-flex align-items-center gap-2 mb-1"><span class="${alert ? "text-danger fw-medium" : ""}">${alert ? icon("alert-triangle", "me-1") : ""}${esc(label)}</span>
      <span class="ms-auto fw-bold num">${n}</span></div>
    <div class="progress progress-sm"><div class="progress-bar ${alert ? "bg-red" : "bar-brand"}" style="width:${(n / max) * 100}%"></div></div></a>`).join("")
    || `<div class="list-group-item text-secondary">Nothing open.</div>`}</div>`; };

/* ---------- complaints dashboard ---------- */
ROUTES.cdash = () => {
  const open = DB.complaints.filter(isOpen);
  const count = s => DB.complaints.filter(c => c.status === s).length;
  const closed30 = DB.complaints.filter(c => !isOpen(c) && c.closedOn >= addDays(today(), -30)).length;
  setHeader("Complaints", "Complaints dashboard", `<a href="#complaint-new" class="btn btn-primary">${icon("plus")} New complaint</a>
    ${exportBtn("Pending_Complaints.xlsx", "Pending complaints")}`);
  const by = f => { const t = {}; for (const c of open) t[f(c)] = (t[f(c)] || 0) + 1; return Object.entries(t).sort((a, b) => b[1] - a[1]); };
  const oldest = open.slice().sort((a, b) => ageDays(b) - ageDays(a)).slice(0, 6);
  view().innerHTML = `<div class="row row-deck row-cards">
    ${kpiTile(CSTYLE.NOT_ATTENDED[1], count("NOT_ATTENDED") ? "alert" : "brand", count("NOT_ATTENDED"), "Not attended", "", "#complaints/NOT_ATTENDED")}
    ${kpiTile(CSTYLE.ATTENDED[1], "brand", count("ATTENDED"), "Attended", "", "#complaints/ATTENDED")}
    ${kpiTile(CSTYLE.MATERIAL_CHECK[1], "brand", count("MATERIAL_CHECK"), "Material need to check", "", "#complaints/MATERIAL_CHECK")}
    ${kpiTile(CSTYLE.AWAITING_MATERIAL[1], count("AWAITING_MATERIAL") ? "wait" : "brand", count("AWAITING_MATERIAL"), "Awaiting material", "", "#complaints/AWAITING_MATERIAL")}
    ${kpiTile(CSTYLE.RESOLVED[1], "brand", count("RESOLVED"), "Resolved", "to be closed", "#complaints/RESOLVED")}
    ${kpiTile("lock", "brand", closed30, "Closed / not covered", "last 30 days", "#complaints/CLOSED")}
    <div class="col-lg-4"><div class="card"><div class="card-header"><div><h3 class="card-title">Open complaints by age</h3>
      <div class="card-subtitle">${open.length} open · days since reported</div></div></div>
      ${barList(AGE_BUCKETS.map(([k, label]) => [label, open.filter(c => ageBucket(ageDays(c)) === k).length, k === "15+", k]), k => `#complaints/age=${k}`)}</div></div>
    <div class="col-lg-8"><div class="card"><div class="card-header"><h3 class="card-title">Oldest open complaints</h3>
      <div class="card-actions"><a href="#complaints/open" class="btn btn-sm btn-outline-primary">All open ${icon("arrow-right")}</a></div></div>
      ${dataTable("oldest", { rows: oldest, paging: false, sort: "age", dir: "desc", columns: [
        { key: "no", label: "Complaint", html: c => cLink(c.no) },
        { key: "site", label: "Site", sort: siteName, html: c => `${siteLink(c)}<div class="small text-secondary">${esc(siteCity(c))}</div>` },
        { key: "company", label: "Company" }, { key: "status", label: "Status", sort: c => CSTATUS[c.status], html: c => cBadge(c.status) },
        { key: "age", label: "Age", num: true, sort: ageDays, html: ageHtml }] })}</div></div>
    <div class="col-md-6"><div class="card"><div class="card-header"><h3 class="card-title">Open by company</h3></div>
      ${barList(by(c => c.company).map(([k, n]) => [k, n]), k => `#complaints/company=${encodeURIComponent(k)}`)}</div></div>
    <div class="col-md-6"><div class="card"><div class="card-header"><h3 class="card-title">Open by city</h3></div>
      ${barList(by(siteCity).map(([k, n]) => [k, n]), k => `#complaints/city=${encodeURIComponent(k)}`)}</div></div>
  </div>`;
};

/* ---------- complaints list ---------- */
let cf = { tab: "open", company: "", city: "", tech: "", age: "", q: "" };
const C_TABS = [["open", "Open"], ...OPEN_STATUSES.map(s => [s, CSTATUS[s]]), ["CLOSED", "Closed"], ["NOT_COVERED", "Not covered"], ["all", "All"]];
ROUTES.complaints = arg => {
  if (arg !== undefined) {
    cf = { tab: "open", company: "", city: "", tech: "", age: "", q: "" };
    if (arg.includes("=")) { const [k, v] = arg.split("="); cf[k] = v; } else cf.tab = arg;
    resetPage("complaints");
  }
  const q = cf.q.trim().toUpperCase();
  const base = DB.complaints.filter(c => (!cf.company || c.company === cf.company) && (!cf.city || siteCity(c) === cf.city)
    && (!cf.tech || c.techs.includes(cf.tech)) && (!cf.age || ageBucket(ageDays(c)) === cf.age)
    && (!q || [c.no, c.companyRef, siteName(c), c.fault].join(" ").toUpperCase().includes(q)));
  const inTab = (c, t) => t === "all" || (t === "open" ? isOpen(c) : c.status === t);
  const rows = base.filter(c => inTab(c, cf.tab));
  const set = k => `cf.${k}=this.value;resetPage('complaints');route()`;
  setHeader("Complaints", "All complaints", `<a href="#complaint-new" class="btn btn-primary">${icon("plus")} New complaint</a>${exportBtn("Complaint_List.xlsx")}`);
  view().innerHTML = `<div class="card">
    <div class="card-header pb-0 border-0"><ul class="nav nav-tabs card-header-tabs status-tabs mb-0" role="tablist">${C_TABS.map(([k, l]) =>
      `<li class="nav-item"><a href="#" class="nav-link ${cf.tab === k ? "active" : ""}" onclick="cf.tab='${k}';resetPage('complaints');route();return false">${l}
        <span class="badge ${cf.tab === k ? "bg-primary text-white" : "bg-secondary-lt"} ms-1">${base.filter(c => inTab(c, k)).length}</span></a></li>`).join("")}</ul></div>
    <div class="card-body border-bottom py-3"><div class="row g-2 align-items-end">
      ${filterCol(2, fsel("Company", set("company"), DB.companies, cf.company, "All companies"))}
      ${filterCol(2, fsel("City", set("city"), cities(), cf.city, "All cities"))}
      ${filterCol(2, fsel("Technician", set("tech"), DB.techs.map(t => t.name), cf.tech, "Anyone"))}
      ${filterCol(2, fsel("Age", set("age"), AGE_BUCKETS.map(([k, l]) => [k, l]), cf.age, "Any age"))}
      ${filterCol(4, fsearch(cf.q, set("q"), "Complaint no., company ref, site, fault"))}</div></div>
    ${dataTable("complaints", { rows, sort: "reported", dir: "desc", empty: "No complaints match these filters.", columns: [
      { key: "no", label: "Complaint", html: c => cLink(c.no) },
      { key: "reported", label: "Reported", cls: "nowrap", sort: c => c.reportedOn + c.no, html: c => fmt(c.reportedOn) },
      { key: "site", label: "Site", sort: siteName, html: c => `${siteLink(c)}<div class="small text-secondary">${esc(siteCity(c))}</div>` },
      { key: "company", label: "Company", html: c => `${esc(c.company)}${c.companyRef ? `<div class="small text-secondary code">${esc(c.companyRef)}</div>` : ""}` },
      { key: "fault", label: "Fault", cls: "cell-wrap", html: c => esc(c.fault) + (c.qty ? ` <span class="text-secondary">(${c.qty})</span>` : "") },
      { key: "techs", label: "Technicians", sort: c => c.techs.join(), html: c => esc(c.techs.join(", ")) || `<span class="text-secondary">Not assigned</span>` },
      { key: "status", label: "Status · priority", sort: c => Object.keys(CSTATUS).indexOf(c.status),
        html: c => `${cBadge(c.status)}${c.priority !== "Normal" ? `<div class="mt-1">${prioBadge(c.priority)}</div>` : ""}` },
      { key: "due", label: "Due", cls: "nowrap", sort: dueSort, html: c => `${dueChip(c)}<div class="small text-secondary mt-1">${ageHtml(c)} old</div>` }] })}
  </div><p class="text-secondary small mt-2">${icon("info-circle")} Due = working days allowed for the priority (Urgent ${SMART.due.Urgent}, High ${SMART.due.High}, Normal ${SMART.due.Normal}; set in Smart settings). Time in Awaiting material, Sundays and holidays don't count. Age = calendar days since reported.</p>`;
};

/* ---------- new site modal (also used from the Sites page) ---------- */
function openSiteModal(name, done) {
  window._siteDone = done;
  openModal(`<div class="modal-header"><h5 class="modal-title">${icon("building")} New site</h5>
      <button type="button" class="btn-close" aria-label="Close" onclick="closeModal();window._siteDone(null)"></button></div>
    <div class="modal-body"><div class="row g-3">
      ${fcol(8, lbl("ns-name", "Site name") + `<input id="ns-name" class="form-control" value="${esc(name || "")}" placeholder="e.g. Andhra University">`)}
      ${fcol(4, lbl("ns-city", "City") + `<input id="ns-city" class="form-control" list="ns-cities" placeholder="e.g. Visakhapatnam"><datalist id="ns-cities">${opt(cities())}</datalist>`)}
      ${fcol(6, lbl("ns-contact", "Contact person", false) + `<input id="ns-contact" class="form-control" placeholder="Name at the site">`)}
      ${fcol(6, lbl("ns-phone", "Phone", false) + `<input id="ns-phone" type="tel" inputmode="tel" maxlength="13" class="form-control" placeholder="10-digit mobile or STD landline">`)}
      ${fcol(12, lbl("ns-address", "Address", false) + `<textarea id="ns-address" class="form-control" rows="2" placeholder="Optional"></textarea>`)}
    </div><div id="ns-dup" class="mt-3"></div><div id="ns-err" class="mt-3"></div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" onclick="closeModal();window._siteDone(null)">Cancel</button>
      <button type="button" class="btn btn-primary ms-auto" id="ns-save" onclick="saveSiteModal()">${icon("check")} Save site</button></div>`, "modal-lg");
  ["ns-name", "ns-city", "ns-phone"].forEach(id => field(id).addEventListener("input", siteDupCheck));
  siteDupCheck();
  setTimeout(() => field(name ? "ns-city" : "ns-name").focus(), 300);
}
function saveSiteModal() {
  const r = saveSite({ name: field("ns-name").value, city: field("ns-city").value, contact: field("ns-contact").value, phone: field("ns-phone").value, address: field("ns-address").value });
  if (r.error) { field("ns-err").innerHTML = `<div class="alert alert-danger mb-0">${icon("alert-circle")}${esc(r.error)}</div>`; return; }
  closeModal(); toast(`Site <b>${esc(r.site.name)}</b> added.`); window._siteDone(r.site);
}

/* ---------- new complaint ---------- */
const siteOpt = s => ({ id: s.id, name: s.name, city: s.city, contact: s.contact, hay: `${s.name} ${s.city} ${s.contact}` });
let cSite = null, cCompany = null, cTechs = null;
ROUTES["complaint-new"] = siteId => {
  setHeader("Complaints", `${icon("message-report")} New complaint`);
  const def = DB.config.defaultCompany;
  view().innerHTML = `<form id="c-form" novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveComplaint()">
    <div class="card mb-3"><div class="card-header"><h3 class="card-title">${icon("building")} Site</h3>
      <div class="card-subtitle ms-2 text-secondary">Where the problem is</div></div><div class="card-body"><div class="row g-3">
      ${fcol(6, lbl("c-site", "Site") + `<select id="c-site"></select><small class="form-hint">Type to search saved sites, or add a new one.</small>`)}
      ${fcol(3, lbl("c-contact", "Contact person", false) + `<input id="c-contact" class="form-control" placeholder="Filled from the site">`)}
      ${fcol(3, lbl("c-phone", "Phone", false) + `<input id="c-phone" type="tel" inputmode="tel" maxlength="13" class="form-control" placeholder="10-digit mobile or STD landline">`)}
      <div class="col-12 mt-1"><button type="button" class="btn btn-quiet btn-sm" onclick="openSiteModal('', s => { if (s) { cSite.addOption(siteOpt(s)); cSite.setValue(s.id); } })">${icon("plus")} New site</button>
        <span class="small text-secondary ms-2">Contact and phone are copied from the site; change them here for this complaint only.</span></div>
    </div></div></div>
    <div class="card mb-3"><div class="card-header"><h3 class="card-title">${icon("file-description")} Complaint</h3></div><div class="card-body"><div class="row g-3">
      ${fcol(4, lbl("c-company", "Company (whose product failed)") + `<select id="c-company" data-master="companies" data-noun="company">${opt(DB.companies, def)}</select>
        <small class="form-hint">Default from Setup: ${esc(def)}. Change it for other companies' products.</small>`)}
      ${fcol(4, lbl("c-ref", "Company complaint no.", false) + `<input id="c-ref" class="form-control" placeholder="The company's ticket no., if any">`)}
      ${fcol(2, lbl("c-date", "Reported on") + `<input id="c-date" type="date" class="form-control" value="${today()}" max="${today()}">`)}
      ${fcol(2, lbl("c-qty", "Qty affected", false) + `<input id="c-qty" type="number" min="1" step="1" inputmode="numeric" class="form-control" placeholder="e.g. 6">`)}
      ${fcol(12, lbl("c-fault", "Fault") + `<textarea id="c-fault" class="form-control" rows="2" placeholder="e.g. 6 linear fittings flickering on the 2nd floor"></textarea>`)}
      ${fcol(5, lbl("", "Priority") + selectgroup("prio", PRIORITIES.map(p => [p, p, p === "Urgent" ? "urgent" : p === "High" ? "arrow-up" : "minus"]), "Normal", ""))}
      ${fcol(7, lbl("c-techs", "Technicians", false) + `<select id="c-techs" multiple placeholder="Assign now or later">${opt(activeTechs())}</select>`)}
    </div></div>
    <div class="card-footer d-flex flex-wrap align-items-center gap-2"><span class="text-secondary small">${icon("info-circle")} Saved as <b>Not attended</b>. Every status change is logged.</span>
      <div class="ms-auto btn-list"><a href="#complaints" class="btn btn-link link-secondary">Cancel</a>
      <button type="submit" class="btn btn-primary">${icon("device-floppy")} Save complaint</button></div></div></div>
    <div id="form-error" class="mt-3"></div></form>`;
  cSite = new TomSelect("#c-site", {
    options: DB.sites.filter(s => s.active).map(siteOpt), valueField: "id", labelField: "name", searchField: ["hay"], maxOptions: 50,
    placeholder: "Type site name, city or contact…", closeAfterSelect: true,
    create: (input, cb) => openSiteModal(input, s => cb(s ? siteOpt(s) : false)),
    render: { option: d => `<div><span class="fw-medium">${esc(d.name)}</span><span class="opt-meta">${esc(d.city)}${d.contact ? " · " + esc(d.contact) : ""}</span></div>`,
      item: d => `<div>${esc(d.name)}, ${esc(d.city)}</div>`,
      option_create: d => `<div class="create">＋ New site <b>${esc(d.input)}</b>…</div>`, no_results: () => `<div class="no-results">No saved site. Keep typing to add it.</div>` },
    onChange: v => { const s = site(v); if (s) { field("c-contact").value = s.contact; field("c-phone").value = s.phone; } clearFormError(); },
  });
  cCompany = masterPicker(field("c-company"));
  cTechs = new TomSelect("#c-techs", { plugins: ["remove_button"], maxOptions: 50, render: { option: techOption } });
  if (siteId && site(siteId)) cSite.setValue(Number(siteId));
};
function saveComplaint() {
  const qv = field("c-qty").value.trim();
  const r = fileComplaint({ site: Number(cSite.getValue()) || null, company: cCompany.getValue(), companyRef: field("c-ref").value, fault: field("c-fault").value,
    qty: qv === "" ? null : Number(qv), reportedOn: field("c-date").value, priority: radioVal("prio"), techs: cTechs.getValue(),
    contact: field("c-contact").value, phone: field("c-phone").value });
  if (r.error) {
    formFail(r.error, ["c-fault", "c-date", "c-qty"].includes(r.focus) ? r.focus : null);
    if (r.focus === "site") cSite.focus(); if (r.focus === "company") cCompany.focus();
    return;
  }
  smartAfterComplaint(r.complaint);
  toastAfterNav(`Complaint <b>${r.complaint.no}</b> filed for ${esc(siteName(r.complaint))}.`);
  go(`#complaint/${r.complaint.no}`);
}

/* ---------- complaint detail ---------- */
ROUTES.complaint = no => {
  const c = complaint(no);
  if (!c) { setHeader("Complaints", "Complaint not found"); view().innerHTML = ""; return; }
  const s = site(c.site), open = isOpen(c), aw = awaitingDays(c);
  setHeader(`Complaint · ${esc(c.company)}`, `<span class="code">${c.no}</span> ${cBadge(c.status)}`,
    (open ? `<a href="#visit/${c.no}" class="btn btn-primary">${icon("clipboard-plus")} Record visit</a>` : "")
    + (c.status !== "NOT_COVERED" ? `<button class="btn btn-quiet" onclick="askStatus('${c.no}')">${icon("arrows-right-left")} Change status</button>` : "")
    + (open ? `<button class="btn btn-quiet" onclick="askNotCovered('${c.no}')">${icon("ban")} Close as Not covered</button>` : ""));
  const visits = DB.visits.filter(v => v.complaint === c.no);
  const ev = cEvents(c.no).slice().reverse();
  view().innerHTML = `<div class="row row-cards">
    <div class="col-12"><div class="d-flex flex-wrap gap-2">
      <span class="chip">${icon("calendar")} Reported ${fmt(c.reportedOn)}</span>
      <span class="chip">${icon("clock")} Age <b>${ageDays(c)}</b> days${c.closedOn ? ` (closed ${fmt(c.closedOn)})` : ""}</span>
      <span class="chip ${c.status === "AWAITING_MATERIAL" ? "chip-wait" : ""}">${icon("hourglass")} Awaiting material <b>${aw}</b> days</span>
      ${c.priority !== "Normal" ? prioBadge(c.priority) : ""}
      ${c.notCoveredReason ? `<span class="chip">${icon("ban")} Not covered: <b>${esc(c.notCoveredReason)}</b></span>` : ""}</div></div>
    <div class="col-lg-8"><div class="card mb-3"><div class="card-header"><h3 class="card-title">Details</h3></div><div class="card-body"><div class="datagrid">
      ${factRow("Site", `<a href="#site/${s.id}">${esc(s.name)}</a>`)}${factRow("City", esc(s.city))}
      ${factRow("Contact", esc(c.contact) || "—")}${factRow("Phone", c.phone ? `<a href="tel:${esc(c.phone)}">${esc(c.phone)}</a>` : "—")}
      ${factRow("Company", esc(c.company))}${factRow("Company complaint no.", c.companyRef ? `<span class="code">${esc(c.companyRef)}</span>` : "—")}
      ${factRow("Qty affected", c.qty ?? "—")}${factRow("Priority", c.priority)}
      ${factRow("Technicians", esc(c.techs.join(", ")) || "Not assigned")}
      </div><div class="mt-3"><div class="datagrid-title">Fault</div><div>${esc(c.fault)}</div></div></div></div></div>
    <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">${icon("timeline")} Status timeline</h3></div>
      <div class="card-body"><ul class="tl">${ev.map(e => `<li class="tl-item"><span class="tl-dot ${CSTYLE[e.to][0]}">${icon(CSTYLE[e.to][1])}</span>
        <div class="tl-body"><div class="fw-medium">${e.from ? `${CSTATUS[e.from]} → ` : ""}${CSTATUS[e.to]}</div>
        <div class="small text-secondary">${fmt(e.at)} · ${esc(e.by)}</div>
        ${e.reason ? `<div class="small">Reason: <b>${esc(e.reason)}</b></div>` : ""}${e.note ? `<div class="small">${esc(e.note)}</div>` : ""}</div></li>`).join("")}</ul></div></div></div>
    <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">${icon("clipboard-list")} Visits</h3><span class="badge bg-secondary-lt ms-2">${visits.length}</span>
        ${open ? `<div class="card-actions"><a href="#visit/${c.no}" class="btn btn-sm btn-outline-primary">${icon("plus")} Record visit</a></div>` : ""}</div>
      ${dataTable("visits", { rows: visits, paging: false, sort: "date", dir: "desc", empty: "No visits yet.", columns: [
        { key: "date", label: "Visit", sort: v => v.date + v.no, html: v => `<span class="code">${v.no}</span><div class="small text-secondary nowrap">${fmt(v.date)}</div>` },
        { key: "techs", label: "Technicians", sort: v => v.techs.join(), html: v => esc(v.techs.join(", ")) },
        { key: "work", label: "Work done", cls: "cell-wrap", html: v => esc(v.work) },
        { key: "parts", label: "Parts given", nosort: true, html: v => { const e = v.outEntry && entry(v.outEntry);
          return e ? `${entryLink(e.no)}${undoneBy(e.no) ? ` <span class="badge bg-secondary-lt">undone</span>` : ""}<div class="small">${e.lines.map(l => `<span class="code">${esc(l.code)}</span> × ${-l.qty}`).join("<br>")}</div>`
            : `<span class="text-secondary">None</span>`; } },
        { key: "tags", label: "Failed parts collected", nosort: true, html: v => v.tags.length ? `<div class="tag-list">${v.tags.map(t =>
          `<span class="nowrap">${tagLink(t)} <span class="small text-secondary">${esc(piece(t).code)}</span></span>`).join("<br>")}</div>` : `<span class="text-secondary">None</span>` },
        { key: "next", label: "Status after", sort: v => v.nextStatus, html: v => cBadge(v.nextStatus) }] })}</div></div>
  </div>`;
};
function statusModal(title, body, footer) {
  openModal(`<div class="modal-header"><h5 class="modal-title">${title}</h5><button type="button" class="btn-close" aria-label="Close" onclick="closeModal()"></button></div>
    <div class="modal-body">${body}<div id="st-err" class="mt-3"></div></div><div class="modal-footer">${footer}</div>`);
}
const stErr = msg => { field("st-err").innerHTML = `<div class="alert alert-danger mb-0" role="alert">${icon("alert-circle")}${esc(msg)}</div>`; };
function askStatus(no) {
  const c = complaint(no), next = TRANSITIONS[c.status].filter(s => s !== "NOT_COVERED");
  const note = `<label class="form-label mt-3" for="st-note">Note</label><textarea id="st-note" class="form-control" rows="2" placeholder="Optional: what happened"></textarea>`;
  if (!next.length) {
    statusModal(`${icon("lock")} ${c.no} is ${CSTATUS[c.status]}`, `<p class="text-secondary mb-0">A closed complaint is final. Only Admin can reopen it; reopening moves it back to <b>Attended</b> and is logged.</p>${note}`,
      `<button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
       <button type="button" class="btn btn-outline-danger ms-auto" onclick="doStatus('${no}','ATTENDED')">${icon("arrow-back-up")} Reopen (move to Attended)</button>`);
    return;
  }
  statusModal(`${icon("arrows-right-left")} Change status of ${c.no}`, `<div class="mb-2 text-secondary">Now: ${cBadge(c.status)}. Only the moves allowed from here are offered.</div>
    <div class="form-selectgroup form-selectgroup-boxes d-flex flex-column gap-2">${next.map((s, i) => `<label class="form-selectgroup-item flex-fill">
      <input type="radio" name="st-to" value="${s}" class="form-selectgroup-input" ${i === 0 ? "checked" : ""}>
      <div class="form-selectgroup-label d-flex align-items-center p-2"><span class="form-selectgroup-check me-2"></span>${cBadge(s)}</div></label>`).join("")}</div>${note}`,
    `<button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
     <button type="button" class="btn btn-primary ms-auto" onclick="doStatus('${no}', radioVal('st-to'))">${icon("check")} Change status</button>`);
}
function doStatus(no, to) {
  const c = complaint(no), from = c.status, err = changeStatus(c, to, field("st-note").value);
  if (err) return stErr(err);
  closeModal(); toastAfterNav(`${no}: ${CSTATUS[from]} → <b>${CSTATUS[to]}</b>.`); route();
}
function askNotCovered(no) {
  const c = complaint(no);
  statusModal(`${icon("ban")} Close ${c.no} as Not covered`, `<p class="text-secondary">Use this when the job isn't ours to do. It can be done from any open status and is logged.</p>
    <label class="form-label required" for="nc-reason">Reason</label><select id="nc-reason" class="form-select"><option value="">Choose…</option>${opt(DB.notCoveredReasons)}</select>
    <label class="form-label mt-3" for="st-note">Note</label><textarea id="st-note" class="form-control" rows="2" placeholder="Required when the reason is Other"></textarea>`,
    `<button type="button" class="btn btn-link link-secondary" onclick="closeModal()">Cancel</button>
     <button type="button" class="btn btn-danger ms-auto" onclick="doNotCovered('${no}')">${icon("ban")} Close as Not covered</button>`);
}
function doNotCovered(no) {
  const c = complaint(no), err = changeStatus(c, "NOT_COVERED", field("st-note").value, field("nc-reason").value);
  if (err) return stErr(err);
  closeModal(); toastAfterNav(`${no} closed as <b>Not covered</b> (${esc(c.notCoveredReason)}).`); route();
}

/* ---------- record visit (the key daily action) ---------- */
let visitParts = null, visitCollect = null, vTechs = null;
ROUTES.visit = no => {
  const c = complaint(no);
  if (!c) { setHeader("Complaints", "Complaint not found"); view().innerHTML = ""; return; }
  setHeader(`Complaint ${c.no} · ${esc(siteName(c))}, ${esc(siteCity(c))}`, `${icon("clipboard-plus")} Record visit`);
  if (!isOpen(c)) { view().innerHTML = `<div class="alert alert-warning">${icon("lock")} ${c.no} is ${CSTATUS[c.status]}, so visits can't be added. <a href="#complaint/${c.no}">Back to the complaint</a></div>`; return; }
  const nexts = visitNextOptions(c), defNext = c.status === "NOT_ATTENDED" ? "ATTENDED" : c.status;
  view().innerHTML = `<form id="v-form" novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveVisit('${c.no}')">
    <div class="card mb-3"><div class="card-body py-2 d-flex flex-wrap align-items-center gap-2">${cBadge(c.status)}
      <span class="fw-medium">${esc(c.fault)}</span><span class="text-secondary">· ${esc(c.company)} · reported ${fmt(c.reportedOn)}</span></div></div>
    <div class="card mb-3"><div class="card-header"><h3 class="card-title">${icon("calendar-event")} Visit</h3></div><div class="card-body"><div class="row g-3">
      ${fcol(3, lbl("v-date", "Visit date") + `<div class="input-icon"><span class="input-icon-addon">${icon("calendar")}</span>
        <input id="v-date" type="date" class="form-control" value="${today()}" min="${c.reportedOn}" max="${today()}"></div>`)}
      ${fcol(9, lbl("v-techs", "Technicians who attended") + `<select id="v-techs" multiple>${opt(activeTechs())}</select>`)}
      ${fcol(12, lbl("v-work", "Work done") + `<textarea id="v-work" class="form-control" rows="2" placeholder="e.g. Changed 2 drivers, 4 fittings still to check"></textarea>`)}
    </div></div></div>
    <div class="card mb-3"><div class="card-header flex-wrap gap-2"><h3 class="card-title">${icon("package-export", "text-out")} Parts given</h3>
      <div class="card-subtitle ms-2 text-secondary">Posts a Stock OUT from the location. Leave empty if no parts were given.</div></div>
      <div class="card-body"><div class="row g-3 mb-3">${fcol(3, lbl("v-loc", "From location") + `<select id="v-loc" class="form-select" onchange="visitParts.refreshAll()">${opt(DB.locations, "Vizag Office")}</select>`)}</div>
        <div id="v-parts"></div></div><div class="card-footer text-secondary" id="parts-summary"></div></div>
    <div class="card mb-3"><div class="card-header flex-wrap gap-2"><h3 class="card-title">${icon("recycle")} Failed parts collected</h3>
      <div class="card-subtitle ms-2 text-secondary">Each piece gets its own tag (quantity 3 = 3 tags) and goes to the Defective store, not good stock.</div></div>
      <div class="card-body"><div id="v-collect"></div></div><div class="card-footer text-secondary" id="collect-summary"></div></div>
    <div class="card"><div class="card-header"><h3 class="card-title">${icon("flag")} Status after this visit</h3></div>
      <div class="card-body">${selectgroup("v-next", nexts.map(s => [s, CSTATUS[s], CSTYLE[s][1]]), defNext, "")}
        ${c.status === "NOT_ATTENDED" ? `<div class="form-hint mt-2">The first visit also logs Not attended → Attended.</div>` : ""}</div>
      <div class="card-footer d-flex flex-wrap align-items-center gap-2"><div class="ms-auto btn-list"><a href="#complaint/${c.no}" class="btn btn-link link-secondary">Cancel</a>
        <button type="submit" class="btn btn-primary">${icon("device-floppy")} Save visit</button></div></div></div>
    <div id="form-error" class="mt-3"></div></form>`;
  vTechs = new TomSelect("#v-techs", { plugins: ["remove_button"], maxOptions: 50, items: c.techs.filter(t => activeTechs().includes(t)) });
  visitParts = new Lines(field("v-parts"), "out", () => field("v-loc").value, { summaryId: "parts-summary", allowEmpty: true, addLabel: "Add another part" });
  visitParts.add();
  visitCollect = new Lines(field("v-collect"), "collect", null, { summaryId: "collect-summary", allowEmpty: true, addLabel: "Add another failed part" });
  visitCollect.add();
};
function saveVisit(no) {
  const c = complaint(no), parts = visitParts.collect(), col = visitCollect.collect();
  if (parts.error) return formFail("Parts given: " + parts.error);
  if (col.error) return formFail("Failed parts collected: " + col.error);
  const r = recordVisit(c, { date: field("v-date").value, techs: vTechs.getValue(), work: field("v-work").value, loc: field("v-loc").value,
    parts: parts.lines, collected: col.lines, next: radioVal("v-next") });
  if (r.error) { formFail(r.error, ["v-date", "v-work"].includes(r.focus) ? r.focus : null); if (r.focus === "v-techs") vTechs.focus(); return; }
  toastAfterNav(`Visit <b>${r.visit}</b> saved.${r.out ? ` Parts given: ${r.out.no}.` : ""}${r.tags.length ? ` New defective tags: <b>${r.tags.join(", ")}</b>.` : ""}`);
  go(`#complaint/${no}`);
}

/* ---------- sites ---------- */
let stf = { q: "", city: "" };
ROUTES.sites = () => {
  const q = stf.q.trim().toUpperCase();
  const rows = DB.sites.filter(s => (!stf.city || s.city === stf.city) && (!q || [s.name, s.city, s.contact, s.phone].join(" ").toUpperCase().includes(q)));
  const of = s => DB.complaints.filter(c => c.site === s.id);
  const set = k => `stf.${k}=this.value;resetPage('sites');route()`;
  setHeader("Complaints", "Sites", `<button class="btn btn-primary" onclick="openSiteModal('', s => { if (s) route(); })">${icon("plus")} Add site</button>`);
  view().innerHTML = `<div class="card"><div class="card-body border-bottom py-3"><div class="row g-2 align-items-end">
      ${filterCol(4, fsearch(stf.q, set("q"), "Site, city, contact, phone"))}${filterCol(3, fsel("City", set("city"), cities(), stf.city, "All cities"))}</div></div>
    ${dataTable("sites", { rows, sort: "name", columns: [
      { key: "name", label: "Site", html: s => `<a href="#site/${s.id}" class="fw-medium">${esc(s.name)}</a>` }, { key: "city", label: "City" },
      { key: "contact", label: "Contact" }, { key: "phone", label: "Phone", html: s => s.phone ? `<a href="tel:${esc(s.phone)}">${esc(s.phone)}</a>` : "" },
      { key: "open", label: "Open complaints", num: true, sort: s => of(s).filter(isOpen).length, html: s => { const n = of(s).filter(isOpen).length; return n ? `<b>${n}</b>` : qtyHtml(0); } },
      { key: "total", label: "All complaints", num: true, sort: s => of(s).length, html: s => of(s).length },
      { key: "last", label: "Last complaint", sort: s => of(s).map(c => c.reportedOn).sort().at(-1) || "", html: s => fmt(of(s).map(c => c.reportedOn).sort().at(-1) || "") }] })}</div>`;
};
ROUTES.site = id => {
  const s = site(id);
  if (!s) { setHeader("Sites", "Site not found"); view().innerHTML = ""; return; }
  const rows = DB.complaints.filter(c => c.site === s.id);
  setHeader(`Site · ${esc(s.city)}`, esc(s.name), `<a href="#complaint-new/${s.id}" class="btn btn-primary">${icon("plus")} New complaint for this site</a>`);
  view().innerHTML = `<div class="row row-cards"><div class="col-12"><div class="card"><div class="card-body"><div class="datagrid">
      ${factRow("City", esc(s.city))}${factRow("Contact", esc(s.contact) || "—")}${factRow("Phone", s.phone ? `<a href="tel:${esc(s.phone)}">${esc(s.phone)}</a>` : "—")}
      ${factRow("Address", esc(s.address) || "—")}${factRow("Open complaints", rows.filter(isOpen).length)}${factRow("All complaints", rows.length)}
      ${factRow("Status", s.active ? `<span class="badge st st-ok">${icon("check")}Active</span>` : `<span class="badge st st-done">Hidden</span>`)}</div></div></div></div>
    <div class="col-12"><div class="card"><div class="card-header"><h3 class="card-title">${icon("history")} Complaint history</h3></div>
      ${dataTable("site-hist", { rows, sort: "reported", dir: "desc", empty: "No complaints for this site yet.", columns: [
        { key: "no", label: "Complaint", html: c => cLink(c.no) }, { key: "reported", label: "Reported", sort: c => c.reportedOn, html: c => fmt(c.reportedOn) },
        { key: "company", label: "Company" }, { key: "fault", label: "Fault", cls: "cell-wrap" },
        { key: "visits", label: "Visits", num: true, sort: c => DB.visits.filter(v => v.complaint === c.no).length, html: c => DB.visits.filter(v => v.complaint === c.no).length },
        { key: "status", label: "Status", sort: c => c.status, html: c => cBadge(c.status) }, { key: "age", label: "Age", num: true, sort: ageDays, html: ageHtml }] })}</div></div></div>`;
};

/* ---------- technicians ---------- */
ROUTES.techs = () => {
  const assigned = t => DB.complaints.filter(c => isOpen(c) && c.techs.includes(t.name));
  const visits30 = t => DB.visits.filter(v => v.techs.includes(t.name) && v.date > addDays(today(), -30));
  setHeader("Complaints", "Technicians");
  view().innerHTML = `<div class="row row-cards"><div class="col-lg-8"><div class="card">
      ${dataTable("techs", { rows: DB.techs, sort: "name", paging: false, columns: [
        { key: "name", label: "Technician", html: t => `<span class="avatar avatar-xs bg-secondary-lt me-2">${esc(t.name.slice(0, 2).toUpperCase())}</span>${esc(t.name)}` },
        { key: "phone", label: "Phone", html: t => t.phone ? `<a href="tel:${esc(t.phone)}">${esc(t.phone)}</a>` : "" },
        { key: "open", label: "Open complaints", num: true, sort: t => assigned(t).length,
          html: t => assigned(t).length ? `<a href="#complaints/tech=${encodeURIComponent(t.name)}" class="fw-bold">${assigned(t).length}</a>` : qtyHtml(0) },
        { key: "visits", label: "Visits (30 days)", num: true, sort: t => visits30(t).length, html: t => visits30(t).length },
        { key: "last", label: "Last visit", sort: t => DB.visits.filter(v => v.techs.includes(t.name)).map(v => v.date).sort().at(-1) || "",
          html: t => fmt(DB.visits.filter(v => v.techs.includes(t.name)).map(v => v.date).sort().at(-1) || "") },
        { key: "active", label: "Status", sort: t => t.active, html: t => t.active ? `<span class="badge st st-ok">${icon("check")}Active</span>` : `<span class="badge st st-done">Hidden</span>` }] })}
    </div><p class="text-secondary small mt-2">${icon("info-circle")} Technicians don't log in. Office staff record their visits. Hiding a technician is Admin only.</p></div>
    <div class="col-lg-4"><div class="card"><div class="card-header"><h3 class="card-title">${icon("user-plus")} Add technician</h3></div>
      <form class="card-body" novalidate onsubmit="event.preventDefault();addTech()">
        <label class="form-label required" for="t-name">Name</label><input id="t-name" class="form-control mb-3" placeholder="e.g. Suresh">
        <label class="form-label" for="t-phone">Phone</label><input id="t-phone" type="tel" inputmode="numeric" maxlength="10" class="form-control mb-3" placeholder="10-digit mobile">
        <div id="t-err"></div><button class="btn btn-primary w-100">${icon("plus")} Add technician</button></form></div></div></div>`;
};
function addTech() {
  const err = saveTech(field("t-name").value, field("t-phone").value.trim());
  if (err) { field("t-err").innerHTML = `<div class="alert alert-danger">${icon("alert-circle")}${esc(err)}</div>`; return; }
  toastAfterNav(`Technician <b>${esc(field("t-name").value.trim())}</b> added.`); route();
}
