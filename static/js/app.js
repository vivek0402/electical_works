/* Top-bar search: shows matching items, entries, complaints, sites and defective pieces in the #gresults dropdown. */
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
      const complaints = (d.complaints || []).map((c, n) => `<a class="dropdown-item" role="option" id="gs-c${n}" href="${esc(c.url)}"><span><span class="code">${esc(c.number)}</span> <span class="text-secondary">${esc(c.status)}</span><br>
        <small class="text-secondary">${esc(c.label)}${c.ref ? ` · <span class="code">${esc(c.ref)}</span>` : ""}</small></span></a>`);
      const sites = (d.sites || []).map((s, n) => `<a class="dropdown-item" role="option" id="gs-s${n}" href="${esc(s.url)}"><span><i class="ti ti-building" aria-hidden="true"></i> ${esc(s.name)}<br><small class="text-secondary">${esc(s.label)}</small></span></a>`);
      const pieces = (d.pieces || []).map((p, n) => `<a class="dropdown-item" role="option" id="gs-p${n}" href="${esc(p.url)}"><span><span class="code">${esc(p.tag)}</span> <span class="text-secondary">${esc(p.status)}</span><br><small class="text-secondary">${esc(p.label)}</small></span></a>`);
      // [heading, rows, one, many] for the dropdown and the screen-reader count
      const groups = [["Items", items, "item", "items"], ["Entries", entries, "entry", "entries"], ["Complaints", complaints, "complaint", "complaints"],
        ["Sites", sites, "site", "sites"], ["Defective pieces", pieces, "piece", "pieces"]].filter(([, list]) => list.length);
      menu.innerHTML = groups.map(([title, list]) => `<span class="dropdown-header" role="presentation">${title}</span>${list.join("")}`).join("")
        || `<span class="dropdown-item-text text-secondary" role="presentation">Nothing found for “${esc(q)}”.</span>`;
      menu.classList.add("show"); active = -1; box.setAttribute("aria-expanded", "true");
      announce(groups.length
        ? groups.map(([, list, one, many]) => `${list.length} ${list.length > 1 ? many : one}`).join(", ")
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
