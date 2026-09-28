/*
 * page-semesters.js: semesters as cards. "Set active" (with confirmation) and
 * "Close semester" (finalizes every grade, then switches the active semester).
 */

function initSemesters({ content }) {
  content.innerHTML = `
    ${pageHeader('Semesters', 'Only one semester can be active at a time (enforced by a partial unique index).',
      `<button type="button" id="new-semester" class="${btnClass('primary')}">${icon('plus', 16)} New semester</button>`)}
    <div id="cards" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">${skeletonCards(3)}</div>`;
  refreshIcons();
  document.getElementById('new-semester').addEventListener('click', openSemesterForm);
  loadSemesterCards();
}

async function loadSemesterCards() {
  const box = document.getElementById('cards');
  box.innerHTML = skeletonCards(3);
  try {
    const data = await api.get('/semesters', { limit: 100 }, { silent: true });
    if (!data.items.length) {
      box.innerHTML = `<div class="md:col-span-2 xl:col-span-3">${card(emptyState({ iconName: 'calendar-range', title: 'No semesters yet' }))}</div>`;
      refreshIcons();
      return;
    }
    box.innerHTML = data.items.map((s) => semesterCard(s)).join('');
    refreshIcons();
    box.querySelectorAll('[data-activate]').forEach((b) => b.addEventListener('click', () => activate(data.items.find((s) => s.id === Number(b.dataset.activate)))));
    box.querySelectorAll('[data-close-semester]').forEach((b) => b.addEventListener('click', () => openCloseForm(data.items.find((s) => s.id === Number(b.dataset.closeSemester)), data.items)));
  } catch (error) {
    showError(box, error, loadSemesterCards);
  }
}

function semesterCard(s) {
  const dateRow = (iconName, label, value) => `
    <div class="flex items-center gap-2 text-xs"><span class="text-slate-400">${icon(iconName, 14)}</span>
      <span class="text-muted w-24">${label}</span><span class="text-ink">${value}</span></div>`;
  return `
    <div class="bg-white rounded-xl border ${s.is_active ? 'border-primary-500 ring-2 ring-primary-100' : 'border-line'} shadow-sm p-5 flex flex-col">
      <div class="flex items-start justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-wide text-muted">${escapeHtml(s.code)}</p>
          <h3 class="text-base font-semibold tracking-tight text-ink mt-0.5">${escapeHtml(s.name)}</h3>
        </div>
        <div class="flex flex-col items-end gap-1">
          ${s.is_active ? badge('active', 'Active') : badge('closed', 'Inactive')}
          ${s.registration_open ? badge('open', 'Registration open') : ''}
        </div>
      </div>
      <div class="space-y-2 mt-4">
        ${dateRow('calendar-range', 'Classes', `${formatDate(s.start_date)} – ${formatDate(s.end_date)}`)}
        ${dateRow('clipboard-list', 'Registration', `${formatDate(s.registration_start)} – ${formatDate(s.registration_end)}`)}
      </div>
      <div class="grid grid-cols-2 gap-3 mt-4">
        <div class="rounded-lg bg-slate-50 p-3"><p class="text-xs text-muted">Offerings</p><p class="text-lg font-semibold text-ink">${s.offering_count}</p></div>
        <div class="rounded-lg bg-slate-50 p-3"><p class="text-xs text-muted">Enrollments</p><p class="text-lg font-semibold text-ink">${formatNumber(s.enrollment_count)}</p></div>
      </div>
      <div class="mt-4 pt-4 border-t border-line flex justify-end gap-2 mt-auto">
        ${s.is_active
          ? `<button type="button" data-close-semester="${s.id}" class="${btnClass('secondary', 'sm')}">${icon('lock', 14)} Close semester</button>`
          : `<button type="button" data-activate="${s.id}" class="${btnClass('secondary', 'sm')}">${icon('check', 14)} Set active</button>`}
      </div>
    </div>`;
}

async function activate(semester) {
  const ok = await confirmDialog({
    title: `Make ${semester.code} the active semester?`,
    message: 'The current active semester will be switched off. Registration, routines and dashboards will use this semester instead.',
    confirmText: 'Set active',
    danger: false,
  });
  if (!ok) return;
  await api.patch(`/semesters/${semester.id}/activate`);
  toast(`${semester.code} is now active`);
  dataCache['active-semester'] = null;
  loadActiveSemester().then((s) => { const pill = document.querySelector('#semester-pill span'); if (pill && s) pill.textContent = `${s.code} · Active`; });
  loadSemesterCards();
}

function openCloseForm(semester, all) {
  const others = all.filter((s) => s.id !== semester.id);
  formModal({
    title: `Close ${semester.code}`,
    submitText: 'Close semester',
    fieldsHtml: `
      <div class="rounded-lg bg-amber-50 text-amber-800 text-xs px-3 py-2.5 mb-4 flex gap-2">${icon('triangle-alert', 16)}
        <span>Every enrollment still "enrolled" gets its final grade now, and marks become locked. All of this runs in ONE transaction: if any grade cannot be finalized, nothing changes.</span></div>
      ${field({ name: 'next_semester_id', label: 'Next active semester', type: 'select', number: true, required: true, options: toOptions(others, (s) => `${s.code} · ${s.name}`) })}`,
    onSubmit: async (values) => {
      const ok = await confirmDialog({ title: 'Are you absolutely sure?', message: `Grades of ${semester.code} will be finalized. This cannot be undone.`, confirmText: 'Yes, close it' });
      if (!ok) throw new Error('cancelled');
      return api.post(`/semesters/${semester.id}/close`, values);
    },
    onSuccess: (result) => {
      toast(`${result.closed_semester} closed · ${result.grades_finalized} grades finalized`);
      dataCache['active-semester'] = null;
      loadSemesterCards();
    },
  });
}

function openSemesterForm() {
  formModal({
    title: 'New semester',
    submitText: 'Create semester',
    fieldsHtml: `
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
        ${field({ name: 'name', label: 'Name', required: true, minlength: 2, maxlength: 60, placeholder: 'Spring 2027' })}
        ${field({ name: 'code', label: 'Code', required: true, pattern: '[A-Z]{3}[0-9]{2}', title: '3 letters + 2 digits, e.g. SPR27', placeholder: 'SPR27' })}
        ${field({ name: 'start_date', label: 'Classes start', type: 'date', required: true })}
        ${field({ name: 'end_date', label: 'Classes end', type: 'date', required: true })}
        ${field({ name: 'registration_start', label: 'Registration opens', type: 'date', required: true })}
        ${field({ name: 'registration_end', label: 'Registration closes', type: 'date', required: true })}
      </div>
      <p class="text-xs text-muted">New semesters start inactive. Use "Set active" when it begins.</p>`,
    // Same rules as the CHECK constraints in the semesters table
    extraCheck: (v) => {
      const errors = {};
      if (v.start_date && v.end_date && v.end_date <= v.start_date) errors.end_date = 'Must be after the start date';
      if (v.registration_start && v.registration_end && v.registration_end <= v.registration_start) errors.registration_end = 'Must be after registration opens';
      return errors;
    },
    onSubmit: (values) => api.post('/semesters', values),
    onSuccess: (saved) => { toast(`${saved.code} created`); dataCache.semesters = null; loadSemesterCards(); },
  });
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('semesters', 'Semesters');
if (session) initSemesters(session);
