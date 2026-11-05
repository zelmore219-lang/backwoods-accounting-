(()=>{
 function open(){if(window.backwoodsUpdates)return window.backwoodsUpdates.open();const cap=window.Capacitor;if(cap?.isPluginAvailable?.('BackwoodsUpdater'))return cap.nativePromise('BackwoodsUpdater','open',{});}
 function attach(){
  const supported=!!window.backwoodsUpdates||window.Capacitor?.isPluginAvailable?.('BackwoodsUpdater');if(!supported)return;
  if(document.getElementById('backwoods-app-updates'))return;
  const button=document.createElement('button');button.id='backwoods-app-updates';button.type='button';button.textContent='App updates';button.setAttribute('aria-label','Open app updates');button.onclick=()=>Promise.resolve(open()).catch(()=>{button.textContent='Could not open updates. Try again.';});
  const aside=document.querySelector('aside');
  if(aside){button.style.cssText='display:block;margin:12px;width:calc(100% - 24px);padding:12px;cursor:pointer';aside.append(button);}
  else{button.style.cssText='position:fixed;right:12px;top:12px;z-index:1000;border:1px solid #b78a36;border-radius:8px;background:#153e35;color:white;padding:10px 14px;cursor:pointer';document.body.append(button);}
 }
 setInterval(attach,1500);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',attach);else attach();
})();
