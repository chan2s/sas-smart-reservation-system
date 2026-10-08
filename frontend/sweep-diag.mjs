// Temporary diagnostic: sweep remaining equipment surfaces + create/edit round-trip.
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
  if (m.method === 'Runtime.exceptionThrown')
    logs.push(`exception: ${m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text}`)
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

for (const path of ['/facilities/1', '/facilities/3', '/equipment/1', '/calendar']) {
  logs.length = 0; net.length = 0
  await send('Page.navigate', { url: `${HOST}${path}` })
  await sleep(5000)
  const info = await ev(`({
    href: location.href,
    text: document.body.innerText.replace(/\\s+/g, ' ').trim(),
  })`)
  const mentions = await ev(`['Portable Sound System','Folding Chair','Extension Cord','Available equipment'].map(n => [n, document.body.innerText.includes(n)])`)
  console.log(`\n=== ${path}`)
  console.log('href:', info.href)
  console.log('mentions:', JSON.stringify(mentions))
  console.log('text:', info.text.slice(700, 2600))
  console.log('api:', JSON.stringify(net))
  console.log('logs:', JSON.stringify(logs))
}

// ---- Admin create/edit round-trip on /equipment ----
logs.length = 0; net.length = 0
await send('Page.navigate', { url: `${HOST}/equipment` })
await sleep(5000)
const opened = await ev(`(() => { const b = [...document.querySelectorAll('button')].find(x => /add equipment/i.test(x.innerText)); b?.click(); return b ? 'clicked' : 'missing' })()`)
console.log('\n=== create flow, open:', opened)
await sleep(1500)
const filled = await ev(`(() => {
  const scope = document.querySelector('[role="dialog"]') ?? document
  const set = (el, v) => { if (!el) return; const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype; const s = Object.getOwnPropertyDescriptor(proto, 'value').set; s.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })) }
  const byLabel = (txt) => { const l = [...scope.querySelectorAll('label')].find(x => x.innerText.trim().toLowerCase().startsWith(txt)); return l ? scope.querySelector('#' + CSS.escape(l.htmlFor)) ?? l.parentElement.querySelector('input,select,textarea') : null }
  set(byLabel('equipment name'), 'Round Trip Probe')
  const cat = byLabel('category')
  const catOpts = cat ? [...cat.options].map(o => [o.value, o.textContent.trim()]) : []
  set(cat, [...cat.options].find(o => /Microphones/i.test(o.textContent))?.value)
  set(byLabel('total quantity'), '3')
  const unitSel = scope.querySelector('#equipment-unit')
  const unitOpts = unitSel ? [...unitSel.options].map(o => o.value) : []
  set(unitSel, 'pair')
  set(byLabel('price'), '250.50')
  return { name: byLabel('equipment name')?.value, unit: unitSel?.value, unitOpts, price: byLabel('price')?.value, category: cat?.value, catOpts }
})()`)
console.log('filled:', JSON.stringify(filled))
await sleep(500)
const saved = await ev(`(() => {
  const btns = [...document.querySelectorAll('button')].filter(x => /^(save|add equipment|create)/i.test(x.innerText.trim()))
  const b = btns[btns.length - 1]
  b?.click()
  return { picked: b?.innerText, count: btns.length }
})()`)
console.log('save clicked:', JSON.stringify(saved))
await sleep(5000)
const afterSave = await ev(`({
  text: document.body.innerText.replace(/\\s+/g,' ').trim(),
  hasRow: document.body.innerText.includes('Round Trip Probe'),
  modalOpen: !!document.querySelector('[role="dialog"]'),
})`)
console.log('after save hasRow:', afterSave.hasRow, 'modalOpen:', afterSave.modalOpen)
console.log('after save text:', afterSave.text.slice(400, 2400))
console.log('api:', JSON.stringify(net))
console.log('logs:', JSON.stringify(logs))

await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
