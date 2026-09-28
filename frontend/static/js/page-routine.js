/*
 * page-routine.js: weekly class routine.
 *   Desktop: days as columns, 08:00–18:00 as rows, one colored block per class.
 *   Mobile:  a simple list grouped by day.
 * Students see their own classes, teachers their own; admins can filter.
 */

const DAY_START = 8 * 60;      // 08:00
const DAY_END = 18 * 60;       // 18:00
const PX_PER_MINUTE = 1.4;     // 10 minutes = 14 px (matches .routine-grid rows in app.css)

async function initRoutine({ user, content }) {
  const isAdmin = user.role === 'admin' || user.role === 'accountant';
  const description = {
    student: 'Your classes this week.', teacher: 'Your teaching schedule this week.',
  }[user.role] || 'All classes of the week. Filter by semester, department or room.';

  content.innerHTML = `
    ${pageHeader('Weekly routine', description)}
    <div id="filters" class="mb-4"></div>
    <div id="routine">${card(skeletonBlock('h-96 w-full'))}</div>`;

  let semesters = [];
  let departments = [];
  let rooms = [];
  let active = null;
  try {
    [semesters, active] = await Promise.all([loadSemesters(), loadActiveSemester()]);
    if (isAdmin) {
      departments = await loadDepartments();
      rooms = (await api.get('/rooms', { limit: 200, sort: 'building' }, { silent: true })).items;
    }
  } catch (error) {
    showError(document.getElementById('routine'), error, () => initRoutine({ user, content }));
    return;
  }

  const select = (name, label, options, value = '') => `
    <select data-filter="${name}" class="${INPUT_CLASS} sm:w-56" aria-label="${label}">
      ${name === 'semester_id' ? '' : `<option value="">${label}: All</option>`}
      ${options.map((o) => `<option value="${o.value}" ${String(o.value) === String(value) ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
    </select>`;
  document.getElementById('filters').innerHTML = `
    <div class="flex flex-col sm:flex-row flex-wrap gap-2">
      ${select('semester_id', 'Semester', toOptions(semesters, (s) => `${s.code}${s.is_active ? ' (active)' : ''}`), active?.id)}
      ${isAdmin ? select('department_id', 'Department', toOptions(departments, (d) => d.code), departments[0]?.id) : ''}
      ${isAdmin ? select('room_id', 'Room', toOptions(rooms, (r) => `${r.building} ${r.room_number}`)) : ''}
    </div>`;

  const filters = () => {
    const values = {};
    document.querySelectorAll('#filters [data-filter]').forEach((el) => { values[el.dataset.filter] = el.value; });
    return values;
  };
  document.querySelectorAll('#filters [data-filter]').forEach((el) => el.addEventListener('change', () => loadRoutine(filters(), user)));
  loadRoutine(filters(), user);
}

async function loadRoutine(filters, user) {
  const box = document.getElementById('routine');
  box.innerHTML = card(skeletonBlock('h-96 w-full'));
  try {
    const data = await api.get('/schedules/weekly', filters, { silent: true });
    if (!data.items.length) {
      box.innerHTML = card(emptyState({ iconName: 'calendar-clock', title: 'No classes scheduled',
        subtitle: user.role === 'student' ? 'Enroll in courses to see them here.' : 'Nothing matches these filters.' }));
      refreshIcons();
      return;
    }
    box.innerHTML = `<div class="hidden md:block">${gridView(data.items, user)}</div><div class="md:hidden">${listView(data.items, user)}</div>`;
    refreshIcons();
  } catch (error) {
    showError(box, error, () => loadRoutine(filters, user));
  }
}

/**
 * Place overlapping classes side by side: each class gets a "lane".
 * A class goes into the first lane whose previous class has already ended.
 */
function assignLanes(classes) {
  const laneEnds = [];
  const sorted = [...classes].sort((a, b) => timeToMinutes(a.start_time) - timeToMinutes(b.start_time));
  for (const c of sorted) {
    const start = timeToMinutes(c.start_time);
    let lane = laneEnds.findIndex((end) => end <= start);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(0); }
    laneEnds[lane] = timeToMinutes(c.end_time);
    c.lane = lane;
  }
  return { classes: sorted, laneCount: Math.max(1, laneEnds.length) };
}

function gridView(items, user) {
  // Sunday–Thursday always; Friday/Saturday only if something is scheduled
  const days = [0, 1, 2, 3, 4].concat([5, 6].filter((d) => items.some((i) => i.day_of_week === d)));
  const height = (DAY_END - DAY_START) * PX_PER_MINUTE;
  const hours = [];
  for (let m = DAY_START; m <= DAY_END; m += 60) hours.push(m);

  const timeColumn = `
    <div class="relative" style="height:${height}px">
      ${hours.map((m) => `<span class="absolute -translate-y-1/2 right-2 text-[11px] text-muted tabular-nums" style="top:${(m - DAY_START) * PX_PER_MINUTE}px">${String(m / 60).padStart(2, '0')}:00</span>`).join('')}
    </div>`;

  const dayColumn = (day) => {
    const { classes, laneCount } = assignLanes(items.filter((i) => i.day_of_week === day));
    const width = 100 / laneCount;
    return `
      <div class="relative border-l border-line" style="height:${height}px">
        ${hours.map((m) => `<div class="absolute inset-x-0 routine-hour-line" style="top:${(m - DAY_START) * PX_PER_MINUTE}px"></div>`).join('')}
        ${classes.map((c) => {
          const top = (timeToMinutes(c.start_time) - DAY_START) * PX_PER_MINUTE;
          const blockHeight = (timeToMinutes(c.end_time) - timeToMinutes(c.start_time)) * PX_PER_MINUTE;
          return `
            <div class="absolute rounded-lg border-l-4 px-2 py-1.5 overflow-hidden shadow-sm ${colorFor(c.course_code)}"
                 style="top:${top + 1}px;height:${blockHeight - 2}px;left:calc(${c.lane * width}% + 3px);width:calc(${width}% - 6px)"
                 title="${escapeHtml(`${c.course_code}-${c.section} ${c.title}\n${c.start_time}–${c.end_time} · ${c.room}\n${c.teacher_name}`)}">
              <p class="text-xs font-semibold truncate">${escapeHtml(c.course_code)}-${escapeHtml(c.section)}</p>
              <p class="text-[11px] truncate opacity-80">${c.start_time}–${c.end_time}</p>
              <p class="text-[11px] truncate opacity-80">${escapeHtml(c.room)}</p>
              ${user.role !== 'teacher' ? `<p class="text-[11px] truncate opacity-70">${escapeHtml(c.teacher_name)}</p>` : ''}
            </div>`;
        }).join('')}
      </div>`;
  };

  return `
    <div class="bg-white rounded-xl border border-line shadow-sm overflow-x-auto thin-scroll">
      <div class="min-w-[760px]">
        <div class="grid border-b border-line" style="grid-template-columns:64px repeat(${days.length}, minmax(0,1fr))">
          <div></div>
          ${days.map((d) => `<div class="h-10 flex items-center justify-center text-xs font-medium uppercase tracking-wide text-muted border-l border-line">${DAY_NAMES[d].slice(0, 3)}</div>`).join('')}
        </div>
        <div class="grid py-3" style="grid-template-columns:64px repeat(${days.length}, minmax(0,1fr))">
          ${timeColumn}${days.map(dayColumn).join('')}
        </div>
      </div>
    </div>`;
}

function listView(items, user) {
  const days = [...new Set(items.map((i) => i.day_of_week))].sort();
  return days.map((day) => `
    <div class="bg-white rounded-xl border border-line shadow-sm mb-3">
      <p class="px-4 h-10 flex items-center text-xs font-medium uppercase tracking-wide text-muted border-b border-line">${DAY_NAMES[day]}</p>
      ${items.filter((i) => i.day_of_week === day).map((c) => `
        <div class="flex gap-3 px-4 py-3 border-b border-line last:border-0">
          <div class="w-1 rounded-full ${colorFor(c.course_code).split(' ')[1].replace('border-', 'bg-')}"></div>
          <div class="min-w-0">
            <p class="text-sm font-semibold text-ink">${escapeHtml(c.course_code)}-${escapeHtml(c.section)} <span class="font-normal text-muted">${escapeHtml(c.title)}</span></p>
            <p class="text-xs text-muted mt-0.5">${c.start_time}–${c.end_time} · ${escapeHtml(c.room)}${user.role !== 'teacher' ? ` · ${escapeHtml(c.teacher_name)}` : ''}</p>
          </div>
        </div>`).join('')}
    </div>`).join('');
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('routine', 'Weekly Routine');
if (session) initRoutine(session);
