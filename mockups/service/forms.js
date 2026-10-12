/* Entry forms (Stock IN / OUT / Transfer / Adjust) and item fields, in Tabler markup.
   Location pickers use DB.locations only, so the Defective store is never offered here. */

const field = id => document.getElementById(id);

/* ---------- searchable item picker (Tom Select, styled by Tabler) ---------- */
function itemOption(i) {
  return { code: i.code, type: i.type, desc: i.desc, cat: i.catRef, company: i.company, unit: i.unit,
    hay: [i.code, ...i.aliases, i.desc, i.catRef, i.type, i.company, i.fittingType].join(" ").toUpperCase(),
    keys: [i.code, ...i.aliases, i.catRef].filter(Boolean).map(key).join(" ") };
}
function makeItemPicker(select, { allowCreate, onPick }) {
  return new TomSelect(select, {
    options: DB.items.filter(i => i.active).map(itemOption),
    valueField: "code", labelField: "code", maxOptions: 60, closeAfterSelect: true, openOnFocus: false,
    placeholder: "Type code, old spelling or description…",
    // Matches text anywhere, and look-alike codes (O/0, I/1, hyphens, leading zeros).
    score(search) {
      const t = norm(search), k = key(search);
      return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
    },
    create: allowCreate ? (input, done) => openNewItemModal(norm(input), it => done(it ? itemOption(it) : false)) : false,
    render: {
      option: d => `<div><span class="opt-code">${esc(d.code)}</span>
        <span class="opt-meta">${esc(d.type)} · ${esc(d.desc)}${d.cat && d.cat !== d.code ? ` · for ${esc(d.cat)}` : ""} · ${esc(d.company)}</span></div>`,
      item: d => `<div>${esc(d.code)}</div>`,
      option_create: d => `<div class="create">＋ Create new item <b>${esc(norm(d.input))}</b>…</div>`,
      no_results: () => `<div class="no-results">No matching item${allowCreate ? " (type the full code to create it)" : ""}.</div>`,
    },
    onChange: v => onPick(v),
  });
}

/* ---------- item fields (Items page and the quick "create item" modal) ---------- */
function itemFields(d, p = "it") {
  const sel = (id, list, v, ph) => `<select id="${p}-${id}" class="form-select">${ph ? `<option value="">${ph}</option>` : ""}${opt(list, v)}</select>`;
  const col = (w, html) => `<div class="col-12 col-md-${w}">${html}</div>`;
  return `<div class="row g-3">
    ${col(4, `<label class="form-label required" for="${p}-code">Item code</label><input id="${p}-code" class="form-control" value="${esc(d.code || "")}" autocomplete="off"
      placeholder="e.g. LG66-040-078-480IT" oninput="checkCodeHint('${p}', this.value, '${esc(d.originalCode || "")}')"><small id="${p}-code-hint" class="form-hint"></small>`)}
    ${col(4, `<label class="form-label required" for="${p}-type">Spare type</label>${sel("type", DB.spareTypes, d.type, "Choose…")}`)}
    ${col(4, `<label class="form-label required" for="${p}-company">Company / brand</label>${sel("company", DB.companies, d.company || DB.config.defaultCompany)}`)}
    ${col(12, `<label class="form-label" for="${p}-desc">Description</label><input id="${p}-desc" class="form-control" value="${esc(d.desc || "")}" placeholder="e.g. LED driver 40W 480mA">`)}
    ${col(4, `<label class="form-label" for="${p}-cat">Used in fitting (Product Cat Ref)</label><input id="${p}-cat" class="form-control" list="cat-refs" value="${esc(d.catRef || "")}"
      placeholder="e.g. LF40-192-060-57-HE"><small class="form-hint">The fitting this spare belongs to (optional).</small>`)}
    ${col(4, `<label class="form-label" for="${p}-ftype">Fitting type</label>${sel("ftype", DB.fittingTypes, d.fittingType, "None")}`)}
    ${col(2, `<label class="form-label" for="${p}-watt">Wattage</label><div class="input-group"><input id="${p}-watt" type="number" min="0" step="1" inputmode="numeric" class="form-control" value="${d.watt ?? ""}"><span class="input-group-text">W</span></div>`)}
    ${col(2, `<label class="form-label" for="${p}-ma">Current</label><div class="input-group"><input id="${p}-ma" type="number" min="0" step="1" inputmode="numeric" class="form-control" value="${d.ma ?? ""}"><span class="input-group-text">mA</span></div>`)}
    ${col(4, `<label class="form-label required" for="${p}-unit">Unit</label>${sel("unit", DB.units, d.unit || "NOS")}`)}
    ${col(4, `<label class="form-label" for="${p}-reorder">Reorder level</label><input id="${p}-reorder" type="number" min="0" step="1" inputmode="numeric" class="form-control" value="${d.reorder ?? 0}">
      <small class="form-hint">Warn when total stock falls to this.</small>`)}
    ${col(4, `<label class="form-label" for="${p}-aliases">Other spellings of this code</label><input id="${p}-aliases" class="form-control" value="${esc((d.aliases || []).join(", "))}"
      placeholder="e.g. EI08437, EIO-8437"><small class="form-hint">Comma separated. Searching any of these finds this item.</small>`)}
  </div><datalist id="cat-refs">${uniq(DB.items.map(i => i.catRef).filter(Boolean)).map(c => `<option value="${esc(c)}">`).join("")}</datalist>`;
}
function checkCodeHint(p, v, original) {
  const hit = findByCode(v), el = field(`${p}-code-hint`), input = field(`${p}-code`), bad = hit && hit.code !== original;
  input.classList.toggle("is-invalid", !!bad); input.classList.toggle("is-valid", !!v.trim() && !bad);
  el.className = bad ? "invalid-feedback d-block" : "form-hint";
  el.textContent = !v.trim() ? "" : bad ? (hit.code === norm(v) ? `${hit.code} already exists.` : `Looks like existing item ${hit.code}. Use that instead?`)
    : `Will be saved as ${norm(v)}`;
}
function readItemFields(p = "it") {
  const v = id => field(`${p}-${id}`).value, n = id => v(id) === "" ? null : Number(v(id));
  return { code: v("code"), type: v("type"), desc: v("desc").trim(), catRef: norm(v("cat")), fittingType: v("ftype"),
    watt: n("watt"), ma: n("ma"), company: v("company"), unit: v("unit"), reorder: n("reorder") || 0,
    aliases: v("aliases").split(",").map(s => s.trim()).filter(Boolean) };
}
function openNewItemModal(code, done) {
  window._niDone = done;
  openModal(`<div class="modal-header"><h5 class="modal-title">${icon("box")} Create new item</h5>
      <button type="button" class="btn-close" aria-label="Close" onclick="closeModal();window._niDone(null)"></button></div>
    <div class="modal-body">${itemFields({ code })}<div id="ni-err" class="text-danger mt-3"></div></div>
    <div class="modal-footer"><button type="button" class="btn btn-link link-secondary" onclick="closeModal();window._niDone(null)">Cancel</button>
      <button type="button" class="btn btn-primary ms-auto" onclick="saveNewItem()">${icon("check")} Create item</button></div>`, "modal-lg");
  checkCodeHint("it", code, "");
}
function saveNewItem() {
  const d = readItemFields(), err = saveItem(d);
  if (err) { field("ni-err").textContent = err; return; }
  closeModal(); toast(`Item <b>${esc(norm(d.code))}</b> created.`); window._niDone(item(norm(d.code)));
}

/* ---------- reusable item-lines editor (table on desktop, stacked cards on phones) ----------
   Modes: in / out / trf / adj (stock forms), collect (failed parts collected at a site: in + fault),
   mark (mark defective from stock: out + fault). opts: { summaryId, allowEmpty, addLabel } */
class Lines {
  constructor(host, mode, getLoc, opts = {}) {
    Object.assign(this, { host, mode, getLoc, rows: [], next: 1, opts });
    this.inLike = mode === "in" || mode === "collect";
    const heads = { in: ["#", "Item", "Quantity", "Batch code", "PKD (packed)", ""], out: ["#", "Item", "Available", "Quantity", ""],
      trf: ["#", "Item", "Available", "Quantity", ""], adj: ["#", "Item", "System qty", "Counted qty", "Difference", ""],
      collect: ["#", "Item", "Quantity", "Batch code", "PKD (packed)", "Fault", ""], mark: ["#", "Item", "Available", "Quantity", "Fault", ""] }[mode];
    host.innerHTML = `<div class="lines-wrap"><table class="table table-vcenter lines-table mb-0"><thead><tr>${heads.map((h, i) =>
      `<th class="${i === 0 ? "w-1" : ""}">${h}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
      <button type="button" class="btn btn-outline-primary mt-3 add-line">${icon("plus")} ${opts.addLabel || "Add another item"}</button>`;
    host.querySelector(".add-line").onclick = () => this.add(undefined, true);
  }
  add(code, focus = false) {
    const r = { id: this.next++, code: "", el: document.createElement("tr") };
    const qty = (cls, label, min) => `<td data-label="${label}" style="min-width:9rem"><div class="input-group"><input type="number" class="form-control ${cls}" min="${min}" step="1"
      inputmode="numeric" placeholder="0" aria-label="${label}"><span class="input-group-text u">—</span></div><div class="invalid-feedback d-block err"></div></td>`;
    r.el.innerHTML = `<td class="c-n text-secondary"></td><td class="c-item"><select class="form-select" aria-label="Item"></select><small class="form-hint line-meta"></small></td>` + {
      in: qty("qty", "Quantity", 1) + `<td data-label="Batch code"><input class="form-control batch" placeholder="e.g. B2405"></td>
          <td data-label="PKD (packed)"><input class="form-control pkd" type="month"></td>`,
      out: `<td data-label="Available" class="avail"></td>` + qty("qty", "Quantity", 1),
      trf: `<td data-label="Available" class="avail"></td>` + qty("qty", "Quantity", 1),
      adj: `<td data-label="System qty" class="avail"></td>` + qty("counted", "Counted qty", 0) + `<td data-label="Difference" class="avail diff"></td>`,
      collect: qty("qty", "Quantity", 1) + `<td data-label="Batch code"><input class="form-control batch" placeholder="e.g. B2405" aria-label="Batch code"></td>
          <td data-label="PKD (packed)"><input class="form-control pkd" type="month" aria-label="PKD"></td>
          <td data-label="Fault" class="c-fault"><input class="form-control fault" placeholder="e.g. no output" aria-label="Fault"></td>`,
      mark: `<td data-label="Available" class="avail"></td>` + qty("qty", "Quantity", 1)
          + `<td data-label="Fault" class="c-fault"><input class="form-control fault" placeholder="e.g. dead on arrival" aria-label="Fault"></td>`,
    }[this.mode] + `<td class="c-rm"><button type="button" class="btn btn-icon btn-ghost-danger remove" title="Remove line" aria-label="Remove line">${icon("trash")}</button></td>`;
    this.host.querySelector("tbody").appendChild(r.el);
    r.ts = makeItemPicker(r.el.querySelector("select"), { allowCreate: this.inLike, onPick: v => { r.code = v; this.refresh(r); } });
    r.el.querySelector(".remove").onclick = () => this.remove(r);
    r.el.querySelectorAll("input[type=number]").forEach(i => i.addEventListener("input", () => this.refresh(r)));
    this.rows.push(r);
    if (code) r.ts.setValue(code);
    this.number();
    if (focus) setTimeout(() => r.ts.focus(), 0);
  }
  remove(r) {
    if (this.rows.length === 1) { r.ts.clear(); r.el.querySelectorAll("input").forEach(i => i.value = ""); this.refresh(r); return; }
    r.ts.destroy(); r.el.remove(); this.rows = this.rows.filter(x => x !== r); this.number(); this.summary();
  }
  number() { this.rows.forEach((r, i) => r.el.querySelector(".c-n").textContent = i + 1); }
  refreshAll() { this.rows.forEach(r => this.refresh(r)); }
  refresh(r) {
    const it = item(r.code), u = it ? it.unit : "—";
    r.el.querySelectorAll(".u").forEach(s => s.textContent = u);
    r.el.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}${it.catRef && it.catRef !== it.code ? ` · for ${it.catRef}` : ""}` : "";
    const err = r.el.querySelector(".err"), q = r.el.querySelector(".qty, .counted");
    err.textContent = ""; q.classList.remove("is-invalid");
    if (!this.inLike) {
      const a = r.el.querySelector(".avail");
      if (!it) { a.textContent = ""; } else {
        const loc = this.getLoc(), have = balance(it.code, loc);
        a.innerHTML = `<b>${have}</b> ${u} <span class="text-secondary d-block small">at ${esc(loc)}</span>`;
        if (this.mode === "adj") {
          const c = q.value === "" ? null : Number(q.value), d = c === null ? null : c - have;
          r.el.querySelector(".diff").innerHTML = d === null ? "" : `<span class="badge ${d < 0 ? "bg-red-lt" : d > 0 ? "bg-green-lt" : "bg-secondary-lt"}">${d > 0 ? "+" : ""}${d} ${u}</span>`;
        } else if (Number(q.value) > have) { err.textContent = `Only ${have} ${u} available`; q.classList.add("is-invalid"); }
      }
    }
    this.summary();
  }
  summary() {
    const el = field(this.opts.summaryId || "lines-summary"); if (!el) return;
    const t = {};
    for (const r of this.rows) { const v = Number(r.el.querySelector(".qty, .counted").value); const it = item(r.code); if (it && v > 0 && this.mode !== "adj") t[it.unit] = (t[it.unit] || 0) + v; }
    const n = this.rows.filter(r => r.code).length;
    el.textContent = n ? `${n} item${n > 1 ? "s" : ""}${Object.keys(t).length ? " · " + Object.entries(t).map(([u, q]) => `${q} ${u}`).join(" · ") : ""}` : "";
  }
  collect() {
    const out = [];
    for (const [i, r] of this.rows.entries()) {
      const q = r.el.querySelector(".qty, .counted"), v = q.value.trim();
      if (!r.code && !v) continue;
      if (!r.code) return { error: `Line ${i + 1}: choose an item.` };
      const n = Number(v);
      if (v === "" || !Number.isInteger(n) || n < (this.mode === "adj" ? 0 : 1)) {
        q.classList.add("is-invalid");
        return { error: `Line ${i + 1}: enter a whole-number ${this.mode === "adj" ? "counted quantity (0 or more)" : "quantity of 1 or more"}.` };
      }
      out.push({ code: r.code, qty: n, batch: (r.el.querySelector(".batch") || {}).value || "", pkd: (r.el.querySelector(".pkd") || {}).value || "",
        fault: (r.el.querySelector(".fault") || {}).value || "" });
    }
    if (!out.length) return this.opts.allowEmpty ? { lines: [] } : { error: "Add at least one item." };
    if (!this.inLike && uniq(out.map(l => l.code)).length !== out.length) return { error: "The same item is on two lines. Combine them into one line." };
    return { lines: out };
  }
}

/* ---------- the four entry forms ---------- */
let lines = null;
const selectgroup = (name, choices, value, onchange) => `<div class="form-selectgroup">${choices.map(([v, label, ic]) =>
  `<label class="form-selectgroup-item"><input type="radio" name="${name}" value="${v}" class="form-selectgroup-input" ${v === value ? "checked" : ""} onchange="${onchange}">
    <span class="form-selectgroup-label">${icon(ic)} ${label}</span></label>`).join("")}</div>`;
const fcol = (w, html, id = "") => `<div class="col-12 col-md-${w}" ${id ? `id="${id}"` : ""}>${html}</div>`;
const lbl = (forId, text, req = true) => `<label class="form-label ${req ? "required" : ""}" for="${forId}">${text}</label>`;
const dateField = () => fcol(3, lbl("f-date", "Date") + `<div class="input-icon"><span class="input-icon-addon">${icon("calendar")}</span>
  <input id="f-date" type="date" class="form-control" value="${today()}" max="${today()}" required></div>`);
const locField = (label, onchange = "") => fcol(3, lbl("f-loc", label) + `<select id="f-loc" class="form-select" ${onchange ? `onchange="${onchange}"` : ""}>${opt(DB.locations, "Vizag Office")}</select>`);
const noteField = (label, req, ph) => fcol(12, lbl("f-note", label, req) + `<textarea id="f-note" class="form-control" rows="2" placeholder="${ph}"></textarea>`);

function entryForm(mode, prefill) {
  const meta = {
    in: ["Stock", "Stock IN", "Material received at a location", "package-import", "btn-in"],
    out: ["Stock", "Stock OUT", "Material given out from a location", "package-export", "btn-out"],
    trf: ["Stock", "Transfer stock", "Move stock from one location to another", "arrows-exchange", "btn-primary"],
    adj: ["Stock", "Adjust stock count", "Correct the system count after a physical check", "adjustments-horizontal", "btn-primary"],
  }[mode];
  setHeader(meta[0], `${icon(meta[3])} ${meta[1]}`);
  const details = {
    in: fcol(12, lbl("", "Received from") + selectgroup("from", [["SUPPLIER", "From supplier", "truck-delivery"], ["RETURN", "Returned unused from site", "arrow-back-up"],
          ["OPENING", "Opening stock", "clipboard-list"]], "SUPPLIER", "inFromChanged()"))
      + dateField()
      + fcol(3, lbl("f-supplier", "Supplier / company") + `<select id="f-supplier" class="form-select"><option value="">Choose…</option>${opt(DB.companies, DB.config.defaultCompany)}</select>`, "w-supplier")
      + fcol(3, lbl("f-site", "Site / customer") + `<input id="f-site" class="form-control" list="customers" placeholder="e.g. Dr Reddys, Vizag">`, "w-site")
      + locField("Into location") + fcol(3, lbl("f-ref", "DC / bill no.", false) + `<input id="f-ref" class="form-control" placeholder="e.g. DC 4512">`)
      + noteField("Remarks", false, "Optional"),
    out: fcol(12, lbl("", "Issued to") + selectgroup("to", [["SITE", "Site / customer", "building-factory-2"], ["TECH", "Technician", "user-cog"], ["OTHER", "Other", "user"]],
          "SITE", "outToChanged()"))
      + dateField() + locField("From location", "lines.refreshAll()")
      + fcol(3, lbl("f-site", "Site / customer") + `<input id="f-site" class="form-control" list="customers" placeholder="e.g. GMR Airport, Vizag">`, "w-site")
      + fcol(3, lbl("f-tech", "Technician") + `<select id="f-tech" class="form-select"><option value="">Choose…</option>${opt(DB.technicians)}</select>`, "w-tech")
      + fcol(3, lbl("f-other", "Name") + `<input id="f-other" class="form-control" placeholder="Who received it">`, "w-other")
      + fcol(3, lbl("f-ref", "Job / reference no.", false) + `<input id="f-ref" class="form-control" placeholder="Optional">`)
      + noteField("Remarks", false, "Optional"),
    trf: dateField() + locField("From location", "lines.refreshAll()")
      + fcol(3, lbl("f-dest", "To location") + `<select id="f-dest" class="form-select">${opt(DB.locations, "TV Shop")}</select>`)
      + noteField("Remarks", false, "Optional"),
    adj: dateField() + locField("Location", "lines.refreshAll()")
      + fcol(3, lbl("f-reason", "Reason") + `<select id="f-reason" class="form-select"><option value="">Choose…</option>${opt(ADJ_REASONS)}</select>`)
      + noteField("Note", true, "What happened? e.g. 2 lenses cracked in storage"),
  }[mode];
  view().innerHTML = `<form id="entry-form" novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveEntry('${mode}')">
    <div class="card mb-3"><div class="card-header"><h3 class="card-title">${icon("file-description")} Details</h3>
      <div class="card-subtitle ms-2 text-secondary">${meta[2]}</div></div><div class="card-body"><div class="row g-3">${details}</div></div></div>
    <div class="card"><div class="card-header"><h3 class="card-title">${icon("list-details")} Items</h3></div>
      <div class="card-body"><div id="lines"></div></div>
      <div class="card-footer d-flex flex-wrap align-items-center gap-2">
        <span id="lines-summary" class="text-secondary"></span>
        <div class="ms-auto btn-list"><a href="#dash" class="btn btn-link link-secondary">Cancel</a>
          <button type="submit" class="btn ${meta[4]}">${icon("device-floppy")} Save ${meta[1]}</button></div></div>
    </div>
    <div id="form-error" class="mt-3"></div>
  </form><datalist id="customers">${opt(DB.customers)}</datalist>`;
  if (mode === "in") inFromChanged();
  if (mode === "out") outToChanged();
  lines = new Lines(field("lines"), mode, () => field("f-loc").value);
  lines.add(prefill && item(prefill) ? prefill : undefined);
}
const radioVal = name => document.querySelector(`input[name=${name}]:checked`).value;
function inFromChanged() { const v = radioVal("from"); field("w-supplier").hidden = v !== "SUPPLIER"; field("w-site").hidden = v !== "RETURN"; }
function outToChanged() { const v = radioVal("to"); field("w-site").hidden = v !== "SITE"; field("w-tech").hidden = v !== "TECH"; field("w-other").hidden = v !== "OTHER"; }
function clearFormError() { const el = field("form-error"); if (el) el.innerHTML = ""; }
function formFail(msg, focusId) {
  field("form-error").innerHTML = `<div class="alert alert-danger" role="alert"><div class="d-flex gap-2">${icon("alert-circle")}<div>${esc(msg)}</div></div></div>`;
  if (focusId) { const el = field(focusId); el.classList.add("is-invalid"); el.focus(); el.addEventListener("input", () => el.classList.remove("is-invalid"), { once: true }); }
}
function saveEntry(mode) {
  const date = field("f-date").value, loc = field("f-loc").value, note = field("f-note").value.trim();
  if (!date) return formFail("Choose the date.", "f-date");
  if (date > today()) return formFail("The date can't be in the future.", "f-date");
  const r = lines.collect();
  if (r.error) return formFail(r.error);
  let e;
  if (mode === "in") {
    const from = radioVal("from");
    const party = from === "SUPPLIER" ? field("f-supplier").value : from === "RETURN" ? field("f-site").value.trim() : "Opening stock (first count)";
    if (!party) return formFail(from === "SUPPLIER" ? "Choose the supplier." : "Enter the site / customer.", from === "SUPPLIER" ? "f-supplier" : "f-site");
    e = { kind: "IN", subtype: from, date, party, ref: field("f-ref").value.trim(), note, lines: r.lines.map(l => ({ code: l.code, loc, qty: l.qty, batch: l.batch, pkd: l.pkd })) };
  } else if (mode === "out") {
    const to = radioVal("to"), id = { SITE: "f-site", TECH: "f-tech", OTHER: "f-other" }[to], party = field(id).value.trim();
    if (!party) return formFail(`Enter who it was issued to (${OUT_TO[to].toLowerCase()}).`, id);
    e = { kind: "OUT", subtype: to, date, party, ref: field("f-ref").value.trim(), note, lines: r.lines.map(l => ({ code: l.code, loc, qty: -l.qty })) };
  } else if (mode === "trf") {
    const dest = field("f-dest").value;
    if (dest === loc) return formFail("From and To locations must be different.", "f-dest");
    e = { kind: "TRF", date, party: dest, note, lines: r.lines.flatMap(l => [{ code: l.code, loc, qty: -l.qty }, { code: l.code, loc: dest, qty: l.qty }]) };
  } else {
    const reason = field("f-reason").value;
    if (!reason) return formFail("Choose the reason for the adjustment.", "f-reason");
    if (!note) return formFail("Write a short note explaining the adjustment.", "f-note");
    const diffs = r.lines.map(l => ({ code: l.code, loc, qty: l.qty - balance(l.code, loc) })).filter(l => l.qty !== 0);
    if (!diffs.length) return formFail("The counted quantities match the system. Nothing to adjust.");
    e = { kind: "ADJ", date, reason, note, lines: diffs };
  }
  const err = post(e);
  if (err) return formFail(err + " Nothing was saved.");
  toastAfterNav(`<b>${e.no}</b> saved · ${e.kind === "TRF" ? e.lines.length / 2 : e.lines.length} item(s). Stock updated.`);
  go(`#entry/${e.no}`);
}
