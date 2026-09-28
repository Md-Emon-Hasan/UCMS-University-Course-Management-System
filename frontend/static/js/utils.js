/*
 * utils.js: small helper functions used by every page.
 * Plain functions only: formatting, escaping, dates, CSV and URL helpers.
 */

/**
 * Format money stored as INTEGER paisa into taka text: 150050 -> "৳1,500.50".
 * We never divide into a float for the paisa part: taka = floor(p / 100),
 * paisa = p % 100, so no rounding error can appear.
 */
function formatMoney(paisa) {
  if (paisa === null || paisa === undefined || paisa === '') return '—';
  const value = Math.round(Number(paisa));
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  const taka = Math.floor(abs / 100).toLocaleString('en-US');
  const cents = String(abs % 100).padStart(2, '0');
  return `${sign}৳${taka}.${cents}`;
}

/** "2026-03-09" or "2026-03-09 10:15:00" -> "9 Mar 2026" */
function formatDate(value) {
  if (!value) return '—';
  const date = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** "2026-03-09 10:15:00" -> "9 Mar 2026, 10:15" (database timestamps are UTC) */
function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(String(value).replace(' ', 'T') + (String(value).length === 19 ? 'Z' : ''));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Number with thousands separators; "—" for empty values. */
function formatNumber(value, decimals = 0) {
  if (value === null || value === undefined || value === '') return '—';
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** 81.456 -> "81.5%" */
function formatPercent(value, decimals = 1) {
  if (value === null || value === undefined || value === '') return '—';
  return `${Number(value).toFixed(decimals)}%`;
}

/** Today's date as "YYYY-MM-DD" in local time (for <input type="date">). */
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Wait until the user stops typing before running fn (used for search boxes, 300 ms).
 */
function debounce(fn, wait = 300) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

/**
 * Escape text before putting it into innerHTML. This stops HTML/JS injection:
 * a student named "<img onerror=...>" is shown as text, not run as code.
 */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

/** "assistant_professor" -> "Assistant Professor" */
function titleCase(value) {
  if (!value) return '';
  return String(value).replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** "Hasan Kabir" -> "HK" (for avatar circles) */
function initials(name) {
  if (!name) return '?';
  const parts = String(name).trim().split(/\s+/);
  return ((parts[0]?.[0] || '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

/** Read a value from the page URL: ?id=5 -> queryParam('id') === '5' */
function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

/** Day numbers used by the database: 0 = Sunday ... 6 = Saturday */
const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** "09:30" -> minutes since midnight (570) */
function timeToMinutes(text) {
  const [h, m] = String(text).split(':').map(Number);
  return h * 60 + m;
}

/** The university grading scale (same as app/services/grading_service.py) */
const GRADE_SCALE = [
  [80, 4.0, 'A+'], [75, 3.75, 'A'], [70, 3.5, 'A-'], [65, 3.25, 'B+'], [60, 3.0, 'B'],
  [55, 2.75, 'B-'], [50, 2.5, 'C+'], [45, 2.25, 'C'], [40, 2.0, 'D'], [0, 0.0, 'F'],
];

/** 72.4 -> {point: 3.5, letter: 'A-'} (used for the live preview in the gradebook) */
function marksToGrade(marks) {
  for (const [min, point, letter] of GRADE_SCALE) {
    if (marks >= min) return { point, letter };
  }
  return { point: 0, letter: 'F' };
}

/**
 * Download rows as a CSV file.
 * columns: [{key: 'student_code', label: 'Code'}, ...]
 */
function downloadCSV(filename, rows, columns) {
  const quote = (v) => {
    const text = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const lines = [columns.map((c) => quote(c.label)).join(',')];
  for (const row of rows) {
    lines.push(columns.map((c) => quote(typeof c.value === 'function' ? c.value(row) : row[c.key])).join(','));
  }
  const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

/** Pick a stable color for a text (used for routine blocks): same course, same color. */
const BLOCK_COLORS = [
  'bg-primary-50 border-primary-500 text-primary-700',
  'bg-emerald-50 border-emerald-500 text-emerald-800',
  'bg-amber-50 border-amber-500 text-amber-800',
  'bg-rose-50 border-rose-500 text-rose-800',
  'bg-cyan-50 border-cyan-600 text-cyan-800',
  'bg-violet-50 border-violet-500 text-violet-800',
  'bg-lime-50 border-lime-600 text-lime-800',
  'bg-orange-50 border-orange-500 text-orange-800',
];
function colorFor(text) {
  let hash = 0;
  for (const ch of String(text)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return BLOCK_COLORS[hash % BLOCK_COLORS.length];
}
