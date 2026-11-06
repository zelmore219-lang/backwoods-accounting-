import copy
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('publish_accounting_update',SCRIPTS/'publish_accounting_update.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AccountingFeedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.previous={'schemaVersion':1,'sourceCommit':'old','apps':{
            'main':{'windows':{'version':'8.2.7','sha256':'main-win'},'android':{'version':'8.2.7','sha256':'main-apk'}},
            'vendor':{'windows':{'version':'4.1.8','sha256':'vendor-win'},'android':{'version':'4.1.8','sha256':'vendor-apk'}},
            'accounting':{'windows':{'version':'1.0.6'},'android':{'version':'1.0.6','packageName':'com.backwoodsbrew.accounting','certificateSha256':'retained-key'}}}}
        self.windows={'version':'1.0.7','sha256':'new-windows'}
        self.android={'version':'1.0.7','packageName':'com.backwoodsbrew.accounting','certificateSha256':'retained-key','sha256':'new-apk'}

    def test_preserves_other_app_entries_and_original_feed(self):
        original=copy.deepcopy(self.previous)
        result=module.revised_feed(self.previous,self.windows,self.android,'new')
        for kind in ['main','vendor']:self.assertEqual(result['apps'][kind],original['apps'][kind])
        self.assertEqual(self.previous,original)
        self.assertEqual(result['apps']['accounting']['android'],self.android)

    def test_rejects_same_version_and_rollback(self):
        for version in ['1.0.6','1.0.5']:
            with self.subTest(version=version),self.assertRaises(ValueError):
                module.revised_feed(self.previous,{**self.windows,'version':version},self.android,'new')

    def test_rejects_replacement_signing_key_or_package(self):
        for change in [{'certificateSha256':'replacement-key'},{'packageName':'different.app'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                module.revised_feed(self.previous,self.windows,{**self.android,**change},'new')
