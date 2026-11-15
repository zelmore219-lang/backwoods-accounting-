// Quantity changes use retained operation IDs and server transactions. The
// production receipt and a simultaneous Vendor delivery both keep their stock.
export const stockFields=['onHand','reserved','cost','damagedStock','expiredStock','quarantineStock'];
export function planStockWrite(current,operation){
 if(!current)throw Error('This catalog record no longer exists. Refresh Vendor.');
 const touched=stockFields.filter(k=>Object.hasOwn(operation.fields,k)||operation.removed.includes(k));
 if(!current.productionManaged)return operation.fields;
 if(operation.removed.some(k=>stockFields.includes(k)||['productionManaged','productionSourceId','stockRevision'].includes(k)))throw Error('Production inventory metadata cannot be removed.');
 const revision=current.stockRevision;
 if(!Number.isInteger(revision)||revision<0)throw Error('The Production stock revision needs owner review.');
 if(Object.hasOwn(operation.fields,'productionManaged')||Object.hasOwn(operation.fields,'productionSourceId')||Object.hasOwn(operation.fields,'stockRevision'))throw Error('Production source metadata is managed by the Employee owner service.');
 const changed={...operation.fields};
 for(const key of touched){
  if(!Object.hasOwn(operation.fallback??{},key))throw Error('The stock operation has no reviewed original value.');
  const proposed=Number(operation.fields[key]),before=Number(operation.fallback[key]),live=Number(current[key]??0);
  if(![proposed,before,live].every(Number.isFinite)||Math.min(proposed,before,live)<0)throw Error('Inventory values must be finite and nonnegative.');
  if(key==='cost'){
   if(live!==before)throw Error('Inventory cost changed. Review this cost edit before retrying.');
  }else changed[key]=live+proposed-before;
 }
 if(touched.includes('onHand')&&!touched.includes('cost')){
  const delta=Number(operation.fields.onHand)-Number(operation.fallback.onHand),qty=changed.onHand;
  const value=Number(current.onHand)*Number(current.cost)+delta*Number(operation.fallback.cost);
  if(!Number.isFinite(value)||value< -0.000001)throw Error('Review the captured stock cost before saving this movement.');
  if(qty>0)changed.cost=Math.max(0,value)/qty;
  else if(Math.abs(value)>0.000001)throw Error('A stock-cost variance needs owner review before this last unit can be delivered.');
 }
 if(touched.length)changed.stockRevision=revision+1;
 const onHand=Number(changed.onHand??current.onHand??0),reserved=Number(changed.reserved??current.reserved??0);
 if(onHand<0||reserved<0||reserved>onHand)throw Error('Stock changed and this order would exceed available inventory. Review it before retrying.');
 return changed;
}
