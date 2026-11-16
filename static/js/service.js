/* Small behaviours shared by the complaints and defectives pages:
   - <select data-ts> becomes a Tom Select (multi-selects get remove buttons);
   - in a form, a [data-tick-all] box ticks every [data-tick] box, [data-tick-count] shows how many are ticked
     (or its data-empty-text when none), and a [data-bulk] bar is shown only while something is ticked;
   - [data-outcome] radios show the location field (#w-sloc) only for Replaced / Repaired, with a hint;
     the hidden field is also disabled, so it is never sent;
   - forms marked [data-once] disable their submit button after the first click;
   - a .modal[data-show-on-load] opens when the page loads (it holds an error from the last submit);
   - the Summary card of the New complaint and Record visit forms is filled from the fields (display only);
   - select[data-reload-company] (New batch) reloads the page for the chosen company, keeping the note. */
(function () {
  const BS = window.bootstrap || (window.tabler && window.tabler.bootstrap);

  document.querySelectorAll("select[data-ts]").forEach(s => new TomSelect(s, {
    maxOptions: 100, allowEmptyOption: true, closeAfterSelect: !s.multiple, plugins: s.multiple ? ["remove_button"] : [],
  }));

  document.querySelectorAll("form").forEach(form => {
    const all = form.querySelector("input[data-tick-all]");
    const counters = form.querySelectorAll("[data-tick-count]");
    const bulk = form.querySelector("[data-bulk]");
    if (!all && !counters.length && !bulk) return;
    const boxes = () => [...form.querySelectorAll("input[data-tick]:not(:disabled)")];
    const update = () => {
      const n = boxes().filter(b => b.checked).length;
      counters.forEach(c => { c.textContent = n ? `${n} piece${n > 1 ? "s" : ""} ticked` : (c.dataset.emptyText || ""); });
      if (bulk) bulk.hidden = n === 0;
      if (all) all.checked = n > 0 && n === boxes().length;
    };
    if (all) all.addEventListener("change", () => { boxes().forEach(b => { b.checked = all.checked; }); update(); });
    form.addEventListener("change", e => { if (e.target.matches("input[data-tick]")) update(); });
    update();
  });

  const HINTS = {
    REPLACED: "Posts a Stock IN (replacement from the company) into the chosen good-stock location, so its stock goes up.",
    REPAIRED: "Posts a Stock IN (repaired piece back from the company) into the chosen good-stock location.",
    REJECTED_RETURNED: "The company sent the piece back. It returns to the Defective store; you can batch it again or scrap it.",
    REJECTED_SCRAPPED: "The company kept and scrapped it. Nothing is posted: the piece already left with the dispatch.",
  };
  const outcomes = [...document.querySelectorAll("input[data-outcome]")];
  const showOutcome = () => {
    const picked = outcomes.find(r => r.checked);
    const good = !!picked && (picked.value === "REPLACED" || picked.value === "REPAIRED");
    const wrap = document.getElementById("w-sloc"), hint = document.getElementById("settle-hint");
    if (wrap) {
      wrap.hidden = !good;
      wrap.querySelectorAll("select").forEach(s => { s.disabled = !good; });
    }
    if (hint) hint.textContent = picked ? HINTS[picked.value] : "";
  };
  outcomes.forEach(r => r.addEventListener("change", showOutcome));
  if (outcomes.length) showOutcome();

  document.querySelectorAll("form[data-once]").forEach(form => form.addEventListener("submit", () => {
    const b = form.querySelector("button[type=submit]");
    if (b) { b.disabled = true; b.classList.add("btn-loading"); }
  }));
  window.addEventListener("pageshow", e => {
    if (!e.persisted) return;
    document.querySelectorAll("form[data-once] button[type=submit]").forEach(b => { b.disabled = false; b.classList.remove("btn-loading"); });
  });

  document.querySelectorAll("select[data-reload-company]").forEach(s => s.addEventListener("change", () => {
    const note = document.getElementById("b-note");
    const query = new URLSearchParams({ company: s.value, note: note ? note.value : "" });
    window.location.assign(`?${query}`);
  }));

  // Pieces list: the "Add to draft batch" dialog follows the ticked pieces. Drafts of other companies are hidden,
  // the first remaining draft is picked, and ticks that span companies show the refusal and disable the button.
  const batchModal = document.querySelector("[data-batch-modal]");
  if (batchModal) batchModal.addEventListener("show.bs.modal", () => {
    const form = batchModal.closest("form");
    const companies = [...new Set([...form.querySelectorAll("input[data-tick]:checked")].map(b => b.dataset.company))];
    const mixed = companies.length > 1;
    batchModal.querySelector("[data-batch-mixed]").hidden = !mixed;
    batchModal.querySelector("[data-batch-mixed-count]").textContent = companies.length;
    batchModal.querySelector("[data-batch-hint]").hidden = mixed;
    batchModal.querySelector("[data-batch-submit]").disabled = mixed;
    batchModal.querySelector(".form-selectgroup").hidden = mixed;
    let first = null;
    batchModal.querySelectorAll("[data-draft]").forEach(label => {
      const radio = label.querySelector("input");
      const show = companies.length === 1 && radio.dataset.company === companies[0];
      label.hidden = !show;
      radio.disabled = !show;
      if (show && !first) first = radio;
    });
    (first || batchModal.querySelector("input[value=new]")).checked = true;
  });


  // The Summary card beside the New complaint and Record visit forms (display only: nothing here is posted or
  // validated). It repeats what has been entered so far, and marks a required value that is still missing.
  (function () {
    const form = document.querySelector("form.b-form[data-summary-form], form[data-visit-form]");
    if (!form) return;
    const $ = id => document.getElementById(id);
    const put = (id, text) => {
      const el = $(id);
      if (!el) return;
      el.textContent = text || el.dataset.need || el.dataset.none || "";
      el.classList.toggle("need", !text && !!el.dataset.need);
    };
    const picked = el => (el && el.value ? el.options[el.selectedIndex].text.trim() : "");
    const many = el => el ? [...el.selectedOptions].map(o => o.text.trim()).filter(Boolean).join(", ") : "";
    const date = el => (el && el.value ? el.value.split("-").reverse().join("-") : "");
    const checked = name => { const r = form.querySelector(`input[name=${name}]:checked`); return r ? r.parentElement.textContent.trim() : ""; };
    const refresh = () => {
      if (form.hasAttribute("data-visit-form")) {
        put("sum-date", date($("id_visit_date")));
        put("sum-techs", many($("id_technicians")));
        put("sum-parts", ($("parts-summary") || {}).textContent.trim() || "None");
        put("sum-collected", ($("collect-summary") || {}).textContent.trim() || "None");
        put("sum-next", checked("next_status"));
        return;
      }
      const site = form.querySelector("#id_site + .ts-wrapper .item");
      put("sum-site", site ? site.textContent.trim() : "");
      put("sum-company", picked($("id_company")));
      put("sum-priority", checked("priority"));
      put("sum-date", date($("id_reported_on")));
      put("sum-techs", many($("id_technicians")));
    };
    form.addEventListener("input", refresh);
    form.addEventListener("change", refresh);
    // Tom Select drops the chosen option into the original select and fires change; the site picker (built
    // later by site-picker.js) is read from its own control, so look again shortly after it changes.
    form.addEventListener("click", () => setTimeout(refresh, 0));
    form.addEventListener("keyup", () => setTimeout(refresh, 0));
    ["parts-summary", "collect-summary"].forEach(id => {
      const el = $(id);
      if (el) new MutationObserver(refresh).observe(el, { childList: true, characterData: true, subtree: true });
    });
    setTimeout(refresh, 50);
  })();

  const pending = document.querySelector(".modal[data-show-on-load]");
  if (pending && BS) BS.Modal.getOrCreateInstance(pending).show();
  const settleErr = document.getElementById("settle-err");
  if (settleErr) settleErr.focus();
})();
