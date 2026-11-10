const fs=require('node:fs'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'www/index.html'),'utf8');
for(const name of ['wholesale.js','wholesale-cloud.js','central-accounting-ui.mjs'])assert(!html.includes('src="./'+name+'"'),name+' embedded screen still loads');
for(const name of ['firebase-accounting.js','wholesale-live-adapter.mjs','receipt.mjs'])assert(fs.existsSync(path.join(root,'www',name)));
assert(html.includes('firebase-accounting.js'));assert(html.includes('wholesale-live-adapter.mjs'));
console.log('PASS: embedded business screens removed; shared adapters and receipt module retained');
