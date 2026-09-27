import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from harness.cli import Stop, command, edit, run, safe_path

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        for args in [('init',), ('config','user.email','test@example.invalid'), ('config','user.name','Test')]:
            self.git(*args)
        (self.repo / 'calc.py').write_text('def add(a, b):\n    return a - b\n')
        (self.repo / 'check.py').write_text('from calc import add\nassert add(2, 3) == 5\n')
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')
        fixture = self.base / 'mock.json'
        fixture.write_text(json.dumps({'plan':'Correct addition','edits':[{'path':'calc.py','old':'return a - b','new':'return a + b'}]}))
        self.args = argparse.Namespace(repo=str(self.repo), output=str(self.base/'result'),issue='Fix add in calc.py',mock=str(fixture),adapter=None,test=[sys.executable,'check.py'],attempts=2,seconds=20,command_seconds=3,tokens=12000)
    def git(self,*args):
        return subprocess.run(['git',*args],cwd=self.repo,check=True,capture_output=True)
    def test_end_to_end(self):
        self.assertEqual(run(self.args),0)
        r=json.loads((self.base/'result/report.json').read_text())
        self.assertEqual(r['mode'],'simulation')
        self.assertEqual(r['baseline_verification'],'failed')
        self.assertEqual(r['verification'],'passed')
        self.assertIn('return a - b',(self.repo/'calc.py').read_text())
        self.git('apply','--check',str(self.base/'result/candidate.patch'))
    def test_missing_tests(self):
        self.args.test=None
        self.assertEqual(run(self.args),2)
        self.assertEqual(json.loads((self.base/'result/report.json').read_text())['verification'],'missing')
    def test_dirty_refused(self):
        (self.repo/'personal.txt').write_text('keep')
        with self.assertRaises(Stop): run(self.args)
    def test_path_guards_and_atomic_rejection(self):
        for name in ['../escape','.git/config','secret.txt','/tmp/escape']:
            with self.assertRaises(Stop): safe_path(self.repo,name)
        with self.assertRaises(Stop):
            edit(self.repo,[{'path':'calc.py','old':'return a - b','new':'return a + b'},{'path':'check.py','old':'absent','new':'oops'}])
        self.assertIn('return a - b',(self.repo/'calc.py').read_text())
    def test_timeout(self):
        self.assertEqual(command([sys.executable,'-c','import time; time.sleep(10)'],self.repo,0.1)['reason'],'timeout')
    def test_adapter_recovery(self):
        adapter=self.base/'adapter.py'
        adapter.write_text("import json,sys\nr=json.load(open(sys.argv[1]))\nold='absent' if r['attempt']==1 else 'return a - b'\nprint(json.dumps({'plan':'repair','edits':[{'path':'calc.py','old':old,'new':'return a + b'}]}))\n")
        self.args.mock=None
        self.args.adapter=[sys.executable,str(adapter)]
        self.assertEqual(run(self.args),0)
        self.assertEqual(json.loads((self.base/'result/report.json').read_text())['attempts'],2)
    def test_budget(self):
        self.args.tokens=1
        self.assertEqual(run(self.args),2)
        self.assertIn('budget',json.loads((self.base/'result/report.json').read_text())['error'])

if __name__=='__main__': unittest.main()
