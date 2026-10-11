"""Real process death, exact authority, secretless execution, measured gain."""
import copy
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
import integrations as IN
from coordinator import Controller
from workers import _resolve_in_scope, AirlockWorker
from olp_gate.gateway import verify_decision_receipt
from airlock.improvement import evaluate_survivor

TASK = 'readme-export-docs'

class Phase15Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autonomy-phase15-')
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.env = {**os.environ, 'AUTONOMY_TARGET_REPO': str(EXP.parents[1])}
    def tearDown(self):
        self.tmp.cleanup()
    def ctl(self):
        with patch.dict(os.environ, self.env):
            c = Controller(self.state, 'worker-alpha')
        c.queue = {TASK: c.queue[TASK]}
        return c

    def crash(self, phase):
        marker = self.root / 'ready'
        program = '''import os,signal,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from coordinator import Controller
c=Controller(Path(sys.argv[2]),'worker-alpha')
c.queue={'readme-export-docs':c.queue['readme-export-docs']}
def stop(p):
 if p==sys.argv[3]:
  Path(sys.argv[4]).write_text(p)
  signal.pause()
c._check_stop=stop
c.run_once()
'''
        proc = subprocess.Popen([sys.executable, '-c', program, str(EXP),
            str(self.state), phase, str(marker)], env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 150
        try:
            while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(.05)
            if not marker.exists():
                proc.kill()
                out, err = proc.communicate()
                self.fail(f'phase not reached: {out} {err}')
            os.kill(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, -signal.SIGKILL)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_sigkill_build_is_held_without_rerun(self):
        self.crash('build')
        c = self.ctl()
        self.assertEqual(c.run_once(), 'held')
        self.assertEqual(c.state['cycles_completed'], 1)
        self.assertEqual(self.ctl().run_once(), 'idle')

    def test_sigkill_permission_does_not_create_ref(self):
        self.crash('permission')
        self.assertEqual(self.ctl().run_once(), 'held')
        result = subprocess.run(['git', 'show-ref', '--verify',
            'refs/heads/autonomy-001/accepted/' + TASK], cwd=self.state / 'scratch',
            capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_ref_without_gate_execution_cannot_be_attributed(self):
        self.crash('permission')
        c = self.ctl()
        intent = c.state['current']['accept_intent']
        subprocess.run(['git', 'update-ref', intent['ref'], intent['commit']],
                       cwd=self.state / 'scratch', check=True)
        with self.assertRaisesRegex(RuntimeError, 'Gate consumption missing'):
            c.run_once()

    def test_sigkill_after_effect_reconciles_once_even_after_revocation(self):
        self.crash('effect')
        c = self.ctl()
        c.revoke()
        self.assertEqual(c.run_once(), 'accepted')
        self.assertEqual(self.ctl().run_once(), 'revoked')
        ledger = json.loads((self.state / 'gate-ledger.json').read_text())
        self.assertEqual(len(ledger['consumed_codes']), 1)
        self.assertEqual(len(ledger['attempts']), 1)
        self.assertEqual(c.state['cycles_completed'], 1)

    def permission(self):
        self.state.mkdir()
        key = IN.signing_key(self.state)
        evidence = {'task_id': TASK, 'operation_id': 'authority-test', 'eligible': True}
        receipt, action, code = IN.issue_permission(self.state,
            {'tool': 'git.update-ref', 'target': 'refs/heads/autonomy-001/accepted/test',
             'settings': {'commit': 'a' * 40, 'expected_old': '0' * 40}},
            evidence, 'a' * 64)
        return key, receipt, action, code

    def test_gate_tampering_wrong_action_replay_and_revocation(self):
        key, receipt, action, code = self.permission()
        self.assertTrue(verify_decision_receipt(receipt, [IN.public_key_hex(key)])['valid'])
        ledger = IN.VerifiedCommitLedger(self.state / 'ledger.json')
        calls = []
        def use(r, a, token=code, preflight=None):
            return ledger.execute_once(r, a, one_use_code=token,
                trusted_gate_keys=[IN.public_key_hex(key)],
                executor=lambda: calls.append('effect') or {'effect': True}, preflight=preflight)
        bad = copy.deepcopy(receipt)
        bad['commit_authorization']['target'] = 'refs/heads/main'
        self.assertFalse(use(bad, action)['authorized'])
        for field, value in [('target', 'refs/heads/main'), ('tool', 'git.push'),
                              ('settings', {'commit': 'b' * 40}), ('run_id', 'other')]:
            changed = {**action, field: value}
            self.assertFalse(use(receipt, changed)['authorized'])
        self.assertFalse(use(receipt, action, 'wrong-code')['authorized'])
        denied = use(receipt, action, preflight=lambda: {
            'allowed': False, 'reason_codes': ['revoked'], 'evidence': {'revoked': True}})
        self.assertFalse(denied['authorized'])
        self.assertFalse(use(receipt, action)['authorized'])
        self.assertEqual(calls, [])

    def test_receipt_signature_tampering_blocks_resume(self):
        c = self.ctl()
        c._receipt('mission', None, None, 'DENY', 'test')
        path = next((self.state / 'receipts').glob('*.json'))
        rec = json.loads(path.read_text())
        rec['decision']['reason'] = 'forged'
        path.write_text(json.dumps(rec))
        with self.assertRaisesRegex(RuntimeError, 'signature invalid'):
            self.ctl()

    def test_orphan_signed_receipt_reconciled(self):
        c = self.ctl()
        c._save()
        old = (self.state / 'state.json').read_bytes()
        c._receipt('mission', None, None, 'DENY', 'durable before state')
        (self.state / 'state.json').write_bytes(old)
        self.assertEqual(len(self.ctl().state['receipts']), 1)

    def test_scope_prefix_and_symlink_escape(self):
        work = self.root / 'work'
        work.mkdir()
        (work / 'scope').mkdir()
        (work / 'scope' / 'link').symlink_to(self.root)
        for rel in ['scope-other/a', '../outside', '/tmp/outside', 'scope/link/a']:
            self.assertIsNone(_resolve_in_scope(work, ['scope'], rel))

    def test_isolation_no_credentials_host_files_or_network(self):
        outside = self.root / 'secret-marker'
        outside.write_text('canary')
        exported = self.root / 'exported'
        exported.mkdir()
        script = '''import os,socket
from pathlib import Path
assert 'PHASE15_SECRET_CANARY' not in os.environ
assert not Path(%r).exists()
try:
 socket.create_connection(('1.1.1.1',443),timeout=1)
except OSError:
 pass
else:
 raise AssertionError('network available')
print('ISOLATION_CHECKED')
''' % str(outside)
        with patch.dict(os.environ, {'PHASE15_SECRET_CANARY': 'never-forward'}):
            result = IN.isolated_run(exported, ['python', '-I', '-c', script], 5)
        self.assertEqual(result['exit_code'], 0, result)
        self.assertIn('ISOLATION_CHECKED', result['stdout_tail'])
        with self.assertRaises(ValueError):
            AirlockWorker('test', {'command': ['python'], 'pass_env': ['GH_TOKEN']})

    def test_airlock_worker_adapter_applies_only_exported_changes(self):
        c = self.ctl()
        with patch.dict(os.environ, self.env):
            base = c._ensure_scratch()
        wt = c._worktree(TASK, base)
        script = "from pathlib import Path; p=Path('experiments/review-desk-001/README.md'); p.write_text(p.read_text()+'\\nOffline adapter fixture.\\n')"
        worker = AirlockWorker('offline-fixture', {'command': ['python', '-I', '-c', script], 'pass_env': []})
        result = worker.build(c.queue[TASK], wt, c.mission['target']['scope_paths'],
                              c.mission['boundaries']['protected_paths'])
        self.assertTrue(result.ok, result.notes)
        self.assertEqual(result.files_changed, ['experiments/review-desk-001/README.md'])
        self.assertTrue((wt / '.git').exists())  # worker never received this pointer

    def test_revocation_and_policy_changes_fail_closed(self):
        c = self.ctl()
        self.assertTrue(c._fresh_authority())
        with patch('coordinator.load_policy', return_value={'unauthorized': True}):
            self.assertFalse(c._fresh_authority())
        c.revoke()
        self.assertFalse(c._fresh_authority())
        self.assertEqual(c.run_once(), 'revoked')
        self.assertFalse((self.state / 'scratch').exists())

    def test_evaluator_zero_tests_fail_and_candidate_import_used(self):
        import evaluator as EV
        exported = self.root / 'empty-suite'
        exported.mkdir()
        (exported / 'empty').mkdir()
        with patch.object(IN, 'isolated_run', return_value={
            'stderr_tail': 'Ran 0 tests in 0.001s\nOK', 'stdout_tail': '',
            'exit_code': 0, 'timed_out': False, 'stdout_sha256': 'a', 'stderr_sha256': 'b'}):
            self.assertFalse(EV._run_unittests(exported, 'empty')['ok'])

    def test_protected_tests_pass_but_candidate_fails_hidden_holdout(self):
        import evaluator as EV
        c = self.ctl()
        with patch.dict(os.environ, self.env):
            base = c._ensure_scratch()
        wt = c._worktree(TASK, base)
        product = wt / 'experiments/review-desk-001/review.py'
        product.write_text(product.read_text().replace(
            'if _INJECTION.search(original):',
            'if _INJECTION.search(original) and not original.startswith("Please ignore all prior"):'))
        EV.prepare_holdout(wt, EXP / 'holdout')
        try:
            result = EV.evaluate(c.queue[TASK], wt, wt, '.holdout_tmp',
                                 EXP.parent / 'review-desk-001', c.mission['budgets'])
        finally:
            EV.cleanup_holdout(wt)
        self.assertFalse(result.passed)
        self.assertTrue(result.protected_tests['ok'], result.protected_tests)
        self.assertGreater(result.protected_tests['ran'], 0)
        self.assertFalse(result.holdout['ok'], result.holdout)
        self.assertIn('test_novel_wording_still_flagged', result.holdout['tail'])

    def test_sandbox_enforces_deadline(self):
        exported = self.root / 'timeout'
        exported.mkdir()
        result = IN.isolated_run(exported,
            ['python', '-I', '-c', 'import time; time.sleep(60)'], timeout=1)
        self.assertEqual(result['exit_code'], 124, result)

    def test_passing_tests_not_measured_improvement(self):
        # Exercise Airlock's actual improvement evaluator on frozen commits.
        repo = self.root / 'metric-repo'
        repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-c', 'user.name=test', '-c',
                'user.email=test@local', *args], cwd=repo, text=True).strip()
        git('init', '-q')
        (repo / 'value.txt').write_text('baseline')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        base = git('rev-parse', 'HEAD')
        (repo / 'value.txt').write_text('candidate')
        git('commit', '-qam', 'candidate')
        candidate = git('rev-parse', 'HEAD')
        objective = {'measure': {'command': ['offline-metric'], 'repeats': 1,
            'timeout_seconds': 5, 'direction': 'maximize', 'unit': 'utility'},
            'bounds': {'max_changed_files': 1, 'max_changed_lines': 10},
            'selection': {'minimum_gain': '1', 'complexity_penalty_per_changed_line': '0'}}
        row = {'candidate_id': 'passing-tests', 'commit': candidate,
               'disposition': 'SURVIVED', 'changed_paths': ['value.txt']}
        def measured(value):
            def runner(argv, cwd, **kwargs):
                return {'argv': argv, 'exit_code': 0, 'timed_out': False,
                    'duration_seconds': 0, 'stdout': json.dumps({'value': value}), 'stderr': ''}
            return evaluate_survivor(repo, base=base, row=row,
                baseline={'minimum': '10', 'maximum': '10'}, objective=objective,
                protected_paths=[], objective_relative_path='objective.json', command_runner=runner)
        self.assertEqual(measured('10')['reason'], 'MINIMUM_GAIN_NOT_CLEARED')
        self.assertEqual(measured('9')['reason'], 'MINIMUM_GAIN_NOT_CLEARED')
        self.assertEqual(measured('12')['disposition'], 'ELIGIBLE')
        # Metric runner is synthetic; this test does not demonstrate real improvement.

if __name__ == '__main__':
    unittest.main()
