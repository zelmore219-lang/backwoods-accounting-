// A clock-only Firebase session, independent of regular application sign-in.
// The one-time pairing password and employee PIN are never retained.
export const projectId='backwoodsbrew-e3584-d52a3';
const apiKey='AIzaSyB4Dqp0Du2lGMAqryTRPfvHuBgt69jSmF8';
const storageKey='backwoods-registered-clock-v1';
let session,refreshing;
function saved(){try{return JSON.parse(localStorage.getItem(storageKey)||'null');}catch{return null;}}
async function response(url,body,form=false){
 const reply=await fetch(url,{method:'POST',redirect:'error',headers:{'Content-Type':form?'application/x-www-form-urlencoded':'application/json'},body:form?new URLSearchParams(body):JSON.stringify(body),signal:AbortSignal.timeout(15000)});
 const value=await reply.json();if(!reply.ok)throw Error('This clock device could not authenticate. Ask Employee administration to register it again.');return value;
}
function remember(value,deviceId){
 const uid=value.localId||value.user_id,refreshToken=value.refreshToken||value.refresh_token;
 if(!uid?.startsWith('clock-')||!refreshToken)throw Error('The pairing did not return a clock-only device account.');
 localStorage.setItem(storageKey,JSON.stringify({uid,refreshToken,deviceId}));
 session={uid,token:value.idToken||value.id_token,expires:Date.now()+Number(value.expiresIn||value.expires_in)*1000-60000};
}
export async function pairDevice(text){
 let value;try{value=JSON.parse(text);}catch{throw Error('Paste the one-time device pairing code issued in Employee.');}
 if(!value.email?.endsWith('@clock.backwoods.invalid')||!value.password||!value.deviceId)throw Error('Use a device pairing code from Employee administration.');
 const result=await response('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key='+apiKey,{email:value.email,password:value.password,returnSecureToken:true});
 remember(result,value.deviceId);
}
export function deviceContext(){
 const stored=saved();if(!stored)return null;
 return {uid:stored.uid,projectId,auth:{currentUser:{uid:stored.uid,async getIdToken(){
  if(session?.uid===stored.uid&&session.expires>Date.now())return session.token;
  if(!refreshing)refreshing=response('https://securetoken.googleapis.com/v1/token?key='+apiKey,{grant_type:'refresh_token',refresh_token:stored.refreshToken},true).then(value=>remember(value,stored.deviceId)).finally(()=>{refreshing=null;});
  await refreshing;return session.token;
 }}}};
}
