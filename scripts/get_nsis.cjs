const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'..');
const builder=require.resolve('electron-builder/package.json',{paths:[path.join(root,'desktop')]});
const tools=require(require.resolve('app-builder-lib/out/binDownload.js',{paths:[path.dirname(builder)]}));
tools.getBinFromUrl('nsis','3.0.4.1','VKMiizYdmNdJOWpRGz4trl4lD++BvYP2irAXpMilheUP0pc93iKlWAoP843Vlraj8YG19CVn0j+dCo/hURz9+Q==').then(dir=>{fs.mkdirSync(path.join(root,'.build-tools'),{recursive:true});fs.writeFileSync(path.join(root,'.build-tools/nsis-path.txt'),path.join(dir,process.platform==='win32'?'Bin/makensis.exe':'linux/makensis'));}).catch(e=>{console.error(e);process.exitCode=1});
