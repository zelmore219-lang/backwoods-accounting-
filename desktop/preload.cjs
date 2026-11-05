const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('backwoodsUpdates',{open:()=>ipcRenderer.invoke('backwoods:open-updates')});
