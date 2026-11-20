// Existing Employee owner-host protocol. No administrator key or new login.
const PROTOCOL='backwoods-employee-relay-v1';
const encoder=new TextEncoder(),decoder=new TextDecoder();
const b64=bytes=>btoa(String.fromCharCode(...new Uint8Array(bytes)));
const bytes=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
const hex=value=>Array.from(new Uint8Array(value),n=>n.toString(16).padStart(2,'0')).join('');
export function pendingStore(indexedDB=globalThis.indexedDB){
 let opening;
 function open(){return opening??=new Promise((resolve,reject)=>{
  const request=indexedDB.open('backwoods-shared-clock-v1',1);
  request.onupgradeneeded=()=>request.result.createObjectStore('pending');
  request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
 });}
 async function use(mode,operation){
  const db=await open();return new Promise((resolve,reject)=>{
   const tx=db.transaction('pending',mode),request=operation(tx.objectStore('pending'));let value;
   request.onsuccess=()=>{value=request.result;};tx.oncomplete=()=>resolve(value);
   tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('Could not retain the clock request.'));
  });
 }
 return {get:key=>use('readonly',s=>s.get(key)),put:(key,value)=>use('readwrite',s=>s.put(value,key)),remove:key=>use('readwrite',s=>s.delete(key))};
}
async function transform(value,format,decompress=false){
 const stream=new Blob([value]).stream().pipeThrough(decompress?new DecompressionStream(format):new CompressionStream(format));
 const reader=stream.getReader(),chunks=[];let size=0;
 for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>32*1024*1024){await reader.cancel();throw Error('The Employee response exceeds its supported size.');}chunks.push(value);}
 return new Uint8Array(await new Blob(chunks).arrayBuffer());
}
async function key(privateKey,peer,aad,direction){
 const publicKey=await crypto.subtle.importKey('raw',bytes(peer),{name:'ECDH',namedCurve:'P-256'},false,[]);
 const secret=await crypto.subtle.deriveBits({name:'ECDH',public:publicKey},privateKey,256);
 const material=await crypto.subtle.importKey('raw',secret,'HKDF',false,['deriveKey']);
 return crypto.subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt:await crypto.subtle.digest('SHA-256',aad),info:encoder.encode(PROTOCOL+'/'+direction)},material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
export function createEmployeeRelay(context,{store=pendingStore(),fetcher=fetch,wait=ms=>new Promise(resolve=>setTimeout(resolve,ms)),attempts=40,routePath='/api/shared-clock',scope='account'}={}){
 async function request(data,{status=false,persist=!status}={}){
  const current=context(),uid=current?.uid,project=current?.projectId;
  if(!uid||current.auth.currentUser?.uid!==uid)throw Error('Sign in with your own Backwoods username to record time.');
  if(project!=='backwoodsbrew-e3584-d52a3'&&!project?.startsWith('demo-'))throw Error('The Employee workspace project does not match this Vendor app.');
  const root=`projects/${project}/databases/(default)/documents/`,base='https://firestore.googleapis.com/v1/'+root;
  function check(){if(context()?.uid!==uid||context()?.auth.currentUser?.uid!==uid)throw Error('The signed-in account changed. Your pending clock action remains saved for its original employee.');}
  async function api(path,body,missing=false){
   check();const token=await current.auth.currentUser.getIdToken();check();
   const response=await fetcher((path.startsWith(':')?base.slice(0,-1):base)+path,{method:body?'POST':'GET',redirect:'error',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
   check();if(missing&&[403,404].includes(response.status))return null;
   if(!response.ok)throw Error(response.status===403?'Employee access was denied. Ask the owner to confirm your existing Vendor account and Employee link.':`The Employee service could not confirm the clock request (${response.status}). It remains saved for retry.`);
   return response.json();
  }
  const unpack=document=>Object.fromEntries(Object.entries(document?.fields||{}).map(([k,v])=>[k,v.stringValue??v.booleanValue??(v.integerValue!==undefined?Number(v.integerValue):v.timestampValue)]));
  const fields=value=>Object.fromEntries(Object.entries(value).map(([k,v])=>[k,typeof v==='boolean'?{booleanValue:v}:typeof v==='number'?{integerValue:String(v)}:{stringValue:v}]));
  const config=unpack(await api('employeeService/config'));
  if(config.project!==project||config.protocol!==PROTOCOL||config.apiVersion!==1||config.stateReady!==true||config.pinClockVersion!==1)throw Error('Update Employee on the owner PC and start Owner service to enable the Vendor clock.');
  const storageKey=uid+':'+scope+':'+(data.source||'employee')+':action';let pending=persist?await store.get(storageKey):null;
  if(pending&&pending.peer!==config.publicKey)throw Error('The owner workspace key changed. Ask the owner to review this saved clock request before retrying.');
  if(pending&&pending.data.request_key!==data.request_key)throw Error('A different clock action is still pending. Retry the saved action first.');
  if(!pending){
   const pair=await crypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
   const id=crypto.randomUUID().replaceAll('-',''),aad=encoder.encode(JSON.stringify([PROTOCOL,project,uid,id]));
   const message=encoder.encode(JSON.stringify({method:'POST',path:routePath,data,scope}));
   const nonce=crypto.getRandomValues(new Uint8Array(12));
   const encrypted=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv:nonce,additionalData:aad},await key(pair.privateKey,config.publicKey,aad,'request'),await transform(message,'deflate')));
   const payload=new Uint8Array(12+encrypted.length);payload.set(nonce);payload.set(encrypted,12);
   const token=await current.auth.currentUser.getIdToken();check();
   const claims=JSON.parse(atob(token.split('.')[1].replaceAll('-','+').replaceAll('_','/')));
   pending={id,data:Object.fromEntries(Object.entries(data).filter(([k])=>k!=='pest_token')),privateKey:pair.privateKey,peer:config.publicKey,publicKey:b64(await crypto.subtle.exportKey('raw',pair.publicKey)),payload,authTime:claims.auth_time};
   // IndexedDB retains a non-extractable CryptoKey; tokens/passwords are never saved here.
   if(persist)await store.put(storageKey,pending);
  }
  const path='employeeRequests/'+pending.id,payload=pending.payload,aad=encoder.encode(JSON.stringify([PROTOCOL,project,uid,pending.id]));
  let envelope=unpack(await api(path,null,true));
  if(!envelope.state){
   const value={uid,requestId:pending.id,protocol:PROTOCOL,scope,peer:pending.publicKey,hash:hex(await crypto.subtle.digest('SHA-256',payload)),count:1,state:'uploading',authTime:pending.authTime};
   try{await api(':commit',{writes:[{update:{name:root+path,fields:fields(value)},currentDocument:{exists:false},updateTransforms:[{fieldPath:'createdAt',setToServerValue:'REQUEST_TIME'}]}]});envelope={state:'uploading'};}
   catch(error){const saved=unpack(await api(path,null,true));if(!saved.state)throw error;envelope=saved;}
  }
  if(envelope.state==='uploading'){
   await api(':commit',{writes:[{update:{name:root+path+'/requestParts/0000',fields:fields({data:b64(payload)})}}]});
   await api(':commit',{writes:[{update:{name:root+path,fields:fields({state:'pending'})},updateMask:{fieldPaths:['state']},currentDocument:{exists:true},updateTransforms:[{fieldPath:'readyAt',setToServerValue:'REQUEST_TIME'}]}]});
  }
  for(let attempt=0;;attempt++){
   envelope=unpack(await api(path));if(envelope.state==='done')break;
   if(envelope.state==='failed')throw Error('The Employee service rejected this saved request. Ask the owner to review it.');
   if(attempt>=attempts)throw Error('Waiting for the Employee owner PC. Retry this saved clock action after Owner service reconnects; it will not create a duplicate.');
   await wait(1000);
  }
  if(!Number.isInteger(envelope.responseCount)||envelope.responseCount<1||envelope.responseCount>200)throw Error('Invalid Employee clock response.');
  const chunks=[];let length=0;
  for(let i=0;i<envelope.responseCount;i++){const part=bytes(unpack(await api(path+'/responseParts/'+String(i).padStart(4,'0'))).data);length+=part.length;if(length>32*1024*1024)throw Error('Employee clock response is too large.');chunks.push(part);}
  const response=new Uint8Array(length);let offset=0;for(const chunk of chunks){response.set(chunk,offset);offset+=chunk.length;}
  if(hex(await crypto.subtle.digest('SHA-256',response))!==envelope.responseHash)throw Error('Employee clock response failed its integrity check.');
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:response.subarray(0,12),additionalData:aad},await key(pending.privateKey,pending.peer,aad,'response'),response.subarray(12));
  const reply=JSON.parse(decoder.decode(await transform(plain,'deflate',true)));
  const result=JSON.parse(decoder.decode(bytes(reply.body)));check();
  if(reply.status<200||reply.status>=300){
   // A confirmed rejection did not create time; keep its receipt for audit but
   // allow the employee to refresh and submit a genuinely corrected action.
   if(persist)await store.remove(storageKey);
   throw Object.assign(Error(result.error||'Employee clock request was rejected.'),{confirmedRejection:true});
  }
  if(persist)await store.remove(storageKey);return result;
 }
 return {request,async pending(source){const uid=context()?.uid;return uid?(await store.get(uid+':'+scope+':'+source+':action'))?.data:null;}};
}
