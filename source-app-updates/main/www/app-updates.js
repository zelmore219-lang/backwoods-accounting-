(()=>{
 const id='backwoods-settings-updates';
 function supported(){return !!window.backwoodsUpdates||window.Capacitor?.isPluginAvailable?.('BackwoodsUpdater');}
 function open(){if(window.backwoodsUpdates)return window.backwoodsUpdates.open();return window.Capacitor.nativePromise('BackwoodsUpdater','open',{});}
 function host(){
  const settings=[...document.querySelectorAll('h1')].find(h=>h.textContent.trim()==='Company Settings');
  if(settings)return document.querySelector('.settings-tabs');
  const heading=[...document.querySelectorAll('h3')].find(h=>h.textContent.trim()==='Auto Update');
  return heading?heading.parentElement?.parentElement?.parentElement:null;
 }
 function attach(){
  // Older builds placed this control above login or in the sidebar.
  document.getElementById('backwoods-app-updates')?.remove();
  const target=supported()?host():null,existing=document.getElementById(id);
  if(!target){existing?.remove();return;}
  if(existing?.parentElement===target)return;
  existing?.remove();
  const isMain=!![...target.querySelectorAll('h3')].find(h=>h.textContent.trim()==='Auto Update');
  if(isMain){
   target.setAttribute('data-backwoods-update-settings','true');
   if(!document.getElementById('backwoods-update-settings-style')){
    const style=document.createElement('style');style.id='backwoods-update-settings-style';style.textContent='[data-backwoods-update-settings] > :not(#'+id+'){display:none!important}';document.head.append(style);
   }
  }
  const panel=document.createElement('section');panel.id=id;if(!isMain)panel.className='panel settings-section';
  const title=document.createElement('h2');title.textContent='App updates';panel.append(title);
  const description=document.createElement('p');description.textContent='Check the installed and latest versions, download a verified update, and choose when to install.';panel.append(description);
  const button=document.createElement('button');button.type='button';button.textContent='Open app updates';button.style.cssText='padding:12px 18px;border-radius:8px;background:#153e35;color:white;border:1px solid #b78a36;cursor:pointer';button.onclick=()=>Promise.resolve(open()).catch(()=>{description.textContent='Could not open the update window. Please try again.';});panel.append(button);
  if(isMain)target.append(panel);else target.prepend(panel);
 }
 let pending=false;const schedule=()=>{if(!pending){pending=true;setTimeout(()=>{pending=false;attach();},40);}};
 const start=()=>{new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});window.addEventListener('hashchange',schedule);attach();};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
