/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

declare const process: { env: Record<string, string | undefined> } // avoids a @types/node dependency

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': process.env.API_PROXY ?? 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
  },
})