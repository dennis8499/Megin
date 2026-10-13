"""Install the bundled Skills, refusing upgrades over unfinished workflows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
import quality_gate as q
from quality_policy import path_inside, require
from validate_skills import EXPECTED, validate
from verification_inputs import no_links
import workspace_context as context
import workspace_lock as locks
from workspace_lock import repo_lock


def check_upgrade(root, maintenance=None):
    root = Path(root).resolve()
    no_links(root)
    detected = context.detect(root)
    require(Path(detected['root']) == root, 'installation target must be a Repo or Group root')
    roots = [root]
    repos = list(context.repositories(root).values()) if detected['mode'] == 'group' else [root]
    roots.extend(repo for repo in repos if repo != root)
    for selected in roots:
        for path in (selected / 'docs/work').glob('*/workflow.md'):
            no_links(path)
            fields = q.workflow_fields(path)
            if fields.get('schema', '').startswith('megin-'):
                require(fields.get('status') == 'complete', f'unfinished work blocks upgrade: {path.parent.name}')
        path = selected / '.megin/workspace.lock.json'
        if path.exists():
            require(maintenance is not None, 'active legacy or Group lock blocks upgrade')
            locks.check(path, maintenance)
    for repo in repos:
        if repo_lock(repo).exists():
            require(maintenance is not None, 'active Repo common-dir lock blocks upgrade')
            locks.check(repo_lock(repo), maintenance)
    return root


def install(source, target, check_only=False):
    source = Path(source).resolve()
    target = check_upgrade(target)
    require(source != target / '.agents/skills', 'source and destination are the same Skills directory')
    errors = validate(source)
    require(not errors, '; '.join(errors))
    destination = path_inside(target, '.agents/skills')
    no_links(destination)
    if check_only:
        return {'ok': True, 'target': str(target), 'skill_count': len(EXPECTED)}
    detected = context.detect(target)
    group = detected['mode'] == 'group'
    repo_paths = list(context.repositories(target).values()) if group else [target]
    repos = [{'repo': repo} for repo in repo_paths]
    maintenance = locks.owner(target, 'skills-install-' + uuid.uuid4().hex, 'installer', 'maintenance')
    locks.claim(target, repos, group, maintenance)
    try:
        check_upgrade(target, maintenance)
        return _replace(source, target)
    finally:
        locks.release(target, repos, group, maintenance)


def _replace(source, target):
    destination = path_inside(target, '.agents/skills')
    destination.mkdir(parents=True, exist_ok=True)
    backup = path_inside(target, '.megin/skill-backups/' + uuid.uuid4().hex)
    no_links(backup)
    backup.mkdir(parents=True)
    # Prepare every directory before replacing any installed Skill.
    with tempfile.TemporaryDirectory(dir=target, prefix='.megin-install-') as temporary:
        staging = Path(temporary)
        for name in EXPECTED:
            no_links(destination / name)
            shutil.copytree(source / name, staging / name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        moved, installed = [], []
        try:
            for name in EXPECTED:
                existing = destination / name
                if existing.exists():
                    existing.rename(backup / name)
                    moved.append(name)
                (staging / name).rename(existing)
                installed.append(name)
        except Exception:
            for name in reversed(installed):
                # Keep the replacement for inspection rather than deleting it.
                (destination / name).rename(staging / name)
            for name in reversed(moved):
                (backup / name).rename(destination / name)
            raise
    return {'installed': True, 'target': str(target), 'skill_count': len(EXPECTED), 'backup': str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        result = install(Path(__file__).resolve().parents[2], args.target, args.check)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, q.InvalidEvidence) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
