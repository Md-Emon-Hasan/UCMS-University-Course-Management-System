/*
 * page-course-tree.js: visual prerequisite tree.
 * The API runs a RECURSIVE CTE and returns every link below the course:
 *   edges = [{ parent_id, id, depth, code, title, level, credits }, ...]
 * Here we turn that flat list back into a nested tree and draw it.
 */

async function initCourseTree({ content }) {
  content.innerHTML = `
    ${pageHeader('Prerequisite tree', 'Everything a student must pass before taking a course, at every depth.')}
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div class="xl:col-span-2 space-y-4">
        ${card(`<label class="${LABEL_CLASS}" for="course-select">Course</label><div id="picker">${skeletonBlock('h-9 w-full')}</div>`)}
        <div id="tree-card">${card(skeletonBlock('h-48 w-full'))}</div>
      </div>
      <div class="space-y-4">
        <div id="side">${card(skeletonBlock('h-24 w-full'))}</div>
        ${card(`
          ${cardTitle('How this works')}
          <p class="text-xs text-slate-600 mb-3">The prerequisites are stored as a <b>self many-to-many</b> table
          (<code>course_prerequisites</code>). One SQL query with <code>WITH RECURSIVE</code> follows the links
          down level by level until nothing new is found:</p>
          <pre class="json text-[11px] leading-5 bg-slate-50 border border-line rounded-lg p-3 overflow-x-auto">WITH RECURSIVE tree(parent_id, id, depth) AS (
  SELECT course_id, prerequisite_course_id, 1
  FROM course_prerequisites
  WHERE course_id = :course          -- anchor
  UNION
  SELECT cp.course_id,
         cp.prerequisite_course_id, t.depth + 1
  FROM course_prerequisites cp
  JOIN tree t ON cp.course_id = t.id -- recursive step
  WHERE t.depth &lt; 10
)
SELECT * FROM tree;</pre>`)}
      </div>
    </div>`;

  let courses = [];
  try {
    courses = (await api.get('/courses', { limit: 200, sort: 'code' }, { silent: true })).items;
  } catch (error) {
    showError(document.getElementById('tree-card'), error, () => initCourseTree({ content }));
    return;
  }

  // Course picker grouped by department
  const byDepartment = {};
  for (const c of courses) (byDepartment[c.department_code] ||= []).push(c);
  const startId = Number(queryParam('id')) || (courses.find((c) => c.code === 'CSE401') || courses[0])?.id;
  document.getElementById('picker').innerHTML = `
    <select id="course-select" class="${INPUT_CLASS}">
      ${Object.entries(byDepartment).map(([dept, list]) => `
        <optgroup label="${escapeHtml(dept)}">
          ${list.map((c) => `<option value="${c.id}" ${c.id === startId ? 'selected' : ''}>${escapeHtml(c.code)} · ${escapeHtml(c.title)}</option>`).join('')}
        </optgroup>`).join('')}
    </select>`;
  const select = document.getElementById('course-select');
  select.addEventListener('change', () => {
    history.replaceState(null, '', `?id=${select.value}`);
    loadTree(Number(select.value));
  });
  if (startId) loadTree(startId);
}

async function loadTree(courseId) {
  const treeCard = document.getElementById('tree-card');
  const side = document.getElementById('side');
  treeCard.innerHTML = card(skeletonBlock('h-48 w-full'));
  side.innerHTML = card(skeletonBlock('h-24 w-full'));
  try {
    const [tree, detail] = await Promise.all([
      api.get(`/courses/${courseId}/prerequisite-tree`, null, { silent: true }),
      api.get(`/courses/${courseId}`, null, { silent: true }),
    ]);
    drawTree(tree, treeCard);
    drawSide(tree, detail, side);
  } catch (error) {
    showError(treeCard, error, () => loadTree(courseId));
  }
}

/** One box in the tree */
function treeNode(course, depth, isRoot = false) {
  const levelColor = ['', 'bg-emerald-50 text-emerald-700', 'bg-cyan-50 text-cyan-700', 'bg-amber-50 text-amber-700', 'bg-rose-50 text-rose-700'][course.level] || '';
  return `
    <div class="inline-flex items-center gap-3 rounded-xl border ${isRoot ? 'border-primary-500 bg-primary-50' : 'border-line bg-white'} px-3 py-2 shadow-sm max-w-full">
      <span class="text-xs font-semibold px-1.5 py-0.5 rounded ${levelColor}">L${course.level}</span>
      <div class="min-w-0">
        <p class="text-sm font-semibold text-ink">${escapeHtml(course.code)}</p>
        <p class="text-xs text-muted truncate">${escapeHtml(course.title)} · ${course.credits} cr</p>
      </div>
      ${isRoot ? '' : `<span class="ml-1 text-[11px] text-muted whitespace-nowrap">depth ${depth}</span>`}
    </div>`;
}

function drawTree(tree, container) {
  if (!tree.edges.length) {
    container.innerHTML = card(`
      <div class="tree">${treeNode(tree.course, 0, true)}</div>
      ${emptyState({ iconName: 'circle-check', title: 'No prerequisites', subtitle: `${tree.course.code} can be taken without passing another course first.` })}`);
    refreshIcons();
    return;
  }
  // Children of a course = distinct edges whose parent is that course
  const children = {};
  for (const edge of tree.edges) {
    const list = (children[edge.parent_id] ||= []);
    if (!list.some((e) => e.id === edge.id)) list.push(edge);
  }
  // Recursive drawing; `path` protects against cycles in bad data
  const branch = (parentId, depth, path) => {
    const kids = children[parentId] || [];
    if (!kids.length) return '';
    return `<ul>${kids.map((kid) => `
      <li>${treeNode(kid, depth)}${path.includes(kid.id) ? '' : branch(kid.id, depth + 1, [...path, kid.id])}</li>`).join('')}</ul>`;
  };
  container.innerHTML = card(`
    ${cardTitle('Tree', `<span class="text-xs text-muted">read top-down: "needs"</span>`)}
    <div class="tree overflow-x-auto thin-scroll pb-2">${treeNode(tree.course, 0, true)}${branch(tree.course.id, 1, [tree.course.id])}</div>`);
  refreshIcons();
}

function drawSide(tree, detail, side) {
  const distinct = new Set(tree.edges.map((e) => e.id)).size;
  const requiredBy = detail.required_by.length
    ? detail.required_by.map((c) => `
        <a href="?id=${c.id}" data-jump="${c.id}" class="flex items-center justify-between h-10 px-3 -mx-3 rounded-lg hover:bg-slate-50">
          <span class="text-sm font-medium text-ink">${escapeHtml(c.code)} <span class="font-normal text-muted">${escapeHtml(c.title)}</span></span>
          ${icon('chevron-right', 16, 'text-slate-300')}</a>`).join('')
    : '<p class="text-xs text-muted">No course requires this one.</p>';
  side.innerHTML = `
    <div class="grid grid-cols-3 gap-3 mb-4">
      ${[['Direct', detail.prerequisites.length], ['Total', distinct], ['Depth', tree.max_depth]].map(([label, value]) => `
        <div class="bg-white rounded-xl border border-line shadow-sm p-3 text-center">
          <p class="text-xs uppercase tracking-wide text-muted">${label}</p><p class="text-xl font-semibold text-ink mt-1">${value}</p></div>`).join('')}
    </div>
    ${card(cardTitle('Required by') + requiredBy)}`;
  refreshIcons();
  side.querySelectorAll('[data-jump]').forEach((link) => link.addEventListener('click', (event) => {
    event.preventDefault();
    const select = document.getElementById('course-select');
    select.value = link.dataset.jump;
    select.dispatchEvent(new Event('change'));
  }));
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('course-tree', 'Prerequisite Tree');
if (session) initCourseTree(session);
