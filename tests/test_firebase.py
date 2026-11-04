import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from accounting.firebase_sync import Firebase,SCHEMA,CONFIG
from accounting.ledger import Ledger,AccountingError
from accounting import auth

class MemoryVault:
    value=None
    def read(self):return self.value
    def save(self,value):self.value=value

class FirebaseTests(unittest.TestCase):
    def test_rules_merge_only_adds_accounting_to_supplied_baseline(self):
        root=Path(__file__).resolve().parents[1]/'firebase'
        original=(root/'firestore.original.rules').read_text()
        merged=(root/'firestore.rules').read_text()
        start=merged.index('\n    // BEGIN AUTOMATIC ACCOUNTING ADDITION')
        end=merged.index('    // DENY ALL OTHER FIRESTORE ACCESS',start)
        self.assertEqual(merged[:start]+merged[end:],original)
        added=merged[start:end]
        self.assertIn('request.auth.uid == ownerUid',added)
        self.assertIn("role() in ['owner','admin','administrator']",added)
        self.assertNotIn('if true',added)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'ledger.db');self.ledger.db.executescript(SCHEMA)
        self.user=auth.create_user(self.ledger,{'username':'owner','name':'Owner','password':'a secure testing passphrase'},first=True)
        self.vault=MemoryVault();self.calls=[];self.documents={}
        def transport(url,value=None,token=None,form=False):
            self.calls.append((url,value,token))
            if 'signInWithPassword' in url:return {'localId':'uid-owner','refreshToken':'refresh-secret','idToken':'verified-token','expiresIn':3600}
            if 'accounts:lookup' in url:return {'users':[{'localId':'uid-owner'}]}
            if '/v1/token?' in url:return {'user_id':'uid-owner','id_token':'new-token','expires_in':3600}
            return self.documents.get(url)
        self.client=Firebase(self.temp.name,transport=transport,vault=self.vault)
        self.client.connect(self.ledger,self.user,'owner@example.test','transient password')
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def put(self,raw=None):
        raw=raw or json.dumps({'schemaVersion':1,'type':'business-accounting-feed','data':{'memo':'Unicode ☕'}}).encode()
        root='https://firestore.googleapis.com/v1/'+self.client.root()+'/sources/main'
        meta={'updateTime':'v1','fields':{'sha256':{'stringValue':hashlib.sha256(raw).hexdigest()},'generation':{'stringValue':'00000000-0000-0000-0000-000000000001'},'chunkCount':{'integerValue':'1'},'bytes':{'integerValue':str(len(raw))},'exportedAt':{'stringValue':'2026-11-04T12:00:00Z'}}}
        self.documents[root]=meta
        self.documents[root+'/generations/00000000-0000-0000-0000-000000000001/chunks/0000']={'fields':{'data':{'stringValue':base64.b64encode(raw).decode()}}}
        return root,meta
    def test_verified_complete_snapshot_and_unchanged_skip(self):
        root,meta=self.put();digest,packet=self.client.snapshot('main');self.assertEqual(packet['data']['memo'],'Unicode ☕')
        self.assertIsNone(self.client.snapshot('main',digest))
    def test_incomplete_or_corrupt_snapshot_never_imports(self):
        root,meta=self.put();self.documents.pop(next(k for k in self.documents if '/chunks/' in k))
        with self.assertRaisesRegex(AccountingError,'incomplete'):self.client.snapshot('main')
        self.put();meta=self.documents[root];meta['fields']['sha256']['stringValue']='0'*64
        with self.assertRaisesRegex(AccountingError,'integrity'):self.client.snapshot('main')
    def test_credentials_not_in_ledger_and_rebinding_is_blocked(self):
        dump='\n'.join(self.ledger.db.iterdump());self.assertNotIn('refresh-secret',dump);self.assertNotIn('transient password',dump)
        other={**self.user,'id':'other-user'}
        with self.assertRaisesRegex(AccountingError,'already bound'):self.client.connect(self.ledger,other,'owner@example.test','password')
    def test_google_confirmation_required_for_bound_identity(self):
        self.documents['https://firestore.googleapis.com/v1/'+self.client.root()+'/settings/service']={'fields':{'origin':{'stringValue':'https://books.example.test'}}}
        claims={'aud':CONFIG['projectId'],'iss':'https://securetoken.google.com/'+CONFIG['projectId'],'sub':'uid-owner'}
        token='header.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.signature'
        self.assertEqual(self.client.verify_identity(token),'uid-owner')
        self.assertTrue(any('accounts:lookup' in c[0] for c in self.calls))
        claims['aud']='other-project';token='h.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.s'
        with self.assertRaises(AccountingError):self.client.verify_identity(token)
    def test_refreshed_identity_must_match_company(self):
        self.client.expires=0;self.assertEqual(self.client.bearer(),'new-token')
        self.client.connection['uid']='other-owner';self.client.expires=0
        with self.assertRaisesRegex(AccountingError,'identity changed'):self.client.bearer()
