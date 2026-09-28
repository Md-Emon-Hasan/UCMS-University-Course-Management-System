/*
 * page-attendance.js: take attendance for one offering and one date.
 * The whole roster is saved in ONE request (and one DB transaction). Saving
 * the same date again UPDATES the rows (UPSERT on UNIQUE(enrollment_id, class_date)).
 */

const ATTENDANCE_OPTIONS = [
  { value: 'present', short: 'P', label: 'Present', on: 'peer-checked:bg-green-600 peer-checked:border-green-600' },
  { value: 'absent', short: 'A', label: 'Absent', on: 'peer-checked:bg-red-600 peer-checked:border-red-600' },
  { value: 'late', short: 'L', label: 'Late', on: 'peer-checked:bg-amber-500 peer-checked:border-amber-500' },
  { value: 'excused', short: 'E', label: 'Excused', on: 'peer-checked:bg-cyan-600 peer-checked:border-cyan-600' },
];

async function initAttendance({ content }) {
  content.innerHTML = `
    ${pageHeader('Attendance', 'Pick a class and a date, mark every student, then save once.')}
    ${card(`<div class="grid grid-cols-1 md:grid-cols-[1fr_200px_auto] gap-3 items-end">
      <div><label class="${LABEL_CLASS}" for="offering">Class</label><div id="offering-box">${skeletonBlock('h-9 w-full')}</div></div>
      <div><label class="${LABEL_CLASS}" for="class-date">Date</label>
        <input id="class-date" type="date" value="${todayISO()}" max="${todayISO()}" class="${INPUT_CLASS}"></div>
      <button type="button" id="report-btn" class="${btnClass('secondary')}" disabled>${icon('chart-column', 16)} Report</button>
    </div>`)}
    <div id="roster" class="mt-4"></div>`;
  refreshIcons();

  let offerings = [];
  try {
    const active = await loadActiveSemester();
    offerings = (await api.get('/offerings', { semester_id: active?.id, limit: 200, sort: 'course_code' }, { silent: true }))
      .items.filter((o) => o.status !== 'cancelled');
  } catch (error) {
    showError(document.getElementById('roster'), error, () => initAttendance({ content }));
    return;
  }
  if (!offerings.length) {
    document.getElementById('offering-box').innerHTML = `<select disabled class="${INPUT_CLASS}"><option>No classes this semester</option></select>`;
    document.getElementById('roster').innerHTML = card(emptyState({ iconName: 'layers', title: 'You have no classes in the active semester' }));
    refreshIcons();
    return;
  }

  const initial = Number(queryParam('offering')) || offerings[0].id;
  document.getElementById('offering-box').innerHTML = `
    <select id="offering" class="${INPUT_CLASS}">
      ${offerings.map((o) => `<option value="${o.id}" ${o.id === initial ? 'selected' : ''}>${escapeHtml(o.course_code)}-${escapeHtml(o.section)} · ${escapeHtml(o.title)} (${o.enrolled_count} students)</option>`).join('')}
    </select>`;
  const offeringSelect = document.getElementById('offering');
  const dateInput = document.getElementById('class-date');
  const reportButton = document.getElementById('report-btn');
  reportButton.disabled = false;

  const reload = () => loadRoster(Number(offeringSelect.value), dateInput.value);
  offeringSelect.addEventListener('change', reload);
  dateInput.addEventListener('change', reload);
  reportButton.addEventListener('click', () => openReport(offerings.find((o) => o.id === Number(offeringSelect.value))));
  reload();
}

async function loadRoster(offeringId, classDate) {
  const box = document.getElementById('roster');
  if (!classDate) {
    box.innerHTML = card(emptyState({ iconName: 'calendar-check', title: 'Choose a date' }));
    refreshIcons();
    return;
  }
  box.innerHTML = card(skeletonTable(8, 3), 'p-0 overflow-hidden');
  try {
    const data = await api.get(`/offerings/${offeringId}/attendance`, { class_date: classDate }, { silent: true });
    // Only students still enrolled can be marked
    const students = data.items;
    if (!students.length) {
      box.innerHTML = card(emptyState({ iconName: 'users', title: 'No students in this class' }));
      refreshIcons();
      return;
    }
    box.innerHTML = `
      <form id="attendance-form" class="bg-white rounded-xl border border-line shadow-sm">
        <div class="p-4 border-b border-line flex flex-col sm:flex-row sm:items-center gap-3">
          <div id="counts" class="flex flex-wrap gap-2 text-xs"></div>
          <div class="sm:ml-auto flex gap-2">
            <button type="button" id="all-present" class="${btnClass('secondary', 'sm')}">${icon('check', 14)} Mark all present</button>
            <button type="submit" id="save-attendance" class="${btnClass('primary', 'sm')}">${icon('save', 14)} Save attendance</button>
          </div>
        </div>
        ${data.already_recorded ? `<div class="px-4 py-2.5 text-xs bg-primary-50 text-primary-700 border-b border-line flex gap-2">${icon('info', 14)} Attendance for ${formatDate(classDate)} was already taken. Saving will update it.</div>` : ''}
        <div class="divide-y divide-line">
          ${students.map((s, index) => {
            // A graded ("completed") student is shown, but can no longer be changed
            const locked = s.enrollment_status !== 'enrolled';
            return `
            <div class="flex flex-col md:flex-row md:items-center gap-3 px-4 py-3 hover:bg-slate-50 ${locked ? 'opacity-60' : ''}" ${locked ? 'data-locked' : `data-enrollment="${s.enrollment_id}"`}>
              <div class="flex items-center gap-3 md:w-72 min-w-0">
                <span class="w-6 text-xs text-muted tabular-nums">${index + 1}</span>
                <div class="w-8 h-8 rounded-full bg-slate-100 text-slate-600 text-xs font-semibold flex items-center justify-center shrink-0">${escapeHtml(initials(s.full_name))}</div>
                <div class="min-w-0"><p class="text-sm font-medium text-ink truncate">${escapeHtml(s.full_name)}</p>
                  <p class="text-xs text-muted">${escapeHtml(s.student_code)} ${locked ? badge(s.enrollment_status) : ''}</p></div>
              </div>
              <div class="flex gap-1.5" role="radiogroup" aria-label="Attendance for ${escapeHtml(s.full_name)}">
                ${ATTENDANCE_OPTIONS.map((opt) => `
                  <label class="${locked ? 'cursor-not-allowed' : 'cursor-pointer'}" title="${opt.label}">
                    <input type="radio" name="status-${s.enrollment_id}" value="${opt.value}" class="sr-only peer" ${locked ? 'disabled' : ''} ${(s.status || '') === opt.value ? 'checked' : ''}>
                    <span class="inline-flex items-center justify-center h-8 min-w-8 sm:min-w-[72px] px-2 rounded-lg border border-line text-xs font-medium text-slate-600 bg-white
                                 hover:bg-slate-50 peer-checked:text-white ${opt.on} peer-focus-visible:ring-2 peer-focus-visible:ring-primary-500">
                      <span class="sm:hidden">${opt.short}</span><span class="hidden sm:inline">${opt.label}</span></span>
                  </label>`).join('')}
              </div>
              <input type="text" data-remarks maxlength="200" value="${escapeHtml(s.remarks || '')}" placeholder="Remarks (optional)" ${locked ? 'disabled' : ''} class="${INPUT_CLASS} md:max-w-xs md:ml-auto">
            </div>`;
          }).join('')}
        </div>
      </form>`;
    refreshIcons();

    const form = document.getElementById('attendance-form');
    const updateCounts = () => {
      const counts = { present: 0, absent: 0, late: 0, excused: 0, missing: 0 };
      form.querySelectorAll('[data-enrollment]').forEach((row) => {
        const checked = row.querySelector('input[type=radio]:checked');
        counts[checked ? checked.value : 'missing'] += 1;
      });
      document.getElementById('counts').innerHTML = [
        badge('present', `Present ${counts.present}`), badge('absent', `Absent ${counts.absent}`),
        badge('late', `Late ${counts.late}`), badge('excused', `Excused ${counts.excused}`),
        counts.missing ? badge('closed', `Not marked ${counts.missing}`) : '',
      ].join('');
    };
    updateCounts();
    form.addEventListener('change', updateCounts);

    document.getElementById('all-present').addEventListener('click', () => {
      form.querySelectorAll('input[value=present]:not(:disabled)').forEach((radio) => { radio.checked = true; });
      updateCounts();
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const rows = [...form.querySelectorAll('[data-enrollment]')];
      if (!rows.length) {
        toast('Every student in this class is already graded. There is nothing to save.', 'info');
        return;
      }
      const unmarked = rows.filter((row) => !row.querySelector('input[type=radio]:checked'));
      if (unmarked.length) {
        toast(`${unmarked.length} student(s) are not marked yet`, 'warn');
        unmarked[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        unmarked.forEach((row) => row.classList.add('bg-amber-50'));
        return;
      }
      const records = rows.map((row) => ({
        enrollment_id: Number(row.dataset.enrollment),
        status: row.querySelector('input[type=radio]:checked').value,
        remarks: row.querySelector('[data-remarks]').value.trim() || null,
      }));
      const button = document.getElementById('save-attendance');
      setBusy(button, true);
      try {
        const result = await api.post(`/offerings/${offeringId}/attendance`, { class_date: classDate, records });
        toast(`Attendance saved for ${result.saved} students`);
        loadRoster(offeringId, classDate);
      } catch {
        setBusy(button, false);
      }
    });
  } catch (error) {
    showError(box, error, () => loadRoster(offeringId, classDate));
  }
}

/** Attendance totals per student for the whole semester. */
async function openReport(offering) {
  const modal = openModal({ title: `Attendance report · ${offering.course_code}-${offering.section}`, size: 'max-w-3xl', body: skeletonTable(8, 5) });
  try {
    const data = await api.get(`/offerings/${offering.id}/attendance-report`, null, { silent: true });
    modal.body.innerHTML = data.students.length ? `
      <p class="text-xs text-muted mb-3">${data.dates.length} class days recorded · lowest attendance first</p>
      <div class="border border-line rounded-lg overflow-hidden">${renderTable({
        columns: [
          { key: 'student_code', label: 'Code', className: 'font-medium text-ink' },
          { key: 'full_name', label: 'Name' },
          { key: 'counts', label: 'P · L · A · E', className: 'tabular-nums text-xs whitespace-nowrap', render: (r) => `${r.present_only || 0} · ${r.late_count || 0} · ${r.absent_count || 0} · ${r.excused_count || 0}` },
          { key: 'attendance_percent', label: 'Attendance', render: (r) => (r.attendance_percent === null ? '—' : `
              <div class="flex items-center gap-2 min-w-[120px]"><div class="flex-1">${progressBar(r.attendance_percent, r.attendance_percent < 75 ? 'bg-danger' : 'bg-success')}</div>
              <span class="text-xs tabular-nums ${r.attendance_percent < 75 ? 'text-danger font-medium' : ''}">${formatPercent(r.attendance_percent)}</span></div>`) },
        ],
        rows: data.students,
      })}</div>` : emptyState({ iconName: 'calendar-check', title: 'No attendance recorded yet' });
    refreshIcons();
  } catch (error) {
    showError(modal.body, error, () => { modal.close(); openReport(offering); });
  }
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('attendance', 'Attendance');
if (session) initAttendance(session);
