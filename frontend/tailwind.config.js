/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#0b0f14',
        panel: '#111720',
        raised: '#18212c',
        line: '#303a47',
        primaryText: '#f1f5f9',
        secondaryText: '#a7b3c2',
        mutedText: '#78879a',
        accent: '#a3e635',
        gain: '#4ade80',
        loss: '#f87171',
        warning: '#fbbf24',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: { panel: '0 8px 24px rgba(0,0,0,.12)' },
    },
  },
  plugins: [],
};
