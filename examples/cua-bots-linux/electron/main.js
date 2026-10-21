const { app, BrowserWindow, dialog, shell } = require('electron')
const fs = require('node:fs')
const http = require('node:http')
const net = require('node:net')
const path = require('node:path')
const { spawn } = require('node:child_process')

// The SUID chrome-sandbox helper is often not root-owned in a dev checkout.
app.commandLine.appendSwitch('no-sandbox')
app.setName('Cua Bots')

let backend = null
let mainWindow = null

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port
      server.close(() => resolve(port))
    })
  })
}

function healthy(port, timeout = 600) {
  return new Promise((resolve) => {
    const request = http.get({ host: '127.0.0.1', port, path: '/api/health', timeout }, (response) => {
      response.resume()
      resolve(response.statusCode === 200)
    })
    request.on('error', () => resolve(false))
    request.on('timeout', () => { request.destroy(); resolve(false) })
  })
}

async function startBackend() {
  if (!app.isPackaged) return String(process.env.CUA_BOTS_PORT || '8765')

  const port = await freePort()
  const executable = path.join(process.resourcesPath, 'server', 'cua-bots-server', 'cua-bots-server')
  if (!fs.existsSync(executable)) throw new Error(`Missing backend: ${executable}`)

  const logPath = path.join(app.getPath('userData'), 'backend.log')
  const log = fs.createWriteStream(logPath, { flags: 'a' })
  backend = spawn(executable, [], {
    cwd: path.dirname(executable),
    env: {
      ...process.env,
      CUA_BOTS_PORT: String(port),
      CUA_BOTS_HOST: '127.0.0.1',
      CUA_BOTS_WEB_DIR: path.join(process.resourcesPath, 'web'),
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  backend.stdout.pipe(log)
  backend.stderr.pipe(log)
  backend.on('exit', (code) => {
    if (code && code !== 0 && !app.isQuitting) {
      dialog.showErrorBox('Cua Bots backend stopped', `Exit code ${code}. See ${logPath}`)
    }
  })

  for (let attempt = 0; attempt < 150; attempt += 1) {
    if (await healthy(port)) return String(port)
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`The backend did not start. See ${logPath}`)
}

async function createWindow() {
  let port
  try {
    port = await startBackend()
  } catch (error) {
    dialog.showErrorBox('Cua Bots', error.message)
    app.quit()
    return
  }

  const url = `http://127.0.0.1:${port}`
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: '#f7f6f2',
    title: 'Cua Bots',
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  mainWindow.loadURL(url)
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith(url)) return { action: 'allow' }
    shell.openExternal(target)
    return { action: 'deny' }
  })

  if (process.env.CUA_BOTS_SCREENSHOT) {
    mainWindow.webContents.once('did-finish-load', () => {
      setTimeout(async () => {
        try {
          const image = await mainWindow.webContents.capturePage()
          fs.writeFileSync(process.env.CUA_BOTS_SCREENSHOT, image.toPNG())
        } finally {
          app.quit()
        }
      }, 2500)
    })
  }
}

app.whenReady().then(createWindow)

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})

app.on('before-quit', () => {
  app.isQuitting = true
  if (backend) {
    backend.kill()
    backend = null
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
