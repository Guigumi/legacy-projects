/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#08110d',
        surface: '#0d1a14',
        surface2: '#14261c',
        border: '#294334',
        accent: '#8fd8ac',
        accenthover: '#b4e8c6',
        muted: '#8eaa99',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
