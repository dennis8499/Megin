#!/usr/bin/env python3
"""Run project-knowledge and related owner checks without external dependencies."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["related", "all"], required=True)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    args = parser.parse_args(argv)
    workspace = Path.cwd().resolve()
    fixture_root = args.fixture_root.resolve()
    if fixture_root.parent != workspace or fixture_root.name != ".knowledge-test-tmp":
        print("fixture root is outside the approved path", file=sys.stderr)
        return 2
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    outcomes: list[dict[str, Any]] = []
    for item in _commands(args.scope, args.fixture_root):
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
        except subprocess.TimeoutExpired as exc:
            outcome = {
                "command_id": item["command_id"],
                "exit_code": None,
                "stdout": (exc.stdout or b"").decode("utf-8", errors="replace"),
                "stderr": (exc.stderr or b"").decode("utf-8", errors="replace"),
                "timeout": True,
            }
        outcomes.append(outcome)
        if outcome["exit_code"] != 0:
            print(
                json.dumps(
                    {
                        "schema": "knowledge-suite-report/v1",
                        "scope": args.scope,
                        "outcome": "failed",
                        "commands": outcomes,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
    print(
        json.dumps(
            {
                "schema": "knowledge-suite-report/v1",
                "scope": args.scope,
                "outcome": "passed",
                "commands": outcomes,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


