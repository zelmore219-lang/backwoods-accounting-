/* Phase 6: Firestore wholesale UI bridge. No implicit access to local financial records. */
(() => {
  'use strict';
  const id = x => typeof x === 'string' && /^[a-zA-Z0-9_-]{1,120}$/.test(x);
  const escape = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const state = {connected:false,orders:[],customers:[],products:[],error:'Not connected',unsub:null,busy:false};
  const adapter = () => window.BackwoodsWholesaleCloudAdapter;
  function status(message){state.error=message; render();}
  function html(){
    return `<h3>Live wholesale operations</h3><p><strong>Connection:</strong> ${escape(state.connected?'Authenticated Firestore session':'Not connected')} · ${escape(state.error)}</p>
      <p>This workspace uses cloud records only. It does not transfer local wholesale orders or post accounting entries.</p>
      <button id="bw-cloud-connect" type="button">Connect existing Firebase session</button><button id="bw-cloud-diagnose" type="button">Check Firebase access (read only)</button><pre id="bw-cloud-diagnostics-result" style="white-space:pre-wrap"></pre>
      <button id="bw-cloud-refresh" type="button" ${state.connected?'':'disabled'}>Refresh</button>
      <h4>Submit wholesale order</h4><form id="bw-cloud-order">
      <label>Customer<select name="customerId" required><option value="">Select</option>${state.customers.map(c=>`<option value="${escape(c.id)}">${escape(c.name || c.businessName || c.id)}</option>`).join('')}</select></label>
      <label>Product<select name="productId" required><option value="">Select</option>${state.products.map(p=>`<option value="${escape(p.id)}">${escape(p.name || p.id)}</option>`).join('')}</select></label>
      <label>Quantity<input name="qty" type="number" min="1" step="1" required></label>
      <label>Unit price (USD)<input name="price" type="number" min="0" step="0.01" required></label>
      <button type="submit" ${false?'':'disabled'}>Submit cloud order</button></form>
      <h4>Cloud orders</h4><div class="bw-tablewrap"><table><thead><tr><th>Order</th><th>Status</th><th>Amount</th><th>Workflow</th></tr></thead><tbody>${state.orders.map(o=>`<tr><td>${escape(o.id)}</td><td>${escape(o.status)}</td><td>${Number.isInteger(o.totalCents)?'$'+(o.totalCents/100).toFixed(2):'—'}</td><td>${false&&o.status==='Submitted'?`<button data-cloud-pack="${escape(o.id)}">Confirm packing</button>`:false&&o.status==='Packed'?`<button data-cloud-deliver="${escape(o.id)}">Confirm delivery</button>`:'—'}</td></tr>`).join('')||'<tr><td colspan="4">No cloud orders loaded</td></tr>'}</tbody></table></div>
      <p><small>Read-only cloud preview: order submission, packing and delivery are disabled until secure write testing. Packing and delivery require appropriate Firebase roles. Delivery does not yet deduct inventory or post to the main ledger.</small></p>`;
  }
  function render(){const el=document.getElementById('bw-wh-content');if(el&&window.BackwoodsWholesaleCloudActive)el.innerHTML=html();}
  async function connect(){
    const a=adapter();
    if(!a||!['currentUser','loadWholesaleCatalog','watchOrders','submitOrder','confirmPacking','confirmDelivery'].every(k=>typeof a[k]==='function'))return status('Firebase bridge not installed. No writes attempted.');
    const user=await a.currentUser();
    if(!user?.uid)return status('Sign in to Backwoods Brew before connecting.');
    if(state.unsub){state.unsub();state.unsub=null;}
    const catalog=await a.loadWholesaleCatalog();
    state.customers=catalog.customers;state.products=catalog.products;state.connected=true;
    state.unsub=a.watchOrders(orders=>{state.orders=orders;state.error='Connected';render()},err=>status('Cloud listener: '+(err?.message||err)));
    status('Connected');
  }
  async function refresh(){const a=adapter();if(!state.connected||!a)return;const c=await a.loadWholesaleCatalog();state.customers=c.customers;state.products=c.products;render();}
  async function action(task){if(state.busy)return;state.busy=true;render();try{await task();state.error='Operation accepted by Firestore';}catch(e){state.error='Operation failed: '+(e?.message||e)}finally{state.busy=false;render();}}
  document.addEventListener('click',e=>{
    const target=e.target.closest('#bw-cloud-connect,#bw-cloud-diagnose,#bw-cloud-refresh,[data-cloud-pack],[data-cloud-deliver]');if(!target)return;
    if(target.id==='bw-cloud-connect')action(connect);
    else if(target.id==='bw-cloud-diagnose')window.BackwoodsWholesaleDiagnostics?.run();
    else if(target.id==='bw-cloud-refresh')action(refresh);
    else if(target.dataset.cloudPack){const orderId=target.dataset.cloudPack;if(!id(orderId))return;action(()=>adapter().confirmPacking({orderId,packingId:'pack_'+orderId,packedItems:(state.orders.find(x=>x.id===orderId)?.items||[]).map(x=>({productId:x.productId,qty:x.qty}))}));}
    else if(target.dataset.cloudDeliver){const orderId=target.dataset.cloudDeliver;if(!id(orderId))return;const recipient=prompt('Recipient name for delivery confirmation:');if(!recipient)return;action(()=>adapter().confirmDelivery({orderId,deliveryId:'delivery_'+orderId,recipient}));}
  });
  document.addEventListener('submit',e=>{if(e.target.id!=='bw-cloud-order')return;e.preventDefault();const f=new FormData(e.target),qty=Number(f.get('qty')),price=Number(f.get('price'));if(!id(f.get('customerId'))||!id(f.get('productId'))||!Number.isSafeInteger(qty)||qty<1||!Number.isFinite(price)||price<0||!Number.isSafeInteger(Math.round(price*100)))return status('Invalid order fields');const orderId='ord_'+crypto.randomUUID().replaceAll('-','');action(()=>adapter().submitOrder({orderId,customerId:f.get('customerId'),items:[{productId:f.get('productId'),qty,unitPriceCents:Math.round(price*100)}]}));});
  window.BackwoodsWholesaleCloudUI={show(){window.BackwoodsWholesaleCloudActive=true;render()},hide(){window.BackwoodsWholesaleCloudActive=false;},state};
})();
