// Installed source-app smoke with disposable profiles; no live credentials.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {_electron}=require('../desktop/node_modules/playwright');
const [kind,executable,profile]=process.argv.slice(2),reuse=process.argv.includes('--reuse');
(async()=>{
 assert(['main','vendor'].includes(kind));fs.mkdirSync(profile,{recursive:true});
 const app=await _electron.launch({executablePath:executable,env:{...process.env,BACKWOODS_TEST_DATA_DIR:profile},timeout:90000});
 try{
  const page=await app.firstWindow();page.setDefaultTimeout(30000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.route('https://**/*',route=>route.request.url().includes('identitytoolkit.googleapis.com')?route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:{code:400,message:'CONFIGURATION_NOT_FOUND'}})}):route.abort());
  await page.waitForURL('file:///**/index.html',{timeout:60000});
  assert.equal(await app.evaluate(({app})=>app.getVersion()),kind==='main'?'8.2.10':'4.1.9');
  if(kind==='main'){
   await page.getByPlaceholder('Username',{exact:true}).waitFor();
   const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'../.test-fixtures/main-native.json')));
   if(!reuse)await page.evaluate(f=>{localStorage.setItem('backwoods-brew-stable-data',JSON.stringify(f.data));localStorage.setItem('backwoods-brew-stable-users',JSON.stringify([f.user]));},fixture);
   await page.reload();await page.getByPlaceholder('Username',{exact:true}).fill('receipt-test');await page.getByPlaceholder('Password',{exact:true}).fill(fixture.password);await page.getByRole('button',{name:'Login',exact:true}).click();await page.getByRole('heading',{name:'Owner Portal',exact:true}).waitFor();
   for(const name of ['Subscriptions','Launch Wizard','Guided Walkthrough'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0);
   const data=await page.evaluate(()=>JSON.parse(localStorage.getItem('backwoods-brew-stable-data')));assert.deepEqual(data.subscription,fixture.data.subscription);assert.deepEqual(data.launchWizardActions,fixture.data.launchWizardActions);assert.deepEqual(data.wholesaleSentinel,fixture.data.wholesaleSentinel);
  }else{
   await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();assert.equal(await page.evaluate(()=>typeof window.__bwVendorClockContext),'function');
   // The module is loaded by the real packaged renderer; login is verified in
   // the separate real Auth/Firestore+Employee integration acceptance.
   assert.equal(await page.locator('script[src*="vendor-clock.mjs"]').count(),1);
   const sentinel=await page.evaluate(reuse=>{if(!reuse)localStorage.setItem('coordinated-native-preserve','fixture-keep');return localStorage.getItem('coordinated-native-preserve');},reuse);assert.equal(sentinel,'fixture-keep');
  }
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(profile,reuse?'reinstalled.png':'installed.png'),fullPage:true});
  console.log('PASS installed '+kind+' renderer, version and profile preservation'+(reuse?' after reinstall.':'.'));
 }finally{await app.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
