/* Site picker on the New complaint page (searchable, fills contact + phone, "＋ New site" opens the modal) and the
   New site modal itself (also usable on the Sites page, where a saved site reloads the page). The modal posts to
   site_quick_create and gets the new site back as JSON. Like the Stock IN "Create new item" dialog. */
(function () {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const BS = window.bootstrap || (window.tabler && window.tabler.bootstrap);
  const $ = id => document.getElementById(id);

  // A server error under the complaint form: bring it into view and move focus to it.
  const serverError = $("form-error");
  if (serverError && serverError.textContent.trim()) { serverError.scrollIntoView({ block: "center" }); serverError.focus({ preventScroll: true }); }

  const modalEl = $("site-modal"), siteForm = $("site-form");
  if (!modalEl || !siteForm) return;
  const errBox = $("ns-err");
  const select = $("id_site");
  const dataEl = $("sites-data");
  const sites = new Map(dataEl ? JSON.parse(dataEl.textContent).map(s => [String(s.id), s]) : []);
  const option = s => ({ value: String(s.id), name: s.name, city: s.city, contact: s.contact, hay: `${s.name} ${s.city} ${s.contact}` });
  const showError = msg => {
    errBox.innerHTML = `<div class="alert alert-danger mb-0" role="alert"><div class="d-flex gap-2"><i class="ti ti-alert-circle"></i><div>${esc(msg)}</div></div></div>`;
  };
  const EXPIRED = "Your session expired. Reload the page.";
  let pending = null, picker = null;

  function openModal(name) {
    siteForm.reset();
    $("id_ns-name").value = name || "";
    errBox.textContent = "";
    BS.Modal.getOrCreateInstance(modalEl).show();
  }
  modalEl.addEventListener("shown.bs.modal", () => $($("id_ns-name").value ? "id_ns-city" : "id_ns-name").focus());
  modalEl.addEventListener("hidden.bs.modal", () => { if (pending) { pending(false); pending = null; } });
  const newButton = $("new-site-btn");
  if (newButton) newButton.addEventListener("click", () => { pending = null; openModal(""); });

  if (select) {
    const contact = $("id_contact_name"), phone = $("id_phone");
    const chosen = select.value;
    select.innerHTML = '<option value=""></option>'; // options come from sites-data (with city and contact)
    picker = new TomSelect(select, {
      options: [...sites.values()].map(option), items: chosen && sites.has(chosen) ? [chosen] : [], valueField: "value", labelField: "name",
      searchField: ["hay"], maxOptions: 50, closeAfterSelect: true, placeholder: "Type site name, city or contact…",
      create: (input, done) => { pending = done; openModal(input); },
      render: {
        option: d => `<div><span class="fw-medium">${esc(d.name)}</span><span class="opt-meta">${esc(d.city)}${d.contact ? " · " + esc(d.contact) : ""}</span></div>`,
        item: d => `<div>${esc(d.name)}, ${esc(d.city)}</div>`,
        option_create: d => `<div class="create">＋ New site <b>${esc(d.input)}</b>…</div>`,
        no_results: () => `<div class="no-results">No saved site. Keep typing to add it.</div>`,
      },
      onChange: v => { const s = sites.get(String(v)); if (s) { contact.value = s.contact; phone.value = s.phone_display; } },
    });
  }

  siteForm.addEventListener("submit", async e => {
    e.preventDefault();
    const button = siteForm.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const r = await fetch(siteForm.dataset.url, { method: "POST", body: new FormData(siteForm), headers: { Accept: "application/json" }, redirect: "manual" });
      // A logged-out session answers with a redirect to the login page, a 403 or an HTML page, not JSON.
      if (!r.ok || !(r.headers.get("content-type") || "").includes("application/json")) { showError(EXPIRED); return; }
      const res = await r.json();
      if (!res.ok) { showError(res.error); return; }
      if (!picker) { location.reload(); return; } // Sites page: show the new row
      sites.set(String(res.site.id), res.site);
      const done = pending; pending = null;
      BS.Modal.getInstance(modalEl).hide();
      if (done) done(option(res.site)); else picker.addOption(option(res.site));
      picker.setValue(String(res.site.id)); // fills contact and phone (onChange)
    } catch (err) {
      showError("Could not save the site. Check the connection and try again.");
    } finally {
      button.disabled = false;
    }
  });
})();
