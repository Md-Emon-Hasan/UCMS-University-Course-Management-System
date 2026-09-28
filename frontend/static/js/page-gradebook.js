/*
 * page-gradebook.js: assessments as columns, students as rows.
 *   - Marks cells are editable; the weighted total and letter update live.
 *   - "Save changes" sends one bulk request per changed assessment (each one
 *     all-or-nothing on the server; marks > max_marks are refused).
 *   - "Finalize grades" calls finalize-grade for every enrolled student:
 *     calculate_final_marks -> marks_to_gpa -> status 'completed'.
 */

const ASSESSMENT_TYPES = ['quiz', 'assignment', 'midterm', 'final', 'project'];

async function initGradebook({ content }) {
  content.innerHTML = `
    ${pageHeader('Gradebook', 'Enter marks, check the live weighted total, then finalize the grades.')}
    ${card(`<div class="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-end">
      <div><label class="${LABEL_CLASS}" for="offering">Class</label><div id="offering-box">${skeletonBlock('h-9 w-full')}</div></div>
      <div class="flex flex-wrap gap-2">
        <button type="button" id="add-assessment" class="${btnClass('secondary')}" disabled>${icon('plus', 16)} Assessment</button>
        <button type="button" id="save-marks" class="${btnClass('primary')}" disabled>${icon('save', 16)} Save changes</button>
        <button type="button" id="finalize" class="${btnClass('secondary')}" disabled>${icon('award', 16)} Finalize grades</button>
      </div>
    </div>`)}
    <div id="grid" class="mt-4"></div>`;
  refreshIcons();

  let offerings = [];
  try {
    const active = await loadActiveSemester();
    offerings = (await api.get('/offerings', { semester_id: active?.id, limit: 200, sort: 'course_code' }, { silent: true }))
      .items.filter((o) => o.status !== 'cancelled');
  } catch (error) {
    showError(document.getElementById('grid'), error, () => initGradebook({ content }));
    return;
  }
  if (!offerings.length) {
    document.getElementById('offering-box').innerHTML = `<select disabled class="${INPUT_CLASS}"><option>No classes this semester</option></select>`;
    document.getElementById('grid').innerHTML = card(emptyState({ iconName: 'table', title: 'You have no classes in the active semester' }));
    refreshIcons();
    return;
  }
  document.getElementById('offering-box').innerHTML = `
    <select id="offering" class="${INPUT_CLASS}">
      ${offerings.map((o) => `<option value="${o.id}">${escapeHtml(o.course_code)}-${escapeHtml(o.section)} · ${escapeHtml(o.title)}</option>`).join('')}
    </select>`;

  const state = { offeringId: offerings[0].id, book: null, changes: {} };   // changes[assessmentId][enrollmentId] = marks
  const offeringSelect = document.getElementById('offering');
  const saveButton = document.getElementById('save-marks');
  const finalizeButton = document.getElementById('finalize');
  const addButton = document.getElementById('add-assessment');

  const changeCount = () => Object.values(state.changes).reduce((n, byStudent) => n + Object.keys(byStudent).length, 0);
  function updateButtons() {
    const count = changeCount();
    saveButton.disabled = count === 0;
    saveButton.innerHTML = `${icon('save', 16)} Save changes${count ? ` (${count})` : ''}`;
    const enrolled = state.book ? state.book.students.filter((s) => s.status === 'enrolled').length : 0;
    finalizeButton.disabled = !state.book || enrolled === 0;
    addButton.disabled = !state.book;
    refreshIcons();
  }

  offeringSelect.addEventListener('change', async () => {
    if (changeCount() && !(await confirmDialog({ title: 'Discard unsaved marks?', message: `You have ${changeCount()} unsaved change(s).`, confirmText: 'Discard' }))) {
      offeringSelect.value = state.offeringId;
      return;
    }
    state.offeringId = Number(offeringSelect.value);
    load();
  });
  window.addEventListener('beforeunload', (event) => { if (changeCount()) { event.preventDefault(); event.returnValue = ''; } });

  async function load() {
    state.changes = {};
    state.book = null;
    updateButtons();
    const box = document.getElementById('grid');
    box.innerHTML = card(skeletonTable(8, 6), 'p-0 overflow-hidden');
    try {
      state.book = await api.get(`/offerings/${state.offeringId}/gradebook`, null, { silent: true });
      renderGrid();
      updateButtons();
    } catch (error) {
      showError(box, error, load);
    }
  }

  /** Weighted total of one student row, using the values currently in the inputs. */
  function rowTotal(rowEl) {
    let total = 0;
    rowEl.querySelectorAll('input[data-assessment]').forEach((input) => {
      if (input.value === '') return;
      const a = state.book.assessments.find((x) => x.id === Number(input.dataset.assessment));
      total += (Math.min(Number(input.value), a.max_marks) / a.max_marks) * a.weight_percent;
    });
    return Math.round(total * 100) / 100;
  }

  function renderGrid() {
    const { assessments, students, weight_total: weightTotal } = state.book;
    const box = document.getElementById('grid');
    if (!students.length) {
      box.innerHTML = card(emptyState({ iconName: 'users', title: 'No students in this class yet' }));
      refreshIcons();
      return;
    }
    const weightOk = Math.abs(weightTotal - 100) < 0.001;
    box.innerHTML = `
      ${weightOk ? '' : `<div class="mb-3 rounded-lg bg-amber-50 text-amber-800 text-xs px-3 py-2.5 flex gap-2">${icon('triangle-alert', 16)}
        Assessment weights add up to ${weightTotal}%. They must add up to exactly 100% before grades can be finalized.</div>`}
      <div class="bg-white rounded-xl border border-line shadow-sm overflow-hidden">
        <div class="table-scroll">
          <table class="w-full text-sm">
            <thead><tr class="h-auto text-xs uppercase text-muted">
              <th class="bg-slate-50 px-4 py-2 text-left font-medium sticky left-0 z-[2] min-w-[200px]">Student</th>
              ${assessments.map((a) => `
                <th class="bg-slate-50 px-3 py-2 text-right font-medium whitespace-nowrap">
                  <span class="block text-ink normal-case text-xs">${escapeHtml(a.title)}</span>
                  <span class="block normal-case text-[11px] font-normal">max ${a.max_marks} · ${a.weight_percent}%</span></th>`).join('')}
              <th class="bg-slate-50 px-3 py-2 text-right font-medium whitespace-nowrap">Total <span class="normal-case font-normal">/100</span></th>
              <th class="bg-slate-50 px-3 py-2 text-left font-medium">Grade</th>
            </tr></thead>
            <tbody>
              ${students.map((s) => {
                const locked = s.status !== 'enrolled';
                return `
                <tr class="h-12 border-b border-line hover:bg-slate-50" data-enrollment="${s.enrollment_id}">
                  <td class="px-4 py-2 sticky left-0 bg-white z-[1]">
                    <p class="font-medium text-ink truncate">${escapeHtml(s.full_name)}</p>
                    <p class="text-xs text-muted">${escapeHtml(s.student_code)} ${locked ? badge(s.status) : ''}</p></td>
                  ${assessments.map((a) => {
                    const value = s.marks[a.id] ?? '';
                    return `<td class="px-3 py-2 text-right">
                      <input type="number" inputmode="decimal" step="0.5" min="0" max="${a.max_marks}" value="${value}"
                             data-assessment="${a.id}" data-original="${value}" ${locked ? 'disabled' : ''}
                             aria-label="${escapeHtml(a.title)} marks for ${escapeHtml(s.full_name)}"
                             class="no-spin w-20 h-8 rounded-lg border border-line px-2 text-right text-sm tabular-nums focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none disabled:bg-slate-50 disabled:text-muted">
                    </td>`;
                  }).join('')}
                  <td class="px-3 py-2 text-right font-semibold text-ink tabular-nums" data-total>${s.weighted_total.toFixed(2)}</td>
                  <td class="px-3 py-2" data-grade></td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
      <p class="text-xs text-muted mt-2">Total = Σ (marks ÷ max × weight). Empty cells count as 0. Grey rows are graded or dropped, and their marks are locked.</p>`;
    refreshIcons();

    // Show the grade of every row once
    box.querySelectorAll('tr[data-enrollment]').forEach((row) => showRowGrade(row));

    // Live recalculation while typing
    box.querySelector('tbody').addEventListener('input', (event) => {
      const input = event.target.closest('input[data-assessment]');
      if (!input) return;
      const row = input.closest('tr');
      const assessmentId = Number(input.dataset.assessment);
      const enrollmentId = Number(row.dataset.enrollment);
      const max = Number(input.max);
      const tooHigh = input.value !== '' && (Number(input.value) > max || Number(input.value) < 0);
      input.classList.toggle('border-danger', tooHigh);
      input.classList.toggle('bg-red-50', tooHigh);
      input.title = tooHigh ? `Must be between 0 and ${max}` : '';

      const changed = input.value !== input.dataset.original;
      input.classList.toggle('bg-amber-50', changed && !tooHigh);
      state.changes[assessmentId] = state.changes[assessmentId] || {};
      if (changed && input.value !== '') state.changes[assessmentId][enrollmentId] = Number(input.value);
      else delete state.changes[assessmentId][enrollmentId];

      row.querySelector('[data-total]').textContent = rowTotal(row).toFixed(2);
      showRowGrade(row);
      updateButtons();
    });
  }

  function showRowGrade(row) {
    const student = state.book.students.find((s) => s.enrollment_id === Number(row.dataset.enrollment));
    const cell = row.querySelector('[data-grade]');
    if (student.status === 'completed') {
      cell.innerHTML = `<span class="font-semibold text-ink">${escapeHtml(student.letter_grade)}</span> <span class="text-xs text-muted">final</span>`;
      return;
    }
    const preview = marksToGrade(rowTotal(row));
    cell.innerHTML = `<span class="font-medium ${preview.letter === 'F' ? 'text-danger' : 'text-ink'}">${preview.letter}</span> <span class="text-xs text-muted">${preview.point.toFixed(2)}</span>`;
  }

  // ---- Save: one bulk request per changed assessment
  saveButton.addEventListener('click', async () => {
    if (document.querySelector('#grid input.border-danger')) {
      toast('Fix the red cells first (marks must be between 0 and max)', 'warn');
      return;
    }
    setBusy(saveButton, true);
    let saved = 0;
    try {
      for (const [assessmentId, byStudent] of Object.entries(state.changes)) {
        const results = Object.entries(byStudent).map(([enrollmentId, marks]) => ({ enrollment_id: Number(enrollmentId), marks_obtained: marks }));
        if (!results.length) continue;
        const response = await api.post(`/assessments/${assessmentId}/results`, { results });
        saved += response.saved;
      }
      toast(`${saved} mark(s) saved`);
      load();
    } catch {
      setBusy(saveButton, false);
      updateButtons();
    }
  });

  // ---- Finalize: grade every enrolled student
  finalizeButton.addEventListener('click', async () => {
    if (changeCount()) { toast('Save your changes before finalizing', 'warn'); return; }
    if (Math.abs(state.book.weight_total - 100) > 0.001) { toast(`Weights add up to ${state.book.weight_total}%, not 100%`, 'error'); return; }
    const enrolled = state.book.students.filter((s) => s.status === 'enrolled');
    const ok = await confirmDialog({
      title: `Finalize ${enrolled.length} grades?`,
      message: 'Each student gets their final grade and status "completed". Their marks are then locked. This cannot be undone.',
      confirmText: 'Finalize grades',
    });
    if (!ok) return;
    setBusy(finalizeButton, true, 'Finalizing…');
    let done = 0;
    for (const student of enrolled) {
      try {
        await api.post(`/enrollments/${student.enrollment_id}/finalize-grade`, {}, { silent: true });
        done += 1;
        finalizeButton.lastChild.textContent = `Finalizing… ${done}/${enrolled.length}`;
      } catch (error) {
        toast(`${student.full_name}: ${error.message}`, 'error');
      }
    }
    toast(`${done} grade(s) finalized`);
    setBusy(finalizeButton, false);
    load();
  });

  // ---- New assessment (the server refuses a total weight above 100%)
  addButton.addEventListener('click', () => {
    const remaining = Math.round((100 - state.book.weight_total) * 100) / 100;
    formModal({
      title: 'New assessment',
      submitText: 'Add assessment',
      fieldsHtml: `
        <p class="text-xs text-muted mb-4">${remaining > 0 ? `${remaining}% of the weight is still free.` : 'All 100% of the weight is already used.'}</p>
        ${field({ name: 'title', label: 'Title', required: true, minlength: 2, maxlength: 80, placeholder: 'Quiz 2' })}
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'type', label: 'Type', type: 'select', required: true, options: ASSESSMENT_TYPES.map((t) => ({ value: t, label: titleCase(t) })) })}
          ${field({ name: 'due_date', label: 'Due date', type: 'date', required: true, value: todayISO() })}
          ${field({ name: 'max_marks', label: 'Max marks', type: 'number', required: true, min: 1, max: 1000, step: 0.5, value: 20 })}
          ${field({ name: 'weight_percent', label: 'Weight (%)', type: 'number', required: true, min: 0.5, max: Math.max(remaining, 0.5), step: 0.5, value: remaining > 0 ? Math.min(remaining, 10) : '' })}
        </div>`,
      transform: (values) => ({ ...values, offering_id: state.offeringId }),
      onSubmit: (values) => api.post('/assessments', values),
      onSuccess: (saved) => { toast(`${saved.title} added`); load(); },
    });
  });

  load();
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('gradebook', 'Gradebook');
if (session) initGradebook(session);
