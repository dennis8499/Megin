#!/usr/bin/env python3
"""Compare Windows and Linux knowledge portability reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from knowledge_benchmark import (
    EXPECTED_FUNCTIONAL_SHA256,
    FILE_COUNT,
    MAX_SECONDS,
    PAGE_COUNT,
)
from knowledge_governance import canonical_sha256


REQUIRED_OSES = {"windows", "linux"}


def compare_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(reports)
    diagnostics: list[str] = []
    by_os: dict[str, dict[str, Any]] = {}
    maximum = 0.0
    for report in values:
        host = report.get("host") if isinstance(report, dict) else None
        os_name = host.get("os") if isinstance(host, dict) else None
        if os_name not in REQUIRED_OSES:
            diagnostics.append("report has an unsupported or missing host OS")
            continue
        if os_name in by_os:
            diagnostics.append(f"duplicate report for {os_name}")
            continue
        by_os[os_name] = report
        if report.get("schema") != "knowledge-portability-report/v1":
            diagnostics.append(f"{os_name}: invalid report schema")
        if report.get("outcome") != "passed":
            diagnostics.append(f"{os_name}: benchmark outcome is not passed")
        if report.get("file_count") != FILE_COUNT or report.get("page_count") != PAGE_COUNT:
            diagnostics.append(f"{os_name}: fixture scale drifted")
        if (
            report.get("tracked_fixture") is not True
            or report.get("total_fixture_files") != FILE_COUNT
            or report.get("source_file_count") != FILE_COUNT - (PAGE_COUNT * 2) - 2
        ):
            diagnostics.append(f"{os_name}: fixture is not the reviewed tracked-file shape")
        functional = report.get("functional")
        functional_sha = report.get("functional_sha256")
        if not isinstance(functional, dict) or canonical_sha256(functional) != functional_sha:
            diagnostics.append(f"{os_name}: functional payload hash is invalid")
        if functional_sha != EXPECTED_FUNCTIONAL_SHA256:
            diagnostics.append(f"{os_name}: functional oracle differs")
        warm_query_sha = report.get("warm_queries_sha256")
        cold_query_sha = report.get("cold_queries_sha256")
        functional_queries = functional.get("queries") if isinstance(functional, dict) else None
        if (
            not isinstance(warm_query_sha, str)
            or len(warm_query_sha) != 64
            or not isinstance(functional_queries, list)
            or canonical_sha256(functional_queries) != warm_query_sha
        ):
            diagnostics.append(f"{os_name}: warm query hash is invalid")
        if not isinstance(cold_query_sha, str) or len(cold_query_sha) != 64:
            diagnostics.append(f"{os_name}: cold query hash is invalid")
        elif cold_query_sha != warm_query_sha:
            diagnostics.append(f"{os_name}: cold/warm query hashes differ")
        durations = report.get("durations_seconds")
        if not isinstance(durations, dict):
            diagnostics.append(f"{os_name}: durations are missing")
            continue
        warm_queries = durations.get("queries")
        cold_queries = durations.get("cold_queries")
        if not isinstance(warm_queries, list) or len(warm_queries) != 5:
            diagnostics.append(f"{os_name}: warm query durations are missing or invalid")
            continue
        if not isinstance(cold_queries, list) or len(cold_queries) != 5:
            diagnostics.append(f"{os_name}: cold query durations are missing or invalid")
            continue
        fixture_setup = durations.get("fixture_setup")
        if (
            isinstance(fixture_setup, bool)
            or not isinstance(fixture_setup, (int, float))
            or fixture_setup < 0
        ):
            diagnostics.append(f"{os_name}: fixture setup duration is missing or invalid")
        timed = [*cold_queries, *warm_queries, durations.get("index_candidate")]
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            for value in timed
        ):
            diagnostics.append(f"{os_name}: query or index durations are invalid")
            continue
        maximum = max(maximum, *(float(value) for value in timed))
        if any(float(value) > MAX_SECONDS for value in timed):
            diagnostics.append(f"{os_name}: an operation exceeded {MAX_SECONDS:.3f}s")

    missing = REQUIRED_OSES - set(by_os)
    if missing:
        diagnostics.append(f"missing OS reports: {','.join(sorted(missing))}")
    hashes = {
        report.get("functional_sha256")
        for report in by_os.values()
        if isinstance(report.get("functional_sha256"), str)
    }
    if len(hashes) > 1:
        diagnostics.append("functional results differ across operating systems")
    return {
        "schema": "knowledge-portability-comparison/v1",
        "outcome": "passed" if not diagnostics else "failed",
        "oses": sorted(by_os),
        "functional_sha256": next(iter(hashes), None),
        "max_observed_seconds": maximum,
        "diagnostics": diagnostics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = sorted(args.root.rglob("knowledge-portability-*.json"))
    reports: list[dict[str, Any]] = []
    try:
        for path in paths:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"report is not an object: {path}")
            reports.append(value)
        comparison = compare_reports(reports)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        comparison = {
            "schema": "knowledge-portability-comparison/v1",
            "outcome": "failed",
            "oses": [],
            "functional_sha256": None,
            "max_observed_seconds": 0.0,
            "diagnostics": [str(exc)],
        }
    print(json.dumps(comparison, ensure_ascii=False, sort_keys=True))
    return 0 if comparison["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
