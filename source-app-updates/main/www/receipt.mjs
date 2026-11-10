/** Receipt rendering uses recorded sale values, never today's catalog prices. */
const money=value=>Number(value||0).toLocaleString('en-US',{style:'currency',currency:'USD'});
const number=(value,fallback=0)=>Number.isFinite(Number(value))?Number(value):fallback;
const has=(value,key)=>value[key]!==undefined&&value[key]!==null&&value[key]!=='';

export function receiptBusiness(data,sale) {
  if(sale.receiptBusiness)return sale.receiptBusiness;
  const store=(data.stores||[]).find(row=>String(row.id)===String(sale.storeId||1))||{};
  return {name:data.settings?.businessName||'Backwoods Brew',storeName:store.name||`Store ${sale.storeId||1}`,
    address:store.address||store.streetAddress||'',city:store.city||'',state:store.state||'',zip:store.zip||store.zipCode||''};
}

export function receiptText(data,sale) {
  if(!sale?.id)throw Error('Select a saved transaction before printing.');
  const business=receiptBusiness(data,sale),rule='-'.repeat(32);
  const stamp=sale.createdAt||sale.date;
  const when=stamp&&!Number.isNaN(new Date(stamp).getTime())?new Date(stamp).toLocaleString():String(stamp||'Not recorded');
  const lines=[business.name,business.storeName,business.address,[business.city,business.state,business.zip].filter(Boolean).join(' '),
    when,`Receipt #${sale.id}`,`Cashier: ${sale.cashier||sale.employeeName||'Not recorded'}`,sale.pickupName?`Customer: ${sale.pickupName}`:'',rule];
  for(const item of sale.items||[]) {
    const qty=has(item,'qty')?number(item.qty,1):has(item,'quantity')?number(item.quantity,1):1;
    const extras=number(item.size?.priceAdd)+(item.mods||[]).reduce((sum,mod)=>sum+number(mod.price),0);
    const recordedUnit=has(item,'unitPrice')?number(item.unitPrice):number(item.price)+extras;
    const total=has(item,'lineTotal')?number(item.lineTotal):recordedUnit*qty;
    // Historic sales can lack unitPrice; the recorded extended price takes priority.
    const unit=qty?total/qty:recordedUnit;
    lines.push(String(item.name||item.productName||'Unnamed item'),`  ${qty} x ${money(unit)} = ${money(total)}`);
    if(item.size?.name||item.size?.label)lines.push(`  Size: ${item.size.name||item.size.label}`);
    for(const mod of item.mods||[])lines.push(`  + ${mod.name||''} ${money(mod.price)}`);
  }
  lines.push(rule,`Subtotal: ${money(sale.subtotal)}`,`Discount: -${money(sale.discountAmount)}`,`Sales tax: ${money(sale.tax)}`,
    `TOTAL: ${money(sale.total)}`,`Payment: ${sale.paymentType||sale.paymentMethod||'Not recorded'}`);
  if(sale.paymentType==='Cash') {
    lines.push(`Tendered: ${has(sale,'amountTendered')?money(sale.amountTendered):'Not recorded'}`,
      `Change: ${has(sale,'changeDue')?money(sale.changeDue):'Not recorded'}`);
  }
  if(sale.paymentType==='Split')lines.push(`Cash: ${money(sale.splitCash)} / Card: ${money(sale.splitCard)}`,
    `Tendered: ${money(sale.amountTendered)}`,`Change: ${money(sale.changeDue)}`);
  if(sale.tipAmount)lines.push(`Tip: ${money(sale.tipAmount)}`);
  if(sale.couponCode)lines.push(`Coupon: ${sale.couponCode}`);
  if(sale.loyaltyCode)lines.push(`Loyalty: ${sale.loyaltyCode}`);
  lines.push(rule,'Thank you for supporting us!');
  return lines.filter(line=>line!=='').join('\n');
}

const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function printDocument(title,text) {
  if(!String(text||'').trim())throw Error('Receipt has no recorded content. Reopen the saved transaction and try again.');
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escape(title)}</title><style>
    @page{size:80mm auto;margin:4mm}html,body{margin:0;padding:0;color:#000;background:#fff}
    pre{box-sizing:border-box;margin:0;width:72mm;max-width:100%;font:12px/1.4 monospace;white-space:pre-wrap;overflow-wrap:anywhere}
  </style></head><body><pre>${escape(text)}</pre></body></html>`;
}

export function previewReceipt(title,text,{document:doc=globalThis.document,window:win=globalThis.window}={}) {
  const html=printDocument(title,text);
  doc.getElementById('bw-receipt-preview')?.remove();
  const previous=doc.activeElement,dialog=doc.createElement('dialog');dialog.id='bw-receipt-preview';
  dialog.setAttribute('aria-label',`${title} preview`);
  const heading=doc.createElement('h2');heading.textContent=`${title} preview`;
  const pre=doc.createElement('pre');pre.textContent=text;pre.className='bw-receipt-text';
  const status=doc.createElement('p');status.setAttribute('role','status');status.textContent='Transaction saved. Choose Print to select a printer or save a PDF.';
  const print=doc.createElement('button');print.textContent='Print / Save PDF';print.type='button';
  const close=doc.createElement('button');close.textContent='Close preview';close.type='button';
  const actions=doc.createElement('div');actions.className='bw-receipt-actions';actions.append(print,close);
  let frame;
  const cleanup=()=>{frame?.remove();dialog.remove();doc.body.classList.remove('bw-printing-receipt');previous?.focus?.();};
  close.onclick=()=>dialog.close();dialog.addEventListener('close',cleanup,{once:true});
  print.onclick=async()=>{
    if(print.disabled)return;print.disabled=true;status.textContent='Opening print options…';
    try {
      if(win.backwoodsElectron?.printReceipt) {
        const result=await win.backwoodsElectron.printReceipt({title,text:String(text)});
        if(!result?.ok&&!/cancel/i.test(result?.error||''))throw Error(result?.error||'The printer did not accept the receipt.');
        status.textContent=result?.ok?'Receipt sent to the printer.':'Printing canceled. Your transaction is still saved.';
      } else if(win.Capacitor?.isNativePlatform?.()&&win.Capacitor.isPluginAvailable?.('NativePrint')) {
        // The native plugin prints the current WebView. Print CSS selects only this receipt.
        await win.Capacitor.nativePromise('NativePrint','print',{});
        status.textContent='Print options opened. Your transaction is saved.';
      } else {
        frame?.remove();frame=doc.createElement('iframe');frame.title='Receipt print document';frame.className='bw-receipt-print-frame';
        const loaded=new Promise((resolve,reject)=>{const timer=win.setTimeout(()=>reject(Error('Receipt print document did not finish loading. Try Print again.')),10000);frame.onload=()=>{win.clearTimeout(timer);resolve();};frame.onerror=()=>{win.clearTimeout(timer);reject(Error('Receipt print document could not load.'));};});
        frame.srcdoc=html;doc.body.append(frame);await loaded;
        if(frame.contentDocument.fonts?.ready)await frame.contentDocument.fonts.ready;
        await new Promise(resolve=>win.requestAnimationFrame(()=>win.requestAnimationFrame(resolve)));
        if(!frame.contentDocument.body.textContent.trim())throw Error('Receipt print document is empty.');
        frame.contentWindow.focus();frame.contentWindow.print();
        status.textContent='Print options opened. Your transaction is saved.';
        // Keep the frame until the preview closes; browsers can snapshot after print() returns.
      }
    } catch(error){status.textContent=`Printing did not finish: ${error.message} Your transaction is still saved. You can try again.`;}
    finally{print.disabled=false;}
  };
  dialog.append(heading,actions,status,pre);doc.body.append(dialog);doc.body.classList.add('bw-printing-receipt');dialog.showModal();print.focus();
  return dialog;
}
