/*
 * auth.js: login state in localStorage + page access rules.
 *
 * After login we store the JWT and the user object. Every API call sends
 * the token (see api.js). Which pages each role may open is defined ONCE in
 * NAV_SECTIONS (components.js) and used both for the sidebar and for access checks.
 */

const TOKEN_KEY = 'ucms_token';
const USER_KEY = 'ucms_user';

/** Save the login response: {access_token, user, ...} */
function saveAuth(loginResponse) {
  localStorage.setItem(TOKEN_KEY, loginResponse.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(loginResponse.user));
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

/** The stored user object, or null. */
function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
  } catch {
    return null;
  }
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/** Log out and go to the login page. */
function logout() {
  clearAuth();
  window.location.href = '/pages/login.html';
}

/** The first page a role sees after login. */
function homePageFor(role) {
  return '/pages/dashboard.html';
}

/**
 * Make sure someone is logged in. If not, go to the login page.
 * Returns the user, or null while redirecting.
 */
function requireAuth() {
  const user = getUser();
  if (!getToken() || !user) {
    window.location.href = '/pages/login.html';
    return null;
  }
  return user;
}

/** True if the user's role is in the list. */
function hasRole(user, roles) {
  return Boolean(user) && roles.includes(user.role);
}

/**
 * Make sure the user is logged in AND has one of the roles.
 * Returns the user, or null if they are not allowed. The page then shows a
 * "no access" message instead of its content.
 */
function requireRole(roles) {
  const user = requireAuth();
  if (!user) return null;
  return hasRole(user, roles) ? user : null;
}
