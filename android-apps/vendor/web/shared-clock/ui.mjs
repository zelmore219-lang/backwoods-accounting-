import {createEmployeeRelay} from './relay.mjs';
import {deviceContext,pairDevice} from './device.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clockTime=(at,zone)=>at?new Date(at).toLocaleString(undefined,{timeZone:zone||'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit'}):'';
export function createSharedClock({source,context=()=>null,signedRequest,pendingRequest,enabled=()=>true,kiosk=false,onConfirmed=()=>{}}){
 const device=createEmployeeRelay(deviceContext,{scope:'clock'}),signed=createEmployeeRelay(context);
 let registered=false,checking=false,checkedAt=0,dialog,view,pin='',message='',busy=false,mode='pin',timer,pending,epoch=0;
 const styles=document.createElement('style');styles.textContent=`
 .bw-shared-clock{border:1px solid #61755c;border-radius:12px;background:#172b22;color:#fff;padding:14px;margin:12px 0;font:16px system-ui}.bw-shared-clock button{padding:12px 18px;min-height:48px;background:#d8bd70;color:#102119;border:0;border-radius:8px;font:600 16px system-ui}
 .bw-clock-dialog{background:#14271e;color:#fff;border:1px solid #9eb68c;border-radius:18px;width:min(440px,calc(100vw - 32px));padding:24px;font:18px system-ui}.bw-clock-dialog::backdrop{background:#000b}.bw-clock-dialog button,.bw-clock-dialog select,.bw-clock-dialog textarea{font:inherit;padding:14px;border-radius:8px;min-height:52px;max-width:100%}.bw-clock-dialog button{background:#d8bd70;color:#102119;border:0;cursor:pointer}.bw-clock-dialog button:disabled{opacity:.45;cursor:wait}.bw-clock-dialog .bw-keypad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:16px 0}.bw-clock-dialog output{display:block;letter-spacing:12px;min-height:32px;text-align:center;font-size:28px}.bw-clock-dialog .bw-next{width:100%;margin:14px 0}.bw-clock-dialog [role=alert]{font-size:16px}.bw-clock-dialog select,.bw-clock-dialog textarea{display:block;width:100%;margin:10px 0;background:#fff;color:#14271e}.bw-clock-dialog h2{margin-top:0}.bw-clock-dialog .bw-close{float:right;background:transparent;color:#fff;min-height:44px;padding:5px 8px}
 `;document.head.append(styles);
 function clear(){epoch++;pin='';view=null;pending=null;message='';busy=false;clearTimeout(timer);}
 function idle(){clearTimeout(timer);if(view&&!busy)timer=setTimeout(()=>{clear();if(dialog?.open){mode='pin';if(kiosk)draw();else dialog.close();}},45000);}
 async function send(data,shared=false){
  if(!navigator.onLine)throw Error('No connection. Connect to record and confirm a punch.');
  const result=await(shared?device.request({...data,source},{persist:data.action==='confirm'}):signedRequest?signedRequest({...data,source}):signed.request({...data,source},{persist:data.action==='confirm'}));
  if(result.status_code>=400)throw Object.assign(Error(result.error),{confirmedRejection:true});return result;
 }
 function draw(){
  if(!dialog?.open)return;
  const active=view?.status&&view.status!=='out';
  dialog.innerHTML=`<button type="button" class="bw-close" aria-label="Close time clock">Close</button><h2>Time Clock</h2><p role="alert" aria-live="polite">${esc(message)}</p>${mode==='pair'?'<label>One-time device pairing code<textarea autocomplete="off" data-pair rows="4"></textarea></label><button class="bw-next" data-enroll>Register this device</button>':view?`<h3>${esc(view.name)}</h3><p>${active?'Clocked in at '+esc(clockTime(view.clock_in,view.timezone)):'Clocked out'}${view.business?' · '+esc(view.business):''}</p>${!active?`<label>Assigned job<select data-job><option value="">Choose your job</option>${view.jobs.map(j=>`<option value="${esc(j.id)}" ${view.jobs.length===1?'selected':''}>${esc(j.business+' · '+j.location+' · '+j.title)}</option>`).join('')}</select></label>`:''}<button class="bw-next" data-confirm ${busy?'disabled':''}>${busy?'Checking recorded punch…':active?'Clock Out':'Clock In'}</button>`:mode==='pin'?`<p>Enter your six-digit clock PIN</p><output aria-label="${pin.length} of 6 digits entered">${'●'.repeat(pin.length)}</output><div class="bw-keypad">${['1','2','3','4','5','6','7','8','9','Clear','0','Backspace'].map(n=>`<button type="button" data-key="${n}" ${busy?'disabled':''}>${n}</button>`).join('')}</div><button class="bw-next" data-verify ${pin.length!==6||busy?'disabled':''}>${busy?'Checking PIN…':'Continue'}</button>`:'<p>Checking the shared clock…</p>'}${pending?'<button class="bw-next" data-retry>Check saved punch</button>':''}`;
  dialog.querySelector('.bw-close').onclick=()=>{if(kiosk){clear();mode=registered?'pin':'pair';draw();}else dialog.close();};
  dialog.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>{if(busy)return;const k=b.dataset.key;pin=k==='Clear'?'':k==='Backspace'?pin.slice(0,-1):pin.length<6?pin+k:pin;draw();});
  dialog.querySelector('[data-verify]')?.addEventListener('click',verify);
  dialog.querySelector('[data-confirm]')?.addEventListener('click',confirm);
  dialog.querySelector('[data-retry]')?.addEventListener('click',()=>perform(pending));
  dialog.querySelector('[data-enroll]')?.addEventListener('click',async()=>{const input=dialog.querySelector('[data-pair]'),code=input.value;input.value='';try{await pairDevice(code);const result=await send({action:'device'},true);registered=result.registered===true;if(kiosk){clear();mode='pin';draw();}else dialog.close();checkedAt=0;await tick();}catch(e){message=e.message;draw();}});
 }
 function modal(next){clear();mode=next;if(!dialog){dialog=document.createElement('dialog');dialog.className='bw-clock-dialog';dialog.setAttribute('aria-label','Shared time clock');document.body.append(dialog);dialog.addEventListener('close',clear);dialog.addEventListener('cancel',event=>{if(kiosk){event.preventDefault();clear();mode=registered?'pin':'pair';draw();}else clear();});dialog.addEventListener('pointerdown',idle);}
  dialog.showModal();draw();
 }
 async function verify(){
  if(busy||pin.length!==6)return;const entered=pin;pin='';busy=true;message='';const run=epoch;draw();
  try{const result=await send({action:'verify',pin:entered},true);if(run!==epoch)return;view=result;mode='device';idle();}
  catch(e){if(run===epoch)message=e.message;}finally{if(run===epoch){busy=false;idle();draw();}}
 }
 async function confirm(){
  if(busy||!view)return;
  const kind=view.status==='out'?'in':'out',assignment_id=kind==='in'?dialog.querySelector('[data-job]')?.value:undefined;
  if(kind==='in'&&!assignment_id){message='Choose your assigned job.';draw();return;}
  await perform({action:'confirm',kind,version:view.version,assignment_id,request_key:crypto.randomUUID(),...(mode==='device'?{ticket:view.ticket}:{}),shared:mode==='device'});
 }
 async function perform(action){
  if(busy)return;busy=true;pending=action;message='Confirming with Employee…';clearTimeout(timer);const run=epoch;draw();
  const {shared,...data}=action;
  try{
   const result=await send(data,shared);if(run!==epoch)return;
   if(result.conflict){pending=null;view={...result,ticket:view?.ticket||data.ticket};message=result.error;idle();return;}
   if(result.confirmed!==true)throw Error('The backend has not confirmed this punch. Check the saved request.');
   // Replace employee details before displaying the confirmed time.
   const text=(result.kind==='in'?'Clock In':'Clock Out')+' recorded at '+clockTime(result.recorded_at,result.timezone);
   clear();mode='done';dialog.innerHTML=`<h2>${esc(text)}</h2><p role="status">Confirmed by Employee.</p>`;onConfirmed(result);
   const completed=epoch;setTimeout(()=>{if(epoch===completed){if(kiosk){clear();mode='pin';draw();}else dialog.close();}},2000);checkedAt=0;
  }catch(e){if(run===epoch){message=e.message;if(e.confirmedRejection){pending=null;view=null;mode=shared?'pin':'signed';}else{view=null;mode='pending';} }}
  finally{if(run===epoch){busy=false;idle();draw();}}
 }
 async function openDevice(){modal(registered?'pin':'pair');if(!registered)return;const run=epoch;try{const saved=await device.pending(source);if(run===epoch&&saved){pending={...saved,shared:true};mode='pending';message='Check the previously submitted punch before entering another PIN.';draw();}}catch(e){if(run===epoch){message=e.message;draw();}}}
 async function openSigned(){modal('signed');const run=epoch;
  try{const saved=pendingRequest?await pendingRequest():await signed.pending(source);if(saved){pending={...saved,shared:false};mode='pending';message='Check the previously submitted punch before recording another.';}else view=await send({action:'status'});if(run===epoch){idle();draw();}}
  catch(e){if(run===epoch){message=e.message;draw();}}
 }
 async function tick(){
  if(!enabled()){if(dialog?.open){clear();dialog.close();}document.querySelectorAll('[data-bw-clock-entry]').forEach(e=>e.remove());return;}
  if(!checking&&Date.now()-checkedAt>60000){checking=true;try{registered=deviceContext()?(await send({action:'device'},true)).registered===true:false;}catch(e){registered=!!deviceContext()&&!e.confirmedRejection;message=e.message;}finally{checking=false;checkedAt=Date.now();}}
  const auth=context()?.uid;
  if(kiosk){if(!dialog?.open)await openDevice();return;}
  if(auth){
   document.querySelectorAll('[data-bw-pin-entry]').forEach(e=>e.remove());
   if(!document.querySelector('[data-bw-status]')){
    const host=document.createElement('section');host.className='bw-shared-clock';host.dataset.bwClockEntry='';host.dataset.bwStatus='';host.innerHTML='<span data-state>Time Clock · checking status…</span> <button type="button">Open Time Clock</button>';host.querySelector('button').onclick=openSigned;
    const top=document.querySelector('main header,main .page-heading,main h1,main.content h1');if(top)top.insertAdjacentElement('afterend',host);else document.querySelector('main,#app,#root')?.prepend(host);
   }
   try{const status=await send({action:'status'});const host=document.querySelector('[data-bw-status]');if(host){host.querySelector('[data-state]').textContent=status.status==='out'?'Clocked out':'Clocked in at '+clockTime(status.clock_in,status.timezone);host.querySelector('button').textContent=status.status==='out'?'Clock In':'Clock Out';}}
   catch(e){const host=document.querySelector('[data-bw-status] [data-state]');if(host)host.textContent='Clock status unavailable · '+e.message;}
  }else{
   document.querySelectorAll('[data-bw-status]').forEach(e=>e.remove());
   const signIn=[...document.querySelectorAll('button')].find(b=>/^sign\s*in(?:\s*→)?$/i.test(b.textContent.trim()));
   if(signIn&&!document.querySelector('[data-bw-pin-entry]')){const b=document.createElement('button');b.type='button';b.dataset.bwClockEntry='';b.dataset.bwPinEntry='';b.textContent=registered?'Time Clock':'Register shared time-clock device';b.style.cssText='display:block;width:100%;margin-top:12px;min-height:48px';b.onclick=openDevice;signIn.insertAdjacentElement('afterend',b);}
   const b=document.querySelector('[data-bw-pin-entry]');if(b){b.textContent=registered?'Time Clock':'Register shared time-clock device';b.onclick=openDevice;}
  }
 }
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&dialog?.open){clear();dialog.close();}else if(!document.hidden&&kiosk)tick();});
 let queued=false;
 new MutationObserver(()=>{if(queued)return;queued=true;setTimeout(()=>{queued=false;if(!document.querySelector('[data-bw-clock-entry]'))tick();},200);}).observe(document.body,{childList:true,subtree:true});
 const interval=setInterval(()=>tick(),30000);tick();
 return {open:openSigned,refresh:tick,dispose(){clearInterval(interval);clear();dialog?.remove();styles.remove();}};
}
