import copy
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_main_update import prepare,same_asset

class MainPublicationTests(unittest.TestCase):
    def setUp(self):
        self.feed={'schemaVersion':1,'customTopLevel':{'preserve':True},'apps':{
            'main':{'name':'Main','windows':{'version':'8.2.7','sha256':'old','extra':'keep'},'android':{'version':'8.2.7','sha256':'old','packageName':'com.backwoodsbrew.main.connected'}},
            'vendor':{'windows':{'version':'4.1.8','url':'vendor'},'android':{'version':'4.1.8'}},
            'accounting':{'windows':{'version':'1.0.6'},'android':{'version':'1.0.6'}},
            'future':{'data':[1,2,3]}}}
        self.packages={platform:{'version':'8.2.9','sha256':'verified','url':'main-only','size':123} for platform in ['windows','android']}
    def test_only_main_changes_without_mutating_input(self):
        before=copy.deepcopy(self.feed);result=prepare(self.feed,self.packages,{'versionCode':80209})
        self.assertEqual(self.feed,before)
        for app in ['vendor','accounting','future']:self.assertEqual(result['apps'][app],before['apps'][app])
        self.assertEqual(result['customTopLevel'],before['customTopLevel'])
        self.assertEqual(result['apps']['main']['windows']['extra'],'keep')
        self.assertEqual(result['apps']['main']['android']['versionCode'],80209)
    def test_version_regressions_and_same_version_replacements_are_blocked(self):
        self.feed['apps']['main']['windows']['version']='8.3.0'
        with self.assertRaisesRegex(ValueError,'newer'):prepare(self.feed,self.packages,{})
        self.feed['apps']['main']['windows']['version']='8.2.9'
        with self.assertRaisesRegex(ValueError,'new version'):prepare(self.feed,self.packages,{})
    def test_channel_concurrency_requires_same_asset_identity_and_digest(self):
        self.assertTrue(same_asset({'id':1,'digest':'a'},{'id':1,'digest':'a'}))
        self.assertFalse(same_asset({'id':1,'digest':'a'},{'id':2,'digest':'a'}))
        self.assertFalse(same_asset({'id':1,'digest':'a'},{'id':1,'digest':'b'}))

if __name__=='__main__':unittest.main()
