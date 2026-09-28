/*
 * api.js: one small wrapper around fetch() for every call to the backend.
 *
 *   const page = await api.get('/students', { page: 1, search: 'rahman' });
 *   await api.post('/departments', { name: 'Physics', code: 'PHY' });
 *
 * - Adds "Authorization: Bearer <token>" automatically.
 * - 401 (not logged in / expired) -> clear the token and go to the login page.
 * - Any other error -> a red toast, then throws an ApiError whose .errors
 *   holds per-field messages ({email: "already registered"}) for forms.
 *   Pass { silent: true } to skip the toast (when the page shows the error itself).
 */

const API_BASE = '/api';

class ApiError extends Error {
  constructor(message, status, errors = {}) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

/** Turn {page: 1, search: ''} into "?page=1" (empty values are skipped). */
function toQueryString(params) {
  if (!params) return '';
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') query.append(key, value);
  }
  const text = query.toString();
  return text ? `?${text}` : '';
}

async function apiRequest(method, path, body, options = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(API_BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (networkError) {
    const error = new ApiError('Cannot reach the server. Is it running?', 0);
    if (!options.silent) toast(error.message, 'error');
    throw error;
  }

  // Not logged in or token expired: back to the login page (but not for the login call itself)
  if (response.status === 401 && !path.startsWith('/auth/login')) {
    clearAuth();
    window.location.href = '/pages/login.html?expired=1';
    throw new ApiError('Session expired', 401);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = (data && typeof data.detail === 'string') ? data.detail : `Request failed (${response.status})`;
    const error = new ApiError(message, response.status, (data && data.errors) || {});
    if (!options.silent) toast(message, 'error');
    throw error;
  }
  return data;
}

const api = {
  get: (path, params, options) => apiRequest('GET', path + toQueryString(params), undefined, options),
  post: (path, body, options) => apiRequest('POST', path, body ?? {}, options),
  patch: (path, body, options) => apiRequest('PATCH', path, body ?? {}, options),
  del: (path, options) => apiRequest('DELETE', path, undefined, options),
};
