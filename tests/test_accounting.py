import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

from accounting.ledger import AccountingError, Ledger, cents
from accounting.imports import main_import, vendor_import, line, pair, record
from accounting.costing import calculate,price_channels
from accounting.server import Application, Handler, ThreadingHTTPServer


def vendor():
    payment={"id":"p1","orderId":"o1","amount":50,"method":"Cash","createdAt":"2026-10-02T10:00:00Z"}
    return {"exportedAt":"2026-10-03T00:00:00Z","data":{
        "orders":[{"id":"o1","invoiceNumber":"V-001","createdAt":"2026-10-01T10:00:00Z","deliveredAt":"2026-10-02T09:00:00Z","customerId":"c1","status":"payment_pending","items":[{"qty":10,"deliveredQty":10,"price":10,"returnQty":1,"returnPrice":10,"returnCreditPercent":100}],"tax":9,"credits":[],"payments":[payment]}],
        "products":[{"id":"prod1","cost":7}],"customers":[{"id":"c1","name":"Pine Hill"}],
        "payments":[payment],"inventoryMovements":[{"id":"m1","type":"delivery","quantity":-9,"unitCost":3,"createdAt":"2026-10-02T09:00:00Z"}],
        "purchaseReceipts":[],"credits":[]}}


def main_backup():
    return {"exportedAt":"2026-10-03T00:00:00Z","data":{"orders":[{"id":"s1","date":"2026-10-01","subtotal":100,"tax":10,"total":110,"paymentType":"Cash","depletionLog":[{"cost":20}]}],"journalEntries":[],"bills":[],"invoices":[],"expenses":[]}}


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'books.db';self.ledger=Ledger(self.path)
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def load(self,payload,source='main',preview=False):
        docs,accounts,_=(main_import if source=='main' else vendor_import)(payload)
        return self.ledger.import_documents(source,docs,payload,snapshot_at=payload.get('exportedAt'),accounts=accounts,preview=preview)
    def test_merges_two_apps_into_one_company(self):
        self.load(main_backup());self.load(vendor(),'vendor')
        r=self.ledger.report()
        self.assertEqual(r['income'],19000);self.assertEqual(r['expense'],4700)
        self.assertEqual(r['profit'],14300);self.assertEqual(r['balanceDifference'],0)
        self.assertEqual(r['debits'],r['credits'])
        self.assertEqual(next(a for a in r['trial'] if a['code']=='1100')['balance'],4900)
        self.assertEqual(next(a for a in r['trial'] if a['code']=='1030')['balance'],5000)
    def test_repeat_import_is_idempotent_after_restart(self):
        self.load(vendor(),'vendor');n=len(self.ledger.rows());self.ledger.close();self.ledger=Ledger(self.path)
        result=self.load(vendor(),'vendor');self.assertEqual(result['added'],0);self.assertEqual(result['changed'],0);self.assertEqual(len(self.ledger.rows()),n)
    def test_payment_copies_post_once(self):
        self.load(vendor(),'vendor')
        entries={r['entry_id'] for r in self.ledger.rows() if r['source_id']=='payment:p1'}
        self.assertEqual(len(entries),1)
    def test_conflicting_payment_copies_rejected(self):
        p=vendor();p['data']['payments'][0]=copy.deepcopy(p['data']['payments'][0]);p['data']['payments'][0]['amount']=60
        with self.assertRaisesRegex(AccountingError,'Conflicting'):self.load(p,'vendor')
        self.assertEqual(self.ledger.rows(),[])
    def test_revision_reverses_prior_posting(self):
        p=main_backup();self.load(p);p=copy.deepcopy(p);p['data']['orders'][0].update(subtotal=200,tax=20,total=220);p['exportedAt']='2026-10-04T00:00:00Z';self.load(p)
        r=self.ledger.report();self.assertEqual(r['income'],20000);self.assertEqual(r['profit'],18000)
        self.assertTrue(any(l['reversal_of'] for l in self.ledger.rows()))
        self.assertEqual(r['balanceDifference'],0)
    def test_metadata_revision_does_not_repost_and_later_revision_reverses_active_entry(self):
        p=main_backup();self.load(p);n=len(self.ledger.rows());p=copy.deepcopy(p);p['data']['orders'][0]['receiptDone']=True;self.load(p)
        self.assertEqual(len(self.ledger.rows()),n)
        p['data']['orders'][0].update(subtotal=200,tax=20,total=220);self.load(p)
        self.assertEqual(self.ledger.report()['income'],20000)
    def test_preview_never_writes(self):
        result=self.load(main_backup(),preview=True)
        self.assertEqual(result['added'],1);self.assertEqual(self.ledger.rows(),[])
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)
    def test_bad_batch_rolls_back_entire_import(self):
        docs,_,_=main_import(main_backup());bad=copy.deepcopy(docs[0]);bad['id']='bad';bad['lines'][0]['debit']+=1
        with self.assertRaisesRegex(AccountingError,'Unbalanced'):self.ledger.import_documents('main',docs+[bad],{})
        self.assertEqual(self.ledger.rows(),[])
    def test_closed_period_prevents_source_correction(self):
        p=main_backup();self.load(p);self.ledger.set_settings({'closed_through':'2026-10-31'})
        self.assertEqual(self.load(p)['duplicates'],1)
        p=copy.deepcopy(p);p['data']['orders'][0].update(subtotal=200,tax=20,total=220)
        with self.assertRaisesRegex(AccountingError,'closed'):self.load(p)
    def test_stale_snapshot_rejected(self):
        p=main_backup();self.load(p);p['exportedAt']='2026-10-02T00:00:00Z'
        with self.assertRaisesRegex(AccountingError,'older'):self.load(p)
    def test_missing_historical_cost_becomes_explicit_review(self):
        p=vendor();del p['data']['inventoryMovements'][0]['unitCost'];docs,_,warnings=vendor_import(p)
        review=next(d for d in docs if d['kind']=='needs-cost')
        self.assertEqual(review['id'],'inventory:m1');self.assertEqual(review['lines'],[])
        self.assertTrue(any('historical unit cost' in w for w in warnings))
    def test_void_reverses_sale_including_cost(self):
        p=main_backup();p['data']['orders'][0]['voided']=True
        self.load(p);r=self.ledger.report();self.assertEqual(r['income'],0);self.assertEqual(r['expense'],0);self.assertEqual(r['assets'],0)
    def test_unknown_payroll_backup_is_rejected_not_dropped(self):
        p=main_backup();p['data']['payrollRuns']=[{'id':'pay1'}]
        with self.assertRaisesRegex(AccountingError,'connector'):self.load(p)
    def test_main_exact_ledger_preserves_payroll_accounts(self):
        p={'data':{'generalLedger':[{'source':'Payroll p1','date':'2026-10-01','account':'5200 Wages','debit':100,'credit':0},{'source':'Payroll p1','date':'2026-10-01','account':'1020 Bank Account','debit':0,'credit':100}]}}
        self.load(p);self.assertEqual(self.ledger.report()['expense'],10000)
    def test_vendor_mirrors_are_not_counted_in_main(self):
        p=main_backup();p['data']['invoices']=[{'id':'mirror','sourceSystem':'vendor-ordering','date':'2026-10-01','amount':100}]
        self.load(p);self.assertEqual(self.ledger.report()['income'],10000)
    def test_receipt_and_purchase_movement_not_double_counted(self):
        p=vendor();p['data']['purchaseReceipts']=[{'id':'r1','landedCostTotal':40,'createdAt':'2026-10-01'}]
        p['data']['inventoryMovements'].append({'id':'pm1','type':'purchase_receipt','referenceId':'r1','quantity':4,'unitCost':10,'createdAt':'2026-10-01'})
        self.load(p,'vendor');r=self.ledger.report()
        self.assertEqual(next(a for a in r['trial'] if a['code']=='2000')['balance'],-4000)
        self.assertEqual(next(a for a in r['trial'] if a['code']=='1200')['balance'],1300)
    def test_drafts_do_not_become_revenue(self):
        p=vendor();p['data']['orders'][0].update(status='submitted',payments=[]);p['data']['payments']=[];p['data']['inventoryMovements']=[]
        self.load(p,'vendor');self.assertEqual(self.ledger.report()['income'],0)
    def test_overpayments_require_review(self):
        p=vendor();p['data']['payments'][0]['amount']=1000
        with self.assertRaises(AccountingError):self.load(p,'vendor')
    def test_reconciliation_blocks_wrong_balance_and_reuse(self):
        d=record('journal',{'id':'opening','date':'2026-10-01'},pair('1020','3100',10000))
        self.ledger.import_documents('manual',[d],{})
        lid=next(r['id'] for r in self.ledger.rows() if r['account']=='1020')
        v={'account':'1020','date':'2026-10-31','starting':0,'ending':99,'lineIds':[lid]}
        with self.assertRaisesRegex(AccountingError,'difference'):self.ledger.reconcile(v)
        v['ending']=100;self.ledger.reconcile(v)
        with self.assertRaises(AccountingError):self.ledger.reconcile(v)
        d['lines']=pair('1020','3100',20000)
        with self.assertRaisesRegex(AccountingError,'reconciled'):self.ledger.import_documents('manual',[d],{})
    def test_custom_account_requires_valid_type(self):
        d=record('journal',{'id':'j','date':'2026-10-01'},pair('6800','1020',200))
        self.ledger.import_documents('manual',[d],{},accounts=[('6800','Office rent','expense')])
        self.assertEqual(self.ledger.report()['expense'],200)
    def test_money_uses_decimal_and_rejects_nonfinite(self):
        self.assertEqual(cents('1.005'),101)
        for value in ['NaN','Infinity',True,None]:
            with self.assertRaises(AccountingError):cents(value)
    def test_attach_requires_existing_record(self):
        with self.assertRaises(AccountingError):self.ledger.attach({'source':'main','sourceId':'missing','name':'receipt','content':'YQ=='})
    def test_attachment_survives_source_metadata_revision(self):
        p=main_backup();self.load(p)
        aid=self.ledger.attach({'source':'main','sourceId':'sale:s1','name':'receipt.txt','content':'YQ=='})['id']
        p['data']['orders'][0]['memo']='Receipt reviewed';self.load(p)
        self.assertEqual(self.ledger.db.execute('SELECT content FROM attachments WHERE id=?',(aid,)).fetchone()[0],b'a')


class CostingTests(unittest.TestCase):
    def fixture(self):return {'name':'Root beer','yieldUnits':100,'wastePercent':10,'materials':[{'name':'Syrup','quantity':2,'unitCost':10},{'name':'Bottles','kind':'packaging','quantity':100,'unitCost':.5}],'laborHours':2,'laborRate':20,'laborBurdenPercent':10,'overhead':10,'otherCost':1,'sellingPrice':3,'targetMargin':40}
    def test_complete_batch_cost_yield_margin(self):
        r=calculate(self.fixture());self.assertEqual(r['total'],12500);self.assertEqual(r['sellableUnits'],90)
        self.assertEqual(r['unitCost'],139);self.assertEqual(r['suggestedPrice'],232);self.assertEqual(r['estimatedBatchProfit'],14500)
        self.assertAlmostEqual(r['grossMargin'],53.7037037)
    def test_invalid_yield_margin_and_cost_rejected(self):
        for key,value in [('yieldUnits',0),('wastePercent',100),('targetMargin',100),('laborHours',-1),('sellingPrice','NaN')]:
            f=self.fixture();f[key]=value
            with self.assertRaises(AccountingError):calculate(f)
    def test_channel_case_pack_delivery_and_fee_margins(self):
        r=price_channels({'name':'Bottles','unitCost':1,'caseQty':12,'retailPrice':3,'wholesalePrice':2,'distributorPrice':1.5,'deliveryPerCase':6,'retailFeePercent':3,'targetMargin':35})
        self.assertEqual(r['caseCost'],1200)
        retail,wholesale,distributor=r['channels']
        self.assertEqual(retail['profit'],191);self.assertEqual(wholesale['profit'],50)
        self.assertEqual(wholesale['caseRevenue'],2400);self.assertEqual(distributor['profit'],0)
        self.assertAlmostEqual(r['retailerMargin'],100/3)


class HttpTests(unittest.TestCase):
    def setUp(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.app=Application(cls.temp.name)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.application=cls.app
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        cls.client.open(cls.base).read()
        cls.post('/api/auth/setup',{'name':'Test Owner','username':'owner','password':'test-owner-passphrase-2026'})
    def tearDown(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def post(self,path,value,headers=None):
        req=urllib.request.Request(self.base+path,json.dumps(value).encode(),{'Content-Type':'application/json','X-Accounting-Request':'1',**(headers or {})})
        return json.loads(self.client.open(req).read())
    def test_full_import_preview_reports_export_backup(self):
        preview=self.post('/api/import/preview',{'source':'main','payload':main_backup()});self.assertEqual(preview['added'],1)
        result=self.post('/api/import',{'source':'main','payload':main_backup()});self.assertEqual(result['added'],1)
        state=json.loads(self.client.open(self.base+'/api/state').read());self.assertEqual(state['report']['income'],10000)
        self.assertIn(b'1010',self.client.open(self.base+'/api/export.csv').read())
        backup=self.client.open(self.base+'/api/backup').read();self.assertTrue(backup.startswith(b'SQLite format 3'))
    def test_manual_invoice_payment_and_expense(self):
        result=self.post('/api/manual-document',{'kind':'invoice','date':'2026-11-01','party':'New customer','reference':'MAN-1','amount':'100','tax':'10','account':'4000'})
        state=json.loads(self.client.open(self.base+'/api/state').read());d=next(d for d in state['documents'] if d['reference']=='MAN-1')
        self.post('/api/pay',{'id':d['source_id'],'date':'2026-11-02','amount':'50','account':'1020'})
        state=json.loads(self.client.open(self.base+'/api/state').read());d=next(d for d in state['documents'] if d['reference']=='MAN-1');self.assertEqual(d['balance'],6000)
        self.post('/api/manual-document',{'kind':'expense','date':'2026-11-02','party':'Power company','reference':'UTIL-1','amount':25,'account':'5100'})
    def test_costing_save_does_not_post_ledger(self):
        before=json.loads(self.client.open(self.base+'/api/ledger').read())
        r=self.post('/api/costing/save',CostingTests().fixture());self.assertEqual(r['total'],12500)
        after=json.loads(self.client.open(self.base+'/api/ledger').read());self.assertEqual(before,after)
        state=json.loads(self.client.open(self.base+'/api/state').read());self.assertTrue(state['recipes'])
    def test_cross_origin_and_missing_session_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.post('/api/settings',{'company':'Intruder'},{'Origin':'https://example.com'})
        self.assertEqual(err.exception.code,403)
    def test_native_bootstrap_is_not_disclosed_to_another_loopback_client(self):
        self.app.native_private_bootstrap=True
        response=urllib.request.urlopen(self.base+'/')
        self.assertIsNone(response.headers.get('Set-Cookie'));response.read()
        req=urllib.request.Request(self.base+'/api/auth/login',json.dumps({'username':'owner','password':'test-owner-passphrase-2026'}).encode(),{'Content-Type':'application/json','X-Accounting-Request':'1'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(self.base+'/api/state')
        self.assertEqual(err.exception.code,403)
    def test_optional_https_proxy_origin_and_secure_cookies(self):
        # Simulate a local TLS terminator's Host forwarding, not real TLS.
        self.app.public_host='books.example.test'
        self.app.public_origin='https://books.example.test'
        headers={'Host':'books.example.test','Origin':'https://books.example.test'}
        request=urllib.request.Request(self.base+'/',headers=headers)
        response=self.client.open(request)
        self.assertIn('; Secure',response.headers.get('Set-Cookie'))
        response.read()
        # Existing local login token is forwarded manually, as a TLS proxy would.
        cookie='; '.join(c.name+'='+c.value for handler in self.client.handlers
                        if isinstance(handler,urllib.request.HTTPCookieProcessor) for c in handler.cookiejar)
        request=urllib.request.Request(self.base+'/api/state',headers={**headers,'Cookie':cookie})
        self.assertEqual(urllib.request.urlopen(request).status,200)
        for host,origin in [('untrusted.example.test','https://untrusted.example.test'),
                            ('books.example.test','https://evil.example.test'),
                            ('books.example.test',self.base)]:
            with self.assertRaises(urllib.error.HTTPError) as err:
                self.post('/api/settings',{'company':'Intruder'},{'Host':host,'Origin':origin})
            self.assertEqual(err.exception.code,403)
        login=urllib.request.Request(self.base+'/api/auth/login',json.dumps({'username':'owner','password':'test-owner-passphrase-2026'}).encode(),
                                     {**headers,'Cookie':cookie,'Content-Type':'application/json','X-Accounting-Request':'1'})
        response=urllib.request.urlopen(login)
        self.assertIn('; Secure',response.headers.get('Set-Cookie'));response.read()

    def test_public_origin_requires_https_origin_only(self):
        for origin in ['http://books.example.test','https://owner:secret@books.example.test',
                       'https://books.example.test/path','https://books.example.test?secret=value',
                       'https://books.example.test#fragment']:
            with self.assertRaises(AccountingError):Application(self.temp.name,public_origin=origin)
    def test_feed_worker_imports_without_browser(self):
        p=vendor();(self.app.feed_dir/'vendor.json').write_text(json.dumps(p))
        thread=threading.Thread(target=self.app.watch_feeds,daemon=True);thread.start()
        import time
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            status=self.app.feed_dir/'vendor-status.json'
            if status.exists():break
            time.sleep(.03)
        self.app.stop.set();thread.join(timeout=5)
        self.assertTrue(json.loads(status.read_text())['ok'])
        ledger=self.app.ledger()
        try:self.assertTrue(any(r['source']=='vendor' for r in ledger.rows()))
        finally:ledger.close()
    def test_firebase_login_requires_verified_explicitly_bound_identity(self):
        from unittest.mock import patch
        with patch.object(self.app.firebase,'verify_identity',return_value='verified-company-uid'):
            with self.assertRaises(urllib.error.HTTPError) as err:self.post('/api/auth/firebase-login',{'idToken':'test-token'})
            self.assertEqual(err.exception.code,400)
            ledger=self.app.ledger()
            try:
                owner=ledger.db.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
                with ledger.db:ledger.db.execute('INSERT INTO firebase_link VALUES(?,?,?)',('verified-company-uid',owner,'owner@example.test'))
            finally:ledger.close()
            result=self.post('/api/auth/firebase-login',{'idToken':'test-token'})
            self.assertEqual(result['user']['role'],'owner')
            self.assertEqual(json.loads(self.client.open(self.base+'/api/state').read())['user']['id'],owner)
    def test_firebase_worker_imports_both_sources_into_one_ledger(self):
        import time
        ledger=self.app.ledger()
        try:
            owner=ledger.db.execute("SELECT id FROM users WHERE username='owner'").fetchone()[0]
            with ledger.db:ledger.db.execute('INSERT INTO firebase_link VALUES(?,?,?)',('uid-owner',owner,'owner@example.test'))
        finally:ledger.close()
        retail={**main_backup(),'type':'business-accounting-feed','schemaVersion':1}
        wholesale={**vendor(),'type':'business-accounting-feed','schemaVersion':1}
        class Connected:
            connection={'uid':'uid-owner'}
            def bearer(self):return 'test-token'
            def publish_service(self,origin):pass
            def snapshot(self,source,previous):return None if previous else (source,retail if source=='main' else wholesale)
        self.app.firebase=Connected()
        thread=threading.Thread(target=self.app.watch_firebase,daemon=True);thread.start()
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            if len(self.app.firebase_status.get('sources',{}))==2:break
            time.sleep(.03)
        self.app.stop.set();thread.join(timeout=5)
        self.assertEqual(set(self.app.firebase_status.get('sources',{})),{'main','vendor'})
        ledger=self.app.ledger()
        try:self.assertEqual({r['source'] for r in ledger.rows()},{'main','vendor'})
        finally:ledger.close()
    def test_historical_cost_override_survives_future_feed(self):
        p=vendor();del p['data']['inventoryMovements'][0]['unitCost']
        self.post('/api/import',{'source':'vendor','payload':p})
        self.post('/api/cost',{'id':'m1','unitCost':'4'})
        self.post('/api/import',{'source':'vendor','payload':p})
        l=self.app.ledger()
        try:
            self.assertEqual(l.report()['expense'],3600)
            self.assertEqual(l.db.execute("SELECT kind FROM documents WHERE source='vendor' AND source_id='inventory:m1'").fetchone()[0],'inventory')
        finally:l.close()
    def test_supplier_receipt_payment_remains_paid_on_reimport(self):
        p=vendor();p['data']['purchaseReceipts']=[{'id':'r1','landedCostTotal':40,'createdAt':'2026-10-01'}]
        self.post('/api/import',{'source':'vendor','payload':p})
        v={'source':'vendor','id':'purchase-receipt:r1','paymentId':'stable-payment','date':'2026-10-04','amount':40,'account':'1020'}
        self.post('/api/pay',v)
        self.assertEqual(self.post('/api/pay',v)['duplicates'],1)
        self.post('/api/import',{'source':'vendor','payload':p})
        state=json.loads(self.client.open(self.base+'/api/state').read())
        d=next(d for d in state['documents'] if d['source_id']=='purchase-receipt:r1')
        self.assertEqual(d['balance'],0)
        self.assertEqual(next(a for a in state['report']['trial'] if a['code']=='2000')['balance'],0)
    def test_mixing_main_import_formats_is_rejected(self):
        self.post('/api/import',{'source':'main','payload':main_backup()})
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post('/api/import',{'source':'main','payload':{'data':{'generalLedger':[]}}})
        self.assertEqual(e.exception.code,400)
    def test_missing_posted_feed_record_is_not_silently_deleted(self):
        p=vendor();p['type']='business-accounting-feed'
        self.post('/api/import',{'source':'vendor','payload':p})
        p['data']['orders']=[];p['data']['payments']=[]
        with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/import',{'source':'vendor','payload':p})
        self.assertEqual(e.exception.code,400)
    def test_manual_void_keeps_audit_and_reverses_expense(self):
        self.post('/api/manual-document',{'kind':'expense','date':'2026-11-02','party':'Power company','reference':'VOID-1','amount':25,'account':'5400'})
        state=json.loads(self.client.open(self.base+'/api/state').read());d=next(d for d in state['documents'] if d['reference']=='VOID-1')
        self.post('/api/void',{'id':d['source_id']})
        state=json.loads(self.client.open(self.base+'/api/state').read());self.assertEqual(state['report']['expense'],0)
        self.assertEqual(len(state['batches']),2)
    def test_viewer_cannot_write_download_backup_or_print_payroll(self):
        self.post('/api/users',{'username':'viewer','name':'Viewer','role':'viewer','password':'viewer-test-passphrase'})
        viewer=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
        viewer.open(self.base).read()
        req=urllib.request.Request(self.base+'/api/auth/login',json.dumps({'username':'viewer','password':'viewer-test-passphrase'}).encode(),{'Content-Type':'application/json','X-Accounting-Request':'1'})
        viewer.open(req).read()
        state=json.loads(viewer.open(self.base+'/api/state').read());self.assertEqual(state['user']['role'],'viewer')
        for path in ['/api/backup','/api/payroll.csv']:
            with self.assertRaises(urllib.error.HTTPError) as exc:viewer.open(self.base+path)
            self.assertEqual(exc.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError):viewer.open(self.base+'/print?type=payroll')
        req=urllib.request.Request(self.base+'/api/settings',b'{"company":"Changed"}',{'Content-Type':'application/json','X-Accounting-Request':'1'})
        with self.assertRaises(urllib.error.HTTPError) as exc:viewer.open(req)
        self.assertEqual(exc.exception.code,403)
    def test_import_does_not_retain_credentials_from_source_backup(self):
        p=main_backup();p['data']['users']=[{'password':'not-a-real-secret'}];p['data']['orders'][0]['accessToken']='not-a-real-token'
        self.post('/api/import',{'source':'main','payload':p})
        ledger=self.app.ledger()
        try:
            batch=ledger.db.execute('SELECT payload FROM batches').fetchone()[0]
            self.assertNotIn('not-a-real-secret',batch);self.assertNotIn('not-a-real-token',batch)
        finally:ledger.close()
    def test_bad_import_does_not_leave_mutation_lock_held(self):
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/import',{'source':'main','payload':[]})
        result=self.post('/api/import/preview',{'source':'main','payload':main_backup()})
        self.assertEqual(result['added'],1)


if __name__=='__main__':unittest.main()
