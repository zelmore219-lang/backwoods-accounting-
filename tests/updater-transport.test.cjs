const test=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events'),{Readable}=require('node:stream');
const createTransport=require('../connectors/updater/electron-transport.cjs'),core=require('../connectors/updater/core.cjs');
const source='https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/test/a.exe';
function fixture(target){let requests=[],aborts=0;const net={request(options){requests.push(options);const req=new EventEmitter();req.abort=()=>{aborts++;};req.end=()=>queueMicrotask(()=>{
 if(options.url===source){req.emit('redirect',302,'GET',target,{location:[target]});}
 else{const response=Readable.from([Buffer.from('MZverified file')]);response.statusCode=200;response.headers={'content-type':['application/octet-stream']};req.emit('response',response);}
 });return req;}};return {net,requests,aborts:()=>aborts};}
test('Electron manual redirect is explicitly aborted and safely reissued after validation',async()=>{const f=fixture('https://release-assets.githubusercontent.com/test/a.exe?signature=fixture');const response=await core.response(createTransport(f.net),source);assert.equal(await response.text(),'MZverified file');assert.equal(f.requests.length,2);assert.equal(f.requests[0].redirect,'manual');assert.equal(f.aborts(),1);assert.equal(f.requests[0].credentials,'omit');});
test('untrusted redirect is never requested by Electron',async()=>{const f=fixture('https://attacker.test/file.exe');await assert.rejects(core.response(createTransport(f.net),source),/Untrusted/);assert.equal(f.requests.length,1);assert.equal(f.aborts(),1);});
test('pre-aborted requests never reach the network',async()=>{const f=fixture(source);const controller=new AbortController();controller.abort(Error('cancelled'));await assert.rejects(createTransport(f.net)(source,{signal:controller.signal}),/cancelled/);assert.equal(f.requests.length,0);});
