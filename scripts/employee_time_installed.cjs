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
 const app=await _electron.launch({executablePath:executable,env:{...process.env,LOCALAPPDATA:path.join(profile,'local'),APPDATA:path.join(profile,'roaming')},timeout:90000});
 try{
  const page=await app.firstWindow();await page.waitForURL(/^http:\/\/127\.0\.0\.1:/,{timeout:90000});
  const version=await app.evaluate(({app})=>app.getVersion());assert.equal(version,'1.0.7');
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
  await page.screenshot({path:path.join(profile,reuse?'accounting-reinstalled.png':'accounting-installed.png'),fullPage:true});
  fs.writeFileSync(path.join(profile,reuse?'reinstall-result.json':'install-result.json'),JSON.stringify({version,employeeRecords:value.employeeTime.length,profit:value.report.profit,originalExpensePreserved:true,reuse},null,2));
  console.log('PASS: installed Accounting '+version+' imports approved Employee hours/PTO without financial postings or duplicates and preserves existing records'+(reuse?' after reinstall.':'.'));
 }finally{await app.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
