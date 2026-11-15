"""Event journals in integer cents; source records remain in Production."""
import json, uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

ACCOUNTS=[('1200','Vendor Inventory','asset'),('1240','Production Materials','asset'),('1250','Work in Process','asset'),('1260','Production Finished Goods','asset'),('1150','Supplier Credits Receivable','asset'),('2000','Accounts Payable','liability'),('2010','Production Received Not Invoiced','liability'),('3100','Opening Balance Equity','equity'),('5190','Production Inventory Variance','expense'),('5930','Capitalized Production Cost Recovery','expense')]

def cents(value):
 n=Decimal(str(value))
 if not n.is_finite():raise ValueError('Invalid production value')
 return int((n*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def initialize(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS integration_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS production_journals(id TEXT PRIMARY KEY,date TEXT NOT NULL,memo TEXT NOT NULL,lines TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS integration_transfers(id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL,receipt TEXT);
 CREATE TABLE IF NOT EXISTS production_mappings(sku TEXT PRIMARY KEY,product_id TEXT NOT NULL,weight REAL NOT NULL CHECK(weight>0));''')
 if not setting(c,'source_id'):c.execute('INSERT INTO integration_settings VALUES(?,?)',('source_id',str(uuid.uuid4())))
 c.commit()

def setting(c,key,default=None):
 r=c.execute('SELECT value FROM integration_settings WHERE key=?',(key,)).fetchone()
 return r[0] if r else default

def set_setting(c,key,value):c.execute('INSERT OR REPLACE INTO integration_settings VALUES(?,?)',(key,str(value)))

def positions(c):
 result={'1240':sum(Decimal(str(r['quantity']))*Decimal(str(r['cost'])) for r in c.execute('SELECT quantity,cost FROM lots')),'1250':Decimal(0),'1260':Decimal(0),'2000':Decimal(0),'2010':Decimal(0)}
 for row in c.execute("SELECT kind,data FROM records WHERE kind IN ('batches','purchases','invoices')"):
  b=json.loads(row['data'])
  if row['kind']=='batches':
   if b['status']=='In Production':result['1250']+=Decimal(str(sum(i['cost'] for i in b.get('inputs',[]))))
   else:
    remaining=Decimal(str(b.get('packages',0)))-sum((Decimal(str(b.get(k,0))) for k in ['delivered','written_off','converted_units','vendor_transferred']),Decimal(0))+Decimal(str(b.get('returned',0)))
    if remaining<Decimal('-0.000001'):raise ValueError('Production lot has inconsistent physical stock')
    if b.get('packages'):result['1260']+=max(Decimal(0),remaining)*Decimal(str(b['total']))/Decimal(str(b['packages']))
  elif row['kind']=='purchases':
   qty=Decimal(str(b.get('received',0)))
   if qty:result['2010']-=qty*(Decimal(str(b['cost']))+Decimal(str(b.get('freight',0)))/Decimal(str(b['quantity'])))
  elif b.get('status')=='Approved':
   amount=Decimal(str(b['amount']));result['2000']-=amount;result['2010']+=amount
 return {k:cents(v) for k,v in result.items()}

def journal(c,event,memo,changes,offset=None):
 changes={k:v for k,v in changes.items() if v}
 total=sum(changes.values())
 if total:
  if not offset:raise ValueError('Production journal needs a reviewed offset')
  changes[offset]=changes.get(offset,0)-total
 lines=[{'account':k,'debit':max(v,0),'credit':max(-v,0)} for k,v in changes.items() if v]
 if lines:c.execute('INSERT INTO production_journals VALUES(?,?,?,?)',(event,date.today().isoformat(),memo,json.dumps(lines)))

def baseline(c):
 if setting(c,'baseline'):return
 journal(c,'opening:'+setting(c,'source_id'),'Reviewed Production opening balances',positions(c),'3100')
 set_setting(c,'baseline','1');set_setting(c,'baseline_date',date.today().isoformat())

def capture(c,event,kind,before):
 after=positions(c);changes={k:after[k]-before[k] for k in after}
 if kind in {'manufacture','start_batch','complete_batch','edit_batch','package_inventory'}:offset='5930'
 elif kind=='supplier_returns':offset='1150'
 elif kind=='materials':offset='3100'
 else:offset='5190'
 journal(c,event,'Production '+kind,changes,offset)

def queue_releases(c,event):
 from operations import available_finished_units
 from datetime import date
 for row in c.execute("SELECT id,data FROM records WHERE kind='batches'").fetchall():
  b=json.loads(row['data'])
  if b['status']!='Released for sale' or b.get('bulk') or (b.get('best_by') and b['best_by']<date.today().isoformat()):continue
  q=available_finished_units(b)
  if q<=0:continue
  mapping=c.execute('SELECT * FROM production_mappings WHERE sku=?',(b.get('sku'),)).fetchone()
  if not mapping:continue
  if abs(float(mapping['weight'])-float(b['output'])/float(b['packages']))>1e-8:raise ValueError('The package weight differs from this SKU mapping')
  if int(q)!=q:raise ValueError('Only whole finished packages can transfer to Vendor')
  transfer_id=str(uuid.uuid5(uuid.NAMESPACE_URL,setting(c,'source_id')+':'+row['id']+':'+event))
  payload={'id':transfer_id,'sourceId':setting(c,'source_id'),'batchId':row['id'],'sku':b['sku'],'lot':b['lot'],'bestBy':b.get('best_by',''),'productId':mapping['product_id'],'quantity':int(q),'unitCost':str(Decimal(str(b['total']))/Decimal(str(b['packages']))),'weightLb':str(mapping['weight']),'createdAt':datetime.now(timezone.utc).isoformat()}
  c.execute('INSERT INTO integration_transfers VALUES(?,?,?,NULL)',(transfer_id,json.dumps(payload),'pending'))
  b['vendor_transferred']=float(b.get('vendor_transferred',0))+q
  c.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(b),row['id']))
  # Warehouse ownership changes; a transfer is neither a purchase nor a sale.
  amount=cents(Decimal(str(b['total']))*Decimal(str(q))/Decimal(str(b['packages'])))
  journal(c,'transfer:'+transfer_id,'Finished lot '+b['lot']+' transferred to Vendor',{'1200':amount,'1260':-amount})

def packet(c):
 journals=[{'id':r['id'],'date':r['date'],'memo':r['memo'],'lines':json.loads(r['lines'])} for r in c.execute('SELECT * FROM production_journals ORDER BY rowid')]
 records=[{'id':r['id'],'kind':r['kind'],'data':json.loads(r['data'])} for r in c.execute('SELECT * FROM records WHERE kind NOT IN (\'outbox\') ORDER BY rowid')]
 records.extend({'id':'lot:'+r['id'],'kind':'material-lot','data':dict(r)} for r in c.execute('SELECT * FROM lots ORDER BY rowid'))
 records.extend({'id':'event:'+r['id'],'kind':'production-event','data':{'operation':r['kind'],'date':r['created'][:10],'created':r['created'],'data':json.loads(r['data'])}} for r in c.execute('SELECT * FROM events ORDER BY rowid'))
 # No personnel table, login/session data or secrets are exported.
 return {'schemaVersion':1,'type':'business-accounting-feed','app':'Backwoods Production','data':{'sourceId':setting(c,'source_id'),'baselineDate':setting(c,'baseline_date'),'productionJournals':journals,'productionRecords':records}}
