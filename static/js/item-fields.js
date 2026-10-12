/* Item form behaviour: searchable selects + live duplicate / look-alike code hint.
   window.initItemFields(root, {dropdownParent}) is safe to call more than once on the same root. */
(function () {
  window.initItemFields = function (root, opts) {
    opts = opts || {};
    if (!root) return;
    ["spare_type", "company", "fitting_type"].forEach(function (name) {
      const el = root.querySelector('select[name$="' + name + '"]');
      if (!el || el.tomselect || !window.TomSelect) return;
      const cfg = { allowEmptyOption: true };
      if (opts.dropdownParent) cfg.dropdownParent = opts.dropdownParent;
      new TomSelect(el, cfg);
    });

    const input = root.querySelector('input[name$="code"]');
    const hint = root.querySelector('[id$="code-hint"]');
    if (!input || !hint) return;
    let timer = null, seq = 0;

    async function check() {
      const mine = ++seq;
      const reset = function () {
        hint.textContent = "";
        hint.className = "form-hint";
        input.classList.remove("is-invalid");
      };
      try {
        const url = hint.dataset.url + "?code=" + encodeURIComponent(input.value) +
          "&original=" + encodeURIComponent(hint.dataset.original || "");
        const r = await fetch(url, { headers: { Accept: "application/json" } });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const d = await r.json();
        if (mine !== seq) return; // a newer keystroke superseded this reply
        hint.textContent = d.message || "";
        hint.className = d.status === "clash" ? "invalid-feedback d-block" : "form-hint";
        input.classList.toggle("is-invalid", d.status === "clash");
      } catch (e) {
        if (mine === seq) reset();
      }
    }

    root.checkCodeHint = check;
    if (input.dataset.hintBound) return;
    input.dataset.hintBound = "1";
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(root.checkCodeHint, 250);
    });
  };
})();
