/* Item-line editors for the service pages (Mark defective, Record visit). Same look and rules as the stock entry
   forms (static/js/entry-form.js): searchable item picker with look-alike codes, live availability at the chosen
   location, and an over-issue warning. Every element <div data-lines="<prefix>" data-mode="out|mark|collect"
   data-loc="<location select id>" data-initial="<json_script id>" data-summary="<id>" data-add-label="…"
   data-max="<most per line, optional>"> inside a
   <form data-lines-form> becomes an editor posting <prefix>_item, <prefix>_qty, <prefix>_batch, <prefix>_pkd and
   <prefix>_fault. The page also needs json_script blocks "items-data" and "balances-data". */
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

  class LineEditor {
    constructor({ host, mode, prefix, items, balances, locSelect, addLabel, summaryEl, maxQty }) {
      Object.assign(this, { host, mode, prefix, items, balances, locSelect, summaryEl, maxQty: maxQty || 1000000, rows: [] });
      host.innerHTML = `<div class="lines-wrap"><table class="table table-vcenter lines-table mb-0"><thead><tr>${HEADS[mode]
        .map((h, i) => `<th${i === 0 ? ' class="w-1"' : ""}>${h}</th>`).join("")}</tr></thead><tbody></tbody></table></div>
        <button type="button" class="btn btn-outline-primary mt-3 add-line"><i class="ti ti-plus"></i> ${esc(addLabel || "Add another item")}</button>`;
      this.body = host.querySelector("tbody");
      host.querySelector(".add-line").addEventListener("click", () => this.add({}, true));
      if (locSelect) locSelect.addEventListener("change", () => this.rows.forEach(r => this.refresh(r)));
    }
    name(field) { return `${this.prefix}_${field}`; }
    option(i) { return { ...i, value: String(i.id), hay: norm([i.code, ...i.aliases, i.desc, i.cat, i.type, i.company].join(" ")) }; }
    qtyCell() {
      return `<td data-label="Quantity" style="min-width:9rem"><div class="input-group"><input type="number" name="${this.name("qty")}" class="form-control qty"
        min="1" max="${this.maxQty}" step="1" inputmode="numeric" placeholder="0" aria-label="Quantity"><span class="input-group-text u">—</span></div>
        <div class="invalid-feedback d-block err"></div></td>`;
    }
    faultCell(placeholder) {
      return `<td data-label="Fault" class="c-fault"><input name="${this.name("fault")}" class="form-control fault" maxlength="200" placeholder="${placeholder}" aria-label="Fault"></td>`;
    }
    add(init = {}, focus = false) {
      const tr = document.createElement("tr"), row = { tr };
      const cells = {
        out: `<td data-label="Available" class="avail"></td>` + this.qtyCell(),
        mark: `<td data-label="Available" class="avail"></td>` + this.qtyCell() + this.faultCell("e.g. dead on arrival"),
        collect: this.qtyCell()
          + `<td data-label="Batch code"><input name="${this.name("batch")}" class="form-control batch" maxlength="40" placeholder="e.g. B2405" aria-label="Batch code"></td>`
          + `<td data-label="PKD (packed)"><input name="${this.name("pkd")}" class="form-control pkd" type="month" aria-label="PKD (packed)"></td>`
          + this.faultCell("e.g. no output"),
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
        onChange: () => this.refresh(row),
      });
      row.qty = tr.querySelector(".qty");
      row.qty.addEventListener("input", () => this.refresh(row));
      tr.querySelector(".remove").addEventListener("click", () => this.remove(row));
      this.rows.push(row);
      if (init.item && this.items.has(String(init.item))) row.ts.setValue(String(init.item), true);
      row.qty.value = init.qty || "";
      for (const f of ["batch", "pkd", "fault"]) { const el = tr.querySelector(`.${f}`); if (el) el.value = init[f] || ""; }
      this.number(); this.refresh(row);
      if (focus) setTimeout(() => row.ts.focus(), 0);
    }
    remove(row) {
      if (this.rows.length === 1) { row.ts.clear(); row.tr.querySelectorAll("input").forEach(i => { i.value = ""; }); this.refresh(row); return; }
      row.ts.destroy(); row.tr.remove(); this.rows.splice(this.rows.indexOf(row), 1); this.number(); this.summary();
    }
    number() { this.rows.forEach((r, n) => { r.tr.querySelector(".c-n").textContent = n + 1; }); }
    refresh(row) {
      const it = this.items.get(row.ts.getValue()), unit = it ? it.unit : "—";
      row.tr.querySelectorAll(".u").forEach(s => { s.textContent = unit; });
      row.tr.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}${it.cat && it.cat !== it.code ? ` · for ${it.cat}` : ""}` : "";
      const err = row.tr.querySelector(".err");
      err.textContent = ""; row.qty.classList.remove("is-invalid");
      if (Number(row.qty.value) > this.maxQty) { err.textContent = `At most ${this.maxQty} per line`; row.qty.classList.add("is-invalid"); }
      const avail = row.tr.querySelector(".avail");
      if (avail && this.locSelect) {
        if (!it) { avail.textContent = ""; } else {
          const n = this.balances[`${it.id}-${this.locSelect.value}`] || 0;
          const place = this.locSelect.options[this.locSelect.selectedIndex].text;
          avail.innerHTML = `<b>${n}</b> ${esc(unit)} <span class="text-secondary d-block small">at ${esc(place)}</span>`;
          if (Number(row.qty.value) > n && !err.textContent) { err.textContent = `Only ${n} ${unit} available`; row.qty.classList.add("is-invalid"); }
        }
      }
      this.summary();
    }
    summary() {
      if (!this.summaryEl) return;
      const totals = {}, chosen = this.rows.filter(r => r.ts.getValue());
      for (const r of chosen) { const it = this.items.get(r.ts.getValue()), v = Number(r.qty.value); if (it && v > 0) totals[it.unit] = (totals[it.unit] || 0) + v; }
      const parts = Object.entries(totals).map(([u, q]) => `${q} ${u}`);
      this.summaryEl.textContent = chosen.length ? `${chosen.length} item${chosen.length > 1 ? "s" : ""}${parts.length ? " · " + parts.join(" · ") : ""}` : "";
    }
    invalid() { return this.rows.find(r => r.qty.classList.contains("is-invalid")) || null; }
  }
  window.LineEditor = LineEditor;

  const form = document.querySelector("form[data-lines-form]");
  if (!form) return;
  const json = id => JSON.parse(document.getElementById(id).textContent);
  const items = new Map(json("items-data").map(i => [String(i.id), i]));
  const balances = json("balances-data");
  const editors = [...form.querySelectorAll("[data-lines]")].map(host => {
    const ed = new LineEditor({
      host, mode: host.dataset.mode, prefix: host.dataset.lines, items, balances,
      locSelect: host.dataset.loc ? document.getElementById(host.dataset.loc) : null,
      addLabel: host.dataset.addLabel, maxQty: Number(host.dataset.max) || 0, summaryEl: host.dataset.summary ? document.getElementById(host.dataset.summary) : null,
    });
    const initial = json(host.dataset.initial);
    (initial.length ? initial : [{}]).forEach(line => ed.add(line));
    return ed;
  });
  const errorBox = document.getElementById("form-error");
  form.addEventListener("input", () => { errorBox.innerHTML = ""; });
  form.addEventListener("submit", e => {
    const bad = editors.map(ed => ed.invalid()).find(Boolean);
    if (bad) {
      e.preventDefault();
      errorBox.innerHTML = `<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>Fix the highlighted quantities first.</div></div></div>`;
      bad.qty.focus();
      return;
    }
    const save = form.querySelector("button[type=submit]");
    save.disabled = true; save.classList.add("btn-loading"); // one click, one save
  });
  window.addEventListener("pageshow", e => { // coming Back to a cached page: allow saving again
    if (!e.persisted) return;
    const save = form.querySelector("button[type=submit]");
    save.disabled = false; save.classList.remove("btn-loading");
  });
  if (errorBox.textContent.trim()) { errorBox.scrollIntoView({ block: "center" }); errorBox.focus({ preventScroll: true }); }
})();
