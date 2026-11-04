const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktopApp', {
  isDesktop: true,
  getVersion: () => ipcRenderer.invoke('app:getVersion'),
  saveFile: options => ipcRenderer.invoke('app:saveFile', options)
})

require('electron').contextBridge.exposeInMainWorld('businessAccounting', {status:()=>require('electron').ipcRenderer.invoke('business-accounting:status')});
