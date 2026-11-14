import copy,json,tempfile,unittest
from pathlib import Path
from accounting.imports import prepare,sanitize_payload,record,pair
from accounting.ledger import Ledger,AccountingError

def packet():
 return {'schemaVersion':1,'type':'backwoods-employee-time','source':'employees','exportId':'fixture-export',
  'company':{'id':'backwoods','name':'Fictional Company'},'start':'2026-10-19','endExclusive':'2026-10-26',
  'timesheets':[{'id':'sheet-1','employeeId':'existing-hr-id','employeeNumber':'FIX-1','employee':'Fictional Employee','start':'2026-10-19','endExclusive':'2026-10-26','status':'approved','approvedBy':'reviewer-id','approvedAt':'2026-10-27T08:00:00Z','sourceHash':'a'*64,
   'assignments':[{'assignmentId':'job-1','departmentId':'delivery','department':'Delivery','location':'Fictional depot','payType':'hourly','rateCents':2000,'regularMinutes':'2400','overtimeMinutes':'300','regularCents':80000,'overtimeCents':15000,'estimatedGrossCents':95000}]}],
  'timeOff':[{'id':'leave-1','employeeId':'existing-hr-id','employeeNumber':'FIX-1','employee':'Fictional Employee','kind':'vacation','start':'2026-10-25T08:00:00Z','end':'2026-10-25T16:00:00Z','status':'approved','approvedBy':'reviewer-id','paidMinutes':480,'assignmentId':'job-1','departmentId':'delivery','department':'Delivery','payType':'hourly','rateCents':2000}], 'departments':[]}

class EmployeeTimeImportTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'books.sqlite3')
 def tearDown(self):self.ledger.close();self.temp.cleanup()
 def load(self,value,preview=False):
  clean=sanitize_payload(value,'employees');documents,accounts,warnings=prepare(clean,'employees')
  return self.ledger.import_documents('employees',documents,clean,preview=preview)
 def test_approved_hours_and_pto_preview_import_and_retry_never_post_or_duplicate(self):
  value=packet();self.assertEqual(self.load(value,True)['added'],2);self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0)
  self.assertEqual(self.load(value)['added'],2);self.assertEqual(self.load(value)['duplicates'],2)
  self.assertEqual(self.ledger.rows(),[]);self.assertEqual(self.ledger.report()['profit'],0)
  document=json.loads(self.ledger.db.execute("SELECT payload FROM documents WHERE kind='employee-timesheet'").fetchone()[0])
  self.assertEqual(document['original']['record']['assignments'][0]['departmentId'],'delivery')
  another=packet();another['timesheets'][0]['id']='sheet-2';another['timesheets'][0]['start']='2026-10-26';another['timesheets'][0]['endExclusive']='2026-11-02';another.update(start='2026-10-26',endExclusive='2026-11-02',timeOff=[])
  self.assertEqual(self.load(another)['added'],1);self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],3)
 def test_pending_unauthorized_missing_mapping_and_bad_wage_totals_fail_before_writes(self):
  for change in ['pending','approver','mapping','gross']:
   value=packet();sheet=value['timesheets'][0]
   if change=='pending':sheet['status']='submitted'
   if change=='approver':sheet['approvedBy']=''
   if change=='mapping':sheet['assignments'][0]['departmentId']=''
   if change=='gross':sheet['assignments'][0]['estimatedGrossCents']=100
   with self.assertRaises(AccountingError):self.load(value)
  self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0)
 def test_only_employee_source_accepts_time_packet_and_no_personnel_secrets_are_retained(self):
  value=packet();value['password']='secret';value['timesheets'][0]['ssn']='must-not-retain'
  clean=sanitize_payload(value,'employees');self.assertNotIn('password',clean);self.assertNotIn('ssn',clean['timesheets'][0])
  with self.assertRaises(AccountingError):prepare(value,'main')
 def test_import_preserves_existing_books_and_rejects_overlapping_or_other_company_records(self):
  expense=record('expense',{'id':'keep','date':'2026-10-18'},pair('5100','1020',1250))
  self.ledger.import_documents('manual',[expense],{'fixture':True});before=self.ledger.rows()
  self.load(packet());self.assertEqual(self.ledger.rows(),before);self.assertEqual(self.ledger.report()['profit'],-1250)
  overlap=packet();overlap['timesheets'][0]['id']='another-id-for-the-same-period'
  with self.assertRaises(AccountingError):self.load(overlap)
  other=packet();other['company']['id']='another-company';other['timesheets'][0]['id']='different-company-sheet'
  with self.assertRaises(AccountingError):self.load(other)
 def test_viewer_cannot_print_private_employee_pay_records(self):
  from accounting.printing import render
  self.load(packet())
  with self.assertRaises(AccountingError):render(self.ledger,{'type':'document','source':'employees','id':'employee-timesheet:sheet-1'},{'role':'viewer','name':'Fixture reader'})
