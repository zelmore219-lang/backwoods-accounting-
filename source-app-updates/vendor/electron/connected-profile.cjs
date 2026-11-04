// Copy an existing source profile before Chromium opens the connected edition.
// The original profile is never modified, removed, or opened by this helper.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const MARKER = 'business-accounting-profile.json';
const SKIP = new Set(['Cache','Code Cache','GPUCache','DawnCache','Crashpad','SingletonLock','SingletonCookie','SingletonSocket']);

function populated(directory) {
  return fs.existsSync(directory) && fs.statSync(directory).isDirectory() && fs.readdirSync(directory).length>0;
}

function copyProfile(source, destination) {
  const temporary=destination+'.copying-'+crypto.randomUUID();
  try {
    fs.cpSync(source,temporary,{recursive:true,errorOnExist:true,force:false,filter:item=>{
      const name=path.basename(item);
      if(SKIP.has(name)||name==='LOCK')return false;
      if(fs.lstatSync(item).isSymbolicLink())throw Error('A linked profile file needs manual review: '+item);
      return true;
    }});
    fs.writeFileSync(path.join(temporary,MARKER),JSON.stringify({sourceProfile:source,copiedAt:new Date().toISOString(),method:'copy-before-first-launch'},null,2));
    fs.renameSync(temporary,destination);
  } catch(error) {
    // Remove only this operation's incomplete staging copy, never either profile.
    fs.rmSync(temporary,{recursive:true,force:true});
    throw Error('The existing app profile could not be copied safely. Close the original app and try again. No original records were changed. '+error.message);
  }
}

function prepareProfile({app,dialog},config,options={}) {
  const env=options.env||process.env;
  const platform=options.platform||process.platform;
  const run=options.spawnSync||spawnSync;
  const appData=app.getPath('appData');
  const target=path.resolve(env.BACKWOODS_TEST_DATA_DIR||path.join(appData,config.connectedProfile));
  try {
    if(env.BACKWOODS_TEST_DATA_DIR){
      fs.mkdirSync(target,{recursive:true});
      app.setPath('userData',target);
      return {directory:target,mode:'explicit-test-profile'};
    }
    if(fs.existsSync(path.join(target,MARKER))){
      app.setPath('userData',target);return {directory:target,mode:'existing-connected-profile'};
    }
    if(populated(target))throw Error('The connected profile folder already contains files without a migration marker. Preserve and review this folder before continuing: '+target);
    // A previous empty destination is safe to remove before the atomic rename.
    if(fs.existsSync(target))fs.rmdirSync(target);
    const candidates=env.BACKWOODS_SOURCE_PROFILE?[path.resolve(env.BACKWOODS_SOURCE_PROFILE)]:config.originalProfiles.map(name=>path.join(appData,name));
    const present=candidates.filter(populated);
    if(present.length>1)throw Error('More than one previous app profile was found. Set BACKWOODS_SOURCE_PROFILE to the profile you intend to copy. No profile was changed.');
    if(env.BACKWOODS_SOURCE_PROFILE && !present.length)throw Error('The explicitly selected source profile was not found. No fresh profile was substituted.');
    if(present.length){
      if(platform==='win32'){
        const result=run('tasklist.exe',['/FO','CSV','/NH'],{encoding:'utf8',windowsHide:true});
        if(result.error||result.status!==0)throw Error('Windows could not confirm that the previous app is closed. Close it and retry.');
        const names=String(result.stdout).split(/\r?\n/).map(row=>/^"([^"]+)"/.exec(row)?.[1]?.toLowerCase());
        if(config.originalExecutables.some(name=>names.includes(name.toLowerCase())))throw Error('Close the original '+config.originalLabel+' before opening this connected edition. Its local records must be copied while it is closed.');
      }
      copyProfile(present[0],target);
    } else {
      fs.mkdirSync(target,{recursive:true});
      fs.writeFileSync(path.join(target,MARKER),JSON.stringify({copiedAt:new Date().toISOString(),method:'fresh-profile',sourceProfile:null},null,2));
      app.whenReady().then(()=>dialog.showMessageBox({type:'info',title:config.originalLabel+' Connected',message:'No previous local profile was found.',detail:'This connected edition has started with a fresh local profile. Your original files have not been changed. Sign in with your usual account, or restore a source-app backup before enabling the accounting connection.'}));
    }
    app.setPath('userData',target);
    return {directory:target,mode:present.length?'copied-original-profile':'fresh-profile'};
  } catch(error) {
    dialog.showErrorBox(config.originalLabel+' — profile setup',error.message);
    app.exit(1);
    throw error;
  }
}
module.exports={prepareProfile,copyProfile,MARKER};
