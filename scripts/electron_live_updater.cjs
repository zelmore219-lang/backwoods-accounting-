// Real Electron transport smoke test, run with the pinned Electron executable.
const {app,session,net}=require('electron');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const root=path.resolve(__dirname,'..');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'backwoods-updater-network-'));
app.setPath('userData',temporary);app.disableHardwareAcceleration();
if(process.platform==='linux')app.commandLine.appendSwitch('ozone-platform','headless');
const timeout=setTimeout(()=>{console.error('Electron updater network test timed out.');app.exit(1);},180000);
app.whenReady().then(async()=>{
 try{
  const core=require('../connectors/updater/core.cjs');
  const transport=require('../connectors/updater/electron-transport.cjs');
  const network=session.fromPath(path.join(temporary,'network'));
  if(process.env.HTTPS_PROXY)await network.setProxy({proxyRules:process.env.HTTPS_PROXY});
  const fetch=transport(net,network),feed=await core.readFeed(fetch,core.FEED);
  if(!feed.apps.main||!feed.apps.vendor||!feed.apps.accounting)throw Error('The live feed is incomplete.');
  if(process.argv.includes('--download')){
   const info=core.select(feed,'vendor','0.0.0');
   const downloaded=await core.download(fetch,info,path.join(temporary,'downloads'));
   await core.verify(downloaded,info);fs.rmSync(path.dirname(downloaded),{recursive:true,force:true});
   console.log('PASS: real Electron fetched the live feed and downloaded/verified the published Vendor Windows installer, including redirects, byte count, MZ header and SHA-256. TLS verification remained enabled.');
  }else console.log('PASS: real Electron fetched the public GitHub update feed through its HTTPS redirects.');
  clearTimeout(timeout);app.exit(0);
 }catch(error){clearTimeout(timeout);console.error(error.message);app.exit(1);}
});
