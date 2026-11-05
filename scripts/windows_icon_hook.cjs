const path=require('node:path');
const {execFileSync}=require('node:child_process');
module.exports=async context=>{
  if(context.electronPlatformName!=='win32') return;
  const root=path.resolve(__dirname,'..');
  const name=context.packager.appInfo.productName;
  const kind=name.includes('Vendor')?'vendor':name==='Backwoods Business Accounting'?'accounting':'main';
  const icon=kind==='accounting'?path.join(root,'desktop/icon.ico'):path.join(root,'source-app-updates',kind,kind==='vendor'?'dist/icons/app.ico':'assets/icon.ico');
  execFileSync(process.execPath,[path.join(__dirname,'set_windows_icon.cjs'),path.join(context.appOutDir,name+'.exe'),icon,name,context.packager.appInfo.version],{stdio:'inherit'});
};
