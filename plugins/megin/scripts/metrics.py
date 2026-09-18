#!/usr/bin/env python3
"""Record and summarize the fixed Megin v3 efficiency comparison."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASEBOOK = ROOT / "benchmarks" / "v3-cases.json"


def load_casebook() -> dict[str, Any]:
    return json.loads(CASEBOOK.read_text(encoding="utf-8"))


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def cmd_record(args: argparse.Namespace) -> int:
    casebook = load_casebook()
    task_ids = {item["id"] for item in casebook["fixed_tasks"]}
    if args.task not in task_ids:
        raise SystemExit(f"unknown fixed task: {args.task}")
    if args.method not in casebook["methods"]:
        raise SystemExit(f"unknown comparison method: {args.method}")
    record = {
        "schema": "megin-benchmark-record/v1", "task": args.task, "method": args.method, "run": args.run,
        "acceptance_passed": args.acceptance_passed, "deviations": args.deviations,
        "rework_count": args.rework_count, "regression_count": args.regression_count,
        "human_minutes": args.human_minutes, "repeat_questions": args.repeat_questions,
        "elapsed_minutes": args.elapsed_minutes, "test_reruns": args.test_reruns,
        "token_usage": args.token_usage, "notes": args.notes or "",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 3) if values else None


def cmd_report(args: argparse.Namespace) -> int:
    records = load_records(args.input)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("method")), []).append(record)
    methods: dict[str, Any] = {}
    for method, items in sorted(grouped.items()):
        passed = sum(1 for item in items if item.get("acceptance_passed"))
        methods[method] = {
            "runs": len(items),
            "acceptance_pass_rate": round(passed / len(items), 3) if items else None,
            "human_minutes_mean": mean([float(item["human_minutes"]) for item in items if item.get("human_minutes") is not None]),
            "repeat_questions_mean": mean([float(item["repeat_questions"]) for item in items if item.get("repeat_questions") is not None]),
            "rework_mean": mean([float(item["rework_count"]) for item in items if item.get("rework_count") is not None]),
            "regressions_mean": mean([float(item["regression_count"]) for item in items if item.get("regression_count") is not None]),
            "elapsed_minutes_mean": mean([float(item["elapsed_minutes"]) for item in items if item.get("elapsed_minutes") is not None]),
            "test_reruns_mean": mean([float(item["test_reruns"]) for item in items if item.get("test_reruns") is not None]),
            "token_usage": "unavailable" if any(item.get("token_usage") in (None, "unavailable") for item in items) else sum(float(item["token_usage"]) for item in items),
        }
    report = {"schema": "megin-benchmark-report/v1", "casebook": casebook_digest(), "records": len(records), "methods": methods}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def casebook_digest() -> str:
    import hashlib
    return hashlib.sha256(CASEBOOK.read_bytes()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Megin v3 benchmark metrics")
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--task", required=True)
    record.add_argument("--method", required=True)
    record.add_argument("--run", type=int, required=True)
    record.add_argument("--acceptance-passed", action="store_true")
    record.add_argument("--deviations", type=int, default=0)
    record.add_argument("--rework-count", type=int, default=0)
    record.add_argument("--regression-count", type=int, default=0)
    record.add_argument("--human-minutes", type=float)
    record.add_argument("--repeat-questions", type=int)
    record.add_argument("--elapsed-minutes", type=float)
    record.add_argument("--test-reruns", type=int)
    record.add_argument("--token-usage", type=float)
    record.add_argument("--notes")
    report = sub.add_parser("report")
    report.add_argument("--input", type=Path, required=True)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(cmd_record(args) if args.command == "record" else cmd_report(args))
