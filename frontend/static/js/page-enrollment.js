/*
 * page-enrollment.js: student self-enrollment.
 *   Left:  every offering of the active semester. "Enroll" is disabled (with
 *          the reason as a tooltip) when a rule fails. The reasons come from the
 *          API's dry run of the same 7 checks enroll_student() uses.
 *   Right: "My courses" with a Drop button.
 */

const MAX_CREDITS = 21;

function initEnrollment({ content }) {
  content.innerHTML = `
    ${pageHeader('Course enrollment', 'Pick your courses for the active semester. The rules are checked by the server.')}
    <div id="summary" class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">${skeletonCards(3)}</div>
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div class="xl:col-span-2 bg-white rounded-xl border border-line shadow-sm">
        <div class="p-4 border-b border-line flex flex-col sm:flex-row gap-3 sm:items-center">
          <h3 class="text-sm font-semibold tracking-tight text-ink">Available offerings</h3>
          <div class="sm:ml-auto flex flex-col sm:flex-row gap-2">
            <div class="relative"><span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">${icon('search', 16)}</span>
              <input id="search" type="search" placeholder="Search course…" class="${INPUT_CLASS} pl-9 sm:w-56"></div>
            <select id="dept-filter" class="${INPUT_CLASS} sm:w-36" aria-label="Department"><option value="">All depts</option></select>
            <label class="inline-flex items-center gap-2 text-xs text-ink whitespace-nowrap h-9">
              <input id="eligible-only" type="checkbox" class="h-4 w-4 rounded border-line text-primary-600 focus:ring-primary-500"> Only eligible</label>
          </div>
        </div>
        <div id="offerings">${skeletonTable(8, 5)}</div>
      </div>
      <div class="bg-white rounded-xl border border-line shadow-sm self-start">
        <div class="px-5 h-14 flex items-center justify-between border-b border-line">
          <h3 class="text-sm font-semibold tracking-tight text-ink">My courses</h3><span class="text-muted">${icon('clipboard-list', 18)}</span>
        </div>
        <div id="my-courses" class="p-5 space-y-3">${skeletonBlock('h-12 w-full')}${skeletonBlock('h-12 w-full')}</div>
      </div>
    </div>`;
  refreshIcons();

  let items = [];
  let semester = null;
  const filterState = { search: '', department: '', eligibleOnly: false };

  async function load() {
    try {
      const [data, active] = await Promise.all([
        api.get('/enrollments/eligibility', null, { silent: true }),
        loadActiveSemester(),
      ]);
      items = data.items;
      semester = active;
      fillDepartmentFilter();
      render();
    } catch (error) {
      showError(document.getElementById('offerings'), error, load);
      document.getElementById('summary').innerHTML = '';
      document.getElementById('my-courses').innerHTML = '';
    }
  }

  function fillDepartmentFilter() {
    const selectEl = document.getElementById('dept-filter');
    if (selectEl.options.length > 1) return;
    const codes = [...new Set(items.map((o) => o.department_code))].sort();
    selectEl.insertAdjacentHTML('beforeend', codes.map((c) => `<option value="${c}">${c}</option>`).join(''));
  }

  function render() {
    const mine = items.filter((o) => o.my_enrollment_id);
    const credits = mine.reduce((sum, o) => sum + o.credits, 0);

    // Summary cards
    document.getElementById('summary').innerHTML = `
      ${statCard({ label: 'Credits this semester', value: `${credits} / ${MAX_CREDITS}`, iconName: 'book-open',
                   delta: `${MAX_CREDITS - credits} credits left`, deltaType: credits >= MAX_CREDITS ? 'danger' : 'success' })}
      ${statCard({ label: 'Enrolled courses', value: mine.length, iconName: 'clipboard-list' })}
      ${statCard({ label: 'Registration', value: semester?.registration_open ? 'Open' : 'Closed', iconName: 'calendar-range',
                   delta: semester ? `${formatDate(semester.registration_start)} – ${formatDate(semester.registration_end)}` : '',
                   deltaType: semester?.registration_open ? 'success' : 'danger' })}`;

    // Available offerings (filtered on the client, the list is small)
    const text = filterState.search.toLowerCase();
    const visible = items.filter((o) => (!text || `${o.course_code} ${o.title} ${o.teacher_name}`.toLowerCase().includes(text))
      && (!filterState.department || o.department_code === filterState.department)
      && (!filterState.eligibleOnly || o.eligible));
    const offeringsBox = document.getElementById('offerings');
    offeringsBox.innerHTML = visible.length ? renderTable({
      columns: [
        { key: 'course_code', label: 'Course', render: (o) => `
            <div class="min-w-[200px]"><p class="font-medium text-ink">${escapeHtml(o.course_code)}-${escapeHtml(o.section)} <span class="font-normal text-muted">· ${o.credits} cr</span></p>
            <p class="text-xs text-muted">${escapeHtml(o.title)}</p>
            ${o.prerequisite_codes ? `<p class="text-[11px] text-muted mt-0.5">Needs: ${escapeHtml(o.prerequisite_codes)}</p>` : ''}
            ${!o.eligible && !o.my_enrollment_id ? `<p class="sm:hidden text-[11px] text-danger mt-1">${escapeHtml(o.reason)}</p>` : ''}</div>` },
        { key: 'teacher_name', label: 'Teacher', className: 'hidden md:table-cell', headerClass: 'hidden md:table-cell' },
        { key: 'seats', label: 'Seats', render: (o) => `
            <div class="min-w-[110px]"><p class="text-xs tabular-nums mb-1 ${o.enrolled_count >= o.capacity ? 'text-danger font-medium' : 'text-ink'}">${o.enrolled_count}/${o.capacity}</p>
            ${progressBar(o.fill_percent)}</div>` },
        { key: 'action', label: '', className: 'text-right', render: (o) => {
          if (o.my_enrollment_id) return badge('enrolled', 'Enrolled');
          if (o.eligible) return `<button type="button" data-enroll="${o.id}" class="${btnClass('primary', 'sm')}">Enroll</button>`;
          return `<span class="tip inline-block" data-tip="${escapeHtml(o.reason)}"><button type="button" disabled class="${btnClass('secondary', 'sm')}">${icon('lock', 14)} Enroll</button></span>`;
        } },
      ],
      rows: visible,
    }) : emptyState({ iconName: 'search', title: 'No offerings match', subtitle: 'Change the search or filters.' });

    // My courses panel
    const myBox = document.getElementById('my-courses');
    myBox.innerHTML = mine.length ? mine.map((o) => `
      <div class="flex items-center gap-3 rounded-lg border border-line p-3">
        <div class="w-9 h-9 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center shrink-0">${icon('book-open', 16)}</div>
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-ink truncate">${escapeHtml(o.course_code)}-${escapeHtml(o.section)}</p>
          <p class="text-xs text-muted truncate">${escapeHtml(o.title)} · ${o.credits} cr</p>
        </div>
        <button type="button" data-drop="${o.my_enrollment_id}" data-code="${escapeHtml(o.course_code)}" class="${btnClass('ghost', 'sm')} text-danger">Drop</button>
      </div>`).join('') + `<div class="pt-1">${progressBar((credits / MAX_CREDITS) * 100)}<p class="text-xs text-muted mt-1">${credits} of ${MAX_CREDITS} credits used</p></div>`
      : emptyState({ iconName: 'clipboard-list', title: 'No courses yet', subtitle: 'Enroll from the list on the left.' });
    refreshIcons();
  }

  // Enroll / Drop buttons (event delegation)
  document.getElementById('offerings').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-enroll]');
    if (!button) return;
    const offering = items.find((o) => o.id === Number(button.dataset.enroll));
    setBusy(button, true, '');
    try {
      await api.post('/enrollments', { offering_id: offering.id });
      toast(`Enrolled in ${offering.course_code}-${offering.section}`);
      load();
    } catch {
      setBusy(button, false);
      load();     // the reason may have changed (e.g. the offering just became full)
    }
  });
  document.getElementById('my-courses').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-drop]');
    if (!button) return;
    const ok = await confirmDialog({ title: `Drop ${button.dataset.code}?`, message: 'Your seat will be released. You can enroll again while registration is open, if seats are left.', confirmText: 'Drop course' });
    if (!ok) return;
    await api.patch(`/enrollments/${button.dataset.drop}/drop`);
    toast(`${button.dataset.code} dropped`);
    load();
  });

  document.getElementById('search').addEventListener('input', debounce((e) => { filterState.search = e.target.value.trim(); render(); }, 300));
  document.getElementById('dept-filter').addEventListener('change', (e) => { filterState.department = e.target.value; render(); });
  document.getElementById('eligible-only').addEventListener('change', (e) => { filterState.eligibleOnly = e.target.checked; render(); });

  load();
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('enrollment', 'Enrollment');
if (session) initEnrollment(session);
