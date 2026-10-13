"""Source-backed A -> B -> C impact, with unchanged consumers and unrelated D."""
import copy
import tempfile
import unittest
from pathlib import Path

from test_unified_workflow import WorkFixture, WORK, git
import impact_policy as impact
import quality_policy as policy
import unified_workflow as workflow
import workspace_lock as locks


def chain_fixture(temp, files=None):
    return WorkFixture(temp, group=True, sources={
        'A': 'def get_customer():\n    return {"customer_id": 1}\n',
        'B': 'from a_api import get_customer\n\ndef summarize():\n    return get_customer()["customer_id"]\n',
        'C': 'from b_api import summarize\n\ndef display():\n    return summarize()\n',
        'D': 'def get_customer_label():\n    return "unrelated display text"\n',
    }, selected=['A'], terms={'A': ['get_customer', 'customer_id', 'summarize']},
        aliases=[('A', 'B', 'summarize', 'get_customer')], files=files, edges=[
        ('A', 'A', 'B', 'get_customer', 'get_customer'),
        ('A', 'B', 'C', 'summarize', 'summarize'),
    ])


class GroupImpactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def architecture(self, f, value):
        f.contract['architecture_ref'] = f.f.write('architecture.json', value)
        f.save_contract()
        f.f.approve()

    def test_single_change_traces_two_unchanged_consumers_and_preserves_historical_receipt(self):
        f = chain_fixture(self.temp)
        architecture = policy.read_json(f.root / f.contract['architecture_ref']['path'])
        self.assertEqual({x['repo_path']: x['status'] for x in architecture['repository_impacts']},
                         {'A': 'affected', 'B': 'affected', 'C': 'affected', 'D': 'unaffected'})
        self.assertEqual({x['repo_path'] for x in f.contract['verification_repositories']}, {'B', 'C'})
        f.implement()
        self.assertTrue(workflow.check(f.root, WORK, 'review', True)['ok'])
        f.accept()
        result = workflow.deliver(f.root, WORK, 'writer', True)
        self.assertEqual([x['repo_path'] for x in result['repositories']], ['A'])
        receipt = workflow.export_receipt(f.root, WORK, True)
        self.assertIn(f.f.prefix + 'impact-confirmation-0.json', {x['path'] for x in receipt['record_files']})
        for name in ('B', 'C', 'D'):
            self.assertEqual(git(f.repos[name], 'branch', '--show-current'), 'master')
            self.assertNotIn('feature/', git(f.repos[name], 'branch', '--list'))
            self.assertFalse(locks.repo_lock(f.repos[name]).exists())
        (f.repos['B'] / 'app.py').write_text('later unrelated work\n', encoding='utf-8')
        git(f.repos['B'], 'add', 'app.py')
        git(f.repos['B'], 'commit', '-m', 'later source')
        self.assertEqual(workflow.export_receipt(f.root, WORK, True), receipt)

    def test_incomplete_unrelated_or_unpinned_exploration_cannot_claim_or_create_branches(self):
        f = chain_fixture(self.temp)
        original = policy.read_json(f.root / f.contract['architecture_ref']['path'])
        pristine = copy.deepcopy(f.contract)
        cases = [
            ('empty dispositions', lambda a, c: a.update(repository_impacts=[])),
            ('missing transitive consumer', lambda a, c: a['repository_impacts'].pop(2)),
            ('consumer excluded', lambda a, c: a['repository_impacts'][2].update(status='unaffected', contract_ids=[])),
            ('unknown impact', lambda a, c: a['repository_impacts'][1].update(status='unknown')),
            ('unrelated second query', lambda a, c: a['changed_contracts'][0]['symbols'].__setitem__(1, 'unrelated_nonsense')),
            ('forged no-hit', lambda a, c: a['searches'][0].update(matches=[])),
            ('missing fixed consumer', lambda a, c: c.update(verification_repositories=[])),
            ('missing compatibility', lambda a, c: c['handoff'].update(compatibility_check_ids=[])),
            ('unbound edge checks', lambda a, c: a['impact_edges'][1].update(check_ids=[])),
            ('disconnected wrapper alias', lambda a, c: a['impact_edges'].pop(0)),
            ('wrapper mapping absent', lambda a, c: a['changed_contracts'][0]['symbol_sources'][-1].pop('via')),
            ('external unknown', lambda a, c: a.update(unresolved=['external contract unavailable'])),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                f.contract = copy.deepcopy(pristine)
                f.f.contract = f.contract
                architecture = copy.deepcopy(original)
                mutate(architecture, f.contract)
                self.architecture(f, architecture)
                with self.assertRaises((ValueError, TypeError)):
                    workflow.claim(f.root, WORK, 'writer', True)
                self.assertFalse((f.root / '.megin/workspace.lock.json').exists())
                for repo in f.repos.values():
                    self.assertNotIn('feature/', git(repo, 'branch', '--list'))

    def test_impact_cycles_are_valid_independently_from_delivery_order(self):
        f = chain_fixture(self.temp)
        architecture = policy.read_json(f.root / f.contract['architecture_ref']['path'])
        edge = copy.deepcopy(architecture['impact_edges'][1])
        edge['provider'], edge['consumer'] = edge['consumer'], edge['provider']
        architecture['impact_edges'].append(edge)
        self.architecture(f, architecture)
        self.assertEqual(workflow.validate_record(f.root, WORK, True)['repositories'], ['A'])
        self.assertEqual(f.contract['handoff']['merge_order'], ['A'])

    def test_actual_diff_confirmation_and_consumer_drift_block_gates(self):
        f = chain_fixture(self.temp)
        f.implement()
        original = policy.read_json(f.root / f.f.evidence['impact_confirmation_ref']['path'])
        cases = [
            ('valid classification edited after independent review', lambda v: v['changes'][0].update(reason='different otherwise-valid classification')),
            ('stale diff', lambda v: v.update(diff_sha256='0' * 64)),
            ('missing actual searches', lambda v: v.update(searches=[])),
            ('new interface', lambda v: v['changes'][0].update(kind='interface', contract_ids=['NEW-API'])),
            ('uncovered consumer', lambda v: v['repository_impacts'].pop(2)),
            ('missing path classification', lambda v: v.update(changes=[])),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                value = copy.deepcopy(original)
                mutate(value)
                name = Path(f.f.evidence['impact_confirmation_ref']['path']).name
                f.f.evidence['impact_confirmation_ref'] = f.f.write(name, value)
                f.save_evidence()
                self.assertFalse(workflow.check(f.root, WORK, 'review', True)['ok'])
        f.f.evidence['impact_confirmation_ref'] = f.f.write(Path(f.f.evidence['impact_confirmation_ref']['path']).name, original)
        f.save_evidence()
        (f.repos['C'] / 'app.py').write_text('consumer changed while reviewing\n', encoding='utf-8')
        result = workflow.check(f.root, WORK, 'review', True)
        self.assertFalse(result['ok'])
        self.assertIn('drifted', str(result['reasons']))

    def test_fixed_source_search_and_read_are_read_only(self):
        f = chain_fixture(self.temp)
        before = {name: (git(repo, 'rev-parse', 'HEAD'), git(repo, 'status', '--porcelain')) for name, repo in f.repos.items()}
        self.assertEqual(impact.search(f.repos['C'], f.bases['C'], 'get_customer'), [])
        self.assertEqual(impact.search(f.repos['C'], f.bases['C'], 'customer_id'), [])
        hits = impact.search(f.repos['C'], f.bases['C'], 'summarize()')
        self.assertEqual(hits, [{'path': 'app.py', 'line': 4, 'text': '    return summarize()'}])
        self.assertEqual(impact.search(f.repos['C'], f.bases['C'], 'unrelated_nonsense'), [])
        self.assertEqual(before, {name: (git(repo, 'rev-parse', 'HEAD'), git(repo, 'status', '--porcelain')) for name, repo in f.repos.items()})

    def test_unchanged_consumer_binary_deleted_and_untracked_input_drift_blocks_live_review(self):
        baseline = b'\x00baseline'
        f = chain_fixture(self.temp, files={'B': {'runtime.dat': baseline}})
        f.implement()
        self.assertTrue(workflow.check(f.root, WORK, 'review', True)['ok'])
        path = f.repos['B'] / 'runtime.dat'
        path.write_bytes(b'\x00different')
        result = workflow.check(f.root, WORK, 'review', True)
        self.assertFalse(result['ok'])
        self.assertIn('product bytes drifted', str(result['reasons']))
        path.unlink()
        self.assertFalse(workflow.check(f.root, WORK, 'review', True)['ok'])
        path.write_bytes(baseline)
        untracked = f.repos['B'] / 'runtime-input.json'
        untracked.write_text('{"consumer":"changed"}\n', encoding='utf-8')
        self.assertFalse(workflow.check(f.root, WORK, 'review', True)['ok'])
        untracked.unlink()
        self.assertTrue(workflow.check(f.root, WORK, 'review', True)['ok'])


if __name__ == '__main__':
    unittest.main()
