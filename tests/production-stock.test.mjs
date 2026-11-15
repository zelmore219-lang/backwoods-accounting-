import test from 'node:test';import assert from 'node:assert/strict';
import {planStockWrite} from '../source-app-updates/vendor/dist/production-stock.mjs';
const current={productionManaged:true,productionSourceId:'source',stockRevision:4,onHand:100,reserved:20,cost:2};
test('a simultaneous delivery preserves received Production stock and historical cost',()=>{
 const change=planStockWrite({...current,cost:2.6},{fields:{onHand:50},fallback:{onHand:60,cost:2},removed:[]});
 assert.equal(change.onHand,90);assert.equal(change.stockRevision,5);assert.ok(Math.abs(change.cost-240/90)<1e-10);
});
test('a current reviewed sale advances the stock revision once',()=>{
 assert.deepEqual(planStockWrite(current,{fields:{onHand:80},fallback:{...current},removed:[]}),{onHand:80,cost:2,stockRevision:5});
});
test('catalog-only changes preserve stock revision',()=>{
 assert.deepEqual(planStockWrite(current,{fields:{price:4},fallback:{...current},removed:[]}),{price:4});
});
test('overdraw, missing originals, cost conflicts and metadata edits stop the sync queue',()=>{
 for(const operation of [{fields:{onHand:10},fallback:{...current}},{fields:{reserved:101},fallback:{...current}},{fields:{cost:4},fallback:{...current,cost:1}},{fields:{stockRevision:5},fallback:current},{fields:{onHand:50},fallback:{}},{fields:{cost:NaN},fallback:current}])assert.throws(()=>planStockWrite(current,{...operation,removed:[]}));
});
