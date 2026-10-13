import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('catalog_pr_guard',
    Path(__file__).resolve().parents[1] / 'scripts/check_catalog_pr.py')
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


class CatalogPRGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / 'base'
        self.base.mkdir()
        self.git(self.base, 'init', '-q')
        self.git(self.base, 'config', 'user.name', 'Test Fixture')
        self.git(self.base, 'config', 'user.email', 'fixture@example.invalid')
        (self.base / 'catalog/evidence').mkdir(parents=True)
        (self.base / 'catalog/evidence/original.json').write_text('{}')
        policy = (Path(__file__).resolve().parents[1] / 'catalog/reviewed.json').read_text()
        (self.base / 'catalog/reviewed.json').write_text(policy)
        self.git(self.base, 'add', '.')
        self.git(self.base, 'commit', '-qm', 'Synthetic base')
        self.candidate = Path(self.tmp.name) / 'candidate'
        self.git(self.base, 'clone', '-q', str(self.base), str(self.candidate))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def git(root, *args):
        subprocess.run(['git', '-C', str(root), *args], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def add(self, path, data):
        file = self.candidate / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data)
        self.git(self.candidate, 'add', path)

    def test_candidate_cannot_run_code_or_self_approve(self):
        for path in ('bureau/catalog.py', '.github/workflows/attack.yml', 'catalog/reviewed.json'):
            with self.subTest(path=path):
                self.add(path, 'raise SystemExit("ATTACK")')
                with self.assertRaisesRegex(ValueError, 'separate maintainer'):
                    guard.check(self.base, self.candidate, 'alice')
                self.git(self.candidate, 'reset', '--hard', '-q', 'HEAD')
                self.git(self.candidate, 'clean', '-fdq')

    def test_old_evidence_cannot_be_rewritten_or_deleted(self):
        self.add('catalog/evidence/original.json', '{"now":"success"}')
        with self.assertRaisesRegex(ValueError, 'append-only'):
            guard.check(self.base, self.candidate, 'alice')
        self.git(self.candidate, 'reset', '--hard', '-q', 'HEAD')
        self.git(self.candidate, 'rm', '-q', 'catalog/evidence/original.json')
        with self.assertRaisesRegex(ValueError, 'append-only'):
            guard.check(self.base, self.candidate, 'alice')

    def test_escaping_symlink_refused_before_parser(self):
        file = self.candidate / 'catalog/evidence/secret.json'
        file.symlink_to('/etc/passwd')
        self.git(self.candidate, 'add', 'catalog/evidence/secret.json')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            guard.check(self.base, self.candidate, 'alice')

    def test_oversized_file_refused_before_parser(self):
        self.add('catalog/evidence/huge.json', ' ' * (guard.MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'too large'):
            guard.check(self.base, self.candidate, 'alice')

    def capability(self):
        # Test-only JSON; no public listing is created by the data guard.
        return {'format': 'openline.capability.v1', 'id': 'alice-test-tool',
                'version': '1.0.0', 'name': 'Test fixture', 'summary': 'Local rule test',
                'tasks': ['text-digest'], 'contributor_id': 'alice', 'worker_id': None,
                'provenance': {'source_url': 'https://github.com/alice/fixture',
                               'source_revision': None, 'authors': ['alice']},
                'usage_terms': {'license': 'MIT', 'summary': 'Test-only terms'},
                'price': None, 'inquiry': {'url': 'https://github.com/terryncew/openline-bureau/issues/new',
                                         'accepts_inquiries': False},
                'limitations': ['No real evidence'], 'lineage': [], 'evidence': [],
                'synthetic': False,
                'public_release': {'authorized': True, 'rights_confirmed': True,
                                   'contains_private_data': False}}

    def test_new_author_matched_data_passes_without_approval_or_publication(self):
        self.add('catalog/submissions/capabilities/new.json', json.dumps(self.capability()))
        self.assertEqual(guard.check(self.base, self.candidate, 'Alice'), 1)
        self.assertEqual(json.loads((self.base / 'catalog/reviewed.json').read_text())['reviews'], [])

    def test_claimed_author_cannot_impersonate_actual_pr_author(self):
        self.add('catalog/submissions/capabilities/new.json', json.dumps(self.capability()))
        with self.assertRaisesRegex(ValueError, 'actual PR author'):
            guard.check(self.base, self.candidate, 'mallory')
