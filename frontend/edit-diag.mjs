// Temporary: verify the created item persists, edit it through the UI, then confirm.
const HOST = 'http://localhost:5173'
const TOKEN = process.argv[2]
let id = 0
const pending = new Map()
const logs = []
const net = []
const tab = await (await fetch('http://127.0.0.1:9222/json/new?about:blank', { method: 'PUT' })).json()
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((r) => { ws.onopen = r })
ws.onmessage = (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
  if (m.method === 'Runtime.exceptionThrown') logs.push(`exception: ${m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text}`)
  if (m.method === 'Log.entryAdded') logs.push(`log(${m.params.entry.level}): ${m.params.entry.text.slice(0, 250)}`)
  if (m.method === 'Network.responseReceived') { const r = m.params.response; if (r.url.includes('/api/')) net.push(`${r.status} ${r.url}`) }
}
const send = (method, params = {}) => new Promise((res) => { const m = { id: ++id, method, params }; pending.set(m.id, res); ws.send(JSON.stringify(m)) })
const ev = async (x) => (await send('Runtime.evaluate', { expression: x, returnByValue: true, awaitPromise: true })).result.result.value
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable'); await send('Network.enable')
await send('Emulation.setDeviceMetricsOverride', { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false })

await send('Page.navigate', { url: `${HOST}/login` })
await sleep(2500)
await ev(`localStorage.setItem('sas_access', ${JSON.stringify(TOKEN)})`)

// Refresh (fresh load) — the item must still be listed.
await send('Page.navigate', { url: `${HOST}/equipment` })
await sleep(5000)
const afterRefresh = await ev(`({
  hasRow: document.body.innerText.includes('Round Trip Probe'),
  rowText: (() => { const tr = [...document.querySelectorAll('tbody tr')].find(t => t.innerText.includes('Round Trip Probe')); return tr ? tr.innerText.replace(/\\s+/g,' ').trim() : null })(),
})`)
console.log('after refresh hasRow:', afterRefresh.hasRow, '| row:', afterRefresh.rowText)

// Open the edit modal for the probe.
net.length = 0; logs.length = 0
const opened = await ev(`(() => {
  const tr = [...document.querySelectorAll('tbody tr')].find(t => t.innerText.includes('Round Trip Probe'))
  const b = tr ? [...tr.querySelectorAll('button')].find(x => /edit/i.test(x.innerText) || x.getAttribute('aria-label')?.match(/edit/i)) : null
  b?.click()
  return b ? (b.innerText || b.getAttribute('aria-label')) : 'not found'
})()`)
console.log('edit opened:', opened)
await sleep(2000)
const beforeEdit = await ev(`(() => {
  const scope = document.querySelector('[role="dialog"]')
  if (!scope) return { error: 'no modal' }
  const byLabel = (txt) => { const l = [...scope.querySelectorAll('label')].find(x => x.innerText.trim().toLowerCase().startsWith(txt)); return l ? scope.querySelector('#' + CSS.escape(l.htmlFor)) ?? l.parentElement.querySelector('input,select,textarea') : null }
  return { name: byLabel('equipment name')?.value, unit: byLabel('unit')?.value ?? scope.querySelector('#equipment-unit')?.value, price: byLabel('price')?.value }
})()`)
console.log('edit modal initial values:', JSON.stringify(beforeEdit))

// Change unit + price, save.
const changed = await ev(`(() => {
  const scope = document.querySelector('[role="dialog"]')
  const set = (el, v) => { if (!el) return; const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype; const s = Object.getOwnPropertyDescriptor(proto, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })) }
  const byLabel = (txt) => { const l = [...scope.querySelectorAll('label')].find(x => x.innerText.trim().toLowerCase().startsWith(txt)); return l ? scope.querySelector('#' + CSS.escape(l.htmlFor)) ?? l.parentElement.querySelector('input,select,textarea') : null }
  const unitSel = scope.querySelector('#equipment-unit')
  set(unitSel, 'box')
  set(byLabel('price'), '99.99')
  const btns = [...scope.querySelectorAll('button')].filter(x => /save|update|add equipment/i.test(x.innerText.trim()))
  const b = btns[btns.length - 1]
  b?.click()
  return { unit: unitSel?.value, price: byLabel('price')?.value, btn: b?.innerText }
})()`)
console.log('changed:', JSON.stringify(changed))
await sleep(5000)
const afterEdit = await ev(`({
  hasRow: document.body.innerText.includes('Round Trip Probe'),
  modalOpen: !!document.querySelector('[role="dialog"]'),
  rowText: (() => { const tr = [...document.querySelectorAll('tbody tr')].find(t => t.innerText.includes('Round Trip Probe')); return tr ? tr.innerText.replace(/\\s+/g,' ').trim() : null })(),
})`)
console.log('after edit:', JSON.stringify(afterEdit))
console.log('api:', JSON.stringify(net))
console.log('logs:', JSON.stringify(logs))

// Detail page check for unit/price preservation.
await send('Page.navigate', { url: `${HOST}/equipment` })
await sleep(4000)
const detail = await ev(`(async () => {
  const all = await fetch('/api/equipment/', { headers: { Authorization: 'Bearer ' + localStorage.getItem('sas_access') } }).then(r => r.json())
  const item = all.find(x => x.name === 'Round Trip Probe')
  return item ? { id: item.id, unit: item.unit, price: item.price, total_quantity: item.total_quantity, is_active: item.is_active } : 'not found'
})()`)
console.log('api record:', JSON.stringify(detail))

await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
