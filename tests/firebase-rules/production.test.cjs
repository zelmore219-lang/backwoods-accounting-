const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {initializeTestEnvironment,assertSucceeds,assertFails}=require('@firebase/rules-unit-testing');
const {doc,setDoc,getDoc,updateDoc,deleteDoc,runTransaction}=require('firebase/firestore');
test('Production receipts survive old clients, simultaneous deliveries and repeated delivery attempts',async t=>{
 const env=await initializeTestEnvironment({projectId:'demo-production-stock',firestore:{host:'127.0.0.1',port:8080,rules:fs.readFileSync(path.resolve(__dirname,'../../firebase/firestore.rules'),'utf8')}});
 const {planStockWrite}=await import('../../source-app-updates/vendor/dist/production-stock.mjs');
 try{
  await env.withSecurityRulesDisabled(async ctx=>{
   const db=ctx.firestore();for(const [uid,role] of [['manager','manager'],['driver','driver']])await setDoc(doc(db,'vendorUsers',uid),{authUid:uid,role,active:true});
   await setDoc(doc(db,'usersByUid','owner'),{authUid:'owner',role:'owner',active:true});
   await setDoc(doc(db,'vendorProducts','finished'),{sku:'PEA-8',unit:'each',productionManaged:true,productionSourceId:'source',stockRevision:1,onHand:16,reserved:0,cost:1.875});
  });
  const db=env.authenticatedContext('manager',{email:'manager@example.test'}).firestore(),ref=doc(db,'vendorProducts','finished');
  await t.test('old clients cannot replace or delete protected stock',async()=>{
   await assertFails(updateDoc(ref,{onHand:10}));await assertFails(updateDoc(ref,{productionManaged:false}));await assertFails(deleteDoc(ref));await assertFails(updateDoc(ref,{sku:'different'}));
   await assertSucceeds(updateDoc(ref,{price:4}));
   await assertFails(updateDoc(doc(env.authenticatedContext('driver').firestore(),'vendorProducts','finished'),{onHand:10,stockRevision:2}));
  });
  const operation={fields:{onHand:12},fallback:{onHand:16,reserved:0,cost:1.875},removed:[]};
  // The warehouse receives another finished lot after the delivery was prepared.
  await env.withSecurityRulesDisabled(ctx=>updateDoc(doc(ctx.firestore(),'vendorProducts','finished'),{onHand:24,cost:2.25,stockRevision:2}));
  const receipt=doc(db,'vendorProducts','finished','stockOperations','retained-operation');
  const save=()=>runTransaction(db,async tx=>{
   const p=await tx.get(ref),r=await tx.get(receipt);if(r.exists())return;
   const changed=planStockWrite(p.data(),operation);tx.update(ref,changed);tx.set(receipt,{uid:'manager',token:'retained-operation',revision:changed.stockRevision,createdAt:new Date().toISOString()});
  });
  await assertSucceeds(save());await assertSucceeds(save());
  const product=(await getDoc(ref)).data();assert.equal(product.onHand,20);assert.equal(product.stockRevision,3);assert.equal(product.cost,46.5/20);
  await t.test('Production Accounting source remains owner-only',async()=>{
   const p='businessAccounting/owner/sources/production';
   await env.withSecurityRulesDisabled(ctx=>setDoc(doc(ctx.firestore(),p),{schemaVersion:1,generation:'fixture'}));
   await assertSucceeds(getDoc(doc(env.authenticatedContext('owner').firestore(),p)));
   await assertFails(getDoc(doc(db,p)));await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(),p)));
  });
 }finally{await env.cleanup()}
});
