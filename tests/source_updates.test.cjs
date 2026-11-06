const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const fsp=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const vm=require('node:vm');
const {EventEmitter}=require('node:events');
const {prepareProfile,prepareProfileWithChooser,MARKER}=require('../connectors/connected-profile.cjs');
const ROOT=path.resolve(__dirname,'..');
const {companyServer}=require('../desktop/company-server.cjs');
const config={originalLabel:'Original app',connectedProfile:'Connected app',originalProfiles:['Original app','old-name'],originalExecutables:['Original app.exe']};

test('desktop shared-ledger mode accepts an exact HTTPS origin only',()=>{
  assert.equal(companyServer(undefined),null);
  assert.equal(companyServer('https://BOOKS.example.test:443/'),'https://books.example.test');
  for(const url of ['http://books.example.test','https://user:secret@books.example.test','https://books.example.test/path','https://books.example.test?token=secret','https://books.example.test#fragment'])
    assert.throws(()=>companyServer(url),/HTTPS origin/);
});

function fixture(){
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'backwoods-profile-test-'));
  const messages=[];const paths={appData:folder};let exited=null;
  return {folder,messages,paths,app:{getPath:n=>paths[n],setPath:(n,p)=>paths[n]=p,whenReady:()=>Promise.resolve(),exit:n=>exited=n},
    dialog:{showErrorBox:(title,message)=>messages.push({title,message,error:true}),showMessageBox:m=>messages.push(m)},
    cleanup:()=>fs.rmSync(folder,{recursive:true,force:true}),get exited(){return exited;}};
}
function source(f,name='Original app'){
  const folder=path.join(f.folder,name);fs.mkdirSync(path.join(folder,'Local Storage'),{recursive:true});
  fs.writeFileSync(path.join(folder,'Local Storage','records.json'),JSON.stringify({sales:[{id:'sale-1',amount:10}]}));
  fs.mkdirSync(path.join(folder,'Cache'));fs.writeFileSync(path.join(folder,'Cache','temporary'),'cache');return folder;
}

test('first connected launch copies business storage and leaves original bytes unchanged',()=>{
  const f=fixture();try{
    const src=source(f);const original=fs.readFileSync(path.join(src,'Local Storage','records.json'));
    const result=prepareProfile(f,config,{env:{},platform:'win32',spawnSync:()=>({status:0,stdout:'"other.exe","1"\n'})});
    assert.equal(result.mode,'copied-original-profile');assert.deepEqual(fs.readFileSync(path.join(result.directory,'Local Storage','records.json')),original);
    assert.deepEqual(fs.readFileSync(path.join(src,'Local Storage','records.json')),original);assert(!fs.existsSync(path.join(result.directory,'Cache')));
    assert.equal(JSON.parse(fs.readFileSync(path.join(result.directory,MARKER))).sourceProfile,src);
    fs.writeFileSync(path.join(result.directory,'Local Storage','records.json'),'new connected records');
    prepareProfile(f,config,{env:{},platform:'linux'});
    assert.equal(fs.readFileSync(path.join(result.directory,'Local Storage','records.json'),'utf8'),'new connected records');
  }finally{f.cleanup();}
});
test('running original app blocks profile copying',()=>{
  const f=fixture();try{source(f);assert.throws(()=>prepareProfile(f,config,{env:{},platform:'win32',spawnSync:()=>({status:0,stdout:'"Original app.exe","123"\n'})}),/Close the original/);assert.equal(f.exited,1);assert(!fs.existsSync(path.join(f.folder,config.connectedProfile)));}finally{f.cleanup();}
});
test('ambiguous original profiles do not get selected silently',()=>{
  const f=fixture();try{source(f);source(f,'old-name');assert.throws(()=>prepareProfile(f,config,{env:{},platform:'linux'}),/More than one/);assert(!fs.existsSync(path.join(f.folder,config.connectedProfile)));}finally{f.cleanup();}
});
test('ambiguous Main profiles are copied only after an explicit chooser selection',async()=>{
  const f=fixture();try{
    const first=source(f),second=source(f,'old-name');fs.writeFileSync(path.join(second,'Local Storage','records.json'),'chosen records');
    f.dialog.showMessageBox=async options=>{f.messages.push(options);return {response:1};};
    const result=await prepareProfileWithChooser(f,config,{env:{},platform:'linux'});
    assert.equal(result.mode,'copied-original-profile');
    assert.equal(fs.readFileSync(path.join(result.directory,'Local Storage','records.json'),'utf8'),'chosen records');
    assert.equal(JSON.parse(fs.readFileSync(path.join(result.directory,MARKER))).sourceProfile,second);
    assert.equal(JSON.parse(fs.readFileSync(path.join(first,'Local Storage','records.json'))).sales[0].id,'sale-1');
    assert.equal(fs.readFileSync(path.join(second,'Local Storage','records.json'),'utf8'),'chosen records');
    assert(f.messages[0].detail.includes('Local data last changed:'));
    f.dialog.showMessageBox=async()=>{throw Error('Existing connected profiles must not ask again');};
    await prepareProfileWithChooser(f,config,{env:{},platform:'linux'});
  }finally{f.cleanup();}
});
test('cancelling the profile chooser leaves every profile untouched',async()=>{
  const f=fixture();try{
    source(f);source(f,'old-name');f.dialog.showMessageBox=async()=>({response:2});
    const result=await prepareProfileWithChooser(f,config,{env:{},platform:'linux'});
    assert.equal(result.cancelled,true);assert.equal(f.exited,0);assert(!fs.existsSync(path.join(f.folder,config.connectedProfile)));
  }finally{f.cleanup();}
});
test('existing unmarked connected data is preserved and blocks startup',()=>{
  const f=fixture();try{const target=path.join(f.folder,config.connectedProfile);fs.mkdirSync(target);fs.writeFileSync(path.join(target,'important'),'keep');assert.throws(()=>prepareProfile(f,config,{env:{},platform:'linux'}),/already contains files/);assert.equal(fs.readFileSync(path.join(target,'important'),'utf8'),'keep');}finally{f.cleanup();}
});
test('missing explicitly selected source does not fall back to a blank profile',()=>{
  const f=fixture();try{assert.throws(()=>prepareProfile(f,config,{env:{BACKWOODS_SOURCE_PROFILE:path.join(f.folder,'missing')},platform:'linux'}),/explicitly selected/);}finally{f.cleanup();}
});
test('fresh profile is explicitly disclosed',async()=>{
  const f=fixture();try{const r=prepareProfile(f,config,{env:{},platform:'linux'});await Promise.resolve();assert.equal(r.mode,'fresh-profile');assert(f.messages.some(m=>m.message==='No previous local profile was found.'));}finally{f.cleanup();}
});
test('test profile override never copies live source records',()=>{
  const f=fixture();try{source(f);const target=path.join(f.folder,'test-only');const r=prepareProfile(f,config,{env:{BACKWOODS_TEST_DATA_DIR:target},platform:'linux'});assert.equal(r.mode,'explicit-test-profile');assert(!fs.existsSync(path.join(target,'Local Storage')));}finally{f.cleanup();}
});
test('unrecognized symbolic profile data is rejected without modifying its source',{skip:process.platform==='win32'},()=>{
  const f=fixture();try{const src=source(f);fs.writeFileSync(path.join(f.folder,'outside'),'keep');fs.symlinkSync(path.join(f.folder,'outside'),path.join(src,'unexpected-link'));assert.throws(()=>prepareProfile(f,config,{env:{},platform:'linux'}),/linked profile file/);assert.equal(fs.readFileSync(path.join(f.folder,'outside'),'utf8'),'keep');assert(!fs.existsSync(path.join(f.folder,config.connectedProfile)));}finally{f.cleanup();}
});
test('source connector writes a redacted financial snapshot and survives window cleanup',async()=>{
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'backwoods-feed-test-'));const app=new EventEmitter();let interval,handler;
  const packet={schemaVersion:1,app:'Test source',data:{orders:[{id:'o1',amount:10,password:'not-financial'}],users:[{accessToken:'not-financial'}]}};
  const sourceWindow={__bwAccountingCloudContext:()=>({uid:'owner',auth:{currentUser:{uid:'owner'}}}),__bwAccountingSnapshot:()=>packet};
  const contents=Object.assign(new EventEmitter(),{id:7,getURL:()=> 'file:///connected/index.html',executeJavaScript:async script=>vm.runInNewContext(script,{window:sourceWindow})});
  const win=new EventEmitter();win.id=1;win.webContents=contents;win.isDestroyed=()=>false;
  const sandbox={require:n=>n==='electron'?{app,ipcMain:{handle:(_name,fn)=>handler=fn}}:n==='./business-accounting-config.json'?{source:'vendor'}:require(n),
    process:{platform:'win32',pid:123,env:{LOCALAPPDATA:folder}},setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{},URL,Date,Map,Set};
  try{
    vm.runInNewContext(fs.readFileSync(path.join(ROOT,'connectors/desktop-feed.cjs'),'utf8'),sandbox);
    app.emit('browser-window-created',{},win);await interval();
    const target=path.join(folder,'BackwoodsBusinessAccounting/feeds/vendor.json');const payload=JSON.parse(fs.readFileSync(target,'utf8'));
    assert.equal(payload.data.orders[0].amount,10);assert(!('password' in payload.data.orders[0]));assert(!('accessToken' in payload.data.users[0]));
    assert(payload.exportedAt);const status=await handler({sender:contents});assert(status.sentAt);
    const before=fs.readFileSync(target);await interval();assert.deepEqual(fs.readFileSync(target),before);
    sourceWindow.__bwAccountingCloudContext=()=>null;packet.data.orders[0].amount=99;await interval();assert.deepEqual(fs.readFileSync(target),before);
    win.webContents=null;assert.doesNotThrow(()=>win.emit('closed'));
  }finally{fs.rmSync(folder,{recursive:true,force:true});}
});
test('prepared update packages include the profile helper, sender and renderer assets',()=>{
  for(const kind of ['main','vendor']){
    const folder=path.join(ROOT,'source-app-updates',kind);const pkg=JSON.parse(fs.readFileSync(path.join(folder,'package.json')));
    assert(pkg.productName.endsWith('Connected'));assert(pkg.build.appId.endsWith('.connected'));assert.equal(pkg.build.nsis.deleteAppDataOnUninstall,false);
    assert(fs.readFileSync(path.join(folder,'electron/main.cjs'),'utf8').includes("require('./connected-profile.cjs').prepareProfile"));
    assert(fs.existsSync(path.join(folder,kind==='main'?'www/index.html':'dist/index.html')));
  }
});
test('original retail and wholesale business logic is retained outside accounting-copy hooks and cost metadata',()=>{
  const cases=[
    {kind:'main',file:'www/assets/main-CnsZnSKS.js',sha:'56f226409966eae27e0127d72b670956b2d78731ebff4a5df2b955893906b0de'},
    {kind:'vendor',file:'dist/assets/index-CWBa4KXx.js',sha:'7b639f76f6c0a6d541895bc4a6753d33ad237c7b4ac9074d7dcc260225043ec1'},
  ];
  for(const item of cases){
    const code=fs.readFileSync(path.join(ROOT,'source-app-updates',item.kind,item.file),'utf8');
    let restored;
    if(item.kind==='main'){
      const start=code.indexOf('window.__bwAccountingCloudContext=');
      const end=code.indexOf('\n  function P(',start);
      assert(start>0&&end>start);restored=code.slice(0,start).trimEnd()+code.slice(end);
    }else{
      const start=code.indexOf('\nwindow.__bwAccountingCloudContext=');
      const end=code.indexOf('\n};',start)+3;
      assert(start>0&&end>start);restored=code.slice(0,start)+code.slice(end).replace(/^\n+/,'');
      for(const metadata of ['unitCost:Number(Ce.cost||0),accountingCostCaptured:true,','unitCost:Number((xe.products.find(p=>p.id===Z.productId)||{}).cost||0),accountingCostCaptured:true,'])
        restored=restored.split(metadata).join('');
    }
    assert.equal(require('node:crypto').createHash('sha256').update(restored).digest('hex'),item.sha,item.kind+' native business logic changed');
  }
});
test('main export uses native ledger settings without exporting credentials or mirrored invoices',()=>{
  const script=fs.readFileSync(path.join(ROOT,'scripts/build_connected_apps.py'),'utf8');
  const hook=/MAIN_HOOK=r'''([\s\S]*?)'''/.exec(script)[1];
  const native={accounts:[],orders:[],invoices:[{id:'vendor-copy',sourceSystem:'vendor-ordering'}],settings:{nativeSetting:42,privateSetting:'not exported'}};
  const sandbox={window:{dispatchEvent:()=>true},e:{useEffect:fn=>assert.equal(fn(),undefined,'the source-change effect must not return dispatchEvent\'s boolean as React cleanup')},Event,t:false,a:{role:'owner'},r:native,Ga:data=>{assert.equal(data.settings.nativeSetting,42);assert.equal(data.invoices.length,0);return [];}};
  const before=JSON.stringify(native);vm.runInNewContext(hook,sandbox);const packet=sandbox.window.__bwAccountingSnapshot();
  assert(!('settings' in packet.data));assert.equal(JSON.stringify(native),before);
  sandbox.a.active=false;assert.equal(sandbox.window.__bwAccountingSnapshot(),null);
});
