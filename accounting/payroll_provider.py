"""Gusto Embedded Payroll adapter, based on official SDK 0.16.3 / API 2025-06-15.

No credentials ship with the app. Live submissions require an authenticated owner,
fresh provider calculation, password confirmation, and explicit per-payroll approval.
"""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler,HTTPSHandler,ProxyHandler
from .ledger import AccountingError,cents,canonical,now,day
from .imports import record,pair,line

API_VERSION='2025-06-15'
SCHEMA='''
CREATE TABLE IF NOT EXISTS provider_reviews(payroll_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,payload TEXT NOT NULL,reviewed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provider_actions(payroll_id TEXT PRIMARY KEY,status TEXT NOT NULL,detail TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS provider_cache(kind TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
'''
STATES={
 'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California','CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia',
 'HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa','KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland',
 'MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi','MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire','NJ':'New Jersey',
 'NM':'New Mexico','NY':'New York','NC':'North Carolina','ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania','RI':'Rhode Island','SC':'South Carolina',
 'SD':'South Dakota','TN':'Tennessee','TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington','WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia'}


class ProviderError(AccountingError):
    def __init__(self,message,definitive=False,status=None):
        super().__init__(message);self.definitive=definitive;self.status=status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ProviderError('Payroll service redirected an authenticated request; no token was forwarded')


def safe_uuid(value):
    value=str(value)
    if not re.fullmatch(r'[a-fA-F0-9-]{36}',value):raise AccountingError('Expected a payroll service UUID')
    return value


class SecretStore:
    def __init__(self,directory):self.path=Path(directory)/'payroll-connection.dpapi'
    def read(self):
        env={'accessToken':os.environ.get('GUSTO_ACCESS_TOKEN'),'refreshToken':os.environ.get('GUSTO_REFRESH_TOKEN'),
             'clientId':os.environ.get('GUSTO_CLIENT_ID'),'clientSecret':os.environ.get('GUSTO_CLIENT_SECRET'),
             'companyId':os.environ.get('GUSTO_COMPANY_ID'),'environment':os.environ.get('GUSTO_ENVIRONMENT','demo')}
        if env['accessToken'] and env['companyId']:return {k:v for k,v in env.items() if v is not None}
        if not self.path.exists():return None
        if os.name!='nt':raise ProviderError('Saved Windows payroll credentials cannot be opened on this operating system. Use secure environment bindings here.')
        return json.loads(self.dpapi(self.path.read_bytes(),False))
    def save(self,value):
        if os.name!='nt':raise ProviderError('Use secure environment bindings for payroll credentials on this development machine. The Windows installer saves them with Windows account encryption.')
        encrypted=self.dpapi(canonical(value).encode(),True)
        temp=self.path.with_suffix('.tmp');temp.write_bytes(encrypted);temp.replace(self.path)
    @staticmethod
    def dpapi(data,encrypt):
        from ctypes import wintypes
        class Blob(ctypes.Structure):_fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]
        buffer=ctypes.create_string_buffer(data)
        incoming=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));out=Blob()
        crypt=ctypes.windll.crypt32
        crypt.CryptProtectData.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        crypt.CryptProtectData.restype=wintypes.BOOL
        crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype=wintypes.BOOL
        if encrypt:ok=crypt.CryptProtectData(ctypes.byref(incoming),'Backwoods Payroll',None,None,None,1,ctypes.byref(out))
        else:ok=crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(out))
        if not ok:raise ProviderError('Windows could not protect or open the payroll credentials')
        try:return ctypes.string_at(out.pbData,out.cbData)
        finally:
            free=ctypes.windll.kernel32.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
            free(out.pbData)


class Gusto:
    def __init__(self,directory,connection=None,transport=None):
        self.store=SecretStore(directory);self.connection=connection or self.store.read();self.transport=transport
        if not self.connection:raise ProviderError('Connect an approved Gusto Embedded Payroll account first')
        self.environment=self.connection.get('environment','demo')
        if self.environment not in {'demo','production'}:raise ProviderError('Choose demo or production payroll environment')
        self.host='api.gusto.com' if self.environment=='production' else 'api.gusto-demo.com'
        self.company=safe_uuid(self.connection.get('companyId',''))
    def request(self,method,path,body=None,refresh=True):
        if not path.startswith('/v1/') or '..' in path:raise ProviderError('Unsupported payroll service path')
        headers={'Authorization':'Bearer '+self.connection.get('accessToken',''),'X-Gusto-API-Version':API_VERSION,'Accept':'application/json','Content-Type':'application/json'}
        if self.transport:return self.transport(method,path,body,headers)
        try:
            req=Request('https://'+self.host+path,None if body is None else canonical(body).encode(),headers,method=method)
            with build_opener(NoRedirect()).open(req,timeout=30) as response:
                content=response.read(20*1024*1024+1)
                if len(content)>20*1024*1024:raise ProviderError('Payroll response exceeds supported size')
                return json.loads(content) if content else {'accepted':True,'httpStatus':response.status}
        except HTTPError as exc:
            if exc.code==401 and refresh and self.connection.get('refreshToken'):
                self.refresh();return self.request(method,path,body,False)
            # Do not echo provider bodies: they can contain employee tax IDs or bank information.
            raise ProviderError(f'Payroll service returned HTTP {exc.code}. Check account approval, scopes, company setup and payroll blockers.',definitive=400<=exc.code<500 and exc.code not in {408,429},status=exc.code) from None
        except (URLError,TimeoutError) as exc:
            raise ProviderError('Payroll service could not be reached. A submission may have an unknown outcome; refresh its status before taking further action.') from None
    def refresh(self):
        c=self.connection
        if not all(c.get(k) for k in ['clientId','clientSecret','refreshToken']):raise ProviderError('Payroll authorization expired. Reconnect the approved account.')
        body={'grant_type':'refresh_token','client_id':c['clientId'],'client_secret':c['clientSecret'],'refresh_token':c['refreshToken']}
        try:
            with build_opener(NoRedirect()).open(Request('https://'+self.host+'/oauth/token',canonical(body).encode(),{'Content-Type':'application/json'},method='POST'),timeout=30) as res:tokens=json.load(res)
        except Exception:raise ProviderError('Payroll authorization could not be refreshed; reconnect the account') from None
        self.connection={**c,'accessToken':tokens['access_token'],'refreshToken':tokens.get('refresh_token',c['refreshToken'])}
        self.store.save(self.connection)
    def company_info(self):return self.request('GET',f'/v1/companies/{self.company}')
    def payrolls(self):
        result=[]
        for page in range(1,101):
            batch=self.request('GET',f'/v1/companies/{self.company}/payrolls?per=100&page={page}&include=totals,payroll_status_meta&processing_statuses=processed,unprocessed&payroll_types=regular,off_cycle')
            if not isinstance(batch,list):raise ProviderError('Unexpected payroll list format')
            result.extend(batch)
            if len(batch)<100:return result
        raise ProviderError('Payroll history needs pagination beyond this app limit; narrow the period')
    def payroll(self,pid):return self.request('GET',f'/v1/companies/{self.company}/payrolls/{safe_uuid(pid)}?include=taxes,benefits,deductions')
    def flow(self,kind):
        types={'onboarding':'company_onboarding','run-payroll':'run_payroll','history':'payroll_history'}
        if kind not in types:raise ProviderError('Unknown payroll workflow')
        result=self.request('POST',f'/v1/companies/{self.company}/flows',{'flow_type':types[kind]})
        url=result.get('url')
        parsed=urlparse(str(url))
        if parsed.scheme!='https' or not (parsed.hostname or '').endswith(('.gusto.com','.gusto-demo.com')):
            raise ProviderError('Provider returned an unexpected workflow URL')
        return {'url':url,'expires':'Provider links expire after inactivity; generate a new link when needed.'}
    def prepare(self,pid):return self.request('PUT',f'/v1/companies/{self.company}/payrolls/{safe_uuid(pid)}/prepare',{})
    def calculate(self,pid):return self.request('PUT',f'/v1/companies/{self.company}/payrolls/{safe_uuid(pid)}/calculate')
    def submit(self,pid):return self.request('PUT',f'/v1/companies/{self.company}/payrolls/{safe_uuid(pid)}/submit',{})
    def pay_stub(self,pid,employee_id):
        path=f'/v1/payrolls/{safe_uuid(pid)}/employees/{safe_uuid(employee_id)}/pay_stub'
        headers={'Authorization':'Bearer '+self.connection.get('accessToken',''),'X-Gusto-API-Version':API_VERSION,'Accept':'application/pdf'}
        try:
            with build_opener(NoRedirect()).open(Request('https://'+self.host+path,headers=headers),timeout=30) as response:data=response.read(10*1024*1024+1)
        except Exception:raise ProviderError('The official pay stub is unavailable. Check provider access, payroll status and pay-stub scope.') from None
        if len(data)>10*1024*1024 or not data.startswith(b'%PDF'):raise ProviderError('Provider did not return a supported pay-stub PDF')
        return data


def safe_payroll(payroll):
    # Only display a selected payroll summary, never bank account or SSN fields.
    result={key:payroll.get(key) for key in ['payroll_uuid','uuid','version','check_date','processed','payroll_deadline','pay_period','totals','payroll_status_meta','processing_request']}
    result['taxes']=[{k:t.get(k) for k in ['name','employer','amount']} for t in payroll.get('taxes',[])]
    result['employees']=[{k:e.get(k) for k in ['employee_uuid','first_name','last_name','gross_pay','net_pay','check_amount','payment_method']} for e in payroll.get('employee_compensations',[])]
    return result


def fingerprint(payroll):
    return hashlib.sha256(canonical(payroll).encode()).hexdigest()


def review_payroll(ledger,client,pid):
    data=client.payroll(pid)
    if data.get('processed'):raise ProviderError('This payroll is already processed; refresh and sync its results')
    if not data.get('totals'):raise ProviderError('Payroll calculation has not completed. Calculate with the provider, then refresh for review.')
    if data.get('processing_request'):raise ProviderError('Payroll has an active processing request. Wait for provider confirmation.')
    digest=fingerprint(data)
    with ledger.db:
        ledger.db.execute('INSERT OR REPLACE INTO provider_reviews VALUES(?,?,?,?)',(pid,digest,canonical(data),now()))
        ledger.audit('provider-payroll-reviewed',{'payrollId':pid,'environment':client.environment,'companyId':client.company})
    return {'fingerprint':digest,'payroll':safe_payroll(data)}


def submit_payroll(ledger,client,pid,digest,confirmation):
    review=ledger.db.execute('SELECT * FROM provider_reviews WHERE payroll_id=?',(pid,)).fetchone()
    if not review or review['fingerprint']!=digest:raise ProviderError('Review the current payroll calculation before submitting')
    from datetime import datetime,timezone,timedelta
    if datetime.fromisoformat(review['reviewed_at'])<datetime.now(timezone.utc)-timedelta(minutes=15):raise ProviderError('Payroll review expired. Refresh and review it again.')
    old=ledger.db.execute('SELECT status FROM provider_actions WHERE payroll_id=?',(pid,)).fetchone()
    if old and old['status'] in {'submitting','submitted','unknown','processed'}:raise ProviderError('This submission is already pending, submitted, or uncertain. Refresh provider status; do not submit it again.')
    latest=client.payroll(pid)
    if latest.get('processed') or fingerprint(latest)!=digest:raise ProviderError('Provider payroll changed after your review. Refresh and review the new calculation.')
    expected='RUN PAYROLL '+str(latest.get('check_date',''))
    if confirmation!=expected:raise ProviderError('Type '+expected+' to approve this specific payroll')
    with ledger.db:
        ledger.db.execute('INSERT OR REPLACE INTO provider_actions VALUES(?,?,?,?)',(pid,'submitting','Owner approved; awaiting provider result',now()))
        ledger.audit('provider-payroll-submission-approved',{'payrollId':pid,'companyId':client.company,'environment':client.environment})
    try:response=client.submit(pid)
    except Exception as exc:
        rejected=isinstance(exc,ProviderError) and exc.definitive
        with ledger.db:
            ledger.db.execute('UPDATE provider_actions SET status=?,detail=?,updated_at=? WHERE payroll_id=?',('rejected' if rejected else 'unknown','Provider rejected the request; resolve blockers and review again' if rejected else 'Outcome unconfirmed; check provider before any retry',now(),pid))
            if rejected:ledger.db.execute('DELETE FROM provider_reviews WHERE payroll_id=?',(pid,))
        raise
    with ledger.db:ledger.db.execute('UPDATE provider_actions SET status=?,detail=?,updated_at=? WHERE payroll_id=?',('submitted','Accepted asynchronously; not a confirmation of employee payment',now(),pid))
    return {'status':'submitted','message':'Provider accepted the request. Processing and direct-deposit settlement must still be confirmed.'}


def accounting_document(payroll,company_id):
    if not payroll.get('processed'):raise ProviderError('Only provider-confirmed processed payroll can be posted')
    total=payroll.get('totals') or {}
    required=['gross_pay','net_pay','employee_taxes','employer_taxes']
    if any(k not in total for k in required):raise ProviderError('Provider payroll totals are incomplete; accounting sync needs review')
    amounts={k:cents(v or 0) for k,v in total.items() if isinstance(v,(int,float,str))}
    if any(v<0 for v in amounts.values()):raise ProviderError('Payroll reversals or negative components require a reviewed correcting journal')
    if any(amounts.get(k,0) for k in ['imputed_pay','owners_draw','deferred_payroll_taxes']):
        raise ProviderError('This payroll contains imputed pay, owner draws or deferred taxes. Review its accounting allocation before posting; provider processing is unaffected.')
    gross,net,employee_tax,employer_tax=[amounts[k] for k in required]
    deductions=amounts.get('employee_benefits_deductions',0)+amounts.get('other_deductions',0)
    reimbursement=amounts.get('reimbursements',0)
    # Reimbursements must reconcile to the provider's actual net-pay definition.
    cash_tips=amounts.get('employee_cash_tips',0);paycheck_tips=amounts.get('employee_paycheck_tips',0)
    if gross-employee_tax-deductions-cash_tips!=net or cash_tips+paycheck_tips>gross:
        raise ProviderError('Gross, deductions, reimbursements and net do not reconcile. Review the provider accounting report before posting.')
    rows=[]
    if gross-cash_tips-paycheck_tips:rows.append(line('5200',gross-cash_tips-paycheck_tips))
    if paycheck_tips:rows.append(line('2260',paycheck_tips))
    if employer_tax:rows.append(line('5210',employer_tax))
    if reimbursement:rows.append(line('5100',reimbursement))
    if amounts.get('benefits',0):rows.append(line('5220',amounts['benefits']));rows.append(line('2155',credit=amounts['benefits']))
    if net+reimbursement:rows.append(line('2250',credit=net+reimbursement))
    if employee_tax+employer_tax:rows.append(line('2160',credit=employee_tax+employer_tax))
    if deductions:rows.append(line('2155',credit=deductions))
    pid=safe_uuid(payroll.get('payroll_uuid') or payroll.get('uuid'))
    safe={**safe_payroll(payroll),'id':company_id+':'+pid,'date':day(payroll['check_date']),'memo':'Provider payroll accrual · bank and tax settlement pending','providerPayrollId':pid,'companyId':company_id}
    return record('provider-payroll',safe,rows,amount=gross,reference='Gusto '+pid)


def sync_payrolls(ledger,client):
    summaries=client.payrolls()
    docs=[];issues=[]
    for index,summary in enumerate(summaries):
        pid=summary.get('payroll_uuid') or summary.get('uuid')
        if not pid:raise ProviderError('Provider returned payroll without an ID')
        if summary.get('processed') and client.environment=='production':
            data=client.payroll(pid)
            summaries[index]=data
            try:docs.append(accounting_document(data,client.company))
            except AccountingError as exc:issues.append({'payrollId':pid,'message':str(exc)})
            with ledger.db:
                ledger.db.execute('UPDATE provider_actions SET status=?,detail=?,updated_at=? WHERE payroll_id=?',('processed','Provider reports payroll processed; verify bank settlement separately',now(),pid))
    result=ledger.import_documents('provider',docs,{'provider':'Gusto','environment':client.environment,'companyId':client.company,'payrolls':[safe_payroll(p) for p in summaries]},'Gusto payroll sync') if client.environment=='production' else {'added':0,'changed':0,'duplicates':0,'demo':True}
    if client.environment!='production':issues.append({'payrollId':'Demo environment','message':'Sandbox payroll was not posted to the company ledger.'})
    with ledger.db:ledger.db.execute('INSERT OR REPLACE INTO provider_cache VALUES(?,?,?)',('payrolls',canonical({'payrolls':[safe_payroll(p) for p in summaries],'issues':issues}),now()))
    return {**result,'issues':issues}
