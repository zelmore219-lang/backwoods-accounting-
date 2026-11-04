import {doc,getDoc} from 'firebase/firestore';
import {loadWholesaleCatalog,watchOrders,submitOrder,confirmPacking,confirmDelivery} from './wholesaleFirestore.mjs';
import {authorize} from './rolePolicy.mjs';
/** Install only from a verified Firebase bootstrap using the same app db/auth. */
export function createWholesaleBridge(db,auth){
 if(!db||!auth)throw Error('Existing Firebase instances required');
 const user=()=>{if(!auth.currentUser?.uid)throw Error('Sign in required');return auth.currentUser};
 async function guard(action){
  const u=user(),snapshot=await getDoc(doc(db,'vendorUsers',u.uid));
  authorize(snapshot.exists()?snapshot.data():null,action,u.uid);
  return u;
 }
 return {
  currentUser:async()=>user(),
  loadWholesaleCatalog:async()=>loadWholesaleCatalog(db,await guard('catalog')),
  watchOrders:(onChange,onError)=>{let unsubscribe=()=>{},cancelled=false;
    guard('catalog').then(u=>{if(!cancelled)unsubscribe=watchOrders(db,u,onChange,onError)}).catch(onError);
    return ()=>{cancelled=true;unsubscribe()};},
  submitOrder:async args=>submitOrder(db,await guard('submitOrder'),args),
  confirmPacking:async args=>confirmPacking(db,await guard('pack'),args),
  confirmDelivery:async args=>confirmDelivery(db,await guard('deliver'),args)
 };
}
