import copy,json,tempfile,unittest
from pathlib import Path
from accounting import pest,payroll_management as pm
from accounting.ledger import Ledger,AccountingError,canonical
def packet():return {'schemaVersion':1,'type':'backwoods-pest-accounting','project':pest.PROJECT,'ownerUid':pest.OWNER,'companyId':'backwoods','department':'Pest Control','invoices':[{'id':'pest-1','number':'P-1','customerId':'customer-1','customerName':'Fictitious Pest customer','subtotalCents':10000,'taxCents':800,'totalCents':10800,'paidCents':4000,'createdAt':'2026-11-01T12:00:00Z','due':'2026-12-01','status':'Partially paid','payments':[{'amountCents':4000,'method':'Check','reference':'Fictional check 100','at':'2026-11-02T12:00:00Z'}]}]}
class PestAccountingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'books.sqlite3')
  with self.ledger.db:self.ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('employee_payroll_connection',canonical({'workspace':'reviewed-workspace','companies':['backwoods']})))
 def tearDown(self):self.ledger.close();self.temp.cleanup()
 def connect(self,p=None,**extra):return pest.connect(self.ledger,{'role':'owner'},'reviewed-workspace',[p or packet()],{'companyId':'backwoods','confirmed':True,**extra})
 def test_same_company_department_and_payment_import_once_without_inventing_bank_settlement(self):
  self.assertIsNone(pest.settings(self.ledger));pest.synchronize(self.ledger,'reviewed-workspace',[packet()]);self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM entries WHERE source='pest'").fetchone()[0],0)
  first=self.connect();self.assertEqual(first['added'],2);pest.synchronize(self.ledger,'reviewed-workspace',[packet()]);self.connect()
  self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM documents WHERE source='pest'").fetchone()[0],2)
  balances={a['code']:a['balance'] for a in self.ledger.report()['trial']};self.assertEqual(balances['1100'],6800);self.assertEqual(balances['1030'],4000);self.assertEqual(balances.get('1020',0),0)
  for row in self.ledger.db.execute("SELECT payload FROM documents WHERE source='pest'"):self.assertEqual(json.loads(row[0])['department'],'Pest Control')
 def test_explicit_unpaid_void_reverses_the_original_invoice_once(self):
  p=packet();p['invoices'][0].update(status='Open',paidCents=0,payments=[]);self.connect(p)
  p['invoices'][0]['status']='Void';pest.synchronize(self.ledger,'reviewed-workspace',[p]);pest.synchronize(self.ledger,'reviewed-workspace',[p])
  doc=self.ledger.db.execute("SELECT balance FROM documents WHERE source='pest'").fetchone();self.assertEqual(doc[0],0)
  self.assertEqual(next(a for a in self.ledger.report()['trial'] if a['code']=='1100')['balance'],0)
 def test_missing_invoice_or_payment_does_not_silently_erase_history(self):
  self.connect();p=packet();p['invoices']=[]
  with self.assertRaises(AccountingError):pest.synchronize(self.ledger,'reviewed-workspace',[p])
  with self.assertRaises(AccountingError):self.connect(p)
 def test_wrong_company_unconfirmed_or_nonowner_cannot_connect(self):
  for value in [{'companyId':'another'},{'confirmed':False}]:
   with self.assertRaises(AccountingError):self.connect(**value)
  with self.assertRaises(AccountingError):pest.connect(self.ledger,{'role':'accountant'},'reviewed-workspace',[packet()],{'companyId':'backwoods','confirmed':True})
 def test_malformed_totals_duplicate_ids_or_unverified_source_are_rejected_atomically(self):
  for change in ['totals','duplicate','project']:
   p=packet()
   if change=='totals':p['invoices'][0]['totalCents']+=1
   elif change=='duplicate':p['invoices'].append(copy.deepcopy(p['invoices'][0]))
   else:p['project']='another-project'
   with self.assertRaises(AccountingError):self.connect(p)
  self.assertIsNone(pest.settings(self.ledger));self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM entries WHERE source='pest'").fetchone()[0],0)
