// Development-server PWA verification: tests the ACTUAL site at
// http://localhost:5173/ the way the user sees it. No synthetic events —
// every installability signal comes from real Chromium.
//
// Usage:
//   npm run dev                       (or have the dev server running)
//   chrome --headless=new --remote-debugging-port=9222 --user-data-dir=/tmp/pwa about:blank
//   node dev-pwa-verify.mjs
//
// Exits non-zero if any check fails.
import { setTimeout as sleep } from 'node:timers/promises'

const DEV_URL = 'http://localhost:5173/'

const tab = await (
  await fetch(`http://127.0.0.1:9222/json/new?${encodeURIComponent(DEV_URL)}`, { method: 'PUT' })
).json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((resolve) => {
  ws.onopen = resolve
})

let id = 0
const pending = new Map()
const consoleErrors = []
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message)
    pending.delete(message.id)
  }
  if (message.method === 'Runtime.exceptionThrown') {
    consoleErrors.push(message.params.exceptionDetails.text)
  }
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
    consoleErrors.push(message.params.args.map((a) => a.value ?? a.description ?? '').join(' '))
  }
}
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const message = { id: ++id, method, params }
    pending.set(message.id, resolve)
    ws.send(JSON.stringify(message))
  })
const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (result.result.exceptionDetails) {
    throw new Error(result.result.exceptionDetails.text)
  }
  return result.result.result.value
}

await send('Runtime.enable')
await send('Page.enable')

const checks = []
const check = (name, ok, detail = '') => {
  checks.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

// Record real beforeinstallprompt events from the very first document of the
// next navigations.
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: `window.__bipFired = false;
           window.addEventListener('beforeinstallprompt', () => { window.__bipFired = true })`,
})

await sleep(3000) // initial load + React mount + SW registration

// 1. The manifest is linked in the dev HTML and served from the frontend origin.
const manifestHref = await evaluate(
  `document.querySelector('link[rel="manifest"]')?.href ?? null`,
)
check('manifest <link> present in the dev page', Boolean(manifestHref), manifestHref ?? 'missing')

const manifestResponse = await evaluate(`fetch('/manifest.webmanifest').then(async (r) => ({
  status: r.status,
  type: r.headers.get('content-type'),
  body: await r.json(),
}))`)
check(
  'manifest served from the frontend origin',
  manifestResponse.status === 200 &&
    /manifest/.test(manifestResponse.type ?? '') &&
    manifestResponse.body.name === 'SAS RESERVE',
  `status=${manifestResponse.status} type=${manifestResponse.type}`,
)

// 2. Manifest members Chrome validates for installability.
const manifest = manifestResponse.body
check(
  'manifest members are installability-complete',
  Boolean(manifest.short_name) &&
    Boolean(manifest.start_url) &&
    manifest.scope === '/' &&
    manifest.display === 'standalone' &&
    Boolean(manifest.theme_color) &&
    Boolean(manifest.background_color) &&
    (manifest.icons ?? []).some((icon) => icon.sizes === '192x192') &&
    (manifest.icons ?? []).some((icon) => icon.sizes === '512x512') &&
    (manifest.icons ?? []).some((icon) => icon.purpose === 'maskable'),
  `icons=${(manifest.icons ?? []).length}`,
)

// 3. Every referenced icon exists and returns a real image.
const iconResults = await evaluate(`Promise.all(((${JSON.stringify(manifest.icons)})).map((icon) =>
  fetch(icon.src).then((r) => ({
    src: icon.src,
    status: r.status,
    type: r.headers.get('content-type'),
  }))
))`)
check(
  'all manifest icons return valid image responses',
  iconResults.every((icon) => icon.status === 200 && icon.type.startsWith('image/')),
  iconResults.map((icon) => `${icon.src}=${icon.status}/${icon.type}`).join(' '),
)

// 4. The development service worker is registered and active. The first load
// after a cold dev-server start compiles everything, so registration can lag
// — poll instead of assuming a fixed delay.
await send('Page.reload')
let sw = null
for (let attempt = 0; attempt < 30 && !sw; attempt++) {
  await sleep(500)
  sw = await evaluate(`navigator.serviceWorker.getRegistration().then((r) =>
    r && (r.active || r.installing || r.waiting)
      ? {
          script: (r.active ?? r.installing ?? r.waiting).scriptURL,
          active: Boolean(r.active),
          controller: navigator.serviceWorker.controller !== null,
        }
      : null
  )`)
}
check(
  'service worker registers on the dev server',
  Boolean(sw?.script) && sw.script.includes('dev-sw.js'),
  sw ? `${sw.script} active=${sw.active} controls=${sw.controller}` : 'none after 15s',
)

// 5. Chrome itself offered installation (real event, no simulation), and the
// in-app banner responded.
const nativeOffered = await evaluate('window.__bipFired === true')
await sleep(2500) // 1.5s politeness delay + render
const bannerVisible = await evaluate(`(() => {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Install App')
  return Boolean(button && button.closest('[role="status"]').textContent.includes('Install SAS RESERVE'))
})()`)
check(
  'Chromium fired a real beforeinstallprompt on localhost:5173',
  nativeOffered,
  nativeOffered ? 'real browser event' : 'not fired — see report',
)
check(
  'install banner visible when Chrome offers installation',
  bannerVisible === nativeOffered,
  bannerVisible ? 'banner shown' : 'banner hidden',
)

// 6. The native install action: click Install App and report what the real
// prompt does. In headless the dialog may auto-dismiss; the outcome is
// reported as-is, never faked.
const outcome = await evaluate(`(() => {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Install App')
  if (!button) return 'banner-not-present'
  button.click()
  return 'clicked — native dialog requested'
})()`)
console.log(`INFO  native install action: ${outcome}`)

check('no unhandled page errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' || '))

const failed = checks.filter((entry) => !entry.ok)
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`)
await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
process.exit(failed.length === 0 ? 0 : 1)
