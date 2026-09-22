import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        'surface-strong': 'var(--color-surface-strong)',
        'surface-3': 'var(--surface-3)',
        border: 'var(--color-border)',
        'border-strong': 'var(--border-strong)',
        text: 'var(--color-text)',
        'text-muted': 'var(--color-text-muted)',
        faint: 'var(--faint)',
        primary: 'var(--color-primary)',
        accent: 'var(--color-accent)',
        ring: 'var(--color-ring)',
        // R14/R18/R20 语义色三件套(bg / fg / border)
        blue: { bg: 'var(--blue-bg)', fg: 'var(--blue-tx)', border: 'var(--blue-bd)' },
        green: { bg: 'var(--green-bg)', fg: 'var(--green-tx)', border: 'var(--green-bd)' },
        amber: { bg: 'var(--amber-bg)', fg: 'var(--amber-tx)', border: 'var(--amber-bd)' },
        red: { bg: 'var(--red-bg)', fg: 'var(--red-tx)', border: 'var(--red-bd)' },
        violet: { bg: 'var(--violet-bg)', fg: 'var(--violet-tx)', border: 'var(--violet-bd)' },
        zinc: { bg: 'var(--zinc-bg)', fg: 'var(--zinc-tx)', border: 'var(--zinc-bd)' },
        term: { bg: 'var(--term-bg)', border: 'var(--term-bd)', tx: 'var(--term-tx)', dim: 'var(--term-dim)' },
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        display: 'var(--font-display)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        xs: 'var(--text-xs)',
        sm: 'var(--text-sm)',
        base: 'var(--text-base)',
        lg: 'var(--text-lg)',
        xl: 'var(--text-xl)',
        '2xl': 'var(--text-2xl)',
        '3xl': 'var(--text-3xl)',
        '4xl': 'var(--text-4xl)',
        '5xl': 'var(--text-5xl)',
      },
      spacing: {
        '1': 'var(--space-1)',
        '2': 'var(--space-2)',
        '3': 'var(--space-3)',
        '4': 'var(--space-4)',
        '6': 'var(--space-6)',
        '8': 'var(--space-8)',
        '12': 'var(--space-12)',
        '16': 'var(--space-16)',
        '24': 'var(--space-24)',
      },
      transitionTimingFunction: {
        standard: 'var(--ease-standard)',
      },
    },
  },
  plugins: [],
} satisfies Config
