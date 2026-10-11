#!/usr/bin/env python3
"""Print current source inventory or validate a source-backed exploration report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from functional_inventory import scan, validate_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('scan', 'validate'))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--profile', choices=('target', 'framework'), default='target')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--exclude-path', action='append', default=[],
                        help='Explicit generated document excluded from source inventory; repeatable.')
    args = parser.parse_args(argv)
    try:
        inventory = scan(args.root, args.profile, tuple(args.exclude_path))
        if args.action == 'scan':
            result = inventory
        else:
            if args.report is None:
                parser.error('validate requires --report')
            result = validate_report(inventory, json.loads(args.report.read_text(encoding='utf-8')))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.action == 'scan' or result['complete'] else 1
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
