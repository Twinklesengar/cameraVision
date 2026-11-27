/* Health Sentinel — drowsiness / posture / fatigue telemetry */

window.Views = window.Views || {};

Views.health = {
  render: async (container) => {
    const { data: logs } = await api('/api/analytics/health?limit=150');
    const { data: personnel } = await api('/api/personnel').catch(() => ({}));
    const byId = {};
    (personnel || []).forEach((p) => { byId[p.person_id] = p; });

    const drowsyCount = (logs || []).filter((l) => l.drowsiness_detected).length;
    const riskyPosture = (logs || []).filter((l) => (l.posture_status || 'GOOD') !== 'GOOD').length;

    const stat = (label, value, accent, sub) => `
      <div class="glass-card rounded-2xl p-4">
        <div class="text-[10px] font-mono uppercase text-gray-400">${label}</div>
        <div class="text-3xl font-extrabold ${accent} mt-1">${value}</div>
        <div class="text-[11px] text-gray-500 mt-0.5">${sub}</div>
      </div>`;

    const rows = (logs || []).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).map((l) => {
      const p = byId[l.person_id] || {};
      return `
        <tr class="hover:bg-white/5 transition">
          <td class="px-4 py-2.5 font-mono text-xs text-gray-400">${fmtDt(l.timestamp)}</td>
          <td class="px-4 py-2.5 text-xs"><span class="font-semibold text-white">${esc(p.name || l.person_id)}</span> <span class="font-mono text-[10px] text-gray-500">${esc(l.person_id)}</span></td>
          <td class="px-4 py-2.5 font-mono text-xs text-gray-300">${l.eye_aspect_ratio != null ? l.eye_aspect_ratio.toFixed(2) : '—'}</td>
          <td class="px-4 py-2.5 font-mono text-xs text-purple-300">${Math.round((l.fatigue_score || 0) * 100)}%</td>
          <td class="px-4 py-2.5">${statusBadge(l.posture_status)}</td>
          <td class="px-4 py-2.5">${l.drowsiness_detected
            ? '<span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold">⚠ DROWSINESS</span>'
            : '<span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold">Normal alertness</span>'}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        ${stats('Monitored', (logs || []).length, 'text-white', 'health records in window')}
        ${stats('Drowsiness flags', drowsyCount, 'text-rose-300', 'EAR-based detections')}
        ${stats('Posture risk', riskyPosture, 'text-amber-300', 'slouching / fall-risk')}
      </div>
      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="px-4 py-3 border-b border-white/5">
          <h3 class="text-sm font-bold text-white">Health sentinel telemetry</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="px-3">Time</th><th class="px-3">Person</th><th class="px-3">EAR</th><th class="px-3">Fatigue</th><th class="px-3">Posture</th><th class="px-3">Drowsiness</th></tr>
            </thead>
            <tbody class="divide-y divide-white/5">${rows || '<tr><td colspan="6" class="p-6 text-center text-xs text-gray-500">No health telemetry yet</td></tr>'}</tbody>
          </table>
        </div>
      </div>`;
  },
};