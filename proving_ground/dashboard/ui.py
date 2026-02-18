"""Single-page HTML UI for the proving-ground dashboard."""

INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proving Ground</title>
<style>
  :root { --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #e6edf3;
          --muted: #8b949e; --accent: #58a6ff; --green: #3fb950; --red: #f85149;
          --yellow: #d29922; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; padding: 24px; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 24px; margin-bottom: 4px; }
  h2 { font-size: 18px; margin: 24px 0 12px; color: var(--muted); font-weight: 500; }
  .subtitle { color: var(--muted); font-size: 14px; margin-bottom: 24px; }
  .controls { display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }
  button { background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 6px;
           cursor: pointer; font-size: 14px; font-weight: 500; }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-secondary { background: var(--surface); border: 1px solid var(--border); color: var(--text); }
  .status-bar { font-size: 13px; color: var(--muted); }
  .status-bar .running { color: var(--yellow); }
  .status-bar .done { color: var(--green); }
  .status-bar .error { color: var(--red); }
  table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 14px; }
  th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  tr:hover td { background: var(--surface); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .badge-green { background: #0d2818; color: var(--green); }
  .badge-red { background: #2d1215; color: var(--red); }
  .badge-yellow { background: #2d2200; color: var(--yellow); }
  .badge-blue { background: #0d1d30; color: var(--accent); }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .panel pre { font-size: 13px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; color: var(--muted); }
  .tabs { display: flex; gap: 0; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
  .tab { padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .hidden { display: none; }
  .empty { color: var(--muted); font-size: 14px; padding: 24px; text-align: center; }
  .clickable { cursor: pointer; }
  .clickable:hover td { color: var(--accent); }
  .metric { display: inline-block; margin-right: 20px; }
  .metric-value { font-size: 20px; font-weight: 600; }
  .metric-label { font-size: 12px; color: var(--muted); }
</style>
</head>
<body>

<h1>Proving Ground</h1>
<p class="subtitle">Fleet monitoring dashboard</p>

<div class="controls">
  <button id="btn-run" onclick="startRun()">Start Fleet Run</button>
  <span id="run-status" class="status-bar"></span>
</div>

<div class="tabs">
  <div class="tab active" data-tab="runs" onclick="switchTab('runs')">Runs</div>
  <div class="tab" data-tab="agents" onclick="switchTab('agents')">Agents</div>
  <div class="tab" data-tab="reviews" onclick="switchTab('reviews')">Reviews</div>
  <div class="tab" data-tab="improvements" onclick="switchTab('improvements')">Improvements</div>
</div>

<div id="tab-runs">
  <div id="runs-table"></div>
</div>

<div id="tab-agents" class="hidden">
  <div id="agents-table"></div>
</div>

<div id="tab-reviews" class="hidden">
  <div id="reviews-table"></div>
</div>

<div id="tab-improvements" class="hidden">
  <div id="improvements-table"></div>
</div>

<div id="detail-panel" class="hidden">
  <h2 id="detail-title"></h2>
  <div id="detail-content" class="panel"><pre></pre></div>
  <button class="btn-secondary" onclick="hideDetail()">Back</button>
</div>

<script>
const API = '/api';

function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  ['runs','agents','reviews','improvements'].forEach(id => {
    document.getElementById('tab-' + id).classList.toggle('hidden', id !== name);
  });
  hideDetail();
  if (name === 'runs') loadRuns();
  if (name === 'agents') loadAgents();
  if (name === 'reviews') loadReviews();
  if (name === 'improvements') loadImprovements();
}

async function api(path) {
  const r = await fetch(API + path);
  if (!r.ok && r.status !== 404) throw new Error(r.statusText);
  return r.json();
}

// --- Runs ---
async function loadRuns() {
  const runs = await api('/runs');
  if (!runs.length) { document.getElementById('runs-table').innerHTML = '<div class="empty">No runs yet. Start one above.</div>'; return; }
  let html = '<table><thead><tr><th>Date</th><th>Agents</th><th>Tokens</th><th>Duration</th></tr></thead><tbody>';
  for (const r of runs) {
    html += `<tr class="clickable" onclick="showRun('${r.date}')">
      <td>${r.date}</td><td>${r.agent_count}</td>
      <td>${r.total_tokens.toLocaleString()}</td><td>${r.total_duration_seconds.toFixed(1)}s</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('runs-table').innerHTML = html;
}

async function showRun(date) {
  const data = await api('/runs/' + date);
  document.getElementById('detail-title').textContent = 'Run: ' + date;
  let html = `<div style="margin-bottom:12px">`;
  html += `<span class="metric"><span class="metric-value">${data.agent_count}</span><br><span class="metric-label">Agents</span></span>`;
  html += `</div><table><thead><tr><th>Agent</th><th>Phases</th><th>Status</th><th>Tokens</th></tr></thead><tbody>`;
  for (const j of data.journals) {
    const failed = (j.phases || []).filter(p => p.status === 'failed').length;
    const total = (j.phases || []).length;
    const badge = failed ? 'badge-red' : 'badge-green';
    const label = failed ? `${failed}/${total} failed` : `${total} ok`;
    const tokens = (j.metrics || {}).total_tokens || 0;
    html += `<tr><td>${j.agent_id}</td><td>${total}</td><td><span class="badge ${badge}">${label}</span></td><td>${tokens.toLocaleString()}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('detail-content').innerHTML = html;
  showDetail();
}

// --- Agents ---
async function loadAgents() {
  const agents = await api('/agents');
  if (!agents.length) { document.getElementById('agents-table').innerHTML = '<div class="empty">No agents found.</div>'; return; }
  let html = '<table><thead><tr><th>Agent</th><th>Last Run</th><th>Journals</th></tr></thead><tbody>';
  for (const a of agents) {
    html += `<tr class="clickable" onclick="showAgent('${a.agent_id}')">
      <td>${a.agent_id}</td><td>${a.last_run}</td><td>${a.journal_count}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('agents-table').innerHTML = html;
}

async function showAgent(id) {
  const data = await api('/agents/' + id + '/journals');
  document.getElementById('detail-title').textContent = 'Agent: ' + id;
  let html = '<table><thead><tr><th>Date</th><th>Phases</th><th>Tokens</th><th>Bugs Suspected</th></tr></thead><tbody>';
  for (const j of data.journals) {
    const tokens = (j.metrics || {}).total_tokens || 0;
    const bugs = (j.diagnosis || {}).bugs_suspected || [];
    html += `<tr><td>${j.date}</td><td>${(j.phases||[]).length}</td><td>${tokens.toLocaleString()}</td><td>${bugs.length ? bugs.join(', ') : '-'}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('detail-content').innerHTML = html;
  showDetail();
}

// --- Reviews ---
async function loadReviews() {
  const reviews = await api('/reviews');
  if (!reviews.length) { document.getElementById('reviews-table').innerHTML = '<div class="empty">No reviews yet.</div>'; return; }
  let html = '<table><thead><tr><th>Date</th><th>Health</th><th>Summary</th></tr></thead><tbody>';
  for (const r of reviews) {
    const hc = r.fleet_health === 'healthy' ? 'badge-green' : r.fleet_health === 'unknown' ? 'badge-yellow' : 'badge-red';
    html += `<tr class="clickable" onclick="showReview('${r.date}')">
      <td>${r.date}</td><td><span class="badge ${hc}">${r.fleet_health}</span></td>
      <td>${(r.summary || '').substring(0, 80)}</td></tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('reviews-table').innerHTML = html;
}

async function showReview(date) {
  const data = await api('/reviews/' + date);
  document.getElementById('detail-title').textContent = 'Review: ' + date;
  let html = '';
  const health = data.health || {};
  if (health.fleet_health) html += `<p><strong>Health:</strong> ${health.fleet_health}</p>`;
  if (health.summary) html += `<p style="margin:8px 0">${health.summary}</p>`;
  if (data.bugs && data.bugs.length) {
    html += '<h2>Bugs</h2><ul>';
    for (const b of data.bugs) html += `<li>${b.title || JSON.stringify(b)}</li>`;
    html += '</ul>';
  }
  if (data.improvements && data.improvements.length) {
    html += '<h2>Improvements</h2><ul>';
    for (const b of data.improvements) html += `<li>${b.title || JSON.stringify(b)}</li>`;
    html += '</ul>';
  }
  document.getElementById('detail-content').innerHTML = html || '<div class="empty">No detail available.</div>';
  showDetail();
}

// --- Improvements ---
async function loadImprovements() {
  const data = await api('/improvements');
  if (!data.items.length) { document.getElementById('improvements-table').innerHTML = '<div class="empty">No improvement items.</div>'; return; }
  let html = '<table><thead><tr><th>#</th><th>Category</th><th>Frequency</th><th>Agents</th><th>Message</th></tr></thead><tbody>';
  data.items.forEach((item, i) => {
    const cc = {bug:'badge-red', suggestion:'badge-blue', tool_error:'badge-yellow', risk_flag:'badge-red'}[item.category] || 'badge-blue';
    html += `<tr><td>${i+1}</td><td><span class="badge ${cc}">${item.category}</span></td>
      <td>${item.frequency}</td><td>${item.agents.length}</td><td>${item.message.substring(0,100)}</td></tr>`;
  });
  html += '</tbody></table>';
  document.getElementById('improvements-table').innerHTML = html;
}

// --- Fleet run ---
async function startRun() {
  const btn = document.getElementById('btn-run');
  const status = document.getElementById('run-status');
  btn.disabled = true;
  status.innerHTML = '<span class="running">Running...</span>';
  try {
    const r = await fetch(API + '/runs', { method: 'POST' });
    const data = await r.json();
    if (r.ok && data.status === 'completed') {
      status.innerHTML = '<span class="done">Completed</span>';
      loadRuns();
    } else {
      status.innerHTML = `<span class="error">${data.detail || data.error || 'Failed'}</span>`;
    }
  } catch (e) {
    status.innerHTML = `<span class="error">${e.message}</span>`;
  }
  btn.disabled = false;
}

// --- Detail panel ---
function showDetail() {
  document.getElementById('detail-panel').classList.remove('hidden');
  ['runs','agents','reviews','improvements'].forEach(id => document.getElementById('tab-' + id).classList.add('hidden'));
}
function hideDetail() {
  document.getElementById('detail-panel').classList.add('hidden');
  document.querySelector('.tab.active').click();
}

// Init
loadRuns();
</script>
</body>
</html>
"""
