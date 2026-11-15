import sqlite3,json,uuid,os,hashlib,secrets,time,hmac,threading,argparse
import operations,finance,connected,sync
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).parent
import sys
if os.name=='nt' and sys.version_info[:2]==(3,14):sys.path.insert(0,str(ROOT/'vendor'))
DB=Path(os.environ.get('BACKWOODS_DB_PATH') or ROOT/'backwoods.db')

PRIVATE_COST_FIELDS = {
 'cost', 'total', 'per_lb', 'standard_material_cost', 'material_variance',
 'manufacturing_cost', 'labor', 'energy', 'overhead', 'other', 'packaging',
 'seasoning', 'price', 'freight', 'landed', 'previous_landed', 'increase',
 'amount', 'expected', 'credit', 'estimated_cost', 'estimated_material_cost',
 'planned_extra_cost', 'estimated_total_cost', 'packaging_cost', 'cost_lines', 'invoice_total'
}

def hide_costs(value):
 if isinstance(value, list):
  return [hide_costs(item) for item in value]
 if isinstance(value, dict):
  return {key: hide_costs(item) for key, item in value.items()
          if key not in PRIVATE_COST_FIELDS
          and not (key == 'unit' and isinstance(item, (int, float)))}
 return value

def connect():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def initialize():
 with connect() as c:
  c.executescript((ROOT/'schema.sql').read_text());finance.initialize(c)
def apply(c,kind,d,event):
 if c.execute('select 1 from events where id=?',(event,)).fetchone():return {'duplicate':True}
 if kind=='receive_supplies':
  quantity=operations.number(d['quantity'],True)
  total=operations.number(d['invoice_total'])
  freight=operations.number(d.get('freight') or 0)
  if not d.get('lot','').strip():raise ValueError('Enter the supplier lot')
  if not d.get('name','').strip():raise ValueError('Enter the receipt reference')
  operations.get(c,d['supplier'],'suppliers')
  operations.get(c,d['material'],'materials')
  purchase=operations.save(c,'purchases',dict(name=d['name'],supplier=d['supplier'],material=d['material'],
   quantity=quantity,cost=total/quantity,freight=freight,status='Approved',actor=d.get('actor')))
  apply(c,'receive',dict(id=purchase,quantity=quantity,lot=d['lot'],expires=d.get('expires'),
   location=d.get('location'),actor=d.get('actor')),str(uuid.uuid4()))
 elif operations.apply(c,kind,d,event):pass
 elif kind in ('suppliers','materials','recipes','purchases'):
  if kind=='recipes':raise ValueError('Use version-controlled recipe_versions')
  if not d.get('name','').strip():raise ValueError('Name is required')
  if kind=='materials':
   operations.number(d.get('quantity',0));operations.number(d.get('cost',0))
   if d.get('unit','lb') not in operations.FACTORS:raise ValueError('Unsupported stock unit')
  if kind=='purchases':
   operations.get(c,d['material'],'materials');operations.get(c,d['supplier'],'suppliers');operations.number(d['quantity'],True);operations.number(d['cost']);operations.number(d.get('freight',0))
   d['status']='Draft'
  if kind=='materials' and (float(d.get('quantity',0))<0 or float(d.get('cost',0))<0):raise ValueError('Quantity and cost cannot be negative')
  ident=str(uuid.uuid4());c.execute('insert into records values(?,?,?)',(ident,kind,json.dumps(d)))
  if kind=='materials' and float(d.get('quantity',0))>0:
   c.execute('insert into lots(id,material,source_lot,quantity,cost,location) values(?,?,?,?,?,?)',(str(uuid.uuid4()),ident,d.get('lot','Opening balance'),d['quantity'],d['cost'],d.get('location','')))
 elif kind=='receive':
  row=c.execute('select data from records where id=? and kind="purchases"',(d['id'],)).fetchone()
  if not row:raise ValueError('Purchase not found')
  p=json.loads(row[0]);qty=operations.number(d['quantity'],True);remaining=float(p['quantity'])-float(p.get('received',0))
  if p.get('status')!='Approved':raise ValueError('Purchase order approval required')
  if qty<=0 or qty>remaining:raise ValueError('Receipt exceeds outstanding quantity')
  p['received']=float(p.get('received',0))+qty
  c.execute('update records set data=? where id=?',(json.dumps(p),d['id']))
  m=c.execute('select data from records where id=? and kind="materials"',(p['material'],)).fetchone()
  if not m:raise ValueError('Material not found')
  m=json.loads(m[0]);old=float(m['quantity']);cost=float(p['cost'])+float(p.get('freight',0))/float(p['quantity'])
  m['cost']=(old*float(m['cost'])+qty*cost)/(old+qty);m['quantity']=old+qty
  c.execute('update records set data=? where id=?',(json.dumps(m),p['material']))
  c.execute('insert into movements values(?,?,?,?,?,datetime("now"))',(str(uuid.uuid4()),p['material'],qty,d['lot'],event))
  c.execute('insert into lots(id,material,supplier,source_lot,quantity,cost,expires,location) values(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),p['material'],p.get('supplier'),d['lot'],qty,cost,d.get('expires'),d.get('location','')))
 elif kind=='batches':
  raise ValueError('Use approved BOM manufacture operation')
  recipe=c.execute('select data from records where id=? and kind="recipes"',(d['recipe'],)).fetchone()
  if not recipe:raise ValueError('Recipe not found')
  recipe=json.loads(recipe[0]);weight=float(d['input']);output=float(d['output']);packages=int(d['packages'])
  if weight<=0 or output<=0 or output>weight or packages<=0:raise ValueError('Enter positive input, usable output and package count; output cannot exceed input')
  material=c.execute('select data from records where id=? and kind="materials"',(recipe['material'],)).fetchone()
  if not material:raise ValueError('Material not found')
  m=json.loads(material[0])
  if float(m['quantity'])<weight:raise ValueError('Insufficient material stock')
  costs=[float(d.get(k,0)) for k in ['packaging','labor','energy','overhead','seasoning']]
  if any(x<0 for x in costs):raise ValueError('Costs cannot be negative')
  total=weight*float(m['cost'])+sum(costs);d.update(total=total,unit=total/packages,per_lb=total/output,loss=(weight-output)/weight*100,status='Awaiting inspection',recipe_snapshot=recipe)
  m['quantity']=float(m['quantity'])-weight
  c.execute('update records set data=? where id=?',(json.dumps(m),recipe['material']))
  c.execute('insert into movements values(?,?,?,?,?,datetime("now"))',(str(uuid.uuid4()),recipe['material'],-weight,d['lot'],event))
  c.execute('insert into records values(?,?,?)',(str(uuid.uuid4()),kind,json.dumps(d)))
 elif kind=='quality':
  row=c.execute('select data from records where id=? and kind="batches"',(d['id'],)).fetchone()
  if not row:raise ValueError('Batch not found')
  b=json.loads(row[0]);target=d['status'];allowed={'Awaiting inspection':['Approved','Quarantined','Rejected'],'Approved':['Released for sale','Quarantined'],'Quarantined':['Approved','Rejected'],'Released for sale':['Quarantined']}
  if target not in allowed.get(b['status'],[]):raise ValueError('Invalid quality transition')
  if target=='Released for sale' and b.get('bulk'):raise ValueError('Package bulk stock before releasing it for sale')
  if not d.get('notes','').strip():raise ValueError('Inspection notes required')
  b.update(status=target,inspection=d['notes']);c.execute('update records set data=? where id=?',(json.dumps(b),d['id']))
  if target=='Released for sale':operations.save(c,'outbox',dict(type='inventory.released',event_id=event,batch=d['id'],status='Pending connection'))
 else:raise ValueError('Unknown operation')
 c.execute('insert into events values(?,?,?,datetime("now"))',(event,kind,json.dumps(d)))
 return {'ok':True}
class Handler(BaseHTTPRequestHandler):
 attempts={}
 attempt_lock=threading.Lock()
 def user(self):
  token=self.headers.get('Cookie','').split('bw_session=')[-1].split(';')[0]
  try:
   managed=connected.current(token)
   if managed:return managed
  except ValueError as error:
   self.access_error=str(error);return None
  with connect() as c:
   if finance.setting(c,'company'):return None
   row=c.execute('select u.id,u.name,u.role from sessions s join users u on s.user_id=u.id where s.token=? and s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
  return dict(row) if row else None
 def send(self,status,data,mime='application/json'):
  body=data.encode() if isinstance(data,str) else json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store' if self.path.startswith('/api/') else 'no-cache');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if self.path=='/api/integrations':
   actor=self.user()
   if not actor or actor['role']!='manager':return self.send(403,{'error':'Manager access required'})
   with connect() as c:
    result={'connected':bool(finance.setting(c,'company')),'company':finance.setting(c,'company'),'sourceId':finance.setting(c,'source_id'),'mappings':[{**dict(r),'productName':finance.setting(c,'product_name:'+r['product_id'],r['sku'])} for r in c.execute('SELECT * FROM production_mappings')],'transfers':[{'id':r['id'],'status':r['status'],**json.loads(r['payload'])} for r in c.execute('SELECT * FROM integration_transfers ORDER BY rowid DESC')],'status':sync.STATUS}
   return self.send(200,result)
  if self.path=='/api/users':
   user=self.user()
   if not user or user['role']!='manager':return self.send(403,{'error':'Manager access required'})
   with connect() as c:data=[dict(r) for r in c.execute('select id,name,username,role from users')]
   return self.send(200,data)
  if self.path in ('/app.js','/sw.js','/manifest.json','/icon.svg'):
   mime={'/app.js':'text/javascript','/sw.js':'text/javascript','/manifest.json':'application/manifest+json','/icon.svg':'image/svg+xml'}[self.path]
   return self.send(200,(ROOT/self.path[1:]).read_text(encoding='utf-8'),mime)
  if self.path=='/api/me':
   with connect() as c:setup=c.execute('select count(*) from users').fetchone()[0]==0
   with connect() as c:central=bool(finance.setting(c,'company'))
   return self.send(200,dict(user=self.user(),setup=setup and not central,central=central))
  if self.path.startswith('/api/batch-cost/'):
   user=self.user()
   if not user:return self.send(401,{'error':'Sign in required'})
   if user['role']!='manager':return self.send(403,{'error':'Manager access required'})
   try:
    with connect() as c:
     batch=operations.get(c,self.path.removeprefix('/api/batch-cost/'),'batches')
     result=dict(lines=operations.batch_cost_lines(c,batch),total=batch.get('total'),
                 per_lb=batch.get('per_lb'),per_package=batch.get('unit') if not batch.get('bulk') and batch.get('packages') else None)
   except ValueError as exc:
    return self.send(404,{'error':str(exc)})
   return self.send(200,result)
  if self.path.startswith('/api/schedule/'):
   user=self.user()
   if not user:return self.send(401,{'error':'Sign in required'})
   try:
    with connect() as c:
     c.execute('BEGIN')
     result=operations.schedule_requirements(c,self.path.removeprefix('/api/schedule/'),user['role']=='manager')
   except ValueError as exc:
    return self.send(404,{'error':str(exc)})
   return self.send(200,result)
  if self.path=='/api/state':
   user=self.user()
   if not user:return self.send(401,{'error':'Sign in required'})
   with connect() as c:
    records=[{**json.loads(r['data']), 'id':r['id'], 'kind':r['kind']} for r in c.execute('select * from records')]
    events=[dict(r) for r in c.execute('select id,kind,created from events order by rowid desc limit 100')]
    records.extend({**json.loads(row['data']), 'id':row['id'], 'kind':'stock_adjustments', 'created':row['created']}
                   for row in c.execute("SELECT id,data,created FROM events WHERE kind='adjust' ORDER BY rowid DESC"))
    lots=[dict(r) for r in c.execute('select * from lots')]
   if user['role']!='manager':
    records=[hide_costs(record) for record in records if record['kind'] not in ('prices','invoices','outbox','supplier_credits')]
    lots=hide_costs(lots)
   result={'records':records,'events':events,'lots':lots}
   if user['role']=='manager':
    with connect() as c:result['connections']=finance.connection_status(c,sync.STATUS,records)
   self.send(200,result)
  elif self.path in ('/','/index.html'):self.send(200,(ROOT/'index.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
  else:self.send(404,{'error':'Not found'})
 def do_POST(self):
  try:
   length=int(self.headers.get('Content-Length',0))
   if length<=0 or length>100000:raise ValueError('Invalid request size')
   origin=os.environ.get('BACKWOODS_ORIGIN','http://'+self.headers.get('Host',''))
   if self.headers.get('Origin') and self.headers['Origin']!=origin:raise ValueError('Invalid request origin')
   d=json.loads(self.rfile.read(length))
   if self.path=='/api/login':
    with connect() as c:company=finance.setting(c,'company')
    if company:
     token,actor=connected.login(d.get('username'),d.get('password'),company)
     if actor['role']=='manager':sync.TOKEN=token
     return self.set_login(token,origin)
   if self.path in ('/api/setup','/api/login'):
    with self.attempt_lock:
     key=self.client_address[0];now=time.time();history=[t for t in self.attempts.get(key,[]) if now-t<60]
     if len(history)>=10:return self.send(429,{'error':'Too many sign-in attempts. Wait one minute.'})
     self.attempts[key]=history+[now]
    with connect() as c:
     c.execute('BEGIN IMMEDIATE')
     if self.path=='/api/setup':
      if c.execute('select count(*) from users').fetchone()[0]:raise ValueError('Setup already completed')
      if len(d['password'])<12:raise ValueError('Use at least 12 password characters')
      salt=secrets.token_hex(16);hashed=hashlib.pbkdf2_hmac('sha256',d['password'].encode(),salt.encode(),300000).hex()
      c.execute('insert into users values(?,?,?,?,?,?)',(str(uuid.uuid4()),d['name'],d['username'],salt,hashed,'manager'))
     u=c.execute('select * from users where username=?',(d['username'],)).fetchone()
     if not u or not hmac.compare_digest(u['password'],hashlib.pbkdf2_hmac('sha256',d['password'].encode(),u['salt'].encode(),300000).hex()):raise ValueError('Invalid sign-in')
     token=secrets.token_urlsafe(32);c.execute('insert into sessions values(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],time.time()+28800))
    return self.set_login(token,origin)
   actor=self.user()
   if not actor:return self.send(401,{'error':'Sign in required'})
   if self.path=='/api/logout':
    token=self.headers.get('Cookie','').split('bw_session=')[-1].split(';')[0]
    connected.logout(token)
    if sync.TOKEN==token:sync.TOKEN=None
    with connect() as c:c.execute('delete from sessions where token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    return self.send(200,{'ok':True})
   if self.path.startswith('/api/integrations/'):
    if actor['role']!='manager':return self.send(403,{'error':'Manager access required'})
    token=self.headers.get('Cookie','').split('bw_session=')[-1].split(';')[0]
    if self.path=='/api/integrations/prepare':
     token,person=connected.login(d.get('username'),d.get('password'),None)
     catalog=connected.bridge(token,{'kind':'catalog'},DB.parent)
     catalog['companyId']=person['company']
     return self.set_login(token,origin,catalog)
    if not actor.get('employeeManaged'):raise ValueError('Verify your Employee/Employer account first')
    if self.path=='/api/integrations/connect':
     if d.get('reviewed') is not True:raise ValueError('Review existing stock and Accounting opening balances before connecting')
     with connect() as c:source=finance.setting(c,'source_id')
     receipt=connected.bridge(token,{'kind':'register','sourceId':source,'accountingOwnerUid':d.get('accountingOwnerUid'),'reviewed':True},DB.parent)
     with connect() as c:
      c.execute('BEGIN IMMEDIATE')
      old=finance.setting(c,'company')
      if old and old!=actor['company']:raise ValueError('This Production database is bound to another company')
      finance.baseline(c);finance.set_setting(c,'company',actor['company']);finance.set_setting(c,'accounting_owner',receipt['accountingOwnerUid'])
     sync.TOKEN=token
     return self.send(200,receipt)
    if self.path=='/api/integrations/catalog':return self.send(200,connected.bridge(token,{'kind':'catalog'},DB.parent))
    if self.path=='/api/integrations/map':
     if d.get('reviewed') is not True:raise ValueError('Review the existing physical stock before mapping this SKU')
     catalog=connected.bridge(token,{'kind':'catalog'},DB.parent)
     product=next((p for p in catalog['products'] if p['id']==d.get('productId')),None)
     if not product or product.get('sku')!=d.get('sku') or product.get('unit') not in ('each','bag'):raise ValueError('Choose the exact Vendor SKU stocked by individual package')
     weight=operations.number(d.get('weightLb'),True)
     with connect() as c:
      c.execute('BEGIN IMMEDIATE')
      if not finance.setting(c,'company'):raise ValueError('Connect the company first')
      old=c.execute('SELECT * FROM production_mappings WHERE sku=?',(d['sku'],)).fetchone()
      if old and (old['product_id']!=product['id'] or abs(old['weight']-weight)>1e-8):raise ValueError('Existing SKU mappings cannot be reassigned; use a distinct SKU for a different package')
      c.execute('INSERT OR IGNORE INTO production_mappings VALUES(?,?,?)',(d['sku'],product['id'],weight))
      finance.set_setting(c,'product_name:'+product['id'],product.get('name') or d['sku'])
      finance.queue_releases(c,str(uuid.uuid4()))
     sync.TOKEN=token
     return self.send(200,{'ok':True})
    if self.path=='/api/integrations/sync':
     sync.TOKEN=token;return self.send(200,sync.run(connect))
    raise ValueError('Unknown integration action')
   if self.path=='/api/users':
    if actor.get('employeeManaged'):raise ValueError('Manage Production access in Employee/Employer')
    if actor['role']!='manager':return self.send(403,{'error':'Manager access required'})
    if d['role'] not in ('manager','operator','purchasing') or len(d['password'])<12:raise ValueError('Valid role and password of at least 12 characters required')
    salt=secrets.token_hex(16);hashed=hashlib.pbkdf2_hmac('sha256',d['password'].encode(),salt.encode(),300000).hex()
    with connect() as c:c.execute('insert into users values(?,?,?,?,?,?)',(str(uuid.uuid4()),d['name'],d['username'],salt,hashed,d['role']))
    return self.send(200,{'ok':True})
   manager={'quality','lot_hold','approve_recipe','approve_purchase','approve_invoice','adjust','supplier_credits','supplier_returns','writeoff','save_schedule','package_inventory','correct_lot_cost','edit_purchase','edit_batch'}
   purchasing={'suppliers','materials','purchases','prices','receive','invoices'}
   kind=self.path.removeprefix('/api/')
   operator={'manufacture','start_batch','complete_batch','batch_stage','sanitation','inspections'}
   if actor['role']!='manager' and (kind in manager or (actor['role']=='operator' and kind not in operator) or (actor['role']=='purchasing' and kind not in purchasing)):return self.send(403,{'error':'Your role cannot perform this action'})
   with connect() as c:
    if actor.get('employeeManaged') and not finance.setting(c,'company'):raise ValueError('Finish the company connection before changing Production records')
   event=d.pop('event_id',None);d['actor']=actor['id']
   if not event:raise ValueError('Event ID required')
   with connect() as c:
    c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM events WHERE id=?',(event,)).fetchone():
     before=finance.positions(c)
     if finance.setting(c,'company'):
      if kind in {'reserve','deliver','returns'}:raise ValueError('Use Vendor for reservations, deliveries and finished-goods returns after connecting Production')
      if kind=='quality':
       batch=operations.get(c,d['id'],'batches')
       if batch.get('vendor_transferred'):raise ValueError('This lot belongs to Vendor. Review its recall or stock adjustment there before changing Production quality.')
      result=apply(c,kind,d,event)
      finance.capture(c,event,kind,before);finance.queue_releases(c,event)
     else:result=apply(c,kind,d,event)
    else:result={'duplicate':True}
   self.send(200,result)
  except (ValueError,KeyError,TypeError,sqlite3.Error) as e:self.send(400,{'error':str(e)})
 def set_login(self,token,origin,data=None):
  secure='; Secure' if origin.startswith('https://') else ''
  body=json.dumps(data or {'ok':True}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('Set-Cookie','bw_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+secure);self.end_headers();self.wfile.write(body)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8080);args=parser.parse_args()
 initialize()
 def synchronize():
  while True:
   time.sleep(15);sync.run(connect)
 threading.Thread(target=synchronize,daemon=True).start()
 with ThreadingHTTPServer((args.host,args.port),Handler) as http:
  print('Backwoods Production: http://'+args.host+':'+str(http.server_port),flush=True)
  http.serve_forever()
