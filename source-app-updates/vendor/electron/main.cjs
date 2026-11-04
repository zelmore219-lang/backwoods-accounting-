const { app, BrowserWindow, shell, ipcMain, dialog } = require('electron')
require('./connected-profile.cjs').prepareProfile({app,dialog}, require('./business-accounting-config.json'));
const fs = require('fs/promises')
const path = require('path')

const isDev = !app.isPackaged
const windowIcon = isDev
  ? path.join(__dirname, '..', 'dist', 'icons', 'icon-512.png')
  : path.join(__dirname, '..', 'dist', 'icons', 'icon-512.png')

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1040,
    minHeight: 700,
    title: 'Backwoods Vendor Ordering',
    backgroundColor: '#f3f1e8',
    icon: windowIcon,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url === 'about:blank') return { action: 'allow' }
    if (/^(https?:|mailto:|tel:)/i.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })

  if (isDev) {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  ipcMain.handle('app:getVersion', () => app.getVersion())
  ipcMain.handle('app:saveFile', async (event, options = {}) => {
    const owner = BrowserWindow.fromWebContents(event.sender)
    const fallbackName = 'backwoods-catalog-export.txt'
    const safeName = String(options.defaultPath || fallbackName)
      .replace(/[<>:"/\\|?*\x00-\x1F]/g, '-')
      .slice(0, 180) || fallbackName
    const result = await dialog.showSaveDialog(owner, {
      title: options.title || 'Save export',
      defaultPath: path.join(app.getPath('downloads'), safeName),
      filters: Array.isArray(options.filters) && options.filters.length ? options.filters : undefined
    })
    if (result.canceled || !result.filePath) return { canceled: true }
    await fs.writeFile(result.filePath, String(options.content ?? ''), options.encoding || 'utf8')
    return { canceled: false, filePath: result.filePath }
  })
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

require('./desktop-feed.cjs');
