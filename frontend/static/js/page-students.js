/*
 * page-students.js: student table with filters, and a 2-step "new student"
 * form (step 1 account, step 2 profile). All three rows (users, students,
 * student_profiles) are created in ONE database transaction by the API.
 */

const STUDENT_STATUSES = ['active', 'suspended', 'graduated', 'dropped_out'];

async function initStudents({ content }) {
  content.innerHTML = pageHeader('Students', 'All students. Click a row to open the full record.') + `<div id="list">${card(skeletonTable(8, 6), 'p-0')}</div>`;

  let departments = [];
  try {
    departments = await loadDepartments();
  } catch (error) {
    showError(document.getElementById('list'), error, () => initStudents({ content }));
    return;
  }
  const departmentOptions = toOptions(departments, (d) => d.code);

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/students',
    searchPlaceholder: 'Search name, code or email…',
    defaultSort: 'student_code',
    filters: [
      { name: 'department_id', label: 'Department', options: departmentOptions },
      { name: 'status', label: 'Status', options: STUDENT_STATUSES.map((s) => ({ value: s, label: titleCase(s) })) },
    ],
    toolbarHtml: `<button type="button" id="new-student" class="${btnClass('primary')}">${icon('plus', 16)} New student</button>`,
    emptyIcon: 'graduation-cap',
    columns: [
      { key: 'student_code', label: 'Code', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.student_code)}</span>` },
      { key: 'full_name', label: 'Name', sortable: true, render: (r) => `
          <div class="min-w-[160px]"><p class="font-medium text-ink">${escapeHtml(r.full_name)}</p><p class="text-xs text-muted">${escapeHtml(r.email)}</p></div>` },
      { key: 'department_code', label: 'Dept', sortable: true },
      { key: 'admission_date', label: 'Admitted', sortable: true, render: (r) => formatDate(r.admission_date), className: 'whitespace-nowrap' },
      { key: 'cgpa', label: 'CGPA', sortable: true, className: 'tabular-nums', render: (r) => (r.cgpa === null ? '<span class="text-muted">—</span>' : Number(r.cgpa).toFixed(2)) },
      { key: 'status', label: 'Status', sortable: true, render: (r) => badge(r.status) },
      { key: 'go', label: '', className: 'text-right text-slate-300', render: () => icon('chevron-right', 16) },
    ],
    onRowClick: (row) => { window.location.href = `/pages/student-detail.html?id=${row.id}`; },
  });

  document.getElementById('new-student').addEventListener('click', () => openNewStudentForm(departmentOptions, list));
}

/** Two-step modal: Account -> Profile, then one POST /api/students. */
function openNewStudentForm(departmentOptions, list) {
  const formId = 'new-student-form';
  const stepDot = (n, label) => `
    <div class="flex items-center gap-2" data-step-dot="${n}">
      <span class="w-6 h-6 rounded-full text-xs font-semibold flex items-center justify-center">${n}</span>
      <span class="text-xs font-medium">${label}</span>
    </div>`;

  const modal = openModal({
    title: 'New student',
    size: 'max-w-2xl',
    body: `
      <div class="flex items-center gap-3 mb-5">${stepDot(1, 'Account')}<div class="h-px flex-1 bg-line"></div>${stepDot(2, 'Profile')}</div>
      <form id="${formId}" novalidate>
        <div data-form-error class="hidden mb-4 rounded-lg bg-red-50 text-danger text-xs px-3 py-2"></div>
        <div data-step="1" class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'email', label: 'Email (login)', type: 'email', required: true, placeholder: 'student@student.ucms.edu' })}
          ${field({ name: 'password', label: 'Password', type: 'password', required: true, minlength: 8, help: 'At least 8 characters' })}
          ${field({ name: 'first_name', label: 'First name', required: true, maxlength: 80 })}
          ${field({ name: 'last_name', label: 'Last name', required: true, maxlength: 80 })}
          ${field({ name: 'student_code', label: 'Student code', required: true, pattern: '[A-Z0-9\\-]{4,20}', title: '4–20 capital letters or digits, e.g. CSE26061', placeholder: 'CSE26061' })}
          ${field({ name: 'department_id', label: 'Department', type: 'select', number: true, required: true, options: departmentOptions })}
          ${field({ name: 'admission_date', label: 'Admission date', type: 'date', required: true, value: todayISO() })}
          ${field({ name: 'status', label: 'Status', type: 'select', noEmpty: true, value: 'active', options: STUDENT_STATUSES.map((s) => ({ value: s, label: titleCase(s) })) })}
        </div>
        <div data-step="2" class="hidden grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'profile.date_of_birth', label: 'Date of birth', type: 'date', required: true, max: todayISO() })}
          ${field({ name: 'profile.gender', label: 'Gender', type: 'select', required: true, options: ['male', 'female', 'other'].map((g) => ({ value: g, label: titleCase(g) })) })}
          ${field({ name: 'profile.blood_group', label: 'Blood group', type: 'select', emptyLabel: 'Unknown', options: ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'].map((b) => ({ value: b, label: b })) })}
          ${field({ name: 'profile.city', label: 'City', maxlength: 60, placeholder: 'Dhaka' })}
          ${field({ name: 'profile.address_line', label: 'Address', maxlength: 200, className: 'sm:col-span-2', placeholder: 'House 12, Road 5, Dhanmondi' })}
          ${field({ name: 'profile.postal_code', label: 'Postal code', pattern: '[0-9]{4}', title: '4 digits', placeholder: '1209' })}
          ${field({ name: 'profile.guardian_relation', label: 'Guardian relation', required: true, minlength: 2, placeholder: 'Father' })}
          ${field({ name: 'profile.guardian_name', label: 'Guardian name', required: true, maxlength: 80 })}
          ${field({ name: 'profile.guardian_phone', label: 'Guardian phone', type: 'tel', required: true, pattern: '\\+?[0-9]{7,15}', title: '7–15 digits', placeholder: '01712345678' })}
        </div>
      </form>`,
    footer: `
      <button type="button" data-back class="${btnClass('secondary')}">Cancel</button>
      <button type="button" data-next class="${btnClass('primary')}">Next ${icon('chevron-right', 16)}</button>
      <button type="submit" form="${formId}" data-submit class="${btnClass('primary')} hidden">Create student</button>`,
  });

  const form = modal.root.querySelector('form');
  const backButton = modal.root.querySelector('[data-back]');
  const nextButton = modal.root.querySelector('[data-next]');
  const submitButton = modal.root.querySelector('[data-submit]');
  let step = 1;

  function showStep(n) {
    step = n;
    modal.root.querySelectorAll('[data-step]').forEach((el) => {
      const visible = Number(el.dataset.step) === n;
      el.classList.toggle('hidden', !visible);
      el.classList.toggle('grid', visible);
    });
    modal.root.querySelectorAll('[data-step-dot]').forEach((dot) => {
      const active = Number(dot.dataset.stepDot) <= n;
      dot.querySelector('span').className = `w-6 h-6 rounded-full text-xs font-semibold flex items-center justify-center ${active ? 'bg-primary-600 text-white' : 'bg-slate-100 text-muted'}`;
      dot.querySelector('span + span').className = `text-xs font-medium ${active ? 'text-ink' : 'text-muted'}`;
    });
    backButton.textContent = n === 1 ? 'Cancel' : 'Back';
    nextButton.classList.toggle('hidden', n !== 1);
    submitButton.classList.toggle('hidden', n !== 2);
    modal.root.querySelector(`[data-step="${n}"] input, [data-step="${n}"] select`)?.focus();
  }
  showStep(1);

  backButton.addEventListener('click', () => (step === 1 ? modal.close() : showStep(1)));
  // validateForm() only checks VISIBLE fields, so this validates step 1 only
  nextButton.addEventListener('click', () => { if (validateForm(form)) showStep(2); });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (step === 1) { if (validateForm(form)) showStep(2); return; }     // Enter on step 1 = Next
    if (!validateForm(form)) return;
    setBusy(submitButton, true, 'Creating…');
    try {
      const student = await api.post('/students', getFormValues(form));
      modal.close();
      toast(`${student.full_name} created`);
      list.reload();
    } catch (error) {
      setBusy(submitButton, false);
      if (!(error instanceof ApiError)) return;
      // An error in an account field? Go back to step 1 so the user can see it.
      const accountError = Object.keys(error.errors).some((name) => !name.startsWith('profile.'));
      if (accountError) showStep(1);
      setFormErrors(form, error.errors, error.message);
    }
  });
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('students', 'Students');
if (session) initStudents(session);
