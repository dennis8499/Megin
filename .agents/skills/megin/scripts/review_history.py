"""Append a fresh review attempt; existing attempts are never overwritten."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from quality_policy import NEW_CONTRACTS, read_json, path_inside, validate_reviews


def recover(root, work_id, contract, records, evidence):
    """Rebuild a partially saved index from retained attempts without resetting."""
    history = []
    for relative in contract['review_records']:
        path = path_inside(root, relative)
        if path.is_file():
            history.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {**evidence, 'review_history': history}
    if history:
        latest = read_json(path_inside(root, history[-1]['path']))
        result['review'] = {k: latest[k] for k in ('context', 'verdict', 'snapshot', 'source')}
    validate_reviews(root, work_id, contract, records, result, evidence.get('snapshot'), 'review', allow_exhausted=True)
    return result


def append(root, work_id, contract, records, evidence, attempt):
    if contract.get('schema') not in NEW_CONTRACTS:
        raise ValueError('append requires a native v2 or Group v4 contract')
    validate_reviews(root, work_id, contract, records, evidence, evidence.get('snapshot'), 'review')
    history = evidence.get('review_history', [])
    number = len(history)
    if number >= 4:
        raise ValueError('initial review plus three corrections already recorded')
    if history:
        previous = read_json(path_inside(root, history[-1]['path']))
        if previous['verdict'] == 'APPROVED' and previous['snapshot'] == evidence.get('snapshot'):
            raise ValueError('approved history is closed')
    target = path_inside(root, contract['review_records'][number])
    attempt = dict(attempt)
    attempt.update(schema='megin-review-attempt/v1', work_id=work_id, round=number,
                   previous_sha256=history[-1]['sha256'] if history else None,
                   requirements_revision=contract['requirements_revision'])
    raw = (json.dumps(attempt, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    ref = {'path': contract['review_records'][number], 'sha256': hashlib.sha256(raw).hexdigest()}
    proposed = {**evidence, 'review_history': history + [ref],
                'review': {k: attempt[k] for k in ('context', 'verdict', 'snapshot', 'source')}}
    validate_reviews(root, work_id, contract, records, proposed, evidence.get('snapshot'), 'review',
                     pending=(ref, attempt), allow_exhausted=True)
    with target.open('xb') as stream:
        stream.write(raw)
    return proposed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--work-id', required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--attempt', type=Path)
    action.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        from quality_gate import load_contract
        if (root / '.git').exists():
            fields, contract, records = load_contract(root, args.work_id)
        else:
            from group_quality_gate import load_group_contract
            fields, contract, _, records = load_group_contract(root, args.work_id)
        evidence = read_json(path_inside(root, fields['quality_ref']))
        result = (recover(root, args.work_id, contract, records, evidence) if args.recover else
                  append(root, args.work_id, contract, records, evidence, read_json(args.attempt)))
        # stdout is the proposed quality JSON; caller saves it to the declared
        # quality_ref. Interruption is recoverable from immutable attempt files.
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
