/**
 * tailwind.config.js - Tailwind CSS Configuration
 *
 * Extends the default Tailwind palette with a custom slate colour scale
 * used throughout the SmartHire UI for consistent dark-mode styling.
 */

/** @type {import('tailwindcss').Config} */
export default {
  // Scan all HTML and JSX/TSX files so unused classes are purged in production
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Custom slate shades matching the app's dark UI design system
      colors: {
        slate: {
          900: '#0f172a',
          800: '#1e293b',
          700: '#334155',
          600: '#475569',
          500: '#64748b',
          400: '#94a3b8',
          300: '#cbd5e1',
          200: '#e2e8f0',
          100: '#f1f5f9',
          50: '#f8fafc',
        },
      },
    },
  },
  // No additional Tailwind plugins required
  plugins: [],
}
