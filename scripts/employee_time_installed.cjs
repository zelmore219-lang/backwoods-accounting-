// Disposable Windows installer acceptance; no company data or external payments.
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {_electron}=require('../desktop/node_modules/playwright');
const executable=process.argv[2],profile=path.resolve(process.argv[3]),reuse=process.argv.includes('--reuse');
const payload=JSON.parse(fs.readFileSync(path.join(__dirname,'../.test-fixtures/employee-time.json'),'utf8'));
const api=(page,route,data)=>page.evaluate(async({route,data})=>{
 const response=await fetch(route,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Accounting-Request':'1'},body:JSON.stringify(data)});
 const value=await response.json();if(!response.ok)throw Error(value.error||'Accounting fixture request failed');return value;
},{route,data});
(async()=>{
 fs.mkdirSync(profile,{recursive:true});
 const app=await _electron.launch({executablePath:executable,...(process.env.BACKWOODS_NATIVE_SOURCE_PROJECT?{args:['--no-sandbox','--ozone-platform=headless',process.env.BACKWOODS_NATIVE_SOURCE_PROJECT]}:{}),env:{...process.env,LOCALAPPDATA:path.join(profile,'local'),APPDATA:path.join(profile,'roaming'),XDG_DATA_HOME:path.join(profile,'local'),XDG_CONFIG_HOME:path.join(profile,'roaming')},timeout:90000});
 try{
  const page=await app.firstWindow();await page.waitForURL(/^http:\/\/127\.0\.0\.1:/,{timeout:90000});
  const version=await app.evaluate(({app})=>app.getVersion());assert.equal(version,'1.0.8');
  await api(page,reuse?'/api/auth/login':'/api/auth/setup',{name:'Fictitious Accounting Owner',username:'time.fixture.owner',password:'fixture-only-long-passphrase'});
  if(!reuse)await api(page,'/api/manual-document',{kind:'expense',date:'2026-10-18',party:'Fictitious utility',reference:'KEEP-TIME-FIXTURE',amount:'12.50',account:'5100'});
  await page.reload();await page.locator('nav [data-view="imports"]').click();
  const form=page.locator('#import-form');await form.locator('[name=source]').selectOption('employees');
  await form.locator('[name=file]').setInputFiles({name:'business-accounting-time.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(payload))});
  await form.getByRole('button',{name:'Preview import',exact:true}).click();
  await page.locator('#import-preview').filter({hasText:reuse?'2 duplicates':'2 new'}).waitFor();
  await page.getByRole('button',{name:'Import into company ledger',exact:true}).click();
  await page.locator('#notice:not([hidden])').waitFor();
  const value=await api(page,'/api/state');assert.equal(value.employeeTime.length,2);assert.equal(value.report.profit,-1250);
  assert.equal(value.documents.filter(item=>item.source==='employees').length,2);
  await page.locator('nav [data-view="payroll"]').click();
  await page.getByRole('heading',{name:'Approved Employee hours & PTO',exact:true}).waitFor();
  assert.ok((await page.locator('#content').innerText()).includes('Delivery'));
  if(!reuse){
   const seed=JSON.parse(fs.readFileSync(path.join(__dirname,'../.test-fixtures/payroll-roster.json')));
   const initialized=await app.evaluate(({app},{seed})=>{
    const require=process.mainModule?.require?process.mainModule.require.bind(process.mainModule):process.getBuiltinModule('node:module').createRequire(app.getAppPath()+'/package.json'),path=require('node:path'),{spawnSync}=require('node:child_process');
    const resources=path.dirname(app.getAppPath()),backend=app.isPackaged?path.join(resources,'backend'):resources,python=app.isPackaged?path.join(resources,'python/python.exe'):process.env.BACKWOODS_TEST_PYTHON||'python3';
    const code='import json,sys;from accounting.server import default_data_dir;from accounting.ledger import Ledger;from accounting import payroll_management as pm;l=Ledger(default_data_dir()/"accounting.sqlite3");pm.sync_employees(l,"native-fictional-workspace-001",json.loads(sys.stdin.read()),confirm=True);pm.save_provider(l,{"id":"hrmy","name":"HR.my external workflow"});l.close()';
    const result=spawnSync(python,['-c',code],{cwd:backend,encoding:'utf8',input:JSON.stringify(seed),timeout:30000});return {status:result.status,error:result.stderr};
   },{seed});assert.equal(initialized.status,0,initialized.error);
  }
  await page.reload();await page.getByRole('button',{name:'Payroll Management',exact:true}).click();await page.getByRole('heading',{name:'Payroll Management',exact:true}).waitFor();
  if(!reuse){
   await page.getByRole('button',{name:'Prepare payroll',exact:true}).click();const form=page.locator('[data-pm-form=prepare]');
   await form.getByLabel('Method',{exact:true}).selectOption('manual');await form.getByLabel('Period start',{exact:true}).fill('2026-10-26');await form.getByLabel('Period end (exclusive)',{exact:true}).fill('2026-11-02');await form.getByLabel('Pay date',{exact:true}).fill('2026-11-06');
   await form.getByLabel('Regular hours',{exact:true}).fill('40');await form.getByLabel('Overtime hours',{exact:true}).fill('5');await form.getByLabel('Approved overtime hourly rate',{exact:true}).fill('22.50');await form.getByLabel('Bonus',{exact:true}).fill('50');
   await form.getByRole('button',{name:'Calculate preview',exact:true}).click();await page.locator('[data-pm-preview]').filter({hasText:'$762.50'}).waitFor();
   await form.getByRole('button',{name:'Create payroll draft',exact:true}).click();await page.getByRole('heading',{name:'Payroll batch',exact:true}).waitFor();
  }
  const payroll=await api(page,'/api/payroll-management');assert.equal(payroll.batches.length,1);assert.equal(payroll.batches[0].totals[0].grossCents,76250);
  const retained=await api(page,'/api/state');assert.equal(retained.report.profit,-1250);assert.equal(retained.employeeTime.length,2);
  await page.screenshot({path:path.join(profile,reuse?'accounting-reinstalled.png':'accounting-installed.png'),fullPage:true});
  fs.writeFileSync(path.join(profile,reuse?'reinstall-result.json':'install-result.json'),JSON.stringify({version,employeeRecords:value.employeeTime.length,profit:value.report.profit,originalExpensePreserved:true,reuse},null,2));
  console.log('PASS: installed Accounting '+version+' imports approved Employee hours/PTO without financial postings or duplicates and preserves existing records'+(reuse?' after reinstall.':'.'));
 }finally{await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
