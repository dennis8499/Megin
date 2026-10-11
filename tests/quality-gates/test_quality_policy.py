"""Adversarial new-work policy cases; fixture outputs are structural test data."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / '.agents/skills/megin/scripts'
sys.path.insert(0, str(SCRIPTS))
import quality_policy as p
from functional_inventory import scan, SCHEMA

WORK = 'work-20261011-policy'


class PolicyFixture:
    def __init__(self, root):
        self.root = root
        self.prefix = f'docs/work/{WORK}/evidence/'
        self.records = set()
        self.fields = {'requirements_revision': 'req-1'}
        self.snapshot = 'a' * 64
        (root / 'app.py').write_text('def main():\n    return "behavior"\n', encoding='utf-8')
        (root / 'test_behavior.py').write_text('assert True\n', encoding='utf-8')
        work = root / 'docs/work' / WORK
        (work / 'plan-1').mkdir(parents=True, exist_ok=True)
        (work / 'evidence').mkdir(exist_ok=True)
        (work / 'plan-1/plan.md').write_text('exact plan\n', encoding='utf-8')
        (work / 'requirements.md').write_text('REQ-1: observable behavior\n', encoding='utf-8')
        inventory = scan(root, exclude_paths=p.SCAN_EXCLUSIONS)
        source_paths = [x['path'] for x in inventory['included']]
        report = {'schema': SCHEMA, 'snapshot_id': inventory['snapshot_id'],
                  'functions': [{'id': 'FUNC-MAIN', 'outcome': 'observable behavior', 'flow': 'input to output',
                                 'dependencies': [], 'paths': source_paths}],
                  'coverage': [{'path': x['path'], 'sha256': x['sha256'], 'status': 'checked',
                                'reason': 'read source', 'function_ids': ['FUNC-MAIN']} for x in inventory['included']],
                  'entrypoints': [{'entrypoint_id': x['entrypoint_id'], 'status': 'checked',
                                   'reason': 'traced', 'function_ids': ['FUNC-MAIN']}
                                  for x in inventory['entrypoint_candidates']], 'gaps': []}
        discovery = {'schema': 'megin-discovery/v1', 'work_id': WORK, 'requirements_revision': 'req-1',
                     'problem': 'problem', 'audience': 'requester', 'outcome': 'result', 'acceptance': 'observed result',
                     'facts': [], 'assumptions': [], 'decisions': [], 'technical_suggestions': [], 'blockers': [],
                     'requirements': [{'id': 'REQ-1', 'text': 'observable behavior'}],
                     'repositories': [{'repo_path': '.', 'scan_ref': self.write('scan.json', inventory),
                                       'functional_report': report}]}
        discovery_ref = self.write('discovery.json', discovery)
        self.contract = {'schema': 'megin-repo-quality-contract/v2', 'work_id': WORK, 'plan_version': 'plan-1',
                         'requirements_revision': 'req-1', 'max_corrections': 3,
                         'requirements_ref': f'docs/work/{WORK}/requirements.md',
                         'requirements_sha256': hashlib.sha256((work / 'requirements.md').read_bytes()).hexdigest(),
                         'scenario_ids': ['SCN-1'], 'behavior_trace': [{'scenario_id': 'SCN-1', 'requirement_ids': ['REQ-1'],
                         'given': 'valid input', 'when': 'operation', 'then': 'result', 'observable': 'result',
                         'assertion': 'AssertionError: expected behavior', 'check_id': 'unit',
                         'implementation_paths': ['app.py']}],
                         'checks': [{'id': 'unit', 'kind': 'test', 'command': 'python -m unittest', 'cwd': '.'}],
                         'discovery_ref': discovery_ref, 'discovery_sha256': discovery_ref['sha256'],
                         'approval_ref': self.prefix + 'approval.json',
                         'review_records': [self.prefix + f'review-attempt-{i}.json' for i in range(4)]}
        self.records.update(self.contract['review_records'] + [self.contract['approval_ref'], self.prefix + 'approval.md'])
        for number in range(4):
            self.records.update((self.prefix + f'review-{number}.md', self.prefix + f'correction-{number}.md'))
        self.records.update((self.prefix + 'red.log', self.prefix + 'green.log'))
        self.contract['process_records'] = sorted(self.records)
        self.approve()
        cycles = []
        test_sha = hashlib.sha256((root / 'test_behavior.py').read_bytes()).hexdigest()
        runs = []
        for number, phase in enumerate(('red', 'green'), 1):
            run = {'sequence': number, 'test_path': 'test_behavior.py', 'test_sha256': test_sha,
                   'command': 'python -m unittest', 'cwd': '.', 'exit_code': 1 if phase == 'red' else 0,
                   'executed': 1, 'failed': 1 if phase == 'red' else 0, 'skipped': 0}
            claims = {'command': 'Command: python -m unittest', 'cwd': 'Working directory: .',
                      'exit_code': f'Exit code: {run["exit_code"]}',
                      'counts': f'Tests: 1 executed, {run["failed"]} failed, 0 skipped',
                      'test_sha256': f'Test SHA-256: {test_sha}', 'sequence': f'Sequence: {number}'}
            if phase == 'red':
                run['failure_kind'] = 'assertion'
                claims['assertion'] = 'AssertionError: expected behavior'
            run['output'] = self.raw(phase + '.log', claims)
            runs.append(run)
        self.evidence = {'requirements_revision': 'req-1', 'writer': {'context': 'writer'}, 'review_history': [],
                         'tdd_cycles': [{'scenario_id': 'SCN-1', 'check_id': 'unit',
                         'assertion': 'AssertionError: expected behavior', 'red': runs[0], 'green': runs[1]}]}

    def write(self, name, value):
        relative = self.prefix + name
        self.records.add(relative)
        path = self.root / relative
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return {'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def raw(self, name, claims):
        relative = self.prefix + name
        self.records.add(relative)
        path = self.root / relative
        path.write_text('\n'.join(claims.values()) + '\n', encoding='utf-8')
        return {'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'claims': {k: {'line': i, 'text': v} for i, (k, v) in enumerate(claims.items(), 1)}}

    def approve(self):
        plan_sha = hashlib.sha256((self.root / f'docs/work/{WORK}/plan-1/plan.md').read_bytes()).hexdigest()
        contract_sha = p.canonical_digest(self.contract)
        raw = self.raw('approval.md', {'work_id': f'- work_id: {WORK}', 'plan_version': '- plan_version: plan-1',
            'verdict': '- verdict: APPROVED', 'response': '- response: "同意 plan-1"',
            'plan_sha256': f'- plan_sha256: {plan_sha}', 'contract_sha256': f'- contract_sha256: {contract_sha}'})
        self.write('approval.json', {'schema': 'megin-plan-approval/v1', 'actor_kind': 'human', 'verdict': 'APPROVED',
            'work_id': WORK, 'plan_version': 'plan-1', 'requirements_revision': 'req-1', 'response': '同意 plan-1',
            'plan_sha256': plan_sha, 'contract_sha256': contract_sha, 'source': raw})

    def review(self, verdict='APPROVED', context=None):
        number = len(self.evidence['review_history'])
        previous = self.evidence['review_history'][-1]['sha256'] if number else None
        context = context or f'reviewer-{number}'
        raw = self.raw(f'review-{number}.md', {'context': f'- context: {context}', 'verdict': f'- verdict: {verdict}',
            'snapshot': f'- snapshot: {self.snapshot}', 'round': f'- round: {number}',
            'previous_sha256': f'- previous_sha256: {previous}'})
        attempt = {'schema': 'megin-review-attempt/v1', 'work_id': WORK, 'requirements_revision': 'req-1',
            'round': number, 'previous_sha256': previous, 'context': context, 'invocation_id': context,
            'reviewer_kind': 'independent_readonly', 'snapshot': self.snapshot, 'verdict': verdict, 'source': raw}
        if number:
            attempt['correction_ref'] = self.raw(f'correction-{number}.md', {'repair': 'fixed findings and reran checks'})
        self.evidence['review_history'].append(self.write(f'review-attempt-{number}.json', attempt))
        self.evidence['review'] = {k: attempt[k] for k in ('context', 'verdict', 'snapshot', 'source')}

    def reasons(self, gate='acceptance'):
        result = []
        p.validate_evidence(self.root, WORK, self.fields, self.contract, self.records, self.evidence,
                            self.snapshot, gate, result)
        return result


class QualityPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.f = PolicyFixture(Path(temp.name))

    def test_initial_approval_passes(self):
        self.f.review()
        self.assertEqual([], self.f.reasons())
        p.validate_contract(self.f.root, WORK, self.f.fields, self.f.contract, self.f.records, live=True)

    def test_correction_approval_stops_early(self):
        self.f.review('CHANGES_REQUESTED')
        self.f.review()
        self.assertEqual([], self.f.reasons())

    def test_three_failed_corrections_block_and_resume_cannot_reset(self):
        for _ in range(4):
            self.f.review('CHANGES_REQUESTED')
        self.assertIn('three corrections exhausted', str(self.f.reasons()))
        self.f.evidence['review_history'] = self.f.evidence['review_history'][:1]
        self.assertIn('cannot discard', str(self.f.reasons()))

    def test_missing_approval_blocks(self):
        (self.f.root / self.f.contract['approval_ref']).unlink()
        self.f.review()
        self.assertTrue(self.f.reasons())

    def test_requirement_and_plan_changes_invalidate_approval(self):
        self.f.review()
        (self.f.root / f'docs/work/{WORK}/plan-1/plan.md').write_text('changed', encoding='utf-8')
        self.assertIn('approval missing', str(self.f.reasons()))

    def test_missing_exploration_coverage_blocks(self):
        path = self.f.root / self.f.contract['discovery_ref']['path']
        data = p.read_json(path)
        data['repositories'][0]['functional_report']['coverage'].pop()
        ref = self.f.write('discovery.json', data)
        self.f.contract.update(discovery_ref=ref, discovery_sha256=ref['sha256'])
        self.f.approve()
        self.f.review()
        self.assertIn('every current source', str(self.f.reasons()))

    def test_source_change_blocks_first_claim(self):
        (self.f.root / 'new.py').write_text('def main(): pass\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'):
            p.validate_contract(self.f.root, WORK, self.f.fields, self.f.contract, self.f.records, live=True)

    def test_invalid_red_cannot_count_as_tdd(self):
        self.f.review()
        for mutation in ({'failure_kind': 'import'}, {'exit_code': 0}, {'executed': 0}, {'skipped': 1}):
            with self.subTest(mutation=mutation):
                original = copy.deepcopy(self.f.evidence['tdd_cycles'])
                self.f.evidence['tdd_cycles'][0]['red'].update(mutation)
                self.assertTrue(self.f.reasons())
                self.f.evidence['tdd_cycles'] = original

    def test_self_review_and_reused_reviewer_block(self):
        self.f.review(context='writer')
        self.assertIn('fresh independent', str(self.f.reasons()))

    def test_stale_review_blocks(self):
        self.f.review()
        self.f.snapshot = 'b' * 64
        self.assertIn('current snapshot', str(self.f.reasons()))

    def test_raw_output_tampering_blocks(self):
        self.f.review()
        (self.f.root / self.f.prefix / 'red.log').write_text('forged summary', encoding='utf-8')
        self.assertIn('digest changed', str(self.f.reasons()))

    def test_missing_scenario_trace_blocks(self):
        self.f.contract['behavior_trace'] = []
        self.f.approve()
        self.f.review()
        self.assertIn('scenario traceability', str(self.f.reasons()))

    def test_unresolved_discovery_decision_blocks(self):
        data = p.read_json(self.f.root / self.f.contract['discovery_ref']['path'])
        data['blockers'] = ['refund policy unknown']
        ref = self.f.write('discovery.json', data)
        self.f.contract.update(discovery_ref=ref, discovery_sha256=ref['sha256'])
        self.f.approve()
        self.f.review()
        self.assertIn('blockers', str(self.f.reasons()))

    def test_append_is_exclusive_and_interrupted_index_recovers(self):
        from review_history import append, recover
        self.f.review()
        ref = self.f.evidence['review_history'][0]
        path = self.f.root / ref['path']
        attempt = p.read_json(path)
        path.unlink()
        self.f.evidence['review_history'] = []
        result = append(self.f.root, WORK, self.f.contract, self.f.records, self.f.evidence, attempt)
        self.assertEqual(ref['path'], result['review_history'][0]['path'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result['review_history'][0]['sha256'])
        original = path.read_bytes()
        with self.assertRaises(ValueError):
            append(self.f.root, WORK, self.f.contract, self.f.records, result, attempt)
        self.assertEqual(original, path.read_bytes())
        recovered = recover(self.f.root, WORK, self.f.contract, self.f.records, self.f.evidence)
        self.assertEqual(result, recovered)

    def test_reused_reviewer_after_correction_blocks(self):
        self.f.review('CHANGES_REQUESTED', context='reviewer')
        self.f.review(context='reviewer')
        self.assertIn('fresh independent', str(self.f.reasons()))

    def test_changed_approved_snapshot_uses_next_round(self):
        self.f.review()
        self.f.snapshot = 'b' * 64
        self.f.review()
        self.assertEqual([], self.f.reasons())


if __name__ == '__main__':
    unittest.main()
