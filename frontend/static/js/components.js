/*
 * components.js: every reusable UI piece, defined ONCE and used by all pages.
 *
 *   Layout ........ startPage(), renderLayout()
 *   Pieces ........ icon(), badge(), card(), statCard(), pageHeader(), emptyState(), errorState()
 *   Loading ....... skeletonTable(), skeletonCards(), skeletonBlock()
 *   Table ......... renderTable(), paginationHtml(), createListView()
 *   Overlays ...... openModal(), confirmDialog(), toast()
 *   Forms ......... field(), getFormValues(), validateForm(), setFormErrors(), formModal()
 *   Data .......... loadDepartments(), loadSemesters(), loadActiveSemester()
 *   Charts ........ renderChart()
 *
 * Every function returns an HTML string or wires events. No framework, no classes.
 * All data put into HTML goes through escapeHtml() (utils.js).
 */

// ============================================================================
// Style constants (the design system, in one place)
// ============================================================================
const BTN_BASE = 'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap';
const BTN_VARIANTS = {
  primary: 'bg-primary-600 text-white hover:bg-primary-700',
  secondary: 'bg-white border border-line text-ink hover:bg-slate-50',
  danger: 'bg-danger text-white hover:bg-red-700',
  ghost: 'text-muted hover:bg-slate-100 hover:text-ink',
};
const BTN_SIZES = { md: 'h-9 px-4', sm: 'h-8 px-3 text-xs', icon: 'h-9 w-9', 'icon-sm': 'h-8 w-8' };

/** Button classes, e.g. btnClass('secondary', 'sm') */
function btnClass(variant = 'primary', size = 'md') {
  return `${BTN_BASE} ${BTN_VARIANTS[variant]} ${BTN_SIZES[size]}`;
}

const INPUT_CLASS = 'h-9 w-full rounded-lg border border-line bg-white px-3 text-sm text-ink placeholder:text-slate-400 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none disabled:bg-slate-50 disabled:text-muted';
const LABEL_CLASS = 'text-xs font-medium text-ink mb-1.5 block';

// ============================================================================
// Navigation: the single source of truth for "which role may open which page"
// ============================================================================
const ALL_ROLES = ['admin', 'teacher', 'student', 'accountant'];

const NAV_SECTIONS = [
  { label: 'Overview', items: [
    { page: 'dashboard', label: 'Dashboard', icon: 'layout-dashboard', roles: ALL_ROLES },
  ] },
  { label: 'Academic', items: [
    { page: 'departments', label: 'Departments', icon: 'building-2', roles: ['admin'] },
    { page: 'teachers', label: 'Teachers', icon: 'users', roles: ['admin'] },
    { page: 'students', label: 'Students', icon: 'graduation-cap', roles: ['admin'] },
    { page: 'courses', label: 'Courses', icon: 'book-open', roles: ['admin', 'teacher', 'student'] },
    { page: 'course-tree', label: 'Prerequisite Tree', icon: 'git-fork', roles: ALL_ROLES },
    { page: 'rooms', label: 'Rooms', icon: 'door-open', roles: ['admin'] },
    { page: 'semesters', label: 'Semesters', icon: 'calendar-range', roles: ['admin'] },
  ] },
  { label: 'Teaching', items: [
    { page: 'offerings', label: 'Offerings', icon: 'layers', roles: ['admin', 'teacher'] },
    { page: 'routine', label: 'Weekly Routine', icon: 'calendar-clock', roles: ['admin', 'teacher', 'student'] },
    { page: 'attendance', label: 'Attendance', icon: 'calendar-check', roles: ['admin', 'teacher'] },
    { page: 'gradebook', label: 'Gradebook', icon: 'table', roles: ['admin', 'teacher'] },
  ] },
  { label: 'My Studies', items: [
    { page: 'enrollment', label: 'Enrollment', icon: 'clipboard-list', roles: ['student'] },
    { page: 'student-detail', label: 'My Record', icon: 'user-round', roles: ['student'] },
  ] },
  { label: 'Finance', items: [
    { page: 'billing', label: 'Billing', icon: 'wallet', roles: ['admin', 'accountant'] },
  ] },
  { label: 'Insights', items: [
    { page: 'reports', label: 'Reports', icon: 'chart-column', roles: ['admin', 'teacher', 'accountant'] },
    { page: 'audit-log', label: 'Audit Log', icon: 'shield-check', roles: ['admin'] },
  ] },
];

// page -> allowed roles. student-detail is also opened by admins from the students table.
const PAGE_ROLES = { 'student-detail': ['admin', 'student'] };
for (const section of NAV_SECTIONS) {
  for (const item of section.items) {
    if (!PAGE_ROLES[item.page]) PAGE_ROLES[item.page] = item.roles;
  }
}

// ============================================================================
// Small pieces
// ============================================================================

/** A Lucide icon placeholder. refreshIcons() turns it into an <svg>. */
function icon(name, size = 18, extraClass = '') {
  return `<i data-lucide="${name}" width="${size}" height="${size}" class="shrink-0 ${extraClass}"></i>`;
}

/** Replace all <i data-lucide> placeholders with real SVG icons (call after every render). */
function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

const LOGO_SVG = `
  <svg viewBox="0 0 32 32" class="w-8 h-8" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="#3f57e0"/>
    <path d="M16 7 5 12.5l11 5.5 9-4.5V20h2v-7.5L16 7Z" fill="#fff"/>
    <path d="M9.5 16.8v4.4c0 1.8 2.9 3.3 6.5 3.3s6.5-1.5 6.5-3.3v-4.4L16 20l-6.5-3.2Z" fill="#dae4ff"/>
  </svg>`;

// Status -> badge color (design system map)
const BADGE_COLORS = {
  green: 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20',
  amber: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20',
  red: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20',
  slate: 'bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-500/20',
  blue: 'bg-primary-50 text-primary-700 ring-1 ring-inset ring-primary-500/20',
};
const STATUS_COLOR = {
  active: 'green', present: 'green', paid: 'green', INSERT: 'green', yes: 'green',
  pending: 'amber', partial: 'amber', late: 'amber', on_leave: 'amber', suspended: 'amber',
  dropped: 'red', absent: 'red', unpaid: 'red', overdue: 'red', cancelled: 'red', dropped_out: 'red',
  resigned: 'red', DELETE: 'red', inactive: 'red', no: 'red',
  completed: 'slate', closed: 'slate', graduated: 'slate',
  open: 'blue', info: 'blue', enrolled: 'blue', excused: 'blue', UPDATE: 'blue',
};

/** <span> badge for a status value; the label defaults to the value in Title Case. */
function badge(value, label) {
  const color = STATUS_COLOR[value] || 'slate';
  const text = label ?? titleCase(value);
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${BADGE_COLORS[color]}">${escapeHtml(text)}</span>`;
}

/** Card container */
function card(inner, extraClass = '') {
  return `<div class="bg-white rounded-xl border border-line shadow-sm p-5 ${extraClass}">${inner}</div>`;
}

/**
 * Stat card: label, big value, delta line, icon square top-right.
 * deltaType: 'success' | 'danger' | 'muted'
 */
function statCard({ label, value, delta, deltaType = 'muted', iconName = 'activity' }) {
  const deltaColor = { success: 'text-success', danger: 'text-danger' }[deltaType] || 'text-muted';
  return `
    <div class="bg-white rounded-xl border border-line shadow-sm p-5">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs uppercase tracking-wide text-muted">${escapeHtml(label)}</p>
          <p class="text-2xl font-semibold text-ink mt-1 truncate">${escapeHtml(value)}</p>
        </div>
        <div class="w-10 h-10 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center shrink-0">${icon(iconName, 20)}</div>
      </div>
      ${delta ? `<p class="text-xs mt-2 ${deltaColor}">${escapeHtml(delta)}</p>` : ''}
    </div>`;
}

/** Title + description row at the top of a page, with optional buttons on the right. */
function pageHeader(title, description = '', actionsHtml = '') {
  return `
    <div class="flex flex-col sm:flex-row sm:items-end justify-between gap-3 mb-5">
      <div>
        <h2 class="text-xl font-semibold tracking-tight text-ink">${escapeHtml(title)}</h2>
        ${description ? `<p class="text-sm text-muted mt-1">${escapeHtml(description)}</p>` : ''}
      </div>
      ${actionsHtml ? `<div class="flex flex-wrap gap-2">${actionsHtml}</div>` : ''}
    </div>`;
}

/** Centered "nothing here" message with an optional action button (HTML). */
function emptyState({ iconName = 'inbox', title = 'Nothing here yet', subtitle = '', actionHtml = '' } = {}) {
  return `
    <div class="flex flex-col items-center justify-center text-center py-12 px-4">
      <div class="text-slate-300">${icon(iconName, 40)}</div>
      <p class="text-sm font-medium text-ink mt-3">${escapeHtml(title)}</p>
      ${subtitle ? `<p class="text-xs text-muted mt-1 max-w-sm">${escapeHtml(subtitle)}</p>` : ''}
      ${actionHtml ? `<div class="mt-4">${actionHtml}</div>` : ''}
    </div>`;
}

/** Error message with a Retry button (the caller wires [data-retry]). */
function errorState(message = 'Something went wrong') {
  return `
    <div class="flex flex-col items-center justify-center text-center py-12 px-4">
      <div class="text-danger/70">${icon('circle-alert', 40)}</div>
      <p class="text-sm font-medium text-ink mt-3">Could not load data</p>
      <p class="text-xs text-muted mt-1 max-w-sm">${escapeHtml(message)}</p>
      <button type="button" data-retry class="${btnClass('secondary', 'sm')} mt-4">${icon('refresh-cw', 14)} Retry</button>
    </div>`;
}

/** Show an error state in `container`, and call `retry` when the button is clicked. */
function showError(container, error, retry) {
  container.innerHTML = errorState(error?.message || String(error));
  refreshIcons();
  container.querySelector('[data-retry]')?.addEventListener('click', retry);
}

// ============================================================================
// Skeleton loaders (never show a blank screen while fetching)
// ============================================================================
function skeletonBlock(classes = 'h-4 w-full') {
  return `<div class="animate-pulse bg-slate-200 rounded ${classes}"></div>`;
}

/** Placeholder table with header + rows */
function skeletonTable(rows = 6, cols = 5) {
  const cells = (height) => Array.from({ length: cols }, (_, i) =>
    `<div class="flex-1">${skeletonBlock(`${height} ${i === 0 ? 'w-3/4' : 'w-1/2'}`)}</div>`).join('');
  return `
    <div class="w-full">
      <div class="h-10 bg-slate-50 flex items-center gap-4 px-4">${cells('h-2.5')}</div>
      ${Array.from({ length: rows }, () => `<div class="h-12 border-b border-line flex items-center gap-4 px-4">${cells('h-3')}</div>`).join('')}
    </div>`;
}

/** Placeholder stat cards */
function skeletonCards(count = 4) {
  return Array.from({ length: count }, () => `
    <div class="bg-white rounded-xl border border-line shadow-sm p-5">
      <div class="flex justify-between">
        <div class="space-y-3 flex-1">${skeletonBlock('h-2.5 w-24')}${skeletonBlock('h-6 w-20')}</div>
        ${skeletonBlock('h-10 w-10 rounded-lg')}
      </div>
      ${skeletonBlock('h-2.5 w-32 mt-4')}
    </div>`).join('');
}

// ============================================================================
// Layout
// ============================================================================

/**
 * Draw the sidebar + topbar and return the <main> element for the page content.
 * The sidebar only lists pages the user's role may open.
 */
function renderLayout(activePage, title, user) {
  const navHtml = NAV_SECTIONS.map((section) => {
    const items = section.items.filter((item) => item.roles.includes(user.role));
    if (!items.length) return '';
    return `
      <div>
        <p class="px-3 mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">${section.label}</p>
        <div class="space-y-0.5">
          ${items.map((item) => {
            const active = item.page === activePage;
            return `<a href="/pages/${item.page}.html"
                      class="flex items-center gap-3 h-10 px-3 rounded-lg text-sm ${active
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-ink'}">
                      ${icon(item.icon, 18)}<span class="truncate">${item.label}</span></a>`;
          }).join('')}
        </div>
      </div>`;
  }).join('');

  document.body.innerHTML = `
    <div id="drawer-overlay" class="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm hidden lg:hidden"></div>
    <aside id="sidebar" class="fixed inset-y-0 left-0 z-40 w-64 bg-white border-r border-line flex flex-col
                               -translate-x-full lg:translate-x-0 transition-transform duration-200">
      <div class="h-16 shrink-0 flex items-center gap-2.5 px-5 border-b border-line">
        ${LOGO_SVG}
        <span class="text-lg font-semibold tracking-tight text-primary-600">UCMS</span>
        <button id="drawer-close" class="${btnClass('ghost', 'icon-sm')} ml-auto lg:hidden" aria-label="Close menu">${icon('x', 18)}</button>
      </div>
      <nav class="flex-1 overflow-y-auto thin-scroll px-3 py-4 space-y-5">${navHtml}</nav>
      <div class="p-4 border-t border-line">
        <p class="text-xs font-medium text-ink truncate">${escapeHtml(user.full_name)}</p>
        <p class="text-xs text-muted truncate">${escapeHtml(user.email)}</p>
      </div>
    </aside>

    <div class="lg:ml-64 min-h-screen flex flex-col">
      <header class="h-16 bg-white border-b border-line sticky top-0 z-20 flex items-center gap-3 px-4 lg:px-6">
        <button id="drawer-open" class="${btnClass('ghost', 'icon')} lg:hidden -ml-2" aria-label="Open menu">${icon('menu', 20)}</button>
        <h1 class="text-base sm:text-lg font-semibold tracking-tight text-ink truncate">${escapeHtml(title)}</h1>
        <div class="ml-auto flex items-center gap-2 sm:gap-3">
          <span id="semester-pill" class="hidden md:inline-flex items-center gap-1.5 h-7 px-3 rounded-full bg-primary-50 text-primary-700 text-xs font-medium">
            ${icon('calendar-range', 14)}<span>…</span>
          </span>
          <span class="hidden sm:inline-flex">${badge('info', titleCase(user.role))}</span>
          <div class="w-8 h-8 rounded-full bg-primary-600 text-white text-xs font-semibold flex items-center justify-center" title="${escapeHtml(user.full_name)}">
            ${escapeHtml(initials(user.full_name))}
          </div>
          <button id="logout-btn" class="${btnClass('ghost', 'icon')}" title="Log out" aria-label="Log out">${icon('log-out', 18)}</button>
        </div>
      </header>
      <main id="page-content" class="flex-1 w-full max-w-[1400px] p-4 sm:p-6"></main>
    </div>
    <div id="toast-stack" class="fixed top-4 right-4 z-[70] flex flex-col gap-2 w-[calc(100%-2rem)] max-w-sm pointer-events-none"></div>`;

  // Mobile drawer: slide the sidebar in/out
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('drawer-overlay');
  const setDrawer = (open) => {
    sidebar.classList.toggle('-translate-x-full', !open);
    overlay.classList.toggle('hidden', !open);
  };
  document.getElementById('drawer-open').addEventListener('click', () => setDrawer(true));
  document.getElementById('drawer-close').addEventListener('click', () => setDrawer(false));
  overlay.addEventListener('click', () => setDrawer(false));
  document.getElementById('logout-btn').addEventListener('click', logout);

  // Active semester pill (fills in when the request returns)
  loadActiveSemester().then((semester) => {
    const pill = document.querySelector('#semester-pill span');
    if (pill) pill.textContent = semester ? `${semester.code} · Active` : 'No active semester';
  });

  refreshIcons();
  return document.getElementById('page-content');
}

/**
 * Standard start of every page script:
 *   const session = startPage('departments', 'Departments');
 *   if (session) { ...build the page into session.content... }
 * Returns null (and shows a "no access" message) if the role may not open the page.
 */
function startPage(page, title) {
  const user = requireAuth();
  if (!user) return null;
  document.title = `${title} · UCMS`;
  const content = renderLayout(page, title, user);
  const roles = PAGE_ROLES[page] || ALL_ROLES;
  if (!roles.includes(user.role)) {
    content.innerHTML = card(emptyState({
      iconName: 'lock',
      title: "You don't have access to this page",
      subtitle: `This page is for: ${roles.map(titleCase).join(', ')}.`,
      actionHtml: `<a href="/pages/dashboard.html" class="${btnClass('secondary')}">Go to dashboard</a>`,
    }));
    refreshIcons();
    return null;
  }
  return { user, content };
}

// ============================================================================
// Table + pagination
// ============================================================================

/**
 * Build a table.
 * columns: [{ key, label, sortable, render(row) -> html, className, headerClass }]
 * Sortable headers show a chevron. The header stays visible while scrolling.
 */
function renderTable({ columns, rows, sort = '', order = 'asc', clickable = false }) {
  const head = columns.map((col) => {
    const isSorted = col.sortable && sort === col.key;
    const chevron = col.sortable
      ? icon(isSorted ? (order === 'asc' ? 'chevron-up' : 'chevron-down') : 'chevrons-up-down', 14,
        isSorted ? 'text-primary-600' : 'text-slate-300')
      : '';
    return `<th class="bg-slate-50 px-4 text-left font-medium whitespace-nowrap ${col.headerClass || ''}
                ${col.sortable ? 'cursor-pointer select-none hover:text-ink' : ''}"
                ${col.sortable ? `data-sort="${col.key}"` : ''}>
              <span class="inline-flex items-center gap-1">${escapeHtml(col.label)}${chevron}</span></th>`;
  }).join('');

  const body = rows.map((row, index) => `
    <tr class="h-12 border-b border-line hover:bg-slate-50 ${clickable ? 'cursor-pointer' : ''}" data-row="${index}">
      ${columns.map((col) => `<td class="px-4 py-2 ${col.className || ''}">${
        col.render ? col.render(row) : escapeHtml(row[col.key] ?? '—')}</td>`).join('')}
    </tr>`).join('');

  return `
    <div class="table-scroll">
      <table class="w-full text-sm">
        <thead><tr class="h-10 text-xs uppercase text-muted">${head}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

/** "Showing 21–40 of 57" + prev / numbered / next buttons. */
function paginationHtml({ page, pages, total, limit }) {
  const from = total === 0 ? 0 : (page - 1) * limit + 1;
  const to = Math.min(page * limit, total);
  // Show at most 5 page numbers around the current page
  let start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  start = Math.max(1, end - 4);
  const numbers = [];
  for (let n = start; n <= end; n++) {
    numbers.push(`<button type="button" data-page="${n}"
      class="${n === page ? 'bg-primary-600 text-white' : 'text-ink hover:bg-slate-100'} hidden sm:inline-flex h-8 min-w-8 px-2 items-center justify-center rounded-lg text-xs font-medium">${n}</button>`);
  }
  return `
    <div class="h-14 px-4 flex items-center justify-between gap-3 border-t border-line">
      <p class="text-xs text-muted">Showing <span class="font-medium text-ink">${from}–${to}</span> of <span class="font-medium text-ink">${formatNumber(total)}</span></p>
      <div class="flex items-center gap-1">
        <button type="button" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''} class="${btnClass('ghost', 'icon-sm')}" aria-label="Previous page">${icon('chevron-left', 16)}</button>
        ${numbers.join('')}
        <span class="sm:hidden text-xs text-muted px-2">${page} / ${pages}</span>
        <button type="button" data-page="${page + 1}" ${page >= pages ? 'disabled' : ''} class="${btnClass('ghost', 'icon-sm')}" aria-label="Next page">${icon('chevron-right', 16)}</button>
      </div>
    </div>`;
}

/**
 * A complete list screen: search box, filter selects, table, paging, and the
 * loading / empty / error states. Used by most admin pages.
 *
 * options = {
 *   mount: element,  endpoint: '/students',  columns: [...],
 *   filters: [{ name, label, options: [{value, label}] }],   // select filters
 *   searchPlaceholder, defaultSort, defaultOrder, limit,
 *   toolbarHtml: extra buttons (right side),
 *   emptyTitle, emptySubtitle, emptyIcon,
 *   extraParams(): {} added to every request,
 *   onRowClick(row), onAction(action, row, button)   // buttons with data-action
 * }
 * Returns { reload(), state, setFilter(name, value) }
 */
function createListView(options) {
  const state = {
    page: 1, limit: options.limit || 20, search: '',
    sort: options.defaultSort || '', order: options.defaultOrder || 'asc',
    filters: { ...(options.initialFilters || {}) },
  };
  let lastItems = [];

  const filterSelects = (options.filters || []).map((filter) => `
    <select data-filter="${filter.name}" class="${INPUT_CLASS} sm:w-44" aria-label="${escapeHtml(filter.label)}">
      <option value="">${escapeHtml(filter.label)}: All</option>
      ${filter.options.map((o) => `<option value="${escapeHtml(o.value)}" ${String(state.filters[filter.name] ?? '') === String(o.value) ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
    </select>`).join('');

  options.mount.innerHTML = `
    <div class="bg-white rounded-xl border border-line shadow-sm">
      <div class="p-4 border-b border-line flex flex-col lg:flex-row gap-3 lg:items-center">
        <div class="relative w-full lg:max-w-xs">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">${icon('search', 16)}</span>
          <input type="search" data-search placeholder="${escapeHtml(options.searchPlaceholder || 'Search…')}" class="${INPUT_CLASS} pl-9">
        </div>
        <div class="flex flex-col sm:flex-row flex-wrap gap-2">${filterSelects}</div>
        <div class="lg:ml-auto flex flex-wrap gap-2">${options.toolbarHtml || ''}</div>
      </div>
      <div data-body></div>
      <div data-pager></div>
    </div>`;
  const root = options.mount;
  const body = root.querySelector('[data-body]');
  const pager = root.querySelector('[data-pager]');

  async function reload() {
    body.innerHTML = skeletonTable(Math.min(state.limit, 8), options.columns.length);
    pager.innerHTML = '';
    const params = {
      page: state.page, limit: state.limit, search: state.search, sort: state.sort, order: state.order,
      ...state.filters, ...(options.extraParams ? options.extraParams() : {}),
    };
    try {
      const data = await api.get(options.endpoint, params, { silent: true });
      lastItems = data.items;
      if (!data.items.length) {
        body.innerHTML = emptyState({
          iconName: options.emptyIcon || 'inbox',
          title: state.search ? `No results for "${state.search}"` : (options.emptyTitle || 'No records yet'),
          subtitle: state.search ? 'Try a different search or clear the filters.' : (options.emptySubtitle || ''),
        });
      } else {
        body.innerHTML = renderTable({
          columns: options.columns, rows: data.items, sort: state.sort, order: state.order,
          clickable: Boolean(options.onRowClick),
        });
        pager.innerHTML = paginationHtml(data);
      }
      refreshIcons();
    } catch (error) {
      showError(body, error, reload);
    }
  }

  // Search: debounced 300 ms, back to page 1
  root.querySelector('[data-search]').addEventListener('input', debounce((event) => {
    state.search = event.target.value.trim();
    state.page = 1;
    reload();
  }, 300));

  root.querySelectorAll('[data-filter]').forEach((select) => {
    select.addEventListener('change', () => {
      state.filters[select.dataset.filter] = select.value;
      state.page = 1;
      reload();
    });
  });

  // One click handler for sorting, row clicks and action buttons (event delegation)
  body.addEventListener('click', (event) => {
    const sortHeader = event.target.closest('[data-sort]');
    if (sortHeader) {
      const key = sortHeader.dataset.sort;
      state.order = state.sort === key && state.order === 'asc' ? 'desc' : 'asc';
      state.sort = key;
      reload();
      return;
    }
    const rowEl = event.target.closest('[data-row]');
    if (!rowEl) return;
    const row = lastItems[Number(rowEl.dataset.row)];
    const actionButton = event.target.closest('[data-action]');
    if (actionButton) {
      event.stopPropagation();
      options.onAction?.(actionButton.dataset.action, row, actionButton);
    } else if (event.target.closest('a')) {
      // let links work normally
    } else {
      options.onRowClick?.(row);
    }
  });

  pager.addEventListener('click', (event) => {
    const button = event.target.closest('[data-page]');
    if (!button || button.disabled) return;
    state.page = Number(button.dataset.page);
    reload();
  });

  reload();
  return {
    reload,
    state,
    setFilter(name, value) { state.filters[name] = value; state.page = 1; reload(); },
  };
}

/** Small icon button for table rows, e.g. rowAction('edit', 'pencil', 'Edit') */
function rowAction(action, iconName, label, variant = 'ghost') {
  return `<button type="button" data-action="${action}" class="${btnClass(variant, 'icon-sm')}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${icon(iconName, 16)}</button>`;
}

/** Thin progress bar: value 0-100 */
function progressBar(percent, colorClass = 'bg-primary-500') {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  const color = value >= 100 ? 'bg-danger' : colorClass;
  return `<div class="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden"><div class="h-full rounded-full ${color}" style="width:${value}%"></div></div>`;
}

// ============================================================================
// Modals, confirm dialog, toasts
// ============================================================================
const openModals = [];

// Esc closes only the TOP modal
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && openModals.length) openModals[openModals.length - 1].close();
});

/**
 * Open a modal.
 *   const modal = openModal({ title, body: html, footer: html, size: 'max-w-lg' });
 *   modal.body -> the body element, modal.close() -> close it
 * Closes on Esc, on the X button and on a click on the dark overlay.
 */
function openModal({ title, body = '', footer = '', size = 'max-w-lg', onClose } = {}) {
  const root = document.createElement('div');
  root.className = 'fixed inset-0 z-50 overflow-y-auto';
  root.innerHTML = `
    <div class="fixed inset-0 bg-black/40 backdrop-blur-sm" data-overlay></div>
    <div class="relative min-h-full flex items-center justify-center p-4 pointer-events-none">
      <div class="relative pointer-events-auto bg-white rounded-2xl w-full ${size} shadow-xl" role="dialog" aria-modal="true">
        <div class="h-14 px-5 border-b border-line flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold tracking-tight text-ink truncate">${escapeHtml(title)}</h3>
          <button type="button" data-close class="${btnClass('ghost', 'icon-sm')} -mr-2" aria-label="Close">${icon('x', 18)}</button>
        </div>
        <div class="p-5" data-body>${body}</div>
        ${footer ? `<div class="h-16 px-5 border-t border-line flex items-center justify-end gap-2" data-footer>${footer}</div>` : ''}
      </div>
    </div>`;
  document.body.appendChild(root);
  document.body.classList.add('overflow-hidden');

  const modal = {
    root,
    body: root.querySelector('[data-body]'),
    footer: root.querySelector('[data-footer]'),
    close() {
      const index = openModals.indexOf(modal);
      if (index >= 0) openModals.splice(index, 1);
      root.remove();
      if (!openModals.length) document.body.classList.remove('overflow-hidden');
      onClose?.();
    },
  };
  openModals.push(modal);
  root.querySelector('[data-overlay]').addEventListener('click', () => modal.close());
  root.querySelector('[data-close]').addEventListener('click', () => modal.close());
  root.querySelectorAll('[data-cancel]').forEach((b) => b.addEventListener('click', () => modal.close()));
  refreshIcons();
  root.querySelector('input:not([type=hidden]), select, textarea')?.focus();
  return modal;
}

/**
 * Ask before a destructive action. Resolves to true (confirmed) or false.
 *   if (!(await confirmDialog({ title: 'Drop course?', message: '...' }))) return;
 */
function confirmDialog({ title = 'Are you sure?', message = '', confirmText = 'Confirm', danger = true } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const modal = openModal({
      title,
      size: 'max-w-md',
      body: `
        <div class="flex gap-3">
          <div class="w-10 h-10 rounded-full ${danger ? 'bg-red-50 text-danger' : 'bg-primary-50 text-primary-600'} flex items-center justify-center shrink-0">
            ${icon(danger ? 'triangle-alert' : 'info', 20)}
          </div>
          <p class="text-sm text-slate-600 pt-2">${escapeHtml(message)}</p>
        </div>`,
      footer: `
        <button type="button" data-cancel class="${btnClass('secondary')}">Cancel</button>
        <button type="button" data-confirm class="${btnClass(danger ? 'danger' : 'primary')}">${escapeHtml(confirmText)}</button>`,
      onClose: () => { if (!answered) resolve(false); },
    });
    modal.root.querySelector('[data-confirm]').addEventListener('click', () => {
      answered = true;
      modal.close();
      resolve(true);
    });
    modal.root.querySelector('[data-confirm]').focus();
  });
}

/** Colored message in the top-right corner, gone after 3.5 s. type: success | error | info | warn */
function toast(message, type = 'success') {
  let stack = document.getElementById('toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toast-stack';
    stack.className = 'fixed top-4 right-4 z-[70] flex flex-col gap-2 w-[calc(100%-2rem)] max-w-sm pointer-events-none';
    document.body.appendChild(stack);
  }
  const colors = { success: 'bg-success', error: 'bg-danger', info: 'bg-info', warn: 'bg-warn' };
  const icons = { success: 'circle-check', error: 'circle-x', info: 'info', warn: 'triangle-alert' };
  const item = document.createElement('div');
  item.className = `pointer-events-auto rounded-lg px-4 py-3 shadow-lg text-sm text-white flex items-start gap-2 transition-all duration-300 ${colors[type] || colors.info}`;
  item.innerHTML = `${icon(icons[type] || 'info', 18, 'mt-px')}<span class="flex-1">${escapeHtml(message)}</span>`;
  stack.appendChild(item);
  refreshIcons();
  setTimeout(() => {
    item.classList.add('opacity-0', 'translate-x-4');
    setTimeout(() => item.remove(), 300);
  }, 3500);
}

// ============================================================================
// Forms
// ============================================================================

/**
 * One form field (label + input + error line).
 * opts: { name, label, type, value, required, placeholder, options:[{value,label}],
 *         min, max, step, pattern, title (pattern message), maxlength, minlength, help, disabled, rows,
 *         number: true (select value is a number), noEmpty / emptyLabel (selects), className }
 * Names with a dot ("profile.city") become nested objects in getFormValues().
 */
function field(opts) {
  const id = `f-${opts.name.replaceAll('.', '-')}-${Math.random().toString(36).slice(2, 7)}`;
  const attrs = [
    `id="${id}"`, `name="${opts.name}"`,
    opts.required ? 'required' : '', opts.disabled ? 'disabled' : '',
    opts.placeholder ? `placeholder="${escapeHtml(opts.placeholder)}"` : '',
    opts.min !== undefined ? `min="${opts.min}"` : '', opts.max !== undefined ? `max="${opts.max}"` : '',
    opts.step !== undefined ? `step="${opts.step}"` : '', opts.pattern ? `pattern="${opts.pattern}"` : '',
    opts.maxlength ? `maxlength="${opts.maxlength}"` : '', opts.minlength ? `minlength="${opts.minlength}"` : '',
    opts.number ? 'data-number' : '', opts.title ? `title="${escapeHtml(opts.title)}"` : '',
  ].filter(Boolean).join(' ');
  const value = opts.value ?? '';
  let control;

  if (opts.type === 'select') {
    // An empty first option ("Select…") unless noEmpty is set
    control = `<select ${attrs} class="${INPUT_CLASS}">
      ${opts.noEmpty ? '' : `<option value="">${escapeHtml(opts.emptyLabel || 'Select…')}</option>`}
      ${(opts.options || []).map((o) => `<option value="${escapeHtml(o.value)}" ${String(o.value) === String(value) ? 'selected' : ''}>${escapeHtml(o.label)}</option>`).join('')}
    </select>`;
  } else if (opts.type === 'textarea') {
    control = `<textarea ${attrs} rows="${opts.rows || 3}" class="${INPUT_CLASS} h-auto py-2">${escapeHtml(value)}</textarea>`;
  } else if (opts.type === 'checkbox') {
    return `
      <div class="mb-4 ${opts.className || ''}" data-field="${opts.name}">
        <label class="inline-flex items-center gap-2 text-sm text-ink cursor-pointer" for="${id}">
          <input type="checkbox" ${attrs} ${value ? 'checked' : ''} class="h-4 w-4 rounded border-line text-primary-600 focus:ring-primary-500">
          ${escapeHtml(opts.label)}
        </label>
        <p class="text-xs text-danger mt-1 hidden" data-error></p>
      </div>`;
  } else {
    control = `<input type="${opts.type || 'text'}" ${attrs} value="${escapeHtml(value)}" class="${INPUT_CLASS}">`;
  }

  return `
    <div class="mb-4 ${opts.className || ''}" data-field="${opts.name}">
      <label class="${LABEL_CLASS}" for="${id}">${escapeHtml(opts.label)}${opts.required ? ' <span class="text-danger">*</span>' : ''}</label>
      ${control}
      ${opts.help ? `<p class="text-xs text-muted mt-1">${escapeHtml(opts.help)}</p>` : ''}
      <p class="text-xs text-danger mt-1 hidden" data-error></p>
    </div>`;
}

/**
 * Read a form into an object.
 *   ""               -> null (optional fields)
 *   type=number      -> Number
 *   select[data-number] -> Number
 *   checkbox         -> true / false
 *   "profile.city"   -> { profile: { city } }
 */
function getFormValues(form) {
  const values = {};
  for (const element of form.elements) {
    if (!element.name || element.disabled || element.dataset.skip !== undefined) continue;
    let value;
    if (element.type === 'checkbox') value = element.checked;
    else if (element.type === 'radio') { if (!element.checked) continue; value = element.value; }
    else if (element.value.trim() === '') value = null;
    else if (element.type === 'number' || element.dataset.number !== undefined) value = Number(element.value);
    else value = element.value.trim();

    const path = element.name.split('.');
    let target = values;
    while (path.length > 1) {
      const key = path.shift();
      target[key] = target[key] || {};
      target = target[key];
    }
    target[path[0]] = value;
  }
  return values;
}

/** Show one error under a field (and color its border red). */
function setFieldError(form, name, message) {
  const wrapper = form.querySelector(`[data-field="${CSS.escape(name)}"]`);
  if (!wrapper) return false;
  const line = wrapper.querySelector('[data-error]');
  line.textContent = message;
  line.classList.remove('hidden');
  wrapper.querySelector('input, select, textarea')?.classList.add('border-danger');
  return true;
}

/** Remove all error messages from a form. */
function clearFormErrors(form) {
  form.querySelectorAll('[data-error]').forEach((line) => { line.textContent = ''; line.classList.add('hidden'); });
  form.querySelectorAll('.border-danger').forEach((el) => el.classList.remove('border-danger'));
  form.querySelector('[data-form-error]')?.classList.add('hidden');
}

/**
 * Show server errors ({email: "...", "profile.gender": "..."}) under their fields.
 * Errors without a matching field are shown in the form's general error box.
 */
function setFormErrors(form, errors = {}, generalMessage = '') {
  const leftovers = [];
  for (const [name, message] of Object.entries(errors)) {
    if (!setFieldError(form, name, message)) leftovers.push(message);
  }
  const box = form.querySelector('[data-form-error]');
  const text = leftovers.length ? leftovers.join(' ') : (Object.keys(errors).length ? '' : generalMessage);
  if (box && text) {
    box.textContent = text;
    box.classList.remove('hidden');
  }
}

/**
 * Client-side validation using the browser's built-in rules (required, min, max,
 * pattern, type=email ...) plus an optional extra check: (values) => ({field: msg}).
 * Returns true if the form is valid.
 */
function validateForm(form, extraCheck) {
  clearFormErrors(form);
  let valid = true;
  for (const element of form.elements) {
    if (!element.name || element.disabled || element.offsetParent === null) continue;   // skip hidden steps
    if (!element.checkValidity()) {
      valid = false;
      const message = element.validity.patternMismatch && element.title ? element.title : element.validationMessage;
      setFieldError(form, element.name, message);
    }
  }
  if (valid && extraCheck) {
    const errors = extraCheck(getFormValues(form)) || {};
    for (const [name, message] of Object.entries(errors)) {
      valid = false;
      setFieldError(form, name, message);
    }
  }
  if (!valid) form.querySelector('.border-danger')?.focus();
  return valid;
}

/** Disable a button and show a small spinner text while a request runs. */
function setBusy(button, busy, busyText = 'Saving…') {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"></span>${busyText}`;
  } else {
    button.disabled = false;
    if (button.dataset.label) button.innerHTML = button.dataset.label;
    refreshIcons();
  }
}

/**
 * A modal with a form: validates on submit (Enter works), sends the request,
 * shows server errors under the fields, closes on success.
 *
 *   formModal({
 *     title: 'New room', fieldsHtml: field(...) + field(...), submitText: 'Create',
 *     onSubmit: async (values) => api.post('/rooms', values),   // throw -> errors shown
 *     onSuccess: (result) => list.reload(),
 *     extraCheck: (values) => ({}),
 *   })
 */
function formModal({ title, fieldsHtml, submitText = 'Save', size = 'max-w-lg', onSubmit, onSuccess, extraCheck, transform }) {
  const formId = `form-${Math.random().toString(36).slice(2, 8)}`;
  const modal = openModal({
    title,
    size,
    body: `
      <form id="${formId}" novalidate>
        <div data-form-error class="hidden mb-4 rounded-lg bg-red-50 text-danger text-xs px-3 py-2"></div>
        ${fieldsHtml}
      </form>`,
    footer: `
      <button type="button" data-cancel class="${btnClass('secondary')}">Cancel</button>
      <button type="submit" form="${formId}" data-submit class="${btnClass('primary')}">${escapeHtml(submitText)}</button>`,
  });
  const form = modal.root.querySelector('form');
  const submitButton = modal.root.querySelector('[data-submit]');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!validateForm(form, extraCheck)) return;
    let values = getFormValues(form);
    if (transform) values = transform(values);
    setBusy(submitButton, true);
    try {
      const result = await onSubmit(values);
      modal.close();
      onSuccess?.(result);
    } catch (error) {
      if (error instanceof ApiError) setFormErrors(form, error.errors, error.message);
      setBusy(submitButton, false);
    }
  });
  return { modal, form };
}

// ============================================================================
// Shared data loaders (cached for the life of the page)
// ============================================================================
const dataCache = {};

function cached(key, loader) {
  if (!dataCache[key]) dataCache[key] = loader().catch((error) => { delete dataCache[key]; throw error; });
  return dataCache[key];
}

/** All departments as [{id, code, name, ...}] */
function loadDepartments() {
  return cached('departments', () => api.get('/departments', { limit: 200, sort: 'code' }, { silent: true }).then((d) => d.items));
}

/** All semesters, newest first */
function loadSemesters() {
  return cached('semesters', () => api.get('/semesters', { limit: 200 }, { silent: true }).then((d) => d.items));
}

/** The active semester (or null) */
function loadActiveSemester() {
  return cached('active-semester', () => api.get('/semesters/active', null, { silent: true }).catch(() => null));
}

/** [{value, label}] option lists for selects */
function toOptions(items, labelFn, valueKey = 'id') {
  return items.map((item) => ({ value: item[valueKey], label: labelFn(item) }));
}

// ============================================================================
// Charts (Chart.js)
// ============================================================================
const CHART_COLORS = ['#4f6ef7', '#16a34a', '#d97706', '#dc2626', '#0891b2', '#7c3aed', '#db2777', '#65a30d', '#ea580c', '#64748b'];

/** Draw (or redraw) a Chart.js chart on a <canvas>. The old chart on that canvas is destroyed first. */
function renderChart(canvas, config) {
  if (!window.Chart || !canvas) return null;
  if (canvas._chart) canvas._chart.destroy();
  Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, sans-serif';
  Chart.defaults.color = '#64748b';
  Chart.defaults.borderColor = '#e2e8f0';
  const options = config.options || {};
  canvas._chart = new Chart(canvas, {
    ...config,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      ...options,
      // plugins LAST, so the default "no legend" survives when a chart only sets a tooltip
      plugins: { legend: { display: false }, ...(options.plugins || {}) },
    },
  });
  return canvas._chart;
}

/** Render tabs: [{key, label}] -> buttons; onChange(key) is called on click. */
function renderTabs(container, tabs, activeKey, onChange) {
  container.innerHTML = `
    <div class="flex gap-1 overflow-x-auto thin-scroll border-b border-line" role="tablist">
      ${tabs.map((tab) => `
        <button type="button" role="tab" data-tab="${tab.key}"
          class="h-10 px-4 -mb-px border-b-2 text-sm whitespace-nowrap ${tab.key === activeKey
            ? 'border-primary-600 text-primary-700 font-medium'
            : 'border-transparent text-muted hover:text-ink'}">${escapeHtml(tab.label)}</button>`).join('')}
    </div>`;
  container.querySelectorAll('[data-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      renderTabs(container, tabs, button.dataset.tab, onChange);
      onChange(button.dataset.tab);
    });
  });
}

// ============================================================================
// Drawer + detail list
// ============================================================================

/** A panel that slides in from the right (used for "detail" views). Closes like a modal. */
function openDrawer({ title, body = '', width = 'max-w-xl' } = {}) {
  const root = document.createElement('div');
  root.className = 'fixed inset-0 z-50';
  root.innerHTML = `
    <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" data-overlay></div>
    <section class="absolute inset-y-0 right-0 w-full ${width} bg-white shadow-xl flex flex-col" role="dialog" aria-modal="true">
      <div class="h-14 shrink-0 px-5 border-b border-line flex items-center justify-between gap-3">
        <h3 class="text-base font-semibold tracking-tight text-ink truncate">${escapeHtml(title)}</h3>
        <button type="button" data-close class="${btnClass('ghost', 'icon-sm')} -mr-2" aria-label="Close">${icon('x', 18)}</button>
      </div>
      <div class="flex-1 overflow-y-auto thin-scroll p-5" data-body>${body}</div>
    </section>`;
  document.body.appendChild(root);
  document.body.classList.add('overflow-hidden');
  const drawer = {
    root,
    body: root.querySelector('[data-body]'),
    close() {
      const index = openModals.indexOf(drawer);
      if (index >= 0) openModals.splice(index, 1);
      root.remove();
      if (!openModals.length) document.body.classList.remove('overflow-hidden');
    },
  };
  openModals.push(drawer);
  root.querySelector('[data-overlay]').addEventListener('click', () => drawer.close());
  root.querySelector('[data-close]').addEventListener('click', () => drawer.close());
  refreshIcons();
  return drawer;
}

/** Label/value pairs in a 2-column grid. items: [[label, valueHtml], ...] (values are HTML!) */
function definitionList(items) {
  return `
    <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
      ${items.map(([label, value]) => `
        <div class="min-w-0">
          <dt class="text-xs text-muted">${escapeHtml(label)}</dt>
          <dd class="text-sm text-ink mt-0.5 break-words">${value === null || value === undefined || value === '' ? '<span class="text-muted">—</span>' : value}</dd>
        </div>`).join('')}
    </dl>`;
}

/** Section title inside a card */
function cardTitle(title, rightHtml = '') {
  return `<div class="flex items-center justify-between gap-3 mb-4"><h3 class="text-sm font-semibold tracking-tight text-ink">${escapeHtml(title)}</h3>${rightHtml}</div>`;
}

// ============================================================================
// Invoice detail modal (used by billing.html and the student "Dues" tab)
// ============================================================================

/**
 * Show one invoice: items, payments and totals. With canPay, a
 * "Record payment" form is shown while money is still due.
 * onChange() is called after a successful payment (to refresh a list).
 */
function openInvoiceModal(invoiceId, { canPay = false, onChange } = {}) {
  const modal = openModal({
    title: 'Invoice',
    size: 'max-w-2xl',
    body: `<div class="space-y-3">${skeletonBlock('h-5 w-1/2')}${skeletonTable(4, 2)}</div>`,
  });

  async function load() {
    try {
      const invoice = await api.get(`/invoices/${invoiceId}`, null, { silent: true });
      render(invoice);
    } catch (error) {
      showError(modal.body, error, load);
    }
  }

  function render(inv) {
    modal.root.querySelector('h3').textContent = inv.invoice_no;
    const itemsRows = inv.items.map((item) => `
      <tr class="h-10 border-b border-line"><td class="px-3">${escapeHtml(item.description)}</td>
      <td class="px-3 text-right tabular-nums">${formatMoney(item.amount)}</td></tr>`).join('');
    const paymentRows = inv.payments.length
      ? inv.payments.map((p) => `
        <tr class="h-10 border-b border-line">
          <td class="px-3 whitespace-nowrap">${formatDateTime(p.paid_at)}</td>
          <td class="px-3">${badge('info', titleCase(p.method))}</td>
          <td class="px-3 text-xs text-muted">${escapeHtml(p.transaction_ref || '—')}</td>
          <td class="px-3 text-right tabular-nums">${formatMoney(p.amount)}</td></tr>`).join('')
      : '<tr><td colspan="4" class="px-3 py-4 text-center text-xs text-muted">No payments yet</td></tr>';

    const methods = ['cash', 'bank', 'bkash', 'nagad', 'card'].map((m) => ({ value: m, label: titleCase(m) }));
    const payForm = canPay && inv.due_amount > 0 ? `
      <form id="pay-form" novalidate class="mt-5 rounded-xl border border-line p-4 bg-slate-50/60">
        <p class="text-sm font-semibold text-ink mb-3">Record payment</p>
        <div data-form-error class="hidden mb-3 rounded-lg bg-red-50 text-danger text-xs px-3 py-2"></div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-x-4">
          ${field({ name: 'amount', label: 'Amount (৳)', type: 'number', value: inv.due_amount_taka, required: true, min: 0.01, max: inv.due_amount_taka, step: 0.01 })}
          ${field({ name: 'method', label: 'Method', type: 'select', required: true, value: 'cash', noEmpty: true, options: methods })}
          ${field({ name: 'transaction_ref', label: 'Transaction ref', placeholder: 'Not needed for cash', maxlength: 50 })}
        </div>
        <div class="flex justify-end"><button type="submit" class="${btnClass('primary')}">${icon('check', 16)} Record payment</button></div>
      </form>` : '';

    const totals = [['Total', inv.total_amount, 'text-ink'], ['Paid', inv.paid_amount, 'text-success'],
      ['Due', inv.due_amount, inv.due_amount ? 'text-danger' : 'text-ink']];
    modal.body.innerHTML = `
      <div class="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <p class="text-sm font-medium text-ink">${escapeHtml(inv.student_name)} <span class="text-muted font-normal">· ${escapeHtml(inv.student_code)}</span></p>
          <p class="text-xs text-muted mt-1">Semester ${escapeHtml(inv.semester_code)} · Issued ${formatDate(inv.issued_at)} · Due ${formatDate(inv.due_date)}</p>
        </div>
        ${badge(inv.status)}
      </div>
      <div class="grid grid-cols-3 gap-3 mb-5">
        ${totals.map(([label, value, color]) => `
          <div class="rounded-lg border border-line p-3"><p class="text-xs text-muted">${label}</p>
          <p class="text-sm sm:text-base font-semibold tabular-nums ${color}">${formatMoney(value)}</p></div>`).join('')}
      </div>
      <p class="text-xs uppercase tracking-wide text-muted mb-2">Items</p>
      <table class="w-full text-sm mb-5"><tbody>${itemsRows}
        <tr class="h-10"><td class="px-3 font-medium text-ink">Total</td><td class="px-3 text-right font-semibold tabular-nums text-ink">${formatMoney(inv.total_amount)}</td></tr>
      </tbody></table>
      <p class="text-xs uppercase tracking-wide text-muted mb-2">Payments</p>
      <div class="overflow-x-auto"><table class="w-full text-sm"><tbody>${paymentRows}</tbody></table></div>
      ${payForm}`;
    refreshIcons();

    const form = modal.body.querySelector('#pay-form');
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const ok = validateForm(form, (v) => (v.method !== 'cash' && !v.transaction_ref
        ? { transaction_ref: 'Required for non-cash payments' } : {}));
      if (!ok) return;
      const values = getFormValues(form);
      const button = form.querySelector('[type=submit]');
      setBusy(button, true);
      try {
        await api.post('/payments', { invoice_id: inv.id, ...values });
        toast(`Payment of ${formatMoney(Math.round(values.amount * 100))} recorded`);
        onChange?.();
        load();
      } catch (error) {
        if (error instanceof ApiError) setFormErrors(form, error.errors, error.message);
        setBusy(button, false);
      }
    });
  }

  load();
  return modal;
}
