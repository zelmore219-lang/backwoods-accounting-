const fs=require('node:fs/promises');
const path=require('node:path');
module.exports=async context=>{
 const root=path.resolve(__dirname,'..'),source=path.join(root,'connectors/updater');
 const name=context.packager.appInfo.productName;
 const target=name==='Backwoods Business Accounting'?path.join(root,'desktop/updater'):path.join(root,'source-app-updates',name.includes('Vendor')?'vendor':'main','electron/updater');
 await fs.mkdir(target,{recursive:true});
 for(const entry of await fs.readdir(source))await fs.copyFile(path.join(source,entry),path.join(target,entry));
};
