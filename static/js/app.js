/* Top-bar search: shows matching items and entries in the #gresults dropdown under the box. */
(function () {
  const box = document.getElementById("gsearch");
  const menu = document.getElementById("gresults");
  const status = document.getElementById("gstatus");
  if (!box || !menu || !box.dataset.url) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let timer, active = -1, seq = 0;
  const isOpen = () => menu.classList.contains("show");
  const links = () => [...menu.querySelectorAll("a")];
  const announce = t => { if (status) status.textContent = t; };
  const close = () => {
    menu.classList.remove("show"); active = -1;
    box.setAttribute("aria-expanded", "false"); box.removeAttribute("aria-activedescendant");
  };
  const clear = () => { menu.innerHTML = ""; close(); };
  box.addEventListener("input", () => {
    clearTimeout(timer);
    clear(); announce("");   // old links must never be followable while a new search is pending
    const mine = ++seq;
    timer = setTimeout(async () => {
      const q = box.value.trim();
      if (q.length <= 2) return;
      let d;
      try {
        const r = await fetch(`${box.dataset.url}?q=${encodeURIComponent(q)}`);
        if (!r.ok) return;
        d = await r.json();
      } catch (e) { return; }
      if (mine !== seq) return; // a newer search is already running
      const items = d.items.map((i, n) => `<a class="dropdown-item" role="option" id="gs-i${n}" href="${esc(i.url)}"><span><span class="code">${esc(i.code)}</span><br>
        <small class="text-secondary">${esc(i.type)} · ${esc(i.desc)}${i.aliases.length ? " · also " + esc(i.aliases.join(", ")) : ""}</small></span></a>`);
      const entries = d.entries.map((e, n) => `<a class="dropdown-item" role="option" id="gs-e${n}" href="${esc(e.url)}"><span class="code">${esc(e.number)}</span><span class="ms-2 text-secondary">${esc(e.label)}</span></a>`);
      menu.innerHTML = (items.length ? `<span class="dropdown-header" role="presentation">Items</span>${items.join("")}` : "")
        + (entries.length ? `<span class="dropdown-header" role="presentation">Entries</span>${entries.join("")}` : "")
        || `<span class="dropdown-item-text text-secondary" role="presentation">Nothing found for “${esc(q)}”.</span>`;
      menu.classList.add("show"); active = -1; box.setAttribute("aria-expanded", "true");
      announce(items.length || entries.length
        ? [items.length ? `${items.length} item${items.length > 1 ? "s" : ""}` : "", entries.length ? `${entries.length} entr${entries.length > 1 ? "ies" : "y"}` : ""].filter(Boolean).join(", ")
        : "Nothing found");
    }, 200);
  });
  box.addEventListener("keydown", e => {
    if (!isOpen()) return;
    const all = links();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); if (!all.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
      all.forEach((a, n) => { a.classList.toggle("active", n === active); a.setAttribute("aria-selected", n === active ? "true" : "false"); });
      box.setAttribute("aria-activedescendant", all[active].id);
      all[active].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      const target = all[active] || all[0];
      if (target) { e.preventDefault(); location.href = target.getAttribute("href"); }
    } else if (e.key === "Escape") { close(); }
  });
  document.addEventListener("click", e => { if (!box.closest(".global-search").contains(e.target)) close(); });
})();
