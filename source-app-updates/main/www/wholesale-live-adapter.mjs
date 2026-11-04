/** Read-only Firebase integration against the actual signed-in Backwoods Brew Auth session.
 * Financial and operational writes are intentionally blocked pending emulator tests.
 */
import { a as auth } from './assets/index-DXWT0E9w.js';
const project = 'backwoodsbrew-e3584-d52a3';
const base = `https://firestore.googleapis.com/v1/projects/${project}/databases/(default)/documents`;
const names = { customers:'vendorCustomers', products:'vendorProducts', orders:'vendorOrders' };
function decode(v) {
 if (!v || typeof v !== 'object') return null;
 if ('stringValue' in v) return v.stringValue;
 if ('integerValue' in v) return Number(v.integerValue);
 if ('doubleValue' in v) return Number(v.doubleValue);
 if ('booleanValue' in v) return v.booleanValue;
 if ('nullValue' in v) return null;
 if ('timestampValue' in v) return v.timestampValue;
 if ('arrayValue' in v) return (v.arrayValue.values||[]).map(decode);
 if ('mapValue' in v) return Object.fromEntries(Object.entries(v.mapValue.fields||{}).map(([k,x])=>[k,decode(x)]));
 return null;
}
function document(d) { return {id:decodeURIComponent((d.name||'').split('/').at(-1)),...Object.fromEntries(Object.entries(d.fields||{}).map(([k,v])=>[k,decode(v)]))}; }
async function user() {
 const u=auth?.currentUser;
 if (!u?.uid || typeof u.getIdToken!=='function') throw Error('Sign in through Backwoods Brew first.');
 return u;
}
async function request(path,query='') {
 const u=await user();
 const response=await fetch(`${base}/${path}${query}`,{headers:{Authorization:`Bearer ${await u.getIdToken()}`},cache:'no-store'});
 if (!response.ok) {
  let reason='';try {reason=(await response.json())?.error?.message||''}catch{}
  throw Error(`Firestore ${response.status}: ${reason||response.statusText}`);
 }
 return response.json();
}
async function checkAccess() {
 const u=await user();
 const profile=await request(`vendorUsers/${encodeURIComponent(u.uid)}`);
 const p=document(profile);
 if(p.active!==true || p.authUid!==u.uid) throw Error('Wholesale profile inactive or linked to another account.');
 return p;
}
async function list(which) {
 const results=[];let pageToken='';let pages=0;
 do {
  const query=`?pageSize=100${pageToken?'&pageToken='+encodeURIComponent(pageToken):''}`;
  const data=await request(names[which],query);
  results.push(...(data.documents||[]).map(document));
  pageToken=data.nextPageToken||'';
  if(++pages>100)throw Error('Catalog pagination limit exceeded');
 }while(pageToken);
 return results;
}
const blocked=async()=>{throw Error('Cloud writes are disabled until security rules and transaction behavior pass integration testing.');};
let unsubscribe=()=>{};
window.BackwoodsWholesaleCloudAdapter={
 currentUser:user,
 loadWholesaleCatalog:async()=>{await checkAccess();const [customers,products]=await Promise.all([list('customers'),list('products')]);return {customers,products};},
 watchOrders:(onChange,onError)=>{
  let stopped=false;
  async function tick(){if(stopped)return;try{await checkAccess();const orders=await list('orders');if(!stopped)onChange(orders);}catch(e){if(!stopped)onError(e);}}
  tick();const timer=setInterval(tick,15000);
  unsubscribe=()=>{stopped=true;clearInterval(timer);};return unsubscribe;
 },
 submitOrder:blocked,confirmPacking:blocked,confirmDelivery:blocked
};
