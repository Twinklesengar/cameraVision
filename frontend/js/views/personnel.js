/* Personnel — roster table, enrollment (photo upload), search, delete (admin) */

window.Views = window.Views || {};

Views.personnel = {
  render: async (container) => {
    const isAdmin = getRole() === 'admin';
    const response = await api('/api/personnel');
    const people = response.data || [];

    function renderRows() {
      const q = (container.querySelector('[data-filter]')?.value || '').toLowerCase();
      const tbody = container.querySelector('#personnel-tbody');
      const filtered = people.filter((p) =>
        (p.person_id || '').toLowerCase().includes(q) || (p.name || '').toLowerCase().includes(q));
      tbody.innerHTML = filtered.length ? filtered.map((p) => `
        <tr class="hover:bg-white/5 transition">
          <td class="px-4 py-3">
            <span class="w-9 h-9 rounded-full grid place-items-center text-sm font-bold bg-indigo-500/25 text-indigo-200 border border-indigo-500/30">
              ${esc((p.name || '?')[0].toUpperCase())}
            </span>
          </td>
          <td class="px-3 py-3">
            <div class="text-sm font-semibold text-white">${esc(p.name)}</div>
            <div class="text-[10px] font-mono text-cyan-300">${esc(p.person_id)}</div>
          </td>
          <td class="px-3 py-3 text-xs text-gray-300">${esc(p.role)}</td>
          <td class="px-3 py-3 text-xs text-gray-400">${esc(p.department)}</td>
          <td class="px-3 py-3 text-xs text-gray-400 max-w-[220px] truncate">${esc(p.email)}</td>
          <td class="px-3 py-3 font-mono text-[11px] text-gray-500">${fmtDt(p.enrolled_at)}</td>
          <td class="px-3 py-3">${p.is_active ? '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">ACTIVE</span>' : '<span class="px-2 py-0.5 rounded-md text-[10px] font-bold bg-gray-500/15 text-gray-300 border border-gray-500/40">INACTIVE</span>'}</td>
          <td class="px-3 py-3 text-right">
            ${isAdmin ? `<button data-del="${esc(p.person_id)}" class="px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-[11px]">Delete</button>` : ''}
          </td>
        </tr>`).join('')
        : '<tr><td colspan="8" class="p-6 text-center text-xs text-gray-500">No personnel matched</td></tr>';
      container.querySelector('#personnel-count').textContent = filtered.length;
    }

    container.innerHTML = `
      <div class="glass-card rounded-2xl p-4 mb-5">
        <div class="flex flex-wrap items-center gap-3">
          <div class="text-sm font-bold text-white mr-auto">Roster <span id="personnel-count" class="text-cyan-300 font-mono">${people.length}</span></div>
          <input data-filter placeholder="Search by ID or name…" class="px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs text-white placeholder-gray-500 focus:outline-none" />
          ${isAdmin ? `<button data-enroll class="px-3 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:opacity-90 text-xs text-white font-semibold">＋ Enroll personnel</button>` : ''}
        </div>
      </div>

      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="p-3"></th><th class="p-3">Person</th><th class="p-3">Role</th><th class="p-3">Department</th><th class="p-3">Email</th><th class="p-3">Enrolled</th><th class="p-3">Status</th><th class="p-3 text-right">Action</th></tr>
            </thead>
            <tbody id="personnel-tbody" class="divide-y divide-white/5"></tbody>
          </table>
        </div>
      </div>`;

    renderRows();
    container.querySelector('[data-filter]').oninput = renderRows;
    container.querySelector('[data-enroll]')?.addEventListener('click', () => enrollModal(container));
    container.querySelector('#personnel-tbody').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-del]');
      if (!btn) return;
      if (!window.confirm(`Delete ${btn.dataset.del}? This removes embeddings and logs.`)) return;
      try {
        await api(`/api/personnel/${encodeURIComponent(btn.dataset.del)}`, { method: 'DELETE' });
        toast(`Deleted ${btn.dataset.del}`, 'info');
        Views.personnel.render(container);
      } catch (err) {
        toast(err.message, 'critical');
      }
    });
  },
};

function enrollModal(container) {
  const modal = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-6 w-full max-w-xl">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">Enroll personnel</h3>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>
        <form id="enroll-form" class="space-y-4">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="text-[11px] text-gray-400">Person ID *</label>
              <input required name="person_id" placeholder="e.g. ID-1001" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none focus:border-cyan-400/50" />
            </div>
            <div>
              <label class="text-[11px] text-gray-400">Full name *</label>
              <input required name="name" placeholder="e.g. Sandeep Kumar" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none focus:border-cyan-400/50" />
            </div>
            <div>
              <label class="text-[11px] text-gray-400">Role</label>
              <input name="role" value="Employee" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none" />
            </div>
            <div>
              <label class="text-[11px] text-gray-400">Department</label>
              <input name="department" value="General" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none" />
            </div>
            <div>
              <label class="text-[11px] text-gray-400">Email</label>
              <input name="email" type="email" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none" />
            </div>
            <div>
              <label class="text-[11px] text-gray-400">Phone</label>
              <input name="phone" class="mt-1 w-full px-3 py-2 rounded-xl bg-ink-800 border border-white/10 text-sm text-white focus:outline-none" />
            </div>
            <div class="md:col-span-2">
              <label class="text-[11px] text-gray-400">Photo (JPG/PNG) *</label>
              <input required name="photo" type="file" accept="image/jpeg,image/png" class="mt-1 block w-full text-xs text-gray-300 file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border-0 file:bg-ink-700 file:text-gray-200 file:text-xs file:font-semibold hover:file:bg-ink-800" />
            </div>
          </div>
          <div class="flex justify-end pt-2">
            <button class="px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:opacity-90 text-white text-sm font-semibold">Enroll &amp; index face</button>
          </div>
        </form>
      </div>
    </div>`);

  const form = modal.querySelector('#enroll-form');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    fd.set('person_id', fd.get('person_id').trim());
    fd.set('name', fd.get('name').trim());
    const submitBtn = form.querySelector('button');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Indexing face…';
    try {
      const res = await api('/api/personnel/enroll', { method: 'POST', body: fd });
      toast(res.message || 'Enrolled', 'info');
      modal.remove();
      Views.personnel.render(container);
    } catch (err) {
      toast(err.message, 'critical');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Enroll & index face';
    }
  };
  modal.querySelectorAll('[data-close]').forEach((c) => { c.onclick = () => modal.remove(); });
  document.body.appendChild(modal);
  form.querySelector('[name=name]').focus();
}