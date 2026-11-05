"""Loopback accounting service and file-feed worker; optional trusted TLS proxy."""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote
import uuid
import webbrowser

from .ledger import AccountingError, Ledger, cents, day, now,ACTOR
from . import auth
from .imports import prepare, record, pair, line, quantity, account_code, catalog_items, unwrap,sanitize_payload
from .costing import calculate, price_channels
from .business import asset_state,register_asset,depreciate,dispose_asset,payroll_preview,post_payroll,pay_payroll
from .payroll_provider import Gusto,SecretStore,STATES,ProviderError,review_payroll,submit_payroll,sync_payrolls
from . import tax_watch
from .printing import render as print_document
from .locking import RunLock
from .firebase_sync import Firebase,SCHEMA as FIREBASE_SCHEMA
from .firebase_ledger import SharedLedger
from .shared_runtime import SharedHandlerMixin

ROOT=Path(__file__).resolve().parents[1]
MAX_BODY=40*1024*1024


def default_data_dir():
    if os.name=="nt":
        return Path(os.environ.get("LOCALAPPDATA",Path.home()))/"BackwoodsBusinessAccounting"
    return Path(os.environ.get("XDG_DATA_HOME",Path.home()/".local/share"))/"BackwoodsBusinessAccounting"


class Application:
    def __init__(self,data_dir,public_origin=None):
        self.public_origin=None
        self.public_host=None
        if public_origin:
            parsed=urlparse(str(public_origin))
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'','/'} or parsed.query or parsed.fragment or any(c.isspace() for c in parsed.netloc):
                raise AccountingError('The shared server origin must be an HTTPS address with no credentials, path, query or fragment')
            self.public_host=parsed.hostname.lower()+(':'+str(parsed.port) if parsed.port and parsed.port!=443 else '')
            self.public_origin='https://'+self.public_host
        self.data_dir=Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True,exist_ok=True)
        self.path=self.data_dir/"accounting.sqlite3"
        self.feed_dir=self.data_dir/"feeds"
        self.feed_dir.mkdir(exist_ok=True)
        self.stop=threading.Event()
        self.write_lock=threading.RLock()
        self.cookie=secrets.token_urlsafe(32)
        self.feed_errors={}
        self.firebase=Firebase(self.data_dir)
        self.firebase_lock=threading.RLock()
        self.firebase_status={'connected':False,'message':'Owner Firebase sign-in has not been linked yet.'}
        ledger=Ledger(self.path)
        ledger.db.executescript(FIREBASE_SCHEMA)
        ledger.db.execute('CREATE TABLE IF NOT EXISTS processed_feeds(source TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(source,fingerprint))')
        ledger.db.commit()
        ledger.close()
        self.shared=SharedLedger(self)

    def ledger(self):return Ledger(self.path)

    def watch_firebase(self):
        hashes={}
        while not self.stop.is_set():
            try:
                with self.firebase_lock:connected=bool(self.firebase.bearer())
                if not connected:
                    self.stop.wait(30);continue
                with self.firebase_lock:
                    ledger=self.ledger()
                    try:link=ledger.db.execute('SELECT * FROM firebase_link WHERE uid=?',(self.firebase.connection['uid'],)).fetchone()
                    finally:ledger.close()
                    if not link:raise AccountingError('Link the Firebase account from the owner settings before importing cloud records.')
                receipts=self.firebase_status.get('sources',{})
                self.firebase_status={'connected':True,'message':'Firebase connected. Checking retail and wholesale records.','sources':receipts}
                for source in ['main','vendor']:
                    try:
                        with self.firebase_lock:result=self.firebase.snapshot(source,hashes.get(source))
                        if result:
                            digest,packet=result
                            receipt=self.process({'source':source,'payload':packet,'filename':'Automatic Firebase '+source+' feed'})
                            hashes[source]=digest
                            receipts[source]={'at':now(),'added':receipt['added'],'changed':receipt['changed'],'duplicates':receipt['duplicates']}
                    except Exception as error:
                        receipts[source]={'error':str(error)}
                        self.firebase_status['message']='One or more source imports need review; other source imports continue.'
            except Exception as error:
                self.firebase_status={'connected':False,'message':str(error)}
            self.stop.wait(30)

    def process(self,value,preview=False):
        if preview:return self._process(value,preview=True)
        with self.shared.mutation():return self._process(value)

    def _process(self,value,preview=False):
        source=value.get("source")
        payload=sanitize_payload(value.get("payload"),source)
        ledger=self.ledger()
        self.write_lock.acquire()
        try:
            # Apply only explicit historical-cost corrections entered by the owner.
            enriched=json.loads(json.dumps(payload))
            overrides=dict(ledger.db.execute("SELECT source_id,unit_cost FROM cost_overrides"))
            if source=="vendor" and overrides:
                data=enriched.get("data",enriched)
                for move in data.get("inventoryMovements",[]):
                    if str(move.get("id")) in overrides:
                        move["unitCost"]=overrides[str(move["id"])]
            documents,accounts,warnings=prepare(enriched,source)
            if source=='main':
                current_mode='ledger' if 'generalLedger' in unwrap(enriched) else 'backup'
                previous=ledger.db.execute("SELECT payload FROM batches WHERE source='main' ORDER BY created_at DESC LIMIT 1").fetchone()
                if previous:
                    prior_mode='ledger' if 'generalLedger' in unwrap(json.loads(previous[0])) else 'backup'
                    if prior_mode!=current_mode:
                        raise AccountingError('Main-app ledger feeds and plain backups use different source IDs. Continue using the original import format; switching requires a reviewed migration to avoid duplicate postings.')
            for doc in documents:
                if doc['kind'] in {'voided-invoice','voided-support-invoices'}:
                    old=ledger.db.execute('SELECT payload FROM documents WHERE source=? AND source_id=?',(source,doc['id'])).fetchone()
                    if old:
                        prior=json.loads(old[0])
                        if prior['amount']>prior['balance'] or prior.get('paymentHistory'):
                            raise AccountingError(f"Invoice {prior['reference']} has payments; record a refund or reviewed correction before voiding")
            if payload.get('type')=='business-accounting-feed':
                # These connectors send complete snapshots. Missing invoices are
                # source corrections, represented as revisions, never SQL deletes.
                incoming={d['id'] for d in documents}
                data=unwrap(enriched)
                for old in ledger.db.execute('SELECT source_id,payload FROM documents WHERE source=?',(source,)):
                    if old['source_id'] in incoming:
                        continue
                    prior=json.loads(old['payload'])
                    if prior.get('sourceDeleted'):
                        continue
                    invoice=prior['kind'] in {'invoice','support-invoices','voided-invoice','voided-support-invoices'}
                    main_ledger=(source=='main' and prior['kind']=='ledger' and 'generalLedger' in data
                                 and prior['reference'].startswith(('Invoice ', 'Invoice Payment ')))
                    # Never infer that a payment was refunded because its invoice
                    # disappeared. Paid invoices require an explicit correction.
                    if invoice:
                        paid=prior['amount']-prior['balance']
                        if paid>0 or prior.get('paymentHistory'):
                            raise AccountingError(f"Deleted invoice {prior['reference']} has payments; record a refund or reviewed correction in the source app")
                    if invoice or main_ledger:
                        collection='orders' if source=='vendor' else 'invoices'
                        if not payload.get('exportedAt') or not isinstance(data.get(collection),list):
                            raise AccountingError('Invoice deletion requires a timestamped complete source snapshot')
                        if source=='vendor' and not isinstance(data.get('payments'),list):
                            raise AccountingError('Invoice deletion requires the complete payments collection')
                        tombstone={**prior,'lines':[],'amount':0,'balance':0,
                                   'kind':'deleted-'+prior['kind'],'sourceDeleted':True,
                                   'memo':prior.get('memo','')+' · Deleted in source app'}
                        documents.append(tombstone)
                        warnings.append(f"{prior['reference']} was deleted in the source app; its posting is reversed and history retained.")
                    elif prior['lines']:
                        raise AccountingError(f"Previously posted record {old['source_id']} is absent from this snapshot. Restore or reverse it in the source app; missing records are never silently deleted.")
            # A source app that already mirrored vendor records must flag them.
            # Catch obvious unmarked duplicate invoice references across feeds.
            for doc in documents:
                if doc['kind']=='purchase-receipt' and doc['balance']<ledger.allocations().get((source,doc['id']),0):
                    raise AccountingError('A changed receipt is below payments already recorded in Business Accounting; review the supplier credit')
                if doc["kind"]=="invoice" and doc["lines"]:
                    duplicate=ledger.db.execute("SELECT source,source_id FROM documents WHERE source<>? AND kind='invoice' AND reference=? AND amount=?",(source,doc["reference"],doc["amount"])).fetchone()
                    if duplicate:
                        raise AccountingError(f"Invoice {doc['reference']} already exists from {duplicate['source']}; identify the original source before importing")
            fingerprint=hashlib.sha256(json.dumps(enriched,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            stamp=payload.get('exportedAt') if isinstance(payload,dict) else None
            previous=ledger.db.execute('SELECT MAX(snapshot_at) FROM batches WHERE source=?',(source,)).fetchone()[0]
            older_unchanged=False
            if stamp and previous:
                from datetime import datetime
                older_unchanged=datetime.fromisoformat(str(stamp).replace('Z','+00:00'))<datetime.fromisoformat(previous)
                if older_unchanged:
                    older_unchanged=all((row:=ledger.db.execute('SELECT hash FROM documents WHERE source=? AND source_id=?',(source,doc['id'])).fetchone()) and row[0]==hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest() for doc in documents)
            if not preview and older_unchanged:
                return {'added':0,'changed':0,'duplicates':len(documents),'records':len(documents),'warnings':warnings,'reviewCount':sum(d['kind']=='needs-cost' for d in documents),'sample':[]}
            if not preview and ledger.db.execute('SELECT 1 FROM processed_feeds WHERE source=? AND fingerprint=?',(source,fingerprint)).fetchone():
                return {'added':0,'changed':0,'duplicates':len(documents),'records':len(documents),'warnings':warnings,'reviewCount':sum(d['kind']=='needs-cost' for d in documents),'sample':[]}
            result=ledger.import_documents(source,documents,payload,value.get("filename","import.json"),payload.get("exportedAt") if isinstance(payload,dict) else None,accounts,preview,catalog=catalog_items(enriched,source))
            if not preview:
                with ledger.db:ledger.db.execute('INSERT OR IGNORE INTO processed_feeds VALUES(?,?)',(source,fingerprint))
            result["warnings"]=warnings
            result["reviewCount"]=sum(d["kind"]=="needs-cost" for d in documents)
            result["sample"]=[{k:v for k,v in d.items() if k not in {"original","lines"}} for d in documents[:12]]
            return result
        finally:ledger.close();self.write_lock.release()

    def watch_feeds(self):
        hashes={}
        while not self.stop.is_set():
            if self.shared.connected():
                self.stop.wait(15);continue
            for source in ["main","vendor"]:
                p=self.feed_dir/(source+".json")
                if not p.exists():continue
                try:
                    data=p.read_bytes()
                    digest=hashlib.sha256(data).hexdigest()
                    if hashes.get(source)==digest:continue
                    if len(data)>MAX_BODY:raise AccountingError("Feed exceeds 40 MB")
                    value=json.loads(data)
                    result=self.process({"source":source,"payload":value,"filename":"Automatic "+source+" feed"})
                    hashes[source]=digest
                    self.feed_errors.pop(source,None)
                    status={"ok":True,"at":now(),"added":result["added"],"changed":result["changed"],"duplicates":result["duplicates"],"reviewCount":result["reviewCount"],"warnings":result["warnings"]}
                except Exception as exc:
                    self.feed_errors[source]=str(exc)
                    status={"ok":False,"at":now(),"error":str(exc)}
                status_path=self.feed_dir/(source+"-status.json")
                temp=status_path.with_suffix(".tmp")
                temp.write_text(json.dumps(status),encoding="utf-8")
                temp.replace(status_path)
            self.stop.wait(3)


class LocalHandler(BaseHTTPRequestHandler):
    server_version="BackwoodsAccounting/1.0"

    @property
    def app(self):return self.server.application

    def log_message(self,fmt,*args):
        # URLs cannot contain credentials; keep ordinary local request diagnostics.
        super().log_message(fmt,*args)

    def send_bytes(self,data,mime="application/json",status=200,filename=None,set_cookie=False,session_token=None):
        self.send_response(status)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header("Content-Disposition","attachment; filename*=UTF-8''"+quote(filename,safe=""))
        secure='; Secure' if self.app.public_host and self.headers.get('Host','').lower()==self.app.public_host else ''
        if set_cookie and not getattr(self.app,'native_private_bootstrap',False):self.send_header("Set-Cookie",f"bw_bootstrap={self.app.cookie}; HttpOnly; SameSite=Strict; Path=/{secure}")
        if session_token is not None:self.send_header('Set-Cookie',f'bw_session={session_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={28800 if session_token else 0}{secure}')
        self.end_headers()
        self.wfile.write(data)

    def respond(self,value,status=200,session_token=None):
        self.send_bytes(json.dumps(value,allow_nan=False).encode(),status=status,session_token=session_token)

    def trusted_host(self):
        host=self.headers.get('Host','').lower()
        return host==f"127.0.0.1:{self.server.server_port}" or bool(self.app.public_host and host==self.app.public_host)

    def allowed_origins(self):
        if self.app.public_host and self.headers.get('Host','').lower()==self.app.public_host:
            return {self.app.public_origin}
        return {f'http://127.0.0.1:{self.server.server_port}'}

    def authorized(self):
        if not self.trusted_host():return False
        origin=self.headers.get("Origin")
        if origin and origin not in self.allowed_origins():return False
        if self.headers.get("Sec-Fetch-Site")=="cross-site":return False
        ledger=self.app.ledger()
        try:self.user=auth.session_user(ledger,self.cookie_value('bw_session'))
        finally:ledger.close()
        if self.user:ACTOR.set(self.user['username'])
        return bool(self.user)

    def cookie_value(self,name):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return ''
        v=cookie.get(name)
        return v.value if v else ''

    def trusted_request(self):
        origin=self.headers.get('Origin')
        return self.trusted_host() and (not origin or origin in self.allowed_origins()) and self.headers.get('Sec-Fetch-Site')!='cross-site'

    def do_GET(self):
        if not self.trusted_host():
            self.respond({"error":"Unrecognized local host"},403);return
        parsed=urlparse(self.path)
        path=parsed.path
        if path=='/api/auth/status':
            if not self.trusted_request():self.respond({'error':'Untrusted request'},403);return
            ledger=self.app.ledger()
            try:self.respond({'initialized':bool(ledger.db.execute('SELECT 1 FROM users').fetchone()),'user':auth.session_user(ledger,self.cookie_value('bw_session')),'firebaseConnected':bool(getattr(self.app.firebase,'connection',None))})
            finally:ledger.close()
            return
        if path in {"/","/app.js","/style.css","/print.css","/print.js"}:
            if self.headers.get("Sec-Fetch-Site")=="cross-site":
                self.respond({"error":"Open the app directly"},403);return
            filename={"/":"index.html","/app.js":"app.js","/style.css":"style.css","/print.css":"print.css","/print.js":"print.js"}[path]
            mime='text/html; charset=utf-8' if path=='/' else 'text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8'
            self.send_bytes((ROOT/"web"/filename).read_bytes(),mime,set_cookie=path=="/");return
        if not self.authorized():self.respond({"error":"Open the accounting home page first"},403);return
        args={k:v[0] for k,v in parse_qs(parsed.query).items()}
        ledger=self.app.ledger()
        try:
            if path=='/print':
                self.send_bytes(print_document(ledger,args,self.user).encode(),'text/html; charset=utf-8')
            elif path=="/api/state":
                value=ledger.summary(args.get("start"),args.get("end"))
                value['user']=self.user
                value['users']=[dict(r) for r in ledger.db.execute('SELECT id,username,name,role FROM users ORDER BY username')] if self.user['role']=='owner' else []
                value["recipes"]=[{"id":r["id"],"name":r["name"],"payload":json.loads(r["payload"]),"result":json.loads(r["result"]),"updated_at":r["updated_at"]} for r in ledger.db.execute("SELECT * FROM recipes ORDER BY name")]
                value['pricing']=[{'id':r['id'],'name':r['name'],'payload':json.loads(r['payload']),'result':json.loads(r['result'])} for r in ledger.db.execute('SELECT * FROM pricing ORDER BY name')]
                plans={(r['source'],r['source_id']):json.loads(r['payload']) for r in ledger.db.execute('SELECT * FROM item_plans')}
                value['catalog']=[{'source':r['source'],**json.loads(r['payload']),'plan':plans.get((r['source'],r['source_id']),{}),'updated_at':r['updated_at']} for r in ledger.db.execute('SELECT * FROM catalog ORDER BY source,source_id')]
                value['assets']=asset_state(ledger)
                value['employees']=[{'id':r['id'],'name':r['name'],**json.loads(r['payload'])} for r in ledger.db.execute('SELECT * FROM employees ORDER BY name')]
                value['payroll']=[{'source':r['source'],**json.loads(r['payload'])} for r in ledger.db.execute("SELECT source,payload FROM documents WHERE kind IN ('payroll','support-payrollRuns') ORDER BY date DESC")]
                if self.user['role']=='viewer':
                    value['employees']=[];value['payroll']=[]
                    value['documents']=[d for d in value['documents'] if 'payroll' not in d['kind'].lower()]
                    value['attachments']=[a for a in value['attachments'] if 'payroll' not in a['source_id'].lower()]
                value['states']=STATES
                value['operationStates']=tax_watch.selected_states(ledger)
                value['taxSources']=[dict(r) for r in ledger.db.execute('SELECT state,url,checked_at,error FROM tax_sources ORDER BY state')]
                value['taxChanges']=[dict(r) for r in ledger.db.execute('SELECT * FROM tax_changes ORDER BY id DESC LIMIT 100')]
                cache=ledger.db.execute("SELECT payload,updated_at FROM provider_cache WHERE kind='payrolls'").fetchone()
                value['providerPayrolls']=json.loads(cache['payload']) if cache and self.user['role']!='viewer' else {'payrolls':[],'issues':[]}
                value['providerActions']=[dict(r) for r in ledger.db.execute('SELECT * FROM provider_actions')] if self.user['role']!='viewer' else []
                try:
                    connection=SecretStore(self.app.data_dir).read()
                    value['payrollConnection']={'connected':bool(connection),'environment':connection.get('environment','demo') if connection else None,'companyId':connection.get('companyId') if connection else None,'companyName':connection.get('companyName') if connection else None}
                except AccountingError as exc:value['payrollConnection']={'connected':False,'error':str(exc)}
                value['aging']=[]
                allocations=ledger.allocations()
                for r in ledger.db.execute("SELECT source,source_id,payload FROM documents WHERE kind IN ('invoice','bill','support-invoices','support-bills') AND balance>0"):
                    d=json.loads(r['payload']);due=d.get('original',{}).get('dueDate')
                    try:due=day(due) if due else None
                    except AccountingError:due=None
                    balance=d['balance']-allocations.get((r['source'],r['source_id']),0)
                    if balance>0:value['aging'].append({'source':r['source'],'id':r['source_id'],'reference':d['reference'],'kind':d['kind'],'party':d['party'],'balance':balance,'dueDate':due,'daysOverdue':max(0,(__import__('datetime').date.today()-__import__('datetime').date.fromisoformat(due)).days) if due else None})
                value["feedDirectory"]=str(self.app.feed_dir)
                value["feedErrors"]=dict(self.app.feed_errors)
                value['firebaseStatus']=dict(self.app.firebase_status)
                value['sharedLedger']=bool(getattr(self.app.firebase,'connection',None))
                value["feeds"]={}
                for source in ["main","vendor"]:
                    p=self.app.feed_dir/(source+"-status.json")
                    if p.exists():
                        try:value["feeds"][source]=json.loads(p.read_text())
                        except (ValueError,OSError):pass
                self.respond(value)
            elif path=="/api/ledger":
                self.respond(ledger.rows(args.get("start"),args.get("end"),args.get("source"),args.get("account")))
            elif path=="/api/document":
                r=ledger.db.execute("SELECT payload FROM documents WHERE source=? AND source_id=?",(args.get("source"),args.get("id"))).fetchone()
                if not r:raise AccountingError("Transaction not found")
                if self.user['role']=='viewer' and 'payroll' in str(args.get('id','')).lower():self.respond({'error':'Payroll access is restricted'},403);return
                self.respond(json.loads(r[0]))
            elif path=='/api/provider/paystub':
                if self.user['role']=='viewer':self.respond({'error':'Payroll access is restricted'},403);return
                data=Gusto(self.app.data_dir).pay_stub(args.get('payrollId'),args.get('employeeId'))
                self.send_bytes(data,'application/pdf',filename='official-payroll-statement.pdf')
            elif path=="/api/export.csv":
                out=io.StringIO(newline="")
                writer=csv.writer(out)
                writer.writerow(["date","entry_id","source","source_id","revision","account","name","memo","debit","credit"])
                for r in ledger.rows(args.get("start"),args.get("end")):
                    def safe(s):
                        s=str(s)
                        return "'"+s if s[:1] in {"=","+","-","@","\t","\r"} else s
                    writer.writerow([safe(r[k]) for k in ["date","entry_id","source","source_id","revision","account","name","memo"]]+[f"{r['debit']/100:.2f}",f"{r['credit']/100:.2f}"])
                self.send_bytes(out.getvalue().encode("utf-8-sig"),"text/csv",filename="backwoods-company-ledger.csv")
            elif path=='/api/payroll.csv':
                if self.user['role']=='viewer':self.respond({'error':'Payroll access is restricted'},403);return
                out=io.StringIO(newline='');writer=csv.writer(out)
                writer.writerow(['record','employee','period_start','period_end','pay_date','gross','net','federal','state','social_security','medicare','deductions','employer_taxes'])
                for r in ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND kind='payroll' ORDER BY date"):
                    d=json.loads(r[0]);o=d['original'];c=o['calculation'];a=c['amounts']
                    safe_name="'"+d['party'] if d['party'][:1] in {'=','+','-','@'} else d['party']
                    writer.writerow([d['id'],safe_name,o['periodStart'],o['periodEnd'],d['date']]+[f'{x/100:.2f}' for x in [c['gross'],c['net'],a['federal'],a['state'],a['socialSecurity'],a['medicare'],a['deductions'],c['employerTaxes']]])
                self.send_bytes(out.getvalue().encode('utf-8-sig'),'text/csv',filename='backwoods-business-payroll-summary.csv')
            elif path=="/api/backup":
                if self.user['role']!='owner':self.respond({'error':'Only the owner can download the database backup'},403);return
                backup=self.app.data_dir/("backup-"+str(uuid.uuid4())+".sqlite3")
                try:
                    dest=sqlite3.connect(backup)
                    try:ledger.db.backup(dest)
                    finally:dest.close()
                    self.send_bytes(backup.read_bytes(),"application/vnd.sqlite3",filename="backwoods-accounting-backup.sqlite3")
                finally:backup.unlink(missing_ok=True)
            elif path=="/api/attachment":
                r=ledger.db.execute("SELECT name,mime,content,source_id FROM attachments WHERE id=?",(args.get("id"),)).fetchone()
                if not r:raise AccountingError("Attachment not found")
                if self.user['role']=='viewer' and 'payroll' in r['source_id'].lower():self.respond({'error':'Payroll access is restricted'},403);return
                self.send_bytes(r["content"],r["mime"],filename=r["name"])
            else:self.respond({"error":"Not found"},404)
        except (AccountingError,ValueError,KeyError) as exc:self.respond({"error":str(exc)},400)
        finally:ledger.close()

    def do_POST(self):
        path=urlparse(self.path).path
        if path.startswith('/api/auth/'):
            self.auth_request(path);return
        if not self.authorized() or self.headers.get("X-Accounting-Request")!="1":
            self.respond({"error":"Request is not from the accounting app"},403);return
        if self.user['role']=='viewer':self.respond({'error':'Your role is read-only'},403);return
        if (path in {'/api/settings','/api/users','/api/provider/connect','/api/provider/submit','/api/tax-watch/configure','/api/tax-watch/review','/api/firebase/connect'} or path.startswith('/api/provider/')) and self.user['role']!='owner':self.respond({'error':'Owner access required'},403);return
        ledger=None
        self.app.write_lock.acquire()
        try:
            length=int(self.headers.get("Content-Length","0"))
            if length<1 or length>MAX_BODY:raise AccountingError("Request must be between 1 byte and 40 MB")
            if self.headers.get_content_type()!="application/json":raise AccountingError("JSON request required")
            value=json.loads(self.rfile.read(length))
            path=urlparse(self.path).path
            if path in {"/api/import/preview","/api/import"}:
                result=self.app.process(value,preview=path.endswith("preview"))
            else:
                ledger=self.app.ledger()
                if path=='/api/tax-watch/configure':result=tax_watch.configure(ledger,value)
                elif path=='/api/tax-watch/review':result=tax_watch.review_change(ledger,value)
                elif path=='/api/tax-watch/check':
                    selected=tax_watch.selected_states(ledger)
                    if not selected:raise AccountingError('Select your states of operation first')
                    # Launch checks in the background; do not hold the UI on many states.
                    def check_now():
                        try:
                            for state in ['US']+selected:
                                if self.app.stop.is_set():break
                                with self.app.shared.mutation():
                                    local=self.app.ledger()
                                    try:tax_watch.check_source(local,state)
                                    finally:local.close()
                        except Exception as error:
                            self.app.firebase_status={'connected':False,'message':'Tax check will retry: '+str(error)}
                    threading.Thread(target=check_now,daemon=True).start();result={'message':'Official-source checks started. Refresh this screen to see results.'}
                elif path=='/api/firebase/connect':
                    verification,_=auth.login(ledger,{'username':self.user['username'],'password':value.get('ownerPassword','')})
                    auth.logout(ledger,verification)
                    with self.app.firebase_lock:
                        result=self.app.firebase.connect(ledger,self.user,value.get('email',''),value.get('password',''))
                        self.app.firebase_status={'connected':True,'message':'Company linked. Automatic imports will start shortly.'}
                elif path=='/api/provider/connect':
                    for key in ['accessToken','companyId']:
                        if not value.get(key):raise AccountingError('Enter the approved company connection details')
                    client=Gusto(self.app.data_dir,connection=value);info=client.company_info()
                    for r in ledger.db.execute("SELECT payload FROM documents WHERE source='provider'"):
                        if json.loads(r[0]).get('original',{}).get('companyId')!=client.company:raise AccountingError('This ledger already contains payroll for a different provider company. Use a separate company database or a reviewed migration.')
                    SecretStore(self.app.data_dir).save({**value,'companyName':info.get('name') or info.get('trade_name')})
                    with ledger.db:ledger.audit('payroll-provider-connected',{'companyId':client.company,'environment':client.environment})
                    result={'connected':True,'companyName':info.get('name') or info.get('trade_name')}
                elif path=='/api/provider/health':
                    client=Gusto(self.app.data_dir);info=client.company_info()
                    result={'connected':True,'companyName':info.get('name') or info.get('trade_name'),'environment':client.environment}
                elif path=='/api/provider/flow':result=Gusto(self.app.data_dir).flow(value.get('kind'))
                elif path=='/api/provider/sync':result=sync_payrolls(ledger,Gusto(self.app.data_dir))
                elif path=='/api/provider/calculate':result=Gusto(self.app.data_dir).calculate(value.get('payrollId'))
                elif path=='/api/provider/review':result=review_payroll(ledger,Gusto(self.app.data_dir),value.get('payrollId'))
                elif path=='/api/provider/submit':
                    r=ledger.db.execute('SELECT * FROM users WHERE id=?',(self.user['id'],)).fetchone()
                    if not secrets.compare_digest(r['password_hash'],auth.password_hash(str(value.get('password','')),r['salt'])):raise AccountingError('Owner password is incorrect')
                    result=submit_payroll(ledger,Gusto(self.app.data_dir),value.get('payrollId'),value.get('fingerprint'),value.get('confirmation'))
                elif path=='/api/users':result=auth.create_user(ledger,value)
                elif path=='/api/assets/register':result=register_asset(ledger,value)
                elif path=='/api/assets/depreciate':result=depreciate(ledger,value)
                elif path=='/api/assets/dispose':result=dispose_asset(ledger,value)
                elif path=='/api/payroll/preview':result=payroll_preview(value)
                elif path=='/api/payroll/post':result=post_payroll(ledger,value)
                elif path=='/api/payroll/pay':result=pay_payroll(ledger,value)
                elif path=='/api/employees':
                    name=str(value.get('name','')).strip()
                    if not name:raise AccountingError('Employee name required')
                    if quantity(value.get('hourlyRate',0))<0:raise AccountingError('Hourly rate must be nonnegative')
                    eid=str(value.get('id') or uuid.uuid4())
                    with ledger.db:
                        ledger.db.execute('INSERT OR REPLACE INTO employees VALUES(?,?,?,?)',(eid,name,json.dumps({'name':name,'jobTitle':str(value.get('jobTitle','')),'hourlyRate':str(value.get('hourlyRate',0)),'notes':str(value.get('notes',''))}),now()))
                        ledger.audit('employee',{'id':eid,'name':name})
                    result={'id':eid}
                elif path=='/api/liability-payment':
                    account=account_code(value.get('account'),'')
                    if account not in {'2100','2151','2152','2153','2154','2155','2156'}:raise AccountingError('Choose a supported payroll or sales-tax liability')
                    amount=cents(value.get('amount'))
                    if amount<=0:raise AccountingError('Payment must be positive')
                    doc=record('tax-payment',{'id':str(uuid.uuid4()),'date':value.get('date'),'memo':value.get('memo','Tax / deduction payment')},pair(account,'1020',amount),amount=amount,reference=value.get('reference'))
                    result=ledger.import_documents('manual',[doc],value,'Tax / payroll liability payment record')
                elif path in {'/api/pricing/calculate','/api/pricing/save'}:
                    result=price_channels(value)
                    if path.endswith('save'):
                        rid=str(value.get('id') or uuid.uuid4())
                        with ledger.db:
                            ledger.db.execute('INSERT OR REPLACE INTO pricing VALUES(?,?,?,?,?)',(rid,result['name'],json.dumps(value),json.dumps(result),now()))
                            ledger.audit('channel-pricing',{'id':rid,'name':result['name']})
                        result['id']=rid
                elif path=='/api/item-plan':
                    if not ledger.db.execute('SELECT 1 FROM catalog WHERE source=? AND source_id=?',(value.get('source'),value.get('id'))).fetchone():raise AccountingError('Imported inventory item not found')
                    for key in ['reorderPoint','targetStock','leadTimeDays','shelfLifeDays']:
                        quantity(value.get(key,0))
                        if quantity(value.get(key,0))<0:raise AccountingError('Planning values cannot be negative')
                    if value.get('expiryDate'):day(value['expiryDate'])
                    with ledger.db:
                        ledger.db.execute('INSERT OR REPLACE INTO item_plans VALUES(?,?,?)',(value['source'],value['id'],json.dumps(value)))
                        ledger.audit('inventory-plan',{'source':value['source'],'id':value['id']})
                    result={'ok':True}
                elif path in {"/api/costing/calculate","/api/costing/save"}:
                    result=calculate(value)
                    if path.endswith("save"):
                        rid=str(value.get("id") or uuid.uuid4())
                        with ledger.db:
                            ledger.db.execute("INSERT OR REPLACE INTO recipes VALUES(?,?,?,?,?)",(rid,result["name"],json.dumps(value),json.dumps(result),now()))
                            ledger.audit("production-cost-estimate",{"id":rid,"name":result["name"],"batchCost":result["total"]})
                        result["id"]=rid
                elif path=="/api/settings":
                    ledger.set_settings(value);result={"ok":True}
                elif path=="/api/reconcile":result=ledger.reconcile(value)
                elif path=="/api/attachment":result=ledger.attach(value)
                elif path=="/api/account":
                    code=account_code(value.get("code"),"")
                    type_=value.get("type")
                    if type_ not in {"asset","liability","equity","income","expense"}:raise AccountingError("Invalid account type")
                    if not value.get("name","").strip():raise AccountingError("Account name required")
                    with ledger.db:
                        ledger.db.execute("INSERT INTO accounts VALUES(?,?,?)",(code,value["name"][:150],type_))
                        ledger.audit("account",value)
                    result={"ok":True}
                elif path=="/api/journal":
                    rows=[line(account_code(l.get("account"),""),cents(l.get("debit",0)),cents(l.get("credit",0))) for l in value.get("lines",[])]
                    if not rows:raise AccountingError("At least two balanced journal lines are required")
                    sid=str(uuid.uuid4())
                    doc=record("journal",{"id":sid,"date":value.get("date"),"memo":value.get("memo","")},rows,amount=sum(l["debit"] for l in rows),reference=value.get("reference") or sid)
                    result=ledger.import_documents("manual",[doc],value,"Manual journal")
                elif path=="/api/manual-document":
                    kind=value.get("kind")
                    if kind not in {"invoice","bill","expense"}:raise AccountingError("Choose invoice, bill or expense")
                    amount=cents(value.get("amount"))
                    tax=cents(value.get("tax",0))
                    if amount<=0 or tax<0:raise AccountingError("Enter positive subtotal and nonnegative tax")
                    if kind!="invoice" and tax:raise AccountingError("Include purchase tax in expense or bill amount")
                    total=amount+tax
                    account=account_code(value.get("account"),"4000" if kind=="invoice" else "5100")
                    acct=ledger.db.execute('SELECT type FROM accounts WHERE code=?',(account,)).fetchone()
                    if not acct or acct[0] not in ({'income'} if kind=='invoice' else {'expense','asset'}):raise AccountingError('Choose a revenue account for invoices, or an expense / asset account for purchases')
                    if value.get('dueDate'):day(value['dueDate'])
                    if not str(value.get('reference','')).strip():raise AccountingError('Reference is required')
                    if ledger.db.execute('SELECT 1 FROM documents WHERE source=? AND kind=? AND reference=?',('manual',kind,str(value['reference']))).fetchone():raise AccountingError('A transaction of this type already uses that reference')
                    if kind=="invoice":rows=pair("1100",account,amount)+pair("1100","2100",tax)
                    else:rows=pair(account,"2000" if kind=="bill" else "1020",amount)
                    sid=str(uuid.uuid4())
                    doc=record(kind,{**value,"id":sid},rows,amount=total,balance=total if kind!="expense" else 0,party=value.get("party",""),reference=value.get("reference") or sid)
                    result=ledger.import_documents("manual",[doc],value,"Manual "+kind)
                elif path=="/api/pay":
                    payment_id=str(value.get('paymentId') or uuid.uuid4())
                    if ledger.db.execute("SELECT 1 FROM documents WHERE source='manual' AND source_id=?",('payment:'+payment_id,)).fetchone():
                        self.respond({'duplicates':1,'added':0});return
                    source=value.get('source','manual')
                    r=ledger.db.execute("SELECT * FROM documents WHERE source=? AND source_id=?",(source,value.get("id"))).fetchone()
                    local_receipt=bool(r and source=='vendor' and r['kind']=='purchase-receipt')
                    if not r or not (local_receipt or (source=='manual' and r["kind"] in {"invoice","bill"})):raise AccountingError("Record source-app customer payments in their original app")
                    amount=cents(value.get("amount"))
                    balance=r['balance']-ledger.allocations().get((source,value.get('id')),0)
                    if amount<=0 or amount>balance:raise AccountingError("Payment must be positive and no more than the balance")
                    doc=json.loads(r["payload"])
                    doc["balance"]-=amount
                    doc.setdefault("paymentHistory",[]).append({"amount":amount,"date":day(value.get("date"))})
                    bank=account_code(value.get("account"),"1020")
                    if bank not in {"1010","1020","1030"}:raise AccountingError("Choose cash, bank or undeposited funds")
                    rows=pair(bank,"1100",amount) if r["kind"]=="invoice" else pair("2000",bank,amount)
                    payment=record("payment",{"id":payment_id,"date":value.get("date"),"memo":"Payment for "+r["reference"]},rows,amount=amount,party=r["party"])
                    if local_receipt:payment['appliedTo']={'source':source,'id':value.get('id')}
                    result=ledger.import_documents("manual",[payment] if local_receipt else [doc,payment],value,"Manual payment")
                elif path=='/api/void':
                    r=ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND source_id=?",(value.get('id'),)).fetchone()
                    if not r:raise AccountingError('Only business-accounting records can be voided here')
                    doc=json.loads(r[0])
                    if doc['kind'] not in {'invoice','bill','expense','journal'}:raise AccountingError('Use a correcting journal for this record')
                    if doc.get('paymentHistory'):raise AccountingError('This record has payments. Record a refund or correcting journal rather than voiding it.')
                    doc.update(lines=[],amount=0,balance=0,kind='voided-'+doc['kind'],memo=doc.get('memo','')+' · Voided')
                    result=ledger.import_documents('manual',[doc],value,'Void business record')
                elif path=="/api/cost":
                    sid=str(value.get("id"))
                    cost=str(value.get("unitCost"))
                    if quantity(cost)<0:raise AccountingError("Unit cost cannot be negative")
                    r=ledger.db.execute("SELECT payload FROM documents WHERE source='vendor' AND source_id=?",("inventory:"+sid,)).fetchone()
                    if not r:raise AccountingError("Inventory movement not found")
                    old=json.loads(r[0]);original={**old["original"],"unitCost":cost}
                    amount=cents(quantity(original["quantity"])*quantity(cost))
                    type_=original.get("type")
                    if type_ not in {"opening_balance","bulk_opening_balance","delivery","credit_return","return","sellable_return","return_sellable","adjustment","damaged","expired","waste","return_damaged","return_expired","return_quarantine"}:raise AccountingError("Review this movement's accounting classification first")
                    rows=[] if type_ in {'return_damaged','return_expired','return_quarantine'} else pair("1200","3100" if "opening_balance" in type_ else "5000",amount)
                    doc=record("inventory",original,rows,amount=amount)
                    result=ledger.import_documents("vendor",[doc],value,"Historical inventory cost correction",overrides=[(sid,cost)])
                else:
                    self.respond({"error":"Not found"},404);return
            self.respond(result)
        except (AccountingError,ValueError,KeyError,TypeError,sqlite3.IntegrityError) as exc:
            self.respond({"error":str(exc)},400)
        except Exception:
            import traceback
            traceback.print_exc()
            self.respond({"error":"Unexpected server error; no successful operation was confirmed. Check the server log."},500)
        finally:
            if ledger:ledger.close()
            self.app.write_lock.release()

    def auth_request(self,path):
        if not self.trusted_request() or self.headers.get('X-Accounting-Request')!='1' or not secrets.compare_digest(self.cookie_value('bw_bootstrap'),self.app.cookie):
            self.respond({'error':'Open the sign-in page directly'},403);return
        ledger=self.app.ledger()
        self.app.write_lock.acquire()
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>4096:raise AccountingError('Invalid sign-in request')
            value=json.loads(self.rfile.read(length))
            if path=='/api/auth/setup':
                auth.create_user(ledger,value,first=True)
                token,user=auth.login(ledger,value);self.respond({'user':user},session_token=token)
            elif path=='/api/auth/login':
                token,user=auth.login(ledger,value);self.respond({'user':user},session_token=token)
            elif path=='/api/auth/firebase-login':
                uid=self.app.firebase.verify_identity(str(value.get('idToken','')))
                row=ledger.db.execute('SELECT u.* FROM users u JOIN firebase_link f ON f.user_id=u.id WHERE f.uid=?',(uid,)).fetchone()
                if not row:raise AccountingError('This Firebase account has not been linked to the company ledger by its owner')
                token,user=auth.issue_session(ledger,row);self.respond({'user':user},session_token=token)
            elif path=='/api/auth/logout':
                auth.logout(ledger,self.cookie_value('bw_session'));self.respond({'ok':True},session_token='')
            elif path=='/api/auth/password':
                user=auth.session_user(ledger,self.cookie_value('bw_session'))
                if not user:raise AccountingError('Sign in first')
                auth.change_password(ledger,user,value);self.respond({'ok':True},session_token='')
            else:self.respond({'error':'Unknown authentication action'},404)
        except (AccountingError,ValueError,KeyError,sqlite3.IntegrityError) as exc:self.respond({'error':str(exc)},400)
        finally:ledger.close();self.app.write_lock.release()


class Handler(SharedHandlerMixin,LocalHandler):
    pass


def main():
    parser=argparse.ArgumentParser(description="Backwoods Business Accounting")
    parser.add_argument("--data-dir",type=Path,default=default_data_dir())
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument('--public-origin',help='Trusted HTTPS origin of a separately configured TLS reverse proxy; backend remains bound to loopback')
    parser.add_argument("--restore",type=Path,help="Restore a downloaded database backup while the app is stopped")
    args=parser.parse_args()
    run_lock=RunLock(args.data_dir)
    if args.restore:
        candidate=sqlite3.connect(args.restore.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            if candidate.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise AccountingError("Backup integrity check failed")
            if candidate.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()[0]!="1":raise AccountingError("Unsupported backup schema")
            required={"documents","entries","lines","accounts","batches","attachments","audit","cost_overrides","reconciliations","reconciliation_lines","settings","recipes","catalog","item_plans","pricing","assets","employees","users","sessions","provider_reviews","provider_actions","provider_cache","tax_sources","tax_changes"}
            if not required.issubset({r[0] for r in candidate.execute("SELECT name FROM sqlite_master WHERE type='table'")}):raise AccountingError("Incomplete accounting backup")
            if candidate.execute("PRAGMA foreign_key_check").fetchone():raise AccountingError("Backup has broken references")
            args.data_dir.mkdir(parents=True,exist_ok=True)
            target=args.data_dir/"accounting.sqlite3"
            if target.exists():
                old=sqlite3.connect(target)
                saved=sqlite3.connect(args.data_dir/("before-restore-"+str(uuid.uuid4())+".sqlite3"))
                try:old.backup(saved)
                finally:old.close();saved.close()
            dest=sqlite3.connect(target)
            try:
                candidate.backup(dest)
                dest.execute('DELETE FROM sessions');dest.commit()
            finally:dest.close()
            print("Backup restored; previous database preserved. Start the app normally.")
        finally:candidate.close();run_lock.close()
        return
    app=Application(args.data_dir,public_origin=args.public_origin)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.application=app
    thread=threading.Thread(target=app.watch_feeds,daemon=True)
    threading.Thread(target=app.watch_firebase,daemon=True).start()
    thread.start()
    tax_thread=threading.Thread(target=tax_watch.monitor,args=(app,),daemon=True)
    tax_thread.start()
    url=f"http://127.0.0.1:{server.server_port}"
    print("Backwoods Business Accounting is running locally.",flush=True)
    print("Data directory:",app.data_dir,flush=True)
    print("Open:",url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.stop.set();server.server_close();thread.join(timeout=5);tax_thread.join(timeout=2);run_lock.close()


if __name__=="__main__":main()
