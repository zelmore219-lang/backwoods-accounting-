"""Employee-managed Accounting access, preserving the existing company owner.

Financial user rows are access projections of reviewed Employee UIDs, not a
second personnel/password database. Credentials stay in native process memory;
each managed request rechecks the server-owned Employee grant and revocation.
The company's existing protected Firebase connection is never replaced by a
staff sign-in. No employee receives the company owner's refresh token.
"""
import base64,hashlib,json,secrets,time,uuid
from .ledger import AccountingError,ACTOR,canonical,now
from . import auth,payroll_management as pm
from .firebase_sync import CONFIG

SCHEMA='''
CREATE TABLE IF NOT EXISTS employee_financial_links(user_id TEXT PRIMARY KEY REFERENCES users(id),
 firebase_uid TEXT NOT NULL UNIQUE,employee_id TEXT NOT NULL UNIQUE,workspace TEXT NOT NULL,linked_at TEXT NOT NULL,linked_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_employee_access(employee_id TEXT PRIMARY KEY REFERENCES pm_employees(id),accounting_role TEXT);
'''

def need(value,message):
 if not value:raise AccountingError(message)
def key(token):return hashlib.sha256((token or '').encode()).hexdigest()
def enabled(ledger):return bool(pm.settings(ledger))
def candidate(ledger,username):
 if not enabled(ledger):return False
 user=ledger.db.execute('SELECT id FROM users WHERE username=?',(auth.username(username),)).fetchone()
 if user:return bool(ledger.db.execute('SELECT 1 FROM employee_financial_links WHERE user_id=?',(user['id'],)).fetchone())
 return bool(ledger.db.execute('SELECT 1 FROM pm_employees WHERE username=?',(auth.username(username),)).fetchone())

def read_access(client,credentials,profile,connection):
 stamp=time.time()
 if credentials['expires']<stamp+60:
  result=client.transport('https://securetoken.googleapis.com/v1/token?key='+CONFIG['apiKey'],{'grant_type':'refresh_token','refresh_token':credentials['refresh']},form=True)
  need(result and result.get('user_id')==profile['uid'] and result.get('id_token'),'The Employee sign-in could not be renewed')
  credentials.update(token=result['id_token'],refresh=result.get('refresh_token',credentials['refresh']),expires=stamp+int(result.get('expires_in',3600)))
 token=credentials['token']
 try:
  claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
  need(claims.get('aud')==CONFIG['projectId'] and claims.get('iss')=='https://securetoken.google.com/'+CONFIG['projectId'],'The Employee sign-in belongs to another project')
 except (ValueError,IndexError,TypeError):raise AccountingError('Invalid Employee sign-in') from None
 # Google verifies this token/account. Decoded claims alone never authenticate.
 result=client.transport('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key='+CONFIG['apiKey'],{'idToken':token})
 users=(result or {}).get('users',[]);need(len(users)==1 and users[0].get('localId')==profile['uid'] and not users[0].get('disabled'),'This Employee account is disabled or no longer verified')
 root='projects/'+CONFIG['projectId']+'/databases/(default)/documents/'
 document=client.transport('https://firestore.googleapis.com/v1/'+root+'employeeAccess/'+profile['uid'],token=token)
 need(document,'Accounting access has not been assigned in Employee')
 f=document.get('fields',{});value=lambda k,kind='stringValue':f.get(k,{}).get(kind)
 role=f.get('applications',{}).get('mapValue',{}).get('fields',{}).get('accounting',{}).get('stringValue')
 need(value('uid')==profile['uid'] and value('employeeId')==profile['id'] and value('companyId')==profile['company_id'] and value('username')==profile['username'],'The Employee UID, username or company link changed; the owner must review it')
 need(value('accountActive','booleanValue') is True and value('employmentStatus')=='active' and value('mustChangePassword','booleanValue') is False and role in {'owner','accountant','viewer'},'Accounting access is inactive, unassigned, or requires a password change in Employee')
 need(profile['company_id'] in connection['companies'],'This Employee belongs to another Accounting company')
 need(int(claims.get('auth_time',0))>=int(value('passwordValidAfter','integerValue') or 0) and int(claims.get('auth_time',0))>=int(users[0].get('validSince') or 0),'The Employee sign-in was revoked; sign in again with the current password')
 return role

def login(app,value):
 ledger=app.ledger()
 try:
  connection=pm.settings(ledger);need(connection,'The owner must connect the actual Employee workspace first')
  name=auth.username(value.get('username',''));local=ledger.db.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
  linked=ledger.db.execute('SELECT * FROM employee_financial_links WHERE user_id=?',(local['id'],)).fetchone() if local else None
  profile=ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(linked['employee_id'],)).fetchone() if linked else ledger.db.execute('SELECT * FROM pm_employees WHERE username=?',(name,)).fetchone()
  need(profile and profile['uid'] and profile['workspace']==connection['workspace'],'Sync the existing Employee roster and link this exact UID before signing in')
  profile=dict(profile)
  attempt=ledger.db.execute('SELECT * FROM login_attempts WHERE username=?',('employee:'+name,)).fetchone();stamp=int(time.time())
  need(not attempt or attempt['locked_until']<=stamp,'Too many failed attempts. Try again after 15 minutes.')
 finally:ledger.close()
 try:
  result=app.firebase.sign_in(profile['username'],str(value.get('password') or ''))
  need(result.get('localId')==profile['uid'],'This username does not match the linked Employee UID')
  credentials={'token':result['idToken'],'refresh':result['refreshToken'],'expires':time.time()+int(result.get('expiresIn',3600))}
  role=read_access(app.firebase,credentials,profile,connection)
 except Exception:
  ledger=app.ledger()
  try:
   failures=(attempt['failures'] if attempt and stamp-attempt['last_at']<900 else 0)+1
   with ledger.db:ledger.db.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?,?)',('employee:'+name,failures,stamp+900 if failures>=5 else 0,stamp));ledger.audit('employee-financial-login-denied',{'employeeId':profile['id']})
  finally:ledger.close()
  raise
 with app.shared.mutation():
  ledger=app.ledger()
  try:
   # Refresh may have installed a newer shared database; recheck the binding.
   latest=pm.settings(ledger);need(latest and latest['workspace']==connection['workspace'],'The Accounting company mapping changed during sign-in')
   link=ledger.db.execute('SELECT * FROM employee_financial_links WHERE firebase_uid=?',(profile['uid'],)).fetchone()
   primary=ledger.db.execute('SELECT user_id FROM firebase_link WHERE uid=?',(profile['uid'],)).fetchone()
   row=ledger.db.execute('SELECT * FROM users WHERE id=?',(link['user_id'] if link else primary['user_id'],)).fetchone() if link or primary else None
   if not row:
    need(not ledger.db.execute('SELECT 1 FROM users WHERE username=?',(profile['username'],)).fetchone(),'A local financial account already uses this username. The owner must explicitly link it to this verified Employee UID in Settings')
    uid_=profile['uid'];need(not ledger.db.execute('SELECT 1 FROM users WHERE id=?',(uid_,)).fetchone(),'This financial account ID needs an owner-reviewed link')
    salt=secrets.token_hex(16)
    with ledger.db:ledger.db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',(uid_,profile['username'],profile['name'],role,auth.password_hash(secrets.token_urlsafe(64),salt),salt,now()))
    row=ledger.db.execute('SELECT * FROM users WHERE id=?',(uid_,)).fetchone()
   with ledger.db:
    ledger.db.execute('INSERT OR IGNORE INTO employee_financial_links VALUES(?,?,?,?,?,?)',(row['id'],profile['uid'],profile['id'],connection['workspace'],now(),'verified Employee Accounting grant'))
    saved=ledger.db.execute('SELECT * FROM employee_financial_links WHERE user_id=?',(row['id'],)).fetchone()
    need(saved['firebase_uid']==profile['uid'] and saved['employee_id']==profile['id'],'The financial account belongs to another Employee UID')
    if not primary:ledger.db.execute('UPDATE users SET role=?,name=? WHERE id=?',(role,profile['name'],row['id']))
    ledger.db.execute('DELETE FROM login_attempts WHERE username=?',('employee:'+name,))
   token,user=auth.issue_session(ledger,ledger.db.execute('SELECT * FROM users WHERE id=?',(row['id'],)).fetchone());user['role']=role
   app.employee_sessions[key(token)]={'credentials':credentials,'profile':profile,'connection':connection}
   ledger.audit('employee-financial-login',{'employeeId':profile['id'],'firebaseUid':profile['uid'],'financialUserId':row['id']})
  finally:ledger.close()
 return token,user

def session_user(app,ledger,token):
 user=auth.session_user(ledger,token)
 if not user:return None
 linked=ledger.db.execute('SELECT * FROM employee_financial_links WHERE user_id=?',(user['id'],)).fetchone()
 if not linked:return user
 if key(token) in app.company_owner_sessions:
  need(user['role']=='owner' and app.firebase.connection and linked['firebase_uid']==app.firebase.connection['uid'],'The company owner identity changed')
  app.firebase.document(app.firebase.root()+'/ledger/state')
  return {**user,'companyOwnerSession':True,'employeeManaged':True}
 current=app.employee_sessions.get(key(token));need(current,'Sign in again with your Employee username and password')
 need(linked['firebase_uid']==current['profile']['uid'] and linked['workspace']==current['connection']['workspace'],'The Employee financial link changed; sign in again')
 user['role']=read_access(app.firebase,current['credentials'],current['profile'],current['connection'])
 user['employeeManaged']=True
 return user

def link_existing(ledger,user,value):
 pm.require_payroll(user,owner=True);need(value.get('confirmed') is True,'Review the exact existing financial account and Employee UID before linking')
 connection=pm.settings(ledger);need(connection,'Connect the actual Employee workspace first')
 financial=ledger.db.execute('SELECT * FROM users WHERE id=?',(value.get('userId'),)).fetchone();profile=ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(value.get('employeeId'),)).fetchone()
 need(financial and profile and profile['uid'] and profile['workspace']==connection['workspace'],'Choose an existing financial account and its verified Employee identity')
 primary=ledger.db.execute('SELECT uid FROM firebase_link WHERE user_id=?',(financial['id'],)).fetchone()
 if primary:need(primary['uid']==profile['uid'],'The existing company owner has a different verified UID. Do not reassign that account by name')
 with ledger.db:
  old=ledger.db.execute('SELECT * FROM employee_financial_links WHERE user_id=?',(financial['id'],)).fetchone()
  if old:need(old['firebase_uid']==profile['uid'],'This financial account is already bound to another Employee UID');return {'linked':True}
  ledger.db.execute('INSERT INTO employee_financial_links VALUES(?,?,?,?,?,?)',(financial['id'],profile['uid'],profile['id'],connection['workspace'],now(),user['username']))
  ledger.db.execute('DELETE FROM sessions WHERE user_id=?',(financial['id'],));ledger.audit('existing-financial-account-linked-to-employee',{'financialUserId':financial['id'],'employeeId':profile['id'],'firebaseUid':profile['uid']})
 return {'linked':True}

def reauthenticate(app,ledger,user,password):
 link=ledger.db.execute('SELECT * FROM employee_financial_links WHERE user_id=?',(user['id'],)).fetchone()
 if not link:
  temporary,_=auth.login(ledger,{'username':user['username'],'password':password});auth.logout(ledger,temporary);return
 if user.get('companyOwnerSession'):
  primary=ledger.db.execute('SELECT uid,email FROM firebase_link WHERE user_id=?',(user['id'],)).fetchone();need(primary,'The company owner link is unavailable')
  result=app.firebase.sign_in(primary['email'],password);need(result.get('localId')==primary['uid'],'The password does not match the existing company owner')
  app.firebase.transport('https://firestore.googleapis.com/v1/'+app.firebase.root()+'/ledger/state',token=result['idToken']);return
 profile=dict(ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(link['employee_id'],)).fetchone())
 result=app.firebase.sign_in(profile['username'],password);need(result.get('localId')==link['firebase_uid'],'Owner password does not match this Employee UID')
 role=read_access(app.firebase,{'token':result['idToken'],'refresh':result['refreshToken'],'expires':time.time()+int(result.get('expiresIn',3600))},profile,pm.settings(ledger));need(role=='owner','Current owner Accounting access is required')
