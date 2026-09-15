import fs from 'node:fs'

let id = 0

async function run(width, height, file) {
  const tab = await (
    await fetch('http://127.0.0.1:9222/json/new?http://127.0.0.1:5173/', {
      method: 'PUT',
    })
  ).json()
  const ws = new WebSocket(tab.webSocketDebuggerUrl)
  const pending = new Map()
  const errors = []

  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const message = { id: ++id, method, params }
      pending.set(message.id, { resolve, reject })
      ws.send(JSON.stringify(message))
    })
  }

  await new Promise((resolve) => {
    ws.onopen = resolve
  })

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      pending.get(message.id).resolve(message)
      pending.delete(message.id)
    }
    if (
      message.method === 'Runtime.consoleAPICalled' &&
      ['error', 'warning'].includes(message.params.type)
    ) {
      errors.push(
        `${message.params.type}: ${message.params.args
          .map((arg) => arg.value || arg.description || '')
          .join(' ')}`,
      )
    }
    if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
      errors.push(`log: ${message.params.entry.text}`)
    }
  }

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Log.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width < 600,
  })
  await send('Page.navigate', { url: 'http://127.0.0.1:5173/' })

  for (let i = 0; i < 80; i += 1) {
    const result = await send('Runtime.evaluate', {
      expression:
        '!!document.querySelector("[data-hero-shell]") && document.fonts.status === "loaded"',
      returnByValue: true,
    })
    if (result.result.result.value) break
    await new Promise((resolve) => setTimeout(resolve, 250))
  }

  await new Promise((resolve) => setTimeout(resolve, 1200))

  const metrics = await send('Runtime.evaluate', {
    expression:
      '({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,hero:document.querySelector("[data-hero-shell]")?.getBoundingClientRect().toJSON(),overview:document.querySelector("[data-hero-next]")?.getBoundingClientRect().toJSON(),text:document.querySelector("[data-hero-content]")?.getBoundingClientRect().toJSON()})',
    returnByValue: true,
  })
  const screenshot = await send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  })

  fs.writeFileSync(file, Buffer.from(screenshot.result.data, 'base64'))
  await fetch(`http://127.0.0.1:9222/json/close/${tab.id}`)
  return { file, width, height, metrics: metrics.result.result.value, errors }
}

const results = await Promise.all([
  run(1440, 1200, 'hero-desktop.png'),
  run(390, 900, 'hero-mobile.png'),
])

console.log(JSON.stringify(results, null, 2))
