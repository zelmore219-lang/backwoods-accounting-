import {createSharedClock} from './ui.mjs';
window.__bwSharedClock=createSharedClock({source:'main',context:()=>window.__bwSharedClockContext?.()});
