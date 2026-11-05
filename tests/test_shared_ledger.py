import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from accounting.server import Application
from accounting.firebase_sync import Firebase
from accounting.firebase_ledger import SharedLedger,BEFORE_EXTERNAL_WRITE
from accounting.ledger import AccountingError
from accounting import auth
from test_accounting import main_backup,vendor

class Vault:
    def read(self):return {'uid':'one-company','refreshToken':'not-a-real-token'}

class Firestore:
    """Atomic REST/precondition fixture, not a live rules emulator."""
    def __init__(self):self.documents={};self.version=0;self.reject_pointer=False;self.fail_reads=False;self.commits=[]
    def __call__(self,url,value=None,token=None,form=False):
        if value is None:
            if self.fail_reads:raise AccountingError('Fixture is offline')
            return copy.deepcopy(self.documents.get(url))
        if not url.endswith(':commit'):raise AssertionError(url)
        current=copy.deepcopy(self.documents)
        for write in value['writes']:
            name=write.get('update',{}).get('name') or write.get('delete')
            key='https://firestore.googleapis.com/v1/'+name
            old=current.get(key);condition=write.get('currentDocument',{})
            if condition.get('exists') is False and old:raise AccountingError('Concurrent creation rejected')
            if condition.get('updateTime') and (not old or old['updateTime']!=condition['updateTime']):raise AccountingError('Concurrent update rejected')
            if 'delete' in write:current.pop(key,None);continue
            fields=copy.deepcopy(write['update']['fields'])
            if self.reject_pointer and fields.get('generation'):raise AccountingError('Fixture connection lost before pointer publication')
            for transform in write.get('updateTransforms',[]):fields[transform['fieldPath']]={'timestampValue':datetime.now(timezone.utc).isoformat()}
            self.version+=1;current[key]={'name':name,'fields':fields,'updateTime':str(self.version)}
        self.documents=current;self.commits.append(value)
        return {}

class SharedLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Firestore();self.a=self.device('a');self.b=self.device('b')
        ledger=self.a.ledger()
        try:
            self.owner=auth.create_user(ledger,{'username':'owner','password':'a strong approval passphrase'},first=True)
            with ledger.db:ledger.db.execute('INSERT INTO firebase_link VALUES(?,?,?)',('one-company',self.owner['id'],'owner@example.test'))
        finally:ledger.close()
        with self.a.shared.mutation():pass
    def device(self,name):
        app=Application(Path(self.temp.name)/name)
        app.firebase=Firebase(app.data_dir,transport=self.store,vault=Vault());app.firebase.connection=Vault().read();app.firebase.token='verified-fixture';app.firebase.expires=time.time()+3600
        app.shared=SharedLedger(app);return app
    def tearDown(self):self.temp.cleanup()
    def rows(self,app):
        ledger=app.ledger()
        try:return ledger.rows()
        finally:ledger.close()
    def test_two_devices_share_retail_and_wholesale_one_ledger(self):
        self.a.process({'source':'main','payload':main_backup()})
        self.b.shared.refresh();self.b.process({'source':'vendor','payload':vendor()})
        self.a.shared.last_checked=0;self.a.shared.refresh()
        self.assertEqual(self.rows(self.a),self.rows(self.b))
        self.assertEqual({r['source'] for r in self.rows(self.a)},{'main','vendor'})
    def test_active_writer_blocks_another_device(self):
        self.a.shared.acquire()
        try:
            with self.assertRaisesRegex(AccountingError,'another device'):
                with self.b.shared.mutation():pass
        finally:self.a.shared.release()
    def test_corrupt_generation_does_not_replace_local_records(self):
        self.a.process({'source':'main','payload':main_backup()});self.b.shared.refresh();before=self.rows(self.b)
        self.a.process({'source':'vendor','payload':vendor()})
        root=self.a.shared.root();meta=self.a.shared.get();gen=meta['fields']['generation']['stringValue']
        self.store.documents['https://firestore.googleapis.com/v1/'+root+'/generations/'+gen+'/chunks/0000']['fields']['data']['stringValue']='YWJj'
        self.b.shared.last_checked=0
        with self.assertRaises(AccountingError):self.b.shared.refresh()
        self.assertEqual(self.rows(self.b),before)
    def test_failed_pointer_keeps_last_confirmed_financial_state(self):
        before=self.rows(self.a);self.store.reject_pointer=True
        with self.assertRaises(AccountingError):self.a.process({'source':'main','payload':main_backup()})
        self.assertEqual(self.rows(self.a),before)
    def test_login_sessions_stay_on_their_device(self):
        ledger=self.a.ledger()
        try:token,_=auth.login(ledger,{'username':'owner','password':'a strong approval passphrase'})
        finally:ledger.close()
        self.a.process({'source':'main','payload':main_backup()});self.b.shared.refresh()
        ledger=self.b.ledger()
        try:self.assertEqual(ledger.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
        finally:ledger.close()
        self.b.process({'source':'vendor','payload':vendor()});self.a.shared.last_checked=0;self.a.shared.refresh()
        ledger=self.a.ledger()
        try:self.assertEqual(auth.session_user(ledger,token)['id'],self.owner['id'])
        finally:ledger.close()
    def test_external_submission_marker_is_durable_before_call(self):
        with self.assertRaisesRegex(AccountingError,'unknown outcome'):
            with self.a.shared.mutation():
                ledger=self.a.ledger()
                try:
                    with ledger.db:ledger.db.execute("INSERT INTO provider_actions VALUES('payroll-id','submitting','owner approved','2026-11-04T12:00:00Z')")
                finally:ledger.close()
                BEFORE_EXTERNAL_WRITE.get()()
                raise AccountingError('Provider has an unknown outcome')
        self.b.shared.refresh();ledger=self.b.ledger()
        try:self.assertEqual(ledger.db.execute("SELECT status FROM provider_actions WHERE payroll_id='payroll-id'").fetchone()[0],'submitting')
        finally:ledger.close()
    def test_noop_import_does_not_publish_another_generation(self):
        value={'source':'main','payload':main_backup()};self.a.process(value)
        generation=self.a.shared.value(self.a.shared.get(),'generation');self.a.process(value)
        self.assertEqual(self.a.shared.value(self.a.shared.get(),'generation'),generation)

    def test_password_change_revokes_other_device_cached_session(self):
        self.b.shared.refresh();ledger=self.b.ledger()
        try:token,_=auth.login(ledger,{'username':'owner','password':'a strong approval passphrase'})
        finally:ledger.close()
        with self.a.shared.mutation():
            ledger=self.a.ledger()
            try:auth.change_password(ledger,self.owner,{'currentPassword':'a strong approval passphrase','newPassword':'a new strong approval passphrase'})
            finally:ledger.close()
        self.b.shared.last_checked=0;self.b.shared.refresh();ledger=self.b.ledger()
        try:self.assertIsNone(auth.session_user(ledger,token))
        finally:ledger.close()
    def test_compact_automatic_batches_retain_source_record_history(self):
        payload={**main_backup(),'type':'business-accounting-feed','schemaVersion':1}
        self.a.process({'source':'main','payload':payload})
        ledger=self.a.ledger()
        try:
            meta=json.loads(ledger.db.execute('SELECT payload FROM batches LIMIT 1').fetchone()[0])
            self.assertEqual(meta['storage'],'financial-record-history-v1')
            self.assertGreater(ledger.db.execute('SELECT COUNT(*) FROM document_history').fetchone()[0],0)
            record=json.loads(ledger.db.execute('SELECT payload FROM document_history LIMIT 1').fetchone()[0])
            self.assertTrue(record['original']);self.assertNotIn('orders',meta.get('data',{}))
        finally:ledger.close()

    def test_offline_rollback_does_not_leave_an_unconfirmed_local_expense(self):
        before=self.rows(self.a)
        try:
            with self.assertRaises(AccountingError):
                with self.a.shared.mutation():
                    self.a._process({'source':'main','payload':main_backup()})
                    self.store.fail_reads=True
                    raise AccountingError('Connection dropped before confirmation')
        finally:self.store.fail_reads=False
        self.assertEqual(self.rows(self.a),before)
    def test_interrupted_process_recovers_known_durable_state(self):
        before=self.rows(self.a);self.a.shared.save_rollback()
        self.a._process({'source':'main','payload':main_backup()})
        restarted=Application(self.a.data_dir)
        self.assertEqual(self.rows(restarted),before)

class SharedHttpTests(unittest.TestCase):
    def setUp(self):
        from test_accounting import HttpTests
        self.http=HttpTests('test_manual_invoice_payment_and_expense');self.http.setUp();self.app=self.http.app;self.store=Firestore()
        self.app.firebase=Firebase(self.app.data_dir,transport=self.store,vault=Vault());self.app.firebase.connection=Vault().read();self.app.firebase.token='fixture';self.app.firebase.expires=time.time()+3600
        self.app.shared=SharedLedger(self.app)
        with self.app.shared.mutation():pass
    def tearDown(self):self.http.tearDown()
    def test_retried_pending_expense_posts_only_once(self):
        body={'kind':'expense','date':'2026-11-02','party':'Power','reference':'SPARK-1','amount':25,'account':'5100'}
        headers={'X-Accounting-Operation':'00000000-0000-0000-0000-000000000001'}
        first=self.http.post('/api/manual-document',body,headers);second=self.http.post('/api/manual-document',body,headers)
        self.assertEqual(first,second)
        ledger=self.app.ledger()
        try:self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM documents WHERE reference='SPARK-1'").fetchone()[0],1)
        finally:ledger.close()
    def test_post_is_not_acknowledged_before_cloud_commit(self):
        import urllib.error
        self.store.reject_pointer=True
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.http.post('/api/manual-document',{'kind':'expense','date':'2026-11-02','party':'Power','reference':'SPARK-FAILED','amount':25,'account':'5100'})
        self.assertEqual(err.exception.code,409)
        ledger=self.app.ledger()
        try:self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM documents WHERE reference='SPARK-FAILED'").fetchone()[0],0)
        finally:ledger.close()
