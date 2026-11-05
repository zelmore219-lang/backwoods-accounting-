const {app,BrowserWindow,ipcMain,net,dialog,shell,Notification}=require('electron');
const fs=require('node:fs/promises');
const path=require('node:path');
const core=require('./core.cjs');
function setup({kind,name,parent}){
 let wizard,busy=false,info,downloaded='',notifiedVersion='',config={enabled:true,autoDownload:false,feedUrl:core.FEED};
 let state={phase:'idle',message:'Ready to check for updates.',currentVersion:app.getVersion(),latestVersion:'',percent:0};
 const configFile=path.join(app.getPath('userData'),'app-updates.json');
 const pendingFile=path.join(app.getPath('userData'),'updates/pending.json');
 const emit=patch=>{state={...state,...patch,...config};if(wizard&&!wizard.isDestroyed())wizard.webContents.send('backwoods:update-state',state);return state;};
 const check=async()=>{
  if(busy)return state;
  if(!config.enabled)return emit({phase:'disabled',message:'Update checks are disabled.'});
  const previous=info,previousDownload=downloaded;
  busy=true;info=undefined;downloaded='';emit({phase:'checking',message:'Checking for updates…',latestVersion:'',percent:0});
  try{info=core.select(await core.readFeed(net.fetch.bind(net),config.feedUrl),kind,app.getVersion());emit({phase:info.available?'available':'current',message:info.available?'A new version is available.':'You have the latest published version.',latestVersion:info.version,notes:info.notes});
   if(!info.available||previous?.sha256!==info.sha256)await fs.rm(pendingFile,{force:true});
   if(info.available&&previousDownload&&previous?.sha256===info.sha256){await core.verify(previousDownload,info);downloaded=previousDownload;emit({phase:'downloaded',message:'A verified update is ready to install.',percent:100});}
   if(info.available&&notifiedVersion!==info.version&&!wizard&&Notification?.isSupported()){
    const note=new Notification({title:name+' update available',body:'Version '+info.version+' is available. Open App updates to review and install.'});note.on('click',open);note.show();notifiedVersion=info.version;
   }}
  catch(e){if(previous&&previousDownload){try{await core.verify(previousDownload,previous);info=previous;downloaded=previousDownload;emit({phase:'downloaded',message:'Could not check the feed. Your verified downloaded update is still ready to install.',latestVersion:previous.version,percent:100});}catch{emit({phase:'error',message:e.message});}}else emit({phase:'error',message:e.message});}
  finally{busy=false;}
  if(info?.available&&config.autoDownload&&state.phase==='available')await get();return state;
 };
 const get=async()=>{
  if(busy)return state;if(!info?.available)return emit({phase:'error',message:'Check for a newer version first.'});busy=true;downloaded='';emit({phase:'downloading',message:'Downloading and verifying the update…',percent:0});
  try{downloaded=await core.download(net.fetch.bind(net),info,path.join(app.getPath('userData'),'updates'),percent=>emit({percent}));await fs.writeFile(pendingFile,JSON.stringify(info),{mode:0o600});emit({phase:'downloaded',message:'Update verified. Save your work and choose Install when ready.',percent:100});}
  catch(e){emit({phase:'error',message:e.message});}finally{busy=false;}return state;
 };
 const install=async()=>{
  if(busy)return state;if(!downloaded||!info?.available)return emit({phase:'error',message:'Download and verify an update first.'});
  busy=true;
  try{await core.verify(downloaded,info);
   const answer=await dialog.showMessageBox(wizard||parent(),{type:'question',title:'Install '+name+' update',message:`Install version ${info.version}?`,detail:'Save your work and back up your company records first. The app will close and the Windows setup wizard will open. Your company data and login are preserved. This test installer is unsigned.',buttons:['Install and close app','Later'],defaultId:1,cancelId:1});
   if(answer.response===0){emit({phase:'installing',message:'Opening Windows setup…'});const error=await shell.openPath(downloaded);if(error)throw Error(error);app.quit();}
  }catch(e){emit({phase:'error',message:e.message});}finally{busy=false;}return state;
 };
 const allowed=event=>wizard&&!wizard.isDestroyed()&&event.sender===wizard.webContents&&event.senderFrame===wizard.webContents.mainFrame;
 for(const [action,handler] of Object.entries({status:()=>emit({}),check,download:get,install,configure:async value=>{
  if(busy)throw Error('Wait for the current update operation to finish.');
  const feedUrl=core.trustedUrl(String(value.feedUrl||core.FEED));
  config={enabled:value.enabled===true,autoDownload:value.autoDownload===true,feedUrl};
  await fs.mkdir(path.dirname(configFile),{recursive:true});await fs.writeFile(configFile,JSON.stringify(config),{mode:0o600});info=undefined;downloaded='';await fs.rm(pendingFile,{force:true});return emit({phase:'idle',latestVersion:'',percent:0,message:'Update settings saved.'});
 }}))ipcMain.handle('backwoods:update-'+action,async(event,value)=>{if(!allowed(event))throw Error('Open the update wizard to use this action.');if(process.platform!=='win32'&&action!=='status')throw Error('This build installs Windows updates only.');return handler(value);});
 function open(){
  if(wizard&&!wizard.isDestroyed()){wizard.show();wizard.focus();return;}
  wizard=new BrowserWindow({width:760,height:700,minWidth:620,minHeight:600,title:name+' updates',parent:parent(),autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
  wizard.webContents.setWindowOpenHandler(()=>({action:'deny'}));wizard.webContents.on('will-navigate',e=>e.preventDefault());
  wizard.loadFile(path.join(__dirname,'wizard.html'));wizard.on('closed',()=>{wizard=undefined;});
 }
 const ready=(async()=>{try{const value=JSON.parse(await fs.readFile(configFile,'utf8'));config={enabled:value.enabled!==false,autoDownload:value.autoDownload===true,feedUrl:core.trustedUrl(value.feedUrl||core.FEED)};}catch{}
   try{const saved=JSON.parse(await fs.readFile(pendingFile,'utf8'));info=core.select({schemaVersion:1,apps:{[kind]:{windows:saved}}},kind,app.getVersion());if(info.available){downloaded=path.join(app.getPath('userData'),'updates',`update-${info.version}.exe`);await core.verify(downloaded,info);emit({phase:'downloaded',message:'A verified update is ready to install.',latestVersion:info.version,percent:100});}else{info=undefined;downloaded='';}}catch{info=undefined;downloaded='';}emit({});})();
 let timer;
 ready.then(()=>{const initial=setTimeout(()=>{if(process.platform==='win32'&&config.enabled)check();},12000);initial.unref();timer=setInterval(()=>{if(process.platform==='win32'&&config.enabled)check();},6*60*60*1000);timer.unref();});
 app.on('before-quit',()=>clearInterval(timer));
 return {open:()=>ready.then(open)};
}
module.exports={setup};
