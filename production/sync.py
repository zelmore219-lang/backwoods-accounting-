"""Retryable transfer worker; acknowledgment never means a sale or a bank payment."""
import json, threading
import connected, finance
LOCK=threading.Lock()
TOKEN=None
STATUS={'message':'Connect Employee/Employer to enable synchronization.'}

def run(connect):
 global STATUS
 if not TOKEN or not LOCK.acquire(blocking=False):return STATUS
 try:
  with connect() as c:
   if not finance.setting(c,'company'):return STATUS
   source=finance.setting(c,'source_id');owner=finance.setting(c,'accounting_owner')
   transfers=[(r['id'],json.loads(r['payload'])) for r in c.execute("SELECT * FROM integration_transfers WHERE status='pending' ORDER BY rowid")]
   directory=__import__('pathlib').Path(c.execute('PRAGMA database_list').fetchone()[2]).parent
  for tid,payload in transfers:
   receipt=connected.bridge(TOKEN,{'kind':'transfer','sourceId':source,'transfer':payload},directory)
   with connect() as c:c.execute("UPDATE integration_transfers SET status='received',receipt=? WHERE id=?",(json.dumps(receipt),tid))
  with connect() as c:
   packet=finance.packet(c);sequence=c.execute('SELECT count(*) FROM events').fetchone()[0]+c.execute('SELECT count(*) FROM production_journals').fetchone()[0]
   packet['data']['sequence']=sequence
   fingerprint=__import__('hashlib').sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest()
   if finance.setting(c,'published_hash')==fingerprint:
    STATUS={'message':'Vendor transfers received; Accounting source is current.','ok':True};return STATUS
  result=connected.bridge(TOKEN,{'kind':'publish','sourceId':source,'accountingOwnerUid':owner,'packet':packet},directory)
  with connect() as c:finance.set_setting(c,'published_hash',fingerprint)
  STATUS={'message':'Vendor transfers received. Accounting data sent; check Business Accounting for import status.','ok':True,'receipt':result}
 except Exception as error:STATUS={'message':str(error),'ok':False}
 finally:LOCK.release()
 return STATUS
