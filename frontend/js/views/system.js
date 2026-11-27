/* Admin / System — health, db + vector counts, camera workers, live log tail, config */

window.Views = window.Views || {};

Views.system = {
  render: async (container) => {
    const isAdmin = getRole() === 'admin';
    const [health, logs, cfg] = await Promise.all([
      api('/api/system/health').catch(() => null),
      isAdmin ? api('/api/system/logs?lines=120').catch(() => ({ lines: [] })) : Promise.resolve({ lines: [] }),
      isAdmin ? api('/api/system/config').catch(() => null) : Promise.resolve(null),
    ]);

    if (!health) {
      container.innerHTML = '<div class="glass-card rounded-2xl p-6 text-xs text-rose-300">Health endpoint unavailable.</div>';
      return;
    }

    const up = health.uptime_seconds || 0;
    const cameraCards = (health.cameras || []).map((c) => `
      <div class="glass-card rounded-2xl p-4">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm font-bold text-white">${esc(c.name)}</div>
            <div class="text-[10px] font-mono text-gray-400">${esc(c.camera_id)} · ${esc(c.type)}</div>
          </div>
          <span class="text-[10px] font-mono ${c.online ? 'text-emerald-300' : 'text-rose-300'}">
            <span class="w-2 h-2 inline-block rounded-full mr-1 ${c.online ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}"></span>${c.online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
        <div class="mt-2 text-[11px] text-gray-500">last frame ${c.last_frame_age == null ? '—' : c.last_frame_age + 's ago'}</div>
      </div>`).join('') || '<div class="glass-card rounded-2xl p-4 text-xs text-gray-500">No cameras configured.</div>';

    const counts = health.counts || {};
    const countCards = [
      ['Personnel', counts.personnel], ['Attendance today', counts.attendance_today],
      ['Productivity logs', counts.productivity], ['Health logs', counts.health_logs],
      ['Incidents', counts.alerts], ['Unresolved', counts.unresolved_alerts], ['Assets', counts.assets],
    ].map(([label, val]) => `
      <div class="glass-card rounded-2xl p-4">
        <div class="text-[10px] font-mono uppercase text-gray-400">${label}</div>
        <div class="text-2xl font-extrabold text-white mt-1 tabular-nums">${val == null ? '—' : val}</div>
      </div>`).join('');

    const vs = health.vector_stats || {};
    container.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div class="glass-card rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-4">Process</h3>
          <div class="space-y-3 text-sm">
            <div class="flex justify-between"><span class="text-gray-400">Version</span><span class="font-mono text-cyan-300">${esc(health.version)}</span></div>
            <div class="flex justify-between"><span class="text-gray-400">Uptime</span><span class="tabular-nums">${fmtSec(up)}</span></div>
            <div class="flex justify-between"><span class="text-gray-400">Reported at</span><span class="font-mono text-[11px] text-gray-300">${fmtDt(health.timestamp)}</span></div>
          </div>
        </div>
        <div class="glass-card rounded-2xl p-5 lg:col-span-2">
          <h3 class="text-sm font-bold text-white mb-4">Stores</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            ${countCards}
            <div class="glass-card rounded-2xl p-4">
              <div class="text-[10px] font-mono uppercase text-gray-400">Vector embeddings</div>
              <div class="text-2xl font-extrabold text-indigo-300 mt-1 tabular-nums">${vs.embeddings ?? '—'}</div>
            </div>
            <div class="glass-card rounded-2xl p-4">
              <div class="text-[10px] font-mono uppercase text-gray-400">Persons indexed</div>
              <div class="text-2xl font-extrabold text-indigo-300 mt-1 tabular-nums">${vs.persons_indexed ?? '—'}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="glass-card rounded-2xl p-5 mb-6">
        <h3 class="text-sm font-bold text-white mb-4">Camera workers</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">${cameraCards}</div>
      </div>

      ${isAdmin ? `
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-card rounded-2xl p-5">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-white">Live log tail</h3>
            <button data-logs class="px-2.5 py-1 rounded-lg bg-ink-700 hover:bg-ink-800 text-[11px] text-gray-200 border border-white/10">Refresh</button>
          </div>
          <div id="log-tail" class="bg-black/40 rounded-xl p-3 h-[320px] overflow-y-auto font-mono text-[10px] leading-relaxed text-gray-400 whitespace-pre-wrap">
            ${(logs.lines || []).map(esc).join('\n') || 'No log entries yet.'}
          </div>
        </div>
        <div class="glass-card rounded-2xl p-5">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-white">Runtime config</h3>
            <button data-config class="px-2.5 py-1 rounded-lg bg-ink-700 hover:bg-ink-800 text-[11px] text-gray-200 border border-white/10">Refresh</button>
          </div>
          <div id="config-view" class="max-h-[320px] overflow-y-auto rounded-xl border border-white/5 divide-y divide-white/5">
            ${cfg ? Object.entries(cfg.config || {}).map(([k, v]) => `
              <div class="flex justify-between gap-4 px-3 py-2 text-xs">
                <span class="font-mono text-gray-400 truncate">${esc(k)}</span>
                <span class="font-mono text-gray-200 text-right break-all">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</span>
              </div>`).join('') : '<div class="px-3 py-6 text-center text-xs text-gray-500">Config unavailable.</div>'}
          </div>
        </div>
      </div>` : '<div class="glass-card rounded-2xl p-5 text-xs text-gray-500">Operator view — system logs and configuration require admin.</div>'}
    `;

    container.querySelector('[data-logs]')?.addEventListener('click', async () => {
      const res = await api('/api/system/logs?lines=120').catch(() => ({ lines: [] }));
      container.querySelector('#log-tail').textContent = (res.lines || []).join('\n') || 'No log entries yet.';
      container.querySelector('#log-tail').scrollTop = container.querySelector('#log-tail').scrollHeight;
    });
    container.querySelector('[data-config]')?.addEventListener('click', async () => {
      const res = await api('/api/system/config').catch(() => null);
      const box = container.querySelector('#config-view');
      if (!res) return;
      const rows = Object.entries(res.config || {}).map(([k, v]) => `
        <div class="flex justify-between gap-4 px-3 py-2 text-xs">
          <span class="font-mono text-gray-400 truncate">${esc(k)}</span>
          <span class="font-mono text-gray-200 text-right break-all">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</span>
        </div>`).join('');
      box.innerHTML = rows || '<div class="px-3 py-6 text-center text-xs text-gray-500">No config keys.</div>';
    });
  },
};