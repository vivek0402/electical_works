/* Item-line editors for the service pages (Mark defective, Record visit). Same look and rules as the stock entry
   forms (static/js/entry-form.js, left untouched): searchable item picker with look-alike codes, live availability
   at the chosen location, and an over-issue warning.

   Page contract (a missing required piece throws "line-editor: …" so a broken page fails loudly):
   - json_script blocks with ids "items-data" (picker options) and "balances-data" ({"<item>-<location>": qty}),
     once per page, shared by every editor. Required as soon as the page has a form[data-lines-form].
   - Every form[data-lines-form] is wired. Inside it:
     - one element with [data-form-error] (required): the form's error box, filled by the server or by this file;
     - one or more editors <div data-lines="<prefix>" data-mode="out|mark|collect" …> posting <prefix>_item,
       <prefix>_qty, <prefix>_batch, <prefix>_pkd and <prefix>_fault. Each editor needs its own prefix.
   - Editor attributes:
     data-lines    (required) the field prefix, e.g. "line", "part", "col";
     data-mode     (required) out = parts going out (Available column), mark = out + a required Fault,
                   collect = failed parts coming in (Batch code, PKD, optional Fault, no Available column);
     data-loc      id of the location <select> the Available column reads (out/mark; optional);
     data-initial  id of a json_script holding this editor's lines ([{item, qty, batch, pkd, fault}]); missing = [].
                   Use a different id per editor;
     data-summary  id of an element for "2 items · 3 NOS"; optional, a different id per editor;
     data-add-label  text of the "Add another item" button; data-max  most per line (default 1,000,000).
   - The same item may be on several lines; the over-issue check adds up all lines of an item. */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Same rules as apps/inventory/normalise.normalise_code and search_key.
  const norm = s => String(s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").replace(/^[ .,;:]+|[ .,;:]+$/g, "");
  const lookKey = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
    .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
  const HEADS = {
    out: ["#", "Item", "Available", "Quantity", ""],
    mark: ["#", "Item", "Available", "Quantity", "Fault", ""],
    collect: ["#", "Item", "Quantity", "Batch code", "PKD (packed)", "Fault", ""],
  };
  const fail = what => { throw new Error(`line-editor: ${what}`); };
  const byId = (id, what) => document.getElementById(id) || fail(`missing #${id}${what ? ` (${what})` : ""}`);
  let uid = 0; // unique ids for aria-describedby

  class LineEditor {
    constructor({ host, mode, prefix, items, balances, locSelect, addLabel, summaryEl, maxQty }) {
      if (!HEADS[mode]) fail(`unknown data-mode "${mode}" on [data-lines="${prefix}"]`);
      if (!prefix) fail("an editor has an empty data-lines prefix");
      Object.assign(this, { host, mode, prefix, items, balances, locSelect, summaryEl, maxQty: maxQty || 1000000, rows: [], checked: false });
      host.innerHTML = `<div class="lines-wrap"><table class="table table-vcenter lines-table mb-0"><thead><tr>${HEADS[mode]
        .map((h, i) => `<th${i === 0 ? ' class="w-1"' : ""}>${h}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
        <button type="button" class="btn btn-outline-primary mt-3 add-line"><i class="ti ti-plus"></i> ${esc(addLabel || "Add another item")}</button>`;
      this.body = host.querySelector("tbody");
      host.querySelector(".add-line").addEventListener("click", () => this.add({}, true));
      if (locSelect) locSelect.addEventListener("change", () => this.refresh());
    }
    name(field) { return `${this.prefix}_${field}`; }
    option(i) { return { ...i, value: String(i.id), hay: norm([i.code, ...i.aliases, i.desc, i.cat, i.type, i.company].join(" ")) }; }
    qtyCell(id) {
      return `<td data-label="Quantity" style="min-width:9rem"><div class="input-group"><input type="number" name="${this.name("qty")}" class="form-control qty"
        min="1" max="${this.maxQty}" step="1" inputmode="numeric" placeholder="0" aria-label="Quantity" aria-describedby="${id}-qerr"><span class="input-group-text u">—</span></div>
        <div class="invalid-feedback d-block err" id="${id}-qerr" aria-live="polite"></div></td>`;
    }
    faultCell(id, placeholder) {
      const required = this.mode === "mark" ? ' aria-required="true"' : "";
      return `<td data-label="Fault" class="c-fault"><input name="${this.name("fault")}" class="form-control fault" maxlength="200" placeholder="${placeholder}" aria-label="Fault"${required}
        aria-describedby="${id}-ferr"><div class="invalid-feedback d-block ferr" id="${id}-ferr" aria-live="polite"></div></td>`;
    }
    add(init = {}, focus = false) {
      const tr = document.createElement("tr"), row = { tr }, id = `le${++uid}`;
      const cells = {
        out: `<td data-label="Available" class="avail"></td>` + this.qtyCell(id),
        mark: `<td data-label="Available" class="avail"></td>` + this.qtyCell(id) + this.faultCell(id, "e.g. dead on arrival"),
        collect: this.qtyCell(id)
          + `<td data-label="Batch code"><input name="${this.name("batch")}" class="form-control batch" maxlength="40" placeholder="e.g. B2405" aria-label="Batch code"></td>`
          + `<td data-label="PKD (packed)"><input name="${this.name("pkd")}" class="form-control pkd" type="month" aria-label="PKD (packed)"></td>`
          + this.faultCell(id, "e.g. no output"),
      }[this.mode];
      tr.innerHTML = `<td class="c-n text-secondary"></td><td class="c-item"><select name="${this.name("item")}" class="form-select" aria-label="Item"><option value=""></option></select>
        <small class="form-hint line-meta"></small></td>${cells}<td class="c-rm"><button type="button" class="btn btn-icon btn-ghost-danger remove" title="Remove line" aria-label="Remove line"><i class="ti ti-trash"></i></button></td>`;
      this.body.appendChild(tr);
      row.ts = new TomSelect(tr.querySelector("select"), {
        options: [...this.items.values()].map(i => this.option(i)), valueField: "value", labelField: "code", maxOptions: 60,
        closeAfterSelect: true, openOnFocus: false, placeholder: "Type code, old spelling or description…",
        score(search) { // text anywhere, or a look-alike code (O/0, I/1, hyphens, leading zeros)
          const t = norm(search), k = lookKey(search);
          return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
        },
        render: {
          option: d => `<div><span class="opt-code">${esc(d.code)}</span><span class="opt-meta">${esc(d.type)} · ${esc(d.desc)}${d.cat && d.cat !== d.code ? ` · for ${esc(d.cat)}` : ""} · ${esc(d.company)}</span></div>`,
          item: d => `<div>${esc(d.code)}</div>`,
          no_results: () => `<div class="no-results">No matching item.</div>`,
        },
        onChange: () => this.refresh(),
      });
      row.ts.control_input.setAttribute("aria-label", "Item");
      row.qty = tr.querySelector(".qty");
      row.fault = tr.querySelector(".fault");
      row.qty.addEventListener("input", () => this.refresh());
      if (row.fault) row.fault.addEventListener("input", () => this.paint(row));
      tr.querySelector(".remove").addEventListener("click", () => this.remove(row));
      this.rows.push(row);
      if (init.item && this.items.has(String(init.item))) row.ts.setValue(String(init.item), true);
      row.qty.value = init.qty || "";
      for (const f of ["batch", "pkd", "fault"]) { const el = tr.querySelector(`.${f}`); if (el) el.value = init[f] || ""; }
      this.number(); this.refresh();
      if (focus) setTimeout(() => row.ts.focus(), 0);
    }
    remove(row) {
      if (this.rows.length === 1) { row.ts.clear(); row.tr.querySelectorAll("input").forEach(i => { i.value = ""; }); this.refresh(); return; }
      row.ts.destroy(); row.tr.remove(); this.rows.splice(this.rows.indexOf(row), 1); this.number(); this.refresh();
    }
    number() { this.rows.forEach((r, n) => { r.tr.querySelector(".c-n").textContent = n + 1; }); }
    have(it) { return this.balances[`${it.id}-${this.locSelect.value}`] || 0; }
    refresh() { this.rows.forEach(r => this.paint(r)); this.summary(); } // every row: lines of one item share a balance
    qtyProblem(row, it) {
      const v = Number(row.qty.value), unit = it ? it.unit : "";
      if (v > this.maxQty) return `At most ${this.maxQty} per line`;
      if (!it || !this.locSelect || this.mode === "collect") return "";
      const n = this.have(it), same = this.rows.filter(r => r.ts.getValue() === String(it.id));
      const total = same.reduce((sum, r) => sum + (Number(r.qty.value) || 0), 0);
      if (v > n) return `Only ${n} ${unit} available`;
      if (v > 0 && total > n) return `Only ${n} ${unit} available (${total} on ${same.length} lines)`;
      return "";
    }
    faultProblem(row) {
      return this.mode === "mark" && row.ts.getValue() && !row.fault.value.trim() ? "Write what is wrong with the piece" : "";
    }
    paint(row) {
      const it = this.items.get(row.ts.getValue()), unit = it ? it.unit : "—";
      row.tr.querySelectorAll(".u").forEach(s => { s.textContent = unit; });
      row.tr.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}${it.cat && it.cat !== it.code ? ` · for ${it.cat}` : ""}` : "";
      const avail = row.tr.querySelector(".avail");
      if (avail && this.locSelect) {
        const place = this.locSelect.options[this.locSelect.selectedIndex]?.text || "";
        avail.innerHTML = it ? `<b>${this.have(it)}</b> ${esc(unit)} <span class="text-secondary d-block small">at ${esc(place)}</span>` : "";
      }
      const qtyMsg = this.qtyProblem(row, it);
      row.tr.querySelector(".err").textContent = qtyMsg;
      row.qty.classList.toggle("is-invalid", !!qtyMsg);
      row.qty.setAttribute("aria-invalid", qtyMsg ? "true" : "false");
      if (row.fault) { // a missing fault is shown once the user has tried to save, then kept up to date
        const faultMsg = this.checked ? this.faultProblem(row) : "";
        row.tr.querySelector(".ferr").textContent = faultMsg;
        row.fault.classList.toggle("is-invalid", !!faultMsg);
        row.fault.setAttribute("aria-invalid", faultMsg ? "true" : "false");
      }
    }
    summary() {
      if (!this.summaryEl) return;
      const totals = {}, chosen = this.rows.filter(r => r.ts.getValue());
      for (const r of chosen) { const it = this.items.get(r.ts.getValue()), v = Number(r.qty.value); if (it && v > 0) totals[it.unit] = (totals[it.unit] || 0) + v; }
      const parts = Object.entries(totals).map(([u, q]) => `${q} ${u}`);
      this.summaryEl.textContent = chosen.length ? `${chosen.length} line${chosen.length > 1 ? "s" : ""}${parts.length ? " · " + parts.join(" · ") : ""}` : "";
    }
    /** The first invalid field (to focus), checking every row; null when the lines can be posted. */
    invalid() {
      this.checked = true; this.refresh();
      for (const r of this.rows) {
        if (r.qty.classList.contains("is-invalid")) return r.qty;
        if (r.fault && r.fault.classList.contains("is-invalid")) return r.fault;
      }
      return null;
    }
  }
  window.LineEditor = LineEditor;

  const forms = [...document.querySelectorAll("form[data-lines-form]")];
  if (!forms.length) return;
  const json = (id, what) => JSON.parse(byId(id, what).textContent);
  const items = new Map(json("items-data", "picker options").map(i => [String(i.id), i]));
  const balances = json("balances-data", "stock balances");
  const alert = text => `<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>${esc(text)}</div></div></div>`;

  forms.forEach(form => {
    const hosts = [...form.querySelectorAll("[data-lines]")];
    if (!hosts.length) fail("a form[data-lines-form] has no [data-lines] editor");
    const errorBox = form.querySelector("[data-form-error]") || fail("a form[data-lines-form] has no [data-form-error] box");
    const editors = hosts.map(host => {
      const d = host.dataset, what = `data-* of [data-lines="${d.lines}"]`;
      const ed = new LineEditor({
        host, mode: d.mode, prefix: d.lines, items, balances,
        locSelect: d.loc ? byId(d.loc, what) : null,
        addLabel: d.addLabel, maxQty: Number(d.max) || 0, summaryEl: d.summary ? byId(d.summary, what) : null,
      });
      const initial = d.initial ? json(d.initial, what) : [];
      (initial.length ? initial : [{}]).forEach(line => ed.add(line));
      return ed;
    });
    const buttons = () => [...form.querySelectorAll("[type=submit]")];
    form.addEventListener("input", () => { errorBox.innerHTML = ""; });
    form.addEventListener("submit", e => {
      const bad = editors.map(ed => ed.invalid()).find(Boolean);
      if (bad) {
        e.preventDefault();
        errorBox.innerHTML = alert("Fix the highlighted lines first.");
        bad.focus();
        return;
      }
      buttons().forEach(b => { b.disabled = true; b.classList.add("btn-loading"); }); // one click, one save
    });
    window.addEventListener("pageshow", e => { // coming Back to a cached page: allow saving again
      if (e.persisted) buttons().forEach(b => { b.disabled = false; b.classList.remove("btn-loading"); });
    });
    if (errorBox.textContent.trim()) { errorBox.scrollIntoView({ block: "center" }); errorBox.focus({ preventScroll: true }); }
  });
})();
