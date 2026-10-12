// Production PWA verification, driven over CDP (same approach as the other
// *-diag.mjs scripts in this folder).
//
// Usage:
//   npm run build
//   chrome --headless=new --remote-debugging-port=9222 --user-data-dir=/tmp/pwa about:blank
//   node pwa-verify.mjs
//
// Exits non-zero if any check fails. It serves `dist/` itself, with a stub
// /api/health/, so nothing else needs to be running.
//
// Serves the built `dist/` (with a stub /api/health/ so the "online" state can
// be observed) and asserts against a real Chrome instance on port 9222:
//   1. the service worker registers and takes control in production
//   2. the app shell renders online with no offline banner
//   3. losing connectivity shows the offline banner
//   4. the shell still opens from the service-worker cache while offline
//   5. reconnecting clears the banner
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const PORT = 4180
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
await send('Network.enable')

const checks = []
const check = (name, ok, detail = '') => {
  checks.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

// 1. Service worker registration in the production build.
let registration = null
for (let attempt = 0; attempt < 20 && !registration; attempt++) {
  await sleep(500)
  registration = await evaluate(`
    navigator.serviceWorker.getRegistration().then((r) =>
      r && r.active ? { scope: r.scope, script: r.active.scriptURL } : null
    )`)
}
check('service worker registered and active', Boolean(registration), registration?.script ?? 'none')

// The worker deliberately does not claim open pages (registerType: 'prompt',
// clientsClaim: false), so control arrives on the next navigation.
await send('Page.reload')
await sleep(3000)
check(
  'service worker controls the page after the next navigation',
  await evaluate('navigator.serviceWorker.controller !== null'),
)

// 2. Online: shell renders, no offline banner.
await sleep(1500)
const onlineText = await evaluate('document.body.innerText')
check('shell renders in production', onlineText.includes('SAS'), `${onlineText.length} chars`)
check('no offline banner while online', !onlineText.includes("You're offline"))

// 3. Connectivity lost: banner appears.
await send('Network.emulateNetworkConditions', {
  offline: true,
  latency: 0,
  downloadThroughput: -1,
  uploadThroughput: -1,
})
await sleep(2500)
const offlineText = await evaluate('document.body.innerText')
check('navigator.onLine reflects the outage', await evaluate('navigator.onLine') === false)
check(
  'offline banner appears',
  offlineText.includes("You're offline") || offlineText.includes("Can't reach SAS RESERVE"),
  offlineText.slice(0, 120).replace(/\n/g, ' | '),
)
check(
  'no backup yet is stated plainly',
  /no saved information/i.test(offlineText) || /local backup/i.test(offlineText),
)
check('banner offers the saved-information view', offlineText.includes('View saved info'))

// 4. The shell still opens from the service-worker cache while offline.
await send('Page.reload', { ignoreCache: true })
await sleep(3500)
const reloaded = await evaluate('document.body.innerText')
check('shell still opens offline (served by the worker)', reloaded.includes('SAS'), `${reloaded.length} chars`)
check(
  'offline banner present after the offline reload',
  reloaded.includes("You're offline") || reloaded.includes("Can't reach SAS RESERVE"),
)

// 5. Reconnect: banner clears.
await send('Network.emulateNetworkConditions', {
  offline: false,
  latency: 0,
  downloadThroughput: -1,
  uploadThroughput: -1,
})
await sleep(3000)
const restored = await evaluate('document.body.innerText')
check('offline banner clears after reconnecting', !restored.includes("You're offline"))

check('no unhandled page errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' || '))

const failed = checks.filter((entry) => !entry.ok)
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`)
await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
server.close()
process.exit(failed.length === 0 ? 0 : 1)
