/*
 * page-offerings.js: course offerings with fill-percent bars.
 *   Admin: create/edit offerings, manage weekly schedules (clashes are rejected by DB triggers)
 *   Teacher: sees only their own offerings; can open the roster
 */

async function initOfferings({ user, content }) {
  const isAdmin = user.role === 'admin';
  content.innerHTML = pageHeader('Course offerings',
    isAdmin ? 'Courses opened in a semester, their teacher, seats and weekly schedule.' : 'Your offerings. Open one to see the roster.')
    + `<div id="list">${card(skeletonTable(8, 7), 'p-0')}</div>`;

  let departments, semesters, active;
  try {
    [departments, semesters, active] = await Promise.all([loadDepartments(), loadSemesters(), loadActiveSemester()]);
  } catch (error) {
    showError(document.getElementById('list'), error, () => initOfferings({ user, content }));
    return;
  }
  const semesterOptions = toOptions(semesters, (s) => `${s.code}${s.is_active ? ' (active)' : ''}`);

  const columns = [
    { key: 'course_code', label: 'Course', sortable: true, render: (r) => `
        <div class="min-w-[180px]"><p class="font-medium text-ink">${escapeHtml(r.course_code)}-${escapeHtml(r.section)}</p>
        <p class="text-xs text-muted truncate max-w-[240px]">${escapeHtml(r.title)}</p></div>` },
    ...(isAdmin ? [{ key: 'teacher_name', label: 'Teacher', sortable: true }] : []),
    { key: 'semester_code', label: 'Semester', sortable: true },
    { key: 'fill_percent', label: 'Seats', sortable: true, render: (r) => `
        <div class="min-w-[150px]">
          <div class="flex justify-between text-xs mb-1"><span class="tabular-nums text-ink">${r.enrolled_count}/${r.capacity}</span>
          <span class="tabular-nums ${r.fill_percent >= 100 ? 'text-danger font-medium' : 'text-muted'}">${formatPercent(r.fill_percent, 0)}</span></div>
          ${progressBar(r.fill_percent)}
        </div>` },
    { key: 'schedule_count', label: 'Schedule', render: (r) => (r.schedule_count ? badge('info', `${r.schedule_count} slots/week`) : badge('pending', 'TBA')) },
    { key: 'status', label: 'Status', sortable: true, render: (r) => badge(r.status) },
    { key: 'actions', label: '', className: 'text-right whitespace-nowrap', render: () =>
      rowAction('roster', 'users', 'Roster') + (isAdmin ? rowAction('schedule', 'calendar-clock', 'Schedule') + rowAction('edit', 'pencil', 'Edit') : '') },
  ];

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/offerings',
    searchPlaceholder: 'Search course or teacher…',
    defaultSort: 'course_code',
    initialFilters: { semester_id: active ? active.id : '' },
    filters: [
      { name: 'semester_id', label: 'Semester', options: semesterOptions },
      ...(isAdmin ? [{ name: 'department_id', label: 'Department', options: toOptions(departments, (d) => d.code) }] : []),
      { name: 'status', label: 'Status', options: ['open', 'closed', 'cancelled'].map((s) => ({ value: s, label: titleCase(s) })) },
    ],
    toolbarHtml: isAdmin ? `<button type="button" id="new-offering" class="${btnClass('primary')}">${icon('plus', 16)} New offering</button>` : '',
    emptyIcon: 'layers',
    emptyTitle: 'No offerings found',
    columns,
    onRowClick: (row) => openRoster(row),
    onAction: (action, row) => {
      if (action === 'roster') openRoster(row);
      if (action === 'schedule') openScheduleManager(row, list);
      if (action === 'edit') openOfferingForm(row, list, semesterOptions, active);
    },
  });

  document.getElementById('new-offering')?.addEventListener('click', () => openOfferingForm(null, list, semesterOptions, active));
}

/** Create or edit an offering (admin). */
async function openOfferingForm(offering, list, semesterOptions, active) {
  const isEdit = Boolean(offering);
  let courses = [];
  let teachers = [];
  try {
    const [courseData, teacherData] = await Promise.all([
      isEdit ? Promise.resolve({ items: [] }) : api.get('/courses', { limit: 200, is_active: true, sort: 'code' }),
      api.get('/teachers', { limit: 200, status: 'active', sort: 'full_name' }),
    ]);
    courses = courseData.items;
    teachers = teacherData.items;
  } catch {
    return;
  }
  const teacherOptions = toOptions(teachers, (t) => `${t.full_name} (${t.department_code})`);

  formModal({
    title: isEdit ? `Edit ${offering.course_code}-${offering.section}` : 'New offering',
    submitText: isEdit ? 'Save changes' : 'Create offering',
    fieldsHtml: `
      ${isEdit ? '' : field({ name: 'course_id', label: 'Course', type: 'select', number: true, required: true, options: toOptions(courses, (c) => `${c.code} · ${c.title}`) })}
      ${isEdit ? '' : field({ name: 'semester_id', label: 'Semester', type: 'select', number: true, required: true, value: active?.id, options: semesterOptions })}
      ${field({ name: 'teacher_id', label: 'Teacher', type: 'select', number: true, required: true, value: offering?.teacher_id, options: teacherOptions, help: 'Only active teachers can be assigned' })}
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-4">
        ${field({ name: 'section', label: 'Section', required: true, pattern: '[A-Z]{1,3}', title: '1–3 capital letters', value: offering?.section || 'A' })}
        ${field({ name: 'capacity', label: 'Capacity', type: 'number', required: true, min: 1, max: 500, step: 1, value: offering?.capacity ?? 40,
                  help: isEdit ? `${offering.enrolled_count} enrolled now` : '' })}
        ${field({ name: 'status', label: 'Status', type: 'select', noEmpty: true, value: offering?.status || 'open', options: ['open', 'closed', 'cancelled'].map((s) => ({ value: s, label: titleCase(s) })) })}
      </div>`,
    onSubmit: async (values) => {
      if (isEdit && values.status === 'cancelled' && offering.status !== 'cancelled') {
        const ok = await confirmDialog({ title: 'Cancel this offering?', message: 'Students can no longer enroll, and the offering is removed from the routine.', confirmText: 'Cancel offering' });
        if (!ok) throw new Error('cancelled');
      }
      return isEdit ? api.patch(`/offerings/${offering.id}`, values) : api.post('/offerings', values);
    },
    onSuccess: (saved) => { toast(`${saved.course_code}-${saved.section} ${isEdit ? 'updated' : 'created'}`); list.reload(); },
  });
}

/** Weekly slots of an offering: list + delete + add. Conflicts come back from the DB triggers. */
async function openScheduleManager(offering, list) {
  const modal = openModal({ title: `Schedule · ${offering.course_code}-${offering.section}`, size: 'max-w-2xl', body: skeletonTable(3, 4) });
  let rooms = [];
  try {
    rooms = (await api.get('/rooms', { limit: 200, sort: 'building' }, { silent: true })).items;
  } catch (error) {
    showError(modal.body, error, () => { modal.close(); openScheduleManager(offering, list); });
    return;
  }
  const roomOptions = toOptions(rooms, (r) => `${r.building} ${r.room_number} · ${titleCase(r.room_type)} · ${r.capacity} seats`);

  async function render() {
    const detail = await api.get(`/offerings/${offering.id}`, null, { silent: true });
    const slots = detail.schedules.length
      ? detail.schedules.map((s) => `
          <div class="flex items-center gap-3 h-12 px-3 border-b border-line last:border-0">
            <span class="w-24 text-sm font-medium text-ink">${s.day_name}</span>
            <span class="text-sm tabular-nums">${s.start_time}–${s.end_time}</span>
            <span class="text-xs text-muted truncate flex-1">${escapeHtml(s.building)} ${escapeHtml(s.room_number)}</span>
            <button type="button" data-delete="${s.id}" class="${btnClass('ghost', 'icon-sm')} text-danger" title="Remove slot">${icon('trash-2', 16)}</button>
          </div>`).join('')
      : `<p class="text-xs text-muted p-4 text-center">No weekly slots yet (shown as "TBA").</p>`;

    modal.body.innerHTML = `
      <p class="text-xs text-muted mb-2">Needs a room with at least <b>${detail.capacity}</b> seats. Two classes cannot share a room, or a teacher, at the same time. The database triggers <code>trg_no_room_conflict</code> and <code>trg_no_teacher_conflict</code> refuse it.</p>
      <div class="border border-line rounded-lg mb-5">${slots}</div>
      <form id="slot-form" novalidate class="rounded-xl border border-line bg-slate-50/60 p-4">
        <p class="text-sm font-semibold text-ink mb-3">Add a weekly slot</p>
        <div data-form-error class="hidden mb-3 rounded-lg bg-red-50 text-danger text-xs px-3 py-2 flex gap-2"></div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'room_id', label: 'Room', type: 'select', number: true, required: true, options: roomOptions, className: 'sm:col-span-2' })}
          ${field({ name: 'day_of_week', label: 'Day', type: 'select', number: true, required: true, noEmpty: true, value: 0, options: DAY_NAMES.map((d, i) => ({ value: i, label: d })) })}
          <div class="grid grid-cols-2 gap-x-3">
            ${field({ name: 'start_time', label: 'Start', type: 'time', required: true, value: '09:00', min: '08:00', max: '18:00' })}
            ${field({ name: 'end_time', label: 'End', type: 'time', required: true, value: '10:20', min: '08:00', max: '18:00' })}
          </div>
        </div>
        <div class="flex justify-end"><button type="submit" class="${btnClass('primary')}">${icon('plus', 16)} Add slot</button></div>
      </form>`;
    refreshIcons();

    modal.body.querySelectorAll('[data-delete]').forEach((button) => button.addEventListener('click', async () => {
      const ok = await confirmDialog({ title: 'Remove this slot?', message: 'The class will disappear from the weekly routine.', confirmText: 'Remove' });
      if (!ok) return;
      await api.del(`/schedules/${button.dataset.delete}`);
      toast('Slot removed');
      render();
      list.reload();
    }));

    const form = modal.body.querySelector('#slot-form');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const valid = validateForm(form, (v) => (v.start_time && v.end_time && v.end_time <= v.start_time ? { end_time: 'Must be after the start time' } : {}));
      if (!valid) return;
      const button = form.querySelector('[type=submit]');
      setBusy(button, true);
      try {
        await api.post(`/offerings/${offering.id}/schedules`, getFormValues(form), { silent: true });
        toast('Slot added');
        render();
        list.reload();
      } catch (error) {
        setBusy(button, false);
        // A clash (409 from a trigger) is shown right inside the form
        if (error instanceof ApiError) setFormErrors(form, error.errors, error.message);
      }
    });
  }

  try {
    await render();
  } catch (error) {
    showError(modal.body, error, render);
  }
}

/** Students of an offering with attendance and grade. */
async function openRoster(offering) {
  const modal = openModal({ title: `Roster · ${offering.course_code}-${offering.section}`, size: 'max-w-3xl', body: skeletonTable(8, 5) });
  try {
    const data = await api.get(`/offerings/${offering.id}/roster`, null, { silent: true });
    modal.body.innerHTML = data.items.length ? `
      <div class="flex flex-wrap gap-2 mb-3 text-xs text-muted">
        <span>${data.items.filter((s) => s.status === 'enrolled').length} enrolled</span>·
        <span>${data.items.filter((s) => s.status === 'completed').length} completed</span>·
        <span>${data.items.filter((s) => s.status === 'dropped').length} dropped</span>
        <button type="button" id="roster-csv" class="${btnClass('ghost', 'sm')} ml-auto -my-1">${icon('download', 14)} CSV</button>
      </div>
      <div class="border border-line rounded-lg overflow-hidden">${renderTable({
        columns: [
          { key: 'student_code', label: 'Code', className: 'font-medium text-ink' },
          { key: 'full_name', label: 'Name' },
          { key: 'status', label: 'Status', render: (r) => badge(r.status) },
          { key: 'attendance_percent', label: 'Attendance', className: 'tabular-nums', render: (r) => (r.attendance_percent === null ? '—'
            : `<span class="${r.attendance_percent < 75 ? 'text-danger font-medium' : ''}">${formatPercent(r.attendance_percent)}</span>`) },
          { key: 'letter_grade', label: 'Grade', render: (r) => escapeHtml(r.letter_grade || '—') },
        ],
        rows: data.items,
      })}</div>` : emptyState({ iconName: 'users', title: 'No students enrolled yet' });
    refreshIcons();
    modal.body.querySelector('#roster-csv')?.addEventListener('click', () => downloadCSV(`roster-${offering.course_code}-${offering.section}.csv`, data.items, [
      { key: 'student_code', label: 'Code' }, { key: 'full_name', label: 'Name' }, { key: 'email', label: 'Email' },
      { key: 'status', label: 'Status' }, { key: 'attendance_percent', label: 'Attendance %' }, { key: 'letter_grade', label: 'Grade' },
    ]));
  } catch (error) {
    showError(modal.body, error, () => { modal.close(); openRoster(offering); });
  }
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('offerings', 'Offerings');
if (session) initOfferings(session);
