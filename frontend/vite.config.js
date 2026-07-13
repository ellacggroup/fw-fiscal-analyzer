import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/agendas': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/analytics': 'http://localhost:8000',
      '/alerts': 'http://localhost:8000',
      '/competitive': 'http://localhost:8000',
      '/bulk-import': 'http://localhost:8000',
      '/parcels': 'http://localhost:8000',
      '/staff-reports': 'http://localhost:8000',
    }
  }
})
