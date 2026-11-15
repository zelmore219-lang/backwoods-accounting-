"""Reviewed Pest billing in the existing company ledger, through Employee's private view."""
import json
from .ledger import AccountingError,canonical,day,now
PROJECT='bugzapper-3397f'
OWNER='o4T4SN4GDlP0I470mhyD77xD9JD3'
def need(ok,message):
 if not ok:raise AccountingError(message)
def amount(value):
 need(type(value) is int and 0<=value<=100_000_000_000,'Invalid Pest integer-cent amount');return value
def settings(ledger):return json.loads(ledger.settings().get('pest_accounting_connection','null'))
def prepare(packet):
 from .imports import line,pair,record
 need(packet.get('schemaVersion')==1 and packet.get('type')=='backwoods-pest-accounting' and packet.get('project')==PROJECT and packet.get('ownerUid')==OWNER and packet.get('department')=='Pest Control','Use the verified Pest billing source from the connected Employee owner service')
 invoices=packet.get('invoices');need(isinstance(invoices,list) and len(invoices)<=30000,'Invalid Pest invoice snapshot')
 docs=[];seen=set()
 for invoice in invoices:
  id_=invoice.get('id');need(isinstance(id_,str) and 0<len(id_)<=160 and id_ not in seen,'Invalid or duplicate Pest invoice ID');seen.add(id_)
  status=invoice.get('status');need(status in {'Open','Partially paid','Paid','Void'},'Only issued or explicitly voided Pest invoices may enter the books')
  subtotal,tax,total,paid=[amount(invoice.get(k)) for k in ['subtotalCents','taxCents','totalCents','paidCents']]
  need(total==subtotal+tax and paid<=total,'Pest invoice totals do not reconcile')
  payments=invoice.get('payments');need(isinstance(payments,list),'Invalid Pest payment history')
  need(sum(amount(p.get('amountCents')) for p in payments)==paid,'Pest payment history does not match its paid total')
  need((status!='Paid' or paid==total) and (status!='Open' or paid==0) and (status!='Partially paid' or 0<paid<total) and (status!='Void' or paid==0),'Pest invoice status and payment history disagree')
  invoice_date=day(str(invoice.get('createdAt') or '')[:10]);party=str(invoice.get('customerName') or '')[:200]
  original={**invoice,'date':invoice_date,'department':'Pest Control','companyId':packet.get('companyId'),'project':PROJECT}
  lines=[] if status=='Void' else [line('1100',total),line('4030',credit=subtotal),line('2100',credit=tax)]
  doc=record('invoice',original,[l for l in lines if l['debit'] or l['credit']],amount=0 if status=='Void' else total,balance=0 if status=='Void' else total-paid,party=party,reference=invoice.get('number') or id_);doc['department']='Pest Control';docs.append(doc)
  for index,p in enumerate(payments):
   need(p.get('method') in {'Cash','Check','External card','External ACH'} and isinstance(p.get('reference'),str) and p['reference'].strip(),'A Pest payment needs its actual method and reference')
   payment={**p,'id':id_+':'+str(index),'date':day(str(p.get('at') or '')[:10]),'invoiceId':id_,'department':'Pest Control','companyId':packet.get('companyId'),'project':PROJECT}
   doc=record('payment',payment,pair('1010' if p['method']=='Cash' else '1030','1100',amount(p['amountCents'])),amount=p['amountCents'],party=party,reference=p['reference']);doc['department']='Pest Control';docs.append(doc)
 return docs,[('4030','Pest Control Service Revenue','income')],['Pest Control department. Recorded cash/check/external payments only; no bank settlement, payment processing, chemical cost or payroll is inferred.']
def available(ledger):return json.loads(ledger.settings().get('pest_accounting_available','null'))
def synchronize(ledger,workspace,packets):
 from . import payroll_management as pm
 connection=pm.settings(ledger);need(connection and connection['workspace']==workspace,'Connect the actual Employee workspace first')
 selected=connection['companies'][0]
 matching=[p for p in packets if p.get('companyId')==selected]
 need(len(matching)<=1,'Multiple Pest sources need owner review')
 if not matching:return None
 packet=matching[0];documents,accounts,warnings=prepare(packet)
 with ledger.db:ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('pest_accounting_available',canonical(packet)))
 bound=settings(ledger)
 if not bound:return {'status':'Review required','invoices':len(packet['invoices']),'department':'Pest Control'}
 need(bound=={'workspace':workspace,'companyId':selected,'project':PROJECT,'ownerUid':OWNER,'department':'Pest Control'},'The reviewed Pest company mapping changed; import stopped')
 current={d['id'] for d in documents}
 old={r[0] for r in ledger.db.execute("SELECT source_id FROM documents WHERE source='pest'")}
 need(old<=current,'A previously imported Pest invoice/payment is missing. Preserve its original source record or review an explicit correction; no deletion was inferred')
 receipt=ledger.import_documents('pest',documents,packet,'Verified Pest Control billing',accounts=accounts)
 with ledger.db:ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('pest_accounting_last_sync',canonical({'at':now(),**receipt,'department':'Pest Control'})))
 return receipt
def connect(ledger,user,workspace,packets,value):
 from . import payroll_management as pm
 pm.require_payroll(user,owner=True);need(value.get('confirmed') is True,'Review the same legal company and Pest Control department before importing')
 connection=pm.settings(ledger);need(connection and connection['workspace']==workspace,'Connect Employee first')
 company=connection['companies'][0];need(value.get('companyId')==company,'The Pest company does not match these existing books')
 packet=next((p for p in packets if p.get('companyId')==company),None);need(packet,'In Pest Control, connect Employee and choose Sync billing to Accounting first')
 prepare(packet)
 binding={'workspace':workspace,'companyId':company,'project':PROJECT,'ownerUid':OWNER,'department':'Pest Control'}
 prior=settings(ledger);need(not prior or prior==binding,'This Pest source is already bound to another company')
 # Add the binding only with the same atomic commit as the first accepted import.
 documents,accounts,warnings=prepare(packet)
 current={d['id'] for d in documents}
 old={r[0] for r in ledger.db.execute("SELECT source_id FROM documents WHERE source='pest'")}
 need(old<=current,'An existing Pest invoice or payment is missing; review an explicit source correction first')
 def save_binding(db):
  ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('pest_accounting_connection',canonical(binding)))
  ledger.audit('pest-accounting-connected',binding)
 result=ledger.import_documents('pest',documents,packet,'Owner-reviewed Pest Control connection',accounts=accounts,commit_hook=save_binding)
 return {**result,'department':'Pest Control','companyId':company}
