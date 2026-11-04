/** Backwoods Brew wholesale Firestore service.
 * Requires a configured firebase/firestore SDK and an authenticated Firebase app.
 * Import these functions from original React source once recovered; NOT connected
 * to the compiled 8.2.0 UI. No localStorage fallback for financial writes.
 */
import {collection, doc, getDoc, getDocs, query, where, onSnapshot, runTransaction, serverTimestamp} from 'firebase/firestore';

const collections = Object.freeze({customers:'vendorCustomers',products:'vendorProducts',orders:'vendorOrders',packing:'vendorPacking',deliveries:'vendorDeliveries',movements:'vendorInventoryMovements',invoices:'vendorInvoices'});
const money = n => Number.isInteger(n) && n >= 0;
const quantity = n => Number.isInteger(n) && n > 0;
const requireId = s => {if(typeof s !== 'string'|| !/^[a-zA-Z0-9_-]{1,120}$/.test(s))throw Error('Invalid document ID');return s};
const ref = (db, type, id) => doc(db, collections[type], requireId(id));
const itemsValid = items => Array.isArray(items) && items.length>0 && items.length<=100 && items.every(x=>x&&requireId(x.productId)&&quantity(x.qty)&&money(x.unitPriceCents));
const assertAuth = user => {if(!user?.uid)throw Error('Firebase sign-in required');};

export async function loadWholesaleCatalog(db,user){
 assertAuth(user);
 const [customers,products] = await Promise.all([getDocs(collection(db,collections.customers)),getDocs(collection(db,collections.products))]);
 return {customers:customers.docs.map(d=>({id:d.id,...d.data()})),products:products.docs.map(d=>({id:d.id,...d.data()}))};
}
export function watchOrders(db,user,onChange,onError){
 assertAuth(user);
 return onSnapshot(collection(db,collections.orders),s=>onChange(s.docs.map(d=>({id:d.id,...d.data()}))),onError);
}
/** One idempotent order document per orderId. No stock is consumed at order submission. */
export async function submitOrder(db,user,{orderId,customerId,items}){
 assertAuth(user);requireId(orderId);requireId(customerId);
 if(!itemsValid(items))throw Error('Invalid order items; prices are integer cents');
 const normalized=items.map(x=>({productId:x.productId,qty:x.qty,unitPriceCents:x.unitPriceCents}));
 return runTransaction(db,async tx=>{
  const customer=await tx.get(ref(db,'customers',customerId));
  const order=await tx.get(ref(db,'orders',orderId));
  const productDocs=await Promise.all(normalized.map(x=>tx.get(ref(db,'products',x.productId))));
  if(!customer.exists())throw Error('Customer not found');
  normalized.forEach((x,i)=>{const p=productDocs[i];if(!p.exists())throw Error('Product not found: '+x.productId);if(!Number.isInteger(p.data().unitPriceCents)||p.data().unitPriceCents!==x.unitPriceCents)throw Error('Product price changed; refresh catalog');});
  if(order.exists()){
   if(order.data().createdBy===user.uid&&JSON.stringify(order.data().items)===JSON.stringify(normalized))return {id:orderId,alreadyExists:true};
   throw Error('Order ID already exists with different contents');
  }
  const totalCents=normalized.reduce((s,x)=>s+x.qty*x.unitPriceCents,0);
  if(!Number.isSafeInteger(totalCents))throw Error('Order total out of range');
  tx.set(ref(db,'orders',orderId),{customerId,items:normalized,totalCents,status:'Submitted',createdBy:user.uid,createdAt:serverTimestamp(),division:'wholesale'});
  return {id:orderId,alreadyExists:false};
 });
}
/** Warehouse-only: atomic status transition and packing document creation. */
export async function confirmPacking(db,user,{orderId,packingId,packedItems}){
 assertAuth(user);requireId(orderId);requireId(packingId);
 if(!Array.isArray(packedItems)||packedItems.length===0||!packedItems.every(x=>x&&requireId(x.productId)&&Number.isInteger(x.qty)&&x.qty>=0))throw Error('Invalid packing quantities');
 return runTransaction(db,async tx=>{
  const orderRef=ref(db,'orders',orderId),packRef=ref(db,'packing',packingId);
  const [order,packing]=await Promise.all([tx.get(orderRef),tx.get(packRef)]);
  if(!order.exists())throw Error('Order missing');
  if(packing.exists())throw Error('Packing ID already exists');
  if(order.data().status!=='Submitted')throw Error('Order is not awaiting packing');
  const requested=new Map(order.data().items.map(x=>[x.productId,x.qty]));
  const seen=new Set();
  for(const x of packedItems){if(seen.has(x.productId)||!requested.has(x.productId)||x.qty>requested.get(x.productId))throw Error('Packing mismatch');seen.add(x.productId)}
  tx.set(packRef,{orderId,packedItems,packedBy:user.uid,packedAt:serverTimestamp(),status:'Packed'});
  tx.update(orderRef,{status:'Packed',packingId,packedAt:serverTimestamp()});
  return {id:packingId};
 });
}
/** Driver confirmation: records proof and moves order to Delivered atomically.
 * Inventory and financial posting intentionally NOT performed here until the
 * authoritative cost model and central-ledger schema are confirmed. */
export async function confirmDelivery(db,user,{orderId,deliveryId,recipient}){
 assertAuth(user);requireId(orderId);requireId(deliveryId);
 if(typeof recipient!=='string'||!recipient.trim()||recipient.length>160)throw Error('Recipient required');
 return runTransaction(db,async tx=>{
  const orderRef=ref(db,'orders',orderId),deliveryRef=ref(db,'deliveries',deliveryId);
  const [order,delivery]=await Promise.all([tx.get(orderRef),tx.get(deliveryRef)]);
  if(!order.exists()||order.data().status!=='Packed')throw Error('Order not ready for delivery');
  if(delivery.exists())throw Error('Delivery ID already exists');
  tx.set(deliveryRef,{orderId,recipient:recipient.trim(),deliveredBy:user.uid,deliveredAt:serverTimestamp(),status:'Delivered'});
  tx.update(orderRef,{status:'Delivered',deliveryId,deliveredAt:serverTimestamp(),accountingStatus:'pending_review'});
  return {id:deliveryId};
 });
}
export {collections};
