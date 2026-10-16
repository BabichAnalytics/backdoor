import json
from pathlib import Path
import tempfile
import threading
import unittest
from engine import backup, roots, verify_report

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name); self.source=self.base/'source'; self.dest=self.base/'dest'
        self.source.mkdir(); self.dest.mkdir()
    def fixture(self):
        (self.source/'nested').mkdir(); (self.source/'empty').mkdir()
        (self.source/'nested'/'hello.txt').write_text('Important example data\n',encoding='utf-8')
        (self.source/'zero.bin').write_bytes(b'')
    def test_verified_copy_and_recheck(self):
        self.fixture(); r=backup(self.source,self.dest)
        self.assertEqual(r['status'],'completed'); self.assertEqual(r['verified_files'],2)
        run=Path(r['run_folder']); self.assertTrue((run/'files'/'empty').is_dir())
        self.assertTrue(verify_report(run/'report.json')['all_match'])
        self.assertEqual((self.source/'nested'/'hello.txt').read_bytes(),(run/'files'/'nested'/'hello.txt').read_bytes())
    def test_no_overwrite_on_repeat(self):
        self.fixture(); a=backup(self.source,self.dest); b=backup(self.source,self.dest)
        self.assertNotEqual(a['run_folder'],b['run_folder'])
    def test_reject_nested_both_directions(self):
        nested=self.source/'nested'; nested.mkdir()
        for a,b in [(self.source,nested),(nested,self.source),(self.source,self.source)]:
            with self.assertRaises(ValueError): roots(a,b)
    def test_tampering_detected(self):
        self.fixture(); r=backup(self.source,self.dest); run=Path(r['run_folder'])
        (run/'files'/'nested'/'hello.txt').write_text('tampered')
        self.assertFalse(verify_report(run/'report.json')['all_match'])
    def test_cancel_retains_partial_not_success(self):
        (self.source/'big').write_bytes(b'a'*(3*1024*1024)); stop=threading.Event()
        def notify(event):
            if event['event']=='progress': stop.set()
        r=backup(self.source,self.dest,stop,notify)
        self.assertEqual(r['status'],'cancelled'); self.assertEqual(r['verified_files'],0)
        self.assertIn('partial_file',r['files'][0]); self.assertTrue((self.source/'big').exists())
    def test_source_changed_during_copy(self):
        target=self.source/'file'; target.write_bytes(b'x'*1024)
        def notify(event):
            if event['event']=='progress': target.write_bytes(b'changed')
        r=backup(self.source,self.dest,notify=notify)
        self.assertEqual(r['status'],'completed_with_issues'); self.assertEqual(r['verified_files'],0)
    def test_skip_symlink(self):
        try: (self.source/'link').symlink_to(self.base)
        except OSError: self.skipTest('Symlink privileges unavailable')
        r=backup(self.source,self.dest); self.assertEqual(r['status'],'completed_with_issues')
        self.assertIn('link',r['skipped'])
    def test_manifest_traversal_rejected(self):
        self.fixture(); r=backup(self.source,self.dest); path=Path(r['run_folder'])/'report.json'
        r['files'][0]['path']='../../outside'; path.write_text(json.dumps(r))
        result=verify_report(path); self.assertEqual(result['results'][0]['status'],'unsafe_path')
    def test_empty_not_false_integrity_claim(self):
        r=backup(self.source,self.dest)
        self.assertFalse(verify_report(Path(r['run_folder'])/'report.json')['all_match'])

if __name__=='__main__': unittest.main()
