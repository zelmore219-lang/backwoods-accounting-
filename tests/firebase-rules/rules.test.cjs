const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {initializeTestEnvironment,assertSucceeds,assertFails}=require('@firebase/rules-unit-testing');
const {doc,setDoc,getDoc,deleteDoc,serverTimestamp,Timestamp}=require('firebase/firestore');

test('merged Firestore permissions and shared Spark writer protocol',async t=>{
 const env=await initializeTestEnvironment({projectId:'demo-backwoods-accounting',firestore:{host:'127.0.0.1',port:8080,rules:fs.readFileSync(path.resolve(__dirname,'../../firebase/firestore.rules'),'utf8')}});
 try{
  await env.clearFirestore();
  await env.withSecurityRulesDisabled(async context=>{
   const db=context.firestore();
   for(const uid of ['owner','other-owner'])await setDoc(doc(db,'usersByUid',uid),{authUid:uid,username:uid,role:'owner',active:true});
   await setDoc(doc(db,'usersByUid','employee'),{authUid:'employee',username:'employee',role:'employee',active:true});
   await setDoc(doc(db,'usersByUid','inactive'),{authUid:'inactive',username:'inactive',role:'owner',active:false});
   await setDoc(doc(db,'vendorUsers','driver'),{authUid:'driver',role:'driver',active:true});
   await setDoc(doc(db,'appData','main'),{company:'Existing retail data'});
   await setDoc(doc(db,'vendorOrders','order-1'),{status:'draft'});
  });
  const owner=env.authenticatedContext('owner',{email:'owner@example.test'}).firestore();
  const other=env.authenticatedContext('other-owner',{email:'other@example.test'}).firestore();
  const employee=env.authenticatedContext('employee',{email:'employee@example.test'}).firestore();
  const driver=env.authenticatedContext('driver',{email:'driver@example.test'}).firestore();
  const anonymous=env.unauthenticatedContext().firestore();
  const inactive=env.authenticatedContext('inactive',{email:'inactive@example.test'}).firestore();
  const root='businessAccounting/owner/ledger/state';
  const lease='00000000-0000-0000-0000-000000000001';
  const generation='00000000-0000-0000-0000-000000000002';
  await t.test('legacy retail/vendor permissions remain available',async()=>{
   await assertSucceeds(getDoc(doc(employee,'appData','main')));
   await assertSucceeds(setDoc(doc(driver,'vendorOrders','order-1'),{status:'delivered'}));
   await assertFails(setDoc(doc(driver,'vendorPayments','payment-1'),{amount:100}));
  });
  await t.test('only the active matching company owner reads the ledger',async()=>{
   await assertSucceeds(getDoc(doc(owner,root)));
   for(const db of [anonymous,employee,driver,other])await assertFails(getDoc(doc(db,root)));
  });
  await t.test('staff and inactive users cannot create even their own ledger namespace',async()=>{
   for(const [db,uid] of [[employee,'employee'],[driver,'driver'],[inactive,'inactive']]){
    const ref=doc(db,`businessAccounting/${uid}/ledger/state`);
    await assertFails(getDoc(ref));
    await assertFails(setDoc(ref,{lockedBy:lease,lockedAt:serverTimestamp()}));
   }
  });
  await t.test('server-timestamp lease, immutable chunks and complete publication',async()=>{
   await assertSucceeds(setDoc(doc(owner,root),{lockedBy:lease,lockedAt:serverTimestamp()}));
   const current=(await getDoc(doc(owner,root))).data();
   await assertFails(setDoc(doc(owner,root),{...current,lockedBy:'00000000-0000-0000-0000-000000000009',lockedAt:serverTimestamp()}));
   const chunk=doc(owner,root+'/generations/'+generation+'/chunks/0000');
   await assertSucceeds(setDoc(chunk,{data:'YWJj'}));
   await assertFails(setDoc(chunk,{data:'ZGlmZmVyZW50'}));
   const manifest={ledgerId:'00000000-0000-0000-0000-000000000003',generation,sha256:'0'.repeat(64),sqliteSha256:'1'.repeat(64),chunkCount:1,bytes:3,rawBytes:100,codec:'zlib-sqlite-v1',lockedBy:lease,lockedAt:serverTimestamp(),previousGeneration:'',previousChunkCount:0};
   await assertSucceeds(setDoc(doc(owner,root),manifest));
   await assertFails(deleteDoc(chunk));
   await assertFails(setDoc(doc(owner,root),{...manifest,rawBytes:67108865}));
   await assertSucceeds(setDoc(doc(owner,root),{...manifest,lockedBy:''}));
  });
  await t.test('expired leases recover using server time',async()=>{
   await env.withSecurityRulesDisabled(async context=>{
    const ref=doc(context.firestore(),root);const current=(await getDoc(ref)).data();
    await setDoc(ref,{...current,lockedBy:lease,lockedAt:Timestamp.fromMillis(Date.now()-601000)});
   });
   const current=(await getDoc(doc(owner,root))).data();
   await assertSucceeds(setDoc(doc(owner,root),{...current,lockedBy:'00000000-0000-0000-0000-000000000009',lockedAt:serverTimestamp()}));
  });
  await t.test('current transfer chunks are protected; retired transfer copies can be cleaned',async()=>{
   const base='businessAccounting/owner/sources/main';
   const chunk=doc(owner,base+'/generations/'+generation+'/chunks/0000');
   await assertSucceeds(setDoc(chunk,{data:'YWJj'}));
   const meta={schemaVersion:1,generation,sha256:'0'.repeat(64),chunkCount:1,bytes:3,exportedAt:'2026-11-04T00:00:00Z'};
   await assertSucceeds(setDoc(doc(owner,base),meta));await assertFails(deleteDoc(chunk));
   await assertSucceeds(setDoc(doc(owner,base),{...meta,generation:'00000000-0000-0000-0000-000000000099'}));
   await assertSucceeds(deleteDoc(chunk));
  });
 }finally{await env.cleanup();}
});
