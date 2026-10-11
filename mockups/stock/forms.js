/* Entry forms: Stock IN / OUT / Transfer / Adjust, built on one reusable item-lines editor. */

/* ---------- searchable item picker (Tom Select) ---------- */
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
    // Matches typed text anywhere, and also look-alike codes (O/0, I/1, hyphens, leading zeros).
    score(search) {
      const t = norm(search), k = key(search);
      return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
    },
    create: allowCreate ? (input, done) => openNewItemDialog(norm(input), it => done(it ? itemOption(it) : false)) : false,
    render: {
      option: d => `<div><span class="opt-code">${esc(d.code)}</span>
        <span class="opt-meta">${esc(d.type)} · ${esc(d.desc)}${d.cat && d.cat !== d.code ? ` · for ${esc(d.cat)}` : ""} · ${esc(d.company)}</span></div>`,
      item: d => `<div>${esc(d.code)}</div>`,
      option_create: d => `<div class="create">＋ Create new item <b>${esc(norm(d.input))}</b>…</div>`,
      no_results: () => `<div class="no-results">No matching item${allowCreate ? " (keep typing the full code to create it)" : ""}.</div>`,
    },
    onChange: v => onPick(v),
  });
}

/* ---------- item fields (shared by the Items page and the quick "create item" dialog) ---------- */
function itemFields(d, p = "it") {
  const sel = (id, list, v, ph) => `<select id="${p}-${id}">${ph ? `<option value="">${ph}</option>` : ""}${list.map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  return `<div class="form-grid">
    <label>Item code <span class="req">*</span><input id="${p}-code" value="${esc(d.code || "")}" autocomplete="off" placeholder="e.g. LG66-040-078-480IT"
      oninput="checkCodeHint('${p}', this.value, '${esc(d.originalCode || "")}')"><small id="${p}-code-hint" class="hint"></small></label>
    <label>Spare type <span class="req">*</span>${sel("type", DB.spareTypes, d.type, "— choose —")}</label>
    <label class="wide">Description<input id="${p}-desc" value="${esc(d.desc || "")}" placeholder="e.g. LED driver 40W 480mA"></label>
    <label>Used in fitting (Product Cat Ref)<input id="${p}-cat" list="cat-refs" value="${esc(d.catRef || "")}" placeholder="e.g. LF40-192-060-57-HE">
      <small class="hint">The fitting this spare belongs to (optional).</small></label>
    <label>Fitting type${sel("ftype", DB.fittingTypes, d.fittingType, "— none —")}</label>
    <label>Wattage (W)<input id="${p}-watt" type="number" min="0" step="1" inputmode="numeric" value="${d.watt ?? ""}"></label>
    <label>Current (mA)<input id="${p}-ma" type="number" min="0" step="1" inputmode="numeric" value="${d.ma ?? ""}"></label>
    <label>Company / brand <span class="req">*</span>${sel("company", DB.companies, d.company || "Wipro Lighting")}</label>
    <label>Unit <span class="req">*</span>${sel("unit", DB.units, d.unit || "NOS")}</label>
    <label>Reorder level<input id="${p}-reorder" type="number" min="0" step="1" inputmode="numeric" value="${d.reorder ?? 0}">
      <small class="hint">Warn when total stock falls to this.</small></label>
    <label class="wide">Other spellings of this code<input id="${p}-aliases" value="${esc((d.aliases || []).join(", "))}" placeholder="e.g. EI08437, EIO-8437">
      <small class="hint">Separate with commas. Searching any of these finds this item.</small></label>
  </div>
  <datalist id="cat-refs">${uniq(DB.items.map(i => i.catRef).filter(Boolean)).map(c => `<option value="${esc(c)}">`).join("")}</datalist>`;
}
function checkCodeHint(p, v, original) {
  const hit = findByCode(v), el = document.getElementById(`${p}-code-hint`);
  el.className = hit && hit.code !== original ? "err" : "hint";
  el.textContent = !v.trim() ? "" : hit && hit.code !== original
    ? (hit.code === norm(v) ? `${hit.code} already exists.` : `Looks like existing item ${hit.code}. Use that instead?`)
    : `Will be saved as ${norm(v)}`;
}
function readItemFields(p = "it") {
  const v = id => document.getElementById(`${p}-${id}`).value;
  const n = id => v(id) === "" ? null : Number(v(id));
  return { code: v("code"), type: v("type"), desc: v("desc").trim(), catRef: norm(v("cat")), fittingType: v("ftype"),
    watt: n("watt"), ma: n("ma"), company: v("company"), unit: v("unit"), reorder: n("reorder") || 0,
    aliases: v("aliases").split(",").map(s => s.trim()).filter(Boolean) };
}
function openNewItemDialog(code, done) {
  openDlg(`<header><strong>Create new item</strong></header>${itemFields({ code })}
    <p id="ni-err" class="err"></p>
    <footer><button class="secondary" type="button" onclick="closeDlg();window._niDone(null)">Cancel</button>
      <button type="button" onclick="saveNewItem()">Create item</button></footer>`);
  window._niDone = done;
  checkCodeHint("it", code, "");
}
function saveNewItem() {
  const d = readItemFields(), err = saveItem(d);
  if (err) { document.getElementById("ni-err").textContent = err; return; }
  closeDlg(); window._niDone(item(norm(d.code)));
}

/* ---------- reusable item-lines editor ---------- */
class Lines {
  /* mode: in | out | trf | adj. getLoc returns the location the lines draw from (out/trf/adj). */
  constructor(host, mode, getLoc) {
    Object.assign(this, { host, mode, getLoc, rows: [], next: 1 });
    const heads = { in: ["#", "Item", "Qty", "Batch code", "PKD (packed)", "", ""],
      out: ["#", "Item", "Available", "Qty", ""], trf: ["#", "Item", "Available", "Qty", ""],
      adj: ["#", "Item", "System qty", "Counted qty", "Difference", ""] }[mode];
    host.className = `lines ${mode === "in" ? "" : mode === "adj" ? "adj" : "out"}`;
    host.innerHTML = `<div class="lines-head">${heads.map(h => `<div>${h}</div>`).join("")}</div><div class="rows"></div>
      <button type="button" class="secondary outline add-line">＋ Add another item</button>`;
    host.querySelector(".add-line").onclick = () => this.add(undefined, true);
  }
  add(code, focus = false) {
    const r = { id: this.next++, code: "", el: document.createElement("div") };
    r.el.className = "line";
    const qty = (cls, lbl, min) => `<div><span class="lbl-m">${lbl}</span><div class="qty-wrap"><input type="number" class="${cls}" min="${min}" step="1" inputmode="numeric"
      placeholder="0" aria-label="${lbl}"><span class="u">—</span></div><small class="err"></small></div>`;
    r.el.innerHTML = `<div class="n"></div><div class="item-cell"><select aria-label="Item"></select><small class="hint meta"></small></div>` + {
      in: qty("qty", "Qty", 1) + `<div><span class="lbl-m">Batch code</span><input class="batch" placeholder="e.g. B2405"></div>
          <div><span class="lbl-m">PKD (packed)</span><input class="pkd" type="month"></div><div></div>`,
      out: `<div class="avail"></div>` + qty("qty", "Qty", 1), trf: `<div class="avail"></div>` + qty("qty", "Qty", 1),
      adj: `<div class="avail"></div>` + qty("counted", "Counted qty", 0) + `<div class="avail diff"></div>`,
    }[this.mode] + `<div class="rm"><button type="button" class="secondary outline remove" title="Remove line" aria-label="Remove line">✕</button></div>`;
    this.host.querySelector(".rows").appendChild(r.el);
    r.ts = makeItemPicker(r.el.querySelector("select"), { allowCreate: this.mode === "in", onPick: v => { r.code = v; this.refresh(r); } });
    r.el.querySelector(".remove").onclick = () => this.remove(r);
    r.el.querySelectorAll("input[type=number]").forEach(i => i.addEventListener("input", () => this.refresh(r)));
    this.rows.push(r);
    if (code) r.ts.setValue(code);
    this.number();
    if (focus) setTimeout(() => r.ts.focus(), 0);
    return r;
  }
  remove(r) {
    if (this.rows.length === 1) { r.ts.clear(); r.el.querySelectorAll("input").forEach(i => i.value = ""); this.refresh(r); return; }
    r.ts.destroy(); r.el.remove(); this.rows = this.rows.filter(x => x !== r); this.number();
  }
  number() { this.rows.forEach((r, i) => r.el.querySelector(".n").textContent = i + 1); }
  refreshAll() { this.rows.forEach(r => this.refresh(r)); }
  refresh(r) {
    const it = item(r.code), u = it ? it.unit : "—";
    r.el.querySelectorAll(".u").forEach(s => s.textContent = u);
    r.el.querySelector(".meta").textContent = it ? `${it.type} · ${it.desc}${it.catRef && it.catRef !== it.code ? ` · for ${it.catRef}` : ""}` : "";
    const err = r.el.querySelector("small.err"); err.textContent = "";
    const qtyEl = r.el.querySelector(".qty, .counted"); qtyEl.removeAttribute("aria-invalid");
    if (this.mode === "in" || !it) { if (!it && this.mode !== "in") r.el.querySelector(".avail").textContent = ""; return; }
    const loc = this.getLoc(), have = balance(it.code, loc);
    r.el.querySelector(".avail").innerHTML = `<b>${have}</b> ${u}<br><span class="muted">at ${esc(loc)}</span>`;
    if (this.mode === "adj") {
      const c = qtyEl.value === "" ? null : Number(qtyEl.value), d = c === null ? null : c - have;
      r.el.querySelector(".diff").innerHTML = d === null ? "" : `<b class="${d < 0 ? "low" : d > 0 ? "ok" : ""}">${d > 0 ? "+" : ""}${d}</b> ${u}`;
    } else if (Number(qtyEl.value) > have) {
      err.textContent = `Only ${have} ${u} available`; qtyEl.setAttribute("aria-invalid", "true");
    }
  }
  /* -> {lines:[{code, qty, batch, pkd, counted}]} or {error} */
  collect() {
    const out = [];
    for (const [i, r] of this.rows.entries()) {
      const q = r.el.querySelector(".qty, .counted"), v = q.value.trim();
      if (!r.code && !v) continue;
      if (!r.code) return { error: `Line ${i + 1}: choose an item.` };
      const n = Number(v);
      if (v === "" || !Number.isInteger(n) || n < (this.mode === "adj" ? 0 : 1))
        return { error: `Line ${i + 1}: enter a whole-number ${this.mode === "adj" ? "counted qty (0 or more)" : "quantity of 1 or more"}.` };
      out.push({ code: r.code, qty: n, batch: (r.el.querySelector(".batch") || {}).value || "", pkd: (r.el.querySelector(".pkd") || {}).value || "" });
    }
    if (!out.length) return { error: "Add at least one item." };
    if (uniq(out.map(l => l.code)).length !== out.length && this.mode !== "in") return { error: "The same item is on two lines. Combine them into one line." };
    return { lines: out };
  }
}

/* ---------- the four entry forms ---------- */
let lines = null;
const field = id => document.getElementById(id);
const opt = (list, v) => list.map(o => Array.isArray(o) ? `<option value="${esc(o[0])}" ${o[0] === v ? "selected" : ""}>${esc(o[1])}</option>`
  : `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("");

function entryForm(mode, prefill) {
  const title = { in: "⬇ Stock IN", out: "⬆ Stock OUT", trf: "⇄ Transfer stock", adj: "± Adjust stock count" }[mode];
  const sub = { in: "Material received at a location", out: "Material given out from a location",
    trf: "Move stock from one location to another", adj: "Correct the system count after a physical check" }[mode];
  const head = {
    in: `<label>Date <span class="req">*</span><input id="f-date" type="date" value="${today()}" max="${today()}" required></label>
      <label>Received from <span class="req">*</span><select id="f-from" onchange="inFromChanged()">${opt(Object.entries(IN_FROM), "SUPPLIER")}</select></label>
      <label id="w-supplier">Supplier / company <span class="req">*</span><select id="f-supplier"><option value="">— choose —</option>${opt(DB.companies, "Wipro Lighting")}</select></label>
      <label id="w-site" hidden>Site / customer <span class="req">*</span><input id="f-site" list="customers" placeholder="e.g. Dr Reddys, Vizag"></label>
      <label>Into location <span class="req">*</span><select id="f-loc">${opt(DB.locations, "Vizag Office")}</select></label>
      <label>DC / bill no.<input id="f-ref" placeholder="e.g. DC 4512"></label>
      <label class="wide">Remarks<textarea id="f-note" rows="2" placeholder="Optional"></textarea></label>`,
    out: `<label>Date <span class="req">*</span><input id="f-date" type="date" value="${today()}" max="${today()}" required></label>
      <label>From location <span class="req">*</span><select id="f-loc" onchange="lines.refreshAll()">${opt(DB.locations, "Vizag Office")}</select></label>
      <label>Issued to <span class="req">*</span><select id="f-to" onchange="outToChanged()">${opt(Object.entries(OUT_TO), "SITE")}</select></label>
      <label id="w-site">Site / customer <span class="req">*</span><input id="f-site" list="customers" placeholder="e.g. GMR Airport, Vizag"></label>
      <label id="w-tech" hidden>Technician <span class="req">*</span><select id="f-tech"><option value="">— choose —</option>${opt(DB.technicians)}</select></label>
      <label id="w-other" hidden>Name <span class="req">*</span><input id="f-other" placeholder="Who received it"></label>
      <label>Job / reference no.<input id="f-ref" placeholder="Optional"></label>
      <label class="wide">Remarks<textarea id="f-note" rows="2" placeholder="Optional"></textarea></label>`,
    trf: `<label>Date <span class="req">*</span><input id="f-date" type="date" value="${today()}" max="${today()}" required></label>
      <label>From location <span class="req">*</span><select id="f-loc" onchange="lines.refreshAll()">${opt(DB.locations, "Vizag Office")}</select></label>
      <label>To location <span class="req">*</span><select id="f-dest">${opt(DB.locations, "TV Shop")}</select></label>
      <label class="wide">Remarks<textarea id="f-note" rows="2" placeholder="Optional"></textarea></label>`,
    adj: `<label>Date <span class="req">*</span><input id="f-date" type="date" value="${today()}" max="${today()}" required></label>
      <label>Location <span class="req">*</span><select id="f-loc" onchange="lines.refreshAll()">${opt(DB.locations, "Vizag Office")}</select></label>
      <label>Reason <span class="req">*</span><select id="f-reason"><option value="">— choose —</option>${opt(ADJ_REASONS)}</select></label>
      <label class="wide">Note <span class="req">*</span><textarea id="f-note" rows="2" placeholder="What happened? e.g. 2 lenses cracked in storage"></textarea></label>`,
  }[mode];
  view().innerHTML = `<div class="page-head"><div><h1>${title}</h1><span class="muted">${sub}</span></div></div>
    <form id="entry-form" novalidate oninput="clearFormError()" onsubmit="event.preventDefault();saveEntry('${mode}')">
      <section class="card"><h2>Details</h2><div class="form-grid">${head}</div></section>
      <section class="card"><h2>Items</h2><div id="lines"></div></section>
      <div id="form-error"></div>
      <div class="form-actions">
        <button type="submit" class="${mode === "in" ? "btn-in" : mode === "out" ? "btn-out" : ""}">Save ${title.replace(/^\S+ /, "")}</button>
        <a href="#dash" role="button" class="secondary outline">Cancel</a>
      </div>
    </form>
    <datalist id="customers">${opt(DB.customers)}</datalist>`;
  lines = new Lines(field("lines"), mode, () => field("f-loc").value);
  lines.add(prefill && item(prefill) ? prefill : undefined);
}
function inFromChanged() {
  const v = field("f-from").value;
  field("w-supplier").hidden = v !== "SUPPLIER"; field("w-site").hidden = v !== "RETURN";
}
function outToChanged() {
  const v = field("f-to").value;
  field("w-site").hidden = v !== "SITE"; field("w-tech").hidden = v !== "TECH"; field("w-other").hidden = v !== "OTHER";
}
function clearFormError() { const el = field("form-error"); if (el) el.innerHTML = ""; }
function formFail(msg, focusId) {
  field("form-error").innerHTML = `<div class="flash bad" role="alert">${esc(msg)}</div>`;
  if (focusId) { const el = field(focusId); el.setAttribute("aria-invalid", "true"); el.focus(); el.addEventListener("input", () => el.removeAttribute("aria-invalid"), { once: true }); }
}
function saveEntry(mode) {
  const date = field("f-date").value, loc = field("f-loc").value, note = field("f-note").value.trim();
  if (!date) return formFail("Choose the date.", "f-date");
  if (date > today()) return formFail("The date can't be in the future.", "f-date");
  const r = lines.collect();
  if (r.error) return formFail(r.error);
  let e;
  if (mode === "in") {
    const from = field("f-from").value;
    const party = from === "SUPPLIER" ? field("f-supplier").value : from === "RETURN" ? field("f-site").value.trim() : "Opening stock (first count)";
    if (!party) return formFail(from === "SUPPLIER" ? "Choose the supplier." : "Enter the site / customer.", from === "SUPPLIER" ? "f-supplier" : "f-site");
    e = { kind: "IN", subtype: from, date, party, ref: field("f-ref").value.trim(), note,
      lines: r.lines.map(l => ({ code: l.code, loc, qty: l.qty, batch: l.batch, pkd: l.pkd })) };
  } else if (mode === "out") {
    const to = field("f-to").value, id = { SITE: "f-site", TECH: "f-tech", OTHER: "f-other" }[to], party = field(id).value.trim();
    if (!party) return formFail(`Enter who it was issued to (${OUT_TO[to].toLowerCase()}).`, id);
    e = { kind: "OUT", subtype: to, date, party, ref: field("f-ref").value.trim(), note,
      lines: r.lines.map(l => ({ code: l.code, loc, qty: -l.qty })) };
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
  setFlash(`Saved <b>${e.no}</b> · ${e.lines.length} line(s). Stock updated.`);
  go(`#entry/${e.no}`);
}
