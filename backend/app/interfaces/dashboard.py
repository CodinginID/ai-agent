"""Read-only web dashboard for Octopus.

Serves a single self-contained HTML page at ``GET /dashboard``. The page holds
no secrets: the admin token is entered by the user, kept in ``localStorage``, and
sent as a Bearer header from the browser to the existing JSON APIs (``/health``,
``/tasks/``). It auto-refreshes every few seconds so you can glance at what
Octopus is doing right now without SSH or curl.

Kept as one inline HTML string (no build step, no static-file mounting) to match
the project's "no extra infra" stance.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Octopus Dashboard</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --fg:#e6edf3;
          --muted:#8b949e; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --acc:#58a6ff; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--fg); font-size:14px; }
  header { display:flex; align-items:center; gap:12px; padding:14px 20px;
           border-bottom:1px solid var(--border); background:var(--panel); position:sticky; top:0; }
  header h1 { font-size:16px; margin:0; font-weight:600; }
  header .spacer { flex:1; }
  .pill { padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .pill.ok { background:rgba(63,185,80,.15); color:var(--ok); }
  .pill.degraded { background:rgba(210,153,34,.15); color:var(--warn); }
  .pill.unknown { background:rgba(139,148,158,.15); color:var(--muted); }
  main { padding:20px; max-width:1000px; margin:0 auto; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }
  .card { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px; }
  .card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
  .card .value { font-size:20px; font-weight:600; margin-top:6px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:middle; }
  .dot.ok { background:var(--ok); } .dot.down { background:var(--bad); } .dot.unknown { background:var(--muted); }
  h2 { font-size:14px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; margin:24px 0 10px; }
  table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--border); border-radius:8px; overflow:hidden; }
  th,td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--border); font-size:13px; }
  th { color:var(--muted); font-weight:600; font-size:11px; text-transform:uppercase; }
  tr:last-child td { border-bottom:none; }
  .status { font-weight:600; }
  .status.closed,.status.done,.status.step_ok { color:var(--ok); }
  .status.failed,.status.step_failed { color:var(--bad); }
  .status.started,.status.step_started,.status.issue_opened { color:var(--acc); }
  a { color:var(--acc); text-decoration:none; } a:hover { text-decoration:underline; }
  .muted { color:var(--muted); }
  .empty { text-align:center; color:var(--muted); padding:24px; }
  .login { max-width:360px; margin:80px auto; text-align:center; }
  .login input { width:100%; padding:10px; margin:12px 0; background:var(--bg); border:1px solid var(--border);
                 border-radius:6px; color:var(--fg); font-size:14px; }
  .login button, .btn { padding:9px 16px; background:var(--acc); color:#0d1117; border:none; border-radius:6px;
                        font-weight:600; cursor:pointer; font-size:13px; }
  .btn.ghost { background:transparent; color:var(--muted); border:1px solid var(--border); }
  .err { color:var(--bad); font-size:13px; min-height:18px; }
  code { background:var(--bg); padding:1px 5px; border-radius:4px; font-size:12px; }
</style>
</head>
<body>
<div id="app"></div>
<script>
const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "octopus_admin_token";
let timer = null;

function getToken() { return localStorage.getItem(TOKEN_KEY) || ""; }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
}

async function api(path) {
  const r = await fetch(path, { headers: { "Authorization": "Bearer " + getToken() } });
  if (r.status === 401) { const e = new Error("unauthorized"); e.code = 401; throw e; }
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function renderLogin(msg) {
  if (timer) { clearInterval(timer); timer = null; }
  $("app").innerHTML = `
    <div class="login">
      <h1>&#128375; Octopus Dashboard</h1>
      <p class="muted">Masukkan admin token untuk memantau.</p>
      <input id="tok" type="password" placeholder="ADMIN_TOKEN" autofocus>
      <div class="err" id="loginErr">${esc(msg || "")}</div>
      <button onclick="doLogin()">Masuk</button>
    </div>`;
  $("tok").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
}

function doLogin() {
  const t = $("tok").value.trim();
  if (!t) { $("loginErr").textContent = "Token tidak boleh kosong."; return; }
  setToken(t);
  start();
}

function renderShell() {
  $("app").innerHTML = `
    <header>
      <h1>&#128375; Octopus</h1>
      <span class="pill unknown" id="statusPill">memuat...</span>
      <div class="spacer"></div>
      <span class="muted" id="lastUpdate"></span>
      <button class="btn ghost" onclick="logout()">Keluar</button>
    </header>
    <main>
      <div class="grid" id="statCards"></div>
      <h2>Task Aktif</h2>
      <div id="tasksBox"></div>
      <h2>Timeline Event</h2>
      <div id="eventsBox"></div>
    </main>`;
}

function statCard(label, value) {
  return `<div class="card"><div class="label">${esc(label)}</div><div class="value">${value}</div></div>`;
}

function renderHealth(h) {
  const st = h.status || "unknown";
  const pill = $("statusPill");
  pill.className = "pill " + (st === "ok" ? "ok" : st === "degraded" ? "degraded" : "unknown");
  pill.textContent = st.toUpperCase();
  const deps = h.dependencies || {};
  const depDots = Object.keys(deps).map((k) => {
    const v = deps[k]; const cls = v === "ok" ? "ok" : "down";
    return `<div><span class="dot ${cls}"></span>${esc(k)}: <span class="muted">${esc(v)}</span></div>`;
  }).join("");
  $("statCards").innerHTML =
    statCard("Versi", "<code>" + esc(h.version || "?") + "</code>") +
    statCard("Status", esc(st)) +
    `<div class="card"><div class="label">Dependencies</div><div class="value" style="font-size:13px;line-height:1.9">${depDots || "-"}</div></div>`;
}

function renderTasks(tasks) {
  if (!tasks || !tasks.length) { $("tasksBox").innerHTML = `<div class="card empty">Tidak ada task.</div>`; return; }
  const rows = tasks.map((t) => {
    const issue = t.issue_url ? `<a href="${esc(t.issue_url)}" target="_blank">#${esc(t.issue_number)}</a>` : "-";
    return `<tr>
      <td><code>${esc((t.task_id || "").slice(0, 8))}</code></td>
      <td class="status ${esc(t.status)}">${esc(t.status)}</td>
      <td>${esc(t.role)}</td>
      <td>${esc(t.message)}</td>
      <td>${issue}</td></tr>`;
  }).join("");
  $("tasksBox").innerHTML =
    `<table><thead><tr><th>Task</th><th>Status</th><th>Role</th><th>Pesan</th><th>Issue</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderEvents(events) {
  if (!events || !events.length) { $("eventsBox").innerHTML = `<div class="card empty">Belum ada event.</div>`; return; }
  const rows = events.map((e) => `<tr>
      <td class="muted">${esc((e.ts || "").replace("T", " ").slice(0, 19))}</td>
      <td><code>${esc((e.task_id || "").slice(0, 8))}</code></td>
      <td>${esc(e.role)}</td>
      <td class="status ${esc(e.status)}">${esc(e.status)}</td>
      <td>${esc(e.message)}</td></tr>`).join("");
  $("eventsBox").innerHTML =
    `<table><thead><tr><th>Waktu</th><th>Task</th><th>Role</th><th>Status</th><th>Pesan</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function refresh() {
  try {
    const [health, board] = await Promise.all([api("/health"), api("/tasks/")]);
    renderHealth(health);
    renderTasks(board.tasks);
    renderEvents(board.events);
    $("lastUpdate").textContent = "Diperbarui " + new Date().toLocaleTimeString("id-ID");
  } catch (e) {
    if (e.code === 401) { clearToken(); renderLogin("Token salah atau kadaluarsa."); }
  }
}

function start() {
  renderShell();
  refresh();
  if (timer) clearInterval(timer);
  timer = setInterval(refresh, 5000);
}

function logout() { clearToken(); renderLogin(""); }

if (getToken()) start(); else renderLogin("");
</script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the self-contained read-only dashboard page."""
    return HTMLResponse(content=_PAGE)
