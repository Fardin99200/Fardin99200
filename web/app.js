// Rare Cash dashboard (vanilla JS, no build step)
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n || 0).toLocaleString("en-IN");
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const STATE = { tab: "dashboard", pages: [], clipFilter: "", campFilter: "all", timers: [] };

if (localStorage.theme === "light") document.documentElement.dataset.theme = "light";

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
async function refreshTop() {
  try {
    const o = await api("/api/overview");
    STATE.overview = o;
    $("#powerToggle").checked = o.enabled;
    $("#powerLabel").textContent = o.enabled ? "Bot ON" : "Bot OFF";
    $("#statusText").textContent = o.status;
    $("#engineDot").className = "dot " + (!o.engine_alive ? "dead" : o.enabled ? "on" : "off");
    if (STATE.tab === "dashboard") renderDashboard(o);
  } catch (e) {
    $("#statusText").textContent = "Dashboard server se connect nahi ho pa raha";
    $("#engineDot").className = "dot dead";
  }
}
$("#powerToggle").addEventListener("change", async (e) => {
  const on = e.target.checked;
  await act(() => api("/api/bot", { method: "POST", body: { enabled: on } }), on ? "Bot ON ho gaya" : "Bot OFF: abhi wala kaam khatam karke ruk jayega");
  refreshTop();
});

// ------------------------------------------------------------------ dashboard
function renderDashboard(o) {
  const warn = o.warnings.map((w) => `<div class="alert ${w.level}"><b>${w.level === "critical" ? "✕ Zaroori" : "! Dhyan do"}</b><span>${esc(w.text)}</span>${w.tab ? `<a href="#${w.tab}">Fix karo →</a>` : ""}</div>`).join("");
  const stat = (label, value, sub = "", hero = false) => `<div class="card stat ${hero ? "hero" : ""}"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`;
  $("#tab-dashboard").innerHTML = `
    <h1>Dashboard</h1>
    ${warn ? `<div class="stack" style="margin-bottom:16px">${warn}</div>` : ""}
    <div class="grid stats">
      ${stat("Estimated kamai", money(o.earned), "views × campaign CPM", true)}
      ${stat("Total views", fmt(o.views), "saare posts")}
      ${stat("Aaj ke posts", fmt(o.posted_today), `${fmt(o.posted)} total`)}
      ${stat("Clips bane", fmt(o.clips), `${fmt(o.clips_today)} aaj`)}
      ${stat("Active campaigns", fmt(o.campaigns_active), `${fmt(o.campaigns_total)} total`)}
      ${stat("Vyro submitted", fmt(o.submitted), "links")}
    </div>
    <div class="grid two">
      <div class="card">
        <div class="row between"><h2>Views per day</h2><a href="#earnings">Earnings →</a></div>
        <div id="dashChart" class="chart"><div class="empty">Loading…</div></div>
      </div>
      <div class="card">
        <h2>Bot control</h2>
        <p class="muted" style="margin-top:0">${esc(o.status)}</p>
        <div class="row" style="margin-bottom:14px">
          <button class="primary" onclick="runNow()">▶ Abhi chalao</button>
          <button onclick="scanNow()">⟳ Vyro scan abhi</button>
        </div>
        <div class="muted" style="font-size:13px">
          Last round: <b>${ago(o.last_cycle)}</b><br>
          Agla Vyro scan: <b>${o.next_scan ? until(o.next_scan) : "jaldi"}</b><br>
          Active pages: <b>${o.pages}</b>
        </div>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="row between"><h2>Live activity</h2><a href="#logs">Saare logs →</a></div>
      ${activityList(o.activity)}
    </div>`;
  api("/api/earnings").then((e) => barChart($("#dashChart"), e.daily)).catch(() => {});
}
function activityList(lines) {
  if (!lines.length) return `<div class="empty"><b>Abhi koi activity nahi</b>Bot ON karo, kaam yahan dikhega.</div>`;
  return `<ul class="activity">${lines.slice().reverse().map((l) => {
    const m = l.match(/^(\S+ (\S+)) (\w+) (.*)$/);
    return m ? `<li class="${m[3]}"><time>${m[2].slice(0, 5)}</time><span>${esc(m[4])}</span></li>` : `<li><span>${esc(l)}</span></li>`;
  }).join("")}</ul>`;
}
async function runNow() { await act(() => api("/api/bot/run-now", { method: "POST" }), "Bot abhi ek round chalayega"); }
async function scanNow() { await act(() => api("/api/bot/scan-now", { method: "POST" }), "Vyro scan shuru ho raha hai"); }

// bar chart: single series, rounded data-end, 2px gaps, hover tooltip
function barChart(el, data) {
  if (!data.length || data.every((d) => !d.views)) {
    el.innerHTML = `<div class="empty"><b>Abhi views ka data nahi</b>Posts hone ke baad har 2 ghante views update honge.</div>`;
    return;
  }
  const W = 640, H = 220, L = 44, B = 24, T = 10;
  const max = Math.max(...data.map((d) => d.views)) || 1;
  const nice = Math.pow(10, Math.floor(Math.log10(max)));
  const top = Math.ceil(max / nice) * nice;
  const bw = (W - L) / data.length;
  const y = (v) => T + (H - T - B) * (1 - v / top);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Views per day">`;
  for (let i = 0; i <= 4; i++) {
    const v = (top / 4) * i;
    svg += `<line class="grid-line" x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><g class="axis"><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : v}</text></g>`;
  }
  data.forEach((d, i) => {
    const x = L + i * bw + 1, w = Math.max(2, bw - 2), h = Math.max(0, H - B - y(d.views));
    const r = Math.min(4, w / 2, h);
    const yy = H - B - h;
    const path = h > 0 ? `M${x},${H - B} V${yy + r} Q${x},${yy} ${x + r},${yy} H${x + w - r} Q${x + w},${yy} ${x + w},${yy + r} V${H - B} Z` : "";
    const label = new Date(d.day).toLocaleDateString([], { day: "numeric", month: "short" });
    svg += `<rect class="hit" x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}" fill="transparent" data-tip="${esc(label)}: ${fmt(d.views)} views"/>`;
    if (path) svg += `<path class="bar" d="${path}" pointer-events="none"/>`;
    if (i % Math.ceil(data.length / 7) === 0) svg += `<g class="axis"><text x="${x + w / 2}" y="${H - 6}" text-anchor="middle">${esc(label)}</text></g>`;
  });
  el.innerHTML = svg + "</svg>";
  bindTips(el);
}
function bindTips(el) {
  const tip = $("#tooltip");
  el.querySelectorAll("[data-tip]").forEach((n) => {
    n.addEventListener("mousemove", (e) => { tip.textContent = n.dataset.tip; tip.hidden = false; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY - 30 + "px"; });
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
  barChart($("#earnChart"), e.daily);
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
async function renderSettings() {
  const s = await api("/api/settings");
  const v = s.vyro, c = s.clip;
  $("#tab-settings").innerHTML = `
    <h1>Settings</h1>
    <form id="setForm" class="stack">
      <div class="grid two">
        <div class="card">
          <h2>Vyro</h2>
          <div class="row" style="margin-bottom:14px">
            <button type="button" class="primary" onclick="vyroLogin()">🔑 Vyro Login</button>
            ${s.vyro_logged_in ? chip("good", "✓", "login saved") : chip("critical", "✕", "login nahi hua")}
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
          <label class="check"><input type="checkbox" id="lightTheme" ${localStorage.theme === "light" ? "checked" : ""}> Light theme</label>
        </div>
      </div>
      <div><button class="primary" type="submit">Save settings</button></div>
    </form>`;
  $("#lightTheme").addEventListener("change", (e) => {
    localStorage.theme = e.target.checked ? "light" : "dark";
    if (e.target.checked) document.documentElement.dataset.theme = "light"; else delete document.documentElement.dataset.theme;
  });
  $("#setForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, fd = Object.fromEntries(new FormData(f));
    await act(() => api("/api/settings", { method: "POST", body: {
      vyro: { start_url: fd.start_url, scan_every_hours: +fd.scan_every_hours, min_cpm_usd: +fd.min_cpm_usd, max_new_campaigns_per_scan: +fd.max_new_campaigns_per_scan, max_materials_per_campaign: +fd.max_materials_per_campaign, headless: f.headless.checked },
      loop_minutes: +fd.loop_minutes,
      clip: { crop_mode: fd.crop_mode, whisper_model: fd.whisper_model, min_seconds: +fd.min_seconds, max_seconds: +fd.max_seconds, caption_highlight_color: (fd.caption_highlight_color || "FFFF00").replace("#", "").toUpperCase(), captions: f.captions.checked, caption_uppercase: f.caption_uppercase.checked },
      api_key: fd.api_key || null,
    } }), "Settings save ho gayi");
    renderSettings();
  });
}
async function vyroLogin() { await act(() => api("/api/vyro/login", { method: "POST" })); }

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
  if (STATE.tab === "logs") $("#tab-logs").innerHTML = "";
  Promise.resolve(RENDER[STATE.tab]()).catch((e) => toast(e.message, true));
  if (AUTO_REFRESH[STATE.tab]) STATE.timers.push(setInterval(() => { if ($("#modal").hidden) RENDER[STATE.tab](); }, AUTO_REFRESH[STATE.tab]));
}
window.addEventListener("hashchange", route);
setInterval(() => { if (STATE.tab !== "dashboard") refreshTop(); }, 8000);
refreshTop();
route();
