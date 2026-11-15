"""Employee-controlled native sessions and encrypted, durable bridge requests."""
import base64, hashlib, json, os, secrets, threading, time, uuid, zlib
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

PROJECT='backwoodsbrew-e3584-d52a3'
API_KEY='AIzaSyB4Dqp0Du2lGMAqryTRPfvHuBgt69jSmF8'
BASE='https://firestore.googleapis.com/v1/projects/'+PROJECT+'/databases/(default)/documents/'
PROTOCOL='backwoods-employee-relay-v1'
_sessions={};_lock=threading.RLock()
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('An authenticated connection was redirected')

def http(url,data=None,token=None,method=None):
 if not url.startswith(('https://firestore.googleapis.com/','https://identitytoolkit.googleapis.com/','https://securetoken.googleapis.com/')):raise ValueError('Unexpected connection address')
 headers={'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 try:
  with build_opener(NoRedirect()).open(Request(url,json.dumps(data).encode() if data is not None else None,headers,method=method),timeout=25) as r:
   body=r.read(32*1024*1024+1)
   if len(body)>32*1024*1024:raise ValueError('Connection response is too large')
   return json.loads(body)
 except HTTPError as e:
  if e.code==404:return None
  raise ValueError('Backwoods connection denied or unavailable ('+str(e.code)+'). Check Employee access and Owner service.') from None
 except (URLError,TimeoutError):raise ValueError('Backwoods is offline. Your saved work remains queued for retry.') from None

def decode(v):
 for key in ['stringValue','booleanValue','timestampValue','integerValue','doubleValue','nullValue']:
  if key in v:return int(v[key]) if key=='integerValue' else v[key]
 if 'mapValue' in v:return unpack(v['mapValue'])
 if 'arrayValue' in v:return [decode(x) for x in v['arrayValue'].get('values',[])]
 raise ValueError('Unsupported Firebase value')
def unpack(d):return {k:decode(v) for k,v in (d or {}).get('fields',{}).items()}
def fields(v):return {k:({'booleanValue':x} if isinstance(x,bool) else {'integerValue':str(x)} if isinstance(x,int) else {'stringValue':x}) for k,x in v.items()}
def claims(token):return json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
def login(username,password,company):
 username=str(username).strip().casefold();email=username if '@' in username else username+'@'+PROJECT+'.firebaseapp.com'
 result=http('https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key='+API_KEY,{'email':email,'password':password,'returnSecureToken':True})
 if not result or not result.get('localId'):raise ValueError('Employee sign-in was not confirmed')
 credentials={'uid':result['localId'],'token':result['idToken'],'refresh':result['refreshToken'],'expires':time.time()+int(result.get('expiresIn',3600)),'company':company,'username':username,'sessionExpires':time.time()+28800}
 if company is None:
  credentials['company']=unpack(http(BASE+'employeeAccess/'+credentials['uid'],token=credentials['token'])).get('companyId')
 person=access(credentials)
 token=secrets.token_urlsafe(32)
 with _lock:_sessions[hashlib.sha256(token.encode()).hexdigest()]=credentials
 return token,person

def access(credentials):
 if credentials['sessionExpires']<=time.time():raise ValueError('Sign in again with your Employee account')
 if credentials['expires']<time.time()+60:
  # Firebase accepts JSON refresh requests as well as its form transport.
  result=http('https://securetoken.googleapis.com/v1/token?key='+API_KEY,{'grant_type':'refresh_token','refresh_token':credentials['refresh']})
  if not result or result.get('user_id')!=credentials['uid']:raise ValueError('The Employee identity could not be renewed')
  credentials.update(token=result['id_token'],refresh=result.get('refresh_token',credentials['refresh']),expires=time.time()+int(result.get('expires_in',3600)))
 token=credentials['token'];c=claims(token)
 if c.get('aud')!=PROJECT or c.get('iss')!='https://securetoken.google.com/'+PROJECT:raise ValueError('Employee project mismatch')
 result=http('https://identitytoolkit.googleapis.com/v1/accounts:lookup?key='+API_KEY,{'idToken':token});users=(result or {}).get('users',[])
 if len(users)!=1 or users[0].get('localId')!=credentials['uid'] or users[0].get('disabled'):raise ValueError('Employee account is disabled')
 person=unpack(http(BASE+'employeeAccess/'+credentials['uid'],token=token))
 role=person.get('applications',{}).get('production')
 if person.get('uid')!=credentials['uid'] or person.get('companyId')!=credentials['company'] or person.get('username','').casefold()!=credentials['username'] or person.get('accountActive') is not True or person.get('employmentStatus')!='active' or person.get('mustChangePassword') is not False or role not in {'production_manager','production_employee','purchasing'}:raise ValueError('Active Production access must be assigned in Employee/Employer. Finish activation and any password change there.')
 if int(c.get('auth_time',0))<max(int(person.get('passwordValidAfter',0)),int(users[0].get('validSince') or 0)):raise ValueError('This Employee sign-in was revoked')
 return {'id':'employee:'+credentials['uid'],'name':person['name'],'role':{'production_manager':'manager','production_employee':'operator','purchasing':'purchasing'}[role],'employeeManaged':True,'company':person['companyId']}

def current(token):
 with _lock:credentials=_sessions.get(hashlib.sha256(token.encode()).hexdigest())
 if not credentials:return None
 return access(credentials)
def logout(token):
 with _lock:_sessions.pop(hashlib.sha256(token.encode()).hexdigest(),None)

def bridge(token,data,directory):
 """Only encrypted mailbox ciphertext and request keys persist; no login secrets."""
 with _lock:credentials=_sessions.get(hashlib.sha256(token.encode()).hexdigest())
 if not credentials:raise ValueError('Sign in with your Employee account to synchronize')
 actor=access(credentials)
 if actor['role']!='manager':raise ValueError('Production manager access required')
 try:
  from cryptography.hazmat.primitives import hashes,serialization
  from cryptography.hazmat.primitives.asymmetric import ec
  from cryptography.hazmat.primitives.ciphers.aead import AESGCM
  from cryptography.hazmat.primitives.kdf.hkdf import HKDF
 except ImportError:raise ValueError('Install the connected Production runtime to enable the secure Employee bridge') from None
 config=unpack(http(BASE+'employeeService/config',token=credentials['token']))
 if config.get('project')!=PROJECT or config.get('protocol')!=PROTOCOL or config.get('productionBridgeVersion')!=1:raise ValueError('Update Employee/Employer Owner service to enable the Production bridge')
 uid=credentials['uid'];data={**data,'companyId':credentials['company']}
 raw=json.dumps({'method':'POST','path':'/api/production-bridge','data':data,'scope':'account'},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
 if len(raw)>12*1024*1024:raise ValueError('Production synchronization exceeds the 12 MB bridge limit')
 folder=Path(directory)/'production-pending';folder.mkdir(exist_ok=True,mode=0o700)
 file=folder/(hashlib.sha256(uid.encode()+raw).hexdigest()+'.json')
 b64=lambda v:base64.b64encode(v).decode()
 un64=lambda v:base64.b64decode(v,validate=True)
 with _lock:
  if file.exists():pending=json.loads(file.read_text())
  else:
   private=ec.generate_private_key(ec.SECP256R1());rid=uuid.uuid4().hex
   aad=json.dumps([PROTOCOL,PROJECT,uid,rid],sort_keys=True,separators=(',',':')).encode()
   peer=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),un64(config['publicKey']))
   key=HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(aad).digest(),info=(PROTOCOL+'/request').encode()).derive(private.exchange(ec.ECDH(),peer))
   nonce=os.urandom(12);payload=nonce+AESGCM(key).encrypt(nonce,zlib.compress(raw,6),aad)
   pending={'id':rid,'peer':config['publicKey'],'private':b64(private.private_numbers().private_value.to_bytes(32,'big')),'public':b64(private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)),'payload':b64(payload),'authTime':int(claims(credentials['token'])['auth_time'])}
   temp=file.with_suffix('.tmp');temp.write_text(json.dumps(pending));temp.chmod(0o600);temp.replace(file)
 if pending['peer']!=config['publicKey']:raise ValueError('The Owner service key changed; review the saved transfer before retrying')
 private=ec.derive_private_key(int.from_bytes(un64(pending['private']),'big'),ec.SECP256R1());rid=pending['id'];payload=un64(pending['payload'])
 aad=json.dumps([PROTOCOL,PROJECT,uid,rid],separators=(',',':')).encode()
 path='employeeRequests/'+rid
 def get(p,missing=False):
  try:return unpack(http(BASE+p,token=credentials['token']))
  except ValueError:
   if missing:return {}
   raise
 def commit(writes):return http(BASE.rstrip('/')+':commit',{'writes':writes},credentials['token'])
 name=BASE.split('/v1/',1)[1]+path
 envelope=get(path,True)
 if not envelope:
  value={'uid':uid,'requestId':rid,'protocol':PROTOCOL,'scope':'account','peer':pending['public'],'hash':hashlib.sha256(payload).hexdigest(),'count':(len(payload)+179999)//180000,'state':'uploading','authTime':pending['authTime']}
  try:commit([{'update':{'name':name,'fields':fields(value)},'currentDocument':{'exists':False},'updateTransforms':[{'fieldPath':'createdAt','setToServerValue':'REQUEST_TIME'}]}]);envelope={'state':'uploading'}
  except ValueError:
   envelope=get(path)
   if not envelope:raise
 if envelope.get('state')=='uploading':
  for i,start in enumerate(range(0,len(payload),180000)):commit([{'update':{'name':name+'/requestParts/'+str(i).zfill(4),'fields':fields({'data':b64(payload[start:start+180000])})}}])
  commit([{'update':{'name':name,'fields':fields({'state':'pending'})},'updateMask':{'fieldPaths':['state']},'currentDocument':{'exists':True},'updateTransforms':[{'fieldPath':'readyAt','setToServerValue':'REQUEST_TIME'}]}])
 deadline=time.monotonic()+40
 while True:
  envelope=get(path)
  if envelope.get('state')=='done':break
  if envelope.get('state')=='failed' or time.monotonic()>=deadline:raise ValueError('Transfer is queued. Keep Employee Owner service online; retry to retrieve the same receipt.')
  time.sleep(1)
 count=envelope.get('responseCount')
 if type(count)is not int or not 1<=count<=200:raise ValueError('Invalid bridge response')
 response=b''.join(un64(get(path+'/responseParts/'+str(i).zfill(4))['data']) for i in range(count))
 if len(response)>32*1024*1024 or hashlib.sha256(response).hexdigest()!=envelope.get('responseHash'):raise ValueError('Bridge response integrity check failed')
 peer=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),un64(pending['peer']))
 key=HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(aad).digest(),info=(PROTOCOL+'/response').encode()).derive(private.exchange(ec.ECDH(),peer))
 packed=AESGCM(key).decrypt(response[:12],response[12:],aad);decoder=zlib.decompressobj();plain=decoder.decompress(packed,32*1024*1024+1)
 if len(plain)>32*1024*1024 or not decoder.eof or decoder.unused_data:raise ValueError('Invalid compressed bridge response')
 reply=json.loads(plain);result=json.loads(un64(reply['body']));file.unlink(missing_ok=True)
 if reply['status']!=200:raise ValueError(result.get('error') or result.get('message') or 'Production bridge rejected this request')
 return result
