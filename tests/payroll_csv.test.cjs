const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const modulePromise=import('data:text/javascript;base64,'+fs.readFileSync(require('node:path').join(__dirname,'../web/payroll-management.js')).toString('base64'));
const header='batchId,entryId,employee,department,gross,employeeTaxes,deductions,netPay,reimbursement,employerTaxes,employerBenefits,fees\r\n';
test('actual-result CSV keeps quoted identities, quoted newlines and dollar amounts',async()=>{
 const {parseResultCsv}=await modulePromise;
 const rows=parseResultCsv('\uFEFF'+header+'batch,0,"O\'Brien, Jo","Wholesale\nPacking",762.50,100,0,662.50,0,50,0,2.50\r\n');
 assert.equal(rows.length,1);assert.equal(rows[0].employee,"O'Brien, Jo");assert.equal(rows[0].department,'Wholesale\nPacking');assert.equal(rows[0].gross,'762.50');
});
test('result template rejects private/wrong columns and incomplete quoting',async()=>{
 const {parseResultCsv}=await modulePromise;
 assert.throws(()=>parseResultCsv(header.replace('gross,','ssn,')),/template/);
 assert.throws(()=>parseResultCsv(header+'batch,0,"unfinished'),/unfinished/);
 assert.throws(()=>parseResultCsv(header+'batch,0,Too few'),/columns/);
});
test('spreadsheet-safe identity comparison preserves legitimate apostrophes',async()=>{
 const {safeCsvIdentity}=await modulePromise;
 assert.equal(safeCsvIdentity("'Jo"),"'Jo");assert.equal(safeCsvIdentity('=SUM(1,2)'),"'=SUM(1,2)");assert.equal(safeCsvIdentity(' +Example'),"' +Example");
});
