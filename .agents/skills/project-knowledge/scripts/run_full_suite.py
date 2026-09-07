#!/usr/bin/env python3
"""Run project-knowledge and related owner checks without external dependencies."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def _command(
    *arguments: str,
    command_id: str,
    timeout: int,
) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "arguments": [sys.executable, "-X", "utf8", "-B", *arguments],
        "timeout": timeout,
    }


def _commands(scope: str, fixture_root: Path) -> list[dict[str, Any]]:
    root = ".agents/skills/project-knowledge/scripts"
    commands = [
        _command(
            f"{root}/test_query.py",
            "--fixture-root",
            str(fixture_root),
            command_id="TEST-QUERY",
            timeout=180,
        ),
        _command(
            f"{root}/test_workflow.py",
            "--fixture-root",
            str(fixture_root),
            command_id="TEST-WORKFLOW",
            timeout=180,
        ),
        _command(
            f"{root}/test_behavior.py",
            *(("--group", "retrieval") if scope == "related" else ()),
            "--fixture-root",
            str(fixture_root),
            command_id="BDD-RELATED" if scope == "related" else "BDD-FULL",
            timeout=900,
        ),
        _command(
            ".agents/skills/requirements-discovery/scripts/validate_contracts.py",
            command_id="OWNER-REQUIREMENTS",
            timeout=120,
        ),
        _command(
            ".agents/skills/technical-planning/scripts/validate_contracts.py",
            command_id="OWNER-PLANNING",
            timeout=120,
        ),
        _command(
            ".agents/skills/implementation-execution/scripts/validate_contracts.py",
            command_id="OWNER-IMPLEMENTATION",
            timeout=120,
        ),
        _command(
            ".agents/skills/bug-diagnosis/scripts/validate_contracts.py",
            command_id="OWNER-BUG",
            timeout=120,
        ),
        _command(
            ".agents/skills/delivery-orchestrator/scripts/validate_contracts.py",
            command_id="OWNER-DELIVERY",
            timeout=180,
        ),
    ]
    if scope == "all":
        governance = Path(f"{root}/test_governance.py")
        validator = Path(f"{root}/validate_contracts.py")
        if governance.is_file():
            commands.insert(
                1,
                _command(
                    str(governance),
                    "--fixture-root",
                    str(fixture_root),
                    command_id="TEST-GOVERNANCE",
                    timeout=360,
                ),
            )
        if validator.is_file():
            commands.extend(
                [
                    _command(
                        str(validator),
                        "--syntax-all",
                        command_id="BUILD-FULL",
                        timeout=120,
                    ),
                    _command(
                        str(validator),
                        "--governance",
                        command_id="GOVERNANCE",
                        timeout=180,
                    ),
                ]
            )
        commands.append(
            _command(
                f"{root}/measure_search_quality.py",
                "--repo",
                ".",
                command_id="SEARCH-QUALITY",
                timeout=180,
            )
        )
        commands.extend(
            [
                _command(
                    ".agents/skills/requirements-discovery/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-REQUIREMENTS",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/technical-planning/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-PLANNING",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/implementation-execution/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-IMPLEMENTATION",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/bug-diagnosis/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-BUG",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/delivery-orchestrator/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-DELIVERY-CONTRACT",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py",
                    command_id="TEST-OWNER-DELIVERY-WORKSPACE",
                    timeout=900,
                ),
            ]
        )
    return commands


def _is_redirect(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return os.name == "nt" and bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _metrics_target(
    workspace: Path,
    value: str | None,
    *,
    allowed_missing_parent: Path | None = None,
) -> Path | None:
    if value is None:
        return None
    lexical = Path(value)
    if not lexical.is_absolute():
        lexical = workspace / lexical
    lexical = Path(os.path.abspath(lexical))
    current = lexical
    reached_workspace = False
    while True:
        if _is_redirect(current):
            raise ValueError("metrics output path is redirected")
        if current.resolve(strict=False) == workspace:
            reached_workspace = True
            break
        if current.parent == current:
            break
        current = current.parent
    candidate = lexical.resolve(strict=False)
    try:
        relative = candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("metrics output is outside the workspace") from exc
    if not reached_workspace:
        raise ValueError("metrics output path cannot be tied to the workspace")
    if not candidate.parent.is_dir() and candidate.parent != allowed_missing_parent:
        raise ValueError("metrics output parent does not exist")
    if candidate.exists() and (_is_redirect(candidate) or not stat.S_ISREG(candidate.lstat().st_mode)):
        raise ValueError("metrics output target is not a regular file")
    return candidate


def _metrics_report(scope: str, metrics: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    counts = {status: 0 for status in ("passed", "failed", "timeout", "not_run")}
    for item in metrics:
        counts[item["status"]] += 1
    return {
        "schema": "knowledge-suite-metrics/v1",
        "scope": scope,
        "outcome": outcome,
        "commands": metrics,
        "summary": {
            "counts": counts,
            "total_duration_seconds": round(
                sum(item["duration_seconds"] or 0.0 for item in metrics),
                6,
            ),
        },
    }


def _write_metrics(
    path: Path | None,
    report: dict[str, Any],
    *,
    create_parent: bool = False,
) -> None:
    if path is None:
        return
    if create_parent:
        path.parent.mkdir(exist_ok=True)
        if _is_redirect(path.parent):
            raise OSError("metrics output parent is redirected")
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["related", "all"], required=True)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    parser.add_argument("--metrics-output")
    args = parser.parse_args(argv)
    workspace = Path.cwd().resolve()
    fixture_root = args.fixture_root.resolve()
    if fixture_root.parent != workspace or fixture_root.name != ".knowledge-test-tmp":
        print("fixture root is outside the approved path", file=sys.stderr)
        return 2
    try:
        metrics_path = _metrics_target(
            workspace,
            args.metrics_output,
            allowed_missing_parent=fixture_root,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    outcomes: list[dict[str, Any]] = []
    commands = _commands(args.scope, args.fixture_root)
    metrics: list[dict[str, Any]] = [
        {
            "command_id": item["command_id"],
            "status": "not_run",
            "duration_seconds": None,
            "exit_code": None,
            "timeout_seconds": item["timeout"],
        }
        for item in commands
    ]
    metrics_parent_is_fixture = (
        metrics_path is not None and metrics_path.parent == fixture_root
    )
    for index, item in enumerate(commands):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                item["arguments"],
                cwd=workspace,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=item["timeout"],
                check=False,
                shell=False,
            )
            outcome = {
                "command_id": item["command_id"],
                "exit_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="replace"),
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            }
            metrics[index].update(
                {
                    "status": "passed" if completed.returncode == 0 else "failed",
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "exit_code": completed.returncode,
                }
            )
        except subprocess.TimeoutExpired as exc:
            outcome = {
                "command_id": item["command_id"],
                "exit_code": None,
                "stdout": (exc.stdout or b"").decode("utf-8", errors="replace"),
                "stderr": (exc.stderr or b"").decode("utf-8", errors="replace"),
                "timeout": True,
            }
            metrics[index].update(
                {
                    "status": "timeout",
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "exit_code": None,
                }
            )
        outcomes.append(outcome)
        if outcome["exit_code"] != 0:
            functional = {
                "schema": "knowledge-suite-report/v1",
                "scope": args.scope,
                "outcome": "failed",
                "commands": outcomes,
            }
            try:
                _write_metrics(
                    metrics_path,
                    _metrics_report(args.scope, metrics, "failed"),
                    create_parent=metrics_parent_is_fixture,
                )
            except OSError:
                print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
                return 2
            print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
    functional = {
        "schema": "knowledge-suite-report/v1",
        "scope": args.scope,
        "outcome": "passed",
        "commands": outcomes,
    }
    try:
        _write_metrics(
            metrics_path,
            _metrics_report(args.scope, metrics, "passed"),
            create_parent=metrics_parent_is_fixture,
        )
    except OSError:
        functional["outcome"] = "failed"
        print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(functional, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
