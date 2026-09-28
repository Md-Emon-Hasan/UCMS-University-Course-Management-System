/*
 * page-courses.js: course catalogue. Admins can create/edit courses and
 * manage prerequisites (a multi-select). Everyone can open the prerequisite tree.
 */

async function initCourses({ user, content }) {
  const isAdmin = user.role === 'admin';
  content.innerHTML = pageHeader('Courses', 'The course catalogue with credits, levels and prerequisites.') + `<div id="list">${card(skeletonTable(8, 6), 'p-0')}</div>`;

  let departments = [];
  try {
    departments = await loadDepartments();
  } catch (error) {
    showError(document.getElementById('list'), error, () => initCourses({ user, content }));
    return;
  }
  const departmentOptions = toOptions(departments, (d) => d.code);

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/courses',
    searchPlaceholder: 'Search code or title…',
    defaultSort: 'code',
    filters: [
      { name: 'department_id', label: 'Department', options: departmentOptions },
      { name: 'level', label: 'Level', options: [1, 2, 3, 4].map((l) => ({ value: l, label: `Level ${l}` })) },
    ],
    toolbarHtml: isAdmin ? `<button type="button" id="new-course" class="${btnClass('primary')}">${icon('plus', 16)} New course</button>` : '',
    emptyIcon: 'book-open',
    columns: [
      { key: 'code', label: 'Code', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.code)}</span>` },
      { key: 'title', label: 'Title', sortable: true, render: (r) => `<p class="text-ink min-w-[180px]">${escapeHtml(r.title)}</p>` },
      { key: 'department_code', label: 'Dept', sortable: true },
      { key: 'level', label: 'Level', sortable: true, className: 'tabular-nums' },
      { key: 'credits', label: 'Credits', sortable: true, className: 'tabular-nums' },
      { key: 'prerequisite_codes', label: 'Prerequisites', render: (r) => (r.prerequisite_codes
        ? r.prerequisite_codes.split(', ').map((code) => `<span class="inline-block mr-1 mb-1">${badge('completed', code)}</span>`).join('')
        : '<span class="text-muted text-xs">None</span>') },
      { key: 'is_active', label: 'Status', render: (r) => badge(r.is_active ? 'active' : 'inactive') },
      { key: 'actions', label: '', className: 'text-right whitespace-nowrap', render: () =>
        rowAction('tree', 'git-fork', 'Prerequisite tree') + (isAdmin ? rowAction('prereqs', 'network', 'Manage prerequisites') + rowAction('edit', 'pencil', 'Edit') : '') },
    ],
    onRowClick: (row) => (isAdmin ? openCourseForm(row) : goToTree(row)),
    onAction: (action, row) => {
      if (action === 'tree') goToTree(row);
      if (action === 'prereqs') openPrerequisiteManager(row, list);
      if (action === 'edit') openCourseForm(row);
    },
  });

  document.getElementById('new-course')?.addEventListener('click', () => openCourseForm(null));

  function goToTree(course) {
    window.location.href = `/pages/course-tree.html?id=${course.id}`;
  }

  function openCourseForm(course) {
    const isEdit = Boolean(course);
    formModal({
      title: isEdit ? `Edit ${course.code}` : 'New course',
      submitText: isEdit ? 'Save changes' : 'Create course',
      fieldsHtml: `
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'code', label: 'Code', required: true, pattern: '[A-Z]{2,6}[0-9]{3}', title: 'Letters then 3 digits, e.g. CSE404', value: course?.code, placeholder: 'CSE404' })}
          ${field({ name: 'department_id', label: 'Department', type: 'select', number: true, required: true, value: course?.department_id, options: departmentOptions })}
        </div>
        ${field({ name: 'title', label: 'Title', required: true, minlength: 2, maxlength: 120, value: course?.title })}
        ${field({ name: 'description', label: 'Description', type: 'textarea', maxlength: 1000, value: course?.description })}
        <div class="grid grid-cols-2 gap-x-4">
          ${field({ name: 'credits', label: 'Credits', type: 'number', required: true, min: 0.5, max: 6, step: 0.5, value: course?.credits ?? 3 })}
          ${field({ name: 'level', label: 'Level', type: 'select', number: true, required: true, noEmpty: true, value: course?.level ?? 1, options: [1, 2, 3, 4].map((l) => ({ value: l, label: `Level ${l}` })) })}
        </div>
        ${isEdit ? field({ name: 'is_active', label: 'Course is active (can be offered)', type: 'checkbox', value: course.is_active }) : ''}`,
      onSubmit: async (values) => {
        if (isEdit && course.is_active && !values.is_active) {
          const ok = await confirmDialog({ title: 'Deactivate course?', message: `${course.code} can no longer be offered in new semesters.`, confirmText: 'Deactivate' });
          if (!ok) throw new Error('cancelled');
        }
        return isEdit ? api.patch(`/courses/${course.id}`, values) : api.post('/courses', values);
      },
      onSuccess: (saved) => { toast(`${saved.code} ${isEdit ? 'updated' : 'created'}`); list.reload(); },
    });
  }
}

/**
 * Multi-select of prerequisites. The whole selection is saved at once. The API
 * rejects a selection that would create a cycle (checked with a recursive CTE).
 */
async function openPrerequisiteManager(course, list) {
  const modal = openModal({ title: `Prerequisites of ${course.code}`, size: 'max-w-xl', body: skeletonTable(6, 2) });
  let allCourses = [];
  let selected = new Set();
  try {
    const [catalogue, detail] = await Promise.all([
      api.get('/courses', { limit: 200, sort: 'code' }, { silent: true }),
      api.get(`/courses/${course.id}`, null, { silent: true }),
    ]);
    allCourses = catalogue.items.filter((c) => c.id !== course.id);
    selected = new Set(detail.prerequisites.map((p) => p.id));
  } catch (error) {
    showError(modal.body, error, () => { modal.close(); openPrerequisiteManager(course, list); });
    return;
  }

  modal.body.innerHTML = `
    <form id="prereq-form" novalidate>
      <div data-form-error class="hidden mb-3 rounded-lg bg-red-50 text-danger text-xs px-3 py-2"></div>
      <p class="text-xs text-muted mb-3">A student must pass every selected course (grade point ≥ 2.00) before enrolling in ${escapeHtml(course.code)}.</p>
      <div id="chips" class="flex flex-wrap gap-1.5 mb-3 min-h-6"></div>
      <div class="relative mb-2">
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">${icon('search', 16)}</span>
        <input type="search" id="prereq-search" data-skip placeholder="Filter courses…" class="${INPUT_CLASS} pl-9">
      </div>
      <div id="prereq-options" class="max-h-72 overflow-y-auto thin-scroll border border-line rounded-lg divide-y divide-line"></div>
    </form>`;
  const footer = document.createElement('div');
  footer.className = 'h-16 px-5 border-t border-line flex items-center justify-end gap-2';
  footer.innerHTML = `<button type="button" data-cancel class="${btnClass('secondary')}">Cancel</button>
    <button type="submit" form="prereq-form" class="${btnClass('primary')}">${icon('save', 16)} Save prerequisites</button>`;
  modal.body.after(footer);
  footer.querySelector('[data-cancel]').addEventListener('click', () => modal.close());
  refreshIcons();

  const form = modal.root.querySelector('#prereq-form');
  const optionsBox = modal.root.querySelector('#prereq-options');

  function renderChips() {
    const chips = allCourses.filter((c) => selected.has(c.id));
    modal.root.querySelector('#chips').innerHTML = chips.length
      ? chips.map((c) => `<span class="inline-flex items-center gap-1 h-6 pl-2 pr-1 rounded-full bg-primary-50 text-primary-700 text-xs font-medium">${escapeHtml(c.code)}
          <button type="button" data-unselect="${c.id}" class="rounded-full hover:bg-primary-100 p-0.5" aria-label="Remove">${icon('x', 12)}</button></span>`).join('')
      : '<span class="text-xs text-muted">No prerequisites selected</span>';
    refreshIcons();
  }

  function renderOptions(filterText = '') {
    const text = filterText.toLowerCase();
    const visible = allCourses.filter((c) => !text || `${c.code} ${c.title}`.toLowerCase().includes(text));
    optionsBox.innerHTML = visible.length ? visible.map((c) => `
      <label class="flex items-center gap-3 px-3 h-11 cursor-pointer hover:bg-slate-50">
        <input type="checkbox" data-skip value="${c.id}" ${selected.has(c.id) ? 'checked' : ''} class="h-4 w-4 rounded border-line text-primary-600 focus:ring-primary-500">
        <span class="text-sm font-medium text-ink w-20">${escapeHtml(c.code)}</span>
        <span class="text-sm text-slate-600 truncate flex-1">${escapeHtml(c.title)}</span>
        <span class="text-xs text-muted">L${c.level}</span>
      </label>`).join('') : `<p class="p-4 text-xs text-muted text-center">No matching courses</p>`;
  }

  optionsBox.addEventListener('change', (event) => {
    const id = Number(event.target.value);
    if (event.target.checked) selected.add(id); else selected.delete(id);
    renderChips();
  });
  modal.root.querySelector('#chips').addEventListener('click', (event) => {
    const button = event.target.closest('[data-unselect]');
    if (!button) return;
    selected.delete(Number(button.dataset.unselect));
    renderChips();
    renderOptions(modal.root.querySelector('#prereq-search').value);
  });
  modal.root.querySelector('#prereq-search').addEventListener('input', debounce((e) => renderOptions(e.target.value), 300));
  renderChips();
  renderOptions();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFormErrors(form);
    const button = footer.querySelector('[type=submit]');
    setBusy(button, true);
    try {
      await api.post(`/courses/${course.id}/prerequisites`, { prerequisite_course_ids: [...selected] }, { silent: true });
      modal.close();
      toast(`Prerequisites of ${course.code} saved`);
      list.reload();
    } catch (error) {
      setBusy(button, false);
      if (error instanceof ApiError) setFormErrors(form, {}, error.message);
    }
  });
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('courses', 'Courses');
if (session) initCourses(session);
