import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/**/*.test.ts'],
    env: { TARO_APP_API_BASE: 'http://127.0.0.1:8000' },
  },
})