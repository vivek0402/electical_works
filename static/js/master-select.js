/* Type-to-add pickers (mirrors masterPicker in mockups/service/ui.js).
   <select data-master-add="company|location|…" data-noun="supplier" data-url="…"> becomes a searchable Tom Select.
   Typing a name that isn't listed offers "＋ Add <name> as a new <noun>"; picking it posts to masters/add/
   (apps/inventory masters.master_add), selects the saved row and says so under the field. A name that is already
   listed (any capitals or spacing) is never offered for adding. */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clean = s => String(s || "").trim().replace(/\s+/g, " ");
  document.querySelectorAll("select[data-master-add]").forEach(select => {
    const form = select.form, kind = select.dataset.masterAdd, noun = select.dataset.noun || "name";
    const csrf = form && form.querySelector("input[name=csrfmiddlewaretoken]");
    const note = document.createElement("div");
    note.className = "form-hint mt-1";
    note.setAttribute("aria-live", "polite");
    const say = (html, cls) => { note.className = `form-hint mt-1 ${cls || ""}`; note.innerHTML = html; };
    const ts = new TomSelect(select, {
      maxOptions: 100, closeAfterSelect: true, allowEmptyOption: true, createOnBlur: false,
      createFilter: input => { const k = clean(input).toLowerCase(); return !!k && !Object.values(ts.options).some(o => String(o.text).toLowerCase() === k); },
      create(input, done) {
        const name = clean(input);
        say(`<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Adding ${esc(name)}…`, "text-secondary");
        fetch(select.dataset.url || "/masters/add/", {
          method: "POST", body: new URLSearchParams({ kind, name }), credentials: "same-origin",
          headers: { "X-CSRFToken": csrf ? csrf.value : "", "X-Requested-With": "XMLHttpRequest" },
        }).then(r => r.json()).then(res => {
          if (!res.ok) { say(`<i class="ti ti-alert-circle"></i> ${esc(res.error)}`, "text-danger"); return done(); }
          say(res.created
            ? `<i class="ti ti-circle-check"></i> Saved as a new ${esc(noun)}.`
            : `<i class="ti ti-info-circle"></i> ${esc(res.name)} was already saved, so it is selected.`, res.created ? "text-success" : "text-secondary");
          done({ value: String(res.id), text: res.name });
        }).catch(() => { say(`<i class="ti ti-alert-circle"></i> Could not add the ${esc(noun)}. Check the connection and try again.`, "text-danger"); done(); });
      },
      render: {
        option_create: d => `<div class="create"><div>＋ Add “${esc(clean(d.input))}”</div><small>Saves it as a new ${esc(noun)}</small></div>`,
        no_results: () => "", // the "Add …" row is the answer; a "no results" line beside it only confuses
      },
    });
    ts.wrapper.after(note);
  });
})();
