#!/usr/bin/env python3
"""Run the complete unittest inventory in isolated, reproducible shards."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def discover(directory: Path, pattern: str) -> dict[str, unittest.TestCase]:
    def flatten(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                yield from flatten(item)
            else:
                yield item
    loader = unittest.TestLoader()
    cases = list(flatten(loader.discover(str(directory), pattern=pattern)))
    if loader.errors:
        raise ValueError("Test discovery failed:\n" + "\n".join(loader.errors))
    counts = Counter(case.id() for case in cases)
    if not cases or any(count != 1 for count in counts.values()):
        raise ValueError("Test discovery must produce nonempty, unique unittest IDs")
    return dict(sorted((case.id(), case) for case in cases))


def shard_ids(ids: list[str], index: int, count: int) -> list[str]:
    if count < 1 or not 0 <= index < count:
        raise ValueError("Require shard-count >= 1 and 0 <= shard-index < shard-count")
    return sorted(value for value in ids
                  if int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big") % count == index)


def coverage(expected: list[str], actual: list[str]) -> dict:
    counts = Counter(actual)
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    duplicates = sorted(value for value, count in counts.items() if count != 1)
    return {"ok": not (missing or unexpected or duplicates), "missing": missing,
            "unexpected": unexpected, "duplicates": duplicates}


def validate_dependencies(selected: list[str]) -> dict:
    dependencies = {}
    if any(name.endswith("NativeV2Tests.test_v2_receipt_passes_standalone_mergereviewer") for name in selected):
        directory = Path(os.environ.get("MEGIN_TEST_MERGE_REVIEWER_SCRIPTS",
            str(ROOT.parent / "MergeReviewer/skills/merge-reviewer/scripts"))).resolve()
        if not (directory / "delivery_binding.py").is_file():
            raise ValueError("Missing legacy reviewer integration fixture. Set MEGIN_TEST_MERGE_REVIEWER_SCRIPTS "
                             "to scripts from the fixed MergeReviewer dependency in knowledge-portability.yml")
        dependencies["merge_reviewer_scripts"] = str(directory)
    return dependencies


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.starts = {}
        self.outcomes = {}

    def startTest(self, test):
        self.starts[test.id()] = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test):
        self.outcomes[test.id()] = "passed"
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.outcomes[test.id()] = "failed"
        super().addFailure(test, err)

    def addError(self, test, err):
        self.outcomes[test.id()] = "error"
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = "skipped"
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.outcomes[test.id()] = "expected_failure"
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = "unexpected_success"
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.outcomes[test.id()] = "failed"
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        self.records.append({"id": test.id(), "seconds": round(time.perf_counter() - self.starts[test.id()], 6),
                             "outcome": self.outcomes.get(test.id(), "passed")})
        super().stopTest(test)


def worker(args) -> int:
    requested = json.load(sys.stdin)
    cases = discover(args.start_directory, args.pattern)
    if not isinstance(requested, list) or len(set(requested)) != len(requested) or set(requested) - cases.keys():
        raise ValueError("Worker received duplicate or unknown unittest IDs")
    started = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(
        unittest.TestSuite(cases[name] for name in requested))
    report = {"ok": result.wasSuccessful(), "tests": result.records,
              "seconds": round(time.perf_counter() - started, 6),
              "coverage": coverage(requested, [row["id"] for row in result.records])}
    args.worker_result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] and report["coverage"]["ok"] else 1


def run(args) -> tuple[dict, int]:
    inventory = list(discover(args.start_directory, args.pattern))
    selected = shard_ids(inventory, args.shard_index, args.shard_count)
    if args.list:
        return {"schema": "megin-unittest-inventory/v1", "inventory": inventory, "selected": selected}, 0
    dependencies = validate_dependencies(selected)
    assignments = [selected[index::args.workers] for index in range(args.workers)]
    started = time.perf_counter()
    rows = []
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="megin-unittest-") as temporary:
        def launch(index, ids):
            result_path = Path(temporary) / f"worker-{index}.json"
            command = [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()),
                       "--worker-result", str(result_path), "--start-directory", str(args.start_directory),
                       "--pattern", args.pattern]
            log_path = (args.output.with_name(f"{args.output.stem}-worker-{index}.log") if args.output
                        else Path(temporary) / f"worker-{index}.log")
            # Write raw diagnostics while the child runs, including interrupted runs.
            with log_path.open("w", encoding="utf-8") as stream:
                process = subprocess.run(command, input=json.dumps(ids), text=True, encoding="utf-8",
                                         errors="replace", stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)
            sys.stderr.write(log_path.read_text(encoding="utf-8", errors="replace"))
            report = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
            return {"worker": index, "assigned": ids, "exit_code": process.returncode,
                    "log": str(log_path) if args.output else None, **report}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(launch, index, ids) for index, ids in enumerate(assignments) if ids]
            for future in as_completed(futures):
                rows.append(future.result())
    tests = [test for row in rows for test in row.get("tests", [])]
    checked = coverage(selected, [test["id"] for test in tests])
    ok = checked["ok"] and all(row.get("ok") and row["exit_code"] == 0 for row in rows)
    report = {"schema": "megin-unittest-run/v1", "ok": ok, "inventory": inventory,
              "shard_index": args.shard_index, "shard_count": args.shard_count, "selected": selected,
              "workers": sorted(rows, key=lambda row: row["worker"]), "coverage": checked, "dependencies": dependencies,
              "tests": sorted(tests, key=lambda row: row["id"]),
              "seconds": round(time.perf_counter() - started, 6)}
    return report, 0 if ok else 1


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--start-directory", type=Path, default=ROOT / "tests/quality-gates")
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--list", action="store_true", help="List stable IDs without executing tests")
    parser.add_argument("--output", type=Path, help="Write JSON results and per-worker raw logs")
    parser.add_argument("--worker-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    args.start_directory = args.start_directory.resolve()
    if args.output:
        args.output = args.output.resolve()
    try:
        if args.worker_result:
            return worker(args)
        report, code = run(args)
    except (OSError, ValueError, ImportError) as error:
        report, code = {"ok": False, "error": str(error)}, 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
