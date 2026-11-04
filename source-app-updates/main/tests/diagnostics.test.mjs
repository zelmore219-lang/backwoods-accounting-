import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
// Test the pure diagnostic functions without importing the browser-only compiled bundle.
const source=readFileSync(new URL('../www/wholesale-diagnostics.mjs',import.meta.url),'utf8');
const pure=source.replace("import { a as existingAuth } from './assets/index-DXWT0E9w.js';",'const existingAuth=null;').replace(/window.BackwoodsWholesaleDiagnostics = \{run: async\(\)=>\{[\s\S]*?\}\};\s*$/,'');
const {checkProfile,diagnose}=await import('data:text/javascript;base64,'+Buffer.from(pure).toString('base64'));
const user={uid:'abc',getIdToken:async()=> 'token'};
const ok=async()=>({ok:true,json:async()=>({fields:{active:{booleanValue:true},authUid:{stringValue:'abc'},role:{stringValue:'sales'}}})});
const denied=async()=>({ok:false,status:403,json:async()=>({error:{message:'Permission denied'}})});
assert.equal((await checkProfile({user,fetcher:ok,collection:'vendorUsers'})).ok,true);
assert.match((await checkProfile({user,fetcher:denied,collection:'vendorUsers'})).reason,/permission denied/i);
assert.rejects(checkProfile({user,fetcher:ok,collection:'other'}));
assert.equal((await diagnose({auth:{currentUser:null},fetcher:ok})).signedIn,false);
assert.equal((await diagnose({auth:{currentUser:user},fetcher:ok})).checks.length,2);
console.log('5 diagnostic assertions passed');
