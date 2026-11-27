/* Attendance — recent in/out table with per-person daily summary modal */

window.Views = window.Views || {};

Views.attendance = {
  render: async (container) => {
    const [{ data: logs }, personnel] = await Promise.all([
      api('/api/analytics/attendance?limit=120'),
      api('/api/personnel').catch(() => ({ data: [] })),
    ]);
    const byId = {};
    (personnel.data || []).forEach((p) => { byId[p.person_id] = p; });

    const badgelist = {
      ENTRY: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
      EXIT: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
      GATE_PASS: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40',
    };

    const rows = (logs || []).map((l) => {
      const cls = badgelist[l.event_type] || badgelist.GATE_PASS;
      const person = byId[l.person_id];
      return `
        <tr class="hover:bg-white/5 transition-colors cursor-pointer" data-pid="${esc(l.person_id || '')}" data-name="${esc(person ? person.name : l.name || '')}">
          <td class="px-4 py-2.5 font-mono text-xs text-gray-400">${fmtDt(l.timestamp)}</td>
          <td class="px-4 py-2.5">
            <div class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-full bg-indigo-500/30 grid place-items-center text-[10px] font-bold text-indigo-200">${esc((person ? person.name : l.name || '?').slice(0, 1).toUpperCase())}</div>
              <div>
                <div class="text-xs font-semibold text-white">${esc(person ? person.name : l.name)}</div>
                <div class="font-mono text-[10px] text-gray-500">${esc(l.person_id || '—')}</div>
              </div>
            </div>
          </td>
          <td class="px-4 py-2.5"><span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${cls}">${esc(l.event_type)}</span></td>
          <td class="px-4 py-2.5 font-mono text-[11px] text-gray-400">${esc(l.camera_id)}</td>
          <td class="px-4 py-2.5 font-mono text-[11px] text-gray-500">${(l.confidence * 100).toFixed(0)}%</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
        <div>
          <p class="text-xs text-gray-400">Cooldown-throttled gate events (30 s/person). Click any row for that person's daily breakdown.</p>
        </div>
        <input data-filter placeholder="Filter by name / id…" class="w-full sm:w-64 px-3.5 py-2 rounded-xl bg-ink-800 border border-white/10 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-cyan-400/50" />
      </div>
      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="p-3">Time</th><th class="p-3">Person</th><th class="p-3">Event</th><th class="p-3">Camera</th><th class="p-3">Confidence</th></tr>
            </thead>
            <tbody class="divide-y divide-white/5">${rows.length ? rows : `<tr><td colspan="5" class="p-6 text-center text-xs text-gray-500">No gate events logged yet</td></tr>`}</tbody>
          </table>
        </div>
      </div>`;

    if (rows.length) {
      container.querySelector('table tbody').addEventListener('click', (e) => {
        const tr = e.target.closest('tr[data-pid]');
        if (tr && tr.dataset.pid) openDailySummary(tr.dataset.pid, tr.dataset.name);
      });

      const filter = container.querySelector('[data-filter]');
      filter.addEventListener('input', () => {
        const q = filter.value.toLowerCase();
        container.querySelectorAll('tr[data-pid]').forEach((tr) => {
          tr.style.display = tr.dataset.pid.toLowerCase().includes(q) || tr.dataset.name.toLowerCase().includes(q) ? '' : 'none';
        });
      });
    }

  },
};

async function openDailySummary(personId, name) {
  const day = new Date().toISOString().slice(0, 10);
  let d = { active_seconds: 0, idle_seconds: 0, bunk_seconds: 0, phone_seconds: 0, productive_score: 0, entries: 0, exits: 0 };
  try { d = await api(`/api/analytics/person/${encodeURIComponent(personId)}/${day}`); } catch (_) {}

  const bar = (label, secs, color) => `
    <div class="flex items-center gap-2">
      <div class="w-28 text-[11px] text-gray-400">${label}</div>
      <div class="flex-1 h-2.5 rounded-full bg-ink-800 overflow-hidden">
        <div class="h-full rounded-full" style="width:${secs ? Math.min(100, (secs / total) * 100) : 0}%;background:${color}"></div>
      </div>
      <div class="w-20 text-right font-mono text-[11px] text-gray-300">${fmtSec(secs)}</div>
    </div>`;

  const total = Math.max(1, d.active_seconds + d.idle_seconds + d.bunk_seconds + d.phone_seconds);

  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-6 w-full max-w-md">
        <div class="flex justify-between items-start mb-1">
          <div>
            <h3 class="text-lg font-bold text-white">${esc(name || personId)}</h3>
            <div class="font-mono text-[11px] text-cyan-300">${esc(personId)} · ${day}</div>
          </div>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>

        <div class="grid grid-cols-3 gap-2 my-4">
          <div class="rounded-xl bg-ink-850 border border-white/5 p-3 text-center">
            <div class="text-2xl font-extrabold text-emerald-300">${d.entries}</div>
            <div class="text-[10px] text-gray-500">ENTRIES</div>
          </div>
          <div class="rounded-xl bg-ink-850 border border-white/5 p-3 text-center">
            <div class="text-2xl font-extrabold text-sky-300">${d.exits}</div>
            <div class="text-[10px] text-gray-500">EXITS</div>
          </div>
          <div class="rounded-xl bg-ink-850 border border-white/5 p-3 text-center">
            <div class="text-2xl font-extrabold ${d.productive_score >= 0.6 ? 'text-emerald-300' : d.productive_score >= 0.3 ? 'text-amber-300' : 'text-rose-300'}">${(d.productive_score * 100).toFixed(0)}</div>
            <div class="text-[10px] text-gray-500">PRODUCTIVITY</div>
          </div>
        </div>

        <div class="space-y-2.5">
          ${bar('Active', d.active_seconds, '#34d399')}
          ${bar('Idle / lazy', d.idle_seconds, '#fbbf24')}
          ${bar('Bunking', d.bunk_seconds, '#f43f5e')}
          ${bar('Phone', d.phone_seconds, '#f59e0b')}
        </div>
      </div>
    </div>`);
  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);
}