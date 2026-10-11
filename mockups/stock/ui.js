/* UI shell for the Tabler layout: page header, modal, toasts, global search, sortable/paged data tables, router. */

const view = () => document.getElementById("view");
const opt = (list, v) => list.map(o => Array.isArray(o) ? `<option value="${esc(o[0])}" ${o[0] === v ? "selected" : ""}>${esc(o[1])}</option>`
  : `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("");
const kindBadge = e => `<span class="badge badge-k k-${e.kind}">${KIND[e.kind]}</span>`;
const codeLink = c => `<a class="code" href="#item/${encodeURIComponent(c)}">${esc(c)}</a>`;
const entryLink = no => `<a class="code" href="#entry/${no}">${no}</a>`;
const qtyHtml = q => q === 0 ? `<span class="zero">0</span>` : q;
const icon = n => `<i class="ti ti-${n}"></i>`;
// Mockup: Export buttons download the sample files made by make_sample_exports.py from the same demo data.
const exportBtn = (file, label = "Export to Excel") =>
  `<a class="btn btn-outline-success" href="exports/${file}" download>${icon("file-spreadsheet")} ${label}</a>`;

function setHeader(pretitle, title, actions = "") {
  document.getElementById("page-header").innerHTML = `<div class="row g-2 align-items-center">
    <div class="col"><div class="page-pretitle">${pretitle}</div><h2 class="page-title">${title}</h2></div>
    ${actions ? `<div class="col-auto ms-auto d-print-none"><div class="btn-list">${actions}</div></div>` : ""}</div>`;
}

/* ---------- modal + toasts ---------- */
function openModal(html, size = "") {
  document.getElementById("modal-dialog").className = `modal-dialog modal-dialog-centered ${size}`;
  document.getElementById("modal-content").innerHTML = html;
  tabler.Modal.getOrCreateInstance(document.getElementById("modal")).show();
}
function closeModal() { tabler.Modal.getOrCreateInstance(document.getElementById("modal")).hide(); }
function toast(msg, kind = "success") {
  const el = document.createElement("div");
  el.className = "toast show"; el.setAttribute("role", "status");
  el.innerHTML = `<div class="toast-header"><span class="badge bg-${kind === "success" ? "green" : "red"} me-2"></span>
    <strong class="me-auto">${kind === "success" ? "Saved" : "Notice"}</strong><button type="button" class="btn-close" data-bs-dismiss="toast"></button></div>
    <div class="toast-body">${msg}</div>`;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.remove(), 5000);
}
let pendingToast = null;
const toastAfterNav = msg => { pendingToast = msg; };

/* ---------- data table: client-side sort + paging (the real app does this on the server) ---------- */
const DT = {};
/* columns: [{key, label, num, sort: row => value, html: row => cell html, cls}] */
function dataTable(id, cfg) {
  DT[id] = { page: 1, size: cfg.size || 10, sort: cfg.sort || null, dir: cfg.dir || "asc", ...(DT[id] || {}), cfg };
  return `<div id="dt-${id}"></div>`;
}
const resetPage = id => { if (DT[id]) DT[id].page = 1; };
function dtRender(id) {
  const t = DT[id], c = t.cfg;
  let rows = c.rows.slice();
  const sortCol = c.columns.find(x => x.key === t.sort);
  if (!sortCol) t.sort = null; // e.g. the sorted column was hidden by a filter
  if (t.sort) {
    const col = sortCol, val = col.sort || (r => r[col.key]);
    rows.sort((a, b) => { const x = val(a), y = val(b);
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "en", { numeric: true })) * (t.dir === "asc" ? 1 : -1); });
  }
  const total = rows.length, pages = Math.max(1, Math.ceil(total / t.size));
  t.page = Math.min(Math.max(1, t.page), pages);
  const from = (t.page - 1) * t.size, shown = c.paging === false ? rows : rows.slice(from, from + t.size);
  const th = col => `<th class="${col.num ? "num" : ""} ${col.nosort ? "" : "sortable"} ${t.sort === col.key ? "sort-" + t.dir : ""}"
    ${col.nosort ? "" : `onclick="dtSort('${id}','${col.key}')"`}>${col.label}</th>`;
  const pageBtn = (p, label, dis, act) => `<li class="page-item ${dis ? "disabled" : ""} ${act ? "active" : ""}">
    <a class="page-link" href="#" onclick="dtPage('${id}',${p});return false">${label}</a></li>`;
  let nums = [];
  for (let p = 1; p <= pages; p++) if (p === 1 || p === pages || Math.abs(p - t.page) <= 1) nums.push(p); else if (nums.at(-1) !== "…") nums.push("…");
  document.getElementById(`dt-${id}`).innerHTML = `<div class="table-responsive"><table class="table table-vcenter card-table table-striped">
      <thead><tr>${c.columns.map(th).join("")}</tr></thead>
      <tbody>${shown.map(r => `<tr class="${c.rowClass ? c.rowClass(r) : ""}">${c.columns.map(col =>
        `<td class="${col.num ? "num" : ""} ${col.cls || ""}">${col.html ? col.html(r) : esc(r[col.key] ?? "")}</td>`).join("")}</tr>`).join("")
        || `<tr><td colspan="${c.columns.length}" class="text-center text-secondary py-4">${c.empty || "Nothing to show."}</td></tr>`}</tbody>
    </table></div>
    ${c.paging === false ? "" : `<div class="card-footer d-flex align-items-center flex-wrap gap-2">
      <p class="m-0 text-secondary">Showing <span>${total ? from + 1 : 0}</span>–<span>${Math.min(from + t.size, total)}</span> of <span>${total}</span></p>
      <div class="ms-auto d-flex align-items-center gap-2"><select class="form-select form-select-sm w-auto" aria-label="Rows per page"
        onchange="DT['${id}'].size=+this.value;DT['${id}'].page=1;dtRender('${id}')">${opt([[10, "10 / page"], [25, "25 / page"], [50, "50 / page"]].map(([v, l]) => [String(v), l]), String(t.size))}</select>
      <ul class="pagination m-0">${pageBtn(t.page - 1, icon("chevron-left"), t.page === 1)}${nums.map(p => p === "…"
        ? `<li class="page-item disabled"><span class="page-link">…</span></li>` : pageBtn(p, p, false, p === t.page)).join("")}${pageBtn(t.page + 1, icon("chevron-right"), t.page === pages)}</ul></div></div>`}`;
}
function dtSort(id, key) { const t = DT[id]; t.dir = t.sort === key && t.dir === "asc" ? "desc" : "asc"; t.sort = key; dtRender(id); }
function dtPage(id, p) { DT[id].page = p; dtRender(id); }
const dtAll = () => Object.keys(DT).forEach(id => document.getElementById(`dt-${id}`) && dtRender(id));

/* ---------- global search (items by any code/spelling/description, entries by number/ref/party) ---------- */
function globalSearch(text) {
  const box = document.getElementById("gresults"), t = norm(text), k = key(text);
  if (t.length < 2) { box.classList.remove("show"); return; }
  const items = DB.items.filter(i => [i.code, ...i.aliases, i.desc, i.catRef].join(" ").toUpperCase().includes(t)
    || (k.length > 2 && [i.code, ...i.aliases].some(c => key(c).includes(k)))).slice(0, 6);
  const ents = byDateDesc(DB.entries).filter(e => [e.no, e.ref, e.party].join(" ").toUpperCase().includes(t)).slice(0, 4);
  box.innerHTML = (items.length ? `<span class="dropdown-header">Items</span>` + items.map(i => `<a class="dropdown-item" href="#item/${encodeURIComponent(i.code)}">
      <span><span class="code">${esc(i.code)}</span><br><small class="text-secondary">${esc(i.type)} · ${esc(i.desc)} · ${total(i.code)} ${i.unit} in stock</small></span></a>`).join("") : "")
    + (ents.length ? `<span class="dropdown-header">Entries</span>` + ents.map(e => `<a class="dropdown-item" href="#entry/${e.no}">
      <span>${kindBadge(e)} <span class="code">${e.no}</span> <small class="text-secondary">${fmt(e.date)} · ${esc(e.party || e.reason || "")}</small></span></a>`).join("") : "")
    || `<span class="dropdown-item-text text-secondary">No matches for "${esc(text)}"</span>`;
  box.classList.add("show");
}

/* ---------- router ---------- */
const ROUTES = {};
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
function route() {
  const [name, ...rest] = (location.hash.slice(1) || "dash").split("/");
  const arg = rest.length ? decodeURIComponent(rest.join("/")) : undefined;
  const navName = { "item-new": "items", "item-edit": "items", item: "items", entry: "moves" }[name] || name;
  document.querySelectorAll("#nav .nav-link").forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + navName));
  const menu = document.getElementById("sidebar-menu");
  if (menu.classList.contains("show")) tabler.Collapse.getOrCreateInstance(menu).hide();
  document.getElementById("gresults").classList.remove("show");
  for (const id in DT) delete DT[id].cfg;
  (ROUTES[name] || ROUTES.dash)(arg);
  for (const id of Object.keys(DT)) if (DT[id].cfg && document.getElementById(`dt-${id}`)) dtRender(id);
  const low = DB.items.filter(i => i.active && isLow(i)).length;
  document.getElementById("nav-low").textContent = low || "";
  document.getElementById("bell-count").textContent = low || "";
  if (pendingToast) { toast(pendingToast); pendingToast = null; }
  window.scrollTo(0, 0);
}
function startApp() {
  const g = document.getElementById("gsearch");
  g.addEventListener("input", () => globalSearch(g.value));
  g.addEventListener("keydown", ev => { if (ev.key === "Enter") { const a = document.querySelector("#gresults a"); if (a) { location.hash = a.getAttribute("href"); g.value = ""; } } });
  g.addEventListener("blur", () => setTimeout(() => document.getElementById("gresults").classList.remove("show"), 200));
  window.addEventListener("hashchange", route);
  route();
}
