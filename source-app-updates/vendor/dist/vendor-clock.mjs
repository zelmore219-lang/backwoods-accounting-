import {createSharedClock} from './shared-clock/ui.mjs';
window.__bwSharedClock=createSharedClock({source:'vendor',context:()=>window.__bwVendorClockContext?.()});
