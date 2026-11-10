const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function documentForReceipt(payload){
  const text=typeof payload==='string'?payload:payload?.text;
  const title=typeof payload==='object'?payload.title:'Receipt';
  if(typeof text!=='string'||!text.trim()||text.length>200000)throw Error('A nonempty receipt up to 200,000 characters is required.');
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><title>${escape(title||'Receipt')}</title><style>@page{size:80mm auto;margin:4mm}html,body{margin:0;padding:0;background:white;color:black}pre{margin:0;width:72mm;max-width:100%;font:12px/1.4 monospace;white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body><pre>${escape(text)}</pre></body></html>`;
}

function registerReceiptPrinter({ipcMain,BrowserWindow}){
  ipcMain.handle('print-receipt',async(event,payload)=>{
    const parent=BrowserWindow.fromWebContents(event.sender);
    if(!parent||event.senderFrame!==parent.webContents.mainFrame)throw Error('Main app window required');
    let preview;
    try{
      const html=documentForReceipt(payload);
      preview=new BrowserWindow({parent,show:false,width:420,height:760,webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:false}});
      preview.webContents.setWindowOpenHandler(()=>({action:'deny'}));
      await preview.loadURL('data:text/html;charset=utf-8,'+encodeURIComponent(html));
      await preview.webContents.executeJavaScript("document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))).then(()=>{if(!document.body.innerText.trim())throw Error('Receipt did not render')})");
      return await new Promise(resolve=>preview.webContents.print({silent:false,printBackground:true,margins:{marginType:'none'}},(ok,error)=>resolve({ok,error:error||''})));
    }catch(error){return {ok:false,error:error.message};}
    finally{if(preview&&!preview.isDestroyed())preview.destroy();}
  });
}
module.exports={documentForReceipt,registerReceiptPrinter};
