// Embed the application's existing icon and version into an unsigned build.
const fs=require('node:fs');
const path=require('node:path');
async function main(){
  const [filename,icon,name,version]=process.argv.slice(2);
  if(!filename||!icon||!name||!/^\d+\.\d+\.\d+$/.test(version||'')) throw Error('Usage: set_windows_icon.cjs APP.exe ICON.ico NAME VERSION');
  const R=await require('../desktop/node_modules/resedit/cjs.cjs').load();
  const exe=R.NtExecutable.from(fs.readFileSync(filename),{ignoreCert:true});
  const res=R.NtExecutableResource.from(exe);
  const retained=res.entries.filter(e=>![3,14,16].includes(e.type)).map(e=>({type:e.type,id:e.id,lang:e.lang,bin:Buffer.from(e.bin)}));
  const icons=R.Data.IconFile.from(fs.readFileSync(icon)).icons.map(i=>i.data);
  const groups=R.Resource.IconGroupEntry.fromEntries(res.entries);
  for(const group of groups.length?groups:[{id:101,lang:1033}]) R.Resource.IconGroupEntry.replaceIconsForResource(res.entries,group.id,group.lang,icons);
  for(const vi of R.Resource.VersionInfo.fromEntries(res.entries)){
    vi.setFileVersion(...version.split('.').map(Number),0,1033);
    vi.setProductVersion(...version.split('.').map(Number),0,1033);
    vi.setStringValues({lang:1033,codepage:1200},{FileDescription:name,ProductName:name,CompanyName:'Backwoods Brew',OriginalFilename:path.basename(filename)});
    vi.outputToResourceEntries(res.entries);
  }
  res.outputResource(exe);
  const output=Buffer.from(exe.generate());
  const checked=R.NtExecutableResource.from(R.NtExecutable.from(output));
  for(const entry of retained){
    const found=checked.entries.find(e=>e.type===entry.type&&e.id===entry.id&&e.lang===entry.lang);
    if(!found||!Buffer.from(found.bin).equals(entry.bin)) throw Error('An unrelated executable resource changed.');
  }
  const result=R.Resource.IconGroupEntry.fromEntries(checked.entries);
  if(!result.length||result.some(g=>g.icons.length!==icons.length)) throw Error('Executable icon verification failed.');
  const temporary=filename+'.icons-tmp';fs.writeFileSync(temporary,output);fs.renameSync(temporary,filename);
  console.log('Embedded and verified '+name+' executable icons ('+icons.length+' sizes).');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
