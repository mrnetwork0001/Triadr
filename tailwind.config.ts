import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#07080c', 900: '#0b0d14', 850: '#10131c', 800: '#161a26', 700: '#1f2534', 600: '#2b3242' },
        signal: {
          ok: '#34d399',
          heal: '#fbbf24',
          fail: '#f87171',
          undo: '#c084fc',
          idle: '#64748b',
          live: '#38bdf8',
        },
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      animation: {
        'pulse-dot': 'pulse-dot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'sweep': 'sweep 1.4s ease-in-out infinite',
      },
      keyframes: {
        'pulse-dot': { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
        sweep: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(300%)' } },
      },
    },
  },
  plugins: [],
}
export default config
