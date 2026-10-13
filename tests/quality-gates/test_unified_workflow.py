"""Public behavior of the native Repo v3 / Group v6 workflow."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/megin/scripts'
sys.path.insert(0, str(SCRIPTS))
import quality_policy as policy
import quality_gate as quality
import unified_workflow as workflow
import workspace_context as context
import workspace_lock as locks
import test_quality_policy as policy_tests

WORK = policy_tests.WORK


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class WorkFixture:
    """Synthetic human/reviewer transcripts are structural test data only."""
    def __init__(self, temp, group=False, count=1, unmodified=False, sources=None, selected=None, edges=None, terms=None, aliases=None, files=None):
        self.group, self.temp = group, temp
        self.root = temp / ('group' if group else 'repo')
        self.root.mkdir()
        shutil.copytree(ROOT / '.agents/skills', self.root / '.agents/skills',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.repos, self.remotes, self.bases = {}, {}, {}
        names = list(sources) if sources else [f'repo-{i}' for i in range(count)] if group else ['.']
        if unmodified:
            names.append('unmodified')
        for name in names:
            repo = self.root if name == '.' else self.root / name
            repo.mkdir(exist_ok=True)
            git(repo, 'init', '-b', 'master')
            git(repo, 'config', 'user.name', 'Workflow test')
            git(repo, 'config', 'user.email', 'workflow@example.invalid')
            (repo / 'app.py').write_text(sources[name] if sources else 'def main():\n    return "behavior"\n', encoding='utf-8')
            (repo / 'test_behavior.py').write_text('assert True\n', encoding='utf-8')
            for relative, content in (files or {}).get(name, {}).items():
                path = repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            git(repo, 'add', '.')
            git(repo, 'commit', '-m', 'base')
            remote = temp / ('remote-' + ('native' if name == '.' else name) + '.git')
            git(temp, 'init', '--bare', '-b', 'master', str(remote))
            git(repo, 'remote', 'add', 'origin', str(remote))
            git(repo, 'push', 'origin', 'master')
            self.repos[name], self.remotes[name], self.bases[name] = repo, remote, git(repo, 'rev-parse', 'HEAD')
        self.selected = selected if selected is not None else [name for name in names if name != 'unmodified']
        self.f = policy_tests.PolicyFixture(self.root)
        if group:
            (self.root / 'app.py').unlink()
            (self.root / 'test_behavior.py').unlink()
        self.work = self.root / f'docs/work/{WORK}'
        discovery_path = self.root / self.f.contract['discovery_ref']['path']
        discovery = policy.read_json(discovery_path)
        discovery['repositories'] = []
        architecture_rows = []
        from functional_inventory import scan, SCHEMA
        for name, repo in self.repos.items():
            inventory = scan(repo, exclude_paths=policy.SCAN_EXCLUSIONS)
            if group:
                inventory['source_commit'] = self.bases[name]
            paths = [x['path'] for x in inventory['included']]
            report = {'schema': SCHEMA, 'snapshot_id': inventory['snapshot_id'],
                      'functions': [{'id': 'FUNC-MAIN', 'outcome': 'result', 'flow': 'input to result',
                                     'dependencies': [], 'paths': paths}],
                      'coverage': [{'path': x['path'], 'sha256': x['sha256'], 'status': 'checked',
                                    'reason': 'read source', 'function_ids': ['FUNC-MAIN']} for x in inventory['included']],
                      'entrypoints': [{'entrypoint_id': x['entrypoint_id'], 'status': 'checked',
                                       'reason': 'traced source', 'function_ids': ['FUNC-MAIN']}
                                      for x in inventory['entrypoint_candidates']], 'gaps': []}
            scan_ref = self.f.write('scan-' + ('native' if name == '.' else name) + '.json', inventory)
            discovery['repositories'].append({'repo_path': name, 'scan_ref': scan_ref, 'functional_report': report})
            architecture_rows.append({'repo_path': name, 'snapshot_id': inventory['snapshot_id'],
                                      'summary': 'entrypoint returns a result', 'components': [{'name': 'application', 'paths': ['app.py']}],
                                      'data_flows': ['input to result'], 'entrypoints': ['app.py:main'], 'dependencies': [],
                                      'test_paths': ['test_behavior.py'], 'impact_paths': ['app.py']})
        discovery_ref = self.f.write('discovery.json', discovery)
        contract = self.f.contract
        contract.update(schema=workflow.schemas(group)[1], discovery_ref=discovery_ref,
                        discovery_sha256=discovery_ref['sha256'], delivery_mode='feature_handoff',
                        quality_ref=self.f.prefix + 'quality.json', delivery_ref=self.f.prefix + 'delivery.json',
                        skills_sha256=workflow.fingerprint(self.root))
        rows = [{'repo_path': name, 'remote_name': 'origin', 'remote_url': str(self.remotes[name]),
                 'base_branch': 'master', 'base_commit': self.bases[name], 'feature_branch': 'feature/' + WORK,
                 'allowed_paths': ['app.py', 'test_behavior.py']} for name in self.selected]
        if group:
            contract['repositories'] = rows
            contract['verification_repositories'] = []
        else:
            contract.update({k: v for k, v in rows[0].items() if k != 'repo_path'})
            contract['allowed_paths'].append(f'docs/work/{WORK}/')
        contract['handoff'] = {'dependencies': {x: [] for x in self.selected}, 'merge_order': self.selected,
                               'compatibility_check_ids': ['unit'] if len(self.selected) > 1 or edges else [],
                               'independent_reason': 'independent applications', 'partial_delivery': 'resume missing commits'}
        contract['checks'][0]['cwd'] = self.selected[0] if group else '.'
        contract['behavior_trace'][0]['implementation_paths'] = [x + '/app.py' for x in self.selected] if group else ['app.py']
        architecture = {'schema': 'megin-architecture/v1', 'work_id': WORK, 'requirements_revision': 'req-1',
                        'requirements_sha256': contract['requirements_sha256'], 'discovery_sha256': discovery_ref['sha256'],
                        'repositories': architecture_rows}
        if group:
            import impact_policy as impact
            architecture.update(schema='megin-architecture/v2', changed_contracts=[], searches=[], impact_edges=[],
                                repository_impacts=[], unresolved=[])
            def cite(name, query):
                lines = (self.repos[name] / 'app.py').read_text(encoding='utf-8').splitlines()
                number, line = next((i, line) for i, line in enumerate(lines, 1) if query in line)
                return {'repo_path': name, 'commit': self.bases[name], 'path': 'app.py', 'line': number, 'text': line}
            for name in self.selected:
                identifier = 'CONTRACT-' + name
                symbols = (terms or {}).get(name, ['def main', 'return'])
                local_symbols = [symbol for symbol in symbols if symbol in (self.repos[name] / 'app.py').read_text(encoding='utf-8')]
                architecture['changed_contracts'].append({'id': identifier, 'kind': 'internal', 'repo_path': name,
                    'description': 'provider behavior or public contract', 'symbols': symbols,
                    'source': cite(name, local_symbols[0]),
                    'symbol_sources': [{'symbol': symbol, 'source': cite(name, symbol)} for symbol in local_symbols] +
                        [{'symbol': symbol, 'source': cite(alias_repo, symbol), 'via': cite(alias_repo, upstream_term),
                          'reason': 'wrapper exposes this alias after calling the traced upstream contract'}
                         for changed, alias_repo, symbol, upstream_term in aliases or [] if changed == name]})
                for candidate, repo in self.repos.items():
                    for number, query in enumerate(symbols):
                        architecture['searches'].append({'id': identifier + '-' + candidate + '-' + str(number),
                            'contract_id': identifier, 'repo_path': candidate, 'commit': self.bases[candidate],
                            'mode': 'literal', 'query': query, 'matches': impact.search(repo, self.bases[candidate], query)})
            for changed, provider, consumer, provider_term, consumer_term in edges or []:
                architecture['impact_edges'].append({'contract_id': 'CONTRACT-' + changed,
                    'provider': cite(provider, provider_term), 'consumer': cite(consumer, consumer_term),
                    'reason': 'consumer imports or forwards this source-backed contract', 'check_ids': ['unit']})
            reached = impact.reachability({x['id']: x for x in architecture['changed_contracts']}, architecture['impact_edges'])
            for name in self.repos:
                identifiers = [identifier for identifier, candidates in reached.items() if name in candidates]
                architecture['repository_impacts'].append({'repo_path': name,
                    'status': 'affected' if identifiers else 'unaffected',
                    'reason': 'independent application; same-named local function has no import or shared contract',
                    'contract_ids': identifiers,
                    'search_ids': [x['id'] for x in architecture['searches'] if x['repo_path'] == name]})
                if identifiers and name not in self.selected:
                    contract['verification_repositories'].append({'repo_path': name, 'base_commit': self.bases[name], 'check_ids': ['unit']})
            self.f.records.update(self.f.prefix + f'impact-confirmation-{i}.json' for i in range(4))
        contract['architecture_ref'] = self.f.write('architecture.json', architecture)
        for name in ('quality.json', 'delivery.json', 'delivery-gate.json', 'writer.md', 'check.log', 'acceptance.md', 'receipt.json'):
            self.f.records.add(self.f.prefix + name)
        contract['process_records'] = sorted(self.f.records)
        self.contract = contract
        self.save_contract()
        self.set_phase('implementation')
        self.f.approve()

    def save_contract(self):
        workflow.save_json(self.work / 'plan-1/quality-contract.json', self.contract)

    def set_phase(self, phase, status='active'):
        fields = {'schema': workflow.schemas(self.group)[0], 'work_id': WORK, 'plan_version': 'plan-1',
                  'requirements_revision': 'req-1', 'delivery_mode': 'feature_handoff', 'phase': phase, 'status': status,
                  'quality_ref': self.contract['quality_ref'], 'delivery_ref': self.contract['delivery_ref']}
        if self.group:
            fields['repositories'] = ','.join(self.selected)
        else:
            for key in ('base_branch', 'base_commit', 'feature_branch', 'remote_name', 'remote_url'):
                fields[key] = self.contract[key]
        (self.work / 'workflow.md').write_text('# Workflow\n\n' + '\n'.join(f'- {k}: {v}' for k, v in fields.items()) + '\n', encoding='utf-8')

    def implement(self, verdict='APPROVED'):
        workflow.claim(self.root, WORK, 'writer', self.group)
        workflow.prepare(self.root, WORK, 'writer', self.group)
        for name in self.selected:
            (self.repos[name] / 'app.py').write_text('def main():\n    return "accepted"\n', encoding='utf-8')
        self.evidence(verdict)

    def evidence(self, verdict='APPROVED'):
        f = self.f
        digest = workflow.snapshot(self.root, WORK, self.group)['product_sha256']
        f.snapshot = digest
        evidence = f.evidence
        evidence.update(schema=workflow.schemas(self.group)[2], work_id=WORK, plan_version='plan-1', snapshot=digest,
                        sources=[])
        evidence['writer'] = {'context': 'writer', 'snapshot': digest,
                              'source': f.raw('writer.md', {'context': '- context: writer', 'snapshot': '- snapshot: ' + digest})}
        check = self.contract['checks'][0]
        output = f.raw('check.log', {'command': 'Command: ' + check['command'], 'cwd': 'Working directory: ' + check['cwd'],
                                   'exit_code': 'Exit code: 0', 'counts': 'Tests: 1 executed, 0 failed, 0 skipped'})
        output.update(line=4, text='Tests: 1 executed, 0 failed, 0 skipped')
        evidence['checks'] = [{'id': 'unit', 'snapshot': digest, 'status': 'passed', 'exit_code': 0,
                               'executed': 1, 'failed': 0, 'skipped': 0, 'output': output}]
        for label in ('red', 'green'):
            run = evidence['tdd_cycles'][0][label]
            run['cwd'] = check['cwd']
            run['test_path'] = self.selected[0] + '/test_behavior.py' if self.group else 'test_behavior.py'
            claims = {'command': 'Command: ' + run['command'], 'cwd': 'Working directory: ' + run['cwd'],
                      'exit_code': f'Exit code: {run["exit_code"]}',
                      'counts': f'Tests: {run["executed"]} executed, {run["failed"]} failed, 0 skipped',
                      'test_sha256': 'Test SHA-256: ' + run['test_sha256'], 'sequence': f'Sequence: {run["sequence"]}'}
            if label == 'red':
                claims['assertion'] = self.contract['behavior_trace'][0]['assertion']
            run['output'] = f.raw(label + '.log', claims)
        if self.group:
            self.confirm_impact()
        if not evidence['review_history']:
            f.review(verdict)
        self.save_evidence()

    def save_evidence(self):
        workflow.save_json(self.root / self.contract['quality_ref'], self.f.evidence)

    def confirm_impact(self):
        import impact_policy as impact
        architecture = policy.read_json(self.root / self.contract['architecture_ref']['path'])
        _, _, repos, records = workflow.load_contract(self.root, WORK, True)
        summary = impact.diff_summary(self.root, WORK, self.contract, repos, records)
        changes = []
        for name, paths in summary['changed_paths'].items():
            for path in paths:
                identifiers = [x['id'] for x in architecture['changed_contracts'] if x['repo_path'] == name and x['source']['path'] == path]
                changes.append({'repo_path': name, 'path': path, 'kind': 'internal', 'reason': 'approved behavior implemented', 'contract_ids': identifiers})
        value = {'schema': 'megin-impact-confirmation/v1', 'work_id': WORK, 'plan_version': 'plan-1',
                 'requirements_revision': 'req-1', 'architecture_sha256': self.contract['architecture_ref']['sha256'],
                 'snapshot': self.f.snapshot, **summary, 'changes': changes,
                 'contract_ids': sorted({i for x in changes for i in x['contract_ids']}),
                 'repository_impacts': architecture['repository_impacts'], 'unresolved': []}
        value['searches'] = impact.confirmation_searches(self.root, WORK, self.contract, repos, records, value['contract_ids'])
        previous = self.f.evidence.get('impact_confirmation_ref')
        name = f'impact-confirmation-{len(self.f.evidence["review_history"])}.json'
        if previous and policy.read_json(self.root / previous['path']).get('snapshot') == self.f.snapshot:
            name = Path(previous['path']).name
        self.f.evidence['impact_confirmation_ref'] = self.f.write(name, value)
        self.save_evidence()

    def accept(self):
        self.set_phase('verification')
        result = workflow.check(self.root, WORK, 'acceptance', self.group)
        if not result['ok']:
            raise AssertionError(result['reasons'])
        value = {'actor_kind': 'human', 'work_id': WORK, 'version': 'acceptance-1',
                 'snapshot': self.f.snapshot, 'verdict': 'ACCEPTED', 'response': '接受本次成果',
                 'timestamp': '2026-10-13T12:00:00+08:00'}
        value['source'] = self.f.raw('acceptance.md', {k: f'- {k}: {value[k]}' for k in
                                    ('work_id', 'version', 'snapshot', 'verdict', 'timestamp')} |
                                    {'response': '- response: ' + json.dumps(value['response'], ensure_ascii=False)})
        self.f.evidence['acceptance'] = value
        self.save_evidence()
        self.set_phase('delivery')


class UnifiedInterfaceTests(unittest.TestCase):
    def test_standalone_bundle_exposes_group_gate(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'quality_gate.py'), '--help'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--group-root', result.stdout)
        self.assertIn('validate-record', result.stdout)


class UnifiedWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def make(self, **kwargs):
        return WorkFixture(self.temp, **kwargs)

    def test_single_repo_feature_delivery_and_historical_receipt(self):
        f = self.make()
        f.implement()
        self.assertTrue(quality.check(f.root, WORK, 'review')['ok'])
        f.accept()
        result = workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(git(f.root, 'rev-parse', 'master'), f.bases['.'])
        self.assertEqual(git(f.root, 'branch', '--show-current'), 'feature/' + WORK)
        self.assertFalse(locks.repo_lock(f.root).exists())
        from delivery_receipt import export_receipt
        receipt = export_receipt(f.root, WORK)
        self.assertEqual(receipt['schema'], 'megin-repo-delivery-receipt/v2')
        (f.root / 'app.py').write_text('unrelated later work\n', encoding='utf-8')
        self.assertEqual(export_receipt(f.root, WORK), receipt)

    def test_group_one_and_multiple_targets_leave_unmodified_repo_alone(self):
        for count in (1, 2):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temporary:
                f = WorkFixture(Path(temporary), group=True, count=count, unmodified=True)
                f.implement()
                f.accept()
                result = workflow.deliver(f.root, WORK, 'writer', True)
                self.assertEqual(len(result['repositories']), count)
                self.assertEqual(git(f.repos['unmodified'], 'branch', '--show-current'), 'master')
                self.assertNotIn('feature/', git(f.repos['unmodified'], 'branch', '--list'))
                self.assertFalse((f.root / '.megin/workspace.lock.json').exists())
                self.assertEqual(workflow.export_receipt(f.root, WORK, True)['schema'], 'megin-delivery-receipt/v2')
                for name in f.selected:
                    self.assertEqual(git(f.repos[name], 'rev-parse', 'master'), f.bases[name])

    def test_missing_approval_and_architecture_block_claim(self):
        f = self.make()
        architecture = f.root / f.contract['architecture_ref']['path']
        old = architecture.read_bytes()
        architecture.unlink()
        with self.assertRaisesRegex(ValueError, 'evidence missing'):
            workflow.claim(f.root, WORK, 'writer')
        architecture.write_bytes(old)
        (f.root / f.contract['approval_ref']).unlink()
        with self.assertRaises((ValueError, OSError)):
            workflow.claim(f.root, WORK, 'writer')
        self.assertFalse(locks.repo_lock(f.root).exists())

    def test_no_acceptance_cannot_stage_or_commit(self):
        f = self.make()
        f.implement()
        f.set_phase('delivery')
        with self.assertRaisesRegex(ValueError, 'human acceptance'):
            workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), f.bases['.'])
        self.assertEqual(git(f.root, 'diff', '--cached', '--name-only'), '')

    def test_review_self_reuse_stale_and_invalid_tdd_are_blocked(self):
        f = self.make()
        f.implement()
        f.set_phase('verification')
        pristine = copy.deepcopy(f.f.evidence)
        for mutate, message in ((lambda e: e['writer'].update(context='reviewer-0'), 'writer'),
                                (lambda e: e.update(snapshot='0' * 64), 'snapshot'),
                                (lambda e: e['tdd_cycles'][0]['red'].update(failure_kind='setup'), 'red')):
            f.f.evidence = copy.deepcopy(pristine)
            mutate(f.f.evidence)
            f.save_evidence()
            report = workflow.check(f.root, WORK, 'acceptance')
            self.assertFalse(report['ok'], (message, report))

    def test_remote_master_advance_blocks_all_group_branches(self):
        f = self.make(group=True, count=2)
        workflow.claim(f.root, WORK, 'writer', True)
        repo = f.repos[f.selected[-1]]
        git(repo, 'commit', '--allow-empty', '-m', 'remote advance')
        git(repo, 'push', 'origin', 'master')
        with self.assertRaisesRegex(ValueError, 'remote master changed'):
            workflow.prepare(f.root, WORK, 'writer', True)
        for repo in f.repos.values():
            self.assertNotIn('feature/', git(repo, 'branch', '--list'))

    def test_remote_drift_after_acceptance_blocks_commit(self):
        f = self.make()
        f.implement()
        f.accept()
        upstream = self.temp / 'upstream'
        git(self.temp, 'clone', str(f.remotes['.']), str(upstream))
        git(upstream, 'config', 'user.name', 'upstream')
        git(upstream, 'config', 'user.email', 'upstream@example.invalid')
        git(upstream, 'commit', '--allow-empty', '-m', 'advance')
        git(upstream, 'push', 'origin', 'master')
        with self.assertRaisesRegex(ValueError, 'remote master changed'):
            workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), f.bases['.'])

    def test_only_main_is_not_a_master_fallback(self):
        f = self.make()
        git(f.root, 'push', 'origin', 'master:main')
        git(f.remotes['.'], 'symbolic-ref', 'HEAD', 'refs/heads/main')
        git(f.root, 'push', 'origin', '--delete', 'master')
        with self.assertRaisesRegex(ValueError, 'master unavailable'):
            context.resolve(f.root)

    def test_fetch_race_does_not_create_branch(self):
        f = self.make()
        workflow.claim(f.root, WORK, 'writer')
        real_git = context.git
        def altered(repo, *args):
            return 'f' * 40 if args == ('rev-parse', 'FETCH_HEAD') else real_git(repo, *args)
        with patch.object(context, 'git', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'moved during fetch'):
                workflow.prepare(f.root, WORK, 'writer')
        self.assertNotIn('feature/', git(f.root, 'branch', '--list'))

    def test_existing_dirty_changes_are_preserved(self):
        f = self.make()
        workflow.claim(f.root, WORK, 'writer')
        (f.root / 'app.py').write_text('unrelated user work\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'existing product changes'):
            workflow.prepare(f.root, WORK, 'writer')
        self.assertEqual((f.root / 'app.py').read_text(encoding='utf-8'), 'unrelated user work\n')

    def test_common_dir_lock_blocks_other_mode_and_linked_worktree(self):
        f = self.make(group=True, count=2)
        workflow.claim(f.root, WORK, 'writer', True)
        repo = f.repos[f.selected[0]]
        other = locks.owner(repo, 'work-20261013-other', 'other', f.contract['skills_sha256'])
        with self.assertRaisesRegex(ValueError, 'another root'):
            locks.claim(repo, [{'repo': repo}], False, other)
        linked = self.temp / 'linked'
        git(repo, 'worktree', 'add', '-b', 'linked', str(linked))
        self.assertEqual(locks.repo_lock(repo), locks.repo_lock(linked))

    def test_partial_delivery_resumes_without_recreating_first_commit(self):
        f = self.make(group=True, count=2)
        f.implement()
        f.accept()
        original = context.git
        second = f.repos[f.selected[1]]
        def fail_second(repo, *args):
            if repo == second and 'commit' in args:
                raise quality.InvalidEvidence('simulated second commit failure')
            return original(repo, *args)
        with patch.object(context, 'git', side_effect=fail_second):
            with self.assertRaisesRegex(quality.InvalidEvidence, 'simulated'):
                workflow.deliver(f.root, WORK, 'writer', True)
        first = git(f.repos[f.selected[0]], 'rev-parse', 'HEAD')
        self.assertNotEqual(first, f.bases[f.selected[0]])
        self.assertTrue((f.root / '.megin/workspace.lock.json').exists())
        result = workflow.deliver(f.root, WORK, 'writer', True)
        self.assertEqual(result['repositories'][0]['feature_commit'], first)
        self.assertEqual(result['status'], 'complete')

    def test_local_master_and_tracking_ref_can_lag_live_master(self):
        f = self.make()
        local_base = f.bases['.']
        upstream = self.temp / 'upstream'
        git(self.temp, 'clone', str(f.remotes['.']), str(upstream))
        git(upstream, 'config', 'user.name', 'upstream')
        git(upstream, 'config', 'user.email', 'upstream@example.invalid')
        git(upstream, 'commit', '--allow-empty', '-m', 'new remote baseline')
        git(upstream, 'push', 'origin', 'master')
        resolved = context.resolve(f.root)
        self.assertNotEqual(resolved['base_commit'], local_base)
        self.assertEqual(git(f.root, 'rev-parse', 'origin/master'), local_base)
        git(f.root, 'fetch', '--no-tags', 'origin', 'refs/heads/master')
        f.bases['.'] = f.contract['base_commit'] = resolved['base_commit']
        f.save_contract()
        f.set_phase('implementation')
        f.f.approve()
        f.implement()
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), resolved['base_commit'])
        f.accept()
        workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'rev-parse', 'master'), local_base)

    def test_remote_selection_order_and_ambiguity(self):
        f = self.make()
        git(f.root, 'remote', 'add', 'other', str(f.remotes['.']))
        self.assertEqual(context.resolve(f.root)['source'], 'origin')
        self.assertEqual(context.resolve(f.root, explicit='other')['source'], 'explicit')
        git(f.root, 'remote', 'rename', 'origin', 'upstream')
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            context.resolve(f.root)
        workflow.save_json(f.root / '.megin/repo.json', {'schema': 'megin-repo-config/v1', 'remote': 'upstream'})
        self.assertEqual(context.resolve(f.root)['remote_name'], 'upstream')
        self.assertEqual(context.resolve(f.root, explicit='other')['remote_name'], 'other')
        (f.root / '.megin/repo.json').unlink()
        git(f.root, 'remote', 'remove', 'other')
        self.assertEqual(context.resolve(f.root)['source'], 'unique_remote')
        git(f.root, 'remote', 'remove', 'upstream')
        with self.assertRaisesRegex(ValueError, 'missing'):
            context.resolve(f.root)

    def test_wrong_branch_blocks_product_write_and_resume_preserves_changes(self):
        f = self.make()
        workflow.claim(f.root, WORK, 'writer')
        with self.assertRaisesRegex(ValueError, 'approved feature branch'):
            workflow.check_owner(f.root, WORK, 'writer')
        workflow.prepare(f.root, WORK, 'writer')
        (f.root / 'app.py').write_text('unfinished implementation\n', encoding='utf-8')
        workflow.claim(f.root, WORK, 'writer')
        workflow.check_owner(f.root, WORK, 'writer')
        self.assertEqual((f.root / 'app.py').read_text(encoding='utf-8'), 'unfinished implementation\n')
        git(f.root, 'switch', 'master')
        with self.assertRaisesRegex(ValueError, 'approved feature branch'):
            workflow.check_owner(f.root, WORK, 'writer')

    def test_exhausted_corrections_block_writes_and_cannot_reset_on_resume(self):
        f = self.make()
        f.implement('CHANGES_REQUESTED')
        for _ in range(3):
            f.f.review('CHANGES_REQUESTED')
        f.save_evidence()
        with self.assertRaisesRegex(ValueError, 'three corrections exhausted'):
            workflow.check_owner(f.root, WORK, 'writer')
        f.f.evidence['review_history'] = f.f.evidence['review_history'][:1]
        f.save_evidence()
        with self.assertRaisesRegex(ValueError, 'discard or skip'):
            workflow.claim(f.root, WORK, 'writer')

    def test_correction_uses_fresh_context_and_can_stop_early(self):
        f = self.make(group=True)
        f.implement('CHANGES_REQUESTED')
        f.f.review('APPROVED')
        f.save_evidence()
        f.accept()
        self.assertEqual(len(f.f.evidence['review_history']), 2)
        self.assertEqual(workflow.deliver(f.root, WORK, 'writer', True)['status'], 'complete')

    def test_bad_review_cannot_stage_even_with_human_acceptance(self):
        f = self.make()
        f.implement()
        f.accept()
        f.f.evidence['review']['context'] = 'writer'
        f.save_evidence()
        with self.assertRaisesRegex(ValueError, 'review'):
            workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'diff', '--cached', '--name-only'), '')

    def test_untracked_installed_skills_are_governance_not_product_changes(self):
        f = self.make()
        git(f.root, 'rm', '-r', '--cached', '.agents')
        git(f.root, 'commit', '-m', 'leave installed Skills untracked')
        git(f.root, 'push', 'origin', 'master')
        f.contract['base_commit'] = f.bases['.'] = git(f.root, 'rev-parse', 'HEAD')
        f.save_contract()
        f.set_phase('implementation')
        f.f.approve()
        f.implement()
        f.accept()
        self.assertEqual(workflow.deliver(f.root, WORK, 'writer')['status'], 'complete')
        self.assertEqual(git(f.root, 'ls-tree', '--name-only', 'HEAD', '.agents'), '')

    def test_failed_group_claim_releases_only_new_locks(self):
        f = self.make(group=True, count=2)
        repo = f.repos[f.selected[-1]]
        other = locks.owner(repo, 'work-20261013-other', 'other', f.contract['skills_sha256'])
        locks.claim(repo, [{'repo': repo}], False, other)
        with self.assertRaisesRegex(ValueError, 'another root'):
            workflow.claim(f.root, WORK, 'writer', True)
        self.assertFalse((f.root / '.megin/workspace.lock.json').exists())
        self.assertFalse(locks.repo_lock(f.repos[f.selected[0]]).exists())
        self.assertTrue(locks.repo_lock(repo).exists())

    def test_upgrade_blocks_unfinished_work_and_preserves_other_skills(self):
        from install_skills import install
        f = self.make()
        with self.assertRaisesRegex(ValueError, 'unfinished work'):
            install(ROOT / '.agents/skills', f.root, check_only=True)
        f.set_phase('delivery', 'complete')
        extra = f.root / '.agents/skills/custom/keep.txt'
        extra.parent.mkdir()
        extra.write_text('user skill\n', encoding='utf-8')
        result = install(ROOT / '.agents/skills', f.root)
        self.assertEqual(result['skill_count'], 13)
        self.assertEqual(extra.read_text(encoding='utf-8'), 'user skill\n')
        self.assertTrue((Path(result['backup']) / 'megin/SKILL.md').is_file())

    def test_crash_after_commit_before_record_is_recovered(self):
        f = self.make(group=True, count=2)
        f.implement()
        f.accept()
        first_repo = f.repos[f.selected[0]]
        original_save = workflow.save_json
        def fail_save(path, value):
            if path == f.root / f.contract['delivery_ref'] and value.get('repositories'):
                raise OSError('simulated crash after commit')
            return original_save(path, value)
        with patch.object(workflow, 'save_json', side_effect=fail_save):
            with self.assertRaisesRegex(OSError, 'after commit'):
                workflow.deliver(f.root, WORK, 'writer', True)
        first = git(first_repo, 'rev-parse', 'HEAD')
        self.assertNotEqual(first, f.bases[f.selected[0]])
        result = workflow.deliver(f.root, WORK, 'writer', True)
        self.assertEqual(result['repositories'][0]['feature_commit'], first)

    def test_group_root_boundaries_and_all_repo_discovery(self):
        f = self.make(group=True, count=1, unmodified=True)
        nested = f.root / 'ordinary/nested'
        nested.mkdir(parents=True)
        git(nested, 'init', '-b', 'master')
        self.assertEqual(set(context.repositories(f.root)), set(f.repos))
        with self.assertRaises(ValueError):
            context.group_root(f.repos[f.selected[0]])
        data = policy.read_json(f.root / f.contract['discovery_ref']['path'])
        data['repositories'] = data['repositories'][:1]
        ref = f.f.write('discovery.json', data)
        f.contract.update(discovery_ref=ref, discovery_sha256=ref['sha256'])
        f.save_contract()
        f.f.approve()
        with self.assertRaisesRegex(ValueError, 'cover every'):
            workflow.claim(f.root, WORK, 'writer', True)

    def test_missing_quality_summary_cannot_bypass_retained_review_attempts(self):
        f = self.make()
        f.implement('CHANGES_REQUESTED')
        for _ in range(3):
            f.f.review('CHANGES_REQUESTED')
        f.save_evidence()
        path = f.root / f.contract['quality_ref']
        path.rename(path.with_suffix('.preserved'))
        for action in (workflow.claim, workflow.check_owner):
            with self.assertRaisesRegex(ValueError, 'quality summary missing'):
                action(f.root, WORK, 'writer')
        self.assertEqual(len(list((f.work / 'evidence').glob('review-attempt-*.json'))), 4)

    def test_group_tdd_must_use_a_selected_repo_test(self):
        f = self.make(group=True)
        f.implement()
        shutil.copyfile(f.repos[f.selected[0]] / 'test_behavior.py', f.root / 'test_behavior.py')
        for run in ('red', 'green'):
            f.f.evidence['tdd_cycles'][0][run]['test_path'] = 'test_behavior.py'
        f.save_evidence()
        f.set_phase('verification')
        report = workflow.check(f.root, WORK, 'acceptance', True)
        self.assertFalse(report['ok'])
        self.assertIn('selected Repo', str(report['reasons']))

    def test_remote_identity_preserves_ssh_user_and_home_relative_path(self):
        alice = context.remote_url('alice@example.invalid:repo.git')
        bob = context.remote_url('bob@example.invalid:repo.git')
        absolute = context.remote_url('ssh://alice@example.invalid/repo.git')
        self.assertNotEqual(alice, bob)
        self.assertNotEqual(alice, absolute)
        self.assertNotEqual(context.remote_url('ssh://alice@example.invalid/repo.git'),
                            context.remote_url('ssh://bob@example.invalid/repo.git'))
        self.assertEqual(context.remote_url('https://token:secret@example.invalid/repo.git?token=hidden'),
                         'https://example.invalid/repo.git')

    def test_actual_upstream_source_requires_reexploration_before_claim(self):
        from source_baseline import scan_commit
        f = self.make()
        upstream = self.temp / 'upstream'
        git(self.temp, 'clone', str(f.remotes['.']), str(upstream))
        git(upstream, 'config', 'user.name', 'upstream')
        git(upstream, 'config', 'user.email', 'upstream@example.invalid')
        original = (f.root / 'app.py').read_text(encoding='utf-8')
        (upstream / 'app.py').write_text(original + '\ndef new_endpoint():\n    return "upstream"\n', encoding='utf-8')
        git(upstream, 'add', 'app.py')
        git(upstream, 'commit', '-m', 'new upstream functionality')
        git(upstream, 'push', 'origin', 'master')
        resolved = context.resolve(f.root)
        destination = self.temp / 'exploration'
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'unified_workflow.py'), 'baseline',
                                 '--repo', str(f.root), '--destination', str(destination)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads(result.stdout)
        self.assertIn('new_endpoint', (destination / 'app.py').read_text(encoding='utf-8'))
        self.assertEqual((f.root / 'app.py').read_text(encoding='utf-8'), original)
        f.contract['base_commit'] = resolved['base_commit']
        f.save_contract()
        f.set_phase('implementation')
        f.f.approve()
        with self.assertRaisesRegex(ValueError, 'architecture baseline'):
            workflow.claim(f.root, WORK, 'writer')
        discovery = policy.read_json(f.root / f.contract['discovery_ref']['path'])
        row = discovery['repositories'][0]
        row['scan_ref'] = f.f.write('scan-native.json', inventory)
        report = row['functional_report']
        report['snapshot_id'] = inventory['snapshot_id']
        report['coverage'] = [{'path': x['path'], 'sha256': x['sha256'], 'status': 'checked',
                               'reason': 'explored pinned master', 'function_ids': ['FUNC-MAIN']} for x in inventory['included']]
        report['entrypoints'] = [{'entrypoint_id': x['entrypoint_id'], 'status': 'checked',
                                 'reason': 'traced new upstream entrypoint', 'function_ids': ['FUNC-MAIN']}
                                for x in inventory['entrypoint_candidates']]
        ref = f.f.write('discovery.json', discovery)
        f.contract.update(discovery_ref=ref, discovery_sha256=ref['sha256'])
        architecture = policy.read_json(f.root / f.contract['architecture_ref']['path'])
        architecture['discovery_sha256'] = ref['sha256']
        architecture['repositories'][0]['snapshot_id'] = inventory['snapshot_id']
        architecture['repositories'][0]['entrypoints'].append('app.py:new_endpoint')
        f.contract['architecture_ref'] = f.f.write('architecture.json', architecture)
        f.save_contract()
        f.f.approve()
        workflow.claim(f.root, WORK, 'writer')
        workflow.prepare(f.root, WORK, 'writer')
        workflow.check_owner(f.root, WORK, 'writer')
        self.assertIn('new_endpoint', (f.root / 'app.py').read_text(encoding='utf-8'))
        self.assertNotEqual(git(f.root, 'rev-parse', 'master'), resolved['base_commit'])

    def test_process_records_cannot_be_staged_before_human_acceptance(self):
        f = self.make()
        f.implement()
        git(f.root, 'add', f.contract['quality_ref'])
        f.set_phase('verification')
        report = workflow.check(f.root, WORK, 'acceptance')
        self.assertFalse(report['ok'])
        self.assertIn('staged before human acceptance', str(report['reasons']))

    def test_commit_hook_cannot_rewrite_accepted_tree(self):
        f = self.make()
        f.implement()
        f.accept()
        hook_root = self.temp / 'user-hooks'
        hook_root.mkdir()
        hook = hook_root / 'pre-commit'
        hook.write_text('#!/bin/sh\nprintf "hook rewrote accepted code\\n" > app.py\ngit add app.py\n', encoding='utf-8')
        hook.chmod(0o755)
        git(f.root, 'config', 'core.hooksPath', str(hook_root))
        accepted = (f.root / 'app.py').read_bytes()
        result = workflow.deliver(f.root, WORK, 'writer')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual((f.root / 'app.py').read_bytes(), accepted)
        self.assertEqual(git(f.root, 'config', 'core.hooksPath'), str(hook_root))
        self.assertNotIn('hook rewrote', git(f.root, 'show', 'HEAD:app.py'))

    def test_ignored_tdd_test_cannot_authorize_acceptance(self):
        f = self.make()
        f.implement()
        hidden = f.root / 'test_hidden.py'
        hidden.write_bytes((f.root / 'test_behavior.py').read_bytes())
        with (f.root / '.git/info/exclude').open('a', encoding='utf-8') as stream:
            stream.write('\ntest_hidden.py\n')
        for label in ('red', 'green'):
            f.f.evidence['tdd_cycles'][0][label]['test_path'] = 'test_hidden.py'
        f.save_evidence()
        f.set_phase('verification')
        report = workflow.check(f.root, WORK, 'acceptance')
        self.assertFalse(report['ok'])
        self.assertIn('accepted product snapshot', str(report['reasons']))
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), f.bases['.'])

    def test_live_completion_reads_delivered_tests_not_ignored_worktree_files(self):
        f = self.make()
        f.implement()
        f.accept()
        workflow.deliver(f.root, WORK, 'writer')
        (f.root / 'test_hidden.py').write_bytes((f.root / 'test_behavior.py').read_bytes())
        with (f.root / '.git/info/exclude').open('a', encoding='utf-8') as stream:
            stream.write('\ntest_hidden.py\n')
        for label in ('red', 'green'):
            f.f.evidence['tdd_cycles'][0][label]['test_path'] = 'test_hidden.py'
        f.save_evidence()
        report = workflow.check(f.root, WORK, 'completion')
        self.assertFalse(report['ok'])
        self.assertIn('delivered TDD test missing', str(report['reasons']))

    def test_completion_rechecks_all_remotes_but_historical_receipt_stays_valid(self):
        f = self.make(group=True, count=2)
        f.implement()
        f.accept()
        workflow.deliver(f.root, WORK, 'writer', True)
        before = workflow.export_receipt(f.root, WORK, True)
        repo = f.repos[f.selected[0]]
        git(repo, 'push', 'origin', 'HEAD:master')
        report = workflow.check(f.root, WORK, 'completion', True)
        self.assertFalse(report['ok'])
        self.assertIn('remote master changed', str(report['reasons']))
        self.assertEqual(workflow.export_receipt(f.root, WORK, True), before)

    def test_prepare_isolates_post_checkout_hooks(self):
        f = self.make()
        workflow.claim(f.root, WORK, 'writer')
        hook_root = self.temp / 'checkout-hooks'
        hook_root.mkdir()
        hook = hook_root / 'post-checkout'
        hook.write_text('#!/bin/sh\nprintf "checkout changed code\\n" > app.py\ngit add app.py\n', encoding='utf-8')
        hook.chmod(0o755)
        git(f.root, 'config', 'core.hooksPath', str(hook_root))
        original = (f.root / 'app.py').read_bytes()
        workflow.prepare(f.root, WORK, 'writer')
        self.assertEqual((f.root / 'app.py').read_bytes(), original)
        self.assertEqual(git(f.root, 'diff', '--cached', '--name-only'), '')
        self.assertEqual(git(f.root, 'config', 'core.hooksPath'), str(hook_root))
        self.assertNotIn('acceptance', f.f.evidence)

    def test_prepare_rejects_tracked_governance_drift_before_switch(self):
        f = self.make()
        metadata = f.root / '.agents/skills/megin/agents/openai.yaml'
        with metadata.open('a', encoding='utf-8') as stream:
            stream.write('\n# local installed Skills upgrade\n')
        git(f.root, 'add', '.agents')
        git(f.root, 'commit', '-m', 'local installed Skills upgrade')
        local_head = git(f.root, 'rev-parse', 'HEAD')
        approved_metadata = metadata.read_bytes()
        f.contract['skills_sha256'] = workflow.fingerprint(f.root)
        f.save_contract()
        f.f.approve()
        workflow.claim(f.root, WORK, 'writer')
        with self.assertRaisesRegex(ValueError, 'governance'):
            workflow.prepare(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), local_head)
        self.assertEqual(git(f.root, 'branch', '--show-current'), 'master')
        self.assertEqual(metadata.read_bytes(), approved_metadata)
        self.assertEqual(git(f.root, 'branch', '--list', 'feature/' + WORK), '')

    def test_group_governance_preflight_checks_all_targets_before_switch(self):
        f = self.make(group=True, count=2)
        second = f.repos[f.selected[1]]
        config = second / '.megin/local.json'
        workflow.save_json(config, {'preserve': 'local governance'})
        git(second, 'add', '.megin')
        git(second, 'commit', '-m', 'local governance')
        workflow.claim(f.root, WORK, 'writer', True)
        with self.assertRaisesRegex(ValueError, 'governance'):
            workflow.prepare(f.root, WORK, 'writer', True)
        for name in f.selected:
            self.assertEqual(git(f.repos[name], 'branch', '--show-current'), 'master')
            self.assertEqual(git(f.repos[name], 'branch', '--list', 'feature/' + WORK), '')
        self.assertEqual(policy.read_json(config), {'preserve': 'local governance'})

    def test_prepare_disables_configured_fetch_refmaps(self):
        f = self.make()
        git(f.root, 'commit', '--allow-empty', '-m', 'local-only master')
        local_master = git(f.root, 'rev-parse', 'master')
        git(f.root, 'switch', '-c', 'scratch', f.bases['.'])
        git(f.root, 'config', 'remote.origin.fetch', '+refs/heads/master:refs/heads/master')
        workflow.claim(f.root, WORK, 'writer')
        workflow.prepare(f.root, WORK, 'writer')
        self.assertEqual(git(f.root, 'rev-parse', 'master'), local_master)
        self.assertEqual(git(f.root, 'rev-parse', 'HEAD'), f.bases['.'])

    def test_baseline_disables_configured_fetch_refmaps(self):
        f = self.make()
        git(f.root, 'commit', '--allow-empty', '-m', 'local-only master')
        local_master = git(f.root, 'rev-parse', 'master')
        git(f.root, 'switch', '-c', 'scratch', f.bases['.'])
        git(f.root, 'config', 'remote.origin.fetch', '+refs/heads/master:refs/heads/master')
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'unified_workflow.py'), 'baseline',
                                 '--repo', str(f.root), '--destination', str(self.temp / 'baseline')],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(f.root, 'rev-parse', 'master'), local_master)
        self.assertEqual(git(f.root, 'branch', '--show-current'), 'scratch')
        self.assertEqual(json.loads(result.stdout)['source_commit'], f.bases['.'])


if __name__ == '__main__':
    unittest.main()
