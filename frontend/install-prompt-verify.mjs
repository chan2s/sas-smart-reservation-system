// Production install-prompt verification, driven over CDP (same approach as
// pwa-verify.mjs).
//
// Usage:
//   npm run build
//   chrome --headless=new --remote-debugging-port=9222 --user-data-dir=/tmp/pwa about:blank
//   node install-prompt-verify.mjs
//
// Serves `dist/` itself (with a stub /api/health/), then drives a real Chrome:
//   1. the manifest is linked and parseable, with the required members
//   2. no install card appears for a normal load (no beforeinstallprompt)
//   3. a deferred prompt produces the card (after its politeness delay) with
//      the icon, required copy, and both actions
//   4. "Not now" hides the card and persists a dismissal timestamp
//   5. the dismissal survives a reload (no re-prompt within the cooldown)
//   6. the invitation becomes eligible again after the 7-day cooldown
//   7. accepting the prompt ("Install App") hides the card for good
//
// Exits non-zero if any check fails.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const PORT = 4181
const DIST = path.resolve('dist')
const MIME = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.webmanifest': 'application/manifest+json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
}

const server = createServer(async (request, response) => {
  const { pathname } = new URL(request.url, `http://localhost:${PORT}`)
  if (pathname === '/api/health/') {
    response.writeHead(200, { 'Content-Type': 'application/json' })
    response.end('{"status":"ok"}')
    return
  }
  const file = path.join(DIST, pathname === '/' ? 'index.html' : pathname)
  try {
    const body = await readFile(file)
    response.writeHead(200, { 'Content-Type': MIME[path.extname(file)] ?? 'application/octet-stream' })
    response.end(body)
  } catch {
    response.writeHead(200, { 'Content-Type': 'text/html' })
    response.end(await readFile(path.join(DIST, 'index.html')))
  }
})
await new Promise((resolve) => server.listen(PORT, resolve))

const tab = await (
  await fetch(`http://127.0.0.1:9222/json/new?http://localhost:${PORT}/`, { method: 'PUT' })
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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

await send('Runtime.enable')
await send('Page.enable')

const checks = []
const check = (name, ok, detail = '') => {
  checks.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

/** Dispatch a rich synthetic beforeinstallprompt, as a Chromium would. */
const firePrompt = () =>
  evaluate(`(() => {
    const event = new Event('beforeinstallprompt')
    event.prompt = () => Promise.resolve()
    event.userChoice = Promise.resolve({ outcome: 'accepted', platform: 'web' })
    window.dispatchEvent(event)
    return true
  })()`)

const cardVisible = () =>
  evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Install App')
    if (!button) return false
    const card = button.closest('[role="status"]')
    return Boolean(card && card.textContent.includes('Install SAS RESERVE'))
  })()`)

const waitMs = (ms) => evaluate(`new Promise((resolve) => setTimeout(resolve, ${ms}))`)

// 1. Manifest is linked and carries the installability essentials.
const manifest = await evaluate(`fetch('/manifest.webmanifest').then((r) => r.json())`)
check(
  'manifest is linked and parseable',
  manifest.name === 'SAS RESERVE' &&
    Boolean(manifest.short_name) &&
    manifest.display === 'standalone' &&
    Boolean(manifest.start_url) &&
    Boolean(manifest.theme_color) &&
    Boolean(manifest.background_color) &&
    (manifest.icons ?? []).some((icon) => icon.sizes === '192x192') &&
    (manifest.icons ?? []).some((icon) => icon.sizes === '512x512') &&
    (manifest.icons ?? []).some((icon) => icon.purpose === 'maskable'),
  `name=${manifest.name} icons=${(manifest.icons ?? []).length}`,
)

await sleep(2500)

// A supported browser (this Chromium) may fire a genuine beforeinstallprompt
// once the service worker + manifest satisfy installability. The card must
// appear exactly when the browser offers installation — no sooner, no later.
// Record whether the real event fired, then reload so the recorder is in
// place from the very start of the document.
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: `window.__bipFired = false;
           window.addEventListener('beforeinstallprompt', () => { window.__bipFired = true })`,
})
await send('Page.reload')
await sleep(2500)
const nativeOffered = await evaluate('window.__bipFired === true')
check(
  'install card appears exactly when the browser offers installation',
  (await cardVisible()) === nativeOffered,
  nativeOffered ? 'Chromium fired a native beforeinstallprompt' : 'no prompt event from the browser',
)

// 3. The deferred prompt produces the card with the required content.
await firePrompt()
await waitMs(2200) // 1.5s politeness delay + render
const cardText = await evaluate(
  `(() => {
    const button = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Install App')
    return button ? button.closest('[role="status"]').textContent : ''
  })()`,
)
check('install card appears after the prompt event', Boolean(cardText), cardText.slice(0, 80))
check(
  'card carries the required description',
  cardText.includes('Install SAS RESERVE for quick access from your home screen or desktop.'),
)
check(
  'card shows the app icon and both actions',
  await evaluate(
    `(() => {
      const img = document.querySelector('img[alt="SAS RESERVE app icon"]')
      const install = [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Install App')
      const dismiss = [...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Not now')
      return Boolean(img) && install && dismiss
    })()`,
  ),
)

// 4. "Not now" hides the card and persists the dismissal.
await evaluate(
  `[...document.querySelectorAll('button')]
     .find((b) => b.textContent.trim() === 'Not now')
     .click()`,
)
await waitMs(300)
check('card hides after dismissal', (await cardVisible()) === false)
const dismissedAt = await evaluate(`localStorage.getItem('sas_pwa_install_dismissed_at')`)
check('dismissal timestamp persisted', dismissedAt !== null && Number(dismissedAt) > 0)

// 5. The dismissal survives a reload — no card even with a fresh prompt event.
await send('Page.reload')
await sleep(2000)
await firePrompt()
await waitMs(2200)
check('no re-prompt after reload within the cooldown', (await cardVisible()) === false)

// 6. Backdate the dismissal past seven days: the invitation is eligible again.
await evaluate(`localStorage.setItem('sas_pwa_install_dismissed_at', String(Date.now() - 8 * 24 * 60 * 60 * 1000))`)
await send('Page.reload')
await sleep(2000)
await firePrompt()
await waitMs(2200)
check('invitation re-eligible after the 7-day cooldown', (await cardVisible()) === true)

// 7. Accepting the install hides the card for good.
await evaluate(
  `[...document.querySelectorAll('button')]
     .find((b) => b.textContent.trim() === 'Install App')
     .click()`,
)
await waitMs(500)
check('card hides after a successful installation', (await cardVisible()) === false)

// A real installed app runs with display-mode: standalone (and Chromium stops
// firing beforeinstallprompt). Emulate the standalone display so the reload
// below behaves like the app's later, installed launches.
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: `(() => {
    const original = window.matchMedia.bind(window)
    window.matchMedia = (query) =>
      query === '(display-mode: standalone)'
        ? { matches: true, media: query, onchange: null, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false } }
        : original(query)
  })()`,
})
await send('Page.reload')
await sleep(2000)
await firePrompt()
await waitMs(2200)
check('no install card when running as an installed (standalone) app', (await cardVisible()) === false)

check('no unhandled page errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' || '))

const failed = checks.filter((entry) => !entry.ok)
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`)
await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
server.close()
process.exit(failed.length === 0 ? 0 : 1)
