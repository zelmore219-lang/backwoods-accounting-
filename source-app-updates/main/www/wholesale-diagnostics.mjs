/* Read-only Phase 8 connectivity check using the exact Auth instance exported by the recovered app bundle.
   No writes, no rule changes, no credentials saved. */
import { a as existingAuth } from './assets/index-DXWT0E9w.js';
const projectId = 'backwoodsbrew-e3584-d52a3';
const base = `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents`;
function normalizeError(code, body) {
  if (code === 401) return 'Authentication expired or token rejected';
  if (code === 403) return 'Firestore permission denied: check profile and rules';
  if (code === 404) return 'Profile document missing';
  return body?.error?.message || `HTTP ${code}`;
}
export async function checkProfile({user, fetcher = fetch, collection}) {
  if (!user?.uid || typeof user.getIdToken !== 'function') throw Error('Sign in to Backwoods Brew first');
  if (!['usersByUid','vendorUsers'].includes(collection)) throw Error('Invalid profile collection');
  const token = await user.getIdToken();
  const response = await fetcher(`${base}/${collection}/${encodeURIComponent(user.uid)}?mask.fieldPaths=active&mask.fieldPaths=role&mask.fieldPaths=authUid`, {
    headers: {Authorization: `Bearer ${token}`}, cache:'no-store'
  });
  if (!response.ok) {
    let body = null; try { body = await response.json(); } catch {}
    return {collection, ok:false, reason:normalizeError(response.status,body), httpStatus:response.status};
  }
  const body = await response.json();
  const fields = body.fields || {};
  const active = fields.active?.booleanValue === true;
  const uidMatches = fields.authUid?.stringValue === user.uid;
  return {collection, ok:active && uidMatches, active, uidMatches,
    role:fields.role?.stringValue || 'missing', reason:active && uidMatches ? 'Profile verified' : 'Inactive or mismatched profile'};
}
export async function diagnose({auth=existingAuth, fetcher=fetch}={}) {
  const user=auth?.currentUser;
  if (!user) return {signedIn:false, checks:[], message:'No signed-in Firebase user detected in the existing application'};
  const checks=[];
  for(const collection of ['usersByUid','vendorUsers']) {
    try { checks.push(await checkProfile({user,fetcher,collection})); }
    catch(e) { checks.push({collection,ok:false,reason:e?.message || String(e)}); }
  }
  return {signedIn:true,checks, message:'Read-only checks completed. No business records changed.'};
}
function render(result) {
  const el=document.getElementById('bw-cloud-diagnostics-result'); if(!el)return;
  const line = result.checks.map(c=>`${c.collection}: ${c.ok?'READY':'NOT READY'} (${c.reason})`).join('\n');
  el.textContent=`${result.message}\n${line}`;
}
window.BackwoodsWholesaleDiagnostics = {run: async()=>{
  const el=document.getElementById('bw-cloud-diagnostics-result'); if(el)el.textContent='Checking Firebase login and profile access...';
  try {render(await diagnose());} catch(e) {render({checks:[],message:`Diagnostic error: ${e.message}`});}
}};
