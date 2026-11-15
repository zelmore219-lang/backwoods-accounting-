// Installed source-app smoke with disposable profiles; no live credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {_electron}=require('../desktop/node_modules/playwright');
let nativeStage='starting',nativeApp;
const deadline=setTimeout(()=>{console.error('Native test exceeded 120 seconds at '+nativeStage);if(nativeApp?.process()?.pid){const child=nativeApp.process();if(process.platform==='win32')require('node:child_process').spawnSync('taskkill',['/PID',String(child.pid),'/T','/F']);else child.kill('SIGKILL');}process.exit(1);},120000);deadline.unref();
const mark=value=>{nativeStage=value;console.log(value);};
const [kind,executable,profile]=process.argv.slice(2),reuse=process.argv.includes('--reuse');
(async()=>{
 assert(['main','vendor'].includes(kind));fs.mkdirSync(profile,{recursive:true});
 mark('Launching '+kind);
 const app=await _electron.launch({executablePath:executable,...(process.env.BACKWOODS_NATIVE_SOURCE_PROJECT?{args:['--no-sandbox','--ozone-platform=headless',process.env.BACKWOODS_NATIVE_SOURCE_PROJECT]}:{}),env:{...process.env,BACKWOODS_TEST_DATA_DIR:profile},timeout:90000});
 nativeApp=app;
 try{
  mark('Opening '+kind+' window');
  const page=await app.firstWindow();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  // Block network in the actual profile Session, including a profile selected
  // by the chooser; context routing does not cover every native Session.
  await app.evaluate(({BrowserWindow})=>{for(const win of BrowserWindow.getAllWindows())win.webContents.session.protocol.handle('https',request=>new Response(JSON.stringify({error:{code:400,message:'CONFIGURATION_NOT_FOUND'}}),{status:400,headers:{'Content-Type':'application/json','Access-Control-Allow-Origin':'*'}}));});
  const sessions=await app.evaluate(({app,BrowserWindow,session})=>{const win=BrowserWindow.getAllWindows()[0];return {userData:app.getPath('userData'),mainPath:win.webContents.session.storagePath,defaultPath:session.defaultSession.storagePath,same:win.webContents.session===session.defaultSession};});
  console.log('Native storage sessions',sessions);
  if(kind==='main'&&sessions.mainPath===sessions.defaultPath)assert(sessions.same,'One physical profile must use one Electron Session');
  mark('Waiting for '+kind+' packaged page');
  await page.waitForURL('file:///**/index.html',{timeout:60000});
  assert.equal(await app.evaluate(({app})=>app.getVersion()),JSON.parse(fs.readFileSync(path.join(__dirname,'../source-app-updates',kind,'package.json'))).version);
  if(kind==='main'){
   await page.getByPlaceholder('Username',{exact:true}).waitFor();
   const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'../.test-fixtures/main-native.json')));
   assert(fixture.data&&fixture.user);
   const probe=async()=>JSON.parse(await app.evaluate(async({BrowserWindow})=>{
    const windows=BrowserWindow.getAllWindows(),win=windows.find(w=>w.webContents.getURL().split('?')[0].endsWith('/www/index.html'));
    if(!win)throw Error('The actual Main application window is missing');
    const payload=await win.webContents.executeJavaScript('JSON.stringify({raw:localStorage.getItem("backwoods-brew-stable-data"),keys:Object.keys(localStorage),state:window.__backwoodsMainContext?.getData?.(),url:location.href})');
    return payload;
   }));
   if(!reuse){
    const seeded=await app.evaluate(async({BrowserWindow},fixture)=>{
     const win=BrowserWindow.getAllWindows().find(w=>w.webContents.getURL().split('?')[0].endsWith('/www/index.html'));
     return await win.webContents.executeJavaScript('(()=>{const f='+JSON.stringify(fixture)+';localStorage.setItem("backwoods-brew-stable-data",JSON.stringify(f.data));localStorage.setItem("backwoods-brew-stable-users",JSON.stringify([f.user]));return localStorage.getItem("backwoods-brew-stable-data");})()');
    },fixture);
    assert(seeded,'The native fixture must be stored before reload');
    assert.deepEqual(JSON.parse(seeded).subscription,fixture.data.subscription);console.log('Verified native seed before reload');
   }
   mark('Signing into fixture Main');
   await page.reload();await page.getByPlaceholder('Username',{exact:true}).fill('receipt-test');await page.getByPlaceholder('Password',{exact:true}).fill(fixture.password);await page.getByRole('button',{name:'Login',exact:true}).click();await page.getByRole('heading',{name:'Owner Portal',exact:true}).waitFor();
   for(const name of ['Subscriptions','Launch Wizard','Guided Walkthrough'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0);
   const snapshot=await probe();console.log('Native Main storage',JSON.stringify({url:snapshot.url,keys:snapshot.keys,rawLength:snapshot.raw?.length,statePresent:!!snapshot.state}));
   const data=JSON.parse(snapshot.raw||'null');
   assert(data,'Main must retain its real native-session records');assert.deepEqual(data.subscription,fixture.data.subscription);assert.deepEqual(data.launchWizardActions,fixture.data.launchWizardActions);assert.deepEqual(data.wholesaleSentinel,fixture.data.wholesaleSentinel);

  }else{
   await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();assert.equal(await page.evaluate(()=>typeof window.__bwVendorClockContext),'function');
   // The module is loaded by the real packaged renderer; login is verified in
   // the separate real Auth/Firestore+Employee integration acceptance.
   assert.equal(await page.locator('script[src*="vendor-clock.mjs"]').count(),1);
   const sentinel=await page.evaluate(reuse=>{if(!reuse)localStorage.setItem('coordinated-native-preserve','fixture-keep');return localStorage.getItem('coordinated-native-preserve');},reuse);assert.equal(sentinel,'fixture-keep');
  }
  mark('Checking '+kind+' result');
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(profile,reuse?'reinstalled.png':'installed.png'),fullPage:true});
  console.log('PASS installed '+kind+' renderer, version and profile preservation'+(reuse?' after reinstall.':'.'));
 }catch(error){console.error('Failure at '+nativeStage,error);throw error;}finally{
  mark('Closing '+kind);
  const stopped=new Promise(resolve=>app.process().once('exit',resolve));
  await app.evaluate(({app,BrowserWindow})=>{for(const win of BrowserWindow.getAllWindows())win.webContents.session.flushStorageData();setTimeout(()=>app.quit(),0);});
  await stopped;clearTimeout(deadline);
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
