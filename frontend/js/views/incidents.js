/* Incident Feed — severity lifecycle, filters, resolve (admin) */

window.Views = window.Views || {};

Views.incidents = {
  render: async (container) => {
    const [alerts, types, personnel] = await Promise.all([
      api('/api/alerts?limit=200').catch(() => ({ data: [] })),
      api('/api/alerts/types').catch(() => ({ data: [] })),
      api('/api/personnel').catch(() => ({ data: [] })),
    ]);
    const byId = {};
    (personnel.data || []).forEach((p) => { byId[p.person_id] = p; });
    const typeOpts = (types.data || []).map((t) => `<option value="${esc(t.alert_type)}">${esc(t.alert_type)}</option>`).join('');
    const isAdmin = getRole() === 'admin';

    const list = (alerts.data || []).slice(0, 100);

    function renderRows() {
      const q = (container.querySelector('[data-filter]')?.value || '').toLowerCase();
      const type = container.querySelector('[data-type]')?.value || 'all';
      const showResolved = container.querySelector('[data-resolved]')?.checked || false;
      const filtered = list.filter((a) => {
        if (type !== 'all' && a.alert_type !== type) return false;
        if (!showResolved && a.is_resolved) return false;
        if (q && !(a.description || '').toLowerCase().includes(q) && !(a.alert_type || '').toLowerCase().includes(q)) return false;
        return true;
      });
      const tbody = container.querySelector('#incident-tbody');
      tbody.innerHTML = filtered.length ? filtered.map((a) => {
        const person = a.person_id ? byId[a.person_id] : null;
        const sevW = { CRITICAL: 3, WARNING: 2, INFO: 1 };
        return `
          <tr class="hover:bg-white/5 transition ${a.is_resolved ? 'opacity-50' : ''}">
            <td class="px-4 py-3"><span class="inline-flex w-1.5 h-6 rounded-full ${a.severity === 'CRITICAL' ? 'bg-rose-500' : a.severity === 'WARNING' ? 'bg-amber-500' : 'bg-sky-500'}"></span></td>
            <td class="px-3 py-3"><span class="font-mono text-[10px] text-gray-400">#${a.id}</span></td>
            <td class="px-3 py-3 font-mono text-[11px] text-gray-400">${fmtDt(a.timestamp)}</td>
            <td class="px-3 py-3">${severityBadge(a.severity)}</td>
            <td class="px-3 py-3"><span class="px-2 py-0.5 rounded-md text-[10px] font-mono bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">${esc(a.alert_type)}</span></td>
            <td class="px-3 py-3 text-xs text-gray-300 max-w-[380px]"><span class="line-clamp-2">${esc(a.description)}</span></td>
            <td class="px-3 py-3 text-xs">
              ${a.person_id ? `<span class="text-cyan-300 font-mono text-[11px]">${esc(a.person_id)}</span>` : '<span class="text-gray-500">—</span>'}
              ${person ? `<span class="text-gray-400">· ${esc(person.name)}</span>` : ''}
            </td>
            <td class="px-3 py-3 text-[11px] font-mono text-gray-500">${esc(a.camera_id || '—')}</td>
            <td class="px-3 py-3 text-right">
              ${a.is_resolved
                ? '<span class="text-[11px] text-emerald-300">✓ resolved</span>'
                : isAdmin
                  ? `<button data-resolve="${a.id}" class="px-2.5 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 text-[11px] font-semibold">Resolve</button>`
                  : '<span class="text-[11px] text-gray-500">—</span>'}
            </td>
          </tr>`;
      }).join('')
      : '<tr><td colspan="9" class="p-6 text-center text-xs text-gray-500">No incidents match</td></tr>';
      container.querySelector('#incident-count').textContent = filtered.length;
    }

    container.innerHTML = `
      <div class="glass-card rounded-2xl p-4 mb-5">
        <div class="flex flex-wrap items-center gap-3">
          <div class="text-sm font-bold text-white mr-auto">Incidents <span id="incident-count" class="text-cyan-300 font-mono">${list.length}</span></div>
          <input data-filter placeholder="Search…" class="px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs text-white placeholder-gray-500 focus:outline-none" />
          <select data-type class="px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200 focus:outline-none">
            <option value="all">All types</option>${typeOpts}
          </select>
          <label class="flex items-center gap-2 text-xs text-gray-300">
            <input data-resolved type="checkbox" class="rounded bg-ink-800" /> include resolved
          </label>
        </div>
      </div>
      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="p-3 w-2"></th><th class="p-3">ID</th><th class="p-3">Time</th><th class="p-3">Severity</th><th class="p-3">Type</th><th class="p-3">Description</th><th class="p-3">Person</th><th class="p-3">Camera</th><th class="p-3 text-right">Action</th></tr>
            </thead>
            <tbody id="incident-tbody" class="divide-y divide-white/5"></tbody>
          </table>
        </div>
      </div>`;

    renderRows();
    container.querySelector('[data-filter]').oninput = renderRows;
    container.querySelector('[data-type]').onchange = renderRows;
    container.querySelector('[data-resolved]').onchange = renderRows;
    container.querySelector('#incident-tbody').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-resolve]');
      if (!btn) return;
      await api(`/api/alerts/resolve/${btn.dataset.resolve}`, { method: 'POST' });
      Views.incidents.render(container);
    });
  },
};