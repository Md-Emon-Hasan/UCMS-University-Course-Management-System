/*
 * Design tokens for Tailwind (loaded right after the Tailwind CDN script on every page).
 * One shared file instead of 18 copies of the same inline config (see DECISIONS.md).
 */
tailwind.config = {
  theme: {
    extend: {
      colors: {
        primary: { 50: '#eef4ff', 100: '#dae4ff', 500: '#4f6ef7', 600: '#3f57e0', 700: '#3345b8' },
        ink: '#0f172a',
        muted: '#64748b',
        line: '#e2e8f0',
        success: '#16a34a',
        warn: '#d97706',
        danger: '#dc2626',
        info: '#0891b2',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
    },
  },
};
