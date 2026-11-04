const test=require('node:test');
const assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const {publish,clean}=require('../connectors/firebase-feed.js');

function fixture(options={}){
 const documents=new Map(),calls=[];
 const context=()=>({uid:'company-owner',projectId:'test-company',auth:{currentUser:{uid:'company-owner',getIdToken:async()=>'test-token'}}});
 const packet={schemaVersion:1,type:'business-accounting-feed',data:{orders:[{id:'sale-1',amount:125,password:'secret'}],memo:'☕ retail'}};
 const snapshot=()=>packet;
 const fetcher=async(url,request)=>{
  assert.equal(request.headers.Authorization,'Bearer test-token');calls.push({url,request});
  if(options.fail&&request.method==='POST')return {ok:false,status:403};
  if(request.method==='GET'){const document=documents.get(url);return {ok:!!document,status:document?200:404,json:async()=>document};}
  const body=JSON.parse(request.body);
  for(const write of body.writes){
   const key='https://firestore.googleapis.com/v1/'+write.update.name;
   const old=documents.get(key);
   if(write.currentDocument?.exists===false&&old)return {ok:false,status:409};
   if(write.currentDocument?.updateTime&&old?.updateTime!==write.currentDocument.updateTime)return {ok:false,status:409};
   documents.set(key,{...write.update,updateTime:String(calls.length)});
  }
  return {ok:true,status:200,json:async()=>({})};
 };
 return {context,snapshot,fetcher,cryptoApi:webcrypto,source:'main',documents,calls,packet};
}
test('automatically publishes a complete redacted Unicode snapshot, then skips an unchanged snapshot',async()=>{
 const f=fixture();await publish(f);
 const root='https://firestore.googleapis.com/v1/projects/test-company/databases/(default)/documents/businessAccounting/company-owner/sources/main';
 const meta=f.documents.get(root).fields;const chunks=[...f.documents.entries()].filter(([p])=>p.includes('/chunks/'));
 assert.equal(meta.chunkCount.integerValue,'1');
 const decoded=JSON.parse(Buffer.from(chunks[0][1].fields.data.stringValue,'base64'));
 assert.equal(decoded.data.memo,'☕ retail');assert(!('password' in decoded.data.orders[0]));
 const posts=f.calls.filter(c=>c.request.method==='POST').length;
 await publish(f);assert.equal(f.calls.filter(c=>c.request.method==='POST').length,posts);
});
test('permission failure never publishes a partial manifest',async()=>{
 const f=fixture({fail:true});await assert.rejects(publish(f),/one-time Firebase rules/);assert.equal(f.documents.size,0);
});
test('multi-chunk transport publishes the pointer after immutable chunks',async()=>{
 const f=fixture();f.packet.data.memo='x'.repeat(520000);await publish(f);
 const posts=f.calls.filter(c=>c.request.method==='POST').map(c=>JSON.parse(c.request.body));
 assert.equal(posts[0].writes.length,3);assert(posts[0].writes.every(w=>w.currentDocument.exists===false));
 assert(posts.at(-1).writes[0].update.fields.sha256);assert(!posts[0].writes[0].update.fields.sha256);
});
test('signed-out and non-owner hooks do not transfer data',async()=>{
 const f=fixture();assert.equal(await publish({...f,context:()=>null}),null);
 assert.equal(await publish({...f,snapshot:()=>null}),null);assert.equal(f.calls.length,0);
});
