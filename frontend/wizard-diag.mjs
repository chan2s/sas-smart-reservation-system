// Temporary diagnostic: walk the reservation wizard and check the resource step.
const HOST = 'http://localhost:5173'
const TOKEN = process.argv[2]
let id = 0
const pending = new Map()
const logs = []
const net = []

const tab = await (
  await fetch('http://127.0.0.1:9222/json/new?about:blank', { method: 'PUT' })
).json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((r) => { ws.onopen = r })
ws.onmessage = (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
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
}
const send = (method, params = {}) =>
  new Promise((resolve) => { const m = { id: ++id, method, params }; pending.set(m.id, resolve); ws.send(JSON.stringify(m)) })
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  return r.result.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const snap = async (label) => {
  const info = await evaluate(`({
    href: location.href,
    buttons: [...document.querySelectorAll('button')].map(b => b.innerText.replace(/\\s+/g,' ').trim()).filter(Boolean).slice(0, 40),
    text: document.body.innerText.replace(/\\s+/g, ' ').trim(),
  })`)
  console.log(`\n--- ${label} ---`)
  console.log('href:', info.href)
  console.log('buttons:', JSON.stringify(info.buttons))
  console.log('text:', info.text.slice(0, 2500))
}

await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false })

await send('Page.navigate', { url: `${HOST}/login` })
await sleep(2500)
await evaluate(`localStorage.setItem('sas_access', ${JSON.stringify(TOKEN)})`)
logs.length = 0; net.length = 0
await send('Page.navigate', { url: `${HOST}/reservations/new` })
await sleep(5000)
await snap('step 1 facility')

// Click the Cafeteria card.
await evaluate(`(() => {
  const cards = [...document.querySelectorAll('*')].filter(el => el.children.length && /^Cafeteria/.test(el.innerText?.trim() ?? ''))
  const card = cards[cards.length - 1]
  card?.click()
  return card ? card.innerText.slice(0,60) : 'no card'
})()`)
await sleep(1200)
await snap('after facility click')

// Continue.
await evaluate(`(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /continue/i.test(b.innerText))
  btn?.click(); return btn?.innerText ?? 'no continue'
})()`)
await sleep(1500)
await snap('step 2 schedule')

// Pick a future day in the calendar, then the time slots.
const filled = await evaluate(`(() => {
  const target = document.querySelector('button[aria-label="October 20, 2026"]')
  target?.click()
  const selects = [...document.querySelectorAll('select')]
  return { clicked: target?.getAttribute('aria-label') ?? 'not found', selectCount: selects.length, options: selects.map(s => [...s.options].map(o => o.value).slice(0, 8)) }
})()`)
console.log('calendar:', JSON.stringify(filled))
await sleep(1200)
const times = await evaluate(`(() => {
  const selects = [...document.querySelectorAll('select')]
  const setSel = (el, v) => { if (!el) return; const s = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('change', { bubbles: true })) }
  const startOpts = selects[0] ? [...selects[0].options].map(o => o.value).filter(Boolean) : []
  const endOpts = selects[1] ? [...selects[1].options].map(o => o.value).filter(Boolean) : []
  setSel(selects[0], startOpts[1] ?? startOpts[0])
  setSel(selects[1], endOpts[endOpts.length - 1] ?? endOpts[0])
  return { start: selects[0]?.value, end: selects[1]?.value, startOpts: startOpts.slice(0,5), endOpts: endOpts.slice(0,5) }
})()`)
console.log('times:', JSON.stringify(times))
await sleep(1500)
const times2 = await evaluate(`(() => {
  const selects = [...document.querySelectorAll('select')]
  const setSel = (el, v) => { if (!el) return; const s = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set; s.call(el, v); el.dispatchEvent(new Event('change', { bubbles: true })) }
  const endOpts = selects[1] ? [...selects[1].options].map(o => o.value).filter(Boolean) : []
  setSel(selects[1], endOpts[4] ?? endOpts[0])
  return { start: selects[0]?.value, end: selects[1]?.value, endCount: endOpts.length }
})()`)
console.log('times2:', JSON.stringify(times2))
await sleep(2500)
await sleep(1500)
await snap('after schedule fill')

await evaluate(`(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /continue/i.test(b.innerText))
  btn?.click(); return btn?.innerText ?? 'no continue'
})()`)
await sleep(2500)
await snap('step 3 resources')

// Fill the required details so the resource sections render fully.
const details = await evaluate(`(() => {
  const set = (el, v) => { if (!el) return; const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype; const s = Object.getOwnPropertyDescriptor(proto, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })) }
  const byLabel = (label) => { const f = [...document.querySelectorAll('label')].find(l => l.innerText.trim().toLowerCase().startsWith(label)); return f ? document.getElementById(f.htmlFor) ?? f.parentElement.querySelector('input,select,textarea') : null }
  set(byLabel('event name'), 'Equipment Visibility Test')
  const type = [...document.querySelectorAll('select')].find(s => [...s.options].some(o => /Seminar/i.test(o.textContent)))
  set(type, [...type.options].find(o => /Seminar/i.test(o.textContent))?.value)
  set(byLabel('expected participants'), '50')
  set(byLabel('purpose'), 'Equipment visibility check')
  set(byLabel('contact phone'), '09171234567')
  return { eventName: byLabel('event name')?.value, type: type?.value, participants: byLabel('expected participants')?.value }
})()`)
console.log('details:', JSON.stringify(details))
await sleep(3000)

// Open the "Add other equipment" picker.
const opened = await evaluate(`(() => {
  const btn = [...document.querySelectorAll('button')].find(b => /add other equipment/i.test(b.innerText))
  btn?.click()
  return btn?.innerText ?? 'no button'
})()`)
console.log('opened picker:', opened)
await sleep(2500)

const mentions = await evaluate(`({
  names: ['Portable Sound System','Folding Chair','Extension Cord','Wired Microphone','Portable Projector','test'].map(n => [n, document.body.innerText.includes(n)]),
  text: document.body.innerText.replace(/\\s+/g, ' ').trim(),
})`)
console.log('equipment mentions:', JSON.stringify(mentions.names))
console.log('page text after picker:', mentions.text.slice(0, 3500))
console.log('api:', JSON.stringify(net, null, 2))
console.log('logs:', JSON.stringify(logs, null, 2))

await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
