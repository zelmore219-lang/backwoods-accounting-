"""One shared Firestore-backed ledger, executed by the installed accounting apps.

Firestore owns the authoritative generation and serializes writers with a bounded
server-timestamp lease. SQLite remains the tested accounting engine on each device.
Immutable compressed generations publish atomically; device login sessions and
provider credentials are not uploaded. No external accounting server is needed.
"""
import base64
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import time
import uuid
import zlib
from .ledger import AccountingError

BEFORE_EXTERNAL_WRITE=ContextVar('before_external_accounting_write',default=None)
MAX_RAW=64*1024*1024
CHUNK=240000

def setting(db,key):
    row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else None

class SharedLedger:
    def __init__(self,app):
        self.app=app;self.firebase=app.firebase;self.meta=None;self.lease=None;self.depth=0;self.last_checked=0
        self.rollback=app.data_dir/'pending-shared-rollback.sqlite3'
        if self.rollback.exists():
            # A process may stop between local calculation and cloud confirmation.
            # Recover the last known durable local state, then reconcile Firestore.
            self.rollback.replace(app.path)
    def save_rollback(self):
        temporary=self.rollback.with_suffix('.tmp')
        source=sqlite3.connect(self.app.path);dest=sqlite3.connect(temporary)
        try:source.backup(dest)
        finally:dest.close();source.close()
        temporary.replace(self.rollback)
    def restore_rollback(self):
        if self.rollback.exists():self.rollback.replace(self.app.path)
        self.last_checked=0
    def connected(self):return bool(self.firebase.connection or self.firebase.vault.read())
    def root(self):
        if not self.firebase.bearer():raise AccountingError('Sign in to the company Firebase account first')
        return self.firebase.root()+'/ledger/state'
    def get(self):return self.firebase.document(self.root())
    @staticmethod
    def value(meta,key,default=None,kind='stringValue'):
        return (meta or {}).get('fields',{}).get(key,{}).get(kind,default)
    def commit(self,writes):
        from .firebase_sync import CONFIG
        return self.firebase.transport('https://firestore.googleapis.com/v1/projects/'+CONFIG['projectId']+'/databases/(default)/documents:commit',{'writes':writes},token=self.firebase.bearer())
    def write_meta(self,fields,prior):
        fields=dict(fields);fields.pop('lockedAt',None)
        write={'update':{'name':self.root(),'fields':fields},'currentDocument':{'updateTime':prior['updateTime']} if prior else {'exists':False}}
        if self.lease:write['updateTransforms']=[{'fieldPath':'lockedAt','setToServerValue':'REQUEST_TIME'}]
        self.commit([write]);self.meta=self.get()
        return self.meta
    def acquire(self):
        prior=self.get()
        holder=self.value(prior,'lockedBy','')
        if holder:
            stamp=self.value(prior,'lockedAt',kind='timestampValue')
            if stamp and (datetime.now(timezone.utc)-datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()<600:
                raise AccountingError('Company books are being updated on another device. Try again shortly.')
        self.lease=str(uuid.uuid4())
        fields=dict((prior or {}).get('fields',{}));fields['lockedBy']={'stringValue':self.lease}
        try:self.write_meta(fields,prior)
        except Exception:self.lease=None;raise
    def release(self):
        if not self.lease:return
        try:
            current=self.get()
            if self.value(current,'lockedBy')==self.lease:
                fields=dict(current['fields']);fields['lockedBy']={'stringValue':''}
                self.write_meta(fields,current)
        except AccountingError:
            # A confirmed generation remains durable if unlock loses its reply.
            # The bounded lease expires; never report a confirmed posting as lost.
            pass
        finally:self.lease=None
    def download(self,meta):
        generation=self.value(meta,'generation');digest=self.value(meta,'sha256')
        count=int(self.value(meta,'chunkCount',0,'integerValue'));size=int(self.value(meta,'bytes',0,'integerValue'))
        if not re.fullmatch('[a-f0-9-]{36}',generation or '') or not re.fullmatch('[a-f0-9]{64}',digest or '') or not 1<=count<=280 or not 1<=size<=MAX_RAW:
            raise AccountingError('Invalid shared company ledger manifest')
        chunks=[];total=0
        for index in range(count):
            chunk=self.firebase.document(self.root()+'/generations/'+generation+'/chunks/'+str(index).zfill(4))
            if not chunk:raise AccountingError('Company ledger changed or is incomplete. Retry the latest generation.')
            raw=base64.b64decode(chunk['fields']['data']['stringValue'],validate=True);total+=len(raw)
            if len(raw)>CHUNK or total>size:raise AccountingError('Invalid shared ledger chunk size')
            chunks.append(raw)
        packed=b''.join(chunks)
        if len(packed)!=size or hashlib.sha256(packed).hexdigest()!=digest:raise AccountingError('Shared ledger integrity check failed; no local records were replaced')
        decoder=zlib.decompressobj();raw=decoder.decompress(packed,MAX_RAW+1)
        if len(raw)>MAX_RAW or not decoder.eof or decoder.unused_data:raise AccountingError('Shared ledger exceeds the supported size or has invalid compression')
        if hashlib.sha256(raw).hexdigest()!=self.value(meta,'sqliteSha256'):raise AccountingError('Shared SQLite checksum failed')
        return raw
    def install(self,raw,meta):
        path=self.app.path;temp=path.with_suffix('.cloud-staging')
        old=sqlite3.connect(path)
        try:
            sessions=list(old.execute('SELECT * FROM sessions'));attempts=list(old.execute('SELECT * FROM login_attempts'))
            users={r[0]:r[1:] for r in old.execute('SELECT id,password_hash,salt,role FROM users')}
        finally:old.close()
        temp.write_bytes(raw)
        incoming=sqlite3.connect(temp)
        try:
            incoming.execute('PRAGMA trusted_schema=OFF')
            if incoming.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():raise AccountingError('Executable schema objects are not accepted in shared accounting data')
            if incoming.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or incoming.execute('PRAGMA foreign_key_check').fetchone():raise AccountingError('Shared ledger database failed validation')
            if setting(incoming,'firebase_ledger_id')!=self.value(meta,'ledgerId'):raise AccountingError('Shared company ledger identity does not match its manifest')
            if incoming.execute('SELECT entry_id FROM lines GROUP BY entry_id HAVING SUM(debit-credit)<>0 LIMIT 1').fetchone():raise AccountingError('Shared ledger contains an unbalanced entry')
            with incoming:
                incoming.execute('DELETE FROM sessions');incoming.execute('DELETE FROM login_attempts')
                for row in sessions:
                    profile=incoming.execute('SELECT password_hash,salt,role FROM users WHERE id=?',(row[1],)).fetchone()
                    if profile and tuple(profile)==tuple(users.get(row[1],())):incoming.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?)',row)
                for row in attempts:incoming.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?,?)',row)
        finally:incoming.close()
        temp.replace(path)
    def refresh(self,allow_empty_local=False):
        if not self.connected():return False
        if not self.lease and time.monotonic()-self.last_checked<30:return False
        self.last_checked=time.monotonic()
        meta=self.get();generation=self.value(meta,'generation')
        if not generation:return False
        db=sqlite3.connect(self.app.path)
        try:
            local_id=setting(db,'firebase_ledger_id');local_generation=setting(db,'firebase_generation')
            has_documents=bool(db.execute('SELECT 1 FROM documents LIMIT 1').fetchone())
        finally:db.close()
        if local_id and local_id!=self.value(meta,'ledgerId'):raise AccountingError('Different company books are already present locally. Use a separate profile or a reviewed migration.')
        if not local_id and has_documents:raise AccountingError('Local and Firebase books both contain records. Back up both and review the migration before replacing either ledger.')
        if generation==local_generation:return False
        raw=self.download(meta)
        latest=self.get()
        if self.value(latest,'generation')!=generation:raise AccountingError('Company ledger changed while reading. Please retry.')
        self.install(raw,meta);self.meta=latest
        return True
    def snapshot(self,generation,ledger_id):
        db=sqlite3.connect(self.app.path)
        try:
            with db:
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('firebase_ledger_id',ledger_id))
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('firebase_generation',generation))
            with tempfile.TemporaryDirectory() as folder:
                dest=Path(folder)/'ledger.sqlite3';copy=sqlite3.connect(dest)
                try:
                    db.backup(copy)
                    with copy:copy.execute('DELETE FROM sessions');copy.execute('DELETE FROM login_attempts')
                    copy.execute('VACUUM')
                finally:copy.close()
                raw=dest.read_bytes()
        finally:db.close()
        if len(raw)>MAX_RAW:raise AccountingError('Company ledger exceeds this build\'s 64 MB supported database size. No incomplete upload was published.')
        return raw
    def flush(self):
        if not self.lease:raise AccountingError('A shared ledger write lease is required')
        current=self.get()
        if self.value(current,'lockedBy')!=self.lease:raise AccountingError('The shared ledger write lease changed. No success was confirmed.')
        generation=str(uuid.uuid4());ledger_id=self.value(current,'ledgerId') or str(uuid.uuid4())
        raw=self.snapshot(generation,ledger_id);packed=zlib.compress(raw,6)
        if len(packed)>MAX_RAW:raise AccountingError('Compressed ledger exceeds supported storage size')
        root=self.root();count=(len(packed)+CHUNK-1)//CHUNK
        for offset in range(0,count,3):
            writes=[]
            for index in range(offset,min(offset+3,count)):
                data=base64.b64encode(packed[index*CHUNK:(index+1)*CHUNK]).decode()
                writes.append({'update':{'name':root+'/generations/'+generation+'/chunks/'+str(index).zfill(4),'fields':{'data':{'stringValue':data}}},'currentDocument':{'exists':False}})
            self.commit(writes)
        fields={'ledgerId':{'stringValue':ledger_id},'generation':{'stringValue':generation},'sha256':{'stringValue':hashlib.sha256(packed).hexdigest()},'sqliteSha256':{'stringValue':hashlib.sha256(raw).hexdigest()},'chunkCount':{'integerValue':str(count)},'bytes':{'integerValue':str(len(packed))},'rawBytes':{'integerValue':str(len(raw))},'codec':{'stringValue':'zlib-sqlite-v1'},'lockedBy':{'stringValue':self.lease},'previousGeneration':{'stringValue':self.value(current,'generation','')},'previousChunkCount':{'integerValue':str(self.value(current,'chunkCount',0,'integerValue'))}}
        self.write_meta(fields,current)
        self.save_rollback()
        # Best-effort cleanup retains current + preceding generation. Readers of
        # a retired generation detect the pointer change and retry atomically.
        retired=self.value(current,'previousGeneration','');retired_count=int(self.value(current,'previousChunkCount',0,'integerValue'))
        if retired and re.fullmatch('[a-f0-9-]{36}',retired) and 0<retired_count<=280:
            try:
                for offset in range(0,retired_count,3):self.commit([{'delete':root+'/generations/'+retired+'/chunks/'+str(i).zfill(4)} for i in range(offset,min(offset+3,retired_count))])
            except AccountingError:pass
    @contextmanager
    def mutation(self):
        with self.app.write_lock:
            if not self.connected() or self.depth:
                self.depth+=1
                try:yield
                finally:self.depth-=1
                return
            self.acquire();self.depth=1;token=BEFORE_EXTERNAL_WRITE.set(self.flush)
            probe=None;cleanup=False
            try:
                self.refresh()
                self.save_rollback()
                probe=sqlite3.connect(self.app.path);version=probe.execute('PRAGMA data_version').fetchone()[0]
                yield
                changed=probe.execute('PRAGMA data_version').fetchone()[0]!=version
                probe.close();probe=None
                if changed or not self.value(self.meta,'generation'):self.flush()
                cleanup=True
            except Exception:
                if probe:probe.close();probe=None
                # The last durable generation includes any pre-submission marker.
                # Restore it rather than exposing an unconfirmed local posting.
                try:
                    latest=self.get()
                    if self.value(latest,'generation'):self.install(self.download(latest),latest)
                    else:self.restore_rollback()
                    cleanup=True
                except Exception:
                    self.restore_rollback();cleanup=True
                raise
            finally:
                if probe:probe.close()
                BEFORE_EXTERNAL_WRITE.reset(token);self.depth=0;self.release()
                if cleanup:self.rollback.unlink(missing_ok=True)
