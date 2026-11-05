"""Publishing must reject invalid packages before touching GitHub."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from publish_updates import publish,release,create_release
from build_update_release import build

class UpdateReleaseTests(unittest.TestCase):
    def test_incomplete_feed_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'backwoods-updates.json').write_text(json.dumps({'schemaVersion':1,'apps':{}}))
            with patch('publish_updates.subprocess.check_output',side_effect=AssertionError('GitHub must not be called')):
                with self.assertRaisesRegex(ValueError,'Incomplete'):publish('test',root)
    def test_checksum_mismatch_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);artifact={'url':'https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/test/a.exe','sha256':'0'*64,'size':2}
            (root/'a.exe').write_bytes(b'MZ');(root/'backwoods-updates.json').write_text(json.dumps({'schemaVersion':1,'apps':{k:{'windows':artifact,'android':artifact} for k in ['main','vendor','accounting']}}))
            with patch('publish_updates.subprocess.check_output',side_effect=AssertionError('GitHub must not be called')):
                with self.assertRaisesRegex(ValueError,'checksum'):publish('test',root)
    def test_drafts_are_found_before_resuming_upload(self):
        draft={'tag_name':'test','draft':True,'assets':[]}
        with patch('publish_updates.subprocess.check_output',return_value=json.dumps([draft])):
            self.assertEqual(release('test'),draft)
    def test_new_draft_uses_creation_response_without_listing_race(self):
        draft={'id':123,'tag_name':'test','draft':True,'assets':[]}
        with patch('publish_updates.subprocess.check_output',return_value=json.dumps(draft)) as command:
            self.assertEqual(create_release('test','abc','Title','Notes'),draft)
            self.assertEqual(command.call_count,1)
            self.assertEqual(json.loads(command.call_args.kwargs['input'])['tag_name'],'test')
    def test_reserved_feed_tag_cannot_be_used_for_package_builds(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'versioned'):build('app-updates',Path(directory))
if __name__=='__main__':unittest.main()
