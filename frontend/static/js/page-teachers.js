/*
 * page-teachers.js: teacher table with filters, create/edit modal, and a
 * detail drawer showing the workload (from the v_teacher_workload view).
 */

const DESIGNATIONS = ['lecturer', 'assistant_professor', 'associate_professor', 'professor'];
const TEACHER_STATUSES = ['active', 'on_leave', 'resigned'];

async function initTeachers({ content }) {
  content.innerHTML = pageHeader('Teachers', 'Faculty members, their departments and workload.') + `<div id="list">${card(skeletonTable(8, 6), 'p-0')}</div>`;

  let departments = [];
  try {
    departments = await loadDepartments();
  } catch (error) {
    showError(document.getElementById('list'), error, () => initTeachers({ content }));
    return;
  }
  const departmentOptions = toOptions(departments, (d) => d.code);

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/teachers',
    searchPlaceholder: 'Search name, code or email…',
    defaultSort: 'full_name',
    filters: [
      { name: 'department_id', label: 'Department', options: departmentOptions },
      { name: 'status', label: 'Status', options: TEACHER_STATUSES.map((s) => ({ value: s, label: titleCase(s) })) },
    ],
    toolbarHtml: `<button type="button" id="new-teacher" class="${btnClass('primary')}">${icon('plus', 16)} New teacher</button>`,
    emptyIcon: 'users',
    columns: [
      { key: 'employee_code', label: 'Code', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.employee_code)}</span>` },
      { key: 'full_name', label: 'Name', sortable: true, render: (r) => `
          <div class="min-w-[160px]"><p class="font-medium text-ink">${escapeHtml(r.full_name)} ${r.is_head ? badge('info', 'Head') : ''}</p>
          <p class="text-xs text-muted">${escapeHtml(r.email)}</p></div>` },
      { key: 'department_code', label: 'Dept', sortable: true },
      { key: 'designation', label: 'Designation', sortable: true, render: (r) => escapeHtml(titleCase(r.designation)) },
      { key: 'hired_at', label: 'Hired', sortable: true, render: (r) => formatDate(r.hired_at), className: 'whitespace-nowrap' },
      { key: 'status', label: 'Status', sortable: true, render: (r) => badge(r.status) },
      { key: 'actions', label: '', className: 'text-right', render: () => rowAction('edit', 'pencil', 'Edit') },
    ],
    onRowClick: (row) => openTeacherDrawer(row),
    onAction: (action, row) => openTeacherForm(row),
  });

  document.getElementById('new-teacher').addEventListener('click', () => openTeacherForm(null));

  /** Create or edit a teacher (create also makes the login account). */
  function openTeacherForm(teacher) {
    const isEdit = Boolean(teacher);
    const fieldsHtml = `
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
        ${isEdit ? '' : field({ name: 'email', label: 'Email (login)', type: 'email', required: true, placeholder: 'name@ucms.edu' })}
        ${isEdit ? '' : field({ name: 'password', label: 'Password', type: 'password', required: true, minlength: 8, help: 'At least 8 characters' })}
        ${field({ name: 'first_name', label: 'First name', required: true, maxlength: 80, value: teacher?.first_name })}
        ${field({ name: 'last_name', label: 'Last name', required: true, maxlength: 80, value: teacher?.last_name })}
        ${isEdit ? '' : field({ name: 'employee_code', label: 'Employee code', required: true, pattern: '[A-Z0-9\\-]{3,20}', title: '3–20 capital letters, digits or dashes', placeholder: 'EMP031' })}
        ${field({ name: 'department_id', label: 'Department', type: 'select', number: true, required: true, value: teacher?.department_id, options: departmentOptions })}
        ${field({ name: 'designation', label: 'Designation', type: 'select', required: true, value: teacher?.designation, options: DESIGNATIONS.map((d) => ({ value: d, label: titleCase(d) })) })}
        ${field({ name: 'hired_at', label: 'Hired on', type: 'date', required: true, value: teacher?.hired_at, max: todayISO() })}
        ${field({ name: 'phone', label: 'Phone', type: 'tel', pattern: '\\+?[0-9]{7,15}', title: '7–15 digits, e.g. 01712345678', value: teacher?.phone, placeholder: '01712345678' })}
        ${field({ name: 'status', label: 'Status', type: 'select', noEmpty: true, value: teacher?.status || 'active', options: TEACHER_STATUSES.map((s) => ({ value: s, label: titleCase(s) })) })}
      </div>
      ${isEdit ? field({ name: 'is_active', label: 'Login account enabled', type: 'checkbox', value: teacher.is_active }) : ''}`;

    formModal({
      title: isEdit ? `Edit ${teacher.full_name}` : 'New teacher',
      submitText: isEdit ? 'Save changes' : 'Create teacher',
      size: 'max-w-2xl',
      fieldsHtml,
      onSubmit: async (values) => {
        if (isEdit) {
          const resigning = values.status === 'resigned' && teacher.status !== 'resigned';
          const disabling = teacher.is_active && values.is_active === false;
          if (resigning || disabling) {
            const ok = await confirmDialog({
              title: resigning ? 'Mark as resigned?' : 'Disable login?',
              message: `${teacher.full_name} ${resigning ? 'can no longer be assigned to new offerings.' : 'will not be able to log in.'}`,
              confirmText: 'Yes, continue',
            });
            if (!ok) throw new Error('cancelled');
          }
          return api.patch(`/teachers/${teacher.id}`, values);
        }
        return api.post('/teachers', values);
      },
      onSuccess: (saved) => { toast(`${saved.full_name} ${isEdit ? 'updated' : 'created'}`); list.reload(); },
    });
  }
}

/** Slide-over with the teacher's profile and workload per semester. */
async function openTeacherDrawer(teacher) {
  const drawer = openDrawer({ title: teacher.full_name, body: `<div class="space-y-4">${skeletonBlock('h-24 w-full')}${skeletonTable(4, 4)}</div>` });
  try {
    const data = await api.get(`/teachers/${teacher.id}/workload`, null, { silent: true });
    const t = data.teacher;
    const current = data.current_offerings.length
      ? data.current_offerings.map((o) => `
          <div class="py-3 border-b border-line last:border-0">
            <div class="flex items-center justify-between gap-2">
              <p class="text-sm font-medium text-ink">${escapeHtml(o.course_code)}-${escapeHtml(o.section)} <span class="font-normal text-muted">${escapeHtml(o.title)}</span></p>
              ${badge(o.status)}
            </div>
            <div class="flex items-center gap-3 mt-2">
              <div class="flex-1">${progressBar(o.fill_percent)}</div>
              <span class="text-xs text-muted tabular-nums whitespace-nowrap">${o.enrolled_count}/${o.capacity} · ${o.credits} cr</span>
            </div>
          </div>`).join('')
      : emptyState({ iconName: 'layers', title: 'No offerings this semester' });

    const history = data.per_semester.length
      ? renderTable({
        columns: [
          { key: 'semester_code', label: 'Semester' },
          { key: 'course_count', label: 'Courses', className: 'tabular-nums' },
          { key: 'total_credits', label: 'Credits', className: 'tabular-nums' },
          { key: 'total_students', label: 'Students', className: 'tabular-nums' },
        ],
        rows: data.per_semester,
      })
      : emptyState({ iconName: 'history', title: 'No teaching history' });

    drawer.body.innerHTML = `
      <div class="flex items-center gap-3 mb-5">
        <div class="w-12 h-12 rounded-full bg-primary-600 text-white font-semibold flex items-center justify-center">${escapeHtml(initials(t.full_name))}</div>
        <div><p class="font-semibold text-ink">${escapeHtml(t.full_name)}</p>
        <p class="text-xs text-muted">${escapeHtml(titleCase(t.designation))} · ${escapeHtml(t.department_name)}</p></div>
        <div class="ml-auto">${badge(t.status)}</div>
      </div>
      ${card(definitionList([
        ['Employee code', escapeHtml(t.employee_code)], ['Email', escapeHtml(t.email)],
        ['Phone', escapeHtml(t.phone)], ['Hired', formatDate(t.hired_at)],
        ['Login', t.is_active ? badge('active', 'Enabled') : badge('inactive', 'Disabled')],
        ['Last login', formatDateTime(t.last_login_at)],
      ]))}
      <div class="mt-4">${card(cardTitle('This semester') + current)}</div>
      <div class="mt-4 bg-white rounded-xl border border-line shadow-sm overflow-hidden">
        <div class="px-5 pt-5">${cardTitle('Workload per semester', '<span class="text-xs text-muted">from v_teacher_workload</span>')}</div>
        ${history}
      </div>`;
    refreshIcons();
  } catch (error) {
    showError(drawer.body, error, () => { drawer.close(); openTeacherDrawer(teacher); });
  }
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('teachers', 'Teachers');
if (session) initTeachers(session);
