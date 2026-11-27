/* Command Center — KPIs, occupancy, charts, live incident strip */

window.Views = window.Views || {};

function kpiCard(label, value, accent, sub) {
  return `
  <div class="glass-card rounded-2xl p-4">
    <div class="text-[10px] font-mono uppercase tracking-widest text-gray-400">${label}</div>
    <div class="mt-2 text-3xl font-extrabold ${accent} tabular-nums leading-none">${esc(value)}</div>
    ${sub ? `<div class="mt-1.5 text-[11px] text-gray-500">${sub}</div>` : ''}
  </div>`;
}

Views.dashboard = {
  render: async (container) => {
    const [dash, occupancy, attTS, alertTS, alerts] = await Promise.all([
      api('/api/analytics/dashboard').catch(() => null),
      api('/api/analytics/occupancy').catch(() => []),
      api('/api/analytics/timeseries?metric=attendance&hours=24').catch(() => ({ data: [] })),
      api('/api/analytics/timeseries?metric=alerts&hours=24').catch(() => ({ data: [] })),
      api('/api/alerts?limit=16').catch(() => ({ data: [] })),
    ]);
    const s = (dash && dash.summary) || {};
    const alertsData = (alerts.data || []).slice(0, 16);

    let occCards = '';
    if (Array.isArray(occupancy) && occupancy.length) {
      occCards = occupancy.map((o) => `
        <div class="glass-card rounded-2xl p-4 flex items-center justify-between">
          <div>
            <div class="text-[10px] font-mono text-gray-400 uppercase">${esc(o.camera_id)}</div>
            <div class="text-[11px] text-gray-300 mt-0.5">Inside now</div>
          </div>
          <div class="text-right">
            <div class="text-3xl font-extrabold text-cyan-300 leading-none tabular-nums">${o.currently_inside}</div>
            <div class="text-[10px] text-gray-500 mt-1">peak ${o.peak_inside} · in ${o.total_entries} / out ${o.total_exits}</div>
          </div>
        </div>`).join('');
    } else {
      occCards = `<div class="glass-card rounded-2xl p-4 text-xs text-gray-400">No gate cameras online to report live occupancy.</div>`;
    }

    container.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4 mb-6">
        ${kpiCard('Personnel', s.total_personnel || 0, 'text-white')}
        ${kpiCard("Today's entries", s.today_attendance || 0, 'text-cyan-300')}
        ${kpiCard('Active Alerts', s.unresolved_alerts || 0, 'text-amber-300')}
        ${kpiCard('Assets Tracked', s.total_assets || 0, 'text-indigo-300')}
        ${kpiCard('Theft Threats', s.theft_threats || 0, 'text-rose-300')}
        ${kpiCard('Phone Distractions', s.phone_distractions || 0, 'text-amber-300')}
      </div>

      <div class="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
        <div class="glass-card rounded-2xl p-5 xl:col-span-2">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-sm font-bold text-white">Event activity — last 24h</h3>
            <span class="text-[10px] font-mono text-gray-400">hourly buckets</span>
          </div>
          <div class="h-64"><canvas id="ts-chart"></canvas></div>
        </div>
        <div class="glass-card rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-4">Incident severity</h3>
          <div class="h-64"><canvas id="sev-chart"></canvas></div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="glass-card rounded-2xl p-5 lg:col-span-2">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-white">Live occupancy</h3>
            <a class="text-[11px] text-cyan-300 hover:underline" href="#live">Open camera grid →</a>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">${occCards}</div>
        </div>
        <div class="glass-card rounded-2xl p-5">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-sm font-bold text-white">Latest incidents</h3>
            <a class="text-[11px] text-cyan-300 hover:underline" href="#incidents">All →</a>
          </div>
          <div class="space-y-2 max-h-[300px] overflow-y-auto">
            ${alertsData.length ? alertsData.map((a) => `
              <div class="p-2.5 rounded-xl border border-white/5 bg-ink-850/60 text-xs">
                <div class="flex items-center justify-between mb-1">
                  <span class="font-mono text-[10px] text-gray-400">${esc(a.alert_type)}</span>
                  <span class="text-[10px] text-gray-500">${fmtDt(a.timestamp)}</span>
                </div>
                <div class="flex items-center gap-2 mb-1.5">${severityBadge(a.severity)}${a.is_resolved ? '<span class="text-[10px] text-emerald-300">✓ resolved</span>' : ''}</div>
                <p class="text-gray-300 leading-relaxed">${esc(a.description)}</p>
              </div>`).join('') : '<div class="text-xs text-gray-400">No incidents yet</div>'}
          </div>
        </div>
      </div>`;

    drawTrend(document.getElementById('ts-chart'), [
      { label: 'Attendance', data: (attTS.data || []).map((b) => ({ t: b.bucket + 'Z', y: b.count })), color: '#22d3ee' },
      { label: 'Alerts', data: (alertTS.data || []).map((b) => ({ t: b.bucket + 'Z', y: b.count })), color: '#f43f5e' },
    ]);
    drawSeverity(document.getElementById('sev-chart'),
      alertsData.map((a) => a.severity || 'INFO'));
  },
};

function drawTrend(canvas, series) {
  const charts = window.__charts = window.__charts || {};
  if (charts[canvas.id]) charts[canvas.id].destroy();
  const labels = series[0] ? series[0].data.map((p) => {
    const d = new Date(p.t);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }) : [];
  charts[canvas.id] = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: series.map((s) => ({
        label: s.label,
        data: s.data.map((p) => p.y),
        borderColor: s.color,
        backgroundColor: s.color + '22',
        fill: true, tension: 0.3, pointRadius: 2, borderWidth: 2,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#9ca3af', font: { size: 11 } } } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', maxTicksLimit: 8, font: { size: 10 } } },
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', precision: 0 } },
      },
    },
  });
}

function drawSeverity(canvas, severities) {
  const charts = window.__charts = window.__charts || {};
  if (charts[canvas.id]) charts[canvas.id].destroy();
  const counts = severities.reduce((acc, s) => { acc[s] = (acc[s] || 0) + 1; return acc; }, {});
  charts[canvas.id] = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: Object.keys(counts), datasets: [{
        data: Object.values(counts),
        backgroundColor: ['#0ea5e9', '#f59e0b', '#f43f5e'].slice(0, Object.keys(counts).length),
        borderColor: '#0b1019', borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#9ca3af', font: { size: 11 }, boxWidth: 12 } } },
    },
  });
}