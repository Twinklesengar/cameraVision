/* AegisVision — console shell: router, sidebar, WebSocket, toasts, search, clock */

window.Views = window.Views || {};

const NAV = [
  { key: 'dashboard', label: 'Command Center', sub: 'Live KPIs · occupancy · alerts' },
  { key: 'live', label: 'Live Cameras', sub: 'MJPEG streams · stills' },
  { key: 'incidents', label: 'Incident Feed', sub: 'Severity-ranked lifecycle' },
  { key: 'attendance', label: 'Attendance', sub: 'Gate in/out · daily summary' },
  { key: 'productivity', label: 'Productivity', sub: 'Active / lazy / phone / bunk' },
  { key: 'health', label: 'Health Sentinel', sub: 'Drowsiness · posture · fatigue' },
  { key: 'assets', label: 'Asset Memory', sub: 'Spatial anti-theft registry' },
  { key: 'copilot', label: 'AI Copilot', sub: 'Gemini decision support' },
  { key: 'analytics', label: 'Analytics', sub: 'Hourly time-series' },
  { key: 'personnel', label: 'Personnel', sub: 'Enrollment · roster · deletion', admin: true },
  { key: 'system', label: 'System / Admin', sub: 'Health · logs · config', admin: true },
];

const state = {
  view: 'dashboard',
  ws: null,
  alerts: [],
  timers: [],
};

function toast(message, type = 'info') {
  const colors = {
    info: 'border-cyan-500/40 bg-ink-800',
    warning: 'border-amber-500/50 bg-ink-800',
    critical: 'border-rose-500/60 bg-ink-800',
  };
  const icon = { info: 'ℹ', warning: '⚠', critical: '🚨' }[type] || 'ℹ';
  const node = el(`
    <div class="toast glass-card rounded-xl shadow-xl shadow-black/40 p-3.5 border ${colors[type]} flex gap-3 items-start">
      <span class="text-base leading-none mt-0.5">${icon}</span>
      <div class="min-w-0 flex-1">
        <div class="text-xs text-white font-semibold break-words">${message}</div>
      </div>
      <button class="text-gray-500 hover:text-white text-sm leading-none">✕</button>
    </div>`);
  node.querySelector('button').onclick = () => node.remove();
  document.getElementById('toasts').appendChild(node);
  setTimeout(() => node.remove(), type === 'critical' ? 8000 : 5000);
}

function beepAlert() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    osc.frequency.value = 880;
    osc.connect(ctx.destination);
    osc.start();
    setTimeout(() => { osc.stop(); ctx.close(); }, 180);
  } catch (_) {}
}

function setWSStatus(text) {
  const dot = document.getElementById('ws-dot');
  document.getElementById('ws-status').textContent = text;
  dot.className = 'w-2 h-2 rounded-full ' + (text.includes('live')
    ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400');
}

function refresh() {
  if (Views[state.view] && Views[state.view].render) mountView(state.view);
}

function onWSMessage(msg) {
  if (msg.type === 'ALERT') {
    state.alerts.unshift(msg);
    beepAlert();
    toast(`${msg.severity} ${msg.alert_type}${msg.person_id ? ' · ' + msg.person_id : ''}`, msg.severity === 'CRITICAL' ? 'critical' : 'warning');
    if (state.view === 'incidents' || state.view === 'dashboard') refresh();
  } else if (msg.type === 'ALERT_RESOLVED') {
    if (state.view === 'incidents' || state.view === 'dashboard') refresh();
  }
}

function mountView(key) {
  const view = Views[key];
  const container = document.getElementById('view');
  const title = document.getElementById('view-title');
  const subtitle = document.getElementById('view-subtitle');
  if (!view) {
    container.innerHTML = `<div class="text-center py-10 text-gray-500">Unknown view</div>`;
    return;
  }
  state.view = key;
  document.querySelectorAll('.nav-link').forEach((n) => n.classList.toggle('active', n.dataset.view === key));
  title.textContent = (NAV.find((n) => n.key === key) || { label: 'View' }).label;
  subtitle.textContent = (NAV.find((n) => n.key === key) || {}).sub || '';
  container.innerHTML = '<div class="dots-loading text-gray-500 text-sm">Loading</div>';
  Promise.resolve(view.render(container))
    .catch((err) => {
      container.innerHTML = `<div class="glass-card rounded-2xl p-6 text-sm text-rose-300">Error: ${esc(err.message)}</div>`;
    });
}

function openSearch() {
  document.getElementById('search-overlay').classList.remove('hidden');
  const input = document.getElementById('search-input-overlay');
  input.value = '';
  input.focus();
  runSearch('');
}

async function runSearch(q) {
  const box = document.getElementById('search-results');
  if (!q.trim()) { box.innerHTML = ''; return; }
  q = q.toLowerCase();
  try {
    const [personnel, incidents] = await Promise.all([
      api('/api/personnel').catch(() => ({ data: [] })),
      api('/api/alerts?limit=200').catch(() => ({ data: [] })),
    ]);
    const people = (personnel.data || []).filter((p) =>
      (p.person_id || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q));
    const incs = (incidents.data || []).filter((a) =>
      (a.description || '').toLowerCase().includes(q) || (a.alert_type || '').toLowerCase().includes(q));
    box.innerHTML = '';
    if (!people.length && !incs.length) {
      box.innerHTML = '<div class="px-4 py-4 text-xs text-gray-500">No matches</div>';
      return;
    }
    if (people.length) {
      box.appendChild(el(`<div class="px-4 py-1.5 text-[10px] font-mono uppercase text-cyan-400">Personnel</div>`));
      people.slice(0, 5).forEach((p) => {
        box.appendChild(el(`<div class="px-4 py-2 flex justify-between items-center gap-3 hover:bg-white/5">
          <span><span class="font-semibold text-white">${esc(p.name)}</span>
          <span class="text-gray-400 text-xs ml-2 font-mono">${esc(p.person_id)}</span></span>
          <span class="text-[10px] text-gray-500">${esc(p.role)}</span></div>`));
      });
    }
    if (incs.length) {
      box.appendChild(el(`<div class="px-4 py-1.5 text-[10px] font-mono text-cyan-400">Incidents</div>`));
      incs.slice(0, 5).forEach((a) => {
        box.appendChild(el(`<div class="px-4 py-2 text-sm flex items-center gap-2">${severityBadge(a.severity)}
          <span class="truncate text-gray-300">${esc(a.description)}</span></div>`));
      });
    }
  } catch (_) { box.innerHTML = ''; }
}

function startClock() {
  const el = document.getElementById('clock');
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };
  tick();
  setInterval(tick, 1000);
}

async function boot() {
  if (!getToken()) { window.location.href = '/login.html'; return; }
  try {
    const me = await api('/api/auth/me');
    document.getElementById('user-name').textContent = me.username || 'operator';
    document.getElementById('user-role').textContent = me.role || 'admin';
    document.getElementById('user-avatar').textContent = ((me.username || 'A')[0] || 'A').toUpperCase();
  } catch (_) { window.location.href = '/login.html'; return; }

  const admin = getRole() === 'admin';
  const navEl = document.getElementById('nav');
  for (const item of NAV) {
    const a = el(`
      <a class="nav-item nav-link flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${item.admin && !admin ? 'hidden' : ''}" data-view="${item.key}">
        <span class="nav-icon grid place-items-center w-6">${Icons[item.key] || ''}</span>
        <span class="nav-label">${item.label}</span>
      </a>`);
    a.addEventListener('click', (e) => {
      e.preventDefault();
      location.hash = '#' + item.key;
      if (window.matchMedia('(max-width: 1023px)').matches) {
        document.getElementById('sidebar').classList.add('-translate-x-full');
      }
    });
    navEl.appendChild(a);
  }

  state.ws = connectWS(onWSMessage, setWSStatus);

  document.getElementById('logout-btn').onclick = () => {
    clearToken();
    window.location.href = '/login.html';
  };
  document.getElementById('menu-btn').onclick = () => {
    document.getElementById('sidebar').classList.toggle('-translate-x-full');
  };

  const topSearch = document.getElementById('search-input');
  topSearch.addEventListener('keydown', (e) => { if (e.key === 'Enter' && topSearch.value) openSearch(); });

  document.getElementById('search-backdrop').onclick = () => document.getElementById('search-overlay').classList.add('hidden');
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); openSearch(); }
    if (e.key === 'Escape') document.getElementById('search-overlay').classList.add('hidden');
    const idx = ['1','2','3','4','5','6','7','8','9'];
    if (e.metaKey || e.ctrlKey) {
      const i = idx.indexOf(e.key);
      if (i >= 0 && i < NAV.length) { e.preventDefault(); location.hash = '#' + NAV[i].key; }
    }
  });

  window.addEventListener('hashchange', buildSidebarNav);
  startClock();
  buildSidebarNav();
}

function buildSidebarNav() {
  const key = (location.hash || '#dashboard').slice(1);
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.toggle('active', n.dataset.view === key));
  mountView(key);
}

document.addEventListener('DOMContentLoaded', boot);