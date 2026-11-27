/* Analytics — hourly time-series across metrics + label breakdown + summary */

window.Views = window.Views || {};

Views.analytics = {
  render: async (container) => {
    const metrics = [
      ['attendance', 'Gate events', '#22d3ee', 'events'],
      ['productivity', 'Productivity sessions', '#a78bfa', 'sessions'],
      ['health', 'Health detections', '#34d399', 'detections'],
      ['alerts', 'Incidents', '#f43f5e', 'incidents'],
    ];

    container.innerHTML = `
      <div class="glass-card rounded-2xl p-4 mb-6">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="text-sm font-bold text-white">Hourly time-series</div>
          <div class="flex items-center gap-2">
            <select id="metric" class="px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200 focus:outline-none">
              ${metrics.map(([k, label]) => `<option value="${k}">${label}</option>`).join('')}
            </select>
            <select id="hours" class="px-3 py-2 rounded-lg bg-ink-800 border border-white/10 text-xs text-gray-200 focus:outline-none">
              ${[24, 48, 72, 168].map((h) => `<option value="${h}">${h} hour${h > 24 ? 's' : ''}</option>`).join('')}
            </select>
          </div>
        </div>
      </div>

      <div class="glass-card rounded-2xl p-5 mb-6">
        <div class="h-80"><canvas id="ts-chart"></canvas></div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="glass-card rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-4">Breakdown by label</h3>
          <div class="h-64"><canvas id="breakdown-chart"></canvas></div>
        </div>
        <div class="glass-card rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-4">Summary</h3>
          <div id="summary" class="space-y-3"></div>
        </div>
      </div>`;

    const charts = window.__charts = window.__charts || {};
    const meta = (k) => metrics.find(([key]) => key === k);

    function renderSummary(labels, series, unit) {
      const total = series.reduce((a, b) => a + b, 0);
      const avg = labels.length ? Math.round(total / labels.length * 10) / 10 : 0;
      const max = Math.max(0, ...series);
      const peak = series.indexOf(max);
      const box = el(`
        <div class="rounded-xl bg-ink-850/70 border border-white/5 p-4 space-y-2 text-sm" id="summary-box">
          <div class="flex justify-between"><span class="text-gray-400">Total</span><span class="font-bold text-white tabular-nums">${total} ${unit}</span></div>
          <div class="flex justify-between"><span class="text-gray-400">Per-bucket average</span><span class="text-cyan-300 tabular-nums">${avg} ${unit}</span></div>
          <div class="flex justify-between"><span class="text-gray-400">Peak bucket</span><span class="text-amber-300 tabular-nums">${max} (${peak >= 0 ? labels[peak] : '—'})</span></div>
          <div class="flex justify-between"><span class="text-gray-400">Buckets with data</span><span class="text-emerald-300 tabular-nums">${series.filter((v) => v > 0).length} / ${labels.length}</span></div>
        </div>`);
      return box;
    }

    async function refresh() {
      const metric = container.querySelector('#metric').value;
      const hours = Number(container.querySelector('#hours').value);
      const [key, _label, color, unit] = meta(metric);
      const res = await api(`/api/analytics/timeseries?metric=${metric}&hours=${hours}`).catch(() => ({ data: [] }));
      const buckets = res.data || [];
      const labels = buckets.map((b) => {
        const d = new Date(b.bucket + (b.bucket.includes('Z') ? '' : 'Z'));
        return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      });
      const totals = buckets.map((b) => b.count);

      const allLabels = {};
      buckets.forEach((b) => Object.entries(b.by_label || {}).forEach(([k, v]) => { allLabels[k] = (allLabels[k] || 0) + v; }));

      if (charts['ts-chart']) charts['ts-chart'].destroy();
      charts['ts-chart'] = new Chart(document.getElementById('ts-chart'), {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: unit, data: totals,
            backgroundColor: color + '55', borderColor: color, borderWidth: 1.5, borderRadius: 4,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', maxTicksLimit: 10, font: { size: 10 } } },
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#6b7280', precision: 0 } },
          },
        },
      });

      const breakdownLabels = Object.keys(allLabels);
      if (charts['breakdown-chart']) charts['breakdown-chart'].destroy();
      if (breakdownLabels.length) {
        charts['breakdown-chart'] = new Chart(document.getElementById('breakdown-chart'), {
          type: 'doughnut',
          data: {
            labels: breakdownLabels,
            datasets: [{
              data: Object.values(allLabels),
              backgroundColor: ['#22d3ee', '#f59e0b', '#f43f5e', '#34d399', '#a78bfa', '#f472b6', '#facc15', '#60a5fa'],
              borderColor: '#0b1019', borderWidth: 2,
            }],
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { position: 'right', labels: { color: '#9ca3af', font: { size: 11 }, boxWidth: 12 } } },
          },
        });
      } else {
        document.getElementById('breakdown-chart').getContext('2d').clearRect(0, 0, 1, 1);
      }

      const summaryEl = document.getElementById('summary');
      summaryEl.innerHTML = '';
      summaryEl.appendChild(render(labels, totals, unit));
    }

    container.querySelector('#metric').onchange = refresh;
    container.querySelector('#hours').onchange = refresh;
    refresh();
  },
};