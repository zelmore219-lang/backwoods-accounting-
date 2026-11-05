const {app,BrowserWindow,Menu,Tray,shell,dialog,ipcMain}=require('electron');
const {spawn}=require('node:child_process');
const path=require('node:path');
let worker,window,tray,origin,quitting=false;
const locked=app.requestSingleInstanceLock();
if(!locked)app.quit();
else {
  app.on('second-instance',()=>{if(window){window.show();window.focus();}});
  app.whenReady().then(start).catch(error=>{dialog.showErrorBox('Backwoods Business Accounting',error.message);app.quit();});
}
async function start(){
  const updates=require('./updater/electron.cjs').setup({kind:'accounting',name:'Business Accounting',parent:()=>window});
  ipcMain.handle('backwoods:open-updates',event=>{if(event.sender!==window?.webContents||event.senderFrame!==window.webContents.mainFrame)throw Error('Main app window required');return updates.open();});
  const remote=require('./company-server.cjs').companyServer(process.env.BACKWOODS_ACCOUNTING_SERVER_URL);
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label:'File',submenu:[{label:'Print current view',accelerator:'CmdOrCtrl+P',click:()=>window?.webContents.print({printBackground:true})},{type:'separator'},{label:'Quit',accelerator:'CmdOrCtrl+Q',click:()=>app.quit()}]},
    {label:'Edit',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},
    {label:'Help',submenu:[{label:'App updates…',click:()=>updates.open()}]},
    {label:'View',submenu:[{role:'reload'},{role:'resetZoom'},{role:'zoomIn'},{role:'zoomOut'},{role:'togglefullscreen'}]}
  ]));
  const base=app.isPackaged?process.resourcesPath:path.join(__dirname,'..','.build-resources');
  const python=process.platform==='win32'?path.join(base,'python','python.exe'):process.env.BACKWOODS_TEST_PYTHON||'python3';
  const backend=app.isPackaged?path.join(base,'backend'):path.join(__dirname,'..');
  window=new BrowserWindow({width:1480,height:1000,minWidth:1050,minHeight:700,title:'Backwoods Business Accounting',backgroundColor:'#f5f5ef',icon:path.join(__dirname,'icon.ico'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
  await window.loadURL('data:text/html;charset=utf-8,'+encodeURIComponent('<html><body style="margin:0;background:#153e35;color:#fff;display:grid;place-content:center;height:100vh;font:16px system-ui"><h1>Backwoods</h1><p>Opening your company books…</p></body></html>'));
  if(!remote){
  let pending='',logs='';
  worker=spawn(python,['-u',path.join(backend,'run.py'),'--no-browser','--port','0'],{cwd:backend,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  const started=setTimeout(()=>{dialog.showErrorBox('Startup is taking longer than expected','Close the app and try again. Your accounting records are preserved.');},30000);
  worker.stdout.on('data',buffer=>{
    pending+=buffer.toString();
    const lines=pending.split(/\r?\n/);pending=lines.pop();
    for(const line of lines){
      const match=/^Open: (http:\/\/127\.0\.0\.1:\d+)$/.exec(line.trim());
      if(match){clearTimeout(started);origin=match[1];window.loadURL(origin);}
    }
  });
  worker.stderr.on('data',buffer=>{logs=(logs+buffer.toString()).slice(-6000);});
  worker.on('error',error=>{clearTimeout(started);dialog.showErrorBox('Could not start Business Accounting',error.message);app.quit();});
  worker.on('exit',code=>{clearTimeout(started);if(!quitting){dialog.showErrorBox('Accounting service stopped','The local accounting service exited. Your saved data remains on this computer.\n\n'+logs.slice(-1500));app.quit();}});
  }else origin=remote;
  const secureChild=wc=>{
    wc.setWindowOpenHandler(({url})=>{
      if(origin&&url.startsWith(origin+'/'))return {action:'allow',overrideBrowserWindowOptions:{width:1050,height:900,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true}}};
      if(/^https:\/\//i.test(url))shell.openExternal(url);
      return {action:'deny'};
    });
    wc.on('will-navigate',(event,url)=>{if(origin&&!url.startsWith(origin+'/')&&url!==origin){event.preventDefault();if(/^https:\/\//i.test(url))shell.openExternal(url);}});
  };
  secureChild(window.webContents);
  app.on('web-contents-created',(_event,wc)=>{if(wc!==window?.webContents)secureChild(wc);});
  if(remote)await window.loadURL(origin);
  try {
    tray=new Tray(path.join(__dirname,'icon.ico'));
    tray.setToolTip('Backwoods Business Accounting');
    tray.setContextMenu(Menu.buildFromTemplate([{label:'Open Business Accounting',click:()=>{window.show();window.focus();}},{label:'Exit',click:()=>app.quit()}]));
    tray.on('double-click',()=>window.show());
    window.on('close',event=>{if(!quitting){event.preventDefault();window.hide();}});
  }catch{}
}
app.on('before-quit',()=>{quitting=true;if(worker&&!worker.killed)worker.kill();tray?.destroy();});
app.on('window-all-closed',()=>{if(!tray)app.quit();});
