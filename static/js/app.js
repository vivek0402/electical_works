/* Top-bar search: shows matching items and entries in the #gresults dropdown under the box. */
(function () {
  const box = document.getElementById("gsearch");
  const menu = document.getElementById("gresults");
  if (!box || !menu || !box.dataset.url) return;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let timer, active = -1, seq = 0;
  const links = () => [...menu.querySelectorAll("a")];
  const close = () => { menu.classList.remove("show"); active = -1; };
  box.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = box.value.trim(), mine = ++seq;
      if (q.length <= 2) return close();
      let d;
      try { d = await (await fetch(`${box.dataset.url}?q=${encodeURIComponent(q)}`)).json(); } catch (e) { return close(); }
      if (mine !== seq) return; // a newer search is already running
      const items = d.items.map(i => `<a class="dropdown-item" href="${esc(i.url)}"><span><span class="code">${esc(i.code)}</span><br>
        <small class="text-secondary">${esc(i.type)} · ${esc(i.desc)}${i.aliases.length ? " · also " + esc(i.aliases.join(", ")) : ""}</small></span></a>`);
      const entries = d.entries.map(e => `<a class="dropdown-item" href="${esc(e.url)}"><span class="code">${esc(e.number)}</span><span class="ms-2 text-secondary">${esc(e.label)}</span></a>`);
      menu.innerHTML = (items.length ? `<span class="dropdown-header">Items</span>${items.join("")}` : "")
        + (entries.length ? `<span class="dropdown-header">Entries</span>${entries.join("")}` : "")
        || `<span class="dropdown-item-text text-secondary">Nothing found for “${esc(q)}”.</span>`;
      menu.classList.add("show"); active = -1;
    }, 200);
  });
  box.addEventListener("keydown", e => {
    const all = links();
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); if (!all.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length;
      all.forEach((a, n) => a.classList.toggle("active", n === active));
      all[active].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      const target = all[active] || all[0];
      if (target) { e.preventDefault(); location.href = target.getAttribute("href"); }
    } else if (e.key === "Escape") { close(); }
  });
  document.addEventListener("click", e => { if (!box.parentElement.parentElement.contains(e.target)) close(); });
})();
