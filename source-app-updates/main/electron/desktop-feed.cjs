// Main-process, file-only connector. Source books and remote databases are read-only.
const {app, ipcMain} = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const source = require('./business-accounting-config.json').source;
if(process.env.BACKWOODS_TEST_DATA_DIR)app.setPath('userData',path.resolve(process.env.BACKWOODS_TEST_DATA_DIR));
const root = process.platform === 'win32'
  ? path.join(process.env.LOCALAPPDATA || os.homedir(), 'BackwoodsBusinessAccounting')
  : path.join(process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local/share'), 'BackwoodsBusinessAccounting');
const feedDir=path.join(root,'feeds');
const state=new Map();
const sensitive=new Set(['password','passwordhash','passwordsalt','accesstoken','refreshtoken','clientsecret','privatekey','ssn','socialsecuritynumber','routingnumber','bankaccountnumber','apikey']);
function accountingOnly(value){
  if(Array.isArray(value))return value.map(accountingOnly);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>!sensitive.has(key.toLowerCase().replace(/[^a-z]/g,''))).map(([key,item])=>[key,accountingOnly(item)]));
  return value;
}
function localWindow(wc) { try { return new URL(wc.getURL()).protocol==='file:'; } catch { return false; } }
ipcMain.handle('business-accounting:status', async event => {
  if (!localWindow(event.sender)) throw Error('Local application window required');
  let received=null;
  try { received=JSON.parse(await fs.readFile(path.join(feedDir,source+'-status.json'),'utf8')); } catch {}
  return {source,feedDir,...state.get(event.sender.id),received};
});
app.on('browser-window-created',(_event,win)=>{
  const windowContentsId=win.webContents.id;
  let busy=false,lastHash='',lastSent=0;
  const send=async()=>{
    if(busy||win.isDestroyed()||!localWindow(win.webContents))return;
    busy=true;
    try {
      const raw=await win.webContents.executeJavaScript(`(() => {
        const c=window.__bwAccountingCloudContext?.();
        if(!c?.auth?.currentUser||c.uid!==c.auth.currentUser.uid)return null;
        return typeof window.__bwAccountingSnapshot==='function' ? window.__bwAccountingSnapshot() : null;
      })()`);
      const packet=accountingOnly(raw);
      if(!packet){state.set(win.webContents.id,{message:'Not sending. Sign in as the owner.'});return;}
      const hash=crypto.createHash('sha256').update(JSON.stringify(packet)).digest('hex');
      // Refresh a heartbeat even if records do not change, so an old receipt is visible.
      if(hash===lastHash)return;
      await fs.mkdir(feedDir,{recursive:true});
      const dest=path.join(feedDir,source+'.json');
      const temporary=path.join(feedDir,source+'-'+process.pid+'-'+win.id+'.tmp');
      await fs.writeFile(temporary,JSON.stringify({...packet,exportedAt:new Date().toISOString()}),{encoding:'utf8',mode:0o600});
      await fs.rename(temporary,dest);
      lastHash=hash;lastSent=Date.now();
      state.set(win.webContents.id,{sentAt:new Date().toISOString(),message:'Snapshot saved for Business Accounting.'});
    } catch(error) {state.set(win.webContents.id,{error:error.message});}
    finally {busy=false;}
  };
  const timer=setInterval(send,5000);
  win.webContents.on('did-finish-load',send);
  win.on('closed',()=>{clearInterval(timer);state.delete(windowContentsId);});
});
