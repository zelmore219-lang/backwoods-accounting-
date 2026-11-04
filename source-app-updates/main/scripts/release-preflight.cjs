const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const required=['package.json','electron/main.cjs','electron/preload.cjs','www/index.html','www/wholesale.js','www/wholesale.css','www/assets/main-CnsZnSKS.js','assets/icon.ico'];
for(const file of required){assert(fs.existsSync(path.join(root,file)),`Missing ${file}`);assert(fs.statSync(path.join(root,file)).size>0,`Empty ${file}`)}
const pkg=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
assert(pkg.build?.win?.target?.includes('nsis'),'NSIS installer target missing');
const html=fs.readFileSync(path.join(root,'www/index.html'),'utf8');
for(const name of ['wholesale.js','wholesale.css'])assert.equal(html.split('./'+name).length-1,1,`${name} loaded more than once`);
const wholesale=fs.readFileSync(path.join(root,'www/wholesale.js'),'utf8');
for(const name of ['function reconcile()','function validateBackup(','function handle(','function next(','function integrityReport()'])assert(wholesale.includes(name),`Missing workflow ${name}`);
assert(wholesale.includes('const snapshot=JSON.stringify(d)'), 'Transaction rollback not present');
console.log('PASS: Windows packaging preflight and offline workflow presence checks');
console.log('NOT TESTED: Windows installer launch, live Firebase, main ledger integration, end-to-end UI');
