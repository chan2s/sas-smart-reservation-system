// Temporary diagnostic: does the Equipment list render in the SPA?
const HOST = 'http://localhost:5173'
const TOKEN = process.argv[2]
const PAGES = process.argv.slice(3)
let id = 0
const pending = new Map()
const logs = []
const net = []

const tab = await (
  await fetch('http://127.0.0.1:9222/json/new?about:blank', { method: 'PUT' })
).json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((r) => {
  ws.onopen = r
})
ws.onmessage = (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m)
    pending.delete(m.id)
  }
  if (m.method === 'Runtime.consoleAPICalled')
    logs.push(`${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 300)}`)
  if (m.method === 'Runtime.exceptionThrown')
    logs.push(`exception: ${m.params.exceptionDetails.text} ${m.params.exceptionDetails.exception?.description ?? ''}`)
  if (m.method === 'Log.entryAdded')
    logs.push(`log(${m.params.entry.level}): ${m.params.entry.text.slice(0, 300)}`)
  if (m.method === 'Network.responseReceived') {
    const r = m.params.response
    if (r.url.includes('/api/')) net.push(`${m.params.response.status} ${r.url}`)
  }
  if (m.method === 'Network.loadingFailed')
    logs.push(`netfail: ${m.params.errorText}`)
}
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const message = { id: ++id, method, params }
    pending.set(message.id, resolve)
    ws.send(JSON.stringify(message))
  })
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  return r.result.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

await send('Page.enable')
await send('Runtime.enable')
await send('Log.enable')
await send('Network.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false })

// Seed the auth tokens, then land on the login page so the AuthProvider picks them up.
await send('Page.navigate', { url: `${HOST}/login` })
await sleep(2500)
const seeded = await evaluate(`(localStorage.setItem('sas_access', ${JSON.stringify(TOKEN)}), localStorage.getItem('sas_access')?.slice(0, 20))`)
console.log('seeded token:', seeded)

for (const rawPath of PAGES) {
  const path = rawPath.replace(/^.*?(\/(?:equipment|facilities|reservations|login).*)$/, '$1')
  console.log('navigating to:', path)
  logs.length = 0
  net.length = 0
  await send('Page.navigate', { url: `${HOST}${path}` })
  await sleep(6000)
  const info = await evaluate(`({
    href: location.href,
    rootChildren: document.getElementById('root')?.children.length ?? -1,
    text: document.body.innerText.replace(/\\s+/g, ' ').trim().slice(0, 700),
    rows: document.querySelectorAll('table tbody tr').length,
    cards: document.querySelectorAll('ul li').length,
    fullText: document.body.innerText.replace(/\s+/g, ' ').trim(),
    equipmentMentions: ['Portable Sound System','Folding Chair','Wireless Microphone','Extension Cord'].map(n => [n, document.body.innerText.includes(n)]),
  })`)
  console.log('=== ' + path)
  console.log(JSON.stringify({ ...info, fullText: info.fullText?.slice(0, 3000) }, null, 2))
  console.log('api:', JSON.stringify(net, null, 2))
  console.log('logs:', JSON.stringify(logs, null, 2))
}

await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
