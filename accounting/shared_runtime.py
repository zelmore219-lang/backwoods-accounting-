"""HTTP integration for the installed Firestore-shared accounting engine."""
import io
import hashlib
import json
import re
import time
from urllib.parse import urlparse
from .ledger import AccountingError
from . import auth
from .firebase_sync import SCHEMA

def company_sign_in(app,email,password):
    """Sign into Google, then open that owner's single shared company ledger."""
    client=app.firebase;result=client.sign_in(email,password);uid=result['localId']
    if not re.fullmatch('[-A-Za-z0-9_]{1,128}',uid):raise AccountingError('Unsupported company identity')
    ledger=app.ledger()
    try:
        bound=ledger.db.execute('SELECT * FROM firebase_link').fetchone()
        if bound and bound['uid']!=uid:raise AccountingError('This profile already belongs to another company. Use a separate app profile; company books are never mixed.')
    finally:ledger.close()
    client.connection={'uid':uid,'refreshToken':result['refreshToken']};client.token=result['idToken'];client.expires=time.time()+int(result.get('expiresIn',3600))-120
    # A private ledger read enforces the deployed active-owner rules before saving
    # credentials. A missing document means a new company, not permission bypass.
    app.shared.get()
    client.vault.save(client.connection)
    with app.write_lock:
        app.shared.last_checked=0;app.shared.refresh()
        ledger=app.ledger()
        try:
            ledger.db.executescript(SCHEMA)
            owner=ledger.db.execute("SELECT * FROM users WHERE role='owner' ORDER BY created_at LIMIT 1").fetchone()
            if not owner:return {'requiresOwnerSetup':True}
            with ledger.db:
                ledger.db.execute('INSERT OR IGNORE INTO firebase_link VALUES(?,?,?)',(uid,owner['id'],email))
            token,user=auth.issue_session(ledger,owner)
            response={'user':user,'sessionToken':token}
        finally:ledger.close()
        link_initial_owner(app)
        return response

def link_initial_owner(app):
    if not app.shared.connected():return
    if not app.firebase.bearer():return
    ledger=app.ledger()
    try:
        owner=ledger.db.execute("SELECT id,username FROM users WHERE role='owner' ORDER BY created_at LIMIT 1").fetchone()
        if not owner:raise AccountingError('Create the company owner account first')
        with ledger.db:ledger.db.execute('INSERT OR IGNORE INTO firebase_link VALUES(?,?,?)',(app.firebase.connection['uid'],owner['id'],owner['username']))
    finally:ledger.close()
    with app.shared.mutation():pass

class SharedHandlerMixin:
    def send_bytes(self,data,*args,**kwargs):
        if getattr(self,'_buffer_shared_response',False):
            self._shared_response=(data,args,kwargs);return
        return super().send_bytes(data,*args,**kwargs)
    def do_GET(self):
        with self.app.write_lock:
            try:
                if self.authorized():self.app.shared.refresh()
            except AccountingError as error:self.app.firebase_status={'connected':False,'message':'Showing cached books. '+str(error)}
            return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/auth/firebase-sign-in':return self.firebase_sign_in()
        private=path.startswith('/api/auth/')
        attaching=path in {'/api/auth/setup','/api/firebase/connect'}
        if private and not attaching:return super().do_POST()
        if not private and not attaching and (not self.authorized() or self.headers.get('X-Accounting-Request')!='1'):
            return super().do_POST()
        if path in {'/api/costing/calculate','/api/pricing/calculate','/api/payroll/preview','/api/import/preview','/api/provider/flow','/api/provider/health','/api/tax-watch/check'}:
            with self.app.write_lock:return super().do_POST()
        self._buffer_shared_response=True;self._shared_response=None
        try:
            if attaching:
                super().do_POST()
                if self._shared_response and self._shared_response[2].get('status',200)<300:link_initial_owner(self.app)
            else:
                with self.app.shared.mutation():
                    fresh_authorized=self.authorized()
                    operation=self.headers.get('X-Accounting-Operation','')
                    cacheable=fresh_authorized and self.user['role']!='viewer' and bool(re.fullmatch('[a-f0-9-]{36}',operation)) and path in {
                        '/api/manual-document','/api/pay','/api/journal','/api/void','/api/assets/register',
                        '/api/assets/depreciate','/api/assets/dispose','/api/payroll/post','/api/payroll/pay',
                        '/api/liability-payment','/api/reconcile','/api/attachment','/api/import'}
                    cached=None
                    if cacheable:
                        length=int(self.headers.get('Content-Length','0'))
                        if not 1<=length<=40*1024*1024:raise AccountingError('Invalid posting body size')
                        raw=self.rfile.read(length);self.rfile=io.BytesIO(raw)
                        request_hash=hashlib.sha256(raw).hexdigest()
                        db=self.app.ledger()
                        try:
                            db.db.execute('CREATE TABLE IF NOT EXISTS shared_requests(id TEXT PRIMARY KEY,path TEXT NOT NULL,request_hash TEXT NOT NULL,status INTEGER NOT NULL,body BLOB NOT NULL)')
                            db.db.commit()
                            cached=db.db.execute('SELECT path,request_hash,status,body FROM shared_requests WHERE id=?',(operation,)).fetchone()
                        finally:db.close()
                    if cached:
                        if cached['path']!=path or cached['request_hash']!=request_hash:raise AccountingError('A pending operation belongs to different posting details')
                        self._shared_response=(cached['body'],(),{'status':cached['status']})
                        # Consume the body so persistent HTTP connections stay aligned.
                        length=int(self.headers.get('Content-Length','0'))
                        self.rfile.read(length)
                    else:
                        super().do_POST()
                        if cacheable and self._shared_response:
                            body,_,kwargs=self._shared_response;status=kwargs.get('status',200)
                            if status<300:
                                db=self.app.ledger()
                                try:
                                    with db.db:db.db.execute('INSERT INTO shared_requests VALUES(?,?,?,?,?)',(operation,path,request_hash,status,body))
                                finally:db.close()
            response=self._shared_response
        except (AccountingError,ValueError,KeyError) as error:
            response=(json.dumps({'error':str(error)}).encode(),(),{'status':409})
        finally:self._buffer_shared_response=False
        if response:super().send_bytes(response[0],*response[1],**response[2])
    def firebase_sign_in(self):
        if not self.trusted_request() or self.headers.get('X-Accounting-Request')!='1' or self.cookie_value('bw_bootstrap')!=self.app.cookie:
            self.respond({'error':'Open the company sign-in screen directly'},403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=4096:raise AccountingError('Invalid sign-in request')
            value=json.loads(self.rfile.read(length))
            with self.app.write_lock:
                result=company_sign_in(self.app,value.get('email',''),value.get('password',''))
            token=result.pop('sessionToken',None)
            self.respond(result,session_token=token)
        except (AccountingError,ValueError,KeyError) as error:self.respond({'error':str(error)},400)
