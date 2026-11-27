// Rare Cash dashboard (vanilla JS, no build step)
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("en-IN");
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const STATE = { tab: "dashboard", pages: [], clipFilter: "", campFilter: "all", timers: [] };

if (localStorage.theme === "dark") document.documentElement.dataset.theme = "dark";

async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) } };
  if (init.body && typeof init.body === "object" && !(init.body instanceof FormData)) init.body = JSON.stringify(init.body);
  const r = await fetch(path, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : r.statusText);
  return data;
}

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 4000);
}
async function act(fn, okMsg) {
  try { const r = await fn(); toast(r?.message || okMsg || "Done"); return r; }
  catch (e) { toast(e.message, true); throw e; }
}

function openModal(html) { $("#modalBody").innerHTML = html; $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; $("#modalBody").innerHTML = ""; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function ago(t) {
  if (!t) return "never";
  const s = Math.round(Date.now() / 1000 - t);
  if (s < 60) return "abhi";
  if (s < 3600) return Math.round(s / 60) + " min pehle";
  if (s < 86400) return Math.round(s / 3600) + " ghante pehle";
  return Math.round(s / 86400) + " din pehle";
}
function until(t) {
  const s = Math.round(t - Date.now() / 1000);
  if (s <= 60) return "abhi";
  const mins = Math.round(s / 60), h = Math.floor(mins / 60), m = mins % 60;
  return h ? `${h}h ${m}m mein` : `${m} min mein`;
}
const clock = (t) => new Date(t * 1000).toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });

function chip(level, icon, text, title = "") {
  return `<span class="chip ${level}" ${title ? `title="${esc(title)}"` : ""}>${icon} ${esc(text)}</span>`;
}
const CAMP_STATUS = {
  ready: ["info", "●", "Clips banenge"], pending: ["warning", "◌", "Bot padhega"], done: ["good", "✓", "Done"],
  skipped: ["", "–", "Skipped"], failed: ["critical", "✕", "Failed"],
};
function postChip(platform, p) {
  const name = platform === "youtube" ? "YT" : "IG";
  if (!p) return chip("", "◌", `${name}: queue`);
  if (p.status === "posted") {
    const v = chip("good", "✓", `${name}: ${fmt(p.views)} views`);
    return p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${v}</a>` : v;
  }
  if (p.error && p.error.startsWith("platform not allowed")) return chip("", "–", `${name}: n/a`, p.error);
  return chip("critical", "✕", `${name}: failed`, p.error || "");
}
function vyroChip(posts) {
  const vals = Object.values(posts).filter((p) => p.status === "posted");
  if (!vals.length) return "";
  if (vals.every((p) => p.vyro === "not_needed")) return chip("", "–", "Vyro: manual");
  if (vals.some((p) => p.vyro === "submitted")) return chip("good", "✓", "Vyro submitted");
  if (vals.some((p) => p.vyro === "failed")) return chip("serious", "!", "Vyro retry", vals.map((p) => p.vyro_error).join(" | "));
  return chip("warning", "◌", "Vyro pending");
}

// ------------------------------------------------------------------ top bar
const TAB_TITLES = { pages: "Pages", add: "Add Video", campaigns: "Campaigns", clips: "Clips", schedule: "Schedule", earnings: "Earnings", logs: "Logs", settings: "Settings" };
function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good Morning" : h < 17 ? "Good Afternoon" : "Good Evening";
}
function setHeader() {
  const who = window.innerWidth < 600 ? "" : ", Rare Cash";
  $("#greet").textContent = STATE.tab === "dashboard" ? `${greeting()}${who}` : TAB_TITLES[STATE.tab] || "Rare Cash";
}
function vpnChip(v, required) {
  if (!v || !v.country) return required ? chip("warning", "◌", "VPN check ho raha hai") : "";
  const where = `${v.country_name} · ${v.ip}`;
  if (!required) return chip("info", "◎", v.country_name, where);
  return v.pass ? chip("good", "✓", `VPN: ${v.country_name}`, where) : chip("critical", "✕", `VPN off (${v.country_name})`, where);
}
async function refreshTop() {
  try {
    const o = await api(STATE.tab === "dashboard" ? "/api/dashboard" : "/api/overview");
    STATE.overview = o;
    $("#powerToggle").checked = o.enabled;
    $("#powerLabel").textContent = o.enabled ? "Bot ON" : "Bot OFF";
    $("#statusText").textContent = o.status;
    $("#engineDot").className = "dot " + (!o.engine_alive ? "dead" : o.enabled ? "on" : "off");
    $("#vpnChip").innerHTML = vpnChip(o.vpn, o.vpn_required);
    renderVpnBtn(o.tunnel);
    if (STATE.tab === "dashboard") renderDashboard(o);
  } catch (e) {
    $("#statusText").textContent = "Dashboard server se connect nahi ho pa raha";
    $("#engineDot").className = "dot dead";
  }
}
async function refreshVpn() {
  try { const v = await api("/api/network"); $("#vpnChip").innerHTML = vpnChip(v, v.required); } catch (e) { /* offline */ }
}
$("#powerToggle").addEventListener("change", async (e) => {
  const on = e.target.checked;
  await act(() => api("/api/bot", { method: "POST", body: { enabled: on } }), on ? "Bot ON ho gaya" : "Bot OFF: abhi wala kaam khatam karke ruk jayega");
  refreshTop();
});

// built-in VPN button
function renderVpnBtn(t) {
  if (!t) return;
  STATE.tunnel = t;
  const b = $("#vpnBtn"), l = $("#vpnLabel");
  const state = !t.wanted ? "off" : t.state === "on" ? "on" : t.state === "error" ? "error" : "connecting";
  b.className = "vpn-btn " + state;
  l.textContent = state === "off" ? "VPN OFF" : state === "on" ? `VPN ${t.country || "ON"}` : state === "error" ? "VPN error" : "Connecting…";
  b.title = state === "error" ? t.error : state === "on" ? `Connected: ${t.config} · ${t.ip}` : "Built-in VPN ON / OFF";
  // the plain location chip is only needed when the built-in VPN isn't used
  $("#vpnChip").style.display = t.wanted ? "none" : "";
  if (state === "connecting") setTimeout(pollVpn, 2500);
}
async function pollVpn() { try { renderVpnBtn(await api("/api/vpn")); } catch (e) { /* offline */ } }
$("#vpnBtn").addEventListener("click", async () => {
  const t = STATE.tunnel || {};
  try {
    const r = await api("/api/vpn", { method: "POST", body: { enabled: !t.wanted } });
    toast(r.message);
  } catch (e) {
    toast(e.message, true);
    if (/server add/i.test(e.message)) location.hash = "settings";
  }
  pollVpn();
  if (STATE.tab === "settings") setTimeout(renderSettings, 600);
});

// ------------------------------------------------------------------ dashboard
const SLOT = (i) => `var(--s${(i % 6) + 1})`;
const SLOT_INK = (i) => ["#fff", "#fff", "#111", "#111", "#111", "#fff"][i % 6]; // readable letter on each slot
function ticks(value, total, n = 44) {
  const on = total ? Math.round(Math.min(1, value / total) * n) : 0;
  return `<div class="ticks" role="img" aria-label="${value} of ${total}">${Array.from({ length: n }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</div>`;
}
function renderDashboard(o) {
  const warn = o.warnings.map((w) => `<div class="alert ${w.level}"><b>${w.level === "critical" ? "✕ Zaroori" : "! Dhyan do"}</b><span>${esc(w.text)}</span>${w.tab ? `<a href="#${w.tab}">Fix karo →</a>` : ""}</div>`).join("");
  const daily = o.daily || [];
  const last14 = daily.slice(-14);
  const views7 = daily.slice(-7).reduce((a, d) => a + d.views, 0);
  const totalPosts = o.by_page.reduce((a, p) => a + p.posts, 0);
  const pagesSorted = [...o.by_page].sort((a, b) => b.earned - a.earned || b.views - a.views);
  $("#tab-dashboard").innerHTML = `
    ${warn ? `<div style="margin-bottom:14px">${warn}</div>` : ""}
    <div class="dash">
      <div class="card c4">
        <div class="card-head"><h2>Estimated kamai</h2><span class="pill">views × CPM</span></div>
        <div class="big">${money(o.earned)}</div>
        ${ticks(o.posted_today, o.capacity_today)}
        <div class="meta-line"><span>Aaj ${fmt(o.posted_today)} / ${fmt(o.capacity_today)} posts</span><span>${fmt(o.posted)} total</span></div>
      </div>
      <div class="card c4">
        <div class="card-head"><h2>Campaigns</h2><a href="#campaigns" class="pill">Sab dekho</a></div>
        <div class="big">${fmt(o.campaigns_active)}<small>active</small></div>
        ${ticks(o.submitted, Math.max(o.posted, 1))}
        <div class="meta-line"><span>Vyro submitted ${fmt(o.submitted)} / ${fmt(o.posted)}</span><span>${fmt(o.campaigns_total)} total</span></div>
      </div>
      <div class="card views-card c4 r2">
        <div class="card-head"><h2>Total views</h2><span class="pill" style="background:rgba(255,255,255,.18);border-color:transparent;color:#fff">14 din</span></div>
        <div class="big">${fmt(o.views)}</div>
        <small>+${fmt(views7)} pichhle 7 din mein</small>
        <div class="chart" id="viewsChart"></div>
      </div>

      <div class="card c4">
        <div class="card-head"><h2>Top pages</h2><a href="#pages" class="pill">Pages</a></div>
        ${pagesSorted.length ? pagesSorted.slice(0, 5).map((p) => `<div class="list-row">
            <span class="ava" style="background:${SLOT(p.slot)};color:${SLOT_INK(p.slot)}">${esc(p.name.slice(0, 2).toUpperCase())}</span>
            <span class="name">${esc(p.name)}${p.enabled ? "" : " <small>(off)</small>"}</span>
            <span class="num"><b>${fmt(p.views)}</b> views</span><span class="num"><b>${money(p.earned)}</b></span></div>`).join("")
          : `<div class="empty"><b>Koi page nahi</b><a href="#pages">Page add karo →</a></div>`}
      </div>
      <div class="card c4">
        <div class="card-head"><h2>Posts by page</h2><span class="pill">${fmt(totalPosts)} posts</span></div>
        <div id="donut"></div>
      </div>

      <div class="card c8">
        <div class="card-head"><h2>Kamai per day</h2><span class="pill">30 din</span></div>
        <div class="chart" id="earnChart"></div>
      </div>
      <div class="c4" style="display:grid;gap:18px">
        <div class="card control-card">
          <div class="card-head"><h2>Bot control</h2><span class="pill">${o.enabled ? "ON" : "OFF"}</span></div>
          <div class="muted" style="font-size:13px">${esc(o.status)}</div>
          <div class="row"><button class="primary" onclick="runNow()">▶ Abhi chalao</button><button onclick="scanNow()">⟳ Vyro scan</button></div>
          <div class="kv"><span>Last round</span><b>${ago(o.last_cycle)}</b><span>Agla Vyro scan</span><b>${o.next_scan ? until(o.next_scan) : "jaldi"}</b>
            <span>Clips bane</span><b>${fmt(o.clips)} (${fmt(o.clips_today)} aaj)</b></div>
        </div>
        <div class="card dark-card">
          <div class="card-head"><h2>Posts per day</h2><span class="pill">14 din</span></div>
          <div class="big" style="color:#fff">${fmt(last14.reduce((a, d) => a + d.posts, 0))}<small style="color:#9c9c9c">posts</small></div>
          <div class="chart" id="postsChart"></div>
        </div>
      </div>

      <div class="card c12">
        <div class="card-head"><h2>Live activity</h2><a href="#logs" class="pill">Saare logs</a></div>
        ${activityList(o.activity)}
      </div>
    </div>`;
  whiteBars($("#viewsChart"), last14);
  donut($("#donut"), o.by_page);
  barChart($("#earnChart"), daily, { H: 340, key: "earned", label: (v) => money(v), axis: (v) => "$" + (v >= 1000 ? (v / 1000).toFixed(1) + "k" : Math.round(v)) });
  areaChart($("#postsChart"), last14);
}
function activityList(lines) {
  if (!lines.length) return `<div class="empty"><b>Abhi koi activity nahi</b>Bot ON karo, kaam yahan dikhega.</div>`;
  lines = lines.filter((l) => /^\d{4}-\d\d-\d\d /.test(l));
  return `<ul class="activity">${lines.slice().reverse().map((l) => {
    const m = l.match(/^(\S+ (\S+)) (\w+) (.*)$/);
    return m ? `<li class="${m[3]}"><time>${m[2].slice(0, 5)}</time><span title="${esc(m[4])}">${esc(m[4])}</span></li>` : `<li><span>${esc(l)}</span></li>`;
  }).join("")}</ul>`;
}
async function runNow() { await act(() => api("/api/bot/run-now", { method: "POST" }), "Bot abhi ek round chalayega"); }
async function scanNow() { await act(() => api("/api/bot/scan-now", { method: "POST" }), "Vyro scan shuru ho raha hai"); }

// ---------- charts (single series unless noted; hover tooltips everywhere) ----------
const dayLabel = (d) => new Date(d + "T00:00:00").toLocaleDateString([], { day: "numeric", month: "short" });
function niceTop(max) {
  if (max <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(max)));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= max);
}
function roundedTop(x, yTop, w, base, r) {
  const h = base - yTop;
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${base} V${yTop + r} Q${x},${yTop} ${x + r},${yTop} H${x + w - r} Q${x + w},${yTop} ${x + w},${yTop + r} V${base} Z`;
}
function emptyChart(el, msg) { el.innerHTML = `<div class="empty" style="width:100%"><b>Abhi data nahi</b>${msg}</div>`; }

// bars: past days in the light step, today in the accent; hover darkens
function barChart(el, data, opt = {}) {
  const key = opt.key || "views", label = opt.label || ((v) => fmt(v) + " views"), axis = opt.axis || ((v) => (v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : v));
  if (!data.length || data.every((d) => !d[key])) return emptyChart(el, "Posts ke views aane ke baad chart dikhega.");
  const W = 760, H = opt.H || 230, L = 44, B = 26, T = 12;
  const top = niceTop(Math.max(...data.map((d) => d[key])));
  const bw = (W - L) / data.length, base = H - B;
  const y = (v) => T + (base - T) * (1 - v / top);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.aria || "chart")}">`;
  for (let i = 0; i <= 4; i++) { const v = (top / 4) * i; svg += `<line class="grid-line" x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><g class="axis"><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${axis(v)}</text></g>`; }
  data.forEach((d, i) => {
    const x = L + i * bw + 1, w = Math.max(2, bw - 2), last = i === data.length - 1;
    svg += `<g class="barg" data-tip="<b>${esc(label(d[key]))}</b>${esc(dayLabel(d.day))}"><rect x="${L + i * bw}" y="${T}" width="${bw}" height="${base - T}" fill="transparent"/>
      <path d="${roundedTop(x, y(d[key]), w, base, 4)}" fill="${last ? "var(--series-1)" : "var(--series-soft)"}" class="bar"/></g>`;
    const step = Math.ceil(data.length / 8);
    if ((i % step === 0 && data.length - 1 - i >= step * 0.7) || last) svg += `<g class="axis"><text x="${x + w / 2}" y="${H - 7}" text-anchor="${last ? "end" : "middle"}" ${last ? `dx="${w / 2}"` : ""}>${esc(dayLabel(d.day))}</text></g>`;
  });
  el.innerHTML = svg + "</svg>";
  el.querySelectorAll(".barg").forEach((g) => { g.addEventListener("mouseenter", () => (g.querySelector(".bar").style.fill = "var(--series-1)")); g.addEventListener("mouseleave", () => (g.querySelector(".bar").style.fill = "")); });
  bindTips(el);
}
// white bars on the blue card
function whiteBars(el, data) {
  if (!data.length || data.every((d) => !d.views)) return emptyChart(el, "Views har 2 ghante update hote hain.");
  const W = 320, H = 250, B = 22, T = 8;
  const top = niceTop(Math.max(...data.map((d) => d.views)));
  const bw = W / data.length, base = H - B;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Views per day">`;
  data.forEach((d, i) => {
    const w = Math.max(3, bw * 0.55), x = i * bw + (bw - w) / 2, yy = T + (base - T) * (1 - d.views / top), last = i === data.length - 1;
    svg += `<g class="barg" data-tip="<b>${fmt(d.views)} views</b>${esc(dayLabel(d.day))}"><rect x="${i * bw}" y="${T}" width="${bw}" height="${base - T}" fill="transparent"/>
      <path class="bar" d="${roundedTop(x, yy, w, base, w / 2)}" fill="#fff" fill-opacity="${last ? 1 : 0.55}"/></g>`;
    if (i % 3 === 0 || last) svg += `<g class="axis"><text x="${x + w / 2}" y="${H - 5}" text-anchor="middle">${new Date(d.day + "T00:00:00").getDate()}</text></g>`;
  });
  el.innerHTML = svg + "</svg>";
  el.querySelectorAll(".barg").forEach((g) => { const b = g.querySelector(".bar"); const o = b.getAttribute("fill-opacity"); g.addEventListener("mouseenter", () => b.setAttribute("fill-opacity", 1)); g.addEventListener("mouseleave", () => b.setAttribute("fill-opacity", o)); });
  bindTips(el);
}
// donut: categorical, colour = page's fixed slot, 2px surface gaps, legend with labels
function donut(el, pages) {
  const items = pages.filter((p) => p.posts > 0);
  const total = items.reduce((a, p) => a + p.posts, 0);
  if (!total) return (el.innerHTML = `<div class="empty"><b>Abhi koi post nahi</b>Post hone ke baad yahan dikhega.</div>`);
  const R = 60, r = 40, C = 75;
  let a0 = -Math.PI / 2, paths = "";
  const pt = (ang, rad) => [C + rad * Math.cos(ang), C + rad * Math.sin(ang)];
  items.forEach((p) => {
    const a1 = a0 + (p.posts / total) * Math.PI * 2, big = a1 - a0 > Math.PI ? 1 : 0;
    const full = items.length === 1;
    const d = full ? `M${C},${C - R} A${R},${R} 0 1 1 ${C - 0.01},${C - R} L${C - 0.01},${C - r} A${r},${r} 0 1 0 ${C},${C - r} Z`
      : (() => { const [x0, y0] = pt(a0, R), [x1, y1] = pt(a1, R), [x2, y2] = pt(a1, r), [x3, y3] = pt(a0, r);
          return `M${x0},${y0} A${R},${R} 0 ${big} 1 ${x1},${y1} L${x2},${y2} A${r},${r} 0 ${big} 0 ${x3},${y3} Z`; })();
    paths += `<path d="${d}" fill="${SLOT(p.slot)}" stroke="var(--surface-1)" stroke-width="2" data-tip="<b>${esc(p.name)}</b>${p.posts} posts · ${Math.round((p.posts / total) * 100)}%"/>`;
    a0 = a1;
  });
  el.innerHTML = `<div class="donut-wrap"><svg viewBox="0 0 150 150" role="img" aria-label="Posts by page">${paths}
      <text x="75" y="72" text-anchor="middle" style="font-size:22px;font-weight:600;fill:var(--text-primary)">${total}</text>
      <text x="75" y="90" text-anchor="middle" style="font-size:11px;fill:var(--text-secondary)">posts</text></svg>
    <ul class="legend">${items.map((p) => `<li><span class="sw" style="background:${SLOT(p.slot)}"></span><span class="lbl">${esc(p.name)}</span><span class="val">${p.posts}</span><span class="pct">${Math.round((p.posts / total) * 100)}%</span></li>`).join("")}</ul></div>`;
  bindTips(el);
}
// area on the dark card: 2px line, ~10% fill, crosshair + tooltip
function areaChart(el, data) {
  if (!data.length || data.every((d) => !d.posts)) return emptyChart(el, "Posts hone par graph banega.");
  const W = 320, H = 120, T = 10, B = 18;
  const top = niceTop(Math.max(...data.map((d) => d.posts)));
  const x = (i) => (i / (data.length - 1)) * W, y = (v) => T + (H - T - B) * (1 - v / top);
  const pts = data.map((d, i) => [x(i), y(d.posts)]);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${W},${H - B} L0,${H - B} Z`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Posts per day">
      <line class="grid-line" x1="0" x2="${W}" y1="${H - B}" y2="${H - B}"/>
      <path d="${area}" fill="#338ced" fill-opacity=".12"/><path d="${line}" fill="none" stroke="#338ced" stroke-width="2" stroke-linejoin="round"/>
      <line id="xhair" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="#9c9c9c" stroke-width="1" visibility="hidden"/>
      <circle id="xdot" r="4.5" fill="#338ced" stroke="#121316" stroke-width="2" visibility="hidden"/>
      <g class="axis"><text x="0" y="${H - 3}">${esc(dayLabel(data[0].day))}</text><text x="${W}" y="${H - 3}" text-anchor="end">aaj</text></g>
      <rect id="xhit" x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
  const svg = el.querySelector("svg"), hit = el.querySelector("#xhit"), xh = el.querySelector("#xhair"), xd = el.querySelector("#xdot"), tip = $("#tooltip");
  hit.addEventListener("mousemove", (e) => {
    const rect = svg.getBoundingClientRect(), i = Math.max(0, Math.min(data.length - 1, Math.round(((e.clientX - rect.left) / rect.width) * (data.length - 1))));
    const [px, py] = pts[i];
    xh.setAttribute("x1", px); xh.setAttribute("x2", px); xh.setAttribute("visibility", "visible");
    xd.setAttribute("cx", px); xd.setAttribute("cy", py); xd.setAttribute("visibility", "visible");
    tip.innerHTML = `<b>${data[i].posts} posts</b>${esc(dayLabel(data[i].day))}`; tip.hidden = false;
    tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 44 + "px";
  });
  hit.addEventListener("mouseleave", () => { xh.setAttribute("visibility", "hidden"); xd.setAttribute("visibility", "hidden"); tip.hidden = true; });
}
function bindTips(el) {
  const tip = $("#tooltip");
  el.querySelectorAll("[data-tip]").forEach((n) => {
    n.addEventListener("mousemove", (e) => { tip.innerHTML = n.dataset.tip; tip.hidden = false; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 44 + "px"; });
    n.addEventListener("mouseleave", () => (tip.hidden = true));
  });
}

// ------------------------------------------------------------------ pages
async function renderPages() {
  const pages = (STATE.pages = await api("/api/pages"));
  const card = (p) => {
    const yt = p.youtube, ig = p.instagram;
    const ytLine = yt ? `<div class="platform-line"><span class="name">YouTube</span>
        ${!yt.enabled ? chip("", "–", "off") : p.youtube_connected ? chip("good", "✓", "connected") : p.youtube_connecting === "running" ? chip("warning", "◌", "connecting…") : chip("critical", "✕", "not connected")}
        <span class="spacer"></span><small style="white-space:nowrap">aaj ${p.youtube_today || "-"}</small>
        ${yt.enabled && !p.youtube_connected ? `<button class="small" onclick="ytConnect('${esc(p.name)}')">Connect</button>` : ""}</div>` : "";
    const igLine = ig ? `<div class="platform-line"><span class="name">Instagram</span>
        ${!ig.enabled ? chip("", "–", "off") : p.instagram_token_set ? chip("good", "✓", "token set") : chip("critical", "✕", "token missing")}
        <span class="spacer"></span><small style="white-space:nowrap">aaj ${p.instagram_today || "-"}</small></div>` : "";
    return `<div class="card page-card ${p.enabled ? "" : "disabled"}">
      <div class="row between"><h3>${esc(p.name)}</h3>
        <label class="mini-switch" title="Page ON/OFF"><input type="checkbox" ${p.enabled ? "checked" : ""} onchange="togglePage('${esc(p.name)}', this.checked)"><span></span></label></div>
      <div class="niche">${esc(p.niche)}</div>
      ${ytLine}${igLine}
      <div class="platform-line"><span class="name">Stats</span><small>${fmt(p.clips)} clips · ${fmt(p.views)} views · ${p.min_gap_minutes} min gap</small></div>
      <div class="row" style="margin-top:10px"><button class="small" onclick="editPage('${esc(p.name)}')">✎ Edit</button>
        <button class="small danger" onclick="deletePage('${esc(p.name)}')">Delete</button></div></div>`;
  };
  $("#tab-pages").innerHTML = `
    <div class="row between"><h1>Pages</h1><button class="primary" onclick="editPage()">＋ Naya page</button></div>
    <p class="muted" style="margin-top:-8px">Har page = ek niche. Bot Vyro campaigns ko niche ke hisaab se sahi page pe daalta hai. Accounts (YouTube channel / Instagram) tumhe khud banane hain, phir yahan connect karo.</p>
    ${pages.length ? `<div class="grid cards">${pages.map(card).join("")}</div>`
      : `<div class="card empty"><b>Abhi koi page nahi</b>Pehla page add karo (jaise: podcast, gaming, comedy, finance).<br><br><button class="primary" onclick="editPage()">＋ Naya page</button></div>`}`;
}
async function togglePage(name, on) { await act(() => api(`/api/pages/${encodeURIComponent(name)}/toggle`, { method: "POST", body: { enabled: on } }), on ? `${name} ON` : `${name} OFF`); renderPages(); }
async function deletePage(name) {
  if (!confirm(`Page "${name}" delete karna hai? (clips aur posts delete nahi honge)`)) return;
  await act(() => api(`/api/pages/${encodeURIComponent(name)}`, { method: "DELETE" }), "Page delete ho gaya"); renderPages();
}
async function ytConnect(name) { await act(() => api(`/api/pages/${encodeURIComponent(name)}/youtube-connect`, { method: "POST" })); setTimeout(renderPages, 3000); }

const NICHES = {
  podcast: "Podcasts, interviews, motivational speeches, self-improvement",
  gaming: "Gaming, streamers, Twitch/Kick/YouTube gaming streams",
  comedy: "Comedy, entertainment, challenges, vlogs, funny moments",
  finance: "Finance, money, crypto, business, entrepreneurship",
};
function editPage(name) {
  const p = STATE.pages.find((x) => x.name === name) || { name: "", niche: "", language: "English", clips_per_video: 4, min_gap_minutes: 120, handles: [], enabled: true, youtube: { enabled: true, privacy: "public", max_per_day: 3, client_secret: "client_secret.json", token_file: "" }, instagram: { enabled: true, user_id: "", token_env: "", max_per_day: 3, graph_version: "v23.0" } };
  const yt = p.youtube || { enabled: false, privacy: "public", max_per_day: 3, client_secret: "client_secret.json", token_file: "" };
  const ig = p.instagram || { enabled: false, user_id: "", token_env: "", max_per_day: 3, graph_version: "v23.0" };
  openModal(`
    <h2>${name ? "Page edit karo" : "Naya page"}</h2>
    <form id="pageForm">
      <div class="form-grid">
        <label class="field"><span>Page ka naam</span><input type="text" name="name" value="${esc(p.name)}" placeholder="podcast" required></label>
        <label class="field"><span>Language (titles/captions)</span><input type="text" name="language" value="${esc(p.language)}"></label>
      </div>
      <label class="field"><span>Niche (kis type ke campaigns lene hain)</span>
        <textarea name="niche" rows="2" required placeholder="Podcasts, interviews, motivation">${esc(p.niche)}</textarea>
        <div class="row" style="margin-top:6px">${Object.entries(NICHES).map(([k, v]) => `<button type="button" class="small" onclick="pickNiche('${k}')">${k}</button>`).join("")}</div></label>
      <div class="form-grid">
        <label class="field"><span>Har video se kitne clips</span><input type="number" name="clips_per_video" min="1" max="15" value="${p.clips_per_video}"></label>
        <label class="field"><span>Do posts ke beech gap (minute)</span><input type="number" name="min_gap_minutes" min="10" value="${p.min_gap_minutes}"></label>
      </div>
      <label class="field"><span>Tumhare handles (comma se alag)</span><input type="text" name="handles" value="${esc((p.handles || []).join(", "))}" placeholder="@mypodcastclips"></label>
      <fieldset><legend>YouTube Shorts</legend>
        <label class="check"><input type="checkbox" name="yt_enabled" ${p.youtube && yt.enabled ? "checked" : ""}> Is page pe YouTube post karo</label>
        <div class="form-grid">
          <label class="field"><span>Privacy</span><select name="yt_privacy">${["public", "unlisted", "private"].map((v) => `<option ${yt.privacy === v ? "selected" : ""}>${v}</option>`).join("")}</select></label>
          <label class="field"><span>Roz max posts</span><input type="number" name="yt_max" min="0" value="${yt.max_per_day}"></label>
        </div>
        <label class="field"><span>client_secret file</span><input type="text" name="yt_secret" value="${esc(yt.client_secret)}"><div class="hint">Save karne ke baad page card pe "Connect" dabao aur is page ka channel chuno.</div></label>
      </fieldset>
      <fieldset><legend>Instagram Reels</legend>
        <label class="check"><input type="checkbox" name="ig_enabled" ${p.instagram && ig.enabled ? "checked" : ""}> Is page pe Instagram post karo</label>
        <div class="form-grid">
          <label class="field"><span>Instagram user ID</span><input type="text" name="ig_user" value="${esc(ig.user_id)}" placeholder="1784..."></label>
          <label class="field"><span>Roz max posts</span><input type="number" name="ig_max" min="0" value="${ig.max_per_day}"></label>
        </div>
        <label class="field"><span>Access token ${p.instagram_token_set ? "(set hai, badalna ho to hi daalo)" : ""}</span><input type="password" name="ig_token" autocomplete="off" placeholder="EAAG..."><div class="hint">Token sirf tumhare PC ki .env file mein save hota hai.</div></label>
      </fieldset>
      <div class="row"><button class="primary" type="submit">Save</button><button type="button" onclick="closeModal()">Cancel</button></div>
    </form>`);
  $("#pageForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const page = {
      name: f.name, niche: f.niche, language: f.language || "English", enabled: p.enabled,
      clips_per_video: +f.clips_per_video, min_gap_minutes: +f.min_gap_minutes,
      handles: f.handles.split(",").map((s) => s.trim()).filter(Boolean),
      youtube: f.yt_enabled || p.youtube ? { enabled: !!f.yt_enabled, privacy: f.yt_privacy, max_per_day: +f.yt_max, client_secret: f.yt_secret || "client_secret.json", token_file: yt.token_file || "" } : null,
      instagram: f.ig_enabled || p.instagram ? { enabled: !!f.ig_enabled, user_id: f.ig_user || "", token_env: ig.token_env || "", max_per_day: +f.ig_max, graph_version: ig.graph_version || "v23.0" } : null,
    };
    if (page.instagram && page.instagram.enabled && !page.instagram.user_id) return toast("Instagram user ID daalo (ya Instagram off karo)", true);
    await act(() => api("/api/pages", { method: "POST", body: { page, original_name: name || null, instagram_token: f.ig_token || null } }), "Page save ho gaya");
    closeModal(); renderPages();
  });
}
function pickNiche(k) { const f = $("#pageForm"); f.niche.value = NICHES[k]; if (!f.name.value) f.name.value = k; }

// ------------------------------------------------------------------ add video
async function renderAdd() {
  const pages = (STATE.pages = await api("/api/pages"));
  const opts = pages.map((p) => `<option value="${esc(p.name)}">${esc(p.name)}</option>`).join("");
  $("#tab-add").innerHTML = `
    <h1>Add Video</h1>
    <div class="grid two">
      <div class="card">
        <h2>Video se clips banao</h2>
        <p class="muted" style="margin-top:0">YouTube / Google Drive / Dropbox link do, ya apne PC se file upload karo. Bot clips banake page ke schedule pe post karega.</p>
        <form id="videoForm">
          <label class="field"><span>Video link</span><input type="url" name="video_url" placeholder="https://www.youtube.com/watch?v=..."></label>
          <label class="field"><span>…ya file upload karo</span><input type="file" name="file" accept="video/*"></label>
          <label class="field"><span>Kis page pe post kare</span><select name="page" required>${opts || "<option value=''>Pehle page banao</option>"}</select></label>
          <label class="field"><span>Vyro campaign link (optional)</span><input type="url" name="campaign_url" placeholder="https://vyro.com/..."><div class="hint">Diya to bot campaign join karke rules follow karega aur post ke baad Vyro pe submit karega. Nahi diya to sirf post hoga.</div></label>
          <label class="field"><span>Naam (optional)</span><input type="text" name="title" placeholder="Mera podcast ep 12"></label>
          <button class="primary" type="submit" ${pages.length ? "" : "disabled"}>＋ Queue mein daalo</button>
        </form>
      </div>
      <div class="card">
        <h2>Vyro campaign add karo</h2>
        <p class="muted" style="margin-top:0">Koi campaign khud chuna hai? Link daalo. Bot use join karega, material download karega, aur clips banayega.</p>
        <form id="campForm">
          <label class="field"><span>Vyro campaign link</span><input type="url" name="url" required placeholder="https://vyro.com/..."></label>
          <label class="field"><span>Page</span><select name="page"><option value="">Auto (AI niche se chunega)</option>${opts}</select></label>
          <button class="primary" type="submit">＋ Campaign add karo</button>
        </form>
      </div>
    </div>`;
  $("#videoForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    let url = (fd.get("video_url") || "").trim();
    const file = fd.get("file");
    const btn = e.target.querySelector("button[type=submit]");
    try {
      btn.disabled = true;
      if (file && file.size) {
        btn.textContent = "Upload ho raha hai…";
        const up = new FormData(); up.append("file", file);
        url = (await api("/api/upload", { method: "POST", body: up })).path;
      }
      if (!url) throw new Error("Link do ya file chuno");
      await act(() => api("/api/videos", { method: "POST", body: { video_url: url, page: fd.get("page"), title: fd.get("title") || "", campaign_url: fd.get("campaign_url") || "" } }), "Video queue mein hai, bot clips bana raha hai");
      e.target.reset();
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; btn.textContent = "＋ Queue mein daalo"; }
  });
  $("#campForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await act(() => api("/api/campaigns", { method: "POST", body: f }), "Campaign add ho gaya, bot jaldi padhega");
    e.target.reset();
  });
}

// ------------------------------------------------------------------ campaigns
async function renderCampaigns() {
  const rows = await api("/api/campaigns");
  const f = STATE.campFilter;
  const shown = rows.filter((r) => f === "all" || (f === "active" ? ["ready", "pending"].includes(r.status) : r.status === f));
  const filters = [["all", "Sab"], ["active", "Active"], ["done", "Done"], ["skipped", "Skipped"], ["failed", "Failed"]]
    .map(([k, l]) => `<button class="small ${f === k ? "on" : ""}" onclick="STATE.campFilter='${k}';renderCampaigns()">${l} (${rows.filter((r) => k === "all" || (k === "active" ? ["ready", "pending"].includes(r.status) : r.status === k)).length})</button>`).join("");
  $("#tab-campaigns").innerHTML = `
    <div class="row between"><h1>Campaigns</h1><a href="#add"><button class="primary">＋ Campaign add karo</button></a></div>
    <div class="filters">${filters}</div>
    <div class="card table-wrap">${shown.length ? `<table>
      <thead><tr><th>Campaign</th><th>Page</th><th>Status</th><th>Pay</th><th class="num">Material</th><th class="num">Clips</th><th></th></tr></thead>
      <tbody>${shown.map((r) => {
        const [lvl, ic, label] = CAMP_STATUS[r.status] || ["", "•", r.status];
        return `<tr><td><div class="ellipsis" title="${esc(r.title)}">${r.manual ? esc(r.title) : `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`}</div>
            <small>${r.manual ? "Tumhari video" : esc((r.platforms || []).join(", "))}${r.reason ? " · " + esc(r.reason) : ""}${r.error ? " · " + esc(r.error) : ""}</small></td>
          <td>${esc(r.page || "–")}</td><td>${chip(lvl, ic, label)}</td>
          <td>${esc(r.pay || (r.cpm ? "$" + r.cpm + "/1K" : "–"))}</td><td class="num">${r.materials}</td><td class="num">${r.clips}</td>
          <td><div class="row">${r.status === "skipped" || r.status === "failed" ? `<button class="small" onclick="setCamp(${r.id},'${r.manual ? "ready" : "pending"}')">Retry</button>` : ""}
            ${["ready", "pending"].includes(r.status) ? `<button class="small" onclick="setCamp(${r.id},'skipped')">Skip</button>` : ""}</div></td></tr>`;
      }).join("")}</tbody></table>` : `<div class="empty"><b>Koi campaign nahi</b>Bot ON hone pe Vyro se campaigns yahan aayenge.</div>`}</div>`;
}
async function setCamp(id, status) { await act(() => api(`/api/campaigns/${id}/status`, { method: "POST", body: { status } }), "Updated"); renderCampaigns(); }

// ------------------------------------------------------------------ clips
async function renderClips() {
  if (!STATE.pages.length) STATE.pages = await api("/api/pages");
  const clips = await api("/api/clips" + (STATE.clipFilter ? `?page=${encodeURIComponent(STATE.clipFilter)}` : ""));
  const filters = [["", "Sab pages"], ...STATE.pages.map((p) => [p.name, p.name])]
    .map(([k, l]) => `<button class="small ${STATE.clipFilter === k ? "on" : ""}" onclick="STATE.clipFilter='${esc(k)}';renderClips()">${esc(l)}</button>`).join("");
  $("#tab-clips").innerHTML = `
    <h1>Clips</h1>
    <div class="filters">${filters}</div>
    ${clips.length ? `<div class="grid clips">${clips.map((c) => `
      <div class="card clip ${c.status === "skipped" ? "skipped" : ""}">
        <div class="thumb" style="background-image:url('/media/thumb/${c.id}')" onclick="playClip(${c.id})"><span class="score">🔥 ${c.score}/10</span></div>
        <div class="body">
          <div class="title">${esc(c.title)}</div>
          <small>${esc(c.page)} · ${c.duration}s · ${ago(c.created)}</small>
          <div class="chips">${postChip("youtube", c.posts.youtube)}${postChip("instagram", c.posts.instagram)}${vyroChip(c.posts)}${c.status === "skipped" ? chip("", "–", "skipped") : ""}</div>
          <div class="row" style="margin-top:auto">
            <button class="small" onclick="clipPriority(${c.id})" title="Queue mein sabse aage">⇡ Pehle post</button>
            <button class="small" onclick="clipSkip(${c.id}, ${c.status !== "skipped"})">${c.status === "skipped" ? "Wapas lao" : "Skip"}</button>
          </div>
        </div>
      </div>`).join("")}</div>` : `<div class="card empty"><b>Abhi koi clip nahi</b>Video add karo ya bot ko Vyro campaigns se clips banane do.</div>`}`;
  STATE.clips = clips;
}
function playClip(id) {
  const c = (STATE.clips || []).find((x) => x.id === id) || {};
  openModal(`<h2>${esc(c.title)}</h2><video class="player" src="/media/clip/${id}" controls autoplay playsinline></video>
    <p class="muted"><b>Kyun viral ho sakta hai:</b> ${esc(c.reason || "")}</p>
    <details><summary class="muted">Caption</summary><pre style="white-space:pre-wrap">${esc(c.description || "")}</pre></details>`);
}
async function clipPriority(id) { await act(() => api(`/api/clips/${id}/priority`, { method: "POST" }), "Ye clip agla post hoga"); renderClips(); }
async function clipSkip(id, skip) { await act(() => api(`/api/clips/${id}/skip`, { method: "POST", body: { enabled: skip } }), skip ? "Clip skip" : "Clip wapas queue mein"); renderClips(); }

// ------------------------------------------------------------------ schedule
async function renderSchedule() {
  const s = await api("/api/schedule");
  const slot = (x) => `<div class="slot">
      <div class="when">${!x.queue_len ? "–" : !s.enabled ? "Bot OFF" : until(x.next_at)}<small>${x.queue_len ? clock(Math.max(x.next_at, Date.now() / 1000)) : "queue khali"}</small></div>
      <div style="flex:1;min-width:0">
        <div><b>${esc(x.page)}</b> · ${x.platform === "youtube" ? "YouTube Shorts" : "Instagram Reels"}</div>
        <small class="ellipsis" style="display:block">${x.next.length ? "Agla: " + esc(x.next[0].title) : "Koi clip queue mein nahi"}</small>
      </div>
      <div style="text-align:right"><div class="progress"><div style="width:${Math.min(100, (x.today / Math.max(1, x.limit)) * 100)}%"></div></div><small>aaj ${x.today}/${x.limit} · queue ${x.queue_len}</small></div>
    </div>`;
  $("#tab-schedule").innerHTML = `
    <h1>Schedule</h1>
    <div class="grid stats">
      <div class="card stat"><div class="label">Agla Vyro scan</div><div class="value" style="font-size:22px">${until(s.next_scan)}</div><div class="sub">har ${s.scan_every_hours} ghante</div></div>
      <div class="card stat"><div class="label">Bot round</div><div class="value" style="font-size:22px">har ${s.loop_minutes} min</div><div class="sub">post + submit check</div></div>
    </div>
    <div class="grid two">
      <div class="card"><h2>Aane wale posts</h2>${s.slots.length ? s.slots.map(slot).join("") : `<div class="empty"><b>Koi active page nahi</b><a href="#pages">Page add karo →</a></div>`}</div>
      <div class="card"><h2>Haal ke posts</h2>${s.recent.length ? `<ul class="activity">${s.recent.map((r) => `<li><time>${clock(r.at)}</time><span><b>${esc(r.page)}</b> ${r.platform === "youtube" ? "YT" : "IG"} · <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a> ${r.vyro === "submitted" ? chip("good", "✓", "Vyro") : ""}</span></li>`).join("")}</ul>` : `<div class="empty">Abhi tak koi post nahi</div>`}</div>
    </div>`;
}

// ------------------------------------------------------------------ earnings
async function renderEarnings() {
  const e = await api("/api/earnings");
  const maxE = Math.max(...e.by_page.map((b) => b.earned), 0.01);
  $("#tab-earnings").innerHTML = `
    <h1>Earnings</h1>
    <div class="grid stats">
      <div class="card stat hero"><div class="label">Estimated kamai</div><div class="value">${money(e.total_earned)}</div><div class="sub">views × campaign CPM</div></div>
      <div class="card stat"><div class="label">Total views</div><div class="value">${fmt(e.total_views)}</div><div class="sub">YouTube + Instagram</div></div>
    </div>
    <div class="alert"><b>ⓘ Note</b><span>Ye andaza hai: views × campaign ka rate (rate pata na ho to $${e.default_cpm}/1K). Vyro ke apne rules (minimum views, approval) lagte hain. Asli payout Vyro dashboard pe dekho.</span></div>
    <div class="grid two" style="margin-top:16px">
      <div class="card"><h2>Views per day (last 14 din)</h2><div id="earnChart" class="chart"></div></div>
      <div class="card"><h2>Page-wise kamai</h2>${e.by_page.length ? e.by_page.map((b) => `<div class="hbar" data-tip="${esc(b.page)}: ${money(b.earned)} · ${fmt(b.views)} views · ${b.posts} posts"><span class="ellipsis">${esc(b.page)}</span><div class="track"><div class="fill" style="width:${(b.earned / maxE) * 100}%"></div></div><span class="val">${money(b.earned)}</span></div>`).join("") : `<div class="empty">Abhi data nahi</div>`}</div>
    </div>
    <div class="card table-wrap" style="margin-top:16px"><h2>Top posts</h2>${e.top.length ? `<table>
      <thead><tr><th>Clip</th><th>Page</th><th>Platform</th><th class="num">Views</th><th class="num">Likes</th><th class="num">CPM</th><th class="num">Est. $</th><th>Vyro</th></tr></thead>
      <tbody>${e.top.map((r) => `<tr><td><div class="ellipsis"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a></div></td><td>${esc(r.page)}</td><td>${r.platform === "youtube" ? "YouTube" : "Instagram"}</td>
        <td class="num">${fmt(r.views)}</td><td class="num">${fmt(r.likes)}</td><td class="num">${r.cpm ? "$" + r.cpm : "–"}</td><td class="num">${money(r.earned)}</td>
        <td>${r.vyro === "submitted" ? chip("good", "✓", "submitted") : r.vyro === "not_needed" ? chip("", "–", "manual") : r.vyro === "failed" ? chip("serious", "!", "retry") : chip("warning", "◌", "pending")}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">Posts hone ke baad yahan dikhega</div>`}</div>`;
  barChart($("#earnChart"), e.daily, { key: "views", aria: "Views per day" });
  bindTips($("#tab-earnings"));
}

// ------------------------------------------------------------------ logs
async function renderLogs() {
  const { lines } = await api("/api/logs?lines=400");
  const box = $("#tab-logs .logbox");
  const html = lines.map((l) => { const lvl = (l.match(/ (INFO|WARNING|ERROR) /) || [])[1] || ""; return `<div class="${lvl}">${esc(l)}</div>`; }).join("") || "Abhi koi log nahi";
  if (box) {
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    box.innerHTML = html;
    if (atBottom) box.scrollTop = box.scrollHeight;
  } else {
    $("#tab-logs").innerHTML = `<div class="row between"><h1>Logs</h1><small class="muted">har 5 second update</small></div><div class="logbox">${html}</div>`;
    const b = $("#tab-logs .logbox"); b.scrollTop = b.scrollHeight;
  }
}

// ------------------------------------------------------------------ settings
function vpnStateChip(vp) {
  if (!vp.wanted) return chip("", "○", "off");
  return vp.state === "on" ? chip("good", "●", "connected") : vp.state === "error" ? chip("critical", "✕", "error", vp.error) : chip("warning", "◌", "connecting");
}
async function vpnUse(name) {
  try { toast((await api("/api/vpn", { method: "POST", body: { enabled: true, config: name } })).message); } catch (e) { toast(e.message, true); }
  pollVpn(); setTimeout(renderSettings, 800);
}
async function vpnDelete(name) {
  if (!confirm(`Server "${name}" delete karna hai?`)) return;
  await act(() => api(`/api/vpn/configs/${encodeURIComponent(name)}`, { method: "DELETE" }), "Server delete ho gaya");
  renderSettings();
}
async function vpnAdd() {
  const file = $("#vpnFile").files[0];
  const text = file ? await file.text() : $("#vpnText").value;
  const name = $("#vpnName").value || (file ? file.name : "");
  if (!text.trim()) return toast("Config file chuno ya paste karo", true);
  if (!name.trim()) return toast("Server ka naam do", true);
  await act(() => api("/api/vpn/configs", { method: "POST", body: { name, text } }));
  renderSettings();
}
async function renderSettings() {
  const [s, vp] = await Promise.all([api("/api/settings"), api("/api/vpn")]);
  renderVpnBtn(vp);
  const v = s.vyro, c = s.clip;
  $("#tab-settings").innerHTML = `
    <h1>Settings</h1>
    <form id="setForm" class="stack">
      <div class="grid two">
        <div class="card">
          <h2>Vyro</h2>
          <div class="vpn-hero" style="flex-direction:column;align-items:stretch;gap:10px">
            <div class="row between">
              <b>Login: ${loginChip(s)}</b>
              <button type="button" class="small" onclick="vyroCheck()">⟳ Check karo</button>
            </div>
            <div class="row">
              <button type="button" class="primary" onclick="vyroLogin('bot')">🔑 Vyro Login</button>
              <button type="button" onclick="vyroLogin('normal')" title="Google sign-in block ho to">🌐 Normal browser se</button>
              <button type="button" onclick="vyroLoginDone()" title="Normal browser wala login ho gaya">✓ Login ho gaya</button>
            </div>
            <div class="hint">
              <b>Kaise:</b> "Vyro Login" dabao → browser khulega (${s.system_browser === "bundled" ? "bot ka browser" : s.system_browser === "msedge" ? "Microsoft Edge" : "Chrome"}) → app.vyro.com pe email daalo →
              email mein aaya <b>code</b> wahin daalo, ya email ka <b>login link</b> copy karke neeche paste karo → login hone ke baad <b>window band karo</b>.
              Google se login block ho to "Normal browser se" try karo. Login ke baad Vyro mein apne YouTube/Instagram accounts bhi connect kar dena.
            </div>
            <div class="row" style="flex-wrap:nowrap">
              <input type="url" id="loginLink" placeholder="Email wala login link yahan paste karo (optional)">
              <button type="button" onclick="vyroLogin('bot', $('#loginLink').value)">Link kholo</button>
            </div>
          </div>
          <label class="field"><span>Campaigns page ka link</span><input type="url" name="start_url" value="${esc(v.start_url)}"><div class="hint">Vyro pe login karke jis page pe campaigns ki list dikhti hai, uska URL</div></label>
          <div class="form-grid">
            <label class="field"><span>Scan har kitne ghante</span><input type="number" step="0.5" min="0.5" name="scan_every_hours" value="${v.scan_every_hours}"></label>
            <label class="field"><span>Minimum CPM ($/1K views)</span><input type="number" step="0.1" min="0" name="min_cpm_usd" value="${v.min_cpm_usd}"></label>
            <label class="field"><span>Naye campaigns / scan</span><input type="number" min="1" name="max_new_campaigns_per_scan" value="${v.max_new_campaigns_per_scan}"></label>
            <label class="field"><span>Videos / campaign</span><input type="number" min="1" name="max_materials_per_campaign" value="${v.max_materials_per_campaign}"></label>
          </div>
          <label class="check"><input type="checkbox" name="headless" ${v.headless ? "checked" : ""}> Browser window chhupa ke chalao (headless)</label>
        </div>
        <div class="card">
          <h2>Clips</h2>
          <div class="form-grid">
            <label class="field"><span>Vertical kaise banaye</span><select name="crop_mode">${[["face", "Face tracking"], ["center", "Center crop"], ["blur", "Blur background"]].map(([k, l]) => `<option value="${k}" ${c.crop_mode === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="field"><span>Transcript quality</span><select name="whisper_model">${[["base", "Fast (base)"], ["small", "Normal (small)"], ["medium", "Achha (medium, GPU)"], ["large-v3", "Best (large, GPU)"]].map(([k, l]) => `<option value="${k}" ${c.whisper_model === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
            <label class="field"><span>Min clip length (sec)</span><input type="number" min="5" name="min_seconds" value="${c.min_seconds}"></label>
            <label class="field"><span>Max clip length (sec)</span><input type="number" min="10" max="180" name="max_seconds" value="${c.max_seconds}"></label>
            <label class="field"><span>Subtitle highlight color</span><input type="text" name="caption_highlight_color" value="${esc(c.caption_highlight_color)}" placeholder="FFFF00"></label>
          </div>
          <label class="check"><input type="checkbox" name="captions" ${c.captions ? "checked" : ""}> Subtitles lagao</label>
          <label class="check"><input type="checkbox" name="hook_text" ${c.hook_text ? "checked" : ""}> Upar hook title (clip ka title bold box mein)</label>
          <label class="check"><input type="checkbox" name="progress_bar" ${c.progress_bar ? "checked" : ""}> Neeche progress bar</label>
          <label class="check"><input type="checkbox" name="zoom" ${c.zoom ? "checked" : ""}> Slow zoom-in (video chalti hui lagti hai)</label>
          <div class="form-grid">
            <label class="field"><span>Hook title kitni der (sec, 0 = poori clip)</span><input type="number" min="0" step="0.5" name="hook_seconds" value="${c.hook_seconds}"></label>
            <label class="field"><span>Music volume (0 = band)</span><input type="number" min="0" max="1" step="0.01" name="music_volume" value="${c.music_volume}"></label>
          </div>
          <div class="hint">Music: Rare Cash folder ke andar <code>music</code> folder mein copyright-free .mp3 daalo (abhi ${s.music_tracks} gaane). Khali = no music.</div>
          <label class="check"><input type="checkbox" name="caption_uppercase" ${c.caption_uppercase ? "checked" : ""}> Subtitles CAPITAL letters mein</label>
        </div>
      </div>
      <div class="grid two">
        <div class="card">
          <h2>Claude AI</h2>
          <label class="field"><span>API key ${s.api_key_set ? "(set hai)" : ""}</span><input type="password" name="api_key" autocomplete="off" placeholder="${s.api_key_set ? "••••••••  (badalna ho to hi daalo)" : "sk-ant-..."}"><div class="hint">platform.claude.com se. Sirf tumhare PC ki .env file mein save hoti hai.</div></label>
          ${s.client_secret_found ? chip("good", "✓", "client_secret.json mili") : chip("warning", "!", "client_secret.json nahi mili (YouTube ke liye zaroori)")}
        </div>
        <div class="card">
          <h2>Bot</h2>
          <label class="field"><span>Round har kitne minute</span><input type="number" min="1" name="loop_minutes" value="${s.loop_minutes}"></label>
          <label class="check"><input type="checkbox" id="darkTheme" ${localStorage.theme === "dark" ? "checked" : ""}> Dark theme</label>
        </div>
      </div>
      <div class="card" id="phoneCard">
        <div class="card-head"><h2>Phone se dashboard</h2>${s.remote.active ? chip("good", "●", "chal raha hai") : s.remote.lan_enabled ? chip("warning", "!", "restart karo") : chip("", "○", "off")}</div>
        <p class="muted" style="margin-top:0">Phone aur PC <b>same Wi-Fi</b> pe hon to phone ke browser mein dashboard khul jayega (PIN ke saath). Ghar ke bahar se control ke liye Telegram use karo.</p>
        ${s.remote.active && s.remote.lan_ip ? `<div class="vpn-hero"><div style="flex:1"><small>Phone ke browser mein ye kholo</small><div class="big" style="font-size:24px">http://${esc(s.remote.lan_ip)}:${s.remote.port_now}</div></div></div>` : ""}
        <div class="form-grid">
          <label class="field"><span>PIN ${s.remote.pin_set ? "(set hai)" : "(4-12 number)"}</span><input type="password" name="pin" inputmode="numeric" autocomplete="new-password" placeholder="${s.remote.pin_set ? "•••• (badalna ho to hi)" : "jaise 482913"}"></label>
          <label class="field"><span>Port</span><input type="number" name="remote_port" min="1024" max="65535" value="${s.remote.port}"></label>
        </div>
        <label class="check"><input type="checkbox" name="lan_enabled" ${s.remote.lan_enabled ? "checked" : ""}> Phone access ON</label>
        <div class="hint">ON karne ke baad Rare Cash band karke dobara kholo. Windows Firewall poochhe to "Private networks" pe <b>Allow</b> karo.</div>
      </div>
      <div class="card" id="tgCard">
        <div class="card-head"><h2>Telegram alerts + phone control</h2>${s.telegram.enabled && s.telegram.chat_id && s.telegram.token_set ? chip("good", "✓", "connected") : chip("", "○", "off")}</div>
        <p class="muted" style="margin-top:0">Post hua, error aaya, VPN gira, login expire hua: sab phone pe aayega. Phone se <code>/on</code> <code>/off</code> <code>/status</code> <code>/run</code> <code>/today</code> bhej ke bot control karo.</p>
        <ol class="hint" style="margin:0 0 12px;padding-left:18px">
          <li>Telegram mein <b>@BotFather</b> kholo → <code>/newbot</code> → naam do → jo <b>token</b> mile wo neeche daalo → Save</li>
          <li>Apne naye bot ko Telegram pe <code>/start</code> bhejo</li>
          <li>Yahan "Use karo" dabao, phir "Test" dabao</li>
        </ol>
        <div class="form-grid">
          <label class="field"><span>Bot token ${s.telegram.token_set ? "(set hai)" : ""}</span><input type="password" name="tg_token" autocomplete="off" placeholder="${s.telegram.token_set ? "•••••• (badalna ho to hi daalo)" : "123456:ABC..."}"></label>
          <label class="field"><span>Chat id</span><input type="text" name="tg_chat" value="${esc(s.telegram.chat_id)}" placeholder="/start bhejne ke baad apne aap aayega"></label>
        </div>
        ${s.telegram.pending_chat ? `<div class="alert"><b>Naya chat mila</b><span>${esc(s.telegram.pending_chat)}</span><a href="javascript:tgUse()">Use karo →</a></div>` : ""}
        <div class="row" style="margin-bottom:10px">
          <label class="check" style="margin:0"><input type="checkbox" name="tg_enabled" ${s.telegram.enabled ? "checked" : ""}> Telegram ON</label>
          <label class="check" style="margin:0"><input type="checkbox" name="tg_posts" ${s.telegram.notify_posts ? "checked" : ""}> Har post</label>
          <label class="check" style="margin:0"><input type="checkbox" name="tg_errors" ${s.telegram.notify_errors ? "checked" : ""}> Errors</label>
          <label class="check" style="margin:0"><input type="checkbox" name="tg_campaigns" ${s.telegram.notify_campaigns ? "checked" : ""}> Naye campaigns</label>
          <label class="check" style="margin:0"><input type="checkbox" name="tg_summary" ${s.telegram.notify_summary ? "checked" : ""}> Roz ka hisaab (${s.telegram.summary_hour}:00)</label>
        </div>
        <button type="button" onclick="tgTest()">✈ Test message bhejo</button>
      </div>
      <div class="card" id="vpnCard">
        <div class="card-head"><h2>VPN (built-in)</h2>${vpnStateChip(vp)}</div>
        <div class="vpn-hero">
          <div style="flex:1">
            <div class="big">${vp.wanted && vp.state === "on" ? `Connected · ${esc(vp.country || "?")}` : vp.wanted ? (vp.state === "error" ? "Connect nahi hua" : "Connecting…") : "VPN OFF"}</div>
            <small>${vp.wanted ? `${esc(vp.config)}${vp.ip ? " · " + esc(vp.ip) : ""}${vp.error ? " · " + esc(vp.error) : ""}` : "Rare Cash ka saara kaam (Vyro, upload, views) VPN se jayega. Baaki PC normal rahega."}</small>
          </div>
          <button type="button" class="${vp.wanted ? "" : "primary"}" onclick="$('#vpnBtn').click()">${vp.wanted ? "Disconnect" : "Connect"}</button>
        </div>
        <div class="grid two">
          <div>
            <h2 style="margin-bottom:8px">Servers</h2>
            ${vp.configs.length ? vp.configs.map((c) => `<div class="server">
                <span class="flag">${esc(c.name.slice(0, 2).toUpperCase())}</span>
                <div class="info"><b>${esc(c.name)}</b><small>${esc(c.endpoint)}</small></div>
                ${vp.selected === c.name && vp.wanted ? chip("good", "●", "active") : `<button type="button" class="small" onclick="vpnUse('${esc(c.name)}')">Connect</button>`}
                <button type="button" class="small danger" onclick="vpnDelete('${esc(c.name)}')">✕</button></div>`).join("")
              : `<div class="empty" style="padding:16px"><b>Koi server nahi</b>Apne VPN provider se WireGuard <code>.conf</code> file laao aur add karo.</div>`}
            <div class="hint" style="margin-top:8px">VPN engine: ${vp.engine_installed ? "✓ ready" : "pehli baar Connect pe apne aap download hoga (~5 MB)"}</div>
          </div>
          <div>
            <h2 style="margin-bottom:8px">Server add karo</h2>
            <label class="field"><span>Naam (jaise us-newyork)</span><input type="text" id="vpnName" placeholder="us-server"></label>
            <label class="field"><span>WireGuard .conf file</span><input type="file" id="vpnFile" accept=".conf,text/plain"></label>
            <label class="field"><span>…ya config yahan paste karo</span><textarea id="vpnText" rows="4" placeholder="[Interface]&#10;PrivateKey = ...&#10;Address = ...&#10;&#10;[Peer]&#10;PublicKey = ...&#10;Endpoint = ..."></textarea></label>
            <button type="button" class="blue" onclick="vpnAdd()">＋ Server save karo</button>
            <div class="hint">Config sirf tumhare PC pe <code>vpn/configs</code> mein save hoti hai.</div>
          </div>
        </div>
        <fieldset style="margin-top:16px"><legend>VPN guard</legend>
          <label class="check"><input type="checkbox" name="vpn_required" ${s.network.vpn_required ? "checked" : ""}> Sirf in countries se kaam karo (warna Vyro/posting roko)</label>
          <div class="form-grid">
            <label class="field"><span>Allowed countries</span><input type="text" name="allowed_countries" value="${esc(s.network.allowed_countries.join(", "))}" placeholder="US, GB, CA, AU"><div class="hint">US = United States, GB = UK, CA = Canada, AU = Australia</div></label>
            <div class="field"><span class="muted" style="display:block;font-size:12.5px;font-weight:600;margin-bottom:5px">Abhi ka internet <span id="vpnNow">${vpnChip(STATE.overview && STATE.overview.vpn, s.network.vpn_required)}</span></span><button type="button" onclick="checkVpn()">⟳ Check karo</button></div>
          </div>
        </fieldset>
      </div>
      <div><button class="primary" type="submit">Save settings</button></div>
    </form>`;
  $("#darkTheme").addEventListener("change", (e) => {
    localStorage.theme = e.target.checked ? "dark" : "light";
    if (e.target.checked) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme;
  });
  $("#setForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, fd = Object.fromEntries(new FormData(f));
    await act(() => api("/api/settings", { method: "POST", body: {
      vyro: { start_url: fd.start_url, scan_every_hours: +fd.scan_every_hours, min_cpm_usd: +fd.min_cpm_usd, max_new_campaigns_per_scan: +fd.max_new_campaigns_per_scan, max_materials_per_campaign: +fd.max_materials_per_campaign, headless: f.headless.checked },
      network: { vpn_required: f.vpn_required.checked, allowed_countries: (fd.allowed_countries || "").split(",") },
      telegram: { enabled: f.tg_enabled.checked, chat_id: (fd.tg_chat || "").trim(), notify_posts: f.tg_posts.checked, notify_errors: f.tg_errors.checked, notify_campaigns: f.tg_campaigns.checked, notify_summary: f.tg_summary.checked },
      telegram_token: fd.tg_token || null,
      remote: { lan_enabled: f.lan_enabled.checked, port: +fd.remote_port || 8000 },
      pin: fd.pin || null,
      loop_minutes: +fd.loop_minutes,
      clip: { crop_mode: fd.crop_mode, whisper_model: fd.whisper_model, min_seconds: +fd.min_seconds, max_seconds: +fd.max_seconds, caption_highlight_color: (fd.caption_highlight_color || "FFFF00").replace("#", "").toUpperCase(), captions: f.captions.checked, caption_uppercase: f.caption_uppercase.checked, hook_text: f.hook_text.checked, progress_bar: f.progress_bar.checked, zoom: f.zoom.checked, hook_seconds: +fd.hook_seconds || 0, music_volume: +fd.music_volume || 0 },
      api_key: fd.api_key || null,
    } }), "Settings save ho gayi");
    renderSettings();
  });
}
async function checkVpn() {
  try {
    const v = await api("/api/network?refresh=1");
    $("#vpnNow").innerHTML = vpnChip(v, v.required) || chip("", "?", "pata nahi chala");
    $("#vpnChip").innerHTML = vpnChip(v, v.required);
    toast(v.country ? `Internet ${v.country_name} se aa raha hai (${v.ip})` : "Country pata nahi chali (internet check karo)");
  } catch (e) { toast(e.message, true); }
}
function loginChip(s) {
  const c = s.login_check || {};
  if (c.ok === true) return chip("good", "✓", `logged in · ${ago(c.at)}`);
  if (c.ok === false) return chip("critical", "✕", "login nahi hua", c.url || "");
  if (c.ok === null && c.error) return chip("warning", "!", "check fail", c.error);
  return s.vyro_logged_in ? chip("info", "◌", "saved (check karo)") : chip("critical", "✕", "login nahi hua");
}
async function vyroLogin(mode = "bot", link = "") {
  await act(() => api("/api/vyro/login", { method: "POST", body: { mode, link: (link || "").trim() } }));
  setTimeout(() => STATE.tab === "settings" && renderSettings(), 15000);
}
async function tgTest() { await act(() => api("/api/telegram/test", { method: "POST" })); }
async function tgUse() { await act(() => api("/api/telegram/use-pending", { method: "POST" })); renderSettings(); }
async function vyroLoginDone() { await act(() => api("/api/vyro/login-done", { method: "POST" })); setTimeout(renderSettings, 20000); }
async function vyroCheck() { await act(() => api("/api/vyro/check", { method: "POST" })); setTimeout(renderSettings, 20000); }

// ------------------------------------------------------------------ router
const RENDER = { dashboard: () => refreshTop(), pages: renderPages, add: renderAdd, campaigns: renderCampaigns, clips: renderClips, schedule: renderSchedule, earnings: renderEarnings, logs: renderLogs, settings: renderSettings };
const AUTO_REFRESH = { dashboard: 5000, schedule: 30000, logs: 5000, pages: 15000 };

function route() {
  closeModal();
  const tab = (location.hash.slice(1) || "dashboard").split("?")[0];
  STATE.tab = RENDER[tab] ? tab : "dashboard";
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + STATE.tab));
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === STATE.tab));
  STATE.timers.forEach(clearInterval); STATE.timers = [];
  setHeader();
  if (STATE.tab === "logs") $("#tab-logs").innerHTML = "";
  Promise.resolve(RENDER[STATE.tab]()).catch((e) => toast(e.message, true));
  if (AUTO_REFRESH[STATE.tab]) STATE.timers.push(setInterval(() => { if ($("#modal").hidden) RENDER[STATE.tab](); }, AUTO_REFRESH[STATE.tab]));
}
window.addEventListener("hashchange", route);
setInterval(() => { if (STATE.tab !== "dashboard") refreshTop(); }, 8000);
setInterval(refreshVpn, 60000);
setTimeout(refreshVpn, 800);
refreshTop();
route();
