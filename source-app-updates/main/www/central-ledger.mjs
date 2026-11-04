// Offline central ledger: immutable source records, read-only consolidation.
// No writes to the legacy main app or Firebase.
export const money = value => {
  if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value)>1e12) throw Error('Invalid monetary amount');
  return Math.round(value * 100);
};
const normal = s => String(s || '').trim();
export function normalizeWholesale(journals) {
  if (!Array.isArray(journals)) throw Error('Wholesale journal must be an array');
  return journals.map(j => ({
    id: 'wholesale:' + normal(j.source), source: normal(j.source), date: j.at || '', division: 'wholesale',
    lines: (j.entries || []).map(e => ({account: normal(e.account), debitCents: money(Number(e.debit || 0)), creditCents: money(Number(e.credit || 0))}))
  }));
}
export function normalizeRetailJournals(records) {
  if (!Array.isArray(records)) throw Error('Retail journal must be an array');
  return records.map(j => ({
    id: 'retail:' + normal(j.id), source: normal(j.id), date: j.date || '', division: normal(j.divisionId || j.storeId || 'retail'),
    lines: (j.lines || []).map(e => ({account: normal(e.account), debitCents: money(Number(e.debit || 0)), creditCents: money(Number(e.credit || 0))}))
  }));
}
export function validateLedger(entries) {
  const seen = new Set(), errors = [];
  for (const e of entries) {
    if (!e.id || seen.has(e.id)) errors.push('Duplicate or missing entry ID: '+e.id);
    seen.add(e.id);
    if (!e.lines.length) errors.push('Empty entry: '+e.id);
    let debit=0,credit=0;
    for(const l of e.lines){
      if (!l.account || !Number.isSafeInteger(l.debitCents) || !Number.isSafeInteger(l.creditCents) || l.debitCents<0 || l.creditCents<0 || (l.debitCents && l.creditCents)) errors.push('Invalid line: '+e.id);
      debit += l.debitCents; credit += l.creditCents;
    }
    if(debit !== credit) errors.push('Unbalanced entry: '+e.id);
  }
  return errors;
}
export function consolidate(wholesale, retail=[]) {
  const entries=[...normalizeWholesale(wholesale),...normalizeRetailJournals(retail)];
  const errors=validateLedger(entries);
  const balances=new Map();
  let debit=0,credit=0;
  for(const e of entries)for(const l of e.lines){
    const key=e.division+'\u0000'+l.account;
    const b=balances.get(key)||{division:e.division,account:l.account,debitCents:0,creditCents:0};
    b.debitCents+=l.debitCents;b.creditCents+=l.creditCents;debit+=l.debitCents;credit+=l.creditCents;
    balances.set(key,b);
  }
  return {entries,errors,balances:[...balances.values()].sort((a,b)=>a.division.localeCompare(b.division)||a.account.localeCompare(b.account)),debitCents:debit,creditCents:credit,retailIncluded:retail.length>0};
}
export function parseRetailBackup(text){
  const input=JSON.parse(text);
  const candidates=[input, input.data, input.appData, input.state, input.payload].filter(x=>x&&typeof x==='object');
  const found=candidates.find(x=>Array.isArray(x.journalEntries));
  if(!found) throw Error('No journalEntries array found in the supplied file. No retail entries imported.');
  return found.journalEntries;
}
export function csvLedger(result){
  const q=x=>'"'+String(x??'').replaceAll('"','""')+'"';
  const rows=[['entry_id','date','division','source','account','debit','credit']];
  for(const e of result.entries)for(const l of e.lines)rows.push([e.id,e.date,e.division,e.source,l.account,(l.debitCents/100).toFixed(2),(l.creditCents/100).toFixed(2)]);
  return rows.map(r=>r.map(q).join(',')).join('\r\n');
}
