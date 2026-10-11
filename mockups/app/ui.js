/* SVKML mockup UI shell: router, header (system switcher, sub-nav, user switch), shared widgets. */

const ROUTES = {};          // "sys/screen" -> render(arg)
const SUBNAV = {};          // sys -> () => [[hash, label], ...]
const SYSTEMS = [["stock", "① Stock"], ["def", "② Defective pieces"], ["cmp", "③ Complaints"]];
const view = () => document.getElementById("view");
let flash = null;

function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
function setFlash(msg, err = false) { flash = { msg, err }; }
function flashHtml() {
  if (!flash) return "";
  const f = flash; flash = null;
  return `<article class="flash ${f.err ? "err" : ""}">${f.msg}</article>`;
}
function openDlg(html) { document.getElementById("dlg-body").innerHTML = html; document.getElementById("dlg").showModal(); }
function closeDlg() { document.getElementById("dlg").close(); }
const opts = (list, sel) => list.map(o => Array.isArray(o)
  ? `<option value="${esc(o[0])}" ${o[0] === sel ? "selected" : ""}>${esc(o[1])}</option>`
  : `<option ${o === sel ? "selected" : ""}>${esc(o)}</option>`).join("");
const codeLink = code => `<a class="code" href="#stock/item/${encodeURIComponent(code)}">${esc(code)}</a>`;
const entryLink = no => no ? `<a class="code" href="#stock/entry/${no}">${no}</a>` : "";
const pieceBadge = s => `<span class="badge s-${s}">${PIECE_STATUS[s]}</span>`;
const cmpBadge = s => `<span class="badge c-${s}">${CMP_STATUS[s]}</span>`;
const ageBadge = d => `<span class="age ${ageClass(d)}">${d} d</span>`;

function switchUser(name) {
  ME = name;
  setFlash(`You are now <strong>${ME}</strong> (${USERS[ME].toLowerCase()}).`);
  go(isTech() ? "#cmp/mine" : "#home");
}

/* ------------------------------ Router ------------------------------ */
function route() {
  const parts = (location.hash.slice(1) || "home").split("/");
  const sys = parts[0], screen = parts[1] || "", arg = parts.length > 2 ? decodeURIComponent(parts.slice(2).join("/")) : undefined;
  if (isTech() && sys === "def") { setFlash("Technicians record defectives from a complaint visit.", true); return go("#cmp/mine"); }
  document.getElementById("systems").innerHTML = SYSTEMS.filter(([s]) => !(isTech() && s === "def"))
    .map(([s, label]) => `<a href="#${s}" class="${s === sys ? "on" : ""}">${label}</a>`).join("");
  const sub = SUBNAV[sys] ? SUBNAV[sys]() : [];
  const here = "#" + parts.slice(0, 2).join("/");
  document.getElementById("subnav").innerHTML = sub.length
    ? `<ul>${sub.map(([h, l]) => `<li><a href="${h}" class="${h === here || (h === "#" + sys && !screen) ? "on" : ""}">${l}</a></li>`).join("")}</ul>` : "";
  const fn = ROUTES[`${sys}/${screen}`] || ROUTES[sys] || renderHome;
  fn(arg);
  window.scrollTo(0, 0);
}
function start() {
  document.getElementById("itemlist").innerHTML = ITEMS.flatMap(i =>
    [`<option value="${esc(i.code)}">${esc(TYPE_LABEL[i.type] + " · " + i.desc)}</option>`,
     ...i.aliases.map(a => `<option value="${esc(a)}">→ ${esc(i.code)}</option>`)]).join("");
  document.getElementById("who").value = ME;
  window.addEventListener("hashchange", route);
  route();
}

/* ------------------------------ Home: the three systems ------------------------------ */
function renderHome() {
  if (isTech()) return go("#cmp/mine");
  const fresh = sum(ITEMS.filter(i => i.unit === "NOS"), i => totalBalance(i.code, "FRESH"));
  const low = ITEMS.filter(i => i.reorder > 0 && totalBalance(i.code, "FRESH") <= i.reorder).length;
  const atOffice = pieces.filter(p => IN_LEDGER.includes(p.status)).length;
  const withWipro = pieces.filter(p => p.status === "SENT_TO_WIPRO").length;
  const open = complaints.filter(c => c.status !== "CLOSED");
  view().innerHTML = `${flashHtml()}
    <h1>Hello, ${ME}</h1>
    <div class="systems-home">
      <a class="sys-tile t-stock" href="#stock"><h2>① Stock</h2><p>Stock IN / OUT, transfers, current stock</p>
        <div class="stats"><span><b>${fresh}</b>NOS fresh</span><span><b>${low}</b>low stock</span><span><b>${entries.filter(e => e.date === today()).length}</b>entries today</span></div></a>
      <a class="sys-tile t-def" href="#def"><h2>② Defective pieces</h2><p>Every failed part, return batches to Wipro</p>
        <div class="stats"><span><b>${atOffice}</b>at office</span><span><b>${withWipro}</b>with Wipro</span><span><b>${batches.filter(b => b.status === "DRAFT").length}</b>draft batches</span></div></a>
      <a class="sys-tile t-cmp" href="#cmp"><h2>③ Complaints</h2><p>File, assign, visits, close</p>
        <div class="stats"><span><b>${open.length}</b>open</span><span><b>${open.filter(c => c.status === "NOT_ATTENDED").length}</b>not attended</span><span><b>${open.filter(c => ageDays(c) > 15).length}</b>over 15 days</span></div></a>
    </div>
    <h3>Quick actions</h3>
    <div class="bigbtns">
      <a href="#stock/in" role="button" class="btn-in">⬇ Stock IN<small>Fresh from Wipro</small></a>
      <a href="#stock/out" role="button" class="btn-out">⬆ Stock OUT<small>Issue to site</small></a>
      <a href="#def/record" role="button" class="btn-def">♻ Record defectives<small>Failed parts brought in</small></a>
      <a href="#cmp/new" role="button" class="btn-cmp">＋ New complaint<small>From Wipro / phone</small></a>
    </div>`;
}

/* ------------------------------ Shared item-lines editor ------------------------------ */
/* opts: { avail: () => ({loc, bucket}) | null, extra: ["batch","pkd","fault"], create: bool, title } */
const editors = {};
const EXTRA = { batch: ["Batch code", "8rem", ""], pkd: ["PKD (MM-YYYY)", "8rem", "MM-YYYY"], fault: ["Fault", "12rem", "e.g. no output"] };
function lineEditor(id, o) {
  if (!editors[id] || o.reset) editors[id] = { lines: [{ text: o.prefill || "", qty: "" }] };
  editors[id].o = o;
  const extra = (o.extra || []).map(k => `<th>${EXTRA[k][0]}</th>`).join("");
  return `<div class="table-wrap"><table class="lines"><thead><tr><th>#</th><th>Item code</th><th>Item</th>
      ${o.avail ? `<th class="num">Available</th>` : ""}<th>Qty</th>${extra}<th></th></tr></thead>
      <tbody id="${id}"></tbody></table></div>
    <button type="button" class="secondary outline small" onclick="edAdd('${id}')">+ Add another item</button>`;
}
let edQueued = {};
function edSoon(id) { if (edQueued[id]) return; edQueued[id] = true; setTimeout(() => { edQueued[id] = false; edRender(id); }); }
function edRender(id) {
  const ed = editors[id], tbody = document.getElementById(id);
  if (!ed || !tbody) return;
  const o = ed.o, where = o.avail ? o.avail() : null;
  tbody.innerHTML = ed.lines.map((l, n) => {
    const r = lookup(l.text);
    let info = "", avail = o.avail ? `<td data-label="Available"></td>` : "";
    if (r.item) {
      info = `<span class="good">✓</span> ${esc(TYPE_LABEL[r.item.type])} · ${esc(r.item.desc)}` +
        (r.via ? `<br><span class="muted">you typed ${esc(r.via)} → ${esc(r.item.code)}</span>` : "");
      if (where) {
        const have = balance(r.item.code, where.loc, where.bucket), short = Number(l.qty) > have;
        const u = r.item.unit;
        avail = `<td data-label="Available" class="num ${short ? "bad" : ""}">${have} ${u}${short ? `<br><small>Only ${have} ${u} at ${esc(where.loc)}</small>` : ""}</td>`;
      }
    } else if (l.text.trim()) {
      info = `<span class="bad">Not found.</span> ` +
        (r.suggest.length ? `Did you mean ${r.suggest.map(s => `<a href="#" onclick="edPick('${id}',${n},'${esc(s.code)}');return false" class="code">${esc(s.code)}</a>`).join(", ")}? ` : "") +
        (o.create ? `<button type="button" class="small secondary" onclick="edCreate('${id}',${n})">+ Create item ${esc(norm(l.text))}</button>` : "");
    }
    const extra = (o.extra || []).map(k => `<td data-label="${EXTRA[k][0]}"><input value="${esc(l[k] || "")}" placeholder="${EXTRA[k][2]}"
      style="width:${EXTRA[k][1]}" onchange="edSet('${id}',${n},'${k}',this.value,true)"></td>`).join("");
    return `<tr><td class="n">${n + 1}</td>
      <td class="wide" data-label="Item ${n + 1}"><input list="itemlist" value="${esc(l.text)}" placeholder="Type code…" style="min-width:14rem"
        onchange="edSet('${id}',${n},'text',this.value)"></td>
      <td class="wide">${info}</td>${avail}
      <td data-label="Qty${r.item ? ` (${r.item.unit})` : ""}"><input class="qty-in" type="number" min="1" value="${esc(l.qty)}"
        oninput="edSet('${id}',${n},'qty',this.value,true)" onchange="edSoon('${id}')"></td>${extra}
      <td>${ed.lines.length > 1 ? `<button type="button" class="small secondary outline" onclick="edRemove('${id}',${n})" title="Remove">✕</button>` : ""}</td></tr>`;
  }).join("");
}
function edSet(id, n, k, v, quiet) { editors[id].lines[n][k] = v; if (!quiet) edSoon(id); }
function edAdd(id) { editors[id].lines.push({ text: "", qty: "" }); edRender(id); }
function edRemove(id, n) { editors[id].lines.splice(n, 1); edRender(id); }
function edPick(id, n, code) { editors[id].lines[n].text = code; edRender(id); }
function edCreate(id, n) {
  openDlg(`<header><strong>Create new item</strong></header>
    <label>Code <input id="ni-code" value="${esc(norm(editors[id].lines[n].text))}"></label>
    <label>Type <select id="ni-type">${opts(Object.entries(TYPE_LABEL), "DRIVER")}</select></label>
    <label>Description <input id="ni-desc" placeholder="e.g. 24W driver 500mA"></label>
    <div class="fields"><label>Unit <select id="ni-unit">${opts(UNITS, "NOS")}</select></label>
      <label>Brand <input id="ni-brand" value="Wipro"></label></div>
    <footer class="actions"><button class="secondary" onclick="closeDlg()">Cancel</button>
      <button onclick="edCreateSave('${id}',${n})">Create item</button></footer>`);
}
function edCreateSave(id, n) {
  const code = norm(document.getElementById("ni-code").value);
  if (!code || lookup(code).item) return alert("That code is empty or already exists.");
  ITEMS.push({ code, type: document.getElementById("ni-type").value, desc: document.getElementById("ni-desc").value || "(new item)", reorder: 0, aliases: [],
    unit: document.getElementById("ni-unit").value, brand: document.getElementById("ni-brand").value || "Wipro" });
  document.getElementById("itemlist").insertAdjacentHTML("beforeend", `<option value="${esc(code)}">`);
  editors[id].lines[n].text = code; closeDlg(); edRender(id);
}
/* -> {lines:[{code, qty, batch, pkd, fault}]} or {error} */
function edCollect(id, { optional = false } = {}) {
  const out = [];
  for (const [n, l] of editors[id].lines.entries()) {
    if (!l.text.trim() && !l.qty) continue;
    const r = lookup(l.text), q = Number(l.qty);
    if (!r.item) return { error: `Line ${n + 1}: pick a known item${editors[id].o.create ? " (or create it)" : ""}.` };
    if (!Number.isInteger(q) || q <= 0) return { error: `Line ${n + 1}: quantity must be a whole number above 0.` };
    out.push({ code: r.item.code, qty: q, batch: l.batch || "", pkd: l.pkd || "", fault: l.fault || "" });
  }
  if (!out.length && !optional) return { error: "Add at least one item with a quantity." };
  return { lines: out };
}
function formError(id, msg) {
  document.getElementById(id).innerHTML = msg ? `<article class="flash err">${esc(msg)}</article>` : "";
}
