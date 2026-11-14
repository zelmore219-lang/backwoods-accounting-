import {createEmployeeRelay,pendingStore} from './employee-relay.mjs';
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stamp=value=>value?new Date(value).toLocaleString():'—';
const hours=minutes=>(Math.max(0,minutes)/60).toFixed(2)+' hours';
const store=pendingStore();
const current=()=>window.__bwVendorClockContext?.();
const relay=createEmployeeRelay(current,{store});
let uid='',view=null,busy=false,message='',opened=false,loadedAt=0,selectedJob='';
const entry=document.createElement('button');entry.id='bw-clock-entry';entry.type='button';entry.textContent='Clock In / Clock Out';entry.hidden=true;
const dialog=document.createElement('dialog');dialog.id='bw-clock-dialog';dialog.setAttribute('aria-label','Vendor time clock');
const style=document.createElement('style');style.textContent=`
#bw-clock-entry{position:fixed;right:18px;bottom:18px;z-index:70;border:1px solid #84a845;border-radius:12px;background:#24452b;color:#fff;padding:12px 18px;font:600 15px system-ui;box-shadow:0 3px 15px #0006;min-height:44px}
#bw-clock-entry[hidden]{display:none}
#bw-clock-dialog{width:min(850px,calc(100vw - 24px));max-height:90dvh;overflow:auto;background:#152119;color:#f5f4ed;border:1px solid #718157;border-radius:16px;padding:22px;font:16px system-ui}
#bw-clock-dialog::backdrop{background:#000b}#bw-clock-dialog h2{font-size:24px;margin:0 0 12px}#bw-clock-dialog p{margin:12px 0}
#bw-clock-dialog button,#bw-clock-dialog select{font:inherit;padding:10px;border-radius:8px;border:1px solid #849078;background:#24452b;color:#fff;min-height:44px}#bw-clock-dialog button:disabled{opacity:.5}#bw-clock-dialog .actions{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
#bw-clock-dialog table{width:100%;border-collapse:collapse;font-size:14px}#bw-clock-dialog td,#bw-clock-dialog th{text-align:left;border-bottom:1px solid #53634a;padding:10px;white-space:normal}#bw-clock-dialog .scroll{overflow:auto}#bw-clock-dialog .close{float:right}#bw-clock-dialog small{display:block;color:#d0d6c6}#bw-clock-dialog [role=status]{white-space:pre-wrap}
@media(max-width:600px){#bw-clock-entry{right:10px;bottom:calc(10px + env(safe-area-inset-bottom));font-size:13px}#bw-clock-dialog{padding:14px}#bw-clock-dialog table{font-size:12px}}
`;
document.head.append(style);document.body.append(entry,dialog);
const storageKey=id=>'backwoods-vendor-clock-action:'+id;
function saved(){try{return JSON.parse(localStorage.getItem(storageKey(uid))||'null');}catch{throw Error('The saved clock action could not be read. Ask the owner to review this device before recording another shift.');}}
function render(){
 if(!opened)return;
 const state=view?.state,active=state&&state.mode!=='out',card=view?.cards.find(c=>c.id===state?.cardId);
 const pending=saved();const jobs=view?.jobs||[];
 const blocked=active&&(!card||!jobs.some(j=>j.id===card.assignment_id));
 const elapsed=loadedAt?Math.max(0,performance.now()-loadedAt)/60000:0;
 const serverNow=view?Date.parse(view.server_now)+elapsed*60000:0;
 let shift=card?(card.worked_minutes??Math.max(0,(serverNow-Date.parse(card.clock_in))/60000-card.unpaid_minutes)):null;
 if(card&&active&&state.mode==='break'&&state.breakStartedAt)shift=Math.max(0,shift-(serverNow-Date.parse(state.breakStartedAt))/60000);
 dialog.innerHTML=`<button class="close" data-close aria-label="Close time clock">Close</button><h2>Vendor time clock</h2><p>${escape(view?.name||current()?.username||'')} <small>${escape(view?.username||'')}</small></p>
 <p><strong>${pending?'Clock action saved on this device; awaiting confirmation':!view?'Shared clock status unavailable':active?'Clocked in'+(card?' · '+escape(card.source):''):'Clocked out'}</strong></p>
 <p role="status" aria-live="polite">${escape(message)}</p>
 ${card?`<p>Shift start: ${escape(stamp(card.clock_in))}<br>Shift end: ${escape(stamp(card.clock_out))}<br>Current / latest shift: <strong>${hours(shift)}</strong></p>`:''}
 ${view?`<p>Vendor hours today (${escape(view.today)} · ${escape(view.timezone)}): <strong>${view.today_worked_minutes===null?escape(view.today_issue):hours(view.today_worked_minutes+(active&&card?.source==='vendor'&&state.mode==='working'?elapsed:0))}</strong></p>`:''}
 <label>Wholesale job <select data-job ${busy||active||pending?'disabled':''}><option value="">Select your assigned job</option>${jobs.map(j=>`<option value="${escape(j.id)}" ${(active?card?.assignment_id===j.id:selectedJob===j.id||!selectedJob&&jobs.length===1)?'selected':''}>${escape(j.title+' · '+j.division+' · '+j.location)}</option>`).join('')}</select></label>
 ${!jobs.length?'<p>Ask the owner to assign your actual Wholesale job in Employee → People → View → Assign job.</p>':''}
 ${blocked?'<p>This shift belongs to another job or app. Finish it in that app or ask Employee administration to review it before starting a Vendor shift.</p>':''}
 <div class="actions"><button data-in ${busy||pending||active||!jobs.length||!view?'disabled':''}>Clock In</button><button data-out ${busy||pending||!active||blocked?'disabled':''}>Clock Out</button><button data-refresh ${busy?'disabled':''}>${pending?'Retry saved clock action':'Refresh'}</button></div>
 ${pending?`<p>Saved ${escape(pending.kind==='in'?'Clock In':'Clock Out')} request: ${escape(stamp(pending.captured_at))}. Keep this app’s data until confirmed. Official times come from the shared service; delayed actions require office review.</p>`:''}
 <p><small>Timecard corrections and approvals are handled in Employee → Time & attendance → Shared time cards. Signing out keeps saved shifts and pending requests with the original account.</small></p>
 <h3>Recorded shifts</h3><div class="scroll"><table><thead><tr><th>Source / division</th><th>Clock in</th><th>Clock out</th><th>Worked</th><th>Status</th></tr></thead><tbody>${(view?.cards||[]).map(c=>`<tr><td>${escape(c.source)}<small>${escape(c.division)}</small></td><td>${escape(stamp(c.clock_in))}</td><td>${escape(stamp(c.clock_out))}</td><td>${c.worked_minutes===null?'Active':hours(c.worked_minutes)}</td><td>${escape(c.status)}${c.review_required?'<small>Office review required</small>':''}</td></tr>`).join('')}</tbody></table></div>`;
 dialog.querySelector('[data-job]').onchange=event=>{selectedJob=event.target.value;};
 dialog.querySelector('[data-close]').onclick=()=>dialog.close();
 dialog.querySelector('[data-in]').onclick=()=>action('in');dialog.querySelector('[data-out]').onclick=()=>action('out');dialog.querySelector('[data-refresh]').onclick=()=>refresh();
}
async function refresh(){
 if(busy||!uid)return;busy=true;message='Checking the Employee service…';render();const identity=uid;
 try{
  const pending=saved();
  const result=await relay.request(pending||{kind:'status'},{status:!pending});
  if(uid!==identity)return;
  if(pending)localStorage.removeItem(storageKey(identity));
  view=result;loadedAt=performance.now();message='Confirmed by the Employee service. Hours remain subject to office approval.';
 }catch(error){if(uid===identity){message=error.message;if(error.confirmedRejection)localStorage.removeItem(storageKey(identity));}}
 finally{busy=false;if(uid===identity)render();}
}
async function action(kind){
 if(busy||saved())return;
 const assignment=dialog.querySelector('[data-job]').value;if(!assignment){message='Select your actual assigned Wholesale job.';render();return;}
 const pending={kind,assignment_id:assignment,card_id:kind==='out'?view?.state?.cardId:'',request_key:crypto.randomUUID(),captured_at:new Date().toISOString(),offline:navigator.onLine===false};
 try{localStorage.setItem(storageKey(uid),JSON.stringify(pending));}
 catch{message='This device could not save the clock request. No clock action was sent.';render();return;}
 await refresh();
}
function identityChanged(){
 const context=current(),next=context?.uid||'';
 entry.hidden=!next;
 if(next!==uid){uid=next;view=null;loadedAt=0;selectedJob='';message='';if(opened)dialog.close();}
}
entry.onclick=()=>{identityChanged();if(!uid)return;opened=true;render();dialog.showModal();refresh();};
dialog.addEventListener('close',()=>{opened=false;});
window.addEventListener('bw:vendor-identity',identityChanged);
window.addEventListener('online',()=>{if(opened)refresh();});
setInterval(()=>{identityChanged();if(opened&&!busy)refresh();},30000);
setInterval(()=>{if(opened&&!busy)render();},60000);
identityChanged();
