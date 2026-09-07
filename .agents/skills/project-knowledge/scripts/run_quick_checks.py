#!/usr/bin/env python3
"""Run the fast, dependency-free validation gate used before the full matrix."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _commands() -> list[dict[str, Any]]:
    python = [sys.executable, "-X", "utf8", "-B"]
    return [
        {
            "command_id": "QUICK-SYNTAX-SCHEMAS",
            "arguments": [
                *python,
                ".agents/skills/project-knowledge/scripts/validate_contracts.py",
                "--syntax-all",
            ],
            "timeout": 120,
        },
        *[
            {
                "command_id": f"QUICK-OWNER-{owner.upper()}",
                "arguments": [
                    *python,
                    f".agents/skills/{skill}/scripts/validate_contracts.py",
                ],
                "timeout": 120,
            }
            for owner, skill in (
                ("requirements", "requirements-discovery"),
                ("planning", "technical-planning"),
                ("implementation", "implementation-execution"),
                ("bug", "bug-diagnosis"),
                ("delivery", "delivery-orchestrator"),
            )
        ],
        {
            "command_id": "QUICK-DOCUMENTATION",
            "arguments": [
                *python,
                ".agents/skills/project-knowledge/scripts/test_workflow.py",
                "DocumentationAndCiImprovementTests",
                "--fixture-root",
                ".knowledge-test-tmp",
            ],
            "timeout": 180,
        },
        {
            "command_id": "QUICK-KNOWLEDGE-LINT",
            "arguments": [
                *python,
                ".agents/skills/project-knowledge/scripts/knowledge_cli.py",
                "lint",
                "--repo",
                ".",
            ],
            "timeout": 180,
        },
    ]


def main() -> int:
    workspace = Path.cwd().resolve()
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    outcomes: list[dict[str, Any]] = []
    commands = _commands()
    for index, item in enumerate(commands):
        timed_out = False
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
            exit_code = completed.returncode
            stdout = completed.stdout.decode("utf-8", errors="replace")
            stderr = completed.stderr.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        outcomes.append(
            {
                "command_id": item["command_id"],
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                **({"timeout": True} if timed_out else {}),
            }
        )
        if exit_code != 0:
            for pending in commands[index + 1 :]:
                outcomes.append(
                    {
                        "command_id": pending["command_id"],
                        "exit_code": None,
                        "stdout": "",
                        "stderr": "",
                        "not_run": True,
                    }
                )
            report = {
                "schema": "knowledge-quick-report/v1",
                "outcome": "failed",
                "commands": outcomes,
            }
            print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
    print(
        json.dumps(
            {
                "schema": "knowledge-quick-report/v1",
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
