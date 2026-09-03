#!/usr/bin/env python3
"""Emit a deterministic portability and large-repository performance report."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from knowledge_governance import canonical_sha256
from knowledge_query import query_repository, sha256_bytes
from knowledge_workflow import build_stage_candidate_draft


FILE_COUNT = 50_000
PAGE_COUNT = 5_000
MAX_SECONDS = 2.0
QUERY_TOKENS = (
    "portable-query-alpha",
    "portable-query-bravo",
    "portable-query-charlie",
    "portable-query-delta",
    "portable-query-echo",
)
# This oracle is intentionally fixed after the first reviewed fixture run. A
# platform-specific path, newline, encoding, or ordering change must alter it.
EXPECTED_FUNCTIONAL_SHA256 = "bae0d3eee98a4ba39967ca26e3b60fd1d2f5f1d781b7dca8e00b8d385c615f83"


def _write(path: Path, value: bytes) -> None:
    path.write_bytes(value)


def _safe_remove_fixture(root: Path) -> None:
    resolved = root.resolve(strict=False)
    workspace = Path.cwd().resolve()
    if resolved.parent != workspace or resolved.name != ".knowledge-test-tmp":
        raise ValueError(f"fixture root is outside the approved path: {resolved}")
    if not resolved.exists():
        return

    def make_writable_and_retry(function: Callable[..., object], path: str, _: object) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)

    os.chmod(resolved, stat.S_IWRITE)
    shutil.rmtree(resolved, onexc=make_writable_and_retry)


def _source_bytes(index: int) -> tuple[bytes, int, bytes]:
    if index < len(QUERY_TOKENS):
        line = f"{QUERY_TOKENS[index]} establishes portable rule {index:05d}.".encode("utf-8")
        if index == len(QUERY_TOKENS) - 1:
            return b"explicit-crlf-header\r\n" + line + b"\r\n", 2, line
        return line + b"\n", 1, line
    line = f"benchmark-source-{index:05d}".encode("utf-8")
    return line + b"\n", 1, line


def _page_contract(index: int, source: bytes, line_number: int, excerpt: bytes) -> tuple[bytes, bytes]:
    token = QUERY_TOKENS[index] if index < len(QUERY_TOKENS) else f"benchmark-topic-{index:04d}"
    title = f"Portable Benchmark Topic {index:04d} {token}"
    statement = f"{token} establishes portable rule {index:05d}."
    content_path = f"docs/knowledge/topics/benchmark-{index:04d}.md"
    source_path = f"evidence/{index // 1000:02d}/source-{index:05d}.md"
    content = (
        f"# {title}\n\n"
        f"## benchmark-topic-{index:04d}\n\n"
        f"{statement}\n"
    ).encode("utf-8")
    page = {
        "schema": "knowledge-page/v1",
        "page_id": f"page-benchmark-{index:04d}",
        "content_path": content_path,
        "content_sha256": sha256_bytes(content),
        "title": title,
        "aliases": [],
        "tags": ["benchmark"],
        "lifecycle": "current",
        "claims": [
            {
                "claim_id": f"claim-benchmark-{index:04d}",
                "evidence_class": "observed",
                "lifecycle": "current",
                "content_anchor": f"benchmark-topic-{index:04d}",
                "source_refs": [
                    {
                        "path": source_path,
                        "sha256": sha256_bytes(source),
                        "locator": {
                            "start_line": line_number,
                            "end_line": line_number,
                        },
                        "excerpt_sha256": sha256_bytes(excerpt),
                    }
                ],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }
    sidecar = (
        json.dumps(page, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return content, sidecar


def _existing_fixture(root: Path, *, file_count: int, page_count: int) -> Path | None:
    repo = root.resolve(strict=False) / "portability-benchmark"
    source_count = file_count - (page_count * 2) - 2
    required = (
        repo / ".git",
        repo / "evidence" / f"{(source_count - 1) // 1000:02d}" / f"source-{source_count - 1:05d}.md",
        repo / "docs" / "knowledge" / "topics" / f"benchmark-{page_count - 1:04d}.md",
        repo
        / "docs"
        / "knowledge"
        / "meta"
        / "pages"
        / f"page-benchmark-{page_count - 1:04d}.json",
    )
    if not all(path.exists() for path in required):
        return None
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    count = len([item for item in tracked.stdout.split(b"\0") if item])
    return repo if tracked.returncode == 0 and count == file_count else None


def _fixture_parent_directories(repo: Path, *, source_count: int) -> tuple[Path, ...]:
    """Return the unique parent plan in ancestor-before-descendant order."""

    directories = {
        repo / "docs",
        repo / "docs" / "knowledge",
        repo / "docs" / "knowledge" / "topics",
        repo / "docs" / "knowledge" / "meta",
        repo / "docs" / "knowledge" / "meta" / "pages",
        repo / "evidence",
        *(
            repo / "evidence" / f"{bucket:02d}"
            for bucket in range(((source_count - 1) // 1000) + 1)
        ),
    }
    return tuple(sorted(directories, key=lambda path: (len(path.parts), path.as_posix())))


def _fixture_entries(*, source_count: int, page_count: int) -> Iterator[tuple[str, bytes]]:
    yield ".gitignore", b".cache/\n"
    yield ".gitattributes", b"* text=auto eol=lf\n"
    for index in range(source_count):
        source, line_number, excerpt = _source_bytes(index)
        yield f"evidence/{index // 1000:02d}/source-{index:05d}.md", source
        if index < page_count:
            content, sidecar = _page_contract(index, source, line_number, excerpt)
            yield f"docs/knowledge/topics/benchmark-{index:04d}.md", content
            yield f"docs/knowledge/meta/pages/page-benchmark-{index:04d}.json", sidecar


def _fixture_import_stream(*, source_count: int, page_count: int) -> bytes:
    stream = bytearray(
        b"commit refs/benchmark/fixture\n"
        b"committer Knowledge Benchmark <benchmark@example.invalid> 1 +0000\n"
        b"data 0\n\n"
        b"deleteall\n"
    )
    for relative_path, worktree_bytes in _fixture_entries(
        source_count=source_count,
        page_count=page_count,
    ):
        index_bytes = worktree_bytes.replace(b"\r\n", b"\n")
        stream.extend(f"M 100644 inline {relative_path}\n".encode("utf-8"))
        stream.extend(f"data {len(index_bytes)}\n".encode("ascii"))
        stream.extend(index_bytes)
        stream.extend(b"\n")
    stream.extend(b"done\n")
    return bytes(stream)


def _build_fixture(
    root: Path,
    *,
    file_count: int,
    page_count: int,
    reuse_fixture: bool,
) -> Path:
    root = root.resolve(strict=False)
    source_count = file_count - (page_count * 2) - 2
    if source_count < page_count or page_count < len(QUERY_TOKENS):
        raise ValueError("benchmark counts cannot represent the required target pages")
    if reuse_fixture:
        existing = _existing_fixture(root, file_count=file_count, page_count=page_count)
        if existing is None:
            raise ValueError("requested benchmark fixture is absent or incomplete")
        return existing
    _safe_remove_fixture(root)
    root.mkdir()
    repo = root / "portability-benchmark"
    repo.mkdir()
    completed = subprocess.run(
        ["git", "init", "-q"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
    for directory in _fixture_parent_directories(repo, source_count=source_count):
        directory.mkdir()
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    subprocess.run(
        ["git", "fast-import", "--quiet"],
        cwd=repo,
        input=_fixture_import_stream(source_count=source_count, page_count=page_count),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    subprocess.run(
        ["git", "read-tree", "refs/benchmark/fixture"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    subprocess.run(
        ["git", "checkout-index", "--all", "--force"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    crlf_source, _, _ = _source_bytes(len(QUERY_TOKENS) - 1)
    _write(
        repo / "evidence" / "00" / f"source-{len(QUERY_TOKENS) - 1:05d}.md",
        crlf_source,
    )
    subprocess.run(
        ["git", "update-index", "--refresh"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    ).stdout
    tracked_count = len([item for item in tracked.split(b"\0") if item])
    if tracked_count != file_count:
        raise RuntimeError(
            f"tracked fixture count mismatch: expected {file_count}, got {tracked_count}"
        )
    return repo


def _timed(operation: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    value = operation()
    return value, time.perf_counter() - started


def _normalized_query_result(query: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": query,
        "results": [
            {
                "authority": item["authority"],
                "path": item["path"],
                "start_line": item["start_line"],
                "claim_id": item["claim_id"],
                "source_refs": [
                    {
                        "path": source["path"],
                        "sha256": source["sha256"],
                        "locator": source["locator"],
                        "excerpt_sha256": source["excerpt_sha256"],
                    }
                    for source in item["source_refs"]
                ],
            }
            for item in report["results"]
        ],
    }


def _cold_query(repo: Path, *, stage: str, query: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            str(Path(__file__).with_name("knowledge_cli.py")),
            "query",
            "--repo",
            str(repo),
            "--stage",
            stage,
            "--query",
            query,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        timeout=30.0,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cold query failed with exit {completed.returncode}: {detail}")
    try:
        report = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cold query returned invalid JSON: {exc}") from exc
    if not isinstance(report, dict):
        raise RuntimeError("cold query returned a non-object report")
    return report


def _version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            shell=False,
        )
    except OSError:
        return "unavailable"
    text = completed.stdout.decode("utf-8", errors="replace").splitlines()
    return text[0].strip() if text else "unavailable"


def _host() -> dict[str, str]:
    system = platform.system().casefold()
    os_name = {"windows": "windows", "darwin": "macos", "linux": "linux"}.get(
        system,
        system or "unknown",
    )
    return {
        "os": os_name,
        "python": platform.python_version(),
        "git": _version(["git", "--version"]),
        "rg": _version(["rg", "--version"]),
        "cpu": platform.processor() or platform.machine() or "unknown",
    }


def run_benchmark(
    fixture_root: Path,
    *,
    file_count: int = FILE_COUNT,
    page_count: int = PAGE_COUNT,
    reuse_fixture: bool = False,
    keep_fixture: bool = False,
) -> dict[str, Any]:
    """Build the fixture, then measure fresh cold and compatible warm paths."""

    succeeded = False
    try:
        repo, fixture_setup_duration = _timed(
            lambda: _build_fixture(
                fixture_root,
                file_count=file_count,
                page_count=page_count,
                reuse_fixture=reuse_fixture,
            )
        )
        artifact_text = (
            "# Benchmark requirements\n\n"
            "Status: Ready\n\n"
            "Benchmark index refresh is portable.\n"
        )
        candidate_arguments = {
            "stage": "requirements",
            "work_id": "work-benchmark",
            "artifact_path": "docs/work/work-benchmark/requirements.md",
            "artifact_text": artifact_text,
            "title": "Benchmark Index Refresh",
            "claim_text": "Benchmark index refresh is portable.",
        }
        tracked_paths = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            shell=False,
        ).stdout.split(b"\0")
        tracked_paths = [item for item in tracked_paths if item]
        tracked_page_count = sum(
            item.startswith(b"docs/knowledge/meta/pages/page-benchmark-")
            and item.endswith(b".json")
            for item in tracked_paths
        )
        # Keep every reported cold sample in a fresh process while excluding
        # one-time interpreter, tool, and repository readiness from timing.
        _cold_query(
            repo,
            stage="requirements",
            query=QUERY_TOKENS[0],
        )
        normalized_cold_queries: list[dict[str, Any]] = []
        cold_query_durations: list[float] = []
        for query in QUERY_TOKENS:
            result, duration = _timed(
                lambda current=query: _cold_query(
                    repo,
                    stage="requirements",
                    query=current,
                )
            )
            normalized_cold_queries.append(_normalized_query_result(query, result))
            cold_query_durations.append(duration)

        for query in QUERY_TOKENS:
            query_repository(str(repo), stage="requirements", query=query)
        build_stage_candidate_draft(str(repo), **candidate_arguments)

        normalized_queries: list[dict[str, Any]] = []
        query_durations: list[float] = []
        for query in QUERY_TOKENS:
            result, duration = _timed(
                lambda current=query: query_repository(
                    str(repo),
                    stage="requirements",
                    query=current,
                )
            )
            normalized_queries.append(_normalized_query_result(query, result))
            query_durations.append(duration)

        candidate, index_duration = _timed(
            lambda: build_stage_candidate_draft(str(repo), **candidate_arguments)
        )
        functional = {
            "schema": "knowledge-portability-functional/v1",
            "queries": normalized_queries,
            "index_candidate": [
                {
                    "kind": operation["kind"],
                    "path": operation["path"],
                    "postimage_sha256": hashlib.sha256(
                        operation["postimage"].encode("utf-8")
                    ).hexdigest(),
                }
                for operation in candidate["operations"]
            ],
            "persisted_path_separator": "/",
            "persisted_encoding": "utf-8",
            "persisted_newline": "lf",
        }
        functional_sha256 = canonical_sha256(functional)
        cold_queries_sha256 = canonical_sha256(normalized_cold_queries)
        warm_queries_sha256 = canonical_sha256(normalized_queries)
        durations = {
            "queries": query_durations,
            "cold_queries": cold_query_durations,
            "index_candidate": index_duration,
            "fixture_setup": fixture_setup_duration,
        }
        timed_values = [*cold_query_durations, *query_durations, index_duration]
        passed = (
            len(tracked_paths) == file_count
            and tracked_page_count == page_count
            and functional_sha256 == EXPECTED_FUNCTIONAL_SHA256
            and cold_queries_sha256 == warm_queries_sha256
            and all(value <= MAX_SECONDS for value in timed_values)
        )
        report = {
            "schema": "knowledge-portability-report/v1",
            "outcome": "passed" if passed else "failed",
            "host": _host(),
            "file_count": len(tracked_paths),
            "page_count": tracked_page_count,
            "source_file_count": file_count - (page_count * 2) - 2,
            "total_fixture_files": len(tracked_paths),
            "tracked_fixture": True,
            "max_operation_seconds": MAX_SECONDS,
            "durations_seconds": durations,
            "functional_sha256": functional_sha256,
            "expected_functional_sha256": EXPECTED_FUNCTIONAL_SHA256,
            "cold_queries_sha256": cold_queries_sha256,
            "warm_queries_sha256": warm_queries_sha256,
            "functional": functional,
        }
        succeeded = True
        return report
    finally:
        if not keep_fixture or not succeeded:
            _safe_remove_fixture(fixture_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    parser.add_argument("--reuse-fixture", action="store_true")
    parser.add_argument("--keep-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_benchmark(
            args.fixture_root,
            reuse_fixture=args.reuse_fixture,
            keep_fixture=args.keep_fixture,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "knowledge-portability-error/v1",
                    "code": "BENCHMARK_ENVIRONMENT",
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 4
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
