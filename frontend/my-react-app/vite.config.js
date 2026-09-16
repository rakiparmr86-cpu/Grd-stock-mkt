import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 collides with another project some contributors run alongside
    // this one; pick a less common port so both can run at once. Vite still
    // auto-increments from here if 5170 itself is taken.
    port: 5170,
  },
})
