import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
// Explicit extension: Vite's forthcoming `configLoader: 'native'` does not
// resolve extensionless imports in vite.config.ts (it currently emits a
// warning). The project sets `allowImportingTsExtensions`, so this is safe.
import { runtimeCaching } from './src/lib/pwa/cache-rules.ts'

// PWA + service-worker strategy.
//
// The app is an authenticated SPA talking to a Django API. Connectivity is an
// enhancement, never a requirement: the service worker is allowed to cache the
// static application shell and public media, and NOTHING else. Every /api/
// request is NetworkOnly in the worker — authenticated and sensitive responses
// must never be served stale, and offline reads are handled explicitly (and
// with clear "local backup" labelling) by the IndexedDB layer in
// src/lib/offline. This keeps Django the single source of truth.
export default defineConfig(({ command }) => {
  // Dev mode (npm run dev) must expose the manifest and a service worker too:
  // without them Chrome reports "No manifest detected" on localhost:5173 and
  // the app is never installable during development. The dev worker does no
  // precaching (there are no hashed build assets to precache), and runtime
  // caching is dropped entirely while serving so no dev-server/HMR response is
  // ever written to a cache. PWA caching behaviour stays production-only.
  const serving = command === 'serve'

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        // 'prompt' — never auto-reload the page under a user in the middle of a
        // reservation flow. The app shows an update prompt instead (see
        // src/hooks/usePwa.ts).
        registerType: 'prompt',
        // Registration is performed manually via the `virtual:pwa-register/react`
        // hook so we can surface update/offline-ready state in the UI.
        injectRegister: null,
        includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
        manifest: {
          id: '/',
          name: 'SAS RESERVE',
          short_name: 'SAS RESERVE',
          description:
            'Smart Web-Based Facility and Resource Reservation System for NORSU-BSC.',
          lang: 'en',
          theme_color: '#4f46e5',
          background_color: '#f8fafc',
          display: 'standalone',
          orientation: 'portrait-primary',
          start_url: '/',
          scope: '/',
          icons: [
            { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            {
              src: '/pwa-maskable-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
        workbox: {
          // Precache the application shell and build assets so the app can boot
          // offline. In production the SPA fallback stays, because Chrome's
          // installability checker requires a worker with a responding fetch
          // handler — without it, no install prompt is ever offered.
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff,woff2}'],
          // SPA navigations fall back to the precached shell...
          //
          // NOT while serving. The plugin's dev worker precaches its own copy of
          // index.html and serves every `/` navigation from that snapshot: the
          // snapshot is fetched once per worker install, and the plugin only
          // stamps a fresh (random) revision when the dev server starts. A dev
          // worker left over from an earlier configuration therefore keeps
          // serving the OUTDATED document for `/` on every reload, and Chrome
          // inspects that stale HTML — reporting "No manifest detected"
          // (Page.getAppManifest -> url "", installability error "no-manifest")
          // even though the dev server injects the manifest link correctly.
          // In dev, navigations must always reach the dev server, so no shell is
          // ever precached or bound here.
          navigateFallback: serving ? undefined : '/index.html',
          // ...but never for the API, uploaded media, Django admin, or static.
          navigateFallbackDenylist: [/^\/api\//, /^\/media\//, /^\/admin\//, /^\/static\//],
          cleanupOutdatedCaches: true,
          // Production is conservative: the user accepts an update through the
          // in-app prompt, so a new worker waits instead of claiming clients.
          // While serving, the worker must activate and take over immediately —
          // otherwise a dev worker from an earlier config keeps controlling the
          // page for the whole dev session and even a plain reload keeps serving
          // its obsolete shell.
          clientsClaim: serving,
          skipWaiting: serving,
          // Policy lives in src/lib/pwa/cache-rules.ts (unit tested): only public
          // /media images are cached; every /api/ request is NetworkOnly. Empty
          // while serving so no dev-server/HMR response is ever cached.
          runtimeCaching: serving ? [] : runtimeCaching,
        },
        devOptions: {
          // Serve the manifest and register a development service worker on
          // localhost:5173 so PWA installability matches production. `type:
          // 'module'` keeps the dev worker HMR-compatible; it never precaches
          // dev responses (see runtimeCaching above) and, with no
          // navigateFallback, never intercepts a navigation either.
          enabled: true,
          type: 'module',
          // With no navigateFallback there is nothing for workbox to precache in
          // dev (dev-dist holds no build assets), which workbox rejects outright.
          // This makes the plugin precache a single empty placeholder instead, so
          // the dev worker still installs, responds to fetches and stays
          // installable while navigations pass straight through to the dev
          // server.
          suppressWarnings: serving,
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      port: 5173,
      // VS Code Dev Tunnels get a new hostname on every restart, so allow the
      // domain pattern instead of pinning one — this is the dev server only;
      // production builds are unaffected.
      allowedHosts: ['.devtunnels.ms'],
      proxy: {
        // Forward API calls to the Django dev server during development.
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
        '/media': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
