"""Exercise native v2 via public locks, gates, delivery export and standalone review."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import test_quality_policy as policy_tests
import test_repo_workflow as legacy
REPO_WORK_ID = legacy.REPO_WORK_ID
import quality_gate as q
import repo_workspace
from delivery_receipt import export_receipt


class NativeV2Tests(legacy.RepoWorkflowTests):
    def prepare_work(self, with_remote=False):
        super().prepare_work(with_remote)
        (self.repo / '.megin/workspace.lock.json').unlink()  # discard legacy fixture lock
        previous = policy_tests.WORK
        policy_tests.WORK = REPO_WORK_ID
        self.addCleanup(setattr, policy_tests, 'WORK', previous)
        work = self.repo / 'docs/work' / REPO_WORK_ID
        old = q.read_json(work / 'plan-1/quality-contract.json')
        f = policy_tests.PolicyFixture(self.repo)
        records = set(old['process_records']) | f.records
        contract = {**old, **f.contract, 'process_records': sorted(records),
                    'allowed_paths': old['allowed_paths'] + ['test_behavior.py']}
        f.contract, f.records = contract, records
        f.approve()
        (work / 'plan-1/quality-contract.json').write_text(json.dumps(contract, indent=2) + '\n', encoding='utf-8')
        workflow = work / 'workflow.md'
        workflow.write_text(workflow.read_text(encoding='utf-8').replace('megin-repo-workflow/v1',
            'megin-repo-workflow/v2') + '- requirements_revision: req-1\n', encoding='utf-8')
        f.fields = q.workflow_fields(workflow)
        (work / 'evidence/quality.json').unlink()  # remove legacy fixture evidence
        repo_workspace.claim(self.repo, REPO_WORK_ID, 'writer-1')
        self.write_accepted_evidence()
        quality_path = work / 'evidence/quality.json'
        quality = q.read_json(quality_path)
        f.snapshot = self.snapshot
        f.evidence['writer'] = quality['writer']
        f.review()
        quality.update(schema='megin-repo-quality-evidence/v2', requirements_revision='req-1',
                       tdd_cycles=f.evidence['tdd_cycles'], review_history=f.evidence['review_history'],
                       review=f.evidence['review'])
        quality_path.write_text(json.dumps(quality, indent=2) + '\n', encoding='utf-8')

    def stage_accepted_snapshot(self):
        super().stage_accepted_snapshot()
        self.git('add', 'test_behavior.py')

    def test_v2_receipt_passes_standalone_mergereviewer(self):
        super().test_remote_is_optional_and_full_local_workflow_completes()
        receipt = export_receipt(self.repo, REPO_WORK_ID)
        paths = {x['path'] for x in receipt['record_files']}
        for name in ('scan.json', 'discovery.json', 'approval.json', 'approval.md',
                     'red.log', 'green.log', 'review-attempt-0.json', 'review-0.md'):
            self.assertIn(f'docs/work/{REPO_WORK_ID}/evidence/{name}', paths)
        binding_root = Path(os.environ.get('MEGIN_TEST_MERGE_REVIEWER_SCRIPTS',
            str(Path(__file__).resolve().parents[3] / 'MergeReviewer/skills/merge-reviewer/scripts')))
        binding_path = binding_root / 'delivery_binding.py'
        spec = importlib.util.spec_from_file_location('independent_binding', binding_path)
        binding = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(binding)
        binding.validate_receipt(receipt, self.repo)
        (self.repo / 'test_behavior.py').write_text('new work after delivery\n', encoding='utf-8')
        self.assertEqual(receipt, export_receipt(self.repo, REPO_WORK_ID))
        binding.validate_receipt(receipt, self.repo)
        raw = self.repo / f'docs/work/{REPO_WORK_ID}/evidence/red.log'
        raw.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            binding.validate_receipt(receipt, self.repo)

    def test_v2_workflow_cannot_downgrade_quality_contract(self):
        self.prepare_work()
        path = self.repo / f'docs/work/{REPO_WORK_ID}/plan-1/quality-contract.json'
        contract = q.read_json(path)
        contract['schema'] = 'megin-repo-quality-contract/v1'
        path.write_text(json.dumps(contract), encoding='utf-8')
        with self.assertRaisesRegex(q.InvalidEvidence, 'matching workflow'):
            q.load_contract(self.repo.resolve(), REPO_WORK_ID)
        with self.assertRaises(q.InvalidEvidence):
            repo_workspace.claim(self.repo, REPO_WORK_ID, 'writer-1')
