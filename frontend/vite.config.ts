import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@app': fileURLToPath(new URL('./src/app', import.meta.url)),
      '@state': fileURLToPath(new URL('./src/state', import.meta.url)),
      '@lib': fileURLToPath(new URL('./src/lib', import.meta.url)),
      '@views': fileURLToPath(new URL('./src/views', import.meta.url)),
      '@charts': fileURLToPath(new URL('./src/charts', import.meta.url)),
      '@export': fileURLToPath(new URL('./src/export', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
  server: {
    // Dev-only convenience so the default VITE_API_BASE='/api' in
    // lib/api/client.ts reaches `hub serve` (FastAPI on :8000, routes
    // mounted at root per spec §3's literal endpoint list, no /api
    // prefix). Prod deploys front the API at whatever VITE_API_BASE points to.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
