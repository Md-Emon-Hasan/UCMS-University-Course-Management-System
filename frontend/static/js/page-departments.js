/*
 * page-departments.js: department table + create/edit modal (admin).
 */

function initDepartments({ content }) {
  content.innerHTML = pageHeader('Departments', 'Academic departments, their heads and their size.') + '<div id="list"></div>';

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/departments',
    searchPlaceholder: 'Search name, code or head…',
    defaultSort: 'code',
    filters: [{ name: 'is_active', label: 'Status', options: [{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }] }],
    toolbarHtml: `<button type="button" id="new-department" class="${btnClass('primary')}">${icon('plus', 16)} New department</button>`,
    emptyIcon: 'building-2',
    emptyTitle: 'No departments yet',
    columns: [
      { key: 'code', label: 'Code', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.code)}</span>` },
      { key: 'name', label: 'Name', sortable: true },
      { key: 'head_teacher_name', label: 'Head', render: (r) => (r.head_teacher_name ? escapeHtml(r.head_teacher_name) : '<span class="text-muted">Not set</span>') },
      { key: 'student_count', label: 'Students', sortable: true, className: 'tabular-nums' },
      { key: 'teacher_count', label: 'Teachers', sortable: true, className: 'tabular-nums' },
      { key: 'course_count', label: 'Courses', sortable: true, className: 'tabular-nums' },
      { key: 'is_active', label: 'Status', render: (r) => badge(r.is_active ? 'active' : 'inactive') },
      { key: 'actions', label: '', className: 'text-right', render: () => rowAction('edit', 'pencil', 'Edit') },
    ],
    onRowClick: (row) => openDepartmentForm(row),
    onAction: (action, row) => openDepartmentForm(row),
  });

  document.getElementById('new-department').addEventListener('click', () => openDepartmentForm(null));

  /** Create (department = null) or edit a department. */
  async function openDepartmentForm(department) {
    const isEdit = Boolean(department);
    let headOptions = [];
    if (isEdit) {
      // The head must be a teacher OF this department
      const teachers = await api.get('/teachers', { department_id: department.id, status: 'active', limit: 100 });
      headOptions = toOptions(teachers.items, (t) => `${t.full_name} (${titleCase(t.designation)})`);
    }

    const fieldsHtml = `
      ${field({ name: 'name', label: 'Name', required: true, minlength: 2, maxlength: 100, value: department?.name, placeholder: 'Computer Science and Engineering' })}
      ${field({ name: 'code', label: 'Code', required: true, pattern: '[A-Z]{2,6}', title: '2 to 6 capital letters, e.g. CSE',
                value: department?.code, placeholder: 'CSE', help: '2–6 capital letters' })}
      ${isEdit ? field({ name: 'head_teacher_id', label: 'Head of department', type: 'select', number: true,
                         value: department.head_teacher_id, options: headOptions, emptyLabel: 'No head' }) : ''}
      ${isEdit ? field({ name: 'is_active', label: 'Department is active', type: 'checkbox', value: department.is_active }) : ''}`;

    formModal({
      title: isEdit ? `Edit ${department.code}` : 'New department',
      submitText: isEdit ? 'Save changes' : 'Create department',
      fieldsHtml,
      onSubmit: async (values) => {
        if (isEdit && department.is_active && !values.is_active) {
          const ok = await confirmDialog({ title: 'Deactivate department?', message: `${department.name} will be marked inactive.`, confirmText: 'Deactivate' });
          if (!ok) throw new Error('cancelled');
        }
        return isEdit ? api.patch(`/departments/${department.id}`, values) : api.post('/departments', values);
      },
      onSuccess: (saved) => {
        toast(isEdit ? `${saved.code} updated` : `${saved.code} created`);
        dataCache.departments = null;
        list.reload();
      },
    });
  }
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('departments', 'Departments');
if (session) initDepartments(session);
