/** @type {import('tailwindcss').Config} */
// Clinical / trust-forward palette. Primary is a deep teal-blue used sparingly
// as the "medical action" color. Accent is a warmer teal for positive/healthy
// states. Semantic tokens (--surface, --border, --muted-fg) live in
// globals.css and are used through classes like bg-surface, text-muted-fg.
// The palette-scale colors below are kept for direct fine-tuning where
// semantic tokens don't fit (charts, custom badges).
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens — always reference these for surfaces + text.
        // Values come from the CSS variables in globals.css.
        surface: 'hsl(var(--surface) / <alpha-value>)',
        'surface-2': 'hsl(var(--surface-2) / <alpha-value>)',
        border: 'hsl(var(--border) / <alpha-value>)',
        'muted-fg': 'hsl(var(--muted-fg) / <alpha-value>)',
        'strong-fg': 'hsl(var(--strong-fg) / <alpha-value>)',

        // Primary — clinical teal-blue. 600 is the workhorse for buttons/links.
        primary: {
          50: '#eff8fb',
          100: '#d5edf5',
          200: '#a8dae9',
          300: '#71c1d8',
          400: '#3ba1c1',
          500: '#1f83a6',
          600: '#0e6a8b',   // ← default action color
          700: '#0c5772',
          800: '#0e485e',
          900: '#0f3d4f',
        },
        // Accent — mint-teal for positive states ("verified", "healthy").
        accent: {
          50: '#effcf6',
          100: '#d7f7e6',
          200: '#b0eecf',
          300: '#7bdcb1',
          400: '#42c48d',
          500: '#1eab72',
          600: '#128a5c',
          700: '#106e4c',
          800: '#10573e',
          900: '#0f4834',
        },
        // Severity tokens for clinical badges.
        severity: {
          critical: '#c02323',
          high: '#e26a1e',
          moderate: '#c98b0a',
          low: '#5a7d8c',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['Merriweather', 'Georgia', 'serif'],
      },
      fontSize: {
        // Tighter tabular sizes for vitals numbers.
        'vital-lg': ['2rem', { lineHeight: '2.25rem', letterSpacing: '-0.02em', fontWeight: '600' }],
        'vital-md': ['1.375rem', { lineHeight: '1.625rem', letterSpacing: '-0.01em', fontWeight: '600' }],
      },
      borderRadius: {
        DEFAULT: '0.5rem',
        lg: '0.625rem',
        xl: '0.75rem',
      },
      boxShadow: {
        // Softer, single-direction — clinical, not playful.
        card: '0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)',
        'card-hover': '0 2px 6px rgba(15, 23, 42, 0.06), 0 4px 12px rgba(15, 23, 42, 0.08)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'pulse-soft': 'pulseSoft 2s infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
      },
    },
  },
  plugins: [],
}
