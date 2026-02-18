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
  .live-header { display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }
  .live-header .metric { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 20px; }
  .event-feed { max-height: 300px; overflow-y: auto; background: var(--surface); border: 1px solid var(--border);
                border-radius: 8px; padding: 12px; font-family: monospace; font-size: 13px; }
  .event-feed .event-line { padding: 2px 0; border-bottom: 1px solid var(--border); }
  .event-feed .event-line:last-child { border-bottom: none; }
  .event-time { color: var(--muted); margin-right: 8px; }
  .event-type { font-weight: 600; margin-right: 8px; }
  .event-type.fleet { color: var(--accent); }
  .event-type.wave { color: var(--yellow); }
  .event-type.agent { color: var(--green); }
  .event-type.phase { color: var(--muted); }
  .event-type.failed { color: var(--red); }
  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--red); margin-right: 6px; }
  .live-dot.connected { background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
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
  <div class="tab" data-tab="live" onclick="switchTab('live')">Live</div>
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

<div id="tab-live" class="hidden">
  <div style="margin-bottom:12px">
    <span class="live-dot" id="live-dot"></span>
    <span id="live-status" style="font-size:13px;color:var(--muted)">Disconnected</span>
  </div>
  <div class="live-header" id="live-header">
    <div class="metric"><span class="metric-value" id="lm-agents">0</span><br><span class="metric-label">Active Agents</span></div>
    <div class="metric"><span class="metric-value" id="lm-waves">0</span><br><span class="metric-label">Current Wave</span></div>
    <div class="metric"><span class="metric-value" id="lm-completed">0</span><br><span class="metric-label">Completed</span></div>
    <div class="metric"><span class="metric-value" id="lm-failed">0</span><br><span class="metric-label">Failed</span></div>
  </div>
  <h2>Agent Progress</h2>
  <table id="live-agents-table">
    <thead><tr><th>Agent</th><th>Phase</th><th>Status</th></tr></thead>
    <tbody id="live-agents-body"></tbody>
  </table>
  <div class="empty" id="live-agents-empty">No agents running.</div>
  <h2>Event Feed</h2>
  <div class="event-feed" id="event-feed"></div>
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
  ['runs','agents','reviews','improvements','live'].forEach(id => {
    document.getElementById('tab-' + id).classList.toggle('hidden', id !== name);
  });
  hideDetail();
  if (name === 'runs') loadRuns();
  if (name === 'agents') loadAgents();
  if (name === 'reviews') loadReviews();
  if (name === 'improvements') loadImprovements();
  if (name === 'live') startSSE();
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
  ['runs','agents','reviews','improvements','live'].forEach(id => document.getElementById('tab-' + id).classList.add('hidden'));
}
function hideDetail() {
  document.getElementById('detail-panel').classList.add('hidden');
  document.querySelector('.tab.active').click();
}

// --- Live SSE ---
let evtSource = null;
const liveAgents = {};  // agent_id -> {phase, status}
let liveStats = {wave: 0, completed: 0, failed: 0};

function startSSE() {
  if (evtSource) return;  // already connected
  evtSource = new EventSource(API + '/events');
  const dot = document.getElementById('live-dot');
  const statusEl = document.getElementById('live-status');

  evtSource.onopen = () => { dot.classList.add('connected'); statusEl.textContent = 'Connected'; };
  evtSource.onerror = () => { dot.classList.remove('connected'); statusEl.textContent = 'Reconnecting...'; };

  evtSource.onmessage = (msg) => {
    try {
      const e = JSON.parse(msg.data);
      handleLiveEvent(e);
    } catch(_) {}
  };
}

function handleLiveEvent(e) {
  // Update stats
  if (e.event_type === 'fleet_start') {
    Object.keys(liveAgents).forEach(k => delete liveAgents[k]);
    liveStats = {wave: 0, completed: 0, failed: 0};
  }
  if (e.event_type === 'wave_start') liveStats.wave = e.wave;
  if (e.event_type === 'agent_start') liveAgents[e.agent_id] = {phase: '-', status: 'running'};
  if (e.event_type === 'phase_start') { if (liveAgents[e.agent_id]) liveAgents[e.agent_id].phase = e.phase; }
  if (e.event_type === 'phase_done') { if (liveAgents[e.agent_id]) liveAgents[e.agent_id].phase = e.phase + ' (' + e.status + ')'; }
  if (e.event_type === 'agent_done') { liveStats.completed++; if (liveAgents[e.agent_id]) liveAgents[e.agent_id].status = 'done'; }
  if (e.event_type === 'agent_failed') { liveStats.failed++; if (liveAgents[e.agent_id]) liveAgents[e.agent_id].status = 'failed'; }

  // Update header metrics
  const activeCount = Object.values(liveAgents).filter(a => a.status === 'running').length;
  document.getElementById('lm-agents').textContent = activeCount;
  document.getElementById('lm-waves').textContent = liveStats.wave;
  document.getElementById('lm-completed').textContent = liveStats.completed;
  document.getElementById('lm-failed').textContent = liveStats.failed;

  // Update agent table
  const tbody = document.getElementById('live-agents-body');
  const emptyEl = document.getElementById('live-agents-empty');
  const ids = Object.keys(liveAgents);
  if (ids.length) {
    emptyEl.classList.add('hidden');
    tbody.innerHTML = ids.map(id => {
      const a = liveAgents[id];
      const badge = a.status === 'done' ? 'badge-green' : a.status === 'failed' ? 'badge-red' : 'badge-yellow';
      return `<tr><td>${id}</td><td>${a.phase}</td><td><span class="badge ${badge}">${a.status}</span></td></tr>`;
    }).join('');
  } else {
    emptyEl.classList.remove('hidden');
    tbody.innerHTML = '';
  }

  // Append to event feed
  const feed = document.getElementById('event-feed');
  const typeClass = e.event_type.startsWith('fleet') ? 'fleet' : e.event_type.startsWith('wave') ? 'wave'
    : e.event_type.includes('failed') ? 'failed' : e.event_type.startsWith('agent') ? 'agent' : 'phase';
  const time = e.timestamp ? e.timestamp.split('T')[1]?.substring(0,8) || '' : '';
  const line = document.createElement('div');
  line.className = 'event-line';
  line.innerHTML = `<span class="event-time">${time}</span><span class="event-type ${typeClass}">${e.event_type}</span>${e.message || ''}`;
  feed.appendChild(line);
  feed.scrollTop = feed.scrollHeight;

  // Cap feed at 200 entries
  while (feed.children.length > 200) feed.removeChild(feed.firstChild);
}

// Init
loadRuns();
</script>
</body>
</html>
"""
