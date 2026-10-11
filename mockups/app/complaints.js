/* System ③ Complaint Filing & Tracking: file, assign, visits (issue parts + collect defectives), statuses, ageing. */

SUBNAV.cmp = () => isTech()
  ? [["#cmp/mine", "My complaints"], ["#cmp", "All complaints"]]
  : [["#cmp", "Complaints"], ["#cmp/new", "＋ New complaint"], ["#cmp/report", "AP Pending report"]];
const ticketLink = t => `<a class="code" href="#cmp/view/${t}">${t}</a>`;
const lastVisit = c => c.visits.length ? c.visits.at(-1).date : "";
const telLink = c => c.phone ? `<a href="tel:${esc(c.phone)}">${esc(c.phone)}</a>${phoneOk(c.phone) ? "" : ` <span class="warn" title="Not a valid 10-digit number">⚠</span>`}` : `<span class="muted">—</span>`;
const CITIES = ["Vizag", "Guntur", "Vijayawada", "Nellore", "Tirupati", "Gudivada", "Anantapur"];
const STEPS = ["NOT_ATTENDED", "ATTENDED", "MATERIAL_TO_CHECK", "AWAITING_MATERIAL", "RESOLVED", "CLOSED"];

/* ------------------------------ Complaint list ------------------------------ */
let cv = { tab: "OPEN", city: "", tech: "", q: "" };
ROUTES.cmp = () => {
  const q = norm(cv.q);
  const inTab = c => cv.tab === "OPEN" ? c.status !== "CLOSED" : c.status === cv.tab;
  const base = complaints.filter(c => (!cv.city || c.city === cv.city) && (!cv.tech || c.techs.includes(cv.tech)) &&
    (!q || c.ticket.includes(q) || norm(c.wipro).includes(q) || norm(c.customer).includes(q)));
  const list = base.filter(inTab).sort((a, b) => ageDays(b) - ageDays(a));
  const tabs = [["OPEN", "All open"], ...STEPS.map(s => [s, CMP_STATUS[s]])];
  view().innerHTML = `${flashHtml()}<h1>③ Complaints</h1>
    ${isTech() ? "" : `<div class="actions" style="margin-bottom:1rem"><a href="#cmp/new" role="button" class="btn-cmp">＋ New complaint</a>
      <a href="#cmp/report" role="button" class="secondary outline">AP Pending report</a></div>`}
    <div class="tabs">${tabs.map(([k, l]) => `<button class="small ${cv.tab === k ? "" : "secondary outline"}" onclick="cv.tab='${k}';route()">
      ${l} (${base.filter(c => k === "OPEN" ? c.status !== "CLOSED" : c.status === k).length})</button>`).join("")}</div>
    <div class="filters">
      <label>City <select onchange="cv.city=this.value;route()"><option value="">All cities</option>${opts(CITIES, cv.city)}</select></label>
      <label>Technician <select onchange="cv.tech=this.value;route()"><option value="">Anyone</option>${opts(TECHNICIANS, cv.tech)}</select></label>
      <label>Search <input type="search" value="${esc(cv.q)}" placeholder="ticket, Wipro no., customer" onchange="cv.q=this.value;route()"></label>
    </div>
    <div class="table-wrap"><table class="striped"><thead><tr><th>Ticket</th><th>Customer</th><th>City</th><th>Contact</th><th>Fault</th>
      <th>Status</th><th>Technicians</th><th>Last visit</th><th class="num">Age</th></tr></thead><tbody>
      ${list.map(c => `<tr><td>${ticketLink(c.ticket)}${c.wipro ? `<br><span class="muted">Wipro ${esc(c.wipro)}</span>` : ""}</td>
        <td>${esc(c.customer)}</td><td>${esc(c.city)}</td><td>${esc(c.contact)}<br>${telLink(c)}</td><td>${esc(c.fault)}</td>
        <td>${cmpBadge(c.status)}</td><td>${esc(c.techs.join(", ")) || `<span class="bad">unassigned</span>`}</td>
        <td>${lastVisit(c)}</td><td class="num">${ageBadge(ageDays(c))}</td></tr>`).join("") || `<tr><td colspan="9">No complaints here.</td></tr>`}
    </tbody></table></div>
    <p class="muted">Age = days since received, not counting days spent "Awaiting material". Colours: 0–2 · 3–7 · 8–15 · over 15 days.</p>`;
};

/* ------------------------------ New complaint ------------------------------ */
let nc = null;
ROUTES["cmp/new"] = () => {
  if (isTech()) return go("#cmp/mine");
  nc = nc || { wipro: "", customer: "", city: "Vizag", contact: "", phone: "", fault: "", qty: "", received: today(), priority: "Normal", techs: [] };
  view().innerHTML = `<h1>＋ New complaint</h1>
    <div class="fields">
      <label>Wipro complaint no. <small class="muted">(optional)</small><input value="${esc(nc.wipro)}" onchange="nc.wipro=this.value"></label>
      <label>Customer <input list="customers" value="${esc(nc.customer)}" placeholder="e.g. Laurus Labs Unit-2" onchange="nc.customer=this.value"></label>
      <label>City <select onchange="nc.city=this.value">${opts(CITIES, nc.city)}</select></label>
      <label>Site contact person <input value="${esc(nc.contact)}" onchange="nc.contact=this.value"></label>
      <label>Contact phone <input value="${esc(nc.phone)}" inputmode="tel" placeholder="10-digit mobile or landline"
        oninput="nc.phone=this.value;document.getElementById('ph-warn').innerHTML=this.value&&!phoneOk(this.value)?'⚠ Not a valid 10-digit Indian number. You can still save.':''">
        <small id="ph-warn" class="warn">${nc.phone && !phoneOk(nc.phone) ? "⚠ Not a valid 10-digit Indian number. You can still save." : ""}</small></label>
      <label>Date received <input value="${nc.received}" onchange="nc.received=this.value"></label>
      <label>Priority <select onchange="nc.priority=this.value">${opts(["Normal", "High", "Urgent"], nc.priority)}</select></label>
      <label>Qty affected <input type="number" min="0" value="${esc(nc.qty)}" onchange="nc.qty=this.value"></label>
    </div>
    <label>Fault / product description <textarea rows="2" placeholder="e.g. 15W drivers 18 NOS not working" onchange="nc.fault=this.value">${esc(nc.fault)}</textarea></label>
    <fieldset><legend>Assign technicians</legend><div class="checks">${TECHNICIANS.map(t => `<label><input type="checkbox" ${nc.techs.includes(t) ? "checked" : ""}
      onchange="nc.techs=this.checked?[...nc.techs,'${t}']:nc.techs.filter(x=>x!=='${t}')"> ${t}</label>`).join("")}</div></fieldset>
    <datalist id="customers">${uniq(complaints.map(c => c.customer)).map(c => `<option value="${esc(c)}">`).join("")}</datalist>
    <div id="nc-error"></div>
    <div class="actions"><button class="btn-cmp" onclick="ncSave()">File complaint</button><a href="#cmp" role="button" class="secondary outline">Cancel</a></div>`;
};
function ncSave() {
  if (!nc.customer.trim()) return formError("nc-error", "Enter the customer.");
  if (!nc.fault.trim()) return formError("nc-error", "Describe the fault.");
  if (!/^\d{2}-\d{2}-\d{4}$/.test(nc.received)) return formError("nc-error", "Date received must be DD-MM-YYYY.");
  const c = fileComplaint({ ...nc, qty: Number(nc.qty) || 0, legacy: "" });
  nc = null; setFlash(`Filed <strong>${c.ticket}</strong>${c.techs.length ? ` and assigned to ${c.techs.join(", ")}` : ""}.`);
  go(`#cmp/view/${c.ticket}`);
}

/* ------------------------------ Complaint detail ------------------------------ */
ROUTES["cmp/view"] = t => {
  const c = complaint(t);
  if (!c) { view().innerHTML = "<p>Complaint not found.</p>"; return; }
  const idx = STEPS.indexOf(c.status), cps = pieces.filter(p => p.ticket === c.ticket);
  view().innerHTML = `${flashHtml()}<h1><span class="code">${c.ticket}</span> ${cmpBadge(c.status)} ${ageBadge(ageDays(c))}</h1>
    <div class="stepper">${STEPS.map((s, n) => `<span class="${n === idx ? "now" : n < idx ? "done" : ""}">${CMP_STATUS[s]}</span>`).join("")}</div>
    <div class="actions" style="margin-bottom:1rem">
      ${c.status !== "CLOSED" ? `<a href="#cmp/visit/${c.ticket}" role="button" class="btn-cmp">＋ Add visit</a>
        <button class="secondary" onclick="askStatus('${c.ticket}')">Change status</button>
        ${isTech() ? "" : `<button class="secondary outline" onclick="askClose('${c.ticket}')">Close complaint…</button>`}`
      : isTech() ? "" : `<button class="secondary" onclick="setStatus(complaint('${c.ticket}'),'ATTENDED',{note:'Reopened'});route()">Reopen</button>`}
    </div>
    <div class="fields">
      <p><strong>Customer</strong><br>${esc(c.customer)}, ${esc(c.city)}</p>
      <p><strong>Contact</strong><br>${esc(c.contact) || "—"} · ${telLink(c)}</p>
      <p><strong>Fault</strong><br>${esc(c.fault)}${c.qty ? ` (${c.qty} NOS)` : ""}</p>
      <p><strong>Received</strong><br>${c.received} · ${esc(c.priority)} priority</p>
      <p><strong>Wipro complaint no.</strong><br>${esc(c.wipro) || "—"}</p>
      <p><strong>Technicians</strong><br>${esc(c.techs.join(", ")) || `<span class="bad">unassigned</span>`}</p>
      ${c.closure ? `<p><strong>Closed as</strong><br>${esc(c.closure)}${c.closeNote ? `: ${esc(c.closeNote)}` : ""}</p>` : ""}
    </div>
    ${c.legacy ? `<p class="muted">Legacy note (from the Excel sheet): ${esc(c.legacy)}</p>` : ""}
    <h3>Visits</h3>
    ${c.visits.length ? `<ul class="timeline">${c.visits.slice().reverse().map(v => `<li><strong>Visit ${v.no} · ${v.date}</strong> · ${esc(v.techs.join(", "))}
      <br>${esc(v.work)}
      ${v.issueEntry ? `<br>⬆ Parts used: ${entry(v.issueEntry).lines.map(l => `${-l.qty} × ${codeLink(l.code)}`).join(", ")} (${entryLink(v.issueEntry)})` : ""}
      ${v.tags.length ? `<br>♻ Defectives collected: ${v.tags.length} piece(s): ${v.tags.slice(0, 6).map(isTech() ? (x => `<span class="code">${x}</span>`) : pieceLink).join(", ")}${v.tags.length > 6 ? "…" : ""}` : ""}</li>`).join("")}</ul>`
      : `<p class="muted">No visits yet.</p>`}
    ${cps.length ? `<h3>Defective pieces from this complaint</h3><p>${Object.keys(PIECE_STATUS).map(s => [s, cps.filter(p => p.status === s).length])
      .filter(x => x[1]).map(([s, n]) => `${pieceBadge(s)} ${n}`).join(" &nbsp; ")}</p>` : ""}
    <h3>Status history</h3>
    <ul class="timeline">${c.events.slice().reverse().map(e => `<li><strong>${e.date}</strong> · ${esc(e.by)}<br>
      ${e.from ? `${CMP_STATUS[e.from]} → ` : ""}${CMP_STATUS[e.to]}${e.note ? ` <span class="muted">· ${esc(e.note)}</span>` : ""}</li>`).join("")}</ul>
    <a href="${isTech() ? "#cmp/mine" : "#cmp"}" role="button" class="secondary outline">← Back</a>`;
};
function askStatus(t) {
  const c = complaint(t), next = CMP_NEXT[c.status].filter(s => s !== "CLOSED");
  openDlg(`<header><strong>Change status of ${t}</strong></header><p>Now: ${cmpBadge(c.status)}</p>
    ${c.status === "NOT_ATTENDED" ? `<p class="muted">A complaint leaves "Not attended" when a visit is logged.</p>` : ""}
    <div class="actions">${next.map(s => `<button class="secondary" onclick="doStatus('${t}','${s}')">${CMP_STATUS[s]}</button>`).join("")}</div>
    <div id="cs-err"></div><footer class="actions"><button class="secondary outline" onclick="closeDlg()">Cancel</button></footer>`);
}
function doStatus(t, s) { const err = setStatus(complaint(t), s); if (err) return formError("cs-err", err); closeDlg(); setFlash(`Status changed to ${CMP_STATUS[s]}.`); route(); }
function askClose(t) {
  openDlg(`<header><strong>Close ${t}</strong></header>
    <label>Closure reason (required) <select id="cl-reason"><option value="">— choose —</option>${opts(CLOSE_REASONS)}</select></label>
    <label>Note <input id="cl-note" placeholder="optional"></label><div id="cl-err"></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button><button onclick="doClose('${t}')">Close complaint</button></footer>`);
}
function doClose(t) {
  const err = setStatus(complaint(t), "CLOSED", { reason: document.getElementById("cl-reason").value, note: document.getElementById("cl-note").value });
  if (err) return formError("cl-err", err); closeDlg(); setFlash(`${t} closed.`); route();
}

/* ------------------------------ Add visit (issues stock + creates defective pieces) ------------------------------ */
let vf = null;
ROUTES["cmp/visit"] = t => {
  const c = complaint(t);
  if (!c) { view().innerHTML = "<p>Complaint not found.</p>"; return; }
  const fresh = !vf || vf.ticket !== t;
  if (fresh) vf = { ticket: t, date: today(), techs: isTech() ? [ME] : c.techs.slice(0, 1), work: "", loc: "Vizag Office",
    next: c.status === "NOT_ATTENDED" ? "ATTENDED" : c.status };
  const nextOpts = ["ATTENDED", "MATERIAL_TO_CHECK", "AWAITING_MATERIAL", "RESOLVED"].filter(s => s === c.status || c.status === "NOT_ATTENDED" || CMP_NEXT[c.status].includes(s));
  view().innerHTML = `<h1>＋ Visit for <span class="code">${c.ticket}</span></h1>
    <p><strong>${esc(c.customer)}</strong>, ${esc(c.city)} · ${esc(c.fault)} · ${telLink(c)}</p>
    <div class="fields">
      <label>Visit date <input value="${vf.date}" onchange="vf.date=this.value"></label>
      <label>Parts taken from <select onchange="vf.loc=this.value;edRender('v-parts')">${opts(LOCATIONS, vf.loc)}</select></label>
    </div>
    <fieldset><legend>Technicians on this visit</legend><div class="checks">${TECHNICIANS.map(x => `<label><input type="checkbox" ${vf.techs.includes(x) ? "checked" : ""}
      onchange="vf.techs=this.checked?[...vf.techs,'${x}']:vf.techs.filter(y=>y!=='${x}')"> ${x}</label>`).join("")}</div></fieldset>
    <label>Work done <textarea rows="2" placeholder="e.g. replaced 2 drivers, 3 fittings still faulty" onchange="vf.work=this.value">${esc(vf.work)}</textarea></label>
    <h3>⬆ Parts used <span class="muted">(fresh stock out)</span></h3>
    ${lineEditor("v-parts", { reset: fresh, avail: () => ({ loc: vf.loc, bucket: "FRESH" }) })}
    <h3>♻ Defective parts collected <span class="muted">(each becomes a tagged piece)</span></h3>
    ${lineEditor("v-defects", { reset: fresh, extra: ["fault", "batch", "pkd"] })}
    <h3>After this visit the complaint is</h3>
    <div class="choices">${nextOpts.map(s => `<label><input type="radio" name="next" ${vf.next === s ? "checked" : ""} onchange="vf.next='${s}'"><strong>${CMP_STATUS[s]}</strong></label>`).join("")}</div>
    <div id="v-error"></div>
    <div class="actions"><button class="btn-cmp" onclick="vSave()">Save visit</button><a href="#cmp/view/${t}" role="button" class="secondary outline">Cancel</a></div>`;
  edRender("v-parts"); edRender("v-defects");
};
function vSave() {
  const c = complaint(vf.ticket);
  if (!/^\d{2}-\d{2}-\d{4}$/.test(vf.date)) return formError("v-error", "Visit date must be DD-MM-YYYY.");
  if (!vf.work.trim()) return formError("v-error", "Write what was done.");
  const parts = edCollect("v-parts", { optional: true }), defects = edCollect("v-defects", { optional: true });
  if (parts.error) return formError("v-error", "Parts used: " + parts.error);
  if (defects.error) return formError("v-error", "Defectives: " + defects.error);
  const err = addVisit(c, { date: vf.date, techs: vf.techs, work: vf.work, loc: vf.loc, next: vf.next,
    parts: parts.lines, defects: defects.lines.map(d => ({ code: d.code, qty: d.qty, fault: d.fault, batchCode: d.batch, pkd: d.pkd })) });
  if (err) return formError("v-error", err);
  const v = c.visits.at(-1);
  setFlash(`Visit ${v.no} saved.${v.issueEntry ? ` Parts issued (${v.issueEntry}).` : ""}${v.tags.length ? ` ${v.tags.length} defective piece(s) created.` : ""}`);
  vf = null; go(`#cmp/view/${c.ticket}`);
}

/* ------------------------------ Technician: My complaints (phone-first) ------------------------------ */
ROUTES["cmp/mine"] = () => {
  const who = isTech() ? ME : "Ramu";
  const mine = complaints.filter(c => c.status !== "CLOSED" && c.techs.includes(who)).sort((a, b) => ageDays(b) - ageDays(a));
  view().innerHTML = `${flashHtml()}<h1>My complaints <span class="muted">(${esc(who)})</span></h1>
    <p class="muted">${mine.length} open · oldest first</p>
    <div class="card-list">${mine.map(c => `<article>
      <h4>${esc(c.customer)} ${ageBadge(ageDays(c))}</h4>
      <p style="margin:0">${esc(c.city)} · ${cmpBadge(c.status)} · <span class="code">${c.ticket}</span><br>${esc(c.fault)}</p>
      <p style="margin:.25rem 0 .75rem">${esc(c.contact)} ${c.phone ? `· <a href="tel:${esc(c.phone)}" role="button" class="secondary outline small">📞 Call</a>` : ""}</p>
      <div class="actions"><a href="#cmp/visit/${c.ticket}" role="button" class="btn-cmp">＋ Add visit</a>
        <a href="#cmp/view/${c.ticket}" role="button" class="secondary outline">Open</a></div></article>`).join("") || "<p>Nothing assigned to you. 🎉</p>"}</div>`;
};

/* ------------------------------ AP Pending Complaints report (their sheet) ------------------------------ */
let rv = { city: "", tech: "" };
ROUTES["cmp/report"] = () => {
  const list = complaints.filter(c => c.status !== "CLOSED" && (!rv.city || c.city === rv.city) && (!rv.tech || c.techs.includes(rv.tech)))
    .sort((a, b) => ageDays(b) - ageDays(a));
  view().innerHTML = `<h1>AP Pending Complaints</h1>
    <div class="filters">
      <label>City <select onchange="rv.city=this.value;route()"><option value="">All cities</option>${opts(CITIES, rv.city)}</select></label>
      <label>Technician <select onchange="rv.tech=this.value;route()"><option value="">Anyone</option>${opts(TECHNICIANS, rv.tech)}</select></label>
      <button class="secondary" onclick="alert('Real app: downloads AP_Pending_Complaints_${today()}.xlsx in this layout')">⬇ Export to Excel</button>
    </div>
    <div class="table-wrap"><table class="xl" style="width:100%"><tr><th>Slno</th><th>Complaint No</th><th>Complaint name</th><th>Location</th><th>Status</th>
      <th>Site contact person</th><th>Site contact number</th><th>Last visit / Technician</th><th>Ageing (days)</th><th>Remarks</th></tr>
      ${list.map((c, n) => `<tr><td>${n + 1}</td><td>${ticketLink(c.ticket)}${c.wipro ? ` / ${esc(c.wipro)}` : ""}</td><td>${esc(c.customer)}</td><td>${esc(c.city)}</td>
        <td>${CMP_STATUS[c.status]}</td><td>${esc(c.contact)}</td><td>${esc(c.phone)}${c.phone && !phoneOk(c.phone) ? " ⚠" : ""}</td>
        <td>${lastVisit(c)} ${esc(c.techs.join("/"))}</td><td>${ageBadge(ageDays(c))}</td><td>${esc(c.fault)}</td></tr>`).join("")}</table></div>
    <p class="muted">Same columns as AP_Pending_Compliants_details.xlsx, plus ageing. The two old "Status" columns are now one status.</p>`;
};
