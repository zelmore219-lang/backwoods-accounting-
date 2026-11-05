"""Scheduled official-source change detection, not a legal interpretation engine.

Provider tax calculations remain authoritative for a connected pay run. A changed
web page is queued for review and never converted into executable tax formulas.
"""
import difflib
import hashlib
from html.parser import HTMLParser
import json
import re
import threading
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from .ledger import AccountingError,canonical,now,day
from .payroll_provider import STATES

SOURCES={
 'US':'https://www.irs.gov/businesses/small-businesses-self-employed/employment-taxes',
 'AL':'https://www.revenue.alabama.gov/withholding-tax/', 'AK':'https://labor.alaska.gov/estax/',
 'AZ':'https://azdor.gov/business/withholding-tax','AR':'https://www.dfa.arkansas.gov/office/taxes/income-tax/withholding-tax/',
 'CA':'https://edd.ca.gov/en/payroll_taxes/','CO':'https://tax.colorado.gov/withholding-tax',
 'CT':'https://portal.ct.gov/drs/withholding-tax/withholding-tax','DE':'https://revenue.delaware.gov/withholding/',
 'FL':'https://floridarevenue.com/taxes/taxesfees/Pages/reemployment.aspx','GA':'https://dor.georgia.gov/withholding-tax',
 'HI':'https://tax.hawaii.gov/geninfo/a2_b2_1/','ID':'https://tax.idaho.gov/taxes/income-tax/withholding/',
 'IL':'https://tax.illinois.gov/businesses/withholding.html','IN':'https://www.in.gov/dor/business-tax/withholding-income-tax/',
 'IA':'https://revenue.iowa.gov/taxes/tax-guidance/withholding-tax','KS':'https://www.ksrevenue.gov/bustaxtypeswh.html',
 'KY':'https://revenue.ky.gov/Business/Pages/Employer-Payroll-Withholding.aspx','LA':'https://revenue.louisiana.gov/withholding-tax/',
 'ME':'https://www.maine.gov/revenue/taxes/income-estate-tax/withholding-tax','MD':'https://www.marylandcomptroller.gov/businesses/taxes/withholding/',
 'MA':'https://www.mass.gov/employer-withholding','MI':'https://www.michigan.gov/taxes/business-taxes/withholding',
 'MN':'https://www.revenue.state.mn.us/withholding-tax','MS':'https://www.dor.ms.gov/business/withholding-tax',
 'MO':'https://dor.mo.gov/taxation/business/tax-types/withholding/','MT':'https://revenue.mt.gov/taxes/withholding-tax/',
 'NE':'https://revenue.nebraska.gov/businesses/withholding','NV':'https://tax.nv.gov/tax-types/modified-business-tax/',
 'NH':'https://www.nhes.nh.gov/services/employers/','NJ':'https://www.nj.gov/treasury/taxation/businesses/payroll/',
 'NM':'https://www.tax.newmexico.gov/businesses/withholding-tax/','NY':'https://www.tax.ny.gov/bus/wt/',
 'NC':'https://www.ncdor.gov/taxes-forms/withholding-tax','ND':'https://www.tax.nd.gov/business/income-tax-withholding',
 'OH':'https://tax.ohio.gov/business/ohio-business-taxes/employer-withholding','OK':'https://oklahoma.gov/tax/businesses/tax-types/income-tax.html',
 'OR':'https://www.oregon.gov/dor/programs/businesses/Pages/withholding-and-payroll-tax.aspx','PA':'https://www.pa.gov/agencies/revenue/resources/tax-types-and-information/personal-income-tax/employer-withholding.html',
 'RI':'https://tax.ri.gov/tax-sections/withholding-tax','SC':'https://dor.sc.gov/tax/withholding',
 'SD':'https://dlr.sd.gov/ra/businesses/default.aspx','TN':'https://www.tn.gov/workforce/employers/tax-and-insurance-redirect/unemployment-insurance-tax.html',
 'TX':'https://www.twc.texas.gov/programs/unemployment-tax','UT':'https://tax.utah.gov/withholding',
 'VT':'https://tax.vermont.gov/business/withholding','VA':'https://www.tax.virginia.gov/withholding-tax',
 'WA':'https://esd.wa.gov/employer-taxes','WV':'https://tax.wv.gov/Business/Withholding/Pages/WithholdingTax.aspx',
 'WI':'https://www.revenue.wi.gov/Pages/Businesses/Withholding.aspx','WY':'https://dws.wyo.gov/dws-division/unemployment-insurance/',
 'DC':'https://otr.cfo.dc.gov/page/withholding-tax'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS tax_sources(state TEXT PRIMARY KEY,url TEXT NOT NULL,checked_at TEXT,content_hash TEXT,body TEXT,etag TEXT,modified TEXT,error TEXT);
CREATE TABLE IF NOT EXISTS tax_changes(id INTEGER PRIMARY KEY,state TEXT NOT NULL,url TEXT NOT NULL,detected_at TEXT NOT NULL,diff TEXT NOT NULL,status TEXT NOT NULL,review TEXT,effective_date TEXT);
'''


class Text(HTMLParser):
    def __init__(self):super().__init__();self.hidden=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript'}:self.hidden+=1
        if tag in {'p','h1','h2','h3','li','br','div','section'}:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript'}:self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)
    def text(self):return '\n'.join(line for raw in ''.join(self.parts).splitlines() if (line:=re.sub(r'\s+',' ',raw).strip()))[:250000]


def selected_states(ledger):
    try:return json.loads(ledger.settings().get('operation_states','[]'))
    except ValueError:return []


def configure(ledger,value):
    states=value.get('states',[])
    if not isinstance(states,list) or any(s not in STATES for s in states):raise AccountingError('Choose valid states of operation')
    with ledger.db:
        ledger.db.execute("INSERT OR REPLACE INTO settings VALUES('operation_states',?)",(canonical(sorted(set(states))),))
        ledger.audit('tax-monitor-states',{'states':states})
    return {'states':states,'sources':[{'state':s,'url':SOURCES[s]} for s in ['US']+states]}


class GovernmentRedirects(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        u=urlparse(newurl)
        if u.scheme!='https' or not u.hostname or not (u.hostname.endswith('.gov') or u.hostname.endswith('.state.mn.us')):
            raise AccountingError('Official source redirected outside an approved government domain')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def check_source(ledger,state,fetch=None):
    url=SOURCES[state];old=ledger.db.execute('SELECT * FROM tax_sources WHERE state=?',(state,)).fetchone()
    headers={'User-Agent':'BackwoodsAccountingTaxMonitor/1.0','Accept':'text/html'}
    if old and old['etag']:headers['If-None-Match']=old['etag']
    if old and old['modified']:headers['If-Modified-Since']=old['modified']
    try:
        if fetch:body,response_headers=fetch(url,headers)
        else:
            with build_opener(GovernmentRedirects()).open(Request(url,headers=headers),timeout=12) as response:
                if 'html' not in response.headers.get('Content-Type',''):raise AccountingError('Official source did not return an HTML page')
                body=response.read(2*1024*1024+1)
                if len(body)>2*1024*1024:raise AccountingError('Official source page is too large')
                response_headers=dict(response.headers)
        parser=Text();parser.feed(body.decode('utf-8',errors='replace'));text=parser.text()
        if len(text)<100:raise AccountingError('Official source did not return enough text to verify')
        digest=hashlib.sha256(text.encode()).hexdigest()
        with ledger.db:
            if old and old['content_hash'] and old['content_hash']!=digest:
                diff='\n'.join(list(difflib.unified_diff((old['body'] or '').splitlines(),text.splitlines(),fromfile='Previously checked source',tofile='Current official source',n=3))[:300])
                ledger.db.execute('INSERT INTO tax_changes(state,url,detected_at,diff,status) VALUES(?,?,?,?,?)',(state,url,now(),diff,'needs-review'))
                ledger.audit('official-tax-source-changed',{'state':state,'url':url})
            ledger.db.execute('INSERT OR REPLACE INTO tax_sources VALUES(?,?,?,?,?,?,?,?)',(state,url,now(),digest,text,response_headers.get('ETag'),response_headers.get('Last-Modified'),None))
        return {'state':state,'ok':True,'changed':bool(old and old['content_hash'] and old['content_hash']!=digest)}
    except HTTPError as exc:
        if exc.code==304 and old:
            with ledger.db:ledger.db.execute('UPDATE tax_sources SET checked_at=?,error=NULL WHERE state=?',(now(),state))
            return {'state':state,'ok':True,'changed':False}
        error=f'Official source returned HTTP {exc.code}; monitoring is not current'
    except Exception as exc:error=str(exc)[:300]
    with ledger.db:
        if old:ledger.db.execute('UPDATE tax_sources SET checked_at=?,error=? WHERE state=?',(now(),error,state))
        else:ledger.db.execute('INSERT INTO tax_sources(state,url,checked_at,error) VALUES(?,?,?,?)',(state,url,now(),error))
    return {'state':state,'ok':False,'error':error}


def review_change(ledger,value):
    if not ledger.db.execute('SELECT 1 FROM tax_changes WHERE id=?',(value.get('id'),)).fetchone():raise AccountingError('Tax source change not found')
    status=value.get('status')
    if status not in {'reviewed','not-applicable'}:raise AccountingError('Choose reviewed or not applicable')
    note=str(value.get('review','')).strip()
    if not note:raise AccountingError('Add a review note with the law or provider action confirmed')
    effective=day(value['effectiveDate']) if value.get('effectiveDate') else None
    with ledger.db:
        ledger.db.execute('UPDATE tax_changes SET status=?,review=?,effective_date=? WHERE id=?',(status,note,effective,value['id']))
        ledger.audit('tax-source-review',{'id':value['id'],'status':status,'effectiveDate':effective,'review':note})
    return {'ok':True}


def monitor(app):
    from datetime import datetime,timezone,timedelta
    while not app.stop.is_set():
        try:
            with app.write_lock:
                ledger=app.ledger()
                try:
                    states=selected_states(ledger);due=[]
                    for state in (['US']+states if states else []):
                        r=ledger.db.execute('SELECT checked_at FROM tax_sources WHERE state=?',(state,)).fetchone()
                        if not r or not r[0] or datetime.fromisoformat(r[0])<datetime.now(timezone.utc)-timedelta(hours=24):due.append(state)
                finally:ledger.close()
            if due:
                for state in due:
                    if app.stop.is_set():break
                    with app.shared.mutation():
                        ledger=app.ledger()
                        try:
                            r=ledger.db.execute('SELECT checked_at FROM tax_sources WHERE state=?',(state,)).fetchone()
                            if not r or not r[0] or datetime.fromisoformat(r[0])<datetime.now(timezone.utc)-timedelta(hours=24):check_source(ledger,state)
                        finally:ledger.close()
        except Exception as error:
            app.firebase_status={'connected':False,'message':'Tax checks will retry: '+str(error)}
        app.stop.wait(60)
