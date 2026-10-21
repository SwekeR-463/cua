const { app, BrowserWindow, shell } = require('electron')

// The SUID chrome-sandbox helper is often not root-owned in a dev checkout.
app.commandLine.appendSwitch('no-sandbox')
const path = require('node:path')

const PORT = process.env.CUA_BOTS_PORT || '8765'
const URL = `http://127.0.0.1:${PORT}`

app.setName('Cua Bots')

function createWindow() {
  const win = new BrowserWindow({
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
  win.loadURL(URL)
  if (process.env.CUA_BOTS_SCREENSHOT) {
    win.webContents.once('did-finish-load', () => {
      setTimeout(async () => {
        try {
          const image = await win.webContents.capturePage()
          require('node:fs').writeFileSync(process.env.CUA_BOTS_SCREENSHOT, image.toPNG())
        } finally {
          app.quit()
        }
      }, 2500)
    })
  }
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(URL)) return { action: 'allow' }
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
