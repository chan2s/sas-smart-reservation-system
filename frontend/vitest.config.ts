import path from 'node:path'
import { defineConfig } from 'vitest/config'

/**
 * Test-only config.
 *
 * Deliberately separate from vite.config.ts: the PWA plugin (and its whole
 * Workbox build) has no business running during unit tests. Only the `@` alias
 * and the jsdom environment are needed here.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['./src/test-setup.ts'],
  },
})
