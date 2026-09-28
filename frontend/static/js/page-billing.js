/*
 * page-billing.js: Fee Structures · Invoices · Payments (admin, accountant).
 * Money arrives as INTEGER paisa and is always shown with formatMoney().
 * Forms send taka (e.g. 1500.50); the API converts to paisa.
 */

const FEE_TYPES = ['tuition', 'admission', 'lab', 'library', 'exam', 'late_fine'];
const PAYMENT_METHODS = ['cash', 'bank', 'bkash', 'nagad', 'card'];
const BILLING_TABS = [
  { key: 'invoices', label: 'Invoices' },
  { key: 'payments', label: 'Payments' },
  { key: 'fees', label: 'Fee Structures' },
];

async function initBilling({ content }) {
  content.innerHTML = `
    ${pageHeader('Billing', 'Fee structures, invoices and payments.')}
    <div id="tabs"></div>
    <div id="panel" class="mt-4">${card(skeletonTable(8, 6), 'p-0')}</div>`;

  let semesters, departments, active;
  try {
    [semesters, departments, active] = await Promise.all([loadSemesters(), loadDepartments(), loadActiveSemester()]);
  } catch (error) {
    showError(document.getElementById('panel'), error, () => initBilling({ content }));
    return;
  }
  const ctx = {
    semesterOptions: toOptions(semesters, (s) => `${s.code}${s.is_active ? ' (active)' : ''}`),
    departmentOptions: toOptions(departments, (d) => d.code),
    activeId: active ? active.id : '',
  };

  const start = BILLING_TABS.some((t) => t.key === location.hash.slice(1)) ? location.hash.slice(1) : 'invoices';
  const showTab = (key) => {
    history.replaceState(null, '', `#${key}`);
    ({ invoices: showInvoices, payments: showPayments, fees: showFees })[key](document.getElementById('panel'), ctx);
  };
  renderTabs(document.getElementById('tabs'), BILLING_TABS, start, showTab);
  showTab(start);
}

// -------------------------------------------------------------------- Invoices
function showInvoices(panel, ctx) {
  const list = createListView({
    mount: panel,
    endpoint: '/invoices',
    searchPlaceholder: 'Search invoice no, student…',
    defaultSort: 'due_amount',
    defaultOrder: 'desc',
    initialFilters: { semester_id: ctx.activeId },
    filters: [
      { name: 'semester_id', label: 'Semester', options: ctx.semesterOptions },
      { name: 'status', label: 'Status', options: ['unpaid', 'partial', 'paid', 'overdue'].map((s) => ({ value: s, label: titleCase(s) })) },
      { name: 'department_id', label: 'Department', options: ctx.departmentOptions },
    ],
    toolbarHtml: `<button type="button" id="generate" class="${btnClass('primary')}">${icon('file-text', 16)} Generate invoices</button>`,
    emptyIcon: 'file-text',
    emptyTitle: 'No invoices',
    columns: [
      { key: 'invoice_no', label: 'Invoice', sortable: true, className: 'font-medium text-ink whitespace-nowrap' },
      { key: 'student_name', label: 'Student', sortable: true, render: (r) => `<p class="text-ink">${escapeHtml(r.student_name)}</p><p class="text-xs text-muted">${escapeHtml(r.student_code)}</p>` },
      { key: 'semester_code', label: 'Semester', sortable: true },
      { key: 'total_amount', label: 'Total', sortable: true, className: 'text-right tabular-nums whitespace-nowrap', headerClass: 'text-right', render: (r) => formatMoney(r.total_amount) },
      { key: 'paid_amount', label: 'Paid', sortable: true, className: 'text-right tabular-nums whitespace-nowrap', headerClass: 'text-right', render: (r) => formatMoney(r.paid_amount) },
      { key: 'due_amount', label: 'Due', sortable: true, className: 'text-right tabular-nums whitespace-nowrap', headerClass: 'text-right',
        render: (r) => `<span class="${r.due_amount ? 'font-semibold text-ink' : 'text-muted'}">${formatMoney(r.due_amount)}</span>` },
      { key: 'due_date', label: 'Due date', sortable: true, className: 'whitespace-nowrap', render: (r) => formatDate(r.due_date) },
      { key: 'status', label: 'Status', sortable: true, render: (r) => badge(r.status) },
    ],
    onRowClick: (row) => openInvoiceModal(row.id, { canPay: true, onChange: () => list.reload() }),
  });

  document.getElementById('generate').addEventListener('click', () => {
    formModal({
      title: 'Generate invoices',
      submitText: 'Generate',
      fieldsHtml: `
        <p class="text-xs text-muted mb-4">Creates an invoice for every student enrolled in the semester who does not have one yet.
          Department-specific fees override the general fees (see Fee Structures).</p>
        ${field({ name: 'semester_id', label: 'Semester', type: 'select', number: true, required: true, value: ctx.activeId, options: ctx.semesterOptions })}`,
      onSubmit: (values) => api.post('/invoices/generate', values),
      onSuccess: (result) => {
        toast(result.created ? `${result.created} invoice(s) generated` : 'Every enrolled student already has an invoice', result.created ? 'success' : 'info');
        list.reload();
      },
    });
  });
}

// -------------------------------------------------------------------- Payments
function showPayments(panel, ctx) {
  createListView({
    mount: panel,
    endpoint: '/payments',
    searchPlaceholder: 'Search invoice, student, reference…',
    defaultSort: 'paid_at',
    defaultOrder: 'desc',
    initialFilters: { semester_id: ctx.activeId },
    filters: [
      { name: 'semester_id', label: 'Semester', options: ctx.semesterOptions },
      { name: 'method', label: 'Method', options: PAYMENT_METHODS.map((m) => ({ value: m, label: titleCase(m) })) },
    ],
    emptyIcon: 'wallet',
    emptyTitle: 'No payments',
    columns: [
      { key: 'paid_at', label: 'Paid at', sortable: true, className: 'whitespace-nowrap', render: (r) => formatDateTime(r.paid_at) },
      { key: 'invoice_no', label: 'Invoice', sortable: true, className: 'font-medium text-ink whitespace-nowrap' },
      { key: 'student_code', label: 'Student', sortable: true, render: (r) => `<p class="text-ink">${escapeHtml(r.student_name)}</p><p class="text-xs text-muted">${escapeHtml(r.student_code)}</p>` },
      { key: 'method', label: 'Method', sortable: true, render: (r) => badge('info', titleCase(r.method)) },
      { key: 'transaction_ref', label: 'Reference', className: 'text-xs text-muted', render: (r) => escapeHtml(r.transaction_ref || '—') },
      { key: 'amount', label: 'Amount', sortable: true, className: 'text-right tabular-nums font-medium text-ink whitespace-nowrap', headerClass: 'text-right', render: (r) => formatMoney(r.amount) },
      { key: 'received_by_email', label: 'Received by', className: 'text-xs text-muted' },
    ],
    onRowClick: (row) => openInvoiceModal(row.invoice_id),
  });
}

// ---------------------------------------------------------------- Fee structures
function showFees(panel, ctx) {
  const list = createListView({
    mount: panel,
    endpoint: '/fee-structures',
    searchPlaceholder: 'Search fee type…',
    defaultSort: 'semester_code',
    initialFilters: { semester_id: ctx.activeId },
    filters: [
      { name: 'semester_id', label: 'Semester', options: ctx.semesterOptions },
      { name: 'department_id', label: 'Department', options: ctx.departmentOptions },
    ],
    toolbarHtml: `<button type="button" id="new-fee" class="${btnClass('primary')}">${icon('plus', 16)} New fee</button>`,
    emptyIcon: 'wallet',
    emptyTitle: 'No fee structures',
    columns: [
      { key: 'semester_code', label: 'Semester', sortable: true },
      { key: 'department_code', label: 'Applies to', sortable: true, render: (r) => (r.department_id ? badge('info', r.department_code) : badge('completed', 'All departments')) },
      { key: 'fee_type', label: 'Fee type', sortable: true, render: (r) => `<span class="text-ink">${escapeHtml(titleCase(r.fee_type))}</span>` },
      { key: 'amount', label: 'Amount', sortable: true, className: 'text-right tabular-nums font-medium text-ink', headerClass: 'text-right', render: (r) => formatMoney(r.amount) },
    ],
  });

  document.getElementById('new-fee').addEventListener('click', () => {
    formModal({
      title: 'New fee',
      submitText: 'Create fee',
      fieldsHtml: `
        ${field({ name: 'semester_id', label: 'Semester', type: 'select', number: true, required: true, value: ctx.activeId, options: ctx.semesterOptions })}
        ${field({ name: 'department_id', label: 'Department', type: 'select', number: true, emptyLabel: 'All departments', options: ctx.departmentOptions,
                  help: 'A department fee replaces the "all departments" fee of the same type' })}
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
          ${field({ name: 'fee_type', label: 'Fee type', type: 'select', required: true, options: FEE_TYPES.map((t) => ({ value: t, label: titleCase(t) })) })}
          ${field({ name: 'amount', label: 'Amount (৳)', type: 'number', required: true, min: 0, step: 0.01, placeholder: '1500.50' })}
        </div>`,
      onSubmit: (values) => api.post('/fee-structures', values),
      onSuccess: (saved) => { toast(`${titleCase(saved.fee_type)} fee of ${formatMoney(saved.amount)} created`); list.reload(); },
    });
  });
}

// ---------------------------------------------------------------------------
// Start the page. This is at the BOTTOM on purpose: every constant and function
// above exists by now (a `const` used before its line throws a ReferenceError).
// ---------------------------------------------------------------------------
const session = startPage('billing', 'Billing');
if (session) initBilling(session);
