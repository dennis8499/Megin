#!/usr/bin/env python3
"""Measure deterministic Top-5 retrieval and source-safety behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from knowledge_query import KnowledgeError, query_repository


CORPUS_SCHEMA = "search-quality-cases/v1"
REPORT_SCHEMA = "knowledge-search-quality/v1"
CASE_ID_RE = re.compile(r"^SQ-[0-9]{3}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STAGES = frozenset({"requirements", "planning", "implementation", "bug"})
REQUIRED_CATEGORIES = frozenset({"zh", "en", "mixed", "exact-id", "no-valid-source"})


class SearchQualityError(RuntimeError):
    pass


def _normalized_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SearchQualityError("source path is not normalized")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SearchQualityError("source path is not normalized")
    return path.as_posix()


def _derived_query(case_id: str) -> str:
    return hashlib.sha256(f"{case_id}:no-valid-source".encode("ascii")).hexdigest()


def _load_corpus(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        corpus = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SearchQualityError("search corpus is unavailable or invalid") from exc
    if not isinstance(corpus, dict) or corpus.get("schema") != CORPUS_SCHEMA:
        raise SearchQualityError("search corpus schema is invalid")
    minimum_hit_rate = corpus.get("minimum_top5_hit_rate")
    if (
        not isinstance(minimum_hit_rate, (int, float))
        or isinstance(minimum_hit_rate, bool)
        or not 0.0 <= minimum_hit_rate <= 1.0
    ):
        raise SearchQualityError("search corpus Top-5 baseline is invalid")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or len(cases) < 20:
        raise SearchQualityError("search corpus requires at least 20 cases")
    identifiers = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if (
        len(identifiers) != len(cases)
        or len(set(identifiers)) != len(identifiers)
        or any(not isinstance(value, str) or not CASE_ID_RE.fullmatch(value) for value in identifiers)
    ):
        raise SearchQualityError("search corpus case IDs are invalid")
    categories = {item.get("category") for item in cases}
    if not REQUIRED_CATEGORIES <= categories:
        raise SearchQualityError("search corpus lacks a required category")
    return corpus, raw


def _validated_sources(repo: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sources = case.get("expected_sources")
    if not isinstance(raw_sources, list):
        raise SearchQualityError("expected_sources must be an array")
    no_source = case.get("category") == "no-valid-source"
    if no_source != (not raw_sources):
        raise SearchQualityError("only no-valid-source cases may omit expected sources")
    validated: list[dict[str, Any]] = []
    for source in raw_sources:
        if not isinstance(source, dict) or set(source) != {"path", "sha256", "locator"}:
            raise SearchQualityError("expected source binding is not closed")
        relative = _normalized_path(source["path"])
        digest = source["sha256"]
        locator = source["locator"]
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise SearchQualityError("expected source digest is invalid")
        if not isinstance(locator, dict) or set(locator) != {"start_line", "end_line"}:
            raise SearchQualityError("expected source locator is invalid")
        start_line = locator["start_line"]
        end_line = locator["end_line"]
        if (
            not isinstance(start_line, int)
            or isinstance(start_line, bool)
            or not isinstance(end_line, int)
            or isinstance(end_line, bool)
            or start_line < 1
            or end_line < start_line
        ):
            raise SearchQualityError("expected source locator is invalid")
        path = repo / Path(*relative.split("/"))
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SearchQualityError("expected source is unavailable") from exc
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SearchQualityError("expected source hash drifted")
        if end_line > len(raw.decode("utf-8").splitlines()):
            raise SearchQualityError("expected source locator is outside the file")
        validated.append(
            {
                "path": relative,
                "sha256": digest,
                "locator": {"start_line": start_line, "end_line": end_line},
            }
        )
    return validated


def _provenance(repo: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    mapping: dict[tuple[str, str], list[dict[str, Any]]] = {}
    sidecars = repo / "docs" / "knowledge" / "meta" / "pages"
    if not sidecars.is_dir():
        return mapping
    for path in sorted(sidecars.glob("*.json"), key=lambda item: item.as_posix().encode("utf-8")):
        try:
            page = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(page, dict) or not isinstance(page.get("content_path"), str):
            continue
        for claim in page.get("claims", []):
            if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str):
                continue
            refs = claim.get("source_refs")
            if isinstance(refs, list):
                mapping[(page["content_path"], claim["claim_id"])] = [
                    ref for ref in refs if isinstance(ref, dict)
                ]
    return mapping


def _observed_sources(
    results: Iterable[dict[str, Any]],
    provenance: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for result in results:
        path = result.get("path")
        if not isinstance(path, str):
            continue
        start = result.get("start_line")
        end = result.get("end_line", start)
        if isinstance(start, int) and isinstance(end, int):
            observed.append(
                {"path": path, "locator": {"start_line": start, "end_line": end}}
            )
        claim_id = result.get("claim_id")
        if isinstance(claim_id, str):
            observed.extend(provenance.get((path, claim_id), []))
    return observed


def _overlaps(left: dict[str, int], right: dict[str, int]) -> bool:
    return left["start_line"] <= right["end_line"] and right["start_line"] <= left["end_line"]


def _source_hit(expected: dict[str, Any], observed: Iterable[dict[str, Any]]) -> bool:
    return any(
        item.get("path") == expected["path"]
        and isinstance(item.get("locator"), dict)
        and _overlaps(expected["locator"], item["locator"])
        for item in observed
    )


def measure_repository(repo_value: str | Path, corpus_value: str | Path) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    corpus_path = Path(corpus_value).resolve()
    if not repo.is_dir():
        raise SearchQualityError("repository root is unavailable")
    corpus, corpus_raw = _load_corpus(corpus_path)
    provenance = _provenance(repo)
    case_reports: list[dict[str, Any]] = []
    hits = 0
    retrieval_cases = 0
    exclusion_passed = True
    no_source_passed = True

    for case in corpus["cases"]:
        if not isinstance(case, dict):
            raise SearchQualityError("search corpus case is invalid")
        if set(case) != {
            "case_id",
            "category",
            "stage",
            "query",
            "query_derivation",
            "expected_sources",
            "excluded_paths",
        }:
            raise SearchQualityError("search corpus case is not closed")
        stage = case["stage"]
        if stage not in ALLOWED_STAGES:
            raise SearchQualityError("search corpus stage is invalid")
        if not isinstance(case["excluded_paths"], list):
            raise SearchQualityError("excluded_paths must be an array")
        excluded = {_normalized_path(value) for value in case["excluded_paths"]}
        expected = _validated_sources(repo, case)
        if case["query_derivation"] == "sha256-case-id":
            if case["query"] is not None or case["category"] != "no-valid-source":
                raise SearchQualityError("derived query contract is invalid")
            query = _derived_query(case["case_id"])
        elif case["query_derivation"] is None:
            query = case["query"]
            if not isinstance(query, str) or not query.strip():
                raise SearchQualityError("search query is invalid")
        else:
            raise SearchQualityError("query derivation is unsupported")

        context = query_repository(str(repo), stage=stage, query=query)
        results = context.get("results", [])
        if not isinstance(results, list):
            raise SearchQualityError("query result contract is invalid")
        observed = _observed_sources(results, provenance)
        excluded_clean = not any(item.get("path") in excluded for item in observed)
        exclusion_passed = exclusion_passed and excluded_clean
        no_source_case = case["category"] == "no-valid-source"
        if no_source_case:
            empty = len(results) == 0
            no_source_passed = no_source_passed and empty
            hit: bool | None = None
        else:
            retrieval_cases += 1
            hit = any(_source_hit(source, observed) for source in expected)
            hits += int(hit)
            empty = False
        case_reports.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "stage": stage,
                "top5_hit": hit,
                "expected_sources": [
                    {"path": item["path"], "locator": item["locator"]}
                    for item in expected
                ],
                "observed_paths": [
                    item["path"] for item in results if isinstance(item, dict) and isinstance(item.get("path"), str)
                ],
                "excluded_source_clean": excluded_clean,
                "no_valid_source_passed": empty if no_source_case else None,
            }
        )

    source_safety_passed = exclusion_passed and no_source_passed
    hit_rate = round(hits / retrieval_cases, 6) if retrieval_cases else None
    minimum_hit_rate = float(corpus["minimum_top5_hit_rate"])
    baseline_passed = hit_rate is not None and hit_rate >= minimum_hit_rate
    all_gates_passed = source_safety_passed and baseline_passed
    return {
        "schema": REPORT_SCHEMA,
        "outcome": "passed" if all_gates_passed else "failed",
        "corpus_sha256": hashlib.sha256(corpus_raw).hexdigest(),
        "case_count": len(case_reports),
        "top5": {
            "eligible_case_count": retrieval_cases,
            "hit_count": hits,
            "hit_rate": hit_rate,
            "minimum_hit_rate": minimum_hit_rate,
            "baseline_passed": baseline_passed,
            "gate": "required",
        },
        "source_safety": {
            "outcome": "passed" if source_safety_passed else "failed",
            "invalid_source_exclusion_passed": exclusion_passed,
            "no_valid_source_passed": no_source_passed,
            "gate": "required",
        },
        "cases": case_reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--corpus",
        default=str(Path(__file__).resolve().parents[1] / "references" / "search-quality-cases.json"),
    )
    args = parser.parse_args(argv)
    try:
        report = measure_repository(args.repo, args.corpus)
    except (SearchQualityError, KnowledgeError) as exc:
        print(
            json.dumps(
                {
                    "schema": REPORT_SCHEMA,
                    "outcome": "invalid",
                    "error": getattr(exc, "code", "SEARCH_QUALITY_INVALID"),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
