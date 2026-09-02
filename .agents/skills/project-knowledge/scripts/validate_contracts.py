#!/usr/bin/env python3
"""Validate project-knowledge syntax, governance, and integration contracts."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = SKILL_ROOT.parents[2]


def _read(relative: str) -> str:
    try:
        return (WORKSPACE / relative).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _required_fragments(text: str, fragments: Iterable[str], label: str) -> list[str]:
    return [f"{label} missing required fragment: {fragment}" for fragment in fragments if fragment not in text]


def _eligible_repository_files() -> tuple[list[Path], list[str]]:
    errors: list[str] = []
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=WORKSPACE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
        )
    except OSError as exc:
        return [], [f"Git inventory unavailable: {exc}"]
    if completed.returncode != 0:
        return [], ["Git inventory failed while discovering build inputs"]
    paths: list[Path] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relative = raw.decode("utf-8").replace("\\", "/")
        except UnicodeDecodeError:
            errors.append("Git inventory contains a non-UTF-8 path")
            continue
        candidate = WORKSPACE / Path(*relative.split("/"))
        if candidate.is_file() and not candidate.is_symlink():
            paths.append(candidate)
    paths.sort(key=lambda path: path.relative_to(WORKSPACE).as_posix().encode("utf-8"))
    return paths, errors


def syntax_errors() -> tuple[list[str], int, int]:
    errors: list[str] = []
    repository_files, inventory_errors = _eligible_repository_files()
    errors.extend(inventory_errors)
    python_files = [path for path in repository_files if path.suffix.casefold() == ".py"]
    schema_files = [path for path in repository_files if path.name.endswith(".schema.json")]
    for path in python_files:
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"Python syntax invalid: {path.relative_to(WORKSPACE).as_posix()}: {exc}")
    for path in schema_files:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                errors.append(
                    f"JSON schema root is not an object: {path.relative_to(WORKSPACE).as_posix()}"
                )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"JSON schema invalid: {path.relative_to(WORKSPACE).as_posix()}: {exc}")
    return errors, len(python_files), len(schema_files)


def governance_errors() -> list[str]:
    errors: list[str] = []
    required_files = (
        ".agents/skills/project-knowledge/SKILL.md",
        ".agents/skills/project-knowledge/agents/openai.yaml",
        ".agents/skills/project-knowledge/schemas/knowledge-contracts.schema.json",
        ".agents/skills/project-knowledge/scripts/knowledge_cli.py",
        ".agents/skills/project-knowledge/scripts/knowledge_benchmark.py",
        ".agents/skills/project-knowledge/scripts/compare_portability_reports.py",
        ".github/workflows/knowledge-portability.yml",
    )
    for relative in required_files:
        if not (WORKSPACE / relative).is_file():
            errors.append(f"required file missing: {relative}")

    skill = _read(".agents/skills/project-knowledge/SKILL.md")
    if not skill.startswith("---\nname: project-knowledge\n"):
        errors.append("SKILL frontmatter name is invalid")
    errors.extend(
        _required_fragments(
            skill,
            (
                "## Choose one branch",
                "## Query protocol",
                "## Candidate and approval protocol",
                "## Lifecycle and certainty",
                "## Failure handling",
                "Re-read every returned `source_refs.path`",
                "A prior plan approval",
                "one local OS result is not Windows/Linux evidence",
            ),
            "SKILL.md",
        )
    )

    agent = _read(".agents/skills/project-knowledge/agents/openai.yaml")
    errors.extend(
        _required_fragments(
            agent,
            (
                'display_name: "Project Knowledge"',
                "allow_implicit_invocation: true",
                "$project-knowledge",
            ),
            "agents/openai.yaml",
        )
    )

    try:
        schema = json.loads(
            _read(".agents/skills/project-knowledge/schemas/knowledge-contracts.schema.json")
        )
    except json.JSONDecodeError as exc:
        errors.append(f"knowledge schema is not valid JSON: {exc}")
        schema = {}
    definitions = schema.get("$defs", {}) if isinstance(schema, dict) else {}
    expected_defs = {
        "page",
        "context",
        "candidate",
        "promotion",
        "applyResult",
        "lint",
        "snapshot",
        "sourceRef",
    }
    missing_defs = expected_defs - set(definitions)
    if missing_defs:
        errors.append(f"knowledge schema definitions missing: {sorted(missing_defs)}")
    for name in ("page", "context", "candidate", "promotion", "applyResult", "snapshot"):
        value = definitions.get(name)
        if isinstance(value, dict) and value.get("additionalProperties") is not False:
            errors.append(f"knowledge schema definition is not closed: {name}")

    cli = _read(".agents/skills/project-knowledge/scripts/knowledge_cli.py")
    errors.extend(
        _required_fragments(
            cli,
            (
                'subcommands.add_parser("bootstrap")',
                'subcommands.add_parser("lint")',
                'subcommands.add_parser("recover")',
                'arguments.command == "query"',
                'arguments.command == "candidate"',
                'arguments.command == "apply"',
                "knowledge-error/v1",
                "known-secret-env",
                "sort_keys=True",
            ),
            "knowledge_cli.py",
        )
    )

    all_python = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SKILL_ROOT.rglob("*.py")
        if path.name != "validate_contracts.py"
    )
    for forbidden in ("import sqlite3", "import requests", "from requests", "import chromadb", "shell=True"):
        if forbidden in all_python:
            errors.append(f"forbidden runtime dependency or shell mode present: {forbidden}")

    ignore = _read(".gitignore")
    errors.extend(
        _required_fragments(
            ignore,
            (
                "docs/*",
                "!docs/work/**",
                "!docs/bugs/**",
                "!docs/knowledge/**",
                ".knowledge-test-tmp/",
            ),
            ".gitignore",
        )
    )
    workflow = _read(".github/workflows/knowledge-portability.yml")
    errors.extend(
        _required_fragments(
            workflow,
            (
                "runner: ubuntu-latest",
                "runner: windows-latest",
                "knowledge_benchmark.py",
                "run_full_suite.py",
                "compare_portability_reports.py",
            ),
            "knowledge-portability.yml",
        )
    )
    benchmark = _read(".agents/skills/project-knowledge/scripts/knowledge_benchmark.py")
    errors.extend(
        _required_fragments(
            benchmark,
            (
                "FILE_COUNT = 50_000",
                "PAGE_COUNT = 5_000",
                "MAX_SECONDS = 2.0",
                "EXPECTED_FUNCTIONAL_SHA256",
                "explicit-crlf-header",
            ),
            "knowledge_benchmark.py",
        )
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--syntax-all", action="store_true")
    parser.add_argument("--governance", action="store_true")
    args = parser.parse_args(argv)
    run_syntax = args.syntax_all or not args.governance
    run_governance = args.governance or not args.syntax_all
    syntax_findings, python_count, schema_count = (
        syntax_errors() if run_syntax else ([], 0, 0)
    )
    errors = [
        *syntax_findings,
        *(governance_errors() if run_governance else []),
    ]
    report = {
        "schema": "knowledge-contract-validation/v1",
        "outcome": "passed" if not errors else "failed",
        "syntax_checked": run_syntax,
        "governance_checked": run_governance,
        "python_files_checked": python_count,
        "json_schema_files_checked": schema_count,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

