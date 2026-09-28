/*
 * page-audit-log.js: history written by the audit TRIGGERS (admin only).
 * Each row stores the old and new version of a record as JSON; the viewer
 * compares them field by field and highlights what changed.
 */

function initAuditLog({ content }) {
  content.innerHTML = pageHeader('Audit log', 'Every INSERT, UPDATE and DELETE on enrollments and payments, recorded automatically by database triggers.') + '<div id="list"></div>';

  const extraInputs = `
    <input type="number" id="record-id" min="1" placeholder="Record id" class="${INPUT_CLASS} sm:w-28" aria-label="Record id">
    <input type="date" id="date-from" class="${INPUT_CLASS} sm:w-40" aria-label="From date" title="From">
    <input type="date" id="date-to" class="${INPUT_CLASS} sm:w-40" aria-label="To date" title="To">`;

  const list = createListView({
    mount: document.getElementById('list'),
    endpoint: '/audit-logs',
    searchPlaceholder: 'Search user or data…',
    defaultSort: 'id',
    defaultOrder: 'desc',
    filters: [
      { name: 'table_name', label: 'Table', options: [{ value: 'enrollments', label: 'Enrollments' }, { value: 'payments', label: 'Payments' }] },
      { name: 'action', label: 'Action', options: ['INSERT', 'UPDATE', 'DELETE'].map((a) => ({ value: a, label: a })) },
    ],
    toolbarHtml: extraInputs,
    extraParams: () => ({
      record_id: document.getElementById('record-id').value,
      date_from: document.getElementById('date-from').value,
      date_to: document.getElementById('date-to').value,
    }),
    emptyIcon: 'shield-check',
    emptyTitle: 'No audit entries',
    columns: [
      { key: 'id', label: '#', sortable: true, className: 'tabular-nums text-muted' },
      { key: 'changed_at', label: 'When', sortable: true, className: 'whitespace-nowrap', render: (r) => formatDateTime(r.changed_at) },
      { key: 'table_name', label: 'Table', sortable: true, render: (r) => `<span class="font-medium text-ink">${escapeHtml(r.table_name)}</span>` },
      { key: 'record_id', label: 'Record', sortable: true, className: 'tabular-nums' },
      { key: 'action', label: 'Action', sortable: true, render: (r) => badge(r.action, r.action) },
      { key: 'changed_by_email', label: 'By', className: 'text-xs', render: (r) => escapeHtml(r.changed_by_email || 'system') },
      { key: 'changes', label: 'Changed fields', render: (r) => {
        const keys = changedKeys(r);
        return keys.length ? `<span class="text-xs text-muted">${escapeHtml(keys.slice(0, 4).join(', '))}${keys.length > 4 ? ` +${keys.length - 4}` : ''}</span>` : '—';
      } },
      { key: 'view', label: '', className: 'text-right', render: () => rowAction('view', 'eye', 'View changes') },
    ],
    onRowClick: (row) => openDiff(row),
    onAction: (action, row) => openDiff(row),
  });

  ['record-id', 'date-from', 'date-to'].forEach((id) => {
    document.getElementById(id).addEventListener('change', () => { list.state.page = 1; list.reload(); });
  });
}

/** Keys whose value differs between old_data and new_data (all keys for INSERT/DELETE). */
function changedKeys(row) {
  const oldData = row.old_data || {};
  const newData = row.new_data || {};
  if (!row.old_data || !row.new_data) return Object.keys(row.new_data || row.old_data || {});
  return Object.keys({ ...oldData, ...newData }).filter((k) => JSON.stringify(oldData[k]) !== JSON.stringify(newData[k]));
}

/** Side-by-side JSON diff. */
function openDiff(row) {
  const oldData = row.old_data || {};
  const newData = row.new_data || {};
  const keys = Object.keys({ ...oldData, ...newData });
  const changed = new Set(changedKeys(row));
  const show = (value) => (value === undefined ? '<span class="text-slate-300">—</span>'
    : value === null ? '<span class="text-muted italic">null</span>' : escapeHtml(JSON.stringify(value)));

  openModal({
    title: `${row.action} · ${row.table_name} #${row.record_id}`,
    size: 'max-w-3xl',
    body: `
      <div class="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted mb-4">
        <span>When: <span class="text-ink">${formatDateTime(row.changed_at)}</span></span>
        <span>By: <span class="text-ink">${escapeHtml(row.changed_by_email || 'system')}</span></span>
        <span>Changed fields: <span class="text-ink">${changed.size}</span></span>
      </div>
      <div class="border border-line rounded-lg overflow-hidden">
        <table class="w-full text-sm">
          <thead><tr class="h-10 bg-slate-50 text-xs uppercase text-muted">
            <th class="px-3 text-left font-medium">Field</th><th class="px-3 text-left font-medium">Old</th><th class="px-3 text-left font-medium">New</th></tr></thead>
          <tbody>
            ${keys.map((k) => `
              <tr class="h-10 border-t border-line ${changed.has(k) && row.action === 'UPDATE' ? 'diff-changed' : ''}">
                <td class="px-3 font-medium text-ink whitespace-nowrap">${escapeHtml(k)}</td>
                <td class="px-3 font-mono text-xs break-all ${changed.has(k) && row.action === 'UPDATE' ? 'text-danger line-through' : ''}">${show(oldData[k] === undefined && !row.old_data ? undefined : oldData[k])}</td>
                <td class="px-3 font-mono text-xs break-all ${changed.has(k) && row.action === 'UPDATE' ? 'text-success font-medium' : ''}">${show(newData[k] === undefined && !row.new_data ? undefined : newData[k])}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <details class="mt-4">
        <summary class="text-xs text-muted cursor-pointer select-none">Raw JSON (as stored by json_object() in the trigger)</summary>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
          <pre class="json text-[11px] bg-slate-50 border border-line rounded-lg p-3">${escapeHtml(JSON.stringify(row.old_data, null, 2))}</pre>
          <pre class="json text-[11px] bg-slate-50 border border-line rounded-lg p-3">${escapeHtml(JSON.stringify(row.new_data, null, 2))}</pre>
        </div>
      </details>`,
  });
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('audit-log', 'Audit Log');
if (session) initAuditLog(session);
