/* AegisVision — fetch wrapper + WebSocket helper */

const TOKEN_KEY = 'aegis_token';
const ROLE_KEY = 'aegis_role';

function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }
function setToken(token, role) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role || 'admin');
}
function clearToken() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ROLE_KEY); }
function getRole() { return localStorage.getItem(ROLE_KEY) || ''; }

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (opts.body && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, { ...opts, headers });
  let data = null;
  try { data = await res.json(); } catch (_) { /* non-JSON body */ }

  if (res.status === 401 && path !== '/api/auth/login' && !path.startsWith('/api/stream')) {
    clearToken();
    if (!location.pathname.endsWith('login.html')) window.location.href = '/login.html';
    throw new Error('session-expired');
  }
  if (!res.ok) {
    let detail = (data && (data.detail || data.message)) || `HTTP ${res.status}`;
    if (typeof detail === 'object' && detail.msg) detail = detail.msg;
    throw new Error(detail);
  }
  return data;
}

/* WebSocket to /api/stream/ws with reconnect + heartbeat. onMessage(data), onStatus(text). */
function connectWS(onMessage, onStatus) {
  let ws = null;
  let closed = false;
  let retry = 0;

  function schedule() {
    if (closed) return;
    const delay = Math.min(5000, 800 * Math.pow(1.8, retry++));
    setTimeout(open, delay);
    if (onStatus) onStatus('connecting');
  }

  function open() {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    try {
      ws = new WebSocket(`${scheme}://${window.location.host}/api/stream/ws`);
    } catch (_) { return schedule(); }

    ws.onopen = () => { retry = 0; if (onStatus) onStatus('live'); };
    ws.onmessage = (ev) => { try { onMessage(JSON.parse(ev.data)); } catch (_) {} };
    ws.onclose = () => { ws = null; if (onStatus) onStatus('connecting'); if (!closed) schedule(); };
    ws.onerror = () => { try { ws.close(); } catch (_) {} };
  }

  open();
  return {
    close() { closed = true; if (ws) ws.close(); },
  };
}

const Icons = {
  dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M3 13h8V3H3v10zM13 21h8V11h-8v10zM13 3v6h8V3h-8zM3 19h8v-2H3v2z"/></svg>',
  live: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M15 10l5-3v10l-5-3"/><rect x="3" y="6" width="12" height="12" rx="2"/></svg>',
  attendance: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/><path d="M9 16l2 2 4-4"/></svg>',
  productivity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  health: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  assets: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><rect x="3" y="8" width="18" height="12" rx="2"/><path d="M7 8V6a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2"/><path d="M12 12v4M10 14h4"/></svg>',
  incidents: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
  copilot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>',
  analytics: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>',
  personnel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  system: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-5 h-5"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/></svg>',
};

/* Small UI helpers */
function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function fmtDt(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function fmtSec(s) {
  s = Number(s || 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function severityBadge(sev) {
  const map = {
    CRITICAL: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
    WARNING: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    INFO: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  };
  return `<span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${map[sev.toUpperCase()] || map.INFO}">${esc(sev.toUpperCase())}</span>`;
}

function statusBadge(status) {
  const map = {
    NORMAL: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    DISPLACED_MISSING: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    MOVED: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    THEFT_SUSPECTED: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
    PRODUCTIVE: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    LAZY_IDLE: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    BUNKING: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
    PHONE_DISTRACTED: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
    GOOD: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
    SLOUCHING: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
    FALL_RISK: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  };
  const cls = map[String(status).toUpperCase()] || 'bg-gray-500/15 text-gray-300 border-gray-500/40';
  return `<span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${cls}">${esc(status)}</span>`;
}