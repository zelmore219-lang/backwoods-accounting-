import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {receiptText,receiptBusiness,printDocument} from '../www/receipt.mjs';
import printer from '../electron/receipt-printer.cjs';
const data={settings:{businessName:'Backwoods Brew'},stores:[{id:1,name:'Oxford',address:'123 Test Street',city:'Oxford',state:'AL',zip:'36203'}]};
const sale={id:'sale-1',storeId:1,createdAt:'2026-11-10T15:30:00Z',cashier:'Test cashier',items:[{name:'Latte <large>',qty:2,unitPrice:5.5,lineTotal:11}],subtotal:11,discountAmount:1,tax:1,total:11,paymentType:'Cash',amountTendered:20,changeDue:9};
test('saved quantity, prices, discounts, tax and cash amounts render completely',()=>{
  const text=receiptText(data,sale);
  for(const value of ['Backwoods Brew','Oxford','123 Test Street','Receipt #sale-1','Cashier: Test cashier','Latte <large>','2 x $5.50 = $11.00','Subtotal: $11.00','Discount: -$1.00','Sales tax: $1.00','TOTAL: $11.00','Payment: Cash','Tendered: $20.00','Change: $9.00'])assert(text.includes(value),value);
});
test('receipt snapshots and historic extended prices survive catalog and location changes',()=>{
  const snapshot=receiptBusiness(data,sale),changed={settings:{businessName:'New name'},stores:[{id:1,name:'New location'}],products:[{price:999}]};
  const text=receiptText(changed,{...sale,receiptBusiness:snapshot,items:[{name:'Historic product',quantity:3,price:999,lineTotal:12}]});
  assert(text.includes('Oxford'));assert(text.includes('3 x $4.00 = $12.00'));assert(!text.includes('999'));
});
test('zero line totals and missing historic cash data do not fabricate amounts',()=>{
  const text=receiptText(data,{...sale,amountTendered:undefined,changeDue:undefined,items:[{name:'Free item',price:5,lineTotal:0}]});
  assert(text.includes('1 x $0.00 = $0.00'));assert(text.includes('Tendered: Not recorded'));
  assert.throws(()=>receiptText(data,{}),/saved transaction/);assert.throws(()=>printDocument('Receipt',''),/no recorded content/);
});
test('HTML escapes all receipt content and never needs inline JavaScript',()=>{
  const html=printDocument('Receipt <test>','<script>alert(1)</script> & $11.00');
  assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>'));assert(html.includes('72mm'));
  const native=printer.documentForReceipt({title:'Receipt',text:'<img src=x onerror=alert(1)>\nTOTAL $11.00'});
  assert(native.includes('&lt;img'));assert(native.includes('TOTAL $11.00'));assert.throws(()=>printer.documentForReceipt({}),/nonempty/);
});
test('native printing waits for document rendering and uses the originating window',async()=>{
  let handle;const calls=[];const parent={webContents:{mainFrame:{}}};
  class Window{constructor(options){assert.equal(options.webPreferences.sandbox,true);assert.equal(options.parent,parent);this.webContents={setWindowOpenHandler(){},executeJavaScript:async()=>calls.push('rendered'),print:(options,done)=>{assert.equal(options.silent,false);calls.push('printed');done(false,'cancelled');}};}
    static fromWebContents(){return parent;}async loadURL(url){assert(url.startsWith('data:text/html'));calls.push('loaded');}isDestroyed(){return false;}destroy(){calls.push('closed');}}
  printer.registerReceiptPrinter({ipcMain:{handle:(channel,handler)=>{assert.equal(channel,'print-receipt');handle=handler;}},BrowserWindow:Window});
  const result=await handle({sender:{},senderFrame:parent.webContents.mainFrame},{title:'Receipt',text:'Sale 1\nTOTAL $11.00'});
  assert.equal(result.error,'cancelled');assert.deepEqual(calls,['loaded','rendered','printed','closed']);
  await assert.rejects(handle({sender:{},senderFrame:{}},{text:'test'}),/Main app window/);
});
test('username authentication, inventory deductions, ledger and synchronization remain byte-identical',()=>{
  const code=fs.readFileSync(new URL('../www/assets/main-CnsZnSKS.js',import.meta.url),'utf8');
  const baseline=JSON.parse(fs.readFileSync(new URL('./unchanged-core.json',import.meta.url),'utf8'));
  for(const [name,hash] of Object.entries(baseline)){
    const start=code.indexOf('function '+name+'('),next=/\n(?:function |const )/.exec(code.slice(start+1));
    assert(start>=0&&next,name);const block=code.slice(start,start+1+next.index);
    assert.equal(createHash('sha256').update(block).digest('hex'),hash,name+' changed outside the receipt repair');
  }
});
