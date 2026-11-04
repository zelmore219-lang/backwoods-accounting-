// Authenticated, one-way cloud copies. Financial source data is never rewritten.
(function(global){
  'use strict';
  const sensitive=new Set(['password','passwordhash','passwordsalt','accesstoken','refreshtoken','clientsecret','privatekey','ssn','socialsecuritynumber','routingnumber','bankaccountnumber','apikey']);
  function clean(v){
    if(Array.isArray(v))return v.map(clean);
    if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).filter(([k])=>!sensitive.has(k.toLowerCase().replace(/[^a-z]/g,''))).map(([k,x])=>[k,clean(x)]));
    return v;
  }
  const hex=bytes=>Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
  const field=v=>typeof v==='number'?{integerValue:String(v)}:{stringValue:v};
  function fields(v){return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,field(x)]));}
  async function publish({source,context,snapshot,fetcher=fetch,cryptoApi=crypto,clock=()=>new Date().toISOString()}){
    const current=context();
    if(!['main','vendor'].includes(source)||!current||!current.uid||!current.projectId||!current.auth?.currentUser||current.auth.currentUser.uid!==current.uid)return null;
    const packet=snapshot();if(!packet)return null;
    const data=new TextEncoder().encode(JSON.stringify(clean(packet)));
    if(data.length>40*1024*1024)throw Error('Accounting snapshot exceeds 40 MB. No partial snapshot was published.');
    const sha256=hex(await cryptoApi.subtle.digest('SHA-256',data));
    const uid=current.uid,project=current.projectId;
    if(!/^[a-z0-9-]+$/.test(project)||!/^[-A-Za-z0-9_]{1,128}$/.test(uid))throw Error('Unsupported Firebase identity.');
    const token=await current.auth.currentUser.getIdToken();
    const root=`projects/${project}/databases/(default)/documents/businessAccounting/${uid}/sources/${source}`;
    const api=`https://firestore.googleapis.com/v1/projects/${project}/databases/(default)/documents`;
    const check=()=>{const c=context();if(!c||c.uid!==uid||c.auth.currentUser?.uid!==uid||!snapshot())throw Error('Accounting sign-in changed. Transfer will retry after sign-in.');};
    async function request(url,body){
      check();const response=await fetcher(url,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
      if(response.status===404&&!body)return null;
      if(!response.ok)throw Error(response.status===403?'Accounting cloud access needs the one-time Firebase rules setup.':`Accounting cloud transfer failed (${response.status}). Records remain in this app.`);
      return response.json();
    }
    const prior=await request('https://firestore.googleapis.com/v1/'+root);
    if(prior?.fields?.sha256?.stringValue===sha256)return {sha256,unchanged:true};
    const generation=cryptoApi.randomUUID(),capturedAt=clock();let index=0;
    // Immutable chunks first; the pointer is published only after every chunk.
    for(let start=0;start<data.length;){
      const writes=[];
      for(let n=0;n<8&&start<data.length;n++,start+=240000){
        let binary='';for(const byte of data.subarray(start,start+240000))binary+=String.fromCharCode(byte);
        writes.push({update:{name:`${root}/generations/${generation}/chunks/${String(index++).padStart(4,'0')}`,fields:fields({data:btoa(binary)})},currentDocument:{exists:false}});
      }
      await request(api+':commit',{writes});
    }
    const write={update:{name:root,fields:fields({schemaVersion:1,generation,sha256,chunkCount:index,bytes:data.length,exportedAt:capturedAt})},currentDocument:prior?{updateTime:prior.updateTime}:{exists:false}};
    await request(api+':commit',{writes:[write]});
    return {sha256,at:capturedAt};
  }
  function start(){
    const source=document.currentScript?.dataset.source;if(!source)return;
    let busy=false,last='',identity='',statusBox;
    const context=()=>global.__bwAccountingCloudContext?.();
    const snapshot=()=>global.__bwAccountingSnapshot?.();
    function status(text){if(!statusBox){statusBox=document.createElement('div');statusBox.id='bw-accounting-cloud-status';statusBox.setAttribute('role','status');statusBox.style.cssText='position:fixed;bottom:8px;left:8px;z-index:2147483645;max-width:340px;background:#153e35;color:#fff;padding:8px 12px;border-radius:8px;font:12px system-ui';document.body.append(statusBox);}statusBox.textContent=text;}
    async function tick(){
      if(busy)return;busy=true;
      try{
        const c=context();const packet=snapshot();
        if(!c?.auth?.currentUser||!packet){status('Accounting: waiting for owner sign-in and source sync.');return;}
        if(c.uid!==identity){last='';identity=c.uid;}
        if(navigator.onLine===false){status('Accounting: offline. Saved records will transfer when connected.');return;}
        const digest=hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(clean(packet)))));
        if(last===digest)return;
        status('Sending accounting records securely…');
        const result=await publish({source,context,snapshot});
        if(result){last=result.sha256;status('Accounting records sent to Firebase. Ledger import is tracked in Business Accounting.');}
      }catch(error){status(error.message);}finally{busy=false;}
    }
    global.addEventListener('online',tick);setInterval(tick,15000);setTimeout(tick,1500);
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={publish,clean};
  else start();
})(typeof window==='undefined'?globalThis:window);
