"""Payroll preparation and actual-result accounting; no invented taxes/payments.

Employee owns identities/time originals. This module stores financial projections,
reviewed payroll inputs and immutable batch snapshots in the existing ledger.
Provider receipt and bank settlement are separate, evidenced owner actions.
"""
import base64,csv,hashlib,io,json,re,sqlite3,uuid,zipfile,zlib
from datetime import date,timedelta
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from xml.sax.saxutils import escape
from .ledger import AccountingError,ACTOR,canonical,day,now
from .imports import record,line,pair

# Shared company snapshots reject executable SQL schema. Keep append-only
# history and frozen-snapshot guards in the authorized domain operations.
SCHEMA='''
CREATE TABLE IF NOT EXISTS pm_employees(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,company_id TEXT NOT NULL,
 uid TEXT,username TEXT NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL,jobs TEXT NOT NULL,source_hash TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_feed_sources(source_id TEXT PRIMARY KEY,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_rates(id TEXT PRIMARY KEY,employee_id TEXT NOT NULL REFERENCES pm_employees(id),
 assignment_id TEXT NOT NULL,effective_date TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,created_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_providers(id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_mappings(provider_id TEXT NOT NULL,employee_id TEXT NOT NULL REFERENCES pm_employees(id),
 provider_employee_id TEXT NOT NULL,PRIMARY KEY(provider_id,employee_id),UNIQUE(provider_id,provider_employee_id));
CREATE TABLE IF NOT EXISTS pm_batches(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,request_hash TEXT NOT NULL,
 company_id TEXT NOT NULL,starts_on TEXT NOT NULL,ends_on TEXT NOT NULL,pay_date TEXT NOT NULL,provider_id TEXT NOT NULL,
 status TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,created_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pm_claims(source_id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES pm_batches(id));
CREATE TABLE IF NOT EXISTS pm_exports(batch_id TEXT NOT NULL REFERENCES pm_batches(id),format TEXT NOT NULL,
 hash TEXT NOT NULL,content BLOB NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(batch_id,format));
CREATE TABLE IF NOT EXISTS pm_receipts(batch_id TEXT PRIMARY KEY REFERENCES pm_batches(id),provider_id TEXT NOT NULL,
 reference TEXT NOT NULL,evidence TEXT NOT NULL,confirmed_at TEXT NOT NULL,confirmed_by TEXT NOT NULL,UNIQUE(provider_id,reference));
CREATE TABLE IF NOT EXISTS pm_final_reports(batch_id TEXT PRIMARY KEY REFERENCES pm_batches(id),provider_id TEXT NOT NULL,
 reference TEXT NOT NULL,payload TEXT NOT NULL,posted_at TEXT NOT NULL,UNIQUE(provider_id,reference));
CREATE TABLE IF NOT EXISTS pm_payments(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES pm_batches(id),kind TEXT NOT NULL,
 reference TEXT UNIQUE NOT NULL,amount INTEGER NOT NULL,bank_line_id INTEGER UNIQUE,payload TEXT NOT NULL,created_at TEXT NOT NULL);
'''

def need(value,message):
 if not value:raise AccountingError(message)
def text(value,label='Value',limit=500):
 value=str(value or '').strip();need(value and len(value)<=limit,'Enter '+label);return value
def number(value,label,maximum=100_000_000):
 need(type(value) is int and 0<=value<=maximum,'Enter a valid nonnegative '+label+' in cents or minutes');return value
def decimal(value,label):
 try:
  need(not isinstance(value,bool),label+' must be a number');n=Decimal(str(value));need(n.is_finite() and 0<=n<=Decimal('1000000'),'Invalid '+label);return n
 except (InvalidOperation,ValueError,TypeError):raise AccountingError('Invalid '+label) from None
def rounded(value):return int(Decimal(value).quantize(Decimal(1),rounding=ROUND_HALF_UP))
def require_payroll(user,owner=False):need(user and user.get('role') in ({'owner'} if owner else {'owner','accountant'}),'Owner access required' if owner else 'Payroll access is restricted')
def get_batch(ledger,id_):
 row=ledger.db.execute('SELECT * FROM pm_batches WHERE id=?',(id_,)).fetchone();need(row,'Payroll batch not found');return dict(row)
def batch_value(ledger,id_):
 row=get_batch(ledger,id_);return {**row,'payload':json.loads(row['payload'])}
def settings(ledger):return json.loads(ledger.settings().get('employee_payroll_connection','null'))

def employee_feed(client):
 """Read only the existing authenticated Employee finance view; no new backend."""
 need(client.connection and client.bearer(),'Connect the existing company Firebase owner before connecting Employee')
 root='projects/'+client.root().split('/')[1]+'/databases/(default)/documents/'
 config=client.document(root+'employeeService/config');need(config,'Start the existing Employee owner service')
 config=config.get('fields',{});workspace=config.get('workspaceId',{}).get('stringValue')
 need(workspace and re.fullmatch(r'[A-Za-z0-9_-]{16,100}',workspace),'The Employee workspace has not published its verified identity')
 path=root+'employeeViews/'+client.connection['uid'];view=client.document(path)
 need(view,'Assign this existing company owner Employee Management access and start Owner service')
 meta=(view.get('fields',{}).get('payroll',{}).get('mapValue',{}).get('fields',{}))
 need(meta,'Update Employee to the connected payroll-feed version and start Owner service')
 value=lambda key,kind='stringValue':meta.get(key,{}).get(kind)
 count=int(value('count','integerValue') or 0);generation=value('generation');fingerprint=value('hash')
 need(1<=count<=200 and re.fullmatch('[a-f0-9]{32}',str(generation)) and re.fullmatch('[a-f0-9]{64}',str(fingerprint)),'Invalid Employee finance view manifest')
 parts=[];size=0
 for index in range(count):
  part=client.document(path+'/generations/'+generation+'/parts/'+str(index).zfill(4));need(part,'The Employee finance view is incomplete; retry')
  raw=base64.b64decode(part['fields']['data']['stringValue'],validate=True);size+=len(raw);need(size<=32*1024*1024,'Employee finance view exceeds the supported size');parts.append(raw)
 raw=b''.join(parts);need(hashlib.sha256(raw).hexdigest()==fingerprint,'Employee finance view failed its integrity check')
 latest=client.document(path);need(latest and latest.get('updateTime')==view.get('updateTime'),'Employee records changed while reading; retry')
 inflater=zlib.decompressobj();raw=inflater.decompress(raw,32*1024*1024+1)
 need(len(raw)<=32*1024*1024 and inflater.eof and not inflater.unused_data,'Invalid Employee finance view compression')
 payload=json.loads(raw);need(payload.get('type')=='backwoods-employee-payroll-feed' and payload.get('schemaVersion')==1,'Unsupported Employee payroll feed')
 return workspace,payload

def sync_employees(ledger,workspace,payload,confirm=False,company_id=None):
 need(payload.get('type')=='backwoods-employee-payroll-feed' and payload.get('schemaVersion')==1,'Use the approved Employee payroll feed')
 existing=settings(ledger)
 need(confirm or existing and existing['workspace']==workspace,'Review and connect the actual Employee workspace first')
 if existing:need(existing['workspace']==workspace,'The Employee workspace changed; do not mix personnel databases')
 companies={str(c['id']) for c in payload.get('companies',[])};need(companies,'The Employee feed has no company identity')
 selected=(existing['companies'][0] if existing and len(existing['companies'])==1 else company_id) or (next(iter(companies)) if len(companies)==1 else None)
 need(selected in companies,'Select the actual Employee legal company for this Accounting profile; unrelated companies cannot share payroll books')
 if existing:need(existing['companies']==[selected],'The Employee company mapping changed. Use a separate Accounting profile for another legal company')
 # Departments stay together; unrelated legal companies never enter this ledger.
 payload={**payload,'companies':[c for c in payload['companies'] if str(c['id'])==selected],
  'employees':[e for e in payload.get('employees',[]) if e.get('company_id')==selected],
  'approvedPackets':[p for p in payload.get('approvedPackets',[]) if p.get('company',{}).get('id')==selected],
  'issues':[i for i in payload.get('issues',[]) if i.get('company_id')==selected],
  'pestAccounting':[p for p in payload.get('pestAccounting',[]) if p.get('companyId')==selected]}
 source_hash=hashlib.sha256(canonical(payload).encode()).hexdigest()
 last=json.loads(ledger.settings().get('employee_payroll_last_sync','null'))
 if existing and not confirm and last and last.get('sourceHash')==source_hash:return {'unchanged':True,'employees':len(payload.get('employees',[])),'imports':[],'issues':payload.get('issues',[])}
 companies={selected}
 profiles=payload.get('employees');need(isinstance(profiles,list) and len(profiles)<=10000,'Invalid Employee roster')
 ids=set()
 for e in profiles:
  id_=text(e.get('id'),'Employee ID',128);need(id_ not in ids,'Duplicate Employee ID in roster');ids.add(id_)
  need(e.get('company_id') in companies and isinstance(e.get('jobs'),list),'Invalid Employee company or assignments')
  old=ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(id_,)).fetchone()
  if old:need(old['workspace']==workspace and old['company_id']==e['company_id'] and (old['uid'] is None or old['uid']==e.get('firebase_uid')) and old['username']==e['username'],'An Employee identity changed. Review the exact UID before replacing payroll links')
  for j in e['jobs']:number(j.get('rate_cents'),'Employee compensation');need(j.get('pay_type') in {'hourly','salary'},'Unsupported Employee compensation type')
 # Existing approved time imports retain their own validation, revisions and IDs.
 from .imports import sanitize_payload,prepare
 receipts=[];current_sources={}
 for packet in payload.get('approvedPackets',[]):
  clean=sanitize_payload(packet,'employees');documents,accounts,warnings=prepare(clean,'employees')
  receipts.append(ledger.import_documents('employees',documents,clean,'Automatic approved Employee hours',accounts=accounts))
  for document in documents:
   saved=ledger.db.execute("SELECT hash FROM documents WHERE source='employees' AND source_id=?",(document['id'],)).fetchone()
   current_sources[document['id']]=saved['hash']
 with ledger.db:
  # Keep historical imported documents, but eligibility follows the complete
  # current protected feed. Withdrawn/stale approvals cannot remain payable.
  ledger.db.execute('DELETE FROM pm_feed_sources')
  ledger.db.executemany('INSERT INTO pm_feed_sources VALUES(?,?)',current_sources.items())
  if not existing:ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('employee_payroll_connection',canonical({'workspace':workspace,'companies':sorted(companies)})))
  for e in profiles:
   ledger.db.execute('INSERT INTO pm_employees VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET uid=COALESCE(pm_employees.uid,excluded.uid),name=excluded.name,status=excluded.status,jobs=excluded.jobs,source_hash=excluded.source_hash,updated_at=excluded.updated_at',
    (e['id'],workspace,e['company_id'],e.get('firebase_uid'),text(e.get('username'),'Employee username',100),text(e.get('name'),'Employee name',150),str(e.get('status')),canonical(e['jobs']),hashlib.sha256(canonical(e).encode()).hexdigest(),now()))
   role=e.get('accountingRole');need(role in {None,'owner','accountant','viewer'},'Unsupported Employee Accounting role')
   ledger.db.execute('INSERT INTO pm_employee_access VALUES(?,?) ON CONFLICT(employee_id) DO UPDATE SET accounting_role=excluded.accounting_role',(e['id'],role))
  # Deletion is not guessed as termination; missing identities require review.
  ledger.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('employee_payroll_last_sync',canonical({'at':now(),'revision':payload.get('revision'),'sourceHash':source_hash,'issues':payload.get('issues',[]),'missingEmployeeIds':[r[0] for r in ledger.db.execute('SELECT id FROM pm_employees') if r[0] not in ids]})))
  ledger.audit('payroll-roster-synchronized',{'workspace':workspace,'employees':len(profiles),'approvedPackets':len(receipts)})
 from . import pest
 pest.synchronize(ledger,workspace,payload.get('pestAccounting',[]))
 return {'employees':len(profiles),'imports':receipts,'issues':payload.get('issues',[])}

def save_rate(ledger,value):
 employee=ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(value.get('employeeId'),)).fetchone();need(employee,'Choose an existing Employee profile')
 assignment=text(value.get('assignmentId'),'assigned job');need(any(j['id']==assignment for j in json.loads(employee['jobs'])),'Choose this employee’s actual job')
 pay_type=value.get('payType');need(pay_type in {'hourly','salary'},'Choose hourly or salary')
 rate=number(value.get('rateCents'),'compensation');need(rate>0,'Compensation must be greater than zero')
 overtime=number(value.get('overtimeRateCents',0),'overtime rate');effective=day(value.get('effectiveDate'))
 note=text(value.get('reason'),'the compensation approval reference')
 need(value.get('reviewed') is True,'Confirm this approved compensation and effective date')
 id_=str(uuid.uuid4());payload={'payType':pay_type,'rateCents':rate,'overtimeRateCents':overtime,'reason':note,'salaryPerPeriod':pay_type=='salary'}
 old=ledger.db.execute('SELECT id FROM pm_rates WHERE employee_id=? AND assignment_id=? AND effective_date=? AND payload=?',(employee['id'],assignment,effective,canonical(payload))).fetchone()
 if old:return {'id':old[0],'alreadyRecorded':True}
 with ledger.db:
  ledger.db.execute('INSERT INTO pm_rates VALUES(?,?,?,?,?,?,?)',(id_,employee['id'],assignment,effective,canonical(payload),now(),ACTOR.get()))
  ledger.audit('payroll-rate-recorded',{'rateId':id_,'employeeId':employee['id'],'effectiveDate':effective})
 return {'id':id_}

def save_provider(ledger,value):
 id_=text(value.get('id'),'provider identifier',80);need(re.fullmatch('[a-z0-9_-]+',id_),'Use a provider identifier with letters, digits, underscores or hyphens')
 payload={'id':id_,'name':text(value.get('name'),'provider name',100),'earningCodes':value.get('earningCodes') or {},'specification':str(value.get('specification') or '')[:1000],
  'verifiedImport':value.get('verifiedImport') is True,'csvColumns':value.get('csvColumns') or {}}
 need(isinstance(payload['earningCodes'],dict) and isinstance(payload['csvColumns'],dict),'Provider mappings must be objects')
 need(not payload['verifiedImport'] or payload['specification'] and payload['csvColumns'],'Record the actual verified provider import specification and column mapping before enabling provider-format exports')
 allowed={'batchId','providerEmployeeId','employeeId','employee','departmentId','regularHours','overtimeHours','paidLeaveHours','hourlyRate','overtimeRate','salary','bonus','commission','otherEarnings','reimbursement','approvedDeductions','grossPay','payDate','periodStart','periodEndExclusive','regularCode','overtimeCode','bonusCode','commissionCode','otherCode','leaveCode','reimbursementCode','deductionCode'}
 need(set(payload['csvColumns'])<=allowed,'The CSV mapping contains an unsupported payroll field')
 for k,v in payload['earningCodes'].items():need(k in {'regular','overtime','bonus','commission','other','leave','reimbursement','deduction'} and re.fullmatch('[A-Za-z0-9_.-]{1,60}',str(v)),'Invalid provider earnings code')
 with ledger.db:
  ledger.db.execute('INSERT INTO pm_providers VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(id_,canonical(payload),now()));ledger.audit('payroll-provider-mapping-saved',{'providerId':id_,'verifiedImport':payload['verifiedImport']})
 return payload

def save_mapping(ledger,value):
 provider=text(value.get('providerId'),'provider');need(ledger.db.execute('SELECT 1 FROM pm_providers WHERE id=?',(provider,)).fetchone(),'Configure this provider first')
 employee=text(value.get('employeeId'),'Employee ID');need(ledger.db.execute('SELECT 1 FROM pm_employees WHERE id=?',(employee,)).fetchone(),'Choose an Employee profile')
 remote=text(value.get('providerEmployeeId'),'provider employee ID',100);need(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',remote),'Use the actual provider employee identifier')
 with ledger.db:
  ledger.db.execute('INSERT INTO pm_mappings VALUES(?,?,?) ON CONFLICT(provider_id,employee_id) DO UPDATE SET provider_employee_id=excluded.provider_employee_id',(provider,employee,remote));ledger.audit('payroll-provider-employee-linked',{'employeeId':employee,'providerId':provider})
 return {'saved':True}

def calculate_entry(value):
 pay_type=value.get('payType');need(pay_type in {'hourly','salary'},'Choose hourly or salary')
 regular=decimal(value.get('regularMinutes',0),'regular minutes');overtime=decimal(value.get('overtimeMinutes',0),'overtime minutes');leave=decimal(value.get('paidLeaveMinutes',0),'paid leave minutes')
 tracked_overtime=overtime
 if pay_type=='salary' and value.get('_verifiedSalaryExempt'):
  regular+=overtime;overtime=Decimal(0)
 rate=number(value.get('rateCents',0),'hourly rate');ot_rate=number(value.get('overtimeRateCents',0),'overtime rate')
 salary=number(value.get('salaryCents',0),'salary for this pay period')
 need(not overtime or ot_rate>0,'Enter the approved overtime rate; it is not guessed')
 need(pay_type!='salary' or salary>0,'Enter the actual salary for this payroll period; annual salaries are not automatically prorated')
 need(pay_type!='hourly' or rate>0,'Enter the hourly rate')
 need(pay_type!='hourly' or not salary,'Choose Salary when entering a salary amount; it cannot be added as an hourly rate')
 need(pay_type=='salary' or not leave or rate>0,'Enter the actual rate used for paid leave')
 base=rounded(regular*rate/60) if pay_type=='hourly' else salary
 ot=rounded(overtime*ot_rate/60);pto=0 if pay_type=='salary' else rounded(leave*rate/60)
 extra={key:number(value.get(key,0),key) for key in ['bonusCents','commissionCents','otherEarningsCents','reimbursementCents','approvedDeductionCents']}
 gross=base+ot+pto+extra['bonusCents']+extra['commissionCents']+extra['otherEarningsCents']
 need(gross<=100_000_000,'Gross wages exceed the supported entry limit')
 need(extra['approvedDeductionCents']<=gross,'Planned deductions exceed gross wages')
 employer=value.get('verifiedEmployerCostCents')
 if employer is not None:
  number(employer,'verified employer cost');need(value.get('employerCostReference'),'Record the source of the configured employer-cost estimate')
 return {'regularMinutes':str(regular),'overtimeMinutes':str(overtime),'trackedOvertimeMinutes':str(tracked_overtime),'paidLeaveMinutes':str(leave),'regularGrossCents':base,'overtimeGrossCents':ot,'paidLeaveGrossCents':pto,'grossCents':gross,
  **extra,'employerLaborCostCents':gross+extra['reimbursementCents']+employer if employer is not None else None}

def effective_rate(ledger,employee,assignment,start,end):
 rows=list(ledger.db.execute('SELECT * FROM pm_rates WHERE employee_id=? AND assignment_id=? AND effective_date<? ORDER BY effective_date,created_at',(employee,assignment,end)))
 need(not any(r['effective_date']>start for r in rows),'Compensation changes inside this period. Split the payroll entry at the verified effective date')
 return json.loads(rows[-1]['payload']) if rows else None

def prepare_entries(ledger,value):
 start,end=day(value.get('periodStart')),day(value.get('periodEndExclusive'));need(start<end and (date.fromisoformat(end)-date.fromisoformat(start)).days<=366,'Choose a valid payroll period, with an exclusive end date')
 company=text(value.get('companyId'),'Employee company');method=value.get('method');need(method in {'manual','approved_timecards'},'Choose manual payroll or approved timecards')
 inputs=value.get('entries',[]) if method=='manual' else [];claims=[]
 if method=='approved_timecards':
  for doc in ledger.db.execute("SELECT source_id,hash,payload FROM documents WHERE source='employees' ORDER BY source_id"):
   approved=ledger.db.execute('SELECT hash FROM pm_feed_sources WHERE source_id=?',(doc['source_id'],)).fetchone()
   if not approved or approved['hash']!=doc['hash']:continue
   data=json.loads(doc['payload']);original=data['original'];r=original['record']
   if original['company']['id']!=company:continue
   if data['kind']=='employee-timesheet':
    if r['start']>=end or r['endExclusive']<=start:continue
    need(r['start']>=start and r['endExclusive']<=end,'Include the complete approved timesheet period')
    for assignment in r['assignments']:
     inputs.append({'employeeId':r['employeeId'],'assignmentId':assignment['assignmentId'],'payType':assignment['payType'],'regularMinutes':assignment['regularMinutes'],'overtimeMinutes':assignment['overtimeMinutes'],
      'rateCents':assignment['rateCents'],'overtimeRateCents':assignment.get('overtimeRateCents') or (0 if not decimal(assignment['overtimeMinutes'],'overtime minutes') else None),
      '_approvedRegularCents':assignment.get('regularCents'),'_approvedOvertimeCents':assignment.get('overtimeCents'),'_sourceId':doc['source_id'],'_sourceHash':doc['hash']})
    claims.append(doc['source_id'])
   elif data['kind']=='employee-time-off' and r['paidMinutes']:
    a,b=r['start'][:10],r['end'][:10]
    if a>=end or b<start:continue
    need(a>=start and b<end,'Include the complete reviewed paid-leave interval')
    inputs.append({'employeeId':r['employeeId'],'assignmentId':r['assignmentId'],'payType':'hourly','regularMinutes':0,'overtimeMinutes':0,'paidLeaveMinutes':r['paidMinutes'],'rateCents':r['rateCents'],'_sourceId':doc['source_id'],'_sourceHash':doc['hash']});claims.append(doc['source_id'])
 if method=='approved_timecards':
  salary={};merged=[]
  for item in inputs:
   employee=ledger.db.execute('SELECT jobs FROM pm_employees WHERE id=?',(item['employeeId'],)).fetchone()
   job=next((j for j in json.loads(employee[0]) if j['id']==item['assignmentId']),None) if employee else None
   if job and '_approvedRegularCents' in item:need(item['payType']==job['pay_type'],'The approved timecard pay type differs from the current Employee job; review compensation history before manual payroll preparation')
   if job and job['pay_type']=='salary':
    key=(item['employeeId'],item['assignmentId'])
    current=salary.get(key)
    if not current:
     current={**item,'payType':'salary','regularMinutes':'0','overtimeMinutes':'0','paidLeaveMinutes':'0','_sourceRefs':[]};salary[key]=current;merged.append(current)
    for field in ['regularMinutes','overtimeMinutes','paidLeaveMinutes']:current[field]=str(decimal(current.get(field,0),field)+decimal(item.get(field,0),field))
    current['_sourceRefs'].append({'id':item['_sourceId'],'hash':item['_sourceHash']})
   else:merged.append(item)
  inputs=merged
 need(isinstance(inputs,list) and 1<=len(inputs)<=10000,'Add payroll entries or retrieve approved Employee hours first')
 additions=value.get('additions') or [];need(isinstance(additions,list) and len(additions)<=10000,'Invalid additional earnings')
 extra_fields={'bonusCents','commissionCents','otherEarningsCents','reimbursementCents','approvedDeductionCents','verifiedEmployerCostCents','employerCostReference','salaryCents','overtimeRateCents','reference'}
 extra={}
 for item in additions:
  need(method=='approved_timecards' and isinstance(item,dict) and set(item)<={'employeeId','assignmentId',*extra_fields},'Additional earnings must refer to approved timecard employees and contain only documented earnings')
  key=(item.get('employeeId'),item.get('assignmentId'));need(key not in extra,'Combine additions for the same employee/job in one line');extra[key]=item
 used_extra=set()
 entries=[];issues=[]
 for index,item in enumerate(inputs):
  need(isinstance(item,dict),'Invalid payroll entry')
  employee=ledger.db.execute('SELECT * FROM pm_employees WHERE id=?',(item.get('employeeId'),)).fetchone();need(employee and employee['company_id']==company,'Choose an existing Employee from the selected company')
  if employee['status']!='active':issues.append('Review final or historical pay for inactive employee '+employee['name'])
  jobs=json.loads(employee['jobs']);job=next((j for j in jobs if j['id']==item.get('assignmentId')),None);need(job,'Select the employee’s actual assigned job/department')
  source=dict(item)
  extra_key=(employee['id'],job['id']);extra_config=extra.get(extra_key);extra_item=extra_config if extra_key not in used_extra else None
  if extra_config and 'overtimeRateCents' in extra_config:
   source['overtimeRateCents']=number(extra_config['overtimeRateCents'],'period overtime rate');source['_periodOvertimeRateOverride']=True
  if extra_item:
   text(extra_item.get('reference'),'the approved additions / deduction authorization reference')
   source.update({k:v for k,v in extra_item.items() if k in extra_fields});used_extra.add(extra_key)
   issues.append('Review additions, deduction authorization and any bonus/commission effect on overtime for '+employee['name'])
  need(method!='manual' or set(item)<={'employeeId','assignmentId','payType','regularMinutes','overtimeMinutes','paidLeaveMinutes','rateCents','overtimeRateCents','salaryCents','bonusCents','commissionCents','otherEarningsCents','reimbursementCents','approvedDeductionCents','verifiedEmployerCostCents','employerCostReference'},'Only documented payroll inputs are accepted; do not upload bank details, SSNs or tax forms')
  override=effective_rate(ledger,employee['id'],job['id'],start,end)
  if override:
   need(method!='approved_timecards' or override['payType']==job['pay_type'],'Automatic pay type differs from Employee. Update the actual job or use qualified manual payroll review')
   issues.append('Review the payroll compensation override against the Employee job for '+employee['name'])
   source.update(payType=override['payType'],rateCents=override['rateCents'],overtimeRateCents=override['overtimeRateCents'])
   if override['payType']=='salary':source['salaryCents']=override['rateCents']
  elif method=='approved_timecards' and source.get('payType')=='salary':source.setdefault('salaryCents',job['rate_cents'])
  if extra_config:
   for field in ['overtimeRateCents','salaryCents']:
    if field in extra_config:source[field]=number(extra_config[field],field)
  if method=='approved_timecards' and source.get('payType')=='salary':
   arrangement=job.get('salary_arrangement') or {}
   need(arrangement.get('exemption')=='verified_exempt' and arrangement.get('verified_by') and arrangement.get('verification'),'Verify the actual salary exemption and pay frequency in Employee before automatic salary preparation; use reviewed manual payroll for provider-approved nonexempt/prorated salary')
   frequency=value.get('frequency');need(frequency==arrangement.get('frequency'),'Choose the actual salary pay frequency verified in Employee')
   days=(date.fromisoformat(end)-date.fromisoformat(start)).days;limits={'weekly':(7,7),'biweekly':(14,14),'semimonthly':(13,16),'monthly':(28,31)}
   need(frequency in limits and limits[frequency][0]<=days<=limits[frequency][1],'Salary period does not match the verified pay frequency')
   need(job['effective_date']<=start and (not job.get('end_date') or job['end_date']>=(date.fromisoformat(end)-timedelta(days=1)).isoformat()),'Partial-period salary needs an actual provider-reviewed amount; use manual payroll rather than automatic proration')
   source['_verifiedSalaryExempt']=True;source['_salaryVerification']=arrangement
  if method=='approved_timecards' and source.get('overtimeRateCents') is None:
   # Use the actual reviewed Employee wage allocation, not a made-up statutory multiplier.
   ot=decimal(source['overtimeMinutes'],'overtime minutes');actual=source.get('_approvedOvertimeCents')
   need(actual is not None,'The approved overtime allocation is incomplete; review it in Employee')
   source['overtimeRateCents']=rounded(Decimal(actual)*60/ot) if ot else 0
  result=calculate_entry(source)
  if method=='approved_timecards' and source['payType']=='hourly' and not override:
   # Employee may split subminute allocations; preserve reviewed cent totals.
   # A verified exempt salary never acquires a second hourly/OT wage payment.
   for original,calculated in [('_approvedRegularCents','regularGrossCents'),('_approvedOvertimeCents','overtimeGrossCents')]:
    if original=='_approvedOvertimeCents' and source.get('_periodOvertimeRateOverride'):continue
    if source.get(original) is not None:
     actual=number(source[original],'approved wage allocation');difference=actual-result[calculated]
     result['grossCents']+=difference;result[calculated]=actual
     if result['employerLaborCostCents'] is not None:result['employerLaborCostCents']+=difference
  if source['payType']=='salary':issues.append('Review salary classification, period amount and any overtime for '+employee['name'])
  if method=='manual':issues.append('Review manually entered workweek hours, overtime and approved additions for '+employee['name'])
  entry={'id':str(index),'method':method,'employeeId':employee['id'],'employee':employee['name'],'username':employee['username'],'firebaseUid':employee['uid'],'assignmentId':job['id'],'departmentId':job['division_id'],'department':job['division_name'],
   'inputs':source,'calculation':result,'sourceId':item.get('_sourceId'),'sourceHash':item.get('_sourceHash'),'rateOverride':bool(override or source.get('_periodOvertimeRateOverride')),'sourceRefs':item.get('_sourceRefs') or ([{'id':item['_sourceId'],'hash':item['_sourceHash']}] if item.get('_sourceId') else [])}
  entries.append(entry)
 if method=='approved_timecards':
  for employee_id in {e['employeeId'] for e in entries}:
   wages=[e for e in entries if e['employeeId']==employee_id];salaries={e['assignmentId'] for e in wages if e['inputs']['payType']=='salary'}
   need(len(salaries)<=1 and (not salaries or all(e['inputs']['payType']=='salary' for e in wages)),'Mixed hourly/salary or multiple salary arrangements need qualified manual payroll review')
 need(set(extra)==used_extra,'An additional-earnings line has no matching approved timecard job; prepare manual payroll for that employee instead')
 return start,end,company,entries,claims,sorted(set(issues))

def create_batch(ledger,value):
 key=text(value.get('requestKey'),'unique batch request key',100);fingerprint=hashlib.sha256(canonical(value).encode()).hexdigest()
 old=ledger.db.execute('SELECT * FROM pm_batches WHERE request_key=?',(key,)).fetchone()
 if old:need(old['request_hash']==fingerprint,'The batch request ID was reused for different payroll');return batch_value(ledger,old['id'])
 start,end,company,entries,claims,issues=prepare_entries(ledger,value);pay_date=day(value.get('payDate'));provider=text(value.get('providerId'),'payroll provider')
 need(ledger.db.execute('SELECT 1 FROM pm_providers WHERE id=?',(provider,)).fetchone(),'Configure the external provider or manual HR.my workflow first')
 employees={e['employeeId'] for e in entries}
 ledger.db.execute('BEGIN IMMEDIATE')
 try:
  for row in ledger.db.execute("SELECT * FROM pm_batches WHERE company_id=? AND status!='cancelled' AND starts_on<? AND ends_on>?",(company,end,start)):
   previous=json.loads(row['payload']);need(not employees.intersection(e['employeeId'] for e in previous['entries']),'This employee already has a payroll batch overlapping this period; open that batch instead of duplicating hours')
  id_=str(uuid.uuid4());payload={'entries':entries,'issues':issues,'review':None,'approval':None}
  ledger.db.execute('INSERT INTO pm_batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(id_,key,fingerprint,company,start,end,pay_date,provider,'draft',canonical(payload),now(),ACTOR.get()))
  for source in set(claims):ledger.db.execute('INSERT INTO pm_claims VALUES(?,?)',(source,id_))
  ledger.audit('payroll-batch-prepared',{'batchId':id_,'method':value['method'],'entries':len(entries)});ledger.db.commit()
 except Exception:ledger.db.rollback();raise
 return batch_value(ledger,id_)

def validate_sources(ledger,batch):
 for entry in batch['payload']['entries']:
  for source in entry.get('sourceRefs',[]):
   doc=ledger.db.execute("SELECT hash FROM documents WHERE source='employees' AND source_id=?",(source['id'],)).fetchone()
   current=ledger.db.execute('SELECT hash FROM pm_feed_sources WHERE source_id=?',(source['id'],)).fetchone()
   need(doc and current and doc['hash']==current['hash']==source['hash'],'Approved Employee hours changed or approval was withdrawn; review the original in Employee before continuing payroll')

def review_batch(ledger,value):
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'draft','reviewed'},'Only an unapproved payroll draft can be reviewed');validate_sources(ledger,batch)
 need(value.get('reviewed') is True and value.get('overtimeReviewed') is True,'Review all employee pay, source hours, overtime, salary classification and additions')
 reason=text(value.get('reason'),'the payroll review reference')
 before=canonical(batch['payload']);payload=json.loads(before);payload['review']={'by':ACTOR.get(),'at':now(),'reason':reason,'overtimeReviewed':True}
 with ledger.db:
  result=ledger.db.execute("UPDATE pm_batches SET status='reviewed',payload=? WHERE id=? AND status IN ('draft','reviewed') AND payload=?",(canonical(payload),batch['id'],before))
  need(result.rowcount==1,'Payroll changed during review; refresh before continuing')
  ledger.audit('payroll-batch-reviewed',{'batchId':batch['id']})
 return batch_value(ledger,batch['id'])

def totals(batch):
 groups={}
 for entry in batch['payload']['entries']:
  group=groups.setdefault(entry['departmentId'],{'departmentId':entry['departmentId'],'department':entry['department'],'grossCents':0,'reimbursementCents':0,'plannedDeductionsCents':0,'employerLaborCostCents':0})
  c=entry['calculation'];group['grossCents']+=c['grossCents'];group['reimbursementCents']+=c['reimbursementCents'];group['plannedDeductionsCents']+=c['approvedDeductionCents']
  group['employerLaborCostCents']=None if group['employerLaborCostCents'] is None or c['employerLaborCostCents'] is None else group['employerLaborCostCents']+c['employerLaborCostCents']
 return list(groups.values())

def approve_batch(ledger,value):
 batch=batch_value(ledger,value.get('id'))
 if batch['status'] in {'approved','exported','receipt_confirmed','final_posted','reconciled'}:return batch
 need(batch['status']=='reviewed' and batch['payload']['review'],'Review this payroll batch before approving')
 need(value.get('confirmed') is True,'Confirm approval of this exact gross-pay batch');validate_sources(ledger,batch)
 before=canonical(batch['payload']);payload=json.loads(before);payload['approval']={'by':ACTOR.get(),'at':now()}
 provider=json.loads(ledger.db.execute('SELECT payload FROM pm_providers WHERE id=?',(batch['provider_id'],)).fetchone()[0])
 payload['providerSnapshot']=provider;payload['providerEmployees']={r['employee_id']:r['provider_employee_id'] for r in ledger.db.execute('SELECT * FROM pm_mappings WHERE provider_id=?',(batch['provider_id'],))}
 documents=[]
 for group in totals(batch):
  if not group['grossCents']:continue
  original={'id':batch['id']+':'+group['departmentId'],'date':batch['pay_date'],'batchId':batch['id'],'companyId':batch['company_id'],'departmentId':group['departmentId'],'department':group['department'],'memo':'Approved gross payroll accrual · '+group['department']}
  documents.append(record('payroll-accrual',original,pair('5200','2270',group['grossCents']),amount=group['grossCents'],balance=group['grossCents']))
 def commit(db):
  updated=db.execute("UPDATE pm_batches SET status='approved',payload=? WHERE id=? AND status='reviewed' AND payload=?",(canonical(payload),batch['id'],before));need(updated.rowcount==1,'Payroll changed during approval; refresh before continuing')
  ledger.audit('payroll-batch-approved',{'batchId':batch['id']})
 ledger.import_documents('manual',documents,{'payrollBatchId':batch['id']},'Approved gross payroll accrual',accounts=[('2270','Approved Gross Payroll Accrual','liability')],commit_hook=commit)
 return batch_value(ledger,batch['id'])

def cancel_batch(ledger,value):
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'draft','reviewed'},'Approved/exported payroll requires an audited financial correction, not draft cancellation')
 reason=text(value.get('reason'),'cancellation reason')
 with ledger.db:
  ledger.db.execute("UPDATE pm_batches SET status='cancelled' WHERE id=? AND status IN ('draft','reviewed')",(batch['id'],));ledger.db.execute('DELETE FROM pm_claims WHERE batch_id=?',(batch['id'],));ledger.audit('payroll-draft-cancelled',{'batchId':batch['id'],'reason':reason})
 return batch_value(ledger,batch['id'])

def confirm_receipt(ledger,value):
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'approved','exported','receipt_confirmed'},'Approve the exact batch, then obtain actual provider confirmation')
 reference=text(value.get('reference'),'the actual provider receipt reference',200);evidence=text(value.get('evidence'),'the provider-confirmed receipt evidence',2000)
 need(value.get('providerConfirmed') is True,'Confirm the external provider actually acknowledged this batch; a download is not a submission')
 old=ledger.db.execute('SELECT * FROM pm_receipts WHERE batch_id=?',(batch['id'],)).fetchone()
 if old:need(old['reference']==reference,'A different provider receipt is already recorded for this batch');return batch_value(ledger,batch['id'])
 with ledger.db:
  ledger.db.execute('INSERT INTO pm_receipts VALUES(?,?,?,?,?,?)',(batch['id'],batch['provider_id'],reference,evidence,now(),ACTOR.get()));ledger.db.execute("UPDATE pm_batches SET status='receipt_confirmed' WHERE id=?",(batch['id'],));ledger.audit('payroll-provider-receipt-confirmed',{'batchId':batch['id']})
 return batch_value(ledger,batch['id'])

def export_rows(batch):
 snapshot=batch['payload'];provider=snapshot['providerSnapshot'];rows=[]
 for e in snapshot['entries']:
  c=e['calculation'];v=e['inputs'];codes=provider.get('earningCodes',{})
  rows.append({'batchId':batch['id'],'providerEmployeeId':snapshot['providerEmployees'].get(e['employeeId'],''),'employeeId':e['employeeId'],'employee':e['employee'],'departmentId':e['departmentId'],
   'regularHours':Decimal(c['regularMinutes'])/60,'overtimeHours':Decimal(c['overtimeMinutes'])/60,'paidLeaveHours':Decimal(c['paidLeaveMinutes'])/60,
   'hourlyRate':Decimal(v.get('rateCents',0))/100,'overtimeRate':Decimal(v.get('overtimeRateCents',0))/100,'salary':Decimal(v.get('salaryCents',0))/100,
   'bonus':Decimal(c['bonusCents'])/100,'commission':Decimal(c['commissionCents'])/100,'otherEarnings':Decimal(c['otherEarningsCents'])/100,'reimbursement':Decimal(c['reimbursementCents'])/100,
   'approvedDeductions':Decimal(c['approvedDeductionCents'])/100,'grossPay':Decimal(c['grossCents'])/100,'payDate':batch['pay_date'],'periodStart':batch['starts_on'],'periodEndExclusive':batch['ends_on'],
   **{name+'Code':codes.get(name,'') for name in ['regular','overtime','bonus','commission','other','leave','reimbursement','deduction']}})
 return rows

def csv_cell(value):
 if isinstance(value,Decimal):return format(value.quantize(Decimal('.000001')),'f').rstrip('0').rstrip('.') or '0'
 value=str(value)
 return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value

def workbook(sheets):
 out=io.BytesIO()
 def xml_file(archive,name,value):
  info=zipfile.ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,value.encode('utf-8'))
 def column(index):
  result=''
  while index:index,n=divmod(index-1,26);result=chr(65+n)+result
  return result
 with zipfile.ZipFile(out,'w') as archive:
  xml_file(archive,'[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join('<Override PartName="/xl/worksheets/sheet'+str(i)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
  xml_file(archive,'_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  xml_file(archive,'xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join('<sheet name="'+name+'" sheetId="'+str(i)+'" r:id="rId'+str(i)+'"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>')
  xml_file(archive,'xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join('<Relationship Id="rId'+str(i)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>' for i in range(1,len(sheets)+1))+'</Relationships>')
  for i,(_,rows) in enumerate(sheets,1):
   body=[]
   for r,values in enumerate(rows,1):
    cells=[]
    for c,v in enumerate(values,1):
     ref=column(c)+str(r)
     cells.append('<c r="'+ref+'"><v>'+str(v)+'</v></c>' if type(v) in {int,float,Decimal} else '<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+escape(str(v))+'</t></is></c>')
    body.append('<row r="'+str(r)+'">'+''.join(cells)+'</row>')
   xml_file(archive,'xl/worksheets/sheet'+str(i)+'.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>'+''.join(body)+'</sheetData></worksheet>')
 return out.getvalue()

def export_batch(ledger,id_,format_):
 batch=batch_value(ledger,id_);need(batch['status'] in {'approved','exported','receipt_confirmed','final_posted','reconciled'},'Review and approve payroll before exporting')
 need(format_ in {'csv','xlsx','provider_csv','final_template'},'Choose CSV or Excel')
 old=ledger.db.execute('SELECT content FROM pm_exports WHERE batch_id=? AND format=?',(id_,format_)).fetchone()
 if old:return bytes(old[0])
 validate_sources(ledger,batch);rows=export_rows(batch)
 columns={key:key for key in rows[0]}
 if format_=='provider_csv':
  provider=batch['payload']['providerSnapshot'];need(provider['verifiedImport'] and provider['specification'],'This provider import format has not been verified; use the general review export')
  columns=provider['csvColumns'];need(all(r['providerEmployeeId'] for r in rows),'Map every employee to the actual provider ID before provider-format export')
 if format_=='final_template':
  output=io.StringIO(newline='');writer=csv.writer(output)
  writer.writerow(['batchId','entryId','employee','department','gross','employeeTaxes','deductions','netPay','reimbursement','employerTaxes','employerBenefits','fees'])
  for e in batch['payload']['entries']:writer.writerow([batch['id'],e['id'],csv_cell(e['employee']),csv_cell(e['department']),*['']*8])
  raw=output.getvalue().encode('utf-8-sig')
 elif format_ in {'csv','provider_csv'}:
  output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(columns.values())
  for row in rows:writer.writerow([csv_cell(row.get(key,'')) for key in columns])
  raw=output.getvalue().encode('utf-8-sig')
 else:
  departments=totals(batch)
  raw=workbook([('Payroll review',[list(columns)]+[[row[key] for key in columns] for row in rows]),
   ('Departments',[['Department','Gross wages','Reimbursements','Planned deductions','Employer labor cost estimate']]+[[r['department'],Decimal(r['grossCents'])/100,Decimal(r['reimbursementCents'])/100,Decimal(r['plannedDeductionsCents'])/100,Decimal(r['employerLaborCostCents'])/100 if r['employerLaborCostCents'] is not None else 'Not fully estimated'] for r in departments]),
   ('Control',[['Field','Value'],['Batch',id_],['Status','Approved export — not submitted or paid'],['Provider',batch['payload']['providerSnapshot']['name']],['Provider import specification',batch['payload']['providerSnapshot']['specification'] or 'General review format; provider compatibility not verified'],['Pay date',batch['pay_date']],['Employee time originals','Unchanged']])])
 with ledger.db:
  ledger.db.execute('INSERT OR IGNORE INTO pm_exports VALUES(?,?,?,?,?)',(id_,format_,hashlib.sha256(raw).hexdigest(),raw,now()))
  ledger.db.execute("UPDATE pm_batches SET status='exported' WHERE id=? AND status='approved'",(id_,));ledger.audit('payroll-approved-export-downloaded',{'batchId':id_,'format':format_,'providerReceipt':False})
 return bytes(ledger.db.execute('SELECT content FROM pm_exports WHERE batch_id=? AND format=?',(id_,format_)).fetchone()[0])

def post_final_report(ledger,value):
 need(set(value)<={'id','reference','actualProviderReport','postingDate','varianceReason','entries'},'Only payroll report totals are accepted; do not upload personal bank or tax-form data')
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'receipt_confirmed','final_posted','reconciled'},'Record the actual provider receipt before posting final payroll results')
 old=ledger.db.execute('SELECT * FROM pm_final_reports WHERE batch_id=?',(batch['id'],)).fetchone()
 if old:
  need(old['payload']==canonical(value),'A different final report is already posted. Use an audited correction rather than replacing payroll history')
  return batch_value(ledger,batch['id'])
 need(value.get('actualProviderReport') is True,'Confirm these actual figures came from the provider’s final payroll report')
 reference=text(value.get('reference'),'final provider report reference',200);posting=day(value.get('postingDate') or batch['pay_date'])
 actual=value.get('entries');need(isinstance(actual,list) and len(actual)==len(batch['payload']['entries']),'Supply one actual result for each employee/department payroll line')
 expected={e['id']:e for e in batch['payload']['entries']};seen=set();groups={};variance=False
 required=['grossCents','employeeTaxesCents','deductionsCents','netPayCents','reimbursementCents','employerTaxesCents','employerBenefitsCents','feesCents']
 for item in actual:
  need(isinstance(item,dict) and set(item)<={'entryId',*required},'Only the documented payroll totals are accepted; do not upload SSNs, bank details or tax forms')
  entry=expected.get(str(item.get('entryId')));need(entry and entry['id'] not in seen,'Invalid or duplicate final payroll line');seen.add(entry['id'])
  amounts={k:number(item.get(k),k) for k in required}
  need(amounts['netPayCents']==amounts['grossCents']-amounts['employeeTaxesCents']-amounts['deductionsCents']+amounts['reimbursementCents'],'Actual net pay does not reconcile to gross, provider taxes, deductions and reimbursements')
  c=entry['calculation'];variance|=any(amounts[k]!=c[other] for k,other in [('grossCents','grossCents'),('deductionsCents','approvedDeductionCents'),('reimbursementCents','reimbursementCents')])
  group=groups.setdefault(entry['departmentId'],{'department':entry['department'],**{k:0 for k in required}})
  for key,amount in amounts.items():group[key]+=amount
 if variance or posting!=batch['pay_date']:text(value.get('varianceReason'),'the reviewed variance or posting-date explanation',2000)
 documents=[]
 for group in totals(batch):
  if group['grossCents']:
   original={'id':batch['id']+':'+group['departmentId'],'date':posting,'batchId':batch['id'],'companyId':batch['company_id'],'departmentId':group['departmentId'],'memo':'Reverse approved gross accrual on final payroll · '+group['department']}
   documents.append(record('payroll-accrual-final-reversal',original,pair('2270','5200',group['grossCents']),amount=group['grossCents']))
 for department,g in groups.items():
  lines=[]
  for account,amount in [('5200',g['grossCents']),('5230',g['reimbursementCents']),('5210',g['employerTaxesCents']),('5220',g['employerBenefitsCents']),('5800',g['feesCents'])]:
   if amount:lines.append(line(account,debit=amount))
  for account,amount in [('2160',g['employeeTaxesCents']+g['employerTaxesCents']),('2155',g['deductionsCents']),('2250',g['netPayCents']),('2280',g['feesCents']),('2290',g['employerBenefitsCents'])]:
   if amount:lines.append(line(account,credit=amount))
  original={'id':batch['id']+':'+department,'date':posting,'batchId':batch['id'],'companyId':batch['company_id'],'departmentId':department,'department':g['department'],'providerReference':reference,'actualReport':value,'memo':'Actual provider payroll result · '+g['department']}
  documents.append(record('payroll-final',original,lines,amount=g['grossCents'],balance=g['netPayCents']))
 def commit(db):
  need(db.execute("UPDATE pm_batches SET status='final_posted' WHERE id=? AND status='receipt_confirmed'",(batch['id'],)).rowcount==1,'Payroll state changed; refresh the existing final report')
  db.execute('INSERT INTO pm_final_reports VALUES(?,?,?,?,?)',(batch['id'],batch['provider_id'],reference,canonical(value),now()));ledger.audit('payroll-final-provider-report-posted',{'batchId':batch['id']})
 ledger.import_documents('manual',documents,{'payrollBatchId':batch['id']},'Actual final provider payroll',accounts=[('5230','Employee Reimbursements','expense'),('2280','Payroll Processing Fees Payable','liability'),('2290','Employer Benefits Payable','liability')],commit_hook=commit)
 return batch_value(ledger,batch['id'])

LIABILITIES={'netPay':'2250','taxes':'2160','deductions':'2155','fees':'2280','benefits':'2290'}

def remaining(ledger,id_):
 report=ledger.db.execute('SELECT payload FROM pm_final_reports WHERE batch_id=?',(id_,)).fetchone();need(report,'Record the final provider report first')
 total={kind:0 for kind in LIABILITIES}
 for row in json.loads(report[0])['entries']:
  total['netPay']+=row['netPayCents'];total['taxes']+=row['employeeTaxesCents']+row['employerTaxesCents'];total['deductions']+=row['deductionsCents'];total['fees']+=row['feesCents'];total['benefits']+=row['employerBenefitsCents']
 for row in ledger.db.execute('SELECT payload FROM pm_payments WHERE batch_id=?',(id_,)):
  for kind,amount in json.loads(row[0])['allocations'].items():total[kind]-=amount
 return total

def record_payment(ledger,value):
 need(set(value)<={'id','reference','actualPayment','allocations','date','bankLineId','reclassifyExpense','reason'},'Only settlement references and amounts are accepted; no bank account numbers are needed')
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'final_posted','reconciled'},'Post the actual final payroll report before recording settlement')
 reference=text(value.get('reference'),'actual bank/provider payment reference',200);old=ledger.db.execute('SELECT * FROM pm_payments WHERE reference=?',(reference,)).fetchone()
 if old:
  need(old['batch_id']==batch['id'] and json.loads(old['payload'])==value,'This bank reference already belongs to another payment');return batch_value(ledger,batch['id'])
 need(value.get('actualPayment') is True,'Confirm this payment already occurred; this app does not send money')
 allocations=value.get('allocations');need(isinstance(allocations,dict) and allocations and set(allocations)<=set(LIABILITIES),'Choose the actual liability amounts included in this bank payment')
 allocations={kind:number(amount,kind) for kind,amount in allocations.items()};outstanding=remaining(ledger,batch['id'])
 need(sum(allocations.values())>0,'Payment must be greater than zero')
 for kind,amount in allocations.items():need(amount<=outstanding[kind],'This payment exceeds the remaining '+kind+' liability')
 amount=sum(allocations.values());posting=day(value.get('date'));id_=str(uuid.uuid4());bank_line=value.get('bankLineId');documents=[]
 rows=[line(LIABILITIES[k],debit=n) for k,n in allocations.items() if n]
 if bank_line is not None:
  need(type(bank_line) is int,'Choose an existing bank credit line ID')
  matched=ledger.db.execute('SELECT * FROM lines WHERE id=? AND account=\'1020\' AND credit=? AND debit=0',(bank_line,amount)).fetchone();need(matched,'The existing bank transaction must match this exact payment amount')
  others=list(ledger.db.execute('SELECT l.*,a.type FROM lines l JOIN accounts a ON a.code=l.account WHERE entry_id=? AND id!=?',(matched['entry_id'],bank_line)))
  posted={r['account']:r['debit'] for r in others if r['debit']}
  expected={LIABILITIES[k]:n for k,n in allocations.items() if n}
  if posted!=expected:
   need(len(others)==1 and others[0]['type']=='expense' and others[0]['debit']==amount and not others[0]['credit'],'This bank transaction needs a Finance-reviewed allocation; no second bank deduction was posted')
   need(value.get('reclassifyExpense') is True and value.get('reason'),'Approve the documented reclassification of this existing bank expense')
   need(not ledger.db.execute('SELECT 1 FROM reconciliation_lines WHERE line_id=?',(bank_line,)).fetchone(),'This expense is already reconciled; review its correction in Finance')
   rows.append(line(others[0]['account'],credit=amount))
   documents.append(record('payroll-bank-reclassification',{'id':id_,'date':posting,'batchId':batch['id'],'companyId':batch['company_id'],'bankLineId':bank_line,'reference':reference,'memo':'Reclassify existing bank expense to actual payroll liabilities'},rows,amount=amount))
 else:
  rows.append(line('1020',credit=amount));documents.append(record('payroll-bank-payment',{'id':id_,'date':posting,'batchId':batch['id'],'companyId':batch['company_id'],'reference':reference,'memo':'Record actual payroll bank settlement'},rows,amount=amount))
 def commit(db):
  latest=remaining(ledger,batch['id'])
  for kind,n in allocations.items():need(n<=latest[kind],'This payroll liability was already settled; refresh before retrying')
  line_id=bank_line
  if line_id is None:
   line_id=db.execute("SELECT l.id FROM lines l JOIN entries e ON e.id=l.entry_id WHERE e.source='manual' AND e.source_id=? AND l.account='1020' AND l.credit=?",('payroll-bank-payment:'+id_,amount)).fetchone()[0]
  db.execute('INSERT INTO pm_payments VALUES(?,?,?,?,?,?,?,?)',(id_,batch['id'],'allocated',reference,amount,line_id,canonical(value),now()));ledger.audit('payroll-actual-bank-settlement-recorded',{'batchId':batch['id'],'bankLineId':line_id})
 ledger.import_documents('manual',documents,{'payrollBatchId':batch['id']},'Actual payroll bank settlement',commit_hook=commit)
 return batch_value(ledger,batch['id'])

def reconcile_batch(ledger,value):
 batch=batch_value(ledger,value.get('id'));need(batch['status'] in {'final_posted','reconciled'},'Post the final payroll report first')
 need(not any(remaining(ledger,batch['id']).values()),'Some actual payroll liabilities remain unpaid')
 payments=list(ledger.db.execute('SELECT bank_line_id FROM pm_payments WHERE batch_id=?',(batch['id'],)))
 need(all(ledger.db.execute('SELECT 1 FROM reconciliation_lines WHERE line_id=?',(p[0],)).fetchone() for p in payments),'Match every payroll bank line in Bank reconciliation before marking the batch reconciled')
 with ledger.db:ledger.db.execute("UPDATE pm_batches SET status='reconciled' WHERE id=?",(batch['id'],));ledger.audit('payroll-batch-bank-reconciled',{'batchId':batch['id']})
 return batch_value(ledger,batch['id'])

def state(ledger,user):
 require_payroll(user)
 return {'connection':settings(ledger),'lastSync':json.loads(ledger.settings().get('employee_payroll_last_sync','null')),
  'employees':[{**dict(r),'jobs':json.loads(r['jobs'])} for r in ledger.db.execute('SELECT * FROM pm_employees ORDER BY name')],
  'rates':[{**dict(r),'payload':json.loads(r['payload'])} for r in ledger.db.execute('SELECT * FROM pm_rates ORDER BY effective_date DESC,created_at DESC')],
  'providers':[json.loads(r[0]) for r in ledger.db.execute('SELECT payload FROM pm_providers ORDER BY id')],
  'mappings':[dict(r) for r in ledger.db.execute('SELECT * FROM pm_mappings')],
  'batches':[{**batch_value(ledger,r[0]),'totals':totals(batch_value(ledger,r[0])),'remaining':remaining(ledger,r[0]) if ledger.db.execute('SELECT 1 FROM pm_final_reports WHERE batch_id=?',(r[0],)).fetchone() else None,
    'receipt':dict(receipt) if (receipt:=ledger.db.execute('SELECT reference,evidence,confirmed_at,confirmed_by FROM pm_receipts WHERE batch_id=?',(r[0],)).fetchone()) else None,
    'payments':[dict(p) for p in ledger.db.execute('SELECT id,reference,amount,bank_line_id,created_at FROM pm_payments WHERE batch_id=?',(r[0],))]} for r in ledger.db.execute('SELECT id FROM pm_batches ORDER BY created_at DESC LIMIT 200')]}
