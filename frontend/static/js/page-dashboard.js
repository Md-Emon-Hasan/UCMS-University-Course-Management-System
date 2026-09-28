/*
 * page-dashboard.js: role-aware home page.
 * GET /api/dashboard/stats returns 4 cards, 2 charts and the latest announcements
 * (the backend decides WHAT to show for each role).
 */

function initDashboard({ user, content }) {
  const firstName = (user.full_name || '').split(' ')[0];
  content.innerHTML = `
    ${pageHeader(`Welcome back, ${firstName}`, 'Here is what is happening this semester.')}
    <div id="stats" class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">${skeletonCards(4)}</div>
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4 mt-4">
      <div class="xl:col-span-2 bg-white rounded-xl border border-line shadow-sm p-5">
        <h3 id="trend-title" class="text-sm font-semibold tracking-tight text-ink">Trend</h3>
        <div class="h-72 mt-4 relative" id="trend-box">${skeletonBlock('h-full w-full')}</div>
      </div>
      <div class="bg-white rounded-xl border border-line shadow-sm p-5">
        <h3 id="dist-title" class="text-sm font-semibold tracking-tight text-ink">Distribution</h3>
        <div class="h-72 mt-4 relative" id="dist-box">${skeletonBlock('h-full w-full')}</div>
      </div>
    </div>
    <div class="bg-white rounded-xl border border-line shadow-sm mt-4">
      <div class="px-5 h-14 flex items-center justify-between border-b border-line">
        <h3 class="text-sm font-semibold tracking-tight text-ink">Recent announcements</h3>
        <span class="text-muted">${icon('megaphone', 18)}</span>
      </div>
      <div id="announcements" class="p-5 space-y-4">${skeletonBlock('h-4 w-2/3')}${skeletonBlock('h-3 w-full')}${skeletonBlock('h-4 w-1/2')}</div>
    </div>`;
  refreshIcons();
  loadDashboard();
}

/** Turn a card value into display text using its format. */
function formatCardValue(cardData) {
  const value = cardData.value;
  if (value === null || value === undefined) return '—';
  switch (cardData.format) {
    case 'money': return formatMoney(value);
    case 'percent': return formatPercent(value);
    case 'gpa': return Number(value).toFixed(2);
    default: return formatNumber(value);
  }
}

async function loadDashboard() {
  const stats = document.getElementById('stats');
  try {
    const data = await api.get('/dashboard/stats', null, { silent: true });
    stats.innerHTML = data.cards.map((c) => statCard({
      label: c.label, value: formatCardValue(c), delta: c.delta, deltaType: c.delta_type, iconName: c.icon,
    })).join('');
    drawCharts(data.charts);
    drawAnnouncements(data.announcements);
    refreshIcons();
  } catch (error) {
    showError(stats, error, loadDashboard);
    stats.className = 'bg-white rounded-xl border border-line shadow-sm';
  }
}

function drawCharts(charts) {
  const { trend, distribution } = charts;
  document.getElementById('trend-title').textContent = trend.title;
  document.getElementById('dist-title').textContent = distribution.title;

  const trendBox = document.getElementById('trend-box');
  const distBox = document.getElementById('dist-box');
  trendBox.innerHTML = trend.values.length ? '<canvas></canvas>' : emptyState({ iconName: 'chart-column', title: 'No data yet' });
  distBox.innerHTML = distribution.values.some((v) => v > 0) ? '<canvas></canvas>' : emptyState({ iconName: 'chart-column', title: 'No data yet' });

  const money = Boolean(trend.money);
  renderChart(trendBox.querySelector('canvas'), {
    type: 'line',
    data: {
      labels: trend.labels,
      datasets: [{
        data: trend.values, borderColor: '#4f6ef7', backgroundColor: 'rgba(79,110,247,0.12)',
        fill: true, tension: 0.35, pointRadius: 4, pointBackgroundColor: '#4f6ef7',
      }],
    },
    options: {
      scales: {
        y: { beginAtZero: true, ticks: { callback: (v) => (money ? formatMoney(v) : v) } },
        x: { grid: { display: false } },
      },
      plugins: { tooltip: { callbacks: { label: (ctx) => (money ? formatMoney(ctx.parsed.y) : ` ${ctx.parsed.y}`) } } },
    },
  });

  renderChart(distBox.querySelector('canvas'), {
    type: 'bar',
    data: {
      labels: distribution.labels.map(titleCase),
      datasets: [{ data: distribution.values, backgroundColor: '#4f6ef7', borderRadius: 6, maxBarThickness: 32 }],
    },
    options: { scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } },
  });
}

function drawAnnouncements(items) {
  const box = document.getElementById('announcements');
  if (!items.length) {
    box.innerHTML = emptyState({ iconName: 'megaphone', title: 'No announcements', subtitle: 'New notices will appear here.' });
    return;
  }
  box.innerHTML = items.map((a) => `
    <article class="flex gap-3">
      <div class="w-9 h-9 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center shrink-0">${icon('megaphone', 16)}</div>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-2">
          <p class="text-sm font-medium text-ink">${escapeHtml(a.title)}</p>
          ${a.target_role ? badge('info', `For ${titleCase(a.target_role)}s`) : ''}
          ${a.target_department_code ? badge('completed', a.target_department_code) : ''}
        </div>
        <p class="text-sm text-slate-600 mt-0.5 line-clamp-2">${escapeHtml(a.body)}</p>
        <p class="text-xs text-muted mt-1">${formatDateTime(a.published_at)}</p>
      </div>
    </article>`).join('');
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('dashboard', 'Dashboard');
if (session) initDashboard(session);
