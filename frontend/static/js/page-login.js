/*
 * page-login.js: the sign-in form.
 */

// Already logged in? Go straight to the app.
if (getToken() && getUser()) {
  window.location.replace(homePageFor(getUser().role));
}

const DEMO_ACCOUNTS = [
  { email: 'admin@ucms.edu', role: 'Admin', iconName: 'shield-check' },
  { email: 'teacher@ucms.edu', role: 'Teacher', iconName: 'users' },
  { email: 'student@ucms.edu', role: 'Student', iconName: 'graduation-cap' },
  { email: 'accountant@ucms.edu', role: 'Accountant', iconName: 'wallet' },
];

const form = document.getElementById('login-form');
const errorBox = document.getElementById('login-error');
const button = document.getElementById('login-button');

/** Show a message in the red error area above the form. */
function showLoginError(message) {
  errorBox.innerHTML = `${icon('circle-alert', 16, 'mt-px')}<span>${escapeHtml(message)}</span>`;
  errorBox.classList.remove('hidden');
  refreshIcons();
}

if (queryParam('expired')) showLoginError('Your session has expired. Please sign in again.');

// Demo account buttons fill in the form
document.getElementById('demo-accounts').innerHTML = DEMO_ACCOUNTS.map((account) => `
  <button type="button" data-email="${account.email}"
          class="flex items-center gap-2 h-9 px-3 rounded-lg border border-line bg-white text-left hover:bg-slate-50">
    <span class="text-primary-600">${icon(account.iconName, 16)}</span>
    <span class="min-w-0"><span class="block text-xs font-medium text-ink">${account.role}</span></span>
  </button>`).join('');
document.querySelectorAll('[data-email]').forEach((demo) => {
  demo.addEventListener('click', () => {
    form.email.value = demo.dataset.email;
    form.password.value = 'Password123!';
    form.password.focus();
  });
});
refreshIcons();

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.classList.add('hidden');
  if (!validateForm(form)) return;

  setBusy(button, true, 'Signing in…');
  try {
    // silent: the error is shown in the form, not as a toast
    const result = await api.post('/auth/login', getFormValues(form), { silent: true });
    saveAuth(result);
    window.location.replace(homePageFor(result.role));
  } catch (error) {
    showLoginError(error.message || 'Login failed');
    setBusy(button, false);
    form.password.select();
  }
});
