import base64,copy,json,secrets,tempfile,time,unittest
from pathlib import Path
from accounting import auth,employee_auth,payroll_management as pm
from accounting.firebase_sync import CONFIG
from accounting.ledger import AccountingError
from accounting.server import Application
from test_payroll_management import roster

class EmployeeFinancialAccessTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
  self.uid='same-existing-uid';self.disabled=False;self.role='accountant';self.valid_after=0;self.username='fixture.staff'
  ledger=self.app.ledger();self.owner=auth.create_user(ledger,{'username':'company.owner','name':'Company Owner','password':'company-recovery-passphrase'},first=True);pm.sync_employees(ledger,'existing-workspace-001',roster(),confirm=True);ledger.close()
  self.calls=[];self.app.firebase.sign_in=self.sign_in;self.app.firebase.transport=self.transport
 def tearDown(self):self.app.stop.set();self.temp.cleanup()
 def sign_in(self,username,password):
  if username!=self.username or password!='existing-employee-passphrase':raise AccountingError('Fixture Firebase rejected the password')
  claims={'aud':CONFIG['projectId'],'iss':'https://securetoken.google.com/'+CONFIG['projectId'],'auth_time':int(time.time())-5}
  middle=base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
  return {'localId':self.uid,'idToken':'fixture.'+middle+'.fixture-signature','refreshToken':'fixture-staff-refresh','expiresIn':'3600'}
 def transport(self,url,value=None,token=None,form=False):
  self.calls.append(url)
  if 'accounts:lookup' in url:return {'users':[{'localId':self.uid,'disabled':self.disabled,'validSince':str(self.valid_after)}]}
  if '/employeeAccess/' in url:
   fields={'uid':{'stringValue':self.uid},'employeeId':{'stringValue':'staff-1'},'companyId':{'stringValue':'backwoods'},'username':{'stringValue':self.username},'employmentStatus':{'stringValue':'active'},'accountActive':{'booleanValue':True},'mustChangePassword':{'booleanValue':False},'passwordValidAfter':{'integerValue':str(self.valid_after)},'applications':{'mapValue':{'fields':{'accounting':{'stringValue':self.role}} if self.role else {}}}}
   return {'fields':fields}
  raise AssertionError('Unexpected fixture authentication request '+url)
 def login(self):return employee_auth.login(self.app,{'username':'fixture.staff','password':'existing-employee-passphrase'})
 def test_new_financial_access_projects_the_same_uid_and_never_clones_employee_password(self):
  token,user=self.login();self.assertEqual(user['id'],self.uid);self.assertEqual(user['role'],'accountant')
  ledger=self.app.ledger()
  try:
   projected=ledger.db.execute('SELECT * FROM users WHERE id=?',(self.uid,)).fetchone()
   self.assertNotEqual(projected['password_hash'],auth.password_hash('existing-employee-passphrase',projected['salt']))
   self.assertEqual(employee_auth.session_user(self.app,ledger,token)['role'],'accountant')
   before=ledger.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
  finally:ledger.close()
  self.login();ledger=self.app.ledger();self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],before);ledger.close()
  self.assertIsNone(self.app.firebase.connection,'Staff login must not replace the company connection')
 def test_every_managed_request_rechecks_role_revocation_disabled_account_and_auth_time(self):
  token,_=self.login();ledger=self.app.ledger()
  try:
   self.role='viewer';self.assertEqual(employee_auth.session_user(self.app,ledger,token)['role'],'viewer')
   self.role=None
   with self.assertRaises(AccountingError):employee_auth.session_user(self.app,ledger,token)
   self.role='accountant';self.disabled=True
   with self.assertRaises(AccountingError):employee_auth.session_user(self.app,ledger,token)
   self.disabled=False;self.valid_after=int(time.time())
   with self.assertRaises(AccountingError):employee_auth.session_user(self.app,ledger,token)
  finally:ledger.close()
 def test_an_explicit_existing_account_link_preserves_original_financial_user_id(self):
  ledger=self.app.ledger()
  local=auth.create_user(ledger,{'username':'old.finance.alias','name':'Existing Finance User','password':'old-local-finance-passphrase','role':'accountant'})
  employee_auth.link_existing(ledger,self.owner,{'userId':local['id'],'employeeId':'staff-1','confirmed':True});ledger.close()
  token,user=employee_auth.login(self.app,{'username':'old.finance.alias','password':'existing-employee-passphrase'})
  self.assertEqual(user['id'],local['id']);ledger=self.app.ledger()
  self.assertTrue(employee_auth.candidate(ledger,'old.finance.alias'));self.assertEqual(employee_auth.session_user(self.app,ledger,token)['id'],local['id']);ledger.close()
 def test_a_matching_username_does_not_implicitly_link_an_unreviewed_local_account(self):
  ledger=self.app.ledger();local=auth.create_user(ledger,{'username':'fixture.staff','name':'Potentially Different Person','password':'unrelated-local-passphrase','role':'accountant'});ledger.close()
  with self.assertRaises(AccountingError):self.login()
  ledger=self.app.ledger();self.assertFalse(ledger.db.execute('SELECT 1 FROM employee_financial_links WHERE user_id=?',(local['id'],)).fetchone());ledger.close()
 def test_stopped_process_cannot_restore_a_managed_session_without_verified_credentials(self):
  token,_=self.login();self.app.employee_sessions.clear();ledger=self.app.ledger()
  with self.assertRaises(AccountingError):employee_auth.session_user(self.app,ledger,token)
  ledger.close()
 def test_owner_recovery_accounts_and_unauthorized_links_are_preserved(self):
  ledger=self.app.ledger();token,_=auth.login(ledger,{'username':'company.owner','password':'company-recovery-passphrase'})
  self.assertFalse(employee_auth.candidate(ledger,'company.owner'));self.assertEqual(employee_auth.session_user(self.app,ledger,token)['role'],'owner')
  with self.assertRaises(AccountingError):employee_auth.link_existing(ledger,{'role':'accountant'},{'userId':self.owner['id'],'employeeId':'staff-1','confirmed':True})
  with self.assertRaises(AccountingError):employee_auth.link_existing(ledger,self.owner,{'userId':self.owner['id'],'employeeId':'staff-1','confirmed':False})
  ledger.close()
 def test_company_owner_proof_preserves_the_original_financial_owner_and_rejects_uid_reassignment(self):
  ledger=self.app.ledger()
  with ledger.db:ledger.db.execute('INSERT INTO firebase_link VALUES(?,?,?)',('actual-company-owner',self.owner['id'],'company.owner'))
  with self.assertRaises(AccountingError):employee_auth.link_existing(ledger,self.owner,{'userId':self.owner['id'],'employeeId':'staff-1','confirmed':True})
  # A separately verified primary-owner session may retain owner recovery even
  # if an Employee alias is linked. Its proof must be rechecked remotely.
  with ledger.db:ledger.db.execute('INSERT INTO employee_financial_links VALUES(?,?,?,?,?,?)',(self.owner['id'],'actual-company-owner','staff-1','existing-workspace-001','fixture','fixture'))
  token,_=auth.issue_session(ledger,ledger.db.execute('SELECT * FROM users WHERE id=?',(self.owner['id'],)).fetchone())
  self.app.company_owner_sessions.add(employee_auth.key(token));self.app.firebase.connection={'uid':'actual-company-owner'}
  reads=[];self.app.firebase.document=lambda path:reads.append(path) or None
  result=employee_auth.session_user(self.app,ledger,token);self.assertEqual(result['role'],'owner');self.assertTrue(result['companyOwnerSession']);self.assertEqual(len(reads),1)
  self.app.firebase.connection={'uid':'unrelated-company'}
  with self.assertRaises(AccountingError):employee_auth.session_user(self.app,ledger,token)
  ledger.close()
