const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("backwoodsElectron", {
  platform: process.platform,
  appInfo: () => ipcRenderer.invoke("app-info"),
  openUserData: () => ipcRenderer.invoke("open-user-data"),
  printReceipt: (payload) => ipcRenderer.invoke("print-receipt", payload),
  updateStatus: () => ipcRenderer.invoke("update-status"),
  configureUpdates: (config) => ipcRenderer.invoke("update-configure", config),
  checkForUpdates: () => ipcRenderer.invoke("update-check"),
  downloadUpdate: () => ipcRenderer.invoke("update-download"),
  installUpdate: () => ipcRenderer.invoke("update-install"),
  fetchLocalWeather: (payload) => ipcRenderer.invoke("local-weather-fetch", payload),
  onUpdateStatus: (callback) => {
    const listener = (_event, status) => callback(status);
    ipcRenderer.on("update-status", listener);
    return () => ipcRenderer.removeListener("update-status", listener);
  },
  ping: () => "Backwoods Brew Electron bridge ready"
});

require('electron').contextBridge.exposeInMainWorld('businessAccounting', {status:()=>require('electron').ipcRenderer.invoke('business-accounting:status')});

require('electron').contextBridge.exposeInMainWorld('backwoodsUpdates',{open:()=>require('electron').ipcRenderer.invoke('backwoods:open-updates')});
