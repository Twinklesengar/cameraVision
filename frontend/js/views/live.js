/* Live Cameras — MJPEG grid, scene awareness, snapshot; admin fleet management */

window.Views = window.Views || {};

const SCENE_STYLE = {
  IDLE: 'bg-sky-500/15 text-sky-300 border-sky-500/40',
  ACTIVE: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40',
  BUSY: 'bg-amber-500/15 text-amber-300 border-amber-500/40',
  CROWDED: 'bg-rose-500/15 text-rose-300 border-rose-500/40',
  OFFLINE: 'bg-gray-600/20 text-gray-400 border-gray-500/40',
};

function sceneBadge(state) {
  state = state || 'OFFLINE';
  const cls = SCENE_STYLE[state] || SCENE_STYLE.IDLE;
  return `<span data-camera-scene class="px-2 py-0.5 rounded-md text-[9px] font-bold border font-mono ${cls}">${esc(state)}</span>`;
}

function motionMeter(score) {
  const v = Math.max(0, Math.min(100, Number(score) || 0));
  const color = v < 12 ? 'bg-sky-500' : v < 35 ? 'bg-cyan-400' : v < 70 ? 'bg-amber-400' : 'bg-rose-500';
  return `
    <div class="mt-2">
      <div class="flex justify-between text-[9px] font-mono text-gray-500 mb-1">
        <span>MOTION</span><span>${v.toFixed(0)}%</span>
      </div>
      <div class="h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div class="h-full rounded-full ${color} transition-all" style="width:${v}%"></div>
      </div>
    </div>`;
}

function motionSparkline(history) {
  if (!history || !history.length) return '';
  const W = 220, H = 26, P = 2;
  const vals = history.map((h) => Math.max(0, Math.min(100, Number(h.motion_score) || 0)));
  const maxV = Math.max(1, ...vals);
  const step = vals.length > 1 ? (W - P * 2) / (vals.length - 1) : 0;
  const pts = vals.map((v, i) => {
    const x = P + step * i;
    const y = H - P - (v / maxV) * (H - P * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const heat = Math.max(0, ...vals) < 12 ? 'stroke-sky-400' : Math.max(1, ...vals) < 35 ? 'stroke-cyan-400' : Math.max(0, ...vals) < 70 ? 'stroke-amber-400' : 'stroke-rose-400';
  return `
    <div class="mt-2">
      <div class="text-[9px] font-mono text-gray-500 mb-1">LAST ${vals.length}s ACTIVITY</div>
      <svg viewBox="0 0 ${W} ${H}" class="w-full h-8 rounded-lg bg-white/5">
        <polyline fill="none" stroke-width="1.6" class="${heat}" points="${pts}" />
      </svg>
    </div>`;
}

function fleetStat(label, value, sub, key) {
  return `
    <div data-fleet-stat="${esc(key)}" class="glass-card rounded-2xl px-4 py-3 border border-white/5">
      <div class="text-[9px] font-mono text-gray-500 mb-1">${label}</div>
      <div data-value class="text-xl font-extrabold text-white tabular-nums leading-tight">${esc(String(value))}</div>
      <div data-sub class="text-[10px] font-mono text-gray-500 mt-0.5">${esc(sub)}</div>
    </div>`;
}

function cameraState(cam) {
  if (!cam.active) return 'DISABLED';
  if (cam.online) return 'ONLINE';
  return cam.last_error === 'Waiting for the first frame' ? 'CONNECTING' : 'OFFLINE';
}

function cameraHealthText(cam) {
  if (!cam.active) return cam.last_error || 'Camera is disabled';
  if (cam.online) {
    const age = cam.last_frame_age == null ? null : Number(cam.last_frame_age);
    return `Receiving frames${age == null || !Number.isFinite(age) ? '' : ` · updated ${age.toFixed(1)}s ago`}`;
  }
  if (cam.last_error) return cam.last_error;
  if (cam.offline_since != null) return `No frames for ${fmtSec(cam.offline_since)}`;
  return 'Waiting for the first frame';
}

Views.live = {
  render: async (container) => {
    const isAdmin = getRole() === 'admin';
    const [{ cameras }, fleet, monitoring] = await Promise.all([
      api('/api/stream/cameras'),
      api('/api/stream/fleet/summary').catch(() => null),
      api('/api/stream/monitoring'),
    ]);
    const monitoringRunning = Boolean(monitoring.running);
    const fs = fleet || { total: cameras.length, online: cameras.filter((c) => c.online).length, active_cameras: cameras.length, busy: 0, analysis_budget_available: 0, analysis_queue: 0 };
    container.innerHTML = `
      <div data-live-root>
      <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div>
          <p class="text-sm font-semibold text-white">Campus camera feeds</p>
          <p class="text-xs text-gray-400 mt-1">Monitoring stays stopped on startup. Start it here when you are ready; status refreshes automatically.</p>
        </div>
        <div class="flex gap-2">
          ${isAdmin ? `<button data-action="monitoring" data-running="${monitoringRunning}" class="px-3 py-1.5 rounded-lg ${monitoringRunning ? 'bg-rose-500/15 text-rose-300 border-rose-500/30' : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'} text-xs border"> ${monitoringRunning ? 'Stop monitoring' : 'Start monitoring'}</button>` : ''}
          ${isAdmin ? `<button data-action="manage" class="px-3 py-1.5 rounded-lg bg-ink-700 hover:bg-ink-800 text-xs text-gray-200 border border-white/10">Manage fleet</button>` : ''}
          <span data-camera-refresh-status role="status" class="text-[10px] font-mono text-gray-500"></span>
          <button data-action="refresh" class="px-3 py-1.5 rounded-lg bg-ink-700 hover:bg-ink-800 text-xs text-gray-200 border border-white/10">Check status</button>
        </div>
      </div>

      <details class="glass-card rounded-xl border border-white/5 px-4 py-3 mb-5">
        <summary class="cursor-pointer text-xs font-semibold text-cyan-300">Camera setup & troubleshooting</summary>
        <div class="mt-3 grid gap-2 text-xs text-gray-400 md:grid-cols-2">
          <p>USB webcam source: <code class="text-gray-200">0</code>. IP camera: use its RTSP/HTTP stream URL.</p>
          <p>For a local webcam, check Windows camera privacy permission and close other apps using it before starting monitoring.</p>
          <p>Read each camera's status under its preview for the latest connection error. API status: <code class="text-gray-200">/api/stream/cameras</code>.</p>
          <p>Direct feed: <code class="text-gray-200">/api/stream/video_feed?camera_id=&lt;camera-id&gt;</code>.</p>
        </div>
      </details>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        ${fleetStat('FLEET', `${fs.online}/${fs.total}`, 'online · active', 'fleet')}
        ${fleetStat('BUSY CAMS', fs.busy, 'scene load', 'busy')}
        ${fleetStat('ANALYSIS BUDGET', `${Number(fs.analysis_budget_available || 0).toFixed(1)}/s`, `${fs.analysis_queue || 0} queued`, 'budget') }
        <div class="glass-card rounded-2xl px-4 py-3 flex items-center gap-4 overflow-hidden border border-white/5">
          <div class="min-w-0">
            <div class="text-[9px] font-mono text-gray-500 mb-0.5">FLEET BAR</div>
            <div class="h-2 rounded-full bg-white/5 overflow-hidden w-36">
              <div data-fleet-bar class="h-full rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500 transition-all" style="width:${Math.min(100, fs.total ? (fs.online / fs.total) * 100 : 0)}%"></div>
            </div>
          </div>
          <span data-fleet-count class="text-[10px] font-mono text-cyan-300">${fs.online}/${fs.total}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        ${cameras.length ? cameras.map((cam) => `
          <div data-camera-card="${esc(cam.camera_id)}" class="glass-card rounded-2xl overflow-hidden">
            <div class="flex items-center justify-between px-4 py-3 border-b border-white/5">
              <div>
                <div class="text-sm font-bold text-white">${esc(cam.name)}</div>
                <div class="text-[10px] font-mono text-gray-400">${esc(cam.camera_id)} · ${esc(cam.type)} · ${esc(cam.source)}</div>
              </div>
              <span data-camera-status class="flex items-center gap-1.5 text-[10px] font-mono ${cameraState(cam) === 'ONLINE' ? 'text-emerald-300' : cameraState(cam) === 'CONNECTING' ? 'text-amber-300' : 'text-rose-300'}">
                <span data-status-dot class="w-2 h-2 rounded-full ${cameraState(cam) === 'ONLINE' ? 'bg-emerald-400 animate-pulse' : cameraState(cam) === 'CONNECTING' ? 'bg-amber-400 animate-pulse' : 'bg-rose-500'}"></span>
                ${cameraState(cam)}
              </span>
            </div>
            <div class="relative bg-black aspect-video">
              <img src="/api/stream/video_feed?camera_id=${encodeURIComponent(cam.camera_id)}" class="absolute inset-0 w-full h-full object-contain" alt="Live stream: ${esc(cam.name)}" loading="lazy" />
              <div class="absolute top-2.5 left-2.5 flex items-center gap-2">
                <span class="text-[10px] font-mono text-cyan-300 bg-black/60 rounded-md px-2 py-1 border border-white/10">● FEED</span>
                ${sceneBadge(cam.scene_state)}
              </div>
              <div data-camera-metrics class="absolute bottom-2.5 right-2.5 text-[10px] font-mono bg-black/70 rounded-md px-2 py-1 border border-white/10 text-gray-300">
                ${cam.people_seen ?? 0} persons · ${cam.captured_per_analysis ?? 0} frames/analyse · ${cam.analysis_latency_ms ?? 0}ms
              </div>
            </div>
            <div class="px-4 py-3">
              <p data-camera-health role="status" aria-live="polite" class="min-h-8 text-[11px] font-mono ${cam.online ? 'text-emerald-300' : 'text-rose-300'}">${esc(cameraHealthText(cam))}</p>
              <div data-camera-motion>
              ${cam.online ? motionMeter(cam.motion_score) : '<div class="mt-2 h-1.5 rounded-full bg-white/5"></div>'}
              ${motionSparkline(cam.history)}
              </div>
              <div class="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3">
                <button data-snap="${esc(cam.camera_id)}" class="py-2 rounded-lg bg-ink-800 hover:bg-ink-700 border border-white/10 text-xs text-gray-200">Snapshot</button>
                <button data-detail="${esc(cam.camera_id)}" class="py-2 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-xs text-cyan-300">Activity</button>
                <button data-clips="${esc(cam.camera_id)}" class="py-2 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-xs text-amber-300">Clips</button>
                <button data-bbox="${esc(cam.camera_id)}" class="py-2 rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-600 hover:opacity-90 text-xs text-white font-semibold">Region</button>
                ${isAdmin ? `<button data-restart-camera="${esc(cam.camera_id)}" class="col-span-2 md:col-span-5 py-2 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-xs text-gray-200">Restart camera</button>` : ''}
              </div>
            </div>
          </div>`).join('') : `
          <div class="glass-card rounded-2xl p-8 text-center md:col-span-2 xl:col-span-3">
            <h2 class="text-sm font-semibold text-white">No cameras configured</h2>
            <p class="mt-2 text-xs text-gray-400">Add a webcam index or RTSP/HTTP camera source to start a feed.</p>
            ${isAdmin ? `<button data-action="manage" class="mt-4 px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs text-white">Set up a camera</button>` : ''}
          </div>`}
        </div>
      </div>`;

    let refreshing = false;
    const updateStat = (key, value, sub) => {
      const card = container.querySelector(`[data-fleet-stat="${key}"]`);
      if (!card) return;
      card.querySelector('[data-value]').textContent = String(value);
      card.querySelector('[data-sub]').textContent = String(sub);
    };
    const updateMonitoringControl = (status) => {
      const button = container.querySelector('[data-action=monitoring]');
      if (!button) return;
      const running = Boolean(status.running);
      button.dataset.running = String(running);
      button.textContent = running ? 'Stop monitoring' : 'Start monitoring';
      button.className = `px-3 py-1.5 rounded-lg ${running ? 'bg-rose-500/15 text-rose-300 border-rose-500/30' : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'} text-xs border`;
    };
    const refreshStatus = async () => {
      if (refreshing || !container.querySelector('[data-live-root]')) return;
      refreshing = true;
      try {
        const [{ cameras: latest }, currentFleet, currentMonitoring] = await Promise.all([
          api('/api/stream/cameras'),
          api('/api/stream/fleet/summary').catch(() => null),
          api('/api/stream/monitoring'),
        ]);
        if (!container.querySelector('[data-live-root]')) return;
        const cards = new Map([...container.querySelectorAll('[data-camera-card]')].map((card) => [card.dataset.cameraCard, card]));
        for (const cam of latest) {
          const card = cards.get(cam.camera_id);
          if (!card) continue;
          const state = cameraState(cam);
          const badge = card.querySelector('[data-camera-status]');
          badge.className = `flex items-center gap-1.5 text-[10px] font-mono ${state === 'ONLINE' ? 'text-emerald-300' : state === 'CONNECTING' ? 'text-amber-300' : 'text-rose-300'}`;
          badge.querySelector('[data-status-dot]').className = `w-2 h-2 rounded-full ${state === 'ONLINE' ? 'bg-emerald-400 animate-pulse' : state === 'CONNECTING' ? 'bg-amber-400 animate-pulse' : 'bg-rose-500'}`;
          badge.lastChild.textContent = ` ${state}`;
          const health = card.querySelector('[data-camera-health]');
          health.textContent = cameraHealthText(cam);
          health.className = `min-h-8 text-[11px] font-mono ${cam.online ? 'text-emerald-300' : 'text-rose-300'}`;
          card.querySelector('[data-camera-metrics]').textContent =
            `${cam.people_seen ?? 0} persons · ${cam.captured_per_analysis ?? 0} frames/analyse · ${cam.analysis_latency_ms ?? 0}ms`;
          const scene = card.querySelector('[data-camera-scene]');
          scene.replaceWith(el(sceneBadge(cam.scene_state)));
          card.querySelector('[data-camera-motion]').innerHTML =
            `${cam.online ? motionMeter(cam.motion_score) : '<div class="mt-2 h-1.5 rounded-full bg-white/5"></div>'}${motionSparkline(cam.history)}`;
        }
        const online = latest.filter((cam) => cam.active && cam.online).length;
        const total = latest.length;
        const busy = currentFleet ? currentFleet.busy : 0;
        const budget = currentFleet ? Number(currentFleet.analysis_budget_available || 0) : 0;
        const queue = currentFleet ? Number(currentFleet.analysis_queue || 0) : 0;
        updateStat('fleet', `${online}/${total}`, `${online} online · ${total - online} offline/disabled`);
        updateStat('busy', busy, 'scene load');
        updateStat('budget', `${budget.toFixed(1)}/s`, `${queue} queued`);
        const bar = container.querySelector('[data-fleet-bar]');
        if (bar) bar.style.width = `${Math.min(100, total ? online / total * 100 : 0)}%`;
        const count = container.querySelector('[data-fleet-count]');
        if (count) count.textContent = `${online}/${total}`;
        updateMonitoringControl(currentMonitoring);
        const updated = container.querySelector('[data-camera-refresh-status]');
        if (updated) {
          updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
          updated.className = 'text-[10px] font-mono text-gray-500';
        }
      } catch (err) {
        const status = container.querySelector('[data-camera-refresh-status]');
        if (status) {
          status.textContent = `Status check failed: ${err.message}`;
          status.className = 'text-[10px] font-mono text-rose-300';
        }
      } finally {
        refreshing = false;
      }
    };

    container.querySelector('[data-action=refresh]').onclick = refreshStatus;
    if (isAdmin) container.querySelector('[data-action=manage]').onclick = () => fleetModal(container);
    if (isAdmin) container.querySelector('[data-action=monitoring]').onclick = async (event) => {
      const button = event.currentTarget;
      const shouldStop = button.dataset.running === 'true';
      button.disabled = true;
      try {
        await api(`/api/stream/monitoring/${shouldStop ? 'stop' : 'start'}`, { method: 'POST' });
        toast(shouldStop ? 'Camera monitoring stopped' : 'Camera monitoring started', 'info');
        await refreshStatus();
      } catch (err) {
        toast(err.message, 'critical');
      } finally {
        button.disabled = false;
      }
    };
    container.querySelectorAll('[data-restart-camera]').forEach((button) => {
      button.onclick = async () => {
        const cameraId = button.dataset.restartCamera;
        button.disabled = true;
        try {
          await api(`/api/stream/cameras/${encodeURIComponent(cameraId)}/restart`, { method: 'POST' });
          toast(`Restart requested for ${cameraId}`, 'info');
          setTimeout(refreshStatus, 1000);
        } catch (err) {
          toast(err.message, 'critical');
        } finally {
          button.disabled = false;
        }
      };
    });
    container.querySelectorAll('[data-snap]').forEach((b) => {
      b.onclick = () => snapshotModal(b.dataset.snap);
    });
    container.querySelectorAll('[data-detail]').forEach((b) => {
      b.onclick = () => cameraDetail(b.dataset.detail);
    });
    container.querySelectorAll('[data-clips]').forEach((b) => {
      b.onclick = () => clipsModal(b.dataset.clips);
    });
    container.querySelectorAll('[data-bbox]').forEach((b) => {
      b.onclick = () => {
        location.hash = '#assets';
        setTimeout(() => window.Views.assets && Views.assets.openPicker && Views.assets.openPicker(b.dataset.bbox), 60);
      };
    });
    const refreshTimer = setInterval(() => {
      if (!container.querySelector('[data-live-root]')) clearInterval(refreshTimer);
      else refreshStatus();
    }, 5000);
    refreshStatus();
  },
};

function cameraDetail(cameraId) {
  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-4 w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div class="flex justify-between items-center mb-3">
          <div class="text-sm font-bold text-white">Activity — ${esc(cameraId)}</div>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>
        <div class="flex items-center gap-2 mb-2">
          <button data-hours="24" class="h-btn px-3 py-1 rounded-lg text-[10px] font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">24h</button>
          <button data-hours="168" class="h-btn px-3 py-1 rounded-lg text-[10px] font-mono bg-ink-700 text-gray-300 border border-white/10">7d</button>
          <span class="text-[10px] font-mono text-gray-500" id="cam-h-stats"></span>
        </div>
        <div class="relative h-52 bg-ink-850 rounded-xl border border-white/5" id="cam-chart"><div class="absolute inset-0 grid place-items-center text-xs text-gray-500 font-mono">loading…</div></div>
      </div>
    </div>`);
  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);

  let hours = 24;
  const drawChart = () => {
    api(`/api/analytics/camera-activity?camera_id=${encodeURIComponent(cameraId)}&hours=${hours}`).then((body) => {
      const h = body.data || [];
      const chart = overlay.querySelector('#cam-chart');
      const stats = overlay.querySelector('#cam-h-stats');
      chart.innerHTML = '<canvas id="cam-chart-canvas"></canvas>';
      if (!h.length) {
        chart.innerHTML = '<div class="absolute inset-0 grid place-items-center text-xs text-gray-500 font-mono">no persisted activity yet — data appears after a few minutes</div>';
        stats.textContent = '';
        return;
      }
      const motion = h.map((x) => Number(x.avg_motion) || 0);
      const crowd = h.map((x) => Number(x.crowd_seconds) || 0);
      const labels = h.map((x) => new Date(x.bucket).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      const avg = (motion.reduce((a, b) => a + b, 0) / motion.length).toFixed(1);
      const peak = Math.max(...motion).toFixed(0);
      stats.textContent = `avg ${avg}% · peak ${peak}% · ${h.length} buckets`;
      new Chart(chart.querySelector('canvas'), {
        type: 'line',
        data: {
          labels,
          datasets: [
            { label: 'motion %', data: motion, borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.08)', fill: true, tension: 0.25, pointRadius: 0, borderWidth: 1.5 },
            { label: 'crowd s', data: crowd, borderColor: '#fbbf24', pointRadius: 0, tension: 0.25, borderWidth: 1.1, yAxisID: 'crowd' },
          ],
        },
        options: {
          animation: false,
          parsing: false,
          scales: {
            x: { ticks: { color: '#6b7280', maxTicksLimit: 8, font: { size: 9 } } },
            y: { beginAtZero: true, ticks: { color: '#6b7280', font: { size: 9 } } },
            crowd: { position: 'right', beginAtZero: true, ticks: { color: '#fbbf24', precision: 0, font: { size: 9 } }, grid: { display: false } },
          },
          plugins: { legend: { labels: { color: '#9ca3af', font: { size: 10 } } } },
        },
      });
    }).catch(() => {
      const chart = overlay.querySelector('#cam-chart');
      chart.innerHTML = '<div class="absolute inset-0 grid place-items-center text-xs text-rose-300 font-mono">activity unavailable</div>';
    });
  };

  overlay.querySelectorAll('[data-hours]').forEach((b) => {
    b.onclick = () => {
      hours = Number(b.dataset.hours);
      overlay.querySelectorAll('[data-hours]').forEach((x) => {
        const active = x === b;
        x.className = 'h-btn px-3 py-1 rounded-lg text-[10px] font-mono ' +
          (active ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : 'bg-ink-700 text-gray-300 border border-white/10');
      });
      drawChart();
    };
  });
  drawChart();
}

function clipsModal(cameraId) {
  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-4 w-full max-w-xl max-h-[85vh] flex flex-col">
        <div class="flex justify-between items-center mb-3">
          <div class="text-sm font-bold text-white">Evidence clips — ${esc(cameraId)}</div>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>
        <div class="text-[10px] font-mono text-gray-500 mb-2">Rolling buffer written to disk on feed loss / crowding incidents.</div>
        <div class="overflow-y-auto divide-y divide-white/5" id="clips-list"><div class="text-xs text-gray-500 font-mono py-6 text-center">loading…</div></div>
      </div>
    </div>`);
  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);
  api(`/api/stream/clips?camera_id=${encodeURIComponent(cameraId)}`).then((body) => {
    const list = overlay.querySelector('#clips-list');
    const clips = body.clips || [];
    if (!clips.length) {
      list.innerHTML = '<div class="text-xs text-gray-500 font-mono py-6 text-center">no saved clips yet</div>';
      return;
    }
    list.innerHTML = clips.map((c) => `
      <div class="flex items-center gap-3 py-2.5">
        <span class="text-[10px] font-mono text-gray-400 shrink-0">${new Date(c.timestamp * 1000).toLocaleString()}</span>
        <span class="text-[10px] font-mono text-amber-300 shrink-0">${(c.size_bytes / 1024).toFixed(0)}KB</span>
        <span class="text-[11px] font-mono text-gray-300 truncate flex-1">${esc(c.filename)}</span>
        <a href="/api/stream/clips/${encodeURIComponent(c.filename)}" class="text-[10px] font-mono px-2 py-1 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-cyan-300" download>open</a>
      </div>`).join('');
  }).catch(() => {
    overlay.querySelector('#clips-list').innerHTML = '<div class="text-xs text-rose-300 font-mono py-6 text-center">clips unavailable</div>';
  });
}

function snapshotModal(cameraId) {
  const img = new Image();
  img.src = `/api/stream/snapshot?camera_id=${cameraId}`;
  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-4 w-full max-w-3xl">
        <div class="flex justify-between items-center mb-3">
          <div class="text-sm font-bold text-white">Snapshot — ${esc(cameraId)}</div>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>
        <div class="bg-black rounded-xl overflow-hidden max-h-[70vh] grid place-items-center">
          <img src="${img.src}" class="max-w-full max-h-[65vh] object-contain" />
        </div>
        <div class="mt-3 text-[11px] text-gray-400">Single frame captured at request time. Head to <a href="#assets" class="text-cyan-300">Asset Memory</a> to register a protected region on a camera backdrop.</div>
      </div>
    </div>`);
  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);
}

function fleetModal(container) {
  const overlay = el(`
    <div class="fixed inset-0 z-50 grid place-items-center p-4">
      <div class="absolute inset-0 bg-black/75 backdrop-blur-sm" data-close></div>
      <div class="relative glass-card rounded-2xl p-6 w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">Camera fleet management</h3>
          <button data-close class="text-gray-400 hover:text-white">✕</button>
        </div>

        <form id="cam-add" class="grid grid-cols-2 md:grid-cols-3 gap-3 p-4 rounded-2xl bg-ink-850/70 border border-white/5 mb-5">
          <div><label class="text-[10px] text-gray-400">Camera ID</label>
            <input required name="camera_id" placeholder="cam_lobby_3" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-white" /></div>
          <div><label class="text-[10px] text-gray-400">Name</label>
            <input required name="name" placeholder="Lobby Level 3" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-white" /></div>
          <div><label class="text-[10px] text-gray-400">Source</label>
            <input required name="source" placeholder="0 | rtsp://camera-host/stream" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-white font-mono" />
            <p class="mt-1 text-[9px] text-gray-500">Webcam index (0/1) or RTSP/HTTP URL.</p></div>
          <div><label class="text-[10px] text-gray-400">Type</label>
            <select name="type" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200">
              <option value="gate">gate</option><option value="productivity">productivity</option><option value="security">security</option>
            </select></div>
          <div><label class="text-[10px] text-gray-400">Resolution</label>
            <select name="resolution" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200">
              <option value="640x480">640×480</option><option value="320x240">320×240</option><option value="1280x720">1280×720</option>
            </select></div>
          <div><label class="text-[10px] text-gray-400">Analyse FPS</label>
            <select name="fps_limit" class="mt-1 w-full px-2.5 py-1.5 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200">
              <option value="25">25</option><option value="10">10</option><option value="5">5</option>
            </select></div>
          <div class="col-span-2 md:col-span-3 flex justify-end"><button class="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:opacity-90 text-xs text-white font-semibold">＋ Add camera</button></div>
        </form>

        <div class="overflow-y-auto" id="fleet-list"></div>
      </div>
    </div>`);

  const list = overlay.querySelector('#fleet-list');
  const form = overlay.querySelector('#cam-add');

  function rowOpacity(cam) {
    if (!cam.active) return 'opacity-40';
    if (cam.online) return '';
    return 'opacity-70';
  }

  async function renderFleet() {
    const { cameras } = await api('/api/stream/cameras');
    list.innerHTML = cameras.map((cam) => `
      <div class="flex items-center gap-3 p-3 rounded-xl border border-white/5 bg-ink-850/50 mb-2 ${rowOpacity(cam)}">
        <span class="w-2 h-8 rounded-full ${cam.online ? 'bg-emerald-400' : cam.active ? 'bg-rose-500' : 'bg-gray-500'}"></span>
        <div class="min-w-0 flex-1">
          <div class="text-sm font-semibold text-white truncate">${esc(cam.name)}</div>
          <div class="text-[10px] font-mono text-gray-400 truncate">${esc(cam.camera_id)} · ${esc(cam.type)} · ${esc(cam.source)}</div>
          ${cam.online
            ? `<div class="text-[10px] font-mono mt-0.5">scene <span class="text-cyan-300">${esc(cam.scene_state)}</span> · motion ${cam.motion_score}% · ${cam.people_seen} persons · ${cam.captured_per_analysis} frames/analyse</div>`
            : `<div class="text-[10px] font-mono mt-0.5 ${cam.active ? 'text-rose-300' : 'text-gray-500'}">${esc(cameraHealthText(cam))}</div>`}
        </div>
        <div class="flex gap-1.5 shrink-0">
          <button data-toggle="${esc(cam.camera_id)}" data-active="${cam.active}" class="px-2 py-1 rounded-lg text-[10px] border ${cam.active ? 'bg-amber-500/15 text-amber-300 border-amber-500/30' : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'}">
            ${cam.active ? 'Disable' : 'Enable'}
          </button>
          <button data-restart="${esc(cam.camera_id)}" class="px-2 py-1 rounded-lg bg-ink-700 hover:bg-ink-800 border border-white/10 text-[10px] text-gray-200">Restart</button>
          <button data-del="${esc(cam.camera_id)}" class="px-2 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/30 text-[10px] text-rose-300">Remove</button>
        </div>
      </div>`).join('') || '<div class="text-center text-xs text-gray-500 py-6">None registered.</div>';
  }

  list.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-toggle],[data-restart],[data-del]');
    if (!t) return;
    const id = t.dataset.toggle || t.dataset.restart || t.dataset.del;
    try {
      if (t.dataset.toggle) {
        await api(`/api/stream/cameras/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ active: t.dataset.active !== 'true' }) });
      } else if (t.dataset.restart) {
        await api(`/api/stream/cameras/${encodeURIComponent(id)}/restart`, { method: 'POST' });
      } else {
        if (!confirm(`Remove camera ${id}? Any persisted override is dropped.`)) return;
        await api(`/api/stream/cameras/${encodeURIComponent(id)}`, { method: 'DELETE' });
      }
      toast(`Camera ${id} updated`, 'info');
      await renderFleet();
      Views.live.render(container);
    } catch (err) {
      toast(err.message, 'critical');
    }
  });

  form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    try {
      await api('/api/stream/cameras', {
        method: 'POST',
        body: JSON.stringify({
          camera_id: fd.get('camera_id').trim(),
          name: fd.get('name').trim(),
          source: fd.get('source').trim(),
          type: fd.get('type'),
          resolution: fd.get('resolution'),
          fps_limit: Number(fd.get('fps_limit')),
        }),
      });
      toast('Camera added. Start monitoring to begin its feed.', 'info');
      form.reset();
      await renderFleet();
      Views.live.render(container);
    } catch (err) {
      toast(err.message, 'critical');
    }
  };

  overlay.querySelectorAll('[data-close]').forEach((c) => (c.onclick = () => overlay.remove()));
  document.body.appendChild(overlay);
  renderFleet();
}