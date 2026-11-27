import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: the UI runs on :5173 and sends /api to the backend (agent-verdict serve, :8000).
// Build: `npm run build` writes dist/, which the backend serves at /.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
