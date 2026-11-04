"""Firebase Auth + immutable financial snapshots, using verified HTTPS REST.

No admin keys. Each ledger is explicitly bound by its owner to one Firebase UID.
Windows refresh credentials use DPAPI; hosted services use secret environment bindings.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .ledger import AccountingError,now
from .payroll_provider import SecretStore

CONFIG=json.loads((Path(__file__).with_name('firebase-config.json')).read_text())
SCHEMA='CREATE TABLE IF NOT EXISTS firebase_link(uid TEXT PRIMARY KEY,user_id TEXT NOT NULL UNIQUE,email TEXT NOT NULL);'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise AccountingError('Firebase redirected an authenticated request; no credential was forwarded')

def request(url,value=None,token=None,form=False):
    # All destinations are generated internally, never accepted from source data.
    if not url.startswith(('https://identitytoolkit.googleapis.com/','https://securetoken.googleapis.com/','https://firestore.googleapis.com/')):
        raise AccountingError('Unexpected Firebase destination')
    data=(urlencode(value) if form else json.dumps(value)).encode() if value is not None else None
    headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'}
    if token:headers['Authorization']='Bearer '+token
    try:
        with build_opener(NoRedirect()).open(Request(url,data,headers),timeout=25) as response:
            body=response.read(2*1024*1024+1)
            if len(body)>2*1024*1024:raise AccountingError('Firebase response exceeds the document limit')
            return json.loads(body)
    except HTTPError as error:
        if error.code==404:return None
        raise AccountingError('Firebase access denied or unavailable. Check the company sign-in and deployed accounting rules ('+str(error.code)+').') from None
    except (URLError,TimeoutError):raise AccountingError('Firebase is unreachable. Saved records will retry when the connection returns.') from None

class Vault(SecretStore):
    def __init__(self,directory):self.path=Path(directory)/'firebase-connection.dpapi'
    def read(self):
        token=os.environ.get('BACKWOODS_FIREBASE_REFRESH_TOKEN')
        uid=os.environ.get('BACKWOODS_FIREBASE_UID')
        if token and uid:return {'refreshToken':token,'uid':uid}
        if not self.path.exists():return None
        if os.name!='nt':raise AccountingError('Use protected Firebase environment bindings on the hosted service')
        return json.loads(self.dpapi(self.path.read_bytes(),False))
    def save(self,value):
        if os.name=='nt':return super().save(value)
        configured=self.read()
        if not configured or configured['uid']!=value['uid']:
            raise AccountingError('Configure the company Firebase UID and refresh token in the hosted service secret bindings before linking this ledger')
        # Hosted deployments retain their configured secret binding, never a
        # plaintext credential file. Fresh credentials stay in process memory.

class Firebase:
    def __init__(self,directory,transport=request,vault=None):
        self.vault=vault or Vault(directory);self.transport=transport
        self.connection=None;self.token=None;self.expires=0
    def sign_in(self,email,password):
        result=self.transport('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key='+CONFIG['apiKey'],{'email':email,'password':password,'returnSecureToken':True})
        if not result or not result.get('localId') or not result.get('refreshToken'):raise AccountingError('Firebase did not confirm the company account')
        return result
    def connect(self,ledger,user,email,password):
        result=self.sign_in(email,password);uid=result['localId']
        if not re.fullmatch(r'[-A-Za-z0-9_]{1,128}',uid):raise AccountingError('Unsupported Firebase identity')
        ledger.db.executescript(SCHEMA)
        prior=ledger.db.execute('SELECT * FROM firebase_link').fetchone()
        if prior and (prior['uid']!=uid or prior['user_id']!=user['id']):raise AccountingError('This ledger is already bound to another company identity. A reviewed migration is required.')
        self.vault.save({'uid':uid,'refreshToken':result['refreshToken']})
        with ledger.db:
            ledger.db.execute('INSERT OR REPLACE INTO firebase_link VALUES(?,?,?)',(uid,user['id'],str(email)))
            ledger.audit('firebase-linked',{'uid':uid,'user_id':user['id']})
        self.connection={'uid':uid,'refreshToken':result['refreshToken']};self.token=result['idToken'];self.expires=time.time()+int(result.get('expiresIn',3600))-120
        return {'connected':True,'email':email}
    def bearer(self):
        if not self.connection:self.connection=self.vault.read()
        if not self.connection:return None
        if not self.token or time.time()>=self.expires:
            result=self.transport('https://securetoken.googleapis.com/v1/token?key='+CONFIG['apiKey'],{'grant_type':'refresh_token','refresh_token':self.connection['refreshToken']},form=True)
            if not result or result.get('user_id')!=self.connection['uid']:raise AccountingError('Firebase company identity changed; reconnect as owner')
            self.token=result['id_token'];self.expires=time.time()+int(result.get('expires_in',3600))-120
        return self.token
    def root(self):return 'projects/'+CONFIG['projectId']+'/databases/(default)/documents/businessAccounting/'+self.connection['uid']
    def document(self,path):return self.transport('https://firestore.googleapis.com/v1/'+path,token=self.bearer())
    def snapshot(self,source,previous=None):
        if not self.bearer():return None
        root=self.root()+'/sources/'+source
        meta=self.document(root)
        if not meta:return None
        f=meta.get('fields',{});get=lambda key,kind='stringValue':f[key][kind]
        digest=get('sha256');generation=get('generation');count=int(get('chunkCount','integerValue'));size=int(get('bytes','integerValue'))
        if digest==previous:return None
        if not re.fullmatch('[a-f0-9]{64}',digest) or not re.fullmatch('[-a-fA-F0-9]{36}',generation) or not 1<=count<=175 or not 1<=size<=40*1024*1024:raise AccountingError('Invalid Firebase accounting snapshot manifest')
        chunks=[];total=0
        for index in range(count):
            chunk=self.document(root+'/generations/'+generation+'/chunks/'+str(index).zfill(4))
            if not chunk:raise AccountingError('Firebase snapshot is incomplete; no records were imported')
            raw=base64.b64decode(chunk['fields']['data']['stringValue'],validate=True);total+=len(raw)
            if len(raw)>240000 or total>size:raise AccountingError('Firebase snapshot exceeds its declared size')
            chunks.append(raw)
        raw=b''.join(chunks)
        if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:raise AccountingError('Firebase snapshot integrity check failed; no records were imported')
        # Concurrent publications are retried; never combine generations.
        latest=self.document(root)
        if not latest or latest.get('updateTime')!=meta.get('updateTime'):raise AccountingError('Firebase snapshot changed while reading; retrying the new generation')
        packet=json.loads(raw)
        if packet.get('type')!='business-accounting-feed' or packet.get('schemaVersion')!=1:raise AccountingError('Unsupported Firebase accounting feed')
        packet['exportedAt']=get('exportedAt')
        return digest,packet
    def publish_service(self,origin):
        if not origin or not self.bearer():return
        if getattr(self,'published_origin',None)==origin:return
        from urllib.parse import urlparse
        p=urlparse(origin)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.path not in {'','/'} or p.query or p.fragment:raise AccountingError('The accounting service needs a valid HTTPS origin')
        name=self.root()+'/settings/service'
        self.transport('https://firestore.googleapis.com/v1/projects/'+CONFIG['projectId']+'/databases/(default)/documents:commit',{'writes':[{'update':{'name':name,'fields':{'origin':{'stringValue':origin},'updatedAt':{'stringValue':now()}}}}]},token=self.bearer())
        self.published_origin=origin
    def verify_identity(self,id_token):
        try:
            claims=json.loads(base64.urlsafe_b64decode(id_token.split('.')[1]+'==='))
            if not isinstance(claims,dict):raise ValueError()
            if claims.get('aud')!=CONFIG['projectId'] or claims.get('iss')!='https://securetoken.google.com/'+CONFIG['projectId']:raise ValueError()
        except (ValueError,IndexError,KeyError,TypeError):raise AccountingError('Invalid company sign-in token') from None
        # Claims above are only a project prefilter. Google verifies the signature,
        # expiration and account identity before any ledger session is issued.
        result=self.transport('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key='+CONFIG['apiKey'],{'idToken':id_token})
        users=(result or {}).get('users',[])
        if len(users)!=1 or users[0].get('disabled') or users[0].get('localId')!=claims.get('sub'):raise AccountingError('Firebase did not verify this company sign-in')
        # Enforce the deployed active-owner rules as well as Google Auth.
        service=self.transport('https://firestore.googleapis.com/v1/projects/'+CONFIG['projectId']+'/databases/(default)/documents/businessAccounting/'+users[0]['localId']+'/settings/service',token=id_token)
        if not service:raise AccountingError('The private company accounting service has not been deployed or this owner access is no longer active')
        return users[0]['localId']
