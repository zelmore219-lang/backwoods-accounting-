const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('updates',{
 action:(name,value)=>{if(!['status','configure','check','download','install'].includes(name))throw Error('Unknown update action');return ipcRenderer.invoke('backwoods:update-'+name,value);},
 onState:callback=>ipcRenderer.on('backwoods:update-state',(_event,state)=>callback(state))
});
