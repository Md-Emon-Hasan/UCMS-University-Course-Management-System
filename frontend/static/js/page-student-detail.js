/*
 * page-student-detail.js: one student's full record.
 *   Admin:   /pages/student-detail.html?id=12
 *   Student: /pages/student-detail.html   (always their own record)
 * Tabs: Profile · Enrollments · Attendance · Transcript · Dues
 */

const TABS = [
  { key: 'profile', label: 'Profile' },
  { key: 'enrollments', label: 'Enrollments' },
  { key: 'attendance', label: 'Attendance' },
  { key: 'transcript', label: 'Transcript' },
  { key: 'dues', label: 'Dues' },
];

function initStudentDetail({ user, content }) {
  const isAdmin = user.role === 'admin';
  // A student always sees their own record (the API would answer 403 for anyone else anyway)
  const studentId = isAdmin ? Number(queryParam('id')) : user.student_id;
  if (!studentId) {
    content.innerHTML = card(emptyState({
      iconName: 'user-round', title: 'No student selected',
      actionHtml: `<a href="/pages/students.html" class="${btnClass('secondary')}">Back to students</a>`,
    }));
    refreshIcons();
    return;
  }

  content.innerHTML = `
    ${isAdmin ? `<a href="/pages/students.html" class="inline-flex items-center gap-1 text-xs text-muted hover:text-ink mb-3">${icon('arrow-left', 14)} All students</a>` : ''}
    <div id="header">${card(`<div class="flex items-center gap-4">${skeletonBlock('h-14 w-14 rounded-full')}<div class="flex-1 space-y-2">${skeletonBlock('h-4 w-48')}${skeletonBlock('h-3 w-64')}</div></div>`)}</div>
    <div id="tabs" class="mt-5"></div>
    <div id="tab-body" class="mt-4"></div>`;
  refreshIcons();

  let student = null;
  const initialTab = TABS.some((t) => t.key === location.hash.slice(1)) ? location.hash.slice(1) : 'profile';

  async function loadStudent() {
    try {
      student = await api.get(`/students/${studentId}`, null, { silent: true });
      document.querySelector('header h1').textContent = student.full_name;
      document.title = `${student.full_name} · UCMS`;
      renderHeader();
      renderTabs(document.getElementById('tabs'), TABS, initialTab, showTab);
      showTab(initialTab);
    } catch (error) {
      showError(document.getElementById('header'), error, loadStudent);
    }
  }

  function renderHeader() {
    document.getElementById('header').innerHTML = card(`
      <div class="flex flex-col sm:flex-row sm:items-center gap-4">
        <div class="w-14 h-14 rounded-full bg-primary-600 text-white text-lg font-semibold flex items-center justify-center shrink-0">${escapeHtml(initials(student.full_name))}</div>
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-lg font-semibold tracking-tight text-ink">${escapeHtml(student.full_name)}</h2>
            ${badge(student.status)}
          </div>
          <p class="text-sm text-muted mt-0.5">${escapeHtml(student.student_code)} · ${escapeHtml(student.department_name)} · ${escapeHtml(student.email)}</p>
        </div>
        <div class="flex gap-6 sm:text-right">
          <div><p class="text-xs uppercase tracking-wide text-muted">CGPA</p><p class="text-2xl font-semibold text-ink">${student.cgpa === null ? '—' : Number(student.cgpa).toFixed(2)}</p></div>
          <div><p class="text-xs uppercase tracking-wide text-muted">Admitted</p><p class="text-sm font-medium text-ink mt-2">${formatDate(student.admission_date)}</p></div>
        </div>
      </div>`);
  }

  function showTab(key) {
    history.replaceState(null, '', `#${key}`);
    const body = document.getElementById('tab-body');
    const loaders = { profile: showProfile, enrollments: showEnrollments, attendance: showAttendance, transcript: showTranscript, dues: showDues };
    loaders[key](body);
  }

  // ---------------------------------------------------------------- Profile
  function showProfile(body) {
    const p = student.profile || {};
    body.innerHTML = `
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        ${card(cardTitle('Personal details', isAdmin ? `<button type="button" id="edit-student" class="${btnClass('secondary', 'sm')}">${icon('pencil', 14)} Edit</button>` : '') + definitionList([
          ['Date of birth', formatDate(p.date_of_birth)], ['Gender', escapeHtml(titleCase(p.gender))],
          ['Blood group', escapeHtml(p.blood_group)], ['City', escapeHtml(p.city)],
          ['Address', escapeHtml(p.address_line)], ['Postal code', escapeHtml(p.postal_code)],
        ]))}
        ${card(cardTitle('Guardian') + definitionList([
          ['Name', escapeHtml(p.guardian_name)], ['Relation', escapeHtml(p.guardian_relation)],
          ['Phone', escapeHtml(p.guardian_phone)],
        ]))}
        ${card(cardTitle('Account') + definitionList([
          ['Email', escapeHtml(student.email)], ['Login', student.is_active ? badge('active', 'Enabled') : badge('inactive', 'Disabled')],
          ['Last login', formatDateTime(student.last_login_at)], ['Department', escapeHtml(student.department_name)],
        ]))}
      </div>`;
    refreshIcons();
    document.getElementById('edit-student')?.addEventListener('click', openEditForm);
  }

  async function openEditForm() {
    const departments = await loadDepartments();
    const p = student.profile || {};
    formModal({
      title: `Edit ${student.full_name}`,
      size: 'max-w-2xl',
      submitText: 'Save changes',
      fieldsHtml: `
        <p class="text-xs uppercase tracking-wide text-muted mb-3">Student</p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'first_name', label: 'First name', required: true, value: student.first_name })}
          ${field({ name: 'last_name', label: 'Last name', required: true, value: student.last_name })}
          ${field({ name: 'department_id', label: 'Department', type: 'select', number: true, required: true, value: student.department_id, options: toOptions(departments, (d) => d.code) })}
          ${field({ name: 'status', label: 'Status', type: 'select', noEmpty: true, value: student.status, options: ['active', 'suspended', 'graduated', 'dropped_out'].map((s) => ({ value: s, label: titleCase(s) })) })}
          ${field({ name: 'admission_date', label: 'Admission date', type: 'date', required: true, value: student.admission_date })}
          ${field({ name: 'is_active', label: 'Login account enabled', type: 'checkbox', value: student.is_active, className: 'self-end' })}
        </div>
        <p class="text-xs uppercase tracking-wide text-muted mb-3 mt-2">Profile</p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'profile.date_of_birth', label: 'Date of birth', type: 'date', required: true, value: p.date_of_birth, max: todayISO() })}
          ${field({ name: 'profile.gender', label: 'Gender', type: 'select', required: true, value: p.gender, options: ['male', 'female', 'other'].map((g) => ({ value: g, label: titleCase(g) })) })}
          ${field({ name: 'profile.blood_group', label: 'Blood group', type: 'select', value: p.blood_group, emptyLabel: 'Unknown', options: ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'].map((b) => ({ value: b, label: b })) })}
          ${field({ name: 'profile.city', label: 'City', value: p.city })}
          ${field({ name: 'profile.address_line', label: 'Address', value: p.address_line, className: 'sm:col-span-2' })}
          ${field({ name: 'profile.postal_code', label: 'Postal code', value: p.postal_code, pattern: '[0-9]{4}', title: '4 digits' })}
          ${field({ name: 'profile.guardian_relation', label: 'Guardian relation', required: true, value: p.guardian_relation })}
          ${field({ name: 'profile.guardian_name', label: 'Guardian name', required: true, value: p.guardian_name })}
          ${field({ name: 'profile.guardian_phone', label: 'Guardian phone', type: 'tel', required: true, value: p.guardian_phone, pattern: '\\+?[0-9]{7,15}', title: '7–15 digits' })}
        </div>`,
      onSubmit: async (values) => {
        const risky = values.status !== student.status && values.status !== 'active';
        if (risky || (student.is_active && !values.is_active)) {
          const ok = await confirmDialog({
            title: 'Confirm change',
            message: risky ? `Status will change to "${titleCase(values.status)}". The student can no longer enroll.` : 'The student will not be able to log in.',
            confirmText: 'Save anyway',
          });
          if (!ok) throw new Error('cancelled');
        }
        return api.patch(`/students/${student.id}`, values);
      },
      onSuccess: (saved) => { student = saved; toast('Student updated'); renderHeader(); showProfile(document.getElementById('tab-body')); },
    });
  }

  // ------------------------------------------------------------ Enrollments
  async function showEnrollments(body) {
    body.innerHTML = card(skeletonTable(6, 6), 'p-0 overflow-hidden');
    try {
      const data = await api.get('/enrollments', { student_id: studentId, limit: 200, sort: 'enrolled_at', order: 'desc' }, { silent: true });
      if (!data.items.length) {
        body.innerHTML = card(emptyState({ iconName: 'clipboard-list', title: 'No enrollments yet' }));
        refreshIcons();
        return;
      }
      body.innerHTML = `<div class="bg-white rounded-xl border border-line shadow-sm overflow-hidden">${renderTable({
        columns: [
          { key: 'semester_code', label: 'Semester' },
          { key: 'course_code', label: 'Course', render: (r) => `<p class="font-medium text-ink">${escapeHtml(r.course_code)}-${escapeHtml(r.section)}</p><p class="text-xs text-muted">${escapeHtml(r.course_title)}</p>` },
          { key: 'teacher_name', label: 'Teacher' },
          { key: 'credits', label: 'Credits', className: 'tabular-nums' },
          { key: 'status', label: 'Status', render: (r) => badge(r.status) },
          { key: 'letter_grade', label: 'Grade', render: (r) => (r.letter_grade ? `<span class="font-medium text-ink">${escapeHtml(r.letter_grade)}</span> <span class="text-xs text-muted">${Number(r.grade_point).toFixed(2)}</span>` : '<span class="text-muted">—</span>') },
          { key: 'actions', label: '', className: 'text-right', render: (r) => (user.role === 'student' && r.status === 'enrolled'
            ? `<button type="button" data-drop="${r.id}" class="${btnClass('ghost', 'sm')} text-danger">Drop</button>` : '') },
        ],
        rows: data.items,
      })}</div>`;
      body.querySelectorAll('[data-drop]').forEach((button) => button.addEventListener('click', async () => {
        const row = data.items.find((r) => r.id === Number(button.dataset.drop));
        const ok = await confirmDialog({ title: 'Drop this course?', message: `You will leave ${row.course_code}-${row.section}. Your seat goes to someone else.`, confirmText: 'Drop course' });
        if (!ok) return;
        await api.patch(`/enrollments/${row.id}/drop`);
        toast(`${row.course_code} dropped`);
        showEnrollments(body);
      }));
    } catch (error) {
      showError(body, error, () => showEnrollments(body));
    }
  }

  // ------------------------------------------------------------- Attendance
  async function showAttendance(body) {
    body.innerHTML = card(skeletonTable(6, 5), 'p-0 overflow-hidden');
    try {
      const data = await api.get(`/students/${studentId}/attendance`, null, { silent: true });
      if (!data.items.length) {
        body.innerHTML = card(emptyState({ iconName: 'calendar-check', title: 'No attendance recorded yet' }));
        refreshIcons();
        return;
      }
      body.innerHTML = `<div class="bg-white rounded-xl border border-line shadow-sm overflow-hidden">${renderTable({
        columns: [
          { key: 'semester_code', label: 'Semester' },
          { key: 'course_code', label: 'Course', render: (r) => `<p class="font-medium text-ink">${escapeHtml(r.course_code)}-${escapeHtml(r.section)}</p><p class="text-xs text-muted">${escapeHtml(r.title)}</p>` },
          { key: 'attended', label: 'Attended', className: 'tabular-nums whitespace-nowrap', render: (r) => `${r.present_count} / ${r.total_classes}` },
          { key: 'breakdown', label: 'Absent · Late · Excused', className: 'tabular-nums text-xs text-muted whitespace-nowrap', render: (r) => `${r.absent_count} · ${r.late_count} · ${r.excused_count}` },
          { key: 'attendance_percent', label: 'Attendance', render: (r) => (r.attendance_percent === null ? '<span class="text-muted">—</span>' : `
              <div class="flex items-center gap-3 min-w-[160px]"><div class="flex-1">${progressBar(r.attendance_percent, r.attendance_percent < 75 ? 'bg-danger' : 'bg-success')}</div>
              <span class="text-xs tabular-nums ${r.attendance_percent < 75 ? 'text-danger font-medium' : 'text-ink'}">${formatPercent(r.attendance_percent)}</span></div>`) },
        ],
        rows: data.items,
      })}</div>
      <p class="text-xs text-muted mt-2">Present and late count as attended. Below 75% is marked in red.</p>`;
    } catch (error) {
      showError(body, error, () => showAttendance(body));
    }
  }

  // ------------------------------------------------------------- Transcript
  async function showTranscript(body) {
    body.innerHTML = `<div class="space-y-4">${card(skeletonBlock('h-16 w-full'))}${card(skeletonTable(4, 5), 'p-0')}</div>`;
    try {
      const data = await api.get(`/students/${studentId}/transcript`, null, { silent: true });
      if (!data.semesters.length) {
        body.innerHTML = card(emptyState({ iconName: 'award', title: 'No completed courses yet', subtitle: 'Grades appear here once a semester is finalized.' }));
        refreshIcons();
        return;
      }
      body.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          ${statCard({ label: 'CGPA', value: data.cgpa === null ? '—' : Number(data.cgpa).toFixed(2), iconName: 'award', delta: 'credit-weighted average', deltaType: 'muted' })}
          ${statCard({ label: 'Credits completed', value: formatNumber(data.credits_completed, 1), iconName: 'book-open' })}
          ${statCard({ label: 'Courses completed', value: data.courses_completed, iconName: 'clipboard-list' })}
        </div>
        <div class="flex justify-end mb-3 no-print"><button type="button" onclick="window.print()" class="${btnClass('secondary', 'sm')}">${icon('download', 14)} Print / Save PDF</button></div>
        <div class="space-y-4">
          ${data.semesters.map((sem) => `
            <div class="bg-white rounded-xl border border-line shadow-sm overflow-hidden">
              <div class="px-5 h-12 flex items-center justify-between border-b border-line">
                <p class="text-sm font-semibold text-ink">${escapeHtml(sem.semester_code)}</p>
                <p class="text-xs text-muted">GPA <span class="text-sm font-semibold text-ink">${sem.gpa === null ? '—' : sem.gpa.toFixed(2)}</span> · ${formatNumber(sem.credits, 1)} credits</p>
              </div>
              ${renderTable({
                columns: [
                  { key: 'course_code', label: 'Code', className: 'font-medium text-ink' },
                  { key: 'course_title', label: 'Course' },
                  { key: 'credits', label: 'Credits', className: 'tabular-nums' },
                  { key: 'total_marks', label: 'Marks', className: 'tabular-nums' },
                  { key: 'letter_grade', label: 'Grade', render: (r) => `<span class="font-medium ${r.letter_grade === 'F' ? 'text-danger' : 'text-ink'}">${escapeHtml(r.letter_grade)}</span>` },
                  { key: 'grade_point', label: 'Point', className: 'tabular-nums', render: (r) => Number(r.grade_point).toFixed(2) },
                ],
                rows: sem.courses,
              })}
            </div>`).join('')}
        </div>`;
      refreshIcons();
    } catch (error) {
      showError(body, error, () => showTranscript(body));
    }
  }

  // ------------------------------------------------------------------- Dues
  async function showDues(body) {
    body.innerHTML = `<div class="space-y-4">${card(skeletonBlock('h-12 w-full'))}${card(skeletonTable(4, 6), 'p-0')}</div>`;
    try {
      const data = await api.get(`/students/${studentId}/dues`, null, { silent: true });
      body.innerHTML = `
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          ${statCard({ label: 'Total due', value: formatMoney(data.total_due), iconName: 'wallet', delta: data.total_due ? 'please pay before the due date' : 'all clear', deltaType: data.total_due ? 'danger' : 'success' })}
          ${statCard({ label: 'Invoices', value: data.invoices.length, iconName: 'file-text' })}
          ${statCard({ label: 'Overdue', value: data.invoices.filter((i) => i.status === 'overdue').length, iconName: 'clock' })}
        </div>
        <div class="bg-white rounded-xl border border-line shadow-sm overflow-hidden">
          ${data.invoices.length ? renderTable({
            clickable: true,
            columns: [
              { key: 'invoice_no', label: 'Invoice', className: 'font-medium text-ink whitespace-nowrap' },
              { key: 'semester_code', label: 'Semester' },
              { key: 'total_amount', label: 'Total', className: 'tabular-nums text-right', headerClass: 'text-right', render: (r) => formatMoney(r.total_amount) },
              { key: 'paid_amount', label: 'Paid', className: 'tabular-nums text-right', headerClass: 'text-right', render: (r) => formatMoney(r.paid_amount) },
              { key: 'due_amount', label: 'Due', className: 'tabular-nums text-right font-medium', headerClass: 'text-right', render: (r) => formatMoney(r.due_amount) },
              { key: 'due_date', label: 'Due date', render: (r) => `${formatDate(r.due_date)}${r.days_overdue ? `<p class="text-xs text-danger">${r.days_overdue} days late</p>` : ''}` },
              { key: 'status', label: 'Status', render: (r) => badge(r.status) },
            ],
            rows: data.invoices,
          }) : emptyState({ iconName: 'file-text', title: 'No invoices yet' })}
        </div>`;
      refreshIcons();
      body.querySelectorAll('[data-row]').forEach((rowEl) => rowEl.addEventListener('click', () => {
        openInvoiceModal(data.invoices[Number(rowEl.dataset.row)].id);
      }));
    } catch (error) {
      showError(body, error, () => showDues(body));
    }
  }

  loadStudent();
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('student-detail', 'Student');
if (session) initStudentDetail(session);
