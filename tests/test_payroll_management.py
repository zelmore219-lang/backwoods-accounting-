import copy,csv,io,json,sqlite3,tempfile,unittest,uuid,zipfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree
from accounting import payroll_management as pm
from accounting.ledger import Ledger,AccountingError

def roster(packets=None):
 return {'schemaVersion':1,'type':'backwoods-employee-payroll-feed','project':'fixture-only','companies':[{'id':'backwoods','name':'Fictional Backwoods'}],
  'employees':[{'id':'staff-1','firebase_uid':'same-existing-uid','username':'fixture.staff','name':'Fictional Employee','employee_number':'FIX-1','company_id':'backwoods','status':'active',
   'jobs':[{'id':'job-1','division_id':'wholesale','division_name':'Wholesale','location_id':'wholesale-main','location_name':'Fictional warehouse','title':'Packer','pay_type':'hourly','rate_cents':1500,'effective_date':'2020-01-01','end_date':None,'timezone':'America/Chicago'}]}],
  'approvedPackets':packets or [],'issues':[],'revision':'fixture-revision'}

def time_packet():
 return {'schemaVersion':1,'type':'backwoods-employee-time','source':'employees','exportId':'fixture-export','company':{'id':'backwoods','name':'Fictional Backwoods'},'start':'2026-10-19','endExclusive':'2026-10-26',
  'timesheets':[{'id':'sheet-1','employeeId':'staff-1','employeeNumber':'FIX-1','employee':'Fictional Employee','start':'2026-10-19','endExclusive':'2026-10-26','status':'approved','approvedBy':'reviewer-1','approvedAt':'2026-10-26T15:00:00Z','sourceHash':'a'*64,
   'assignments':[{'assignmentId':'job-1','departmentId':'wholesale','department':'Wholesale','location':'Fictional warehouse','payType':'hourly','rateCents':1500,'regularMinutes':'2400','overtimeMinutes':'300','regularCents':60000,'overtimeCents':11250,'estimatedGrossCents':71250}]}],
  'timeOff':[],'departments':[]}

class PayrollManagementTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'books.sqlite3')
  pm.sync_employees(self.ledger,'existing-workspace-001',roster(),confirm=True)
  pm.save_provider(self.ledger,{'id':'hrmy','name':'HR.my external workflow'})
 def tearDown(self):self.ledger.close();self.temp.cleanup()
 def input(self,**changes):
  return {'employeeId':'staff-1','assignmentId':'job-1','payType':'hourly','rateCents':1500,'regularMinutes':2400,'overtimeMinutes':300,'overtimeRateCents':2250,'bonusCents':5000,**changes}
 def prepare(self,method='manual',**changes):
  value={'requestKey':str(uuid.uuid4()),'companyId':'backwoods','method':method,'periodStart':'2026-10-19','periodEndExclusive':'2026-10-26','payDate':'2026-10-30','providerId':'hrmy','entries':[self.input()],**changes}
  return pm.create_batch(self.ledger,value)
 def approve(self,batch):
  pm.review_batch(self.ledger,{'id':batch['id'],'reviewed':True,'overtimeReviewed':True,'reason':'Fictional approved wage/hours review'})
  return pm.approve_batch(self.ledger,{'id':batch['id'],'confirmed':True})
 def actual(self,batch,**changes):
  return {'id':batch['id'],'actualProviderReport':True,'reference':'FIXTURE-FINAL-1','entries':[{'entryId':'0','grossCents':76250,'employeeTaxesCents':10000,'deductionsCents':0,'netPayCents':66250,'reimbursementCents':0,'employerTaxesCents':5000,'employerBenefitsCents':0,'feesCents':250}],**changes}
 def final(self):
  batch=self.approve(self.prepare());pm.export_batch(self.ledger,batch['id'],'csv')
  pm.confirm_receipt(self.ledger,{'id':batch['id'],'reference':'FIXTURE-RECEIPT-1','providerConfirmed':True,'evidence':'Fictional provider test receipt, no actual submission'})
  pm.post_final_report(self.ledger,self.actual(batch));return batch
 def test_manual_example_gross_additions_and_no_tax_or_net_guess(self):
  result=pm.calculate_entry(self.input());self.assertEqual(result['grossCents'],76250)
  self.assertNotIn('netCents',result);self.assertIsNone(result['employerLaborCostCents'])
  extra=pm.calculate_entry(self.input(commissionCents=1000,otherEarningsCents=500,reimbursementCents=2500,approvedDeductionCents=1000,verifiedEmployerCostCents=2000,employerCostReference='Actual configured benefit cost'))
  self.assertEqual(extra['grossCents'],77750);self.assertEqual(extra['employerLaborCostCents'],82250)
  for value in [self.input(rateCents=-1),self.input(regularMinutes='NaN'),self.input(overtimeRateCents=0),self.input(approvedDeductionCents=999999)]:
   with self.assertRaises(AccountingError):pm.calculate_entry(value)
 def test_salary_is_an_explicit_period_amount_and_paid_leave_is_not_paid_twice(self):
  result=pm.calculate_entry(self.input(payType='salary',salaryCents=100000,regularMinutes=2400,overtimeMinutes=0,paidLeaveMinutes=480))
  self.assertEqual(result['grossCents'],105000);self.assertEqual(result['paidLeaveGrossCents'],0)
  with self.assertRaises(AccountingError):pm.calculate_entry(self.input(payType='salary',salaryCents=0))
 def test_roster_retries_preserve_uid_and_reject_unreviewed_identity_changes(self):
  pm.sync_employees(self.ledger,'existing-workspace-001',roster());self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM pm_employees').fetchone()[0],1)
  changed=roster();changed['employees'][0]['firebase_uid']='another-person'
  with self.assertRaises(AccountingError):pm.sync_employees(self.ledger,'existing-workspace-001',changed)
  with self.assertRaises(AccountingError):pm.sync_employees(self.ledger,'unrelated-workspace-002',roster())
  self.assertEqual(self.ledger.rows(),[])
 def test_automatic_approved_hours_use_original_overtime_allocation_without_modifying_time(self):
  packet=time_packet();feed=roster([packet]);pm.sync_employees(self.ledger,'existing-workspace-001',feed);pm.sync_employees(self.ledger,'existing-workspace-001',feed)
  original=self.ledger.db.execute("SELECT payload FROM documents WHERE source='employees'").fetchone()[0]
  batch=self.prepare('approved_timecards');entry=batch['payload']['entries'][0]
  self.assertEqual(entry['calculation']['grossCents'],71250);self.assertEqual(entry['inputs']['overtimeRateCents'],2250)
  self.assertEqual(entry['departmentId'],'wholesale');self.assertEqual(entry['method'],'approved_timecards')
  self.assertEqual(self.ledger.db.execute("SELECT payload FROM documents WHERE source='employees'").fetchone()[0],original)
  with self.assertRaises(AccountingError):self.prepare('approved_timecards')
 def test_review_approval_balanced_accrual_and_immutable_export_retries(self):
  batch=self.prepare();self.assertEqual(self.ledger.rows(),[])
  with self.assertRaises(AccountingError):pm.approve_batch(self.ledger,{'id':batch['id'],'confirmed':True})
  batch=self.approve(batch);self.assertEqual(self.ledger.report()['profit'],-76250)
  before=self.ledger.rows();pm.approve_batch(self.ledger,{'id':batch['id'],'confirmed':True});self.assertEqual(self.ledger.rows(),before)
  first=pm.export_batch(self.ledger,batch['id'],'csv');self.assertEqual(pm.export_batch(self.ledger,batch['id'],'csv'),first)
  row=list(csv.DictReader(io.StringIO(first.decode('utf-8-sig'))))[0];self.assertEqual(row['grossPay'],'762.5')
  xlsx=pm.export_batch(self.ledger,batch['id'],'xlsx')
  with zipfile.ZipFile(io.BytesIO(xlsx)) as archive:
   for name in archive.namelist():ElementTree.fromstring(archive.read(name))
   self.assertIn(b'762.5',archive.read('xl/worksheets/sheet1.xml'))
  self.assertEqual(pm.batch_value(self.ledger,batch['id'])['status'],'exported')
  self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM pm_receipts').fetchone()[0],0,'Download must never imply provider receipt')
  with self.assertRaises(AccountingError):pm.export_batch(self.ledger,batch['id'],'provider_csv')
 def test_current_batch_rates_stay_frozen_after_future_effective_rate_change(self):
  batch=self.approve(self.prepare())
  pm.save_rate(self.ledger,{'employeeId':'staff-1','assignmentId':'job-1','effectiveDate':'2026-10-26','payType':'hourly','rateCents':1600,'overtimeRateCents':2400,'reviewed':True,'reason':'Fictional approved raise'})
  self.assertEqual(pm.batch_value(self.ledger,batch['id'])['payload']['entries'][0]['calculation']['grossCents'],76250)
  next_=self.prepare(periodStart='2026-10-26',periodEndExclusive='2026-11-02',payDate='2026-11-06')
  self.assertEqual(next_['payload']['entries'][0]['calculation']['grossCents'],81000)
  saved=self.ledger.db.execute('SELECT payload FROM pm_rates').fetchone()[0]
  pm.save_rate(self.ledger,{'employeeId':'staff-1','assignmentId':'job-1','effectiveDate':'2026-11-02','payType':'hourly','rateCents':1700,'overtimeRateCents':2550,'reviewed':True,'reason':'Fictional later raise'})
  self.assertEqual(self.ledger.db.execute('SELECT payload FROM pm_rates ORDER BY effective_date LIMIT 1').fetchone()[0],saved)
 def test_midperiod_rate_changes_and_payroll_private_fields_require_review(self):
  pm.save_rate(self.ledger,{'employeeId':'staff-1','assignmentId':'job-1','effectiveDate':'2026-10-22','payType':'hourly','rateCents':1600,'overtimeRateCents':2400,'reviewed':True,'reason':'Fictional midperiod raise'})
  with self.assertRaises(AccountingError):self.prepare()
  for role in ['viewer','employee',None]:
   with self.assertRaises(AccountingError):pm.state(self.ledger,{'role':role})
  with self.assertRaises(AccountingError):self.prepare(entries=[self.input(ssn='must not be retained')])
 def test_provider_receipt_requires_evidence_and_cannot_be_recorded_twice(self):
  batch=self.approve(self.prepare());pm.export_batch(self.ledger,batch['id'],'csv')
  with self.assertRaises(AccountingError):pm.confirm_receipt(self.ledger,{'id':batch['id'],'reference':'test','evidence':'Test download only'})
  value={'id':batch['id'],'reference':'FIXTURE-RECEIPT','providerConfirmed':True,'evidence':'Fictional provider acknowledgement'}
  pm.confirm_receipt(self.ledger,value);pm.confirm_receipt(self.ledger,value)
  self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM pm_receipts').fetchone()[0],1)
 def test_final_report_reverses_estimate_once_and_posts_only_actual_provider_taxes(self):
  batch=self.final();self.assertEqual(self.ledger.report()['profit'],-81500)
  before=self.ledger.rows();pm.post_final_report(self.ledger,self.actual(batch));self.assertEqual(self.ledger.rows(),before)
  self.assertEqual(pm.remaining(self.ledger,batch['id']),{'netPay':66250,'taxes':15000,'deductions':0,'fees':250,'benefits':0})
  totals={r['account']:r['debit']-r['credit'] for r in self.ledger.db.execute('SELECT account,SUM(debit) debit,SUM(credit) credit FROM lines GROUP BY account')}
  self.assertEqual(totals['2270'],0);self.assertEqual(totals['1020'] if '1020' in totals else 0,0,'Final reports do not move cash')
  bad=self.actual(batch);bad['entries'][0]['netPayCents']=1
  with self.assertRaises(AccountingError):pm.post_final_report(self.ledger,bad)
 def test_actual_payment_records_reduce_liabilities_once_and_need_bank_reconciliation(self):
  batch=self.final();value={'id':batch['id'],'date':'2026-10-30','reference':'FIXTURE-BANK-1','actualPayment':True,'allocations':{'netPay':66250,'taxes':15000,'fees':250}}
  pm.record_payment(self.ledger,value);before=self.ledger.rows();pm.record_payment(self.ledger,value);self.assertEqual(self.ledger.rows(),before)
  self.assertFalse(any(pm.remaining(self.ledger,batch['id']).values()))
  with self.assertRaises(AccountingError):pm.reconcile_batch(self.ledger,{'id':batch['id']})
  self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM pm_payments').fetchone()[0],1)
  with self.assertRaises(AccountingError):pm.record_payment(self.ledger,{**value,'reference':'FIXTURE-BANK-2'})
 def test_ledger_and_payroll_state_roll_back_together_when_receipt_commit_fails(self):
  batch=self.prepare();pm.review_batch(self.ledger,{'id':batch['id'],'reviewed':True,'overtimeReviewed':True,'reason':'Fictional payroll review'})
  original=self.ledger.audit
  def fail(action,detail):
   if action=='payroll-batch-approved':raise RuntimeError('Synthetic receipt failure')
   return original(action,detail)
  with patch.object(self.ledger,'audit',side_effect=fail):
   with self.assertRaises(RuntimeError):pm.approve_batch(self.ledger,{'id':batch['id'],'confirmed':True})
  self.assertEqual(self.ledger.rows(),[]);self.assertEqual(pm.batch_value(self.ledger,batch['id'])['status'],'reviewed')
 def test_closed_period_and_source_revision_cannot_silently_change_approved_pay(self):
  packet=time_packet();pm.sync_employees(self.ledger,'existing-workspace-001',roster([packet]));batch=self.prepare('approved_timecards')
  self.ledger.db.execute("UPDATE documents SET hash='changed' WHERE source='employees'");self.ledger.db.commit()
  with self.assertRaises(AccountingError):self.approve(batch)
  other=self.prepare(periodStart='2026-10-26',periodEndExclusive='2026-11-02',payDate='2026-11-06');pm.review_batch(self.ledger,{'id':other['id'],'reviewed':True,'overtimeReviewed':True,'reason':'Fictional review'})
  self.ledger.set_settings({'closed_through':'2026-11-06'})
  with self.assertRaises(AccountingError):pm.approve_batch(self.ledger,{'id':other['id'],'confirmed':True})
  self.assertEqual(self.ledger.rows(),[])
 def test_auto_additions_apply_once_and_adjust_overtime_without_changing_source_hours(self):
  first=time_packet();second=copy.deepcopy(first);second.update(exportId='fixture-export-next',start='2026-10-26',endExclusive='2026-11-02')
  second['timesheets'][0].update(id='sheet-2',start='2026-10-26',endExclusive='2026-11-02')
  pm.sync_employees(self.ledger,'existing-workspace-001',roster([first,second]))
  batch=self.prepare('approved_timecards',periodEndExclusive='2026-11-02',payDate='2026-11-06',additions=[{'employeeId':'staff-1','assignmentId':'job-1','bonusCents':5000,'overtimeRateCents':2300,'reference':'Fictional period bonus and regular-rate/OT review'}])
  entries=batch['payload']['entries'];self.assertEqual(len(entries),2)
  self.assertEqual(sum(e['calculation']['bonusCents'] for e in entries),5000)
  self.assertEqual(sum(e['calculation']['grossCents'] for e in entries),148000)
  self.assertEqual(sum(Decimal(e['calculation']['overtimeMinutes']) for e in entries),600)
  with self.assertRaises(AccountingError):self.prepare('approved_timecards',additions=[{'employeeId':'staff-1','assignmentId':'missing','bonusCents':5000,'reference':'No approved job'}])
 def test_verified_salary_is_paid_once_across_two_sheets_and_leave_without_hourly_overtime(self):
  first=time_packet();second=copy.deepcopy(first);second.update(exportId='fixture-export-next',start='2026-10-26',endExclusive='2026-11-02');second['timesheets'][0].update(id='sheet-2',start='2026-10-26',endExclusive='2026-11-02')
  for packet in [first,second]:packet['timesheets'][0]['assignments'][0].update(payType='salary',rateCents=200000,regularCents=0,overtimeCents=0,estimatedGrossCents=0)
  feed=roster([first,second]);job=feed['employees'][0]['jobs'][0];job.update(pay_type='salary',rate_cents=200000,salary_arrangement={'frequency':'biweekly','exemption':'verified_exempt','verification':'Fictional reviewed salary classification','verified_by':'qualified-reviewer','verified_at':'2026-01-01T00:00:00Z'})
  pm.sync_employees(self.ledger,'existing-workspace-001',feed)
  for frequency in ['weekly',None]:
   with self.assertRaises(AccountingError):self.prepare('approved_timecards',periodEndExclusive='2026-11-02',payDate='2026-11-06',frequency=frequency)
  batch=self.prepare('approved_timecards',periodEndExclusive='2026-11-02',payDate='2026-11-06',frequency='biweekly')
  self.assertEqual(len(batch['payload']['entries']),1);entry=batch['payload']['entries'][0]
  self.assertEqual(entry['calculation']['grossCents'],200000);self.assertEqual(entry['calculation']['overtimeGrossCents'],0)
  self.assertEqual(Decimal(entry['calculation']['trackedOvertimeMinutes']),600);self.assertEqual(len(entry['sourceRefs']),2)
  # A manually supplied internal verification flag is never accepted.
  with self.assertRaises(AccountingError):self.prepare(entries=[self.input(payType='salary',salaryCents=200000,_verifiedSalaryExempt=True)])
 def test_matching_an_existing_bank_expense_reclassifies_once_without_a_second_bank_credit(self):
  batch=self.final();amount=81500
  from accounting.imports import record,line
  self.ledger.import_documents('manual',[record('expense',{'id':'existing-bank-payroll','date':'2026-10-30','memo':'Fictional existing bank withdrawal'},[line('5800',debit=amount),line('1020',credit=amount)],amount=amount)],{},'Existing bank fixture')
  bank=self.ledger.db.execute("SELECT id FROM lines WHERE account='1020'").fetchone()[0]
  value={'id':batch['id'],'date':'2026-10-30','reference':'FIXTURE-EXISTING-BANK','actualPayment':True,'allocations':{'netPay':66250,'taxes':15000,'fees':250},'bankLineId':bank}
  with self.assertRaises(AccountingError):pm.record_payment(self.ledger,value)
  value.update(reclassifyExpense=True,reason='Fictional verified payroll withdrawal previously coded as expense');pm.record_payment(self.ledger,value);pm.record_payment(self.ledger,value)
  self.assertEqual(self.ledger.db.execute("SELECT SUM(credit) FROM lines WHERE account='1020'").fetchone()[0],amount)
  self.assertEqual(self.ledger.report()['profit'],-81500)
  self.ledger.reconcile({'account':'1020','date':'2026-10-31','starting':'0','ending':'-815','lineIds':[bank]})
  self.assertEqual(pm.reconcile_batch(self.ledger,{'id':batch['id']})['status'],'reconciled')
 def test_withdrawn_or_stale_employee_approval_blocks_cached_payroll_but_preserves_original_import(self):
  pm.sync_employees(self.ledger,'existing-workspace-001',roster([time_packet()]))
  batch=self.prepare('approved_timecards')
  withdrawn=roster();withdrawn['revision']='withdrawn-current-view'
  pm.sync_employees(self.ledger,'existing-workspace-001',withdrawn)
  self.assertEqual(self.ledger.db.execute("SELECT COUNT(*) FROM documents WHERE source='employees'").fetchone()[0],1)
  with self.assertRaises(AccountingError):self.approve(batch)
  with self.assertRaises(AccountingError):pm.prepare_entries(self.ledger,{'companyId':'backwoods','method':'approved_timecards','periodStart':'2026-10-19','periodEndExclusive':'2026-10-26'})
 def test_another_legal_company_never_enters_the_bound_company_payroll_roster(self):
  feed=roster();feed['companies'].append({'id':'unrelated-business','name':'Unrelated Company'});other=copy.deepcopy(feed['employees'][0]);other.update(id='another-worker',company_id='unrelated-business',firebase_uid='another-uid',username='other.worker');feed['employees'].append(other)
  pm.sync_employees(self.ledger,'existing-workspace-001',feed)
  self.assertEqual([r[0] for r in self.ledger.db.execute('SELECT id FROM pm_employees')],['staff-1'])
  self.assertEqual(pm.settings(self.ledger)['companies'],['backwoods'])
