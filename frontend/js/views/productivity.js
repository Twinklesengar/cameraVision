/* Productivity — per-person workstation state telemetry */

window.Views = window.Views || {};

const PROD_ORDER = { PRODUCTIVE: 0, LAZY_IDLE: 1, PHONE_DISTRACTED: 2, BUNKING: 3 };

Views.productivity = {
  render: async (container) => {
    const { data: logs } = await api('/api/analytics/productivity?limit=150');
    const { data: personnel } = await api('/api/personnel').catch(() => ({}));
    const byId = {};
    (personnel || []).forEach((p) => { byId[p.person_id] = p; });

    const totals = {};
    (logs || []).forEach((l) => {
      const t = (totals[l.status] = totals[l.status] || { count: 0, seconds: 0 });
      t.count += 1;
      t.seconds += Number(l.duration_seconds || 0);
    });

    const summaryChips = [
      ['Productive', totals.PRODUCTIVE || { count: 0, seconds: 0 }, '#34d399'],
      ['Idle / lazy', totals.LAZY_IDLE || { count: 0, seconds: 0 }, '#fbbf24'],
      ['Phone distracted', totals.PHONE_DISTRACTED || { count: 0, seconds: 0 }, '#f59e0b'],
      ['Bunking', totals.BUNKING || { count: 0, seconds: 0 }, '#f43f5e'],
    ].map(([label, t, color]) => `
      <div class="rounded-xl bg-ink-850 border border-white/5 p-3">
        <div class="flex items-center justify-between">
          <span class="flex items-center gap-1.5 text-[11px] text-gray-400"><span class="w-2 h-2 rounded-full" style="background:${color}"></span>${label}</span>
          <span class="font-mono text-sm font-bold text-white">${fmtSec(t.seconds)}</span>
        </div>
        <div class="text-[10px] text-gray-500 mt-0.5">${t.count} sessions</div>
      </div>`).join('');

    const rows = (logs || []).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 120).map((l) => {
      const p = byId[l.person_id] || {};
      return `
        <tr class="hover:bg-white/5 transition">
          <td class="px-4 py-2.5 font-mono text-xs text-gray-400">${fmtDt(l.timestamp)}</td>
          <td class="px-4 py-2.5 text-xs"><span class="font-semibold text-white">${esc(p.name || l.person_id)}</span> <span class="font-mono text-[10px] text-gray-500">${esc(l.person_id)}</span></td>
          <td class="px-4 py-2.5">${statusBadge(l.status)}</td>
          <td class="px-4 py-2.5 font-mono text-xs text-gray-300">${fmtSec(l.duration_seconds)}</td>
          <td class="px-4 py-2.5 font-mono text-[11px] text-gray-400">${esc(l.camera_id || '—')}</td>
          <td class="px-4 py-2.5 text-[11px] text-gray-400">${esc(l.notes || 'Normal session')}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">${summaryChips}</div>
      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between">
          <h3 class="text-sm font-bold text-white">Recent telemetry</h3>
          <span class="text-[10px] font-mono text-gray-500">${(logs || []).length} records</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="px-3">Time</th><th class="px-3">Person</th><th class="px-3">Status</th><th class="px-3">Duration</th><th class="px-3">Camera</th><th class="px-3">Notes</th></tr>
            </thead>
            <tbody class="divide-y divide-white/5">${rows || '<tr><td colspan="6" class="p-6 text-center text-xs text-gray-500">No productivity telemetry yet</td></tr>'}</tbody>
          </table>
        </div>
      </div>`;
  },
};