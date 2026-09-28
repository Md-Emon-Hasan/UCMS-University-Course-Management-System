/*
 * page-reports.js: 4 report sections with charts and CSV export.
 *   Grade distribution    (admin, teacher)
 *   Department performance (admin; read from the mv_department_performance table)
 *   Collection summary    (admin, accountant)
 *   Low attendance        (admin, teacher)
 * Each role only sees the sections it may use.
 */

async function initReports({ user, content }) {
  const can = (roles) => roles.includes(user.role);
  content.innerHTML = `
    ${pageHeader('Reports', 'Summaries built with GROUP BY, views, window functions and a materialized-view table.')}
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      ${can(['admin', 'teacher']) ? '<section id="grades"></section>' : ''}
      ${can(['admin']) ? '<section id="departments"></section>' : ''}
      ${can(['admin', 'accountant']) ? '<section id="collection" class="xl:col-span-2"></section>' : ''}
      ${can(['admin', 'teacher']) ? '<section id="attendance" class="xl:col-span-2"></section>' : ''}
    </div>`;

  let semesters = [];
  let active = null;
  try {
    [semesters, active] = await Promise.all([loadSemesters(), loadActiveSemester()]);
  } catch (error) {
    showError(content.querySelector('section') || content, error, () => initReports({ user, content }));
    return;
  }
  const semesterOptions = semesters.map((s) => `<option value="${s.id}">${escapeHtml(s.code)}${s.is_active ? ' (active)' : ''}</option>`).join('');
  // The most recent semester that already has grades (the active one has none yet)
  const gradedSemester = semesters.find((s) => !s.is_active) || semesters[0];

  if (can(['admin', 'teacher'])) gradeSection(document.getElementById('grades'), semesterOptions, gradedSemester);
  if (can(['admin'])) departmentSection(document.getElementById('departments'));
  if (can(['admin', 'accountant'])) collectionSection(document.getElementById('collection'), semesterOptions, active);
  if (can(['admin', 'teacher'])) attendanceSection(document.getElementById('attendance'), semesterOptions, active);
}

/** Card frame shared by all sections */
function reportCard(title, subtitle, controlsHtml, bodyHtml) {
  return `
    <div class="bg-white rounded-xl border border-line shadow-sm p-5 h-full">
      <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
        <div><h3 class="text-sm font-semibold tracking-tight text-ink">${escapeHtml(title)}</h3>
        <p class="text-xs text-muted mt-0.5">${escapeHtml(subtitle)}</p></div>
        <div class="flex flex-wrap gap-2 items-center">${controlsHtml}</div>
      </div>
      <div data-body>${bodyHtml}</div>
    </div>`;
}

const csvButton = () => `<button type="button" data-csv class="${btnClass('secondary', 'sm')}">${icon('download', 14)} CSV</button>`;

// ------------------------------------------------------------ Grade distribution
function gradeSection(section, semesterOptions, gradedSemester) {
  section.innerHTML = reportCard('Grade distribution', 'Completed enrollments per letter grade',
    `<select data-semester class="${INPUT_CLASS} h-8 text-xs w-32">${semesterOptions}</select>
     <select data-offering class="${INPUT_CLASS} h-8 text-xs w-44"><option value="">All offerings</option></select>${csvButton()}`,
    `<div class="h-64">${skeletonBlock('h-full w-full')}</div>`);
  refreshIcons();
  const semesterSelect = section.querySelector('[data-semester]');
  const offeringSelect = section.querySelector('[data-offering]');
  const body = section.querySelector('[data-body]');
  if (gradedSemester) semesterSelect.value = gradedSemester.id;
  let rows = [];

  async function loadOfferings() {
    const data = await api.get('/offerings', { semester_id: semesterSelect.value, limit: 200, sort: 'course_code' }, { silent: true });
    offeringSelect.innerHTML = '<option value="">All offerings</option>' + data.items
      .map((o) => `<option value="${o.id}">${escapeHtml(o.course_code)}-${escapeHtml(o.section)}</option>`).join('');
  }
  async function load() {
    body.innerHTML = `<div class="h-64">${skeletonBlock('h-full w-full')}</div>`;
    try {
      const data = await api.get('/reports/grade-distribution', { offering_id: offeringSelect.value }, { silent: true });
      rows = data.items;
      if (!rows.some((r) => r.count)) {
        body.innerHTML = emptyState({ iconName: 'chart-column', title: 'No grades yet', subtitle: 'Grades appear after they are finalized.' });
        refreshIcons();
        return;
      }
      body.innerHTML = '<div class="h-64"><canvas></canvas></div>';
      renderChart(body.querySelector('canvas'), {
        type: 'bar',
        data: { labels: rows.map((r) => r.letter_grade), datasets: [{ data: rows.map((r) => r.count), backgroundColor: rows.map((r) => (r.letter_grade === 'F' ? '#dc2626' : '#4f6ef7')), borderRadius: 6, maxBarThickness: 36 }] },
        options: {
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } },
          plugins: { tooltip: { callbacks: { label: (c) => ` ${c.parsed.y} students (${rows[c.dataIndex].percent}%)` } } },
        },
      });
    } catch (error) {
      showError(body, error, load);
    }
  }
  semesterSelect.addEventListener('change', async () => { await loadOfferings().catch(() => {}); offeringSelect.value = ''; load(); });
  offeringSelect.addEventListener('change', load);
  section.querySelector('[data-csv]').addEventListener('click', () => downloadCSV('grade-distribution.csv', rows,
    [{ key: 'letter_grade', label: 'Grade' }, { key: 'count', label: 'Students' }, { key: 'percent', label: 'Percent' }]));
  loadOfferings().catch(() => {}).then(load);
}

// ------------------------------------------------------- Department performance
function departmentSection(section) {
  section.innerHTML = reportCard('Department performance', 'Average GPA per department and semester (pre-calculated table)',
    `<button type="button" data-refresh class="${btnClass('secondary', 'sm')}">${icon('refresh-cw', 14)} Refresh</button>${csvButton()}`,
    `<div class="h-64">${skeletonBlock('h-full w-full')}</div>`);
  refreshIcons();
  const body = section.querySelector('[data-body]');
  let rows = [];

  function draw(data) {
    rows = data.rows;
    if (!rows.length) {
      body.innerHTML = emptyState({ iconName: 'chart-column', title: 'No data', subtitle: 'Press Refresh to calculate it.' });
      refreshIcons();
      return;
    }
    const semestersCodes = [...new Set(rows.map((r) => r.semester_code))];
    const departmentCodes = [...new Set(rows.map((r) => r.department_code))];
    body.innerHTML = `<div class="h-64"><canvas></canvas></div>
      <p class="text-xs text-muted mt-3">Last refreshed ${formatDateTime(data.refreshed_at)}. A "materialized view" is fast to read, but only as fresh as its last refresh.</p>`;
    renderChart(body.querySelector('canvas'), {
      type: 'bar',
      data: {
        labels: semestersCodes,
        datasets: departmentCodes.map((code, i) => ({
          label: code, backgroundColor: CHART_COLORS[i % CHART_COLORS.length], borderRadius: 4, maxBarThickness: 18,
          data: semestersCodes.map((sem) => rows.find((r) => r.semester_code === sem && r.department_code === code)?.avg_gpa ?? null),
        })),
      },
      options: {
        scales: { y: { min: 0, max: 4, title: { display: true, text: 'Average GPA' } }, x: { grid: { display: false } } },
        plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10 } } },
      },
    });
  }
  async function load() {
    try { draw(await api.get('/reports/department-performance', null, { silent: true })); } catch (error) { showError(body, error, load); }
  }
  section.querySelector('[data-refresh]').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, 'Refreshing…');
    try {
      const data = await api.post('/reports/department-performance/refresh');
      toast(`Recalculated ${data.rows.length} rows`);
      draw(data);
    } finally {
      setBusy(button, false);
    }
  });
  section.querySelector('[data-csv]').addEventListener('click', () => downloadCSV('department-performance.csv', rows, [
    { key: 'semester_code', label: 'Semester' }, { key: 'department_code', label: 'Department' },
    { key: 'avg_gpa', label: 'Average GPA' }, { key: 'pass_rate', label: 'Pass rate %' }, { key: 'total_students', label: 'Students' },
  ]));
  load();
}

// ------------------------------------------------------------ Collection summary
function collectionSection(section, semesterOptions, active) {
  section.innerHTML = reportCard('Collection summary', 'Billed vs collected, by payment method and department',
    `<select data-semester class="${INPUT_CLASS} h-8 text-xs w-32">${semesterOptions}</select>${csvButton()}`,
    `<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">${skeletonCards(4)}</div>`);
  refreshIcons();
  const semesterSelect = section.querySelector('[data-semester]');
  const body = section.querySelector('[data-body]');
  if (active) semesterSelect.value = active.id;
  let byDepartment = [];

  async function load() {
    body.innerHTML = `<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">${skeletonCards(4)}</div>`;
    try {
      const data = await api.get('/reports/collection-summary', { semester_id: semesterSelect.value }, { silent: true });
      const t = data.totals;
      byDepartment = data.by_department;
      if (!t.invoices) {
        body.innerHTML = emptyState({ iconName: 'wallet', title: 'No invoices in this semester' });
        refreshIcons();
        return;
      }
      body.innerHTML = `
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
          ${statCard({ label: 'Billed', value: formatMoney(t.billed), iconName: 'file-text', delta: `${t.invoices} invoices` })}
          ${statCard({ label: 'Collected', value: formatMoney(t.collected), iconName: 'wallet', delta: `${t.collection_rate}% collected`, deltaType: 'success' })}
          ${statCard({ label: 'Outstanding', value: formatMoney(t.outstanding), iconName: 'circle-alert', deltaType: 'danger', delta: `${t.invoices - t.paid_invoices} invoices open` })}
          ${statCard({ label: 'Overdue', value: t.overdue_invoices || 0, iconName: 'clock', delta: 'past the due date', deltaType: 'danger' })}
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
          <div><p class="text-xs uppercase tracking-wide text-muted mb-2">By payment method</p><div class="h-56"><canvas data-method></canvas></div></div>
          <div class="lg:col-span-2"><p class="text-xs uppercase tracking-wide text-muted mb-2">By department</p>
            <div class="border border-line rounded-lg overflow-hidden">${renderTable({
              columns: [
                { key: 'department_code', label: 'Dept', className: 'font-medium text-ink' },
                { key: 'invoices', label: 'Invoices', className: 'tabular-nums' },
                { key: 'billed', label: 'Billed', className: 'tabular-nums text-right', headerClass: 'text-right', render: (r) => formatMoney(r.billed) },
                { key: 'collected', label: 'Collected', className: 'tabular-nums text-right', headerClass: 'text-right', render: (r) => formatMoney(r.collected) },
                { key: 'outstanding', label: 'Outstanding', className: 'tabular-nums text-right', headerClass: 'text-right', render: (r) => formatMoney(r.outstanding) },
                { key: 'rate', label: 'Rate', render: (r) => `<div class="flex items-center gap-2 min-w-[100px]"><div class="flex-1">${progressBar((r.collected / r.billed) * 100, 'bg-success')}</div><span class="text-xs tabular-nums">${formatPercent((r.collected / r.billed) * 100, 0)}</span></div>` },
              ],
              rows: data.by_department,
            })}</div></div>
        </div>`;
      refreshIcons();
      renderChart(body.querySelector('[data-method]'), {
        type: 'doughnut',
        data: { labels: data.by_method.map((m) => titleCase(m.method)), datasets: [{ data: data.by_method.map((m) => m.amount), backgroundColor: CHART_COLORS, borderWidth: 0 }] },
        options: {
          cutout: '62%',
          plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10, boxHeight: 10 } },
                     tooltip: { callbacks: { label: (c) => ` ${formatMoney(c.parsed)}` } } },
        },
      });
    } catch (error) {
      showError(body, error, load);
    }
  }
  semesterSelect.addEventListener('change', load);
  section.querySelector('[data-csv]').addEventListener('click', () => downloadCSV('collection-by-department.csv', byDepartment, [
    { key: 'department_code', label: 'Department' }, { key: 'invoices', label: 'Invoices' },
    { key: 'billed_taka', label: 'Billed (BDT)' }, { key: 'collected_taka', label: 'Collected (BDT)' }, { key: 'outstanding_taka', label: 'Outstanding (BDT)' },
  ]));
  load();
}

// -------------------------------------------------------------- Low attendance
function attendanceSection(section, semesterOptions, active) {
  section.innerHTML = reportCard('Low attendance', 'Students below the threshold in a course (present + late count as attended)',
    `<label class="text-xs text-muted flex items-center gap-2">Below
       <input data-threshold type="number" min="1" max="100" step="1" value="75" class="${INPUT_CLASS} h-8 w-20 text-xs">%</label>
     <select data-semester class="${INPUT_CLASS} h-8 text-xs w-32">${semesterOptions}</select>${csvButton()}`,
    skeletonTable(6, 5));
  refreshIcons();
  const body = section.querySelector('[data-body]');
  const semesterSelect = section.querySelector('[data-semester]');
  const thresholdInput = section.querySelector('[data-threshold]');
  if (active) semesterSelect.value = active.id;
  let rows = [];

  async function load() {
    const threshold = Number(thresholdInput.value);
    if (!(threshold > 0 && threshold <= 100)) { thresholdInput.classList.add('border-danger'); return; }
    thresholdInput.classList.remove('border-danger');
    body.innerHTML = skeletonTable(6, 5);
    try {
      const data = await api.get('/reports/low-attendance', { threshold, semester_id: semesterSelect.value }, { silent: true });
      rows = data.items;
      body.innerHTML = rows.length ? `
        <p class="text-xs text-muted mb-2">${rows.length} enrollment(s) below ${threshold}% in ${escapeHtml(data.semester_code)}</p>
        <div class="border border-line rounded-lg overflow-hidden">${renderTable({
          columns: [
            { key: 'student_code', label: 'Code', className: 'font-medium text-ink' },
            { key: 'student_name', label: 'Student' },
            { key: 'course_code', label: 'Course', render: (r) => `${escapeHtml(r.course_code)}-${escapeHtml(r.section)}` },
            { key: 'attended', label: 'Attended', className: 'tabular-nums', render: (r) => `${r.present_count}/${r.total_classes}` },
            { key: 'attendance_percent', label: 'Attendance', render: (r) => `<div class="flex items-center gap-2 min-w-[140px]"><div class="flex-1">${progressBar(r.attendance_percent, 'bg-danger')}</div><span class="text-xs text-danger font-medium tabular-nums">${formatPercent(r.attendance_percent)}</span></div>` },
          ],
          rows,
        })}</div>` : emptyState({ iconName: 'circle-check', title: 'Everyone is above the threshold' });
      refreshIcons();
    } catch (error) {
      showError(body, error, load);
    }
  }
  thresholdInput.addEventListener('input', debounce(load, 300));
  semesterSelect.addEventListener('change', load);
  section.querySelector('[data-csv]').addEventListener('click', () => downloadCSV('low-attendance.csv', rows, [
    { key: 'student_code', label: 'Code' }, { key: 'student_name', label: 'Student' }, { key: 'course_code', label: 'Course' },
    { key: 'section', label: 'Section' }, { key: 'present_count', label: 'Attended' }, { key: 'total_classes', label: 'Classes' },
    { key: 'attendance_percent', label: 'Attendance %' },
  ]));
  load();
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('reports', 'Reports');
if (session) initReports(session);
