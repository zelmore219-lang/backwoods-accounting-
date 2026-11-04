// Visible, owner-operated opt-in. No source records are mutated by this panel.
(() => {
  const mount=()=>{
    if(!window.businessAccounting||document.getElementById('bw-business-feed'))return;
    const box=document.createElement('details');box.id='bw-business-feed';
    box.style.cssText='position:fixed;left:12px;bottom:12px;z-index:2147483646;max-width:350px;background:#153e35;color:#fff;border:1px solid #a6b591;border-radius:9px;padding:10px 14px;font:12px system-ui;box-shadow:0 4px 16px #0003';
    const summary=document.createElement('summary');summary.textContent='Business Accounting connection';summary.style.cursor='pointer';
    const p=document.createElement('p');p.textContent='Send a read-only accounting snapshot to Business Accounting on this computer. Your app keeps its separate books.';
    const button=document.createElement('button');button.style.cssText='padding:8px 12px;border:0;border-radius:6px;cursor:pointer;background:#e4c27d;color:#153e35';
    const status=document.createElement('p');status.style.cssText='font-size:11px;overflow-wrap:anywhere;margin-bottom:0';
    const enabled=()=>localStorage.getItem('bw-business-accounting-enabled')==='yes';
    const refresh=async()=>{
      button.textContent=enabled()?'Stop sending to Business Accounting':'Send to Business Accounting';
      try {
        const s=await window.businessAccounting.status();
        const received=s.received;
        status.textContent=s.error||(!enabled()?'Connection off.':received?received.ok?`Business Accounting received a snapshot at ${received.at}. ${received.reviewCount||0} inventory costs need review.`:`Import needs attention: ${received.error}`:s.message||'Waiting for the next snapshot. Sign in as the owner.');
      }catch(e){status.textContent=e.message;}
    };
    button.onclick=()=>{localStorage.setItem('bw-business-accounting-enabled',enabled()?'no':'yes');refresh();};
    box.append(summary,p,button,status);document.body.append(box);refresh();setInterval(refresh,5000);
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
