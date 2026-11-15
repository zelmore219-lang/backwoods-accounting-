import copy, importlib.util, json, os, sqlite3, sys, tempfile, unittest, uuid
from pathlib import Path
from unittest.mock import patch
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'production'))
import finance, operations, connected, server as production
from accounting.ledger import Ledger, AccountingError
from accounting.server import Application
from accounting.imports import production_import,vendor_import

class ProductionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=production.DB;production.DB=Path(self.tmp.name)/'production.db';production.initialize()
  self.c=production.connect();self.books=Application(Path(self.tmp.name)/'accounting')
 def tearDown(self):self.c.close();production.DB=self.old;self.tmp.cleanup()
 def act(self,kind,data):
  data=copy.deepcopy(data);event=str(uuid.uuid4())
  with self.c:
   self.c.execute('BEGIN IMMEDIATE');before=finance.positions(self.c);production.apply(self.c,kind,data,event)
   if finance.setting(self.c,'baseline'):finance.capture(self.c,event,kind,before);finance.queue_releases(self.c,event)
  return event
 def last(self,kind):return self.c.execute('SELECT id FROM records WHERE kind=? ORDER BY rowid DESC',(kind,)).fetchone()[0]
 def receive(self):
  self.act('suppliers',{'name':'Actual supplier'});supplier=self.last('suppliers')
  self.act('materials',{'name':'Peanuts','unit':'lb','quantity':0,'cost':0});material=self.last('materials')
  self.act('receive_supplies',{'name':'R-1','supplier':supplier,'material':material,'quantity':100,'invoice_total':200,'freight':20,'lot':'RAW-1'})
  return material
 def make(self,material):
  self.act('recipe_versions',{'name':'Original','version':'1','batch_size':10,'expected_yield':8,'lines':[{'material':material,'quantity':10,'unit':'lb'}]});recipe=self.last('recipes')
  self.act('approve_recipe',{'id':recipe})
  self.act('manufacture',{'recipe':recipe,'scale':1,'output':8,'packages':16,'sku':'PEA-8','lot':'FIN-1','labor':5,'overhead':3})
  return self.last('batches')
 def post(self):
  p=finance.packet(self.c);return self.books.process({'source':'production','payload':p})
 def balances(self):
  ledger=self.books.ledger()
  try:return {r['code']:r['balance'] for r in ledger.report()['trial']}
  finally:ledger.close()
 def test_complete_materials_manufacturing_release_and_vendor_sale_post_once(self):
  with self.c:finance.baseline(self.c)
  material=self.receive();batch=self.make(material)
  self.post();b=self.balances();self.assertEqual(b['1240'],19800);self.assertEqual(b['1260'],3000);self.assertEqual(b['2010'],-22000);self.assertEqual(b['5930'],-800)
  self.act('quality',{'id':batch,'status':'Approved','notes':'Checked'})
  with self.c:self.c.execute('INSERT INTO production_mappings VALUES(?,?,?)',('PEA-8','vendor-product',.5))
  self.act('quality',{'id':batch,'status':'Released for sale','notes':'Ready'})
  after=operations.get(self.c,batch);self.assertEqual(operations.available_finished_units(after),0)
  transfer=self.c.execute('SELECT * FROM integration_transfers').fetchone();self.assertEqual(json.loads(transfer['payload'])['quantity'],16)
  self.post();b=self.balances();self.assertEqual(b['1200'],3000);self.assertEqual(b['1260'],0)
  self.assertEqual(self.post()['added'],0)
  ledger=self.books.ledger()
  try:
   catalog=[json.loads(r[0]) for r in ledger.db.execute("SELECT payload FROM catalog WHERE source='production'")]
   self.assertEqual(next(r for r in catalog if r['sku']=='PEA-8')['onHand'],0)
   self.assertEqual(next(r for r in catalog if r['name']=='Peanuts')['onHand'],90)
  finally:ledger.close()
  vendor={'data':{'orders':[{'id':'sale','status':'delivered','createdAt':date.today().isoformat(),'items':[{'qty':4,'price':4}]}],'products':[{'id':'vendor-product','cost':1.875}],'inventoryMovements':[{'id':'receipt','type':'production_transfer','productionTransferId':transfer['id'],'quantity':16,'unitCost':1.875,'date':date.today().isoformat()},{'id':'delivery','type':'delivery','quantity':-4,'unitCost':1.875,'date':date.today().isoformat()}]}}
  self.books.process({'source':'vendor','payload':vendor});self.books.process({'source':'vendor','payload':vendor})
  b=self.balances();self.assertEqual(b['1200'],2250);self.assertEqual(b['5000'],750);self.assertEqual(b['4000'],-1600)
  self.assertFalse(any(k in b for k in ['1010','1020','1030']))
  with self.assertRaises(ValueError):self.act('reserve',{'batch':batch,'quantity':1,'reference':'double-sale'})
 def test_bulk_packaging_preserves_cost_and_held_lots_do_not_transfer(self):
  material=self.receive()
  with self.c:finance.baseline(self.c)
  self.act('recipe_versions',{'name':'Bulk peanuts','version':'1','batch_size':10,'expected_yield':8,'lines':[{'material':material,'quantity':10,'unit':'lb'}]});recipe=self.last('recipes')
  self.act('approve_recipe',{'id':recipe})
  self.act('manufacture',{'recipe':recipe,'scale':1,'output':8,'packages':1,'bulk':True,'sku':'BULK','lot':'BULK-1','labor':5,'overhead':3});bulk=self.last('batches')
  self.act('quality',{'id':bulk,'status':'Approved','notes':'Bulk checked'})
  self.act('package_inventory',{'batch':bulk,'packages':8,'weight_per_package':.5,'sku':'PEA-8','lot':'PACK-1','labor':2,'packaging_cost':1});batch=self.last('batches')
  self.act('quality',{'id':batch,'status':'Quarantined','notes':'Hold'})
  with self.c:
   self.c.execute('INSERT INTO production_mappings VALUES(?,?,?)',('PEA-8','p',.5));finance.queue_releases(self.c,'held')
  self.assertEqual(self.c.execute('SELECT count(*) FROM integration_transfers').fetchone()[0],0)
  self.post();self.assertEqual(self.balances()['1260'],3300)
  self.act('quality',{'id':batch,'status':'Approved','notes':'Resolved'})
  self.act('quality',{'id':batch,'status':'Released for sale','notes':'Released'})
  self.post();b=self.balances();self.assertEqual(b['1260'],1500);self.assertEqual(b['1200'],1800);self.assertEqual(b['5930'],-1100)
  payload=json.loads(self.c.execute('SELECT payload FROM integration_transfers').fetchone()[0]);self.assertEqual(payload['capacity'],8)
 def test_failed_stock_operation_rolls_back_journal_and_quantity(self):
  material=self.receive()
  with self.c:finance.baseline(self.c)
  before=finance.packet(self.c)
  with self.assertRaises(ValueError):self.act('adjust',{'material':material,'quantity':-101,'lot':'RAW-1','reason':'bad'})
  self.assertEqual(before,finance.packet(self.c));self.assertEqual(operations.get(self.c,material)['quantity'],100)
 def test_invoice_approval_reclassifies_receipt_without_second_inventory_debit(self):
  with self.c:finance.baseline(self.c)
  self.receive();purchase=self.last('purchases')
  self.act('invoices',{'purchase':purchase,'number':'SUP-1','amount':220});invoice=self.last('invoices')
  self.act('approve_invoice',{'id':invoice});self.post();b=self.balances()
  self.assertEqual(b['1240'],22000);self.assertEqual(b['2010'],0);self.assertEqual(b['2000'],-22000)
  ledger=self.books.ledger()
  try:self.assertEqual([d['balance'] for d in ledger.summary()['documents'] if d['kind']=='production-payable'],[22000])
  finally:ledger.close()
 def test_unbalanced_cents_and_missing_prior_event_are_rejected(self):
  with self.c:finance.baseline(self.c)
  self.receive();self.post();p=finance.packet(self.c);bad=copy.deepcopy(p);bad['data']['productionJournals'][0]['lines'][0]['debit']+=1
  with self.assertRaises(AccountingError):self.books.process({'source':'production','payload':bad})
  p['data']['productionJournals']=[]
  with self.assertRaisesRegex(AccountingError,'absent'):self.books.process({'source':'production','payload':p})
 def test_unsigned_sync_worker_retains_status_without_crashing(self):
  import sync
  with patch.object(sync,'TOKEN',None):self.assertIsInstance(sync.run(production.connect),dict)
 def test_completed_packaged_release_matches_exact_vendor_sku_in_background(self):
  with self.c:finance.baseline(self.c)
  material=self.receive();batch=self.make(material)
  self.act('quality',{'id':batch,'status':'Approved','notes':'Inspected'})
  self.act('quality',{'id':batch,'status':'Released for sale','notes':'Ready for sale'})
  self.assertEqual(self.c.execute('SELECT count(*) FROM integration_transfers').fetchone()[0],0)
  with self.c:finance.map_new_releases(self.c,[{'id':'exact','sku':'PEA-8','unit':'each','name':'Packaged peanuts'}])
  payload=json.loads(self.c.execute('SELECT payload FROM integration_transfers').fetchone()[0])
  self.assertEqual((payload['quantity'],payload['lot'],payload['productId']),(16,'FIN-1','exact'))
  self.assertEqual(operations.available_finished_units(operations.get(self.c,batch)),0)
  with self.c:finance.map_new_releases(self.c,[{'id':'exact','sku':'PEA-8','unit':'each'}])
  self.assertEqual(self.c.execute('SELECT count(*) FROM integration_transfers').fetchone()[0],1)
 def test_existing_opening_stock_and_ambiguous_skus_need_review_before_transfer(self):
  material=self.receive();batch=self.make(material)
  self.act('quality',{'id':batch,'status':'Approved','notes':'Inspected'})
  self.act('quality',{'id':batch,'status':'Released for sale','notes':'Ready for sale'})
  with self.c:
   finance.baseline(self.c)
   finance.map_new_releases(self.c,[{'id':'existing','sku':'PEA-8','unit':'each'}])
  self.assertEqual(self.c.execute('SELECT count(*) FROM integration_transfers').fetchone()[0],0)
  self.assertEqual(operations.available_finished_units(operations.get(self.c,batch)),16)
 def test_wrong_package_mapping_does_not_undo_normal_release_or_transfer_wrong_count(self):
  with self.c:finance.baseline(self.c)
  material=self.receive();batch=self.make(material)
  with self.c:self.c.execute('INSERT INTO production_mappings VALUES(?,?,?)',('PEA-8','wrong-size',1))
  self.act('quality',{'id':batch,'status':'Approved','notes':'Inspected'})
  self.act('quality',{'id':batch,'status':'Released for sale','notes':'Ready for sale'})
  self.assertEqual(operations.get(self.c,batch)['status'],'Released for sale')
  self.assertEqual(self.c.execute('SELECT count(*) FROM integration_transfers').fetchone()[0],0)
  status=finance.connection_status(self.c,{})
  self.assertEqual(status,{'connected':False})
 def test_employee_role_company_revocation_and_activation_are_checked_each_request(self):
  claims={'aud':connected.PROJECT,'iss':'https://securetoken.google.com/'+connected.PROJECT,'auth_time':200}
  import base64,time
  token='x.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.y'
  credentials={'uid':'employee','token':token,'company':'company','username':'realuser','expires':time.time()+1000,'sessionExpires':time.time()+1000}
  profile={'uid':'employee','employeeId':'person','name':'Real Person','companyId':'company','username':'realuser','accountActive':True,'employmentStatus':'active','mustChangePassword':False,'passwordValidAfter':0,'applications':{'production':'production_employee'}}
  def http(url,*args,**kwargs):
   if 'accounts:lookup' in url:return {'users':[{'localId':'employee','validSince':'0'}]}
   def enc(v):
    if isinstance(v,bool):return {'booleanValue':v}
    if isinstance(v,int):return {'integerValue':str(v)}
    if isinstance(v,dict):return {'mapValue':{'fields':{k:enc(x) for k,x in v.items()}}}
    return {'stringValue':v}
   return {'fields':{k:enc(v) for k,v in profile.items()}}
  with patch.object(connected,'http',http):
   self.assertEqual(connected.access(credentials)['role'],'operator')
   for key,value in [('employmentStatus','inactive'),('mustChangePassword',True),('companyId','other'),('passwordValidAfter',201)]:
    previous=profile[key];profile[key]=value
    with self.assertRaises(ValueError):connected.access(credentials)
    profile[key]=previous
   profile['applications']={}
   with self.assertRaises(ValueError):connected.access(credentials)

if __name__=='__main__':unittest.main()
