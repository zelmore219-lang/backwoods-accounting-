const crypto=require('node:crypto');
const fs=require('node:fs/promises');
const path=require('node:path');
const REPO='/zelmore219-lang/backwoods-accounting-/releases/download/';
const FEED='https://github.com'+REPO+'app-updates/backwoods-updates.json';
function version(value){
 if(!/^\d+\.\d+\.\d+$/.test(String(value)))throw Error('Invalid update version.');
 const parts=value.split('.').map(Number);if(parts.some(n=>!Number.isSafeInteger(n)))throw Error('Invalid update version.');return parts;
}
function newer(a,b){const x=version(a),y=version(b);for(let i=0;i<3;i++)if(x[i]!==y[i])return x[i]>y[i];return false;}
function trustedUrl(value){const u=new URL(value);if(u.protocol!=='https:'||u.hostname!=='github.com'||u.port||u.username||u.password||u.search||u.hash||!u.pathname.startsWith(REPO)||u.pathname.includes('..'))throw Error('Use an HTTPS release download from the Backwoods accounting repository.');return u.href;}
function select(manifest,app,current){
 if(manifest.schemaVersion!==1)throw Error('Unsupported update feed.');
 const info=manifest.apps?.[app]?.windows;
 if(!info||!['accounting','vendor','main'].includes(app))throw Error('This feed has no Windows update for this app.');
 version(info.version);trustedUrl(info.url);
 if(!new URL(info.url).pathname.endsWith('.exe')||!/^[a-f0-9]{64}$/.test(info.sha256)||!Number.isSafeInteger(info.size)||info.size<2||info.size>1024**3)throw Error('Invalid Windows update details.');
 return {...info,notes:String(manifest.apps[app].notes||'').slice(0,12000),available:newer(info.version,current)};
}
async function response(fetch,url){
 let target=url;
 for(let i=0;i<6;i++){
  const u=new URL(target);
  if(u.protocol!=='https:'||u.username||u.password||u.port||!['github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'].includes(u.hostname))throw Error('Untrusted update redirect.');
  const r=await fetch(target,{redirect:'manual',signal:AbortSignal.timeout(120000)});
  if([301,302,303,307,308].includes(r.status)){const next=r.headers.get('location');await r.body?.cancel();if(!next)throw Error('Invalid update redirect.');target=new URL(next,target).href;continue;}
  if(!r.ok)throw Error(r.status===404?'An update feed has not been published at this address yet.':`Update server returned HTTP ${r.status}.`);
  return r;
 }
 throw Error('Too many update redirects.');
}
async function readFeed(fetch,url){trustedUrl(url);const chunks=[];let size=0;const r=await response(fetch,url);for await(const chunk of r.body){size+=chunk.length;if(size>1024*1024)throw Error('Update feed is too large.');chunks.push(Buffer.from(chunk));}return JSON.parse(Buffer.concat(chunks).toString('utf8'));}
async function verify(filename,info){
 const h=crypto.createHash('sha256');const handle=await fs.open(filename,'r');
 try{const stat=await handle.stat();if(stat.size!==info.size)throw Error('The update download is incomplete.');const magic=Buffer.alloc(2);await handle.read(magic,0,2,0);if(magic.toString()!=='MZ')throw Error('The download is not a Windows installer.');for await(const b of handle.createReadStream({start:0,autoClose:false}))h.update(b);if(h.digest('hex')!==info.sha256)throw Error('Update checksum mismatch. The installer will not run.');}finally{await handle.close();}
}
async function download(fetch,info,directory,progress=()=>{}){
 trustedUrl(info.url);await fs.mkdir(directory,{recursive:true});const filename=path.join(directory,`update-${info.version}.exe`),part=filename+'.part';
 const out=await fs.open(part,'w',0o600);
 try{const r=await response(fetch,info.url);let total=0;for await(const b of r.body){total+=b.length;if(total>info.size)throw Error('Update download exceeds its declared size.');await out.writeFile(b);progress(total/info.size*100);}await out.close();await verify(part,info);await fs.rename(part,filename);return filename;}catch(e){await out.close().catch(()=>{});await fs.rm(part,{force:true});throw e;}
}
module.exports={FEED,newer,trustedUrl,select,response,readFeed,verify,download};
