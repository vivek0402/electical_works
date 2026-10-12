/* Item lines for the Stock IN / OUT / Transfer / Adjust forms (mirrors mockups/stock/forms.js).
   Data comes from json_script blocks on the page; each line posts line_item / line_qty / line_batch / line_pkd. */
(function () {
  const $ = id => document.getElementById(id);
  const data = id => JSON.parse($(id).textContent);
  const form = $("entry-form");
  if (!form) return;
  const mode = form.dataset.mode, body = $("lines");
  const items = new Map(data("items-data").map(i => [String(i.id), i]));
  const balances = data("balances-data"), parties = data("parties-data");
  const BS = window.bootstrap || (window.tabler && window.tabler.bootstrap);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Same rules as apps/inventory/normalise.normalise_code and search_key.
  const norm = s => String(s || "").toUpperCase().replace(/[`'"]/g, "").replace(/\s+/g, " ").replace(/^[ .,;:]+|[ .,;:]+$/g, "");
  const lookKey = s => norm(s).replace(/O/g, "0").replace(/I/g, "1")
    .replace(/(^|[^A-Z0-9])0+([0-9]+)(?=[^A-Z0-9]|$)/g, "$1$2").replace(/[^A-Z0-9]/g, "");
  const locSelect = $("id_location");
  const have = id => balances[`${id}-${locSelect.value}`] || 0;
  const locName = () => locSelect.options[locSelect.selectedIndex].text;
  const option = i => ({ ...i, value: String(i.id), hay: norm([i.code, ...i.aliases, i.desc, i.cat, i.type, i.company].join(" ")) });
  const rows = [];

  function picker(select, row) {
    return new TomSelect(select, {
      options: [...items.values()].map(option), valueField: "value", labelField: "code", maxOptions: 60,
      closeAfterSelect: true, openOnFocus: false, placeholder: "Type code, old spelling or description…",
      score(search) { // text anywhere, or a look-alike code (O/0, I/1, hyphens, leading zeros)
        const t = norm(search), k = lookKey(search);
        return it => !t ? 1 : it.hay.includes(t) ? 2 : (k.length > 2 && it.keys.includes(k)) ? 1.5 : 0;
      },
      create: mode === "in" ? (input, done) => openNewItem(norm(input), done) : false,
      render: {
        option: d => `<div><span class="opt-code">${esc(d.code)}</span><span class="opt-meta">${esc(d.type)} · ${esc(d.desc)}${d.cat && d.cat !== d.code ? ` · for ${esc(d.cat)}` : ""} · ${esc(d.company)}</span></div>`,
        item: d => `<div>${esc(d.code)}</div>`,
        option_create: d => `<div class="create">＋ Create new item <b>${esc(norm(d.input))}</b>…</div>`,
        no_results: () => `<div class="no-results">No matching item${mode === "in" ? " (type the full code to create it)" : ""}.</div>`,
      },
      onChange: () => refresh(row),
    });
  }

  function qtyCell(label, min) {
    return `<td data-label="${label}" style="min-width:9rem"><div class="input-group"><input type="number" name="line_qty" class="form-control qty" min="${min}" max="1000000" step="1"
      inputmode="numeric" placeholder="0" aria-label="${label}"><span class="input-group-text u">—</span></div><div class="invalid-feedback d-block err"></div></td>`;
  }

  function addRow(init = {}, focus = false) {
    const tr = document.createElement("tr"), row = { tr };
    const hidden = (mode === "in" ? "" : `<input type="hidden" name="line_batch" value=""><input type="hidden" name="line_pkd" value="">`)
      + (mode === "adj" ? `<input type="hidden" name="line_expected" class="expected" value="">` : "");
    tr.innerHTML = `<td class="c-n text-secondary"></td><td class="c-item"><select name="line_item" class="form-select" aria-label="Item"><option value=""></option></select>${hidden}<small class="form-hint line-meta"></small></td>` + {
      in: qtyCell("Quantity", 1) + `<td data-label="Batch code"><input name="line_batch" class="form-control" maxlength="40" placeholder="e.g. B2405" aria-label="Batch code"></td>
          <td data-label="PKD (packed)"><input name="line_pkd" class="form-control" type="month" aria-label="PKD (packed)"></td>`,
      out: `<td data-label="Available" class="avail"></td>` + qtyCell("Quantity", 1),
      trf: `<td data-label="Available" class="avail"></td>` + qtyCell("Quantity", 1),
      adj: `<td data-label="System qty" class="avail"></td>` + qtyCell("Counted qty", 0) + `<td data-label="Difference" class="avail diff"></td>`,
    }[mode] + `<td class="c-rm"><button type="button" class="btn btn-icon btn-ghost-danger remove" title="Remove line" aria-label="Remove line"><i class="ti ti-trash"></i></button></td>`;
    body.appendChild(tr);
    row.ts = picker(tr.querySelector("select"), row);
    row.qty = tr.querySelector(".qty");
    row.qty.addEventListener("input", () => refresh(row));
    tr.querySelector(".remove").onclick = () => removeRow(row);
    rows.push(row);
    if (init.item && items.has(String(init.item))) row.ts.setValue(String(init.item), true);
    row.qty.value = init.qty || "";
    if (mode === "in") { tr.querySelector("[name=line_batch]").value = init.batch || ""; tr.querySelector("[name=line_pkd]").value = init.pkd || ""; }
    number(); refresh(row);
    if (focus) setTimeout(() => row.ts.focus(), 0);
  }

  function removeRow(row) {
    if (rows.length === 1) { row.ts.clear(); row.tr.querySelectorAll("input:not([type=hidden])").forEach(i => i.value = ""); refresh(row); return; }
    row.ts.destroy(); row.tr.remove(); rows.splice(rows.indexOf(row), 1); number(); summary();
  }

  const number = () => rows.forEach((r, n) => r.tr.querySelector(".c-n").textContent = n + 1);

  function refresh(row) {
    const it = items.get(row.ts.getValue()), unit = it ? it.unit : "—";
    row.tr.querySelectorAll(".u").forEach(s => s.textContent = unit);
    row.tr.querySelector(".line-meta").textContent = it ? `${it.type} · ${it.desc}${it.cat && it.cat !== it.code ? ` · for ${it.cat}` : ""}` : "";
    const err = row.tr.querySelector(".err");
    err.textContent = ""; row.qty.classList.remove("is-invalid");
    const avail = row.tr.querySelector(".avail:not(.diff)");
    if (avail) {
      if (!it) {
        avail.textContent = "";
        const diff = row.tr.querySelector(".diff");
        if (diff) diff.textContent = "";
        const expected = row.tr.querySelector(".expected");
        if (expected) expected.value = "";
      } else {
        const n = have(it.id);
        if (mode === "adj") row.tr.querySelector(".expected").value = n; // the server refuses the count if this changed
        avail.innerHTML = `<b>${n}</b> ${esc(unit)} <span class="text-secondary d-block small">at ${esc(locName())}</span>`;
        if (mode === "adj") {
          const counted = row.qty.value === "" ? null : Number(row.qty.value), d = counted === null ? null : counted - n;
          row.tr.querySelector(".diff").innerHTML = d === null ? "" :
            `<span class="badge ${d < 0 ? "bg-red-lt" : d > 0 ? "bg-green-lt" : "bg-secondary-lt"}">${d > 0 ? "+" : ""}${d} ${esc(unit)}</span>`;
        } else if (Number(row.qty.value) > n) {
          err.textContent = `Only ${n} ${unit} available`; row.qty.classList.add("is-invalid");
        }
      }
    }
    summary();
  }

  function summary() {
    const totals = {}, chosen = rows.filter(r => r.ts.getValue());
    if (mode !== "adj") for (const r of chosen) { const it = items.get(r.ts.getValue()), v = Number(r.qty.value); if (it && v > 0) totals[it.unit] = (totals[it.unit] || 0) + v; }
    const parts = Object.entries(totals).map(([u, q]) => `${q} ${u}`);
    $("lines-summary").textContent = chosen.length ? `${chosen.length} item${chosen.length > 1 ? "s" : ""}${parts.length ? " · " + parts.join(" · ") : ""}` : "";
  }

  // Subtype radios: show the matching "who" field and fill name suggestions.
  function subtypeChanged() {
    const picked = form.querySelector("input[name=subtype]:checked");
    if (!picked) return;
    form.querySelectorAll("[data-show]").forEach(el => el.hidden = el.dataset.show !== picked.value);
    const label = $("party-label");
    if (label) label.textContent = { SITE: "Site / customer", TECH: "Technician", OTHER: "Name" }[picked.value];
    $("parties").innerHTML = (parties[picked.value] || []).map(p => `<option value="${esc(p)}">`).join("");
  }
  form.querySelectorAll("input[name=subtype]").forEach(r => r.addEventListener("change", subtypeChanged));
  subtypeChanged();

  locSelect.addEventListener("change", () => rows.forEach(refresh));
  $("add-line").onclick = () => addRow({}, true);
  const initial = data("initial-lines");
  (initial.length ? initial : [{}]).forEach(l => addRow(l));

  // A server error stays until the user changes something.
  form.addEventListener("input", () => { $("form-error").innerHTML = ""; });

  // Client-side check before posting; the server checks everything again.
  form.addEventListener("submit", e => {
    const bad = rows.find(r => r.qty.classList.contains("is-invalid"));
    if (bad) {
      e.preventDefault();
      $("form-error").innerHTML = `<div class="alert alert-danger" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>Fix the highlighted quantities first.</div></div></div>`;
      bad.qty.focus();
      return;
    }
    const save = form.querySelector("button[type=submit]");
    save.disabled = true; save.classList.add("btn-loading"); // one click, one entry
  });
  window.addEventListener("pageshow", e => { // coming Back to a cached page: allow saving again
    if (!e.persisted) return;
    const save = form.querySelector("button[type=submit]");
    save.disabled = false; save.classList.remove("btn-loading");
  });

  // A server error is shown under the form: bring it into view and move focus to it.
  const serverError = $("form-error");
  if (serverError.textContent.trim()) { serverError.scrollIntoView({ block: "center" }); serverError.focus({ preventScroll: true }); }

  // Quick "create item" (Stock IN only).
  const niForm = $("new-item-form");
  if (!niForm) return;
  const modalEl = $("new-item-modal");
  // No dropdownParent: Tom Select only positions a dropdown itself when it is moved to <body>. Left inside its
  // .ts-wrapper (within .modal-content) it opens right under its control, stacks above the modal and keeps focus.
  window.initItemFields(niForm);
  const selects = [...niForm.querySelectorAll("select")].filter(s => s.tomselect);
  const defaults = new Map(selects.map(s => [s, s.tomselect.getValue()]));
  let pending = null;

  function openNewItem(code, done) {
    pending = done;
    niForm.reset();
    selects.forEach(s => s.tomselect.setValue(defaults.get(s), true));
    niForm.querySelectorAll(".is-invalid").forEach(el => el.classList.remove("is-invalid"));
    $("id_qi-code").value = code;
    $("ni-err").textContent = "";
    niForm.checkCodeHint();
    BS.Modal.getOrCreateInstance(modalEl).show();
  }
  modalEl.addEventListener("shown.bs.modal", () => $("id_qi-code").focus());
  modalEl.addEventListener("hidden.bs.modal", () => { if (pending) { pending(false); pending = null; } });

  niForm.addEventListener("submit", async e => {
    e.preventDefault();
    const button = niForm.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const r = await fetch(niForm.dataset.url, { method: "POST", body: new FormData(niForm), headers: { Accept: "application/json" } });
      const res = await r.json();
      if (!res.ok) { $("ni-err").textContent = res.error; return; }
      items.set(String(res.item.id), res.item);
      rows.forEach(row => row.ts.addOption(option(res.item)));
      const done = pending; pending = null;
      BS.Modal.getInstance(modalEl).hide();
      if (done) done(option(res.item));
    } catch (err) {
      $("ni-err").textContent = "Could not save the item. Check the connection and try again.";
    } finally {
      button.disabled = false;
    }
  });
})();
