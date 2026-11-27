/* Asset Memory — spatial anti-theft registry, register with visual bbox picker */

window.Views = window.Views || {};

const ASSET_STATES = {
  NORMAL: 'Secure',
  MOVED: 'Moved',
  DISPLACED_MISSING: 'Displaced / Missing',
  THEFT_SUSPECTED: 'THEFT SUSPECTED',
};

Views.assets = {
  render: async (container) => {
    const [assetsRes, personnel, cams] = await Promise.all([
      api('/api/assets/').catch(() => ({ data: [] })),
      api('/api/personnel').catch(() => ({ data: [] })),
      api('/api/stream/cameras').catch(() => ({ cameras: [] })),
    ]);
    const assets = assetsRes.data || [];
    const isAdmin = getRole() === 'admin';
    const people = personnel.data || [];
    const cameras = cams.cameras || [];

    const rows = assets.map((a) => {
      const owner = people.find((p) => p.person_id === a.owner_person_id);
      return `
        <tr class="hover:bg-white/5 transition">
          <td class="px-4 py-2.5"><span class="w-9 h-9 grid place-items-center rounded-xl bg-indigo-500/20 text-indigo-300 text-xs">▣</span></td>
          <td class="px-3 py-2.5 text-sm font-semibold text-white">${esc(a.asset_name)}</td>
          <td class="px-3 py-2.5 text-xs text-gray-300">${esc(owner ? owner.name : (a.owner_person_id || 'Unassigned'))}</td>
          <td class="px-3 py-2.5 font-mono text-[11px] text-gray-400">${esc(a.last_seen_bbox)}</td>
          <td class="px-3 py-2.5 font-mono text-[11px] text-gray-400">${esc(a.camera_id)}</td>
          <td class="px-3 py-2.5 text-[11px] text-gray-400">${fmtDt(a.updated_at)}</td>
          <td class="px-3 py-2.5">${statusBadge(a.status)}</td>
          <td class="px-3 py-2.5 text-right">${isAdmin ? `<button data-del="${esc(a.asset_name)}" class="px-2.5 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 text-[11px]">Delete</button>` : ''}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="glass-card rounded-2xl p-4"><div class="text-[10px] font-mono text-gray-400">TRACKED</div><div class="text-3xl font-extrabold text-cyan-300 mt-1">${assets.length}</div></div>
        <div class="glass-card rounded-2xl p-4"><div class="text-[10px] font-mono text-gray-400">SECURE</div><div class="text-3xl font-extrabold text-emerald-300 mt-1">${assets.filter((a) => a.status === 'NORMAL').length}</div></div>
        <div class="glass-card rounded-2xl p-4"><div class="text-[10px] font-mono text-gray-400">DISPLACED</div><div class="text-3xl font-extrabold text-amber-300 mt-1">${assets.filter((a) => a.status === 'DISPLACED_MISSING' || a.status === 'MOVED').length}</div></div>
        <div class="glass-card rounded-2xl p-4"><div class="text-[10px] font-mono text-gray-400">THEFT</div><div class="text-3xl font-extrabold text-rose-300 mt-1">${assets.filter((a) => a.status === 'THEFT_SUSPECTED').length}</div></div>
      </div>

      ${isAdmin ? `
      <div class="glass-card rounded-2xl p-5 mb-6">
        <h3 class="text-sm font-bold text-white mb-4">Register a protected region</h3>
        <form class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="text-[11px] text-gray-400">Asset name</label>
            <input required name="name" placeholder="e.g. Laptop-T14-01" class="mt-1 w-full px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-sm text-white focus:outline-none focus:border-cyan-400/50" />
          </div>
          <div>
            <label class="text-[11px] text-gray-400">Owner</label>
            <select name="owner" class="mt-1 w-full px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-sm text-gray-200 focus:outline-none">
              <option value="">— unassigned —</option>
              ${people.map((p) => `<option value="${esc(p.person_id)}">${esc(p.name)} (${esc(p.person_id)})</option>`).join('')}
            </select>
          </div>
          <div>
            <label class="text-[11px] text-gray-400">Camera</label>
            <select name="camera" class="mt-1 w-full px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-sm text-gray-200 focus:outline-none">
              ${cam.map((c) => `<option value="${esc(c.camera_id)}">${esc(c.name)}</option>`).join('')}
            </select>
          </div>
          <div>
            <label class="text-[11px] text-gray-400">Region (x1,y1,x2,y2)</label>
            <div class="mt-1 flex items-center gap-2">
              <input name="bbox" readonly placeholder="Click “Draw region”" class="flex-1 px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs font-mono text-cyan-300" />
              <button type="button" data-pick class="px-3 py-2 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-xs text-gray-200">▭ Draw region</button>
            </div>
          </div>
          <div class="md:col-span-2 flex justify-end">
            <button class="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:opacity-90 text-white text-sm font-semibold">Register asset</button>
          </div>
        </form>
      </div>` : ''}

      <div class="glass-card rounded-2xl overflow-hidden">
        <div class="px-4 py-3 border-b border-white/5 flex items-center justify-between">
          <h3 class="text-sm font-bold text-white">Registered assets</h3>
          <span class="text-[10px] font-mono text-gray-500">displacement diff + proximity rules active</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left">
            <thead class="bg-ink-850/80 text-gray-400 font-mono uppercase text-[10px]">
              <tr><th class="p-3"></th><th class="p-3">Asset</th><th class="p-3">Owner</th><th class="p-3">Bounding box</th><th class="p-3">Camera</th><th class="p-3">Updated</th><th class="p-3">Status</th><th class="p-3 text-right">Action</th></tr>
            </thead>
            <tbody class="divide-y divide-white/5">${rows || '<tr><td colspan="8" class="p-6 text-center text-xs text-gray-500">No assets registered — protect laptops, equipment and valuables.</td></tr>'}</tbody>
          </table>
        </div>
      </div>`;

    if (isAdmin) {
      const form = container.querySelector('form');
      const bboxInput = form.bbox;
      if (window.__pendingBBox) {
        bboxInput.value = JSON.stringify(window.__pendingBBox);
        window.__pendingBBox = null;
      }
      form.querySelector('[data-pick]').onclick = () => pickBBox(form.camera.value, (bb) => {
        bboxInput.value = JSON.stringify([+bb[0], +bb[1], +bb[2], +bb[3]]);
      }, form.camera);
      form.camera.onchange = () => { bboxInput.value = ''; };
      form.onsubmit = async (e) => {
        e.preventDefault();
        if (!bboxInput.value) { toast('Draw a region box before registering', 'warning'); return; }
        await api('/api/assets/', {
          method: 'POST',
          body: JSON.stringify({
            asset_name: form.name.value.trim(),
            owner_person_id: form.owner.value || null,
            camera_id: form.camera.value,
            bbox: JSON.parse(bboxInput.value),
          }),
        });
        toast(`Asset ${form.name.value.trim()} registered`, 'info');
        Views.assets.render(container);
      };
    }

    container.querySelector('tbody').addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-del]');
      if (!btn) return;
      if (!window.confirm(`Delete asset ${btn.dataset.del}?`)) return;
      await api(`/api/assets/${encodeURIComponent(btn.dataset.del)}`, { method: 'DELETE' });
      Views.assets.render(container);
    });
  },

  openPicker: (cameraId) => pickBBox(cameraId, (bb) => {
    window.__pendingBBox = bb;
    toast('Region selected — set a name then register', 'info');
    const bboxInput = document.querySelector('[name=bbox]');
    if (bboxInput) bboxInput.value = JSON.stringify(bb);
  }, null),
};

/* Bounding-box picker: draw a rectangle over the camera snapshot. */
function pickBBox(cameraId, onDone, cameraSelect) {
  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/75 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-4 w-full max-w-3xl">
        <div class="flex justify-between items-center mb-3">
          <div class="text-sm font-bold text-white">Draw region — ${esc(cameraId)}</div>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>
        <div class="text-[11px] text-gray-500 mb-3">Click and drag over the backdrop to protect that area. The coordinates map to the source frame.</div>
        <div class="bg-black rounded-xl overflow-hidden relative aspect-video">
          <img data-zoom src="/api/stream/snapshot?camera_id=${cameraId}" class="w-full h-full object-contain" />
          <canvas data-canvas class="absolute inset-0 w-full h-full cursor-crosshair"></canvas>
        </div>
        <div class="mt-3 flex items-center justify-between gap-3">
          <div class="font-mono text-[11px] text-cyan-300" data-readout></div>
          <button data-done disabled class="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 text-white text-xs font-semibold disabled:opacity-40">Confirm region</button>
        </div>
      </div>
    </div>`);

  const canvas = overlay.querySelector('[data-canvas]');
  const img = overlay.querySelector('[data-zoom]');
  const readout = overlay.querySelector('[data-readout]');
  const done = overlay.querySelector('[data-done]');
  const ctx = canvas.getContext('2d');

  let start = null, sel = null;

  function fitCanvas() {
    const cs = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = cs.width * dpr;
    canvas.height = cs.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  img.onload = () => {
    const nw = img.naturalWidth || 640;
    const nh = img.naturalHeight || 480;
    const cs = canvas.getBoundingClientRect();
    const scale = Math.min(cs.width / nw, cs.height / nh);
    const cw = nw * scale, ch = nh * scale;
    const ox = (cs.width - cw) / 2, oy = (cs.height - ch) / 2;
    canvas._map = (clientX, clientY) => {
      const x = (clientX - cs.left - ox) / scale;
      const y = (clientY - cs.top - oy) / scale;
      return [Math.max(0, Math.min(nw, x)), Math.max(0, Math.min(nh, y))];
    };
    canvas._toStage = (framePt) => [ox + framePt[0] * scale, oy + framePt[1] * scale];
    fitCanvas();
  };
  window.addEventListener('resize', fitCanvas);

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!sel) return;
    const [sx, sy] = canvas._toStage([sel[0], sel[1]]);
    const [ex, ey] = canvas._toStage([sel[2], sel[3]]);
    ctx.fillStyle = 'rgba(34,211,238,0.18)';
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 2;
    ctx.strokeRect(sx, sy, ex - sx, ey - sy);
    ctx.fillRect(sx, sy, ex - sx, ey - sy);
  }

  canvas.addEventListener('pointerdown', (e) => {
    if (!canvas._map) return;
    start = canvas._map(e.clientX, e.clientY);
    done.disabled = true;
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!start || !canvas._map) return;
    const p = canvas._map(e.clientX, e.clientY);
    sel = [Math.min(start[0], p[0]), Math.min(start[1], p[1]), Math.max(start[0], p[0]), Math.max(start[1], p[1])];
    draw();
    readout.textContent = `[${Math.round(sel[0])}, ${Math.round(sel[1])}, ${Math.round(sel[2])}, ${Math.round(sel[3])}]`;
  });
  window.addEventListener('pointerup', () => {
    if (start && sel) done.disabled = false;
    start = null;
  });

  done.onclick = () => {
    if (!sel) return;
    onDone([Math.round(sel[0]), Math.round(sel[1]), Math.round(sel[2]), Math.round(sel[3])]);
    overlay.remove();
  };
  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);
}