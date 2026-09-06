#!/usr/bin/env python3
"""Validate project-knowledge syntax, governance, and integration contracts."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = SKILL_ROOT.parents[2]
HUMAN_GATE_AUTHORITY = (
    ".agents/skills/project-knowledge/references/human-gate-review.md"
)
HUMAN_GATE_OWNERS = {
    ".agents/skills/requirements-discovery/references/delivery-protocol.md": (
        "Human Gate bundle inventory",
        "Requirements primary",
        "Knowledge postimages",
        "BUG assessment Markdown and JSON",
    ),
    ".agents/skills/technical-planning/references/delivery-protocol.md": (
        "Human Gate bundle inventory",
        "plan primary",
        "handoff.json",
        "supporting artifacts",
        "occurrence_map.yaml",
        "Knowledge postimages",
    ),
    ".agents/skills/project-knowledge/SKILL.md": (
        "Human Gate bundle inventory",
        "candidate.json",
        "review.json",
        "postimages/",
    ),
    ".agents/skills/bug-diagnosis/SKILL.md": (
        "Human Gate bundle inventory",
        "BUG assessment Markdown and JSON",
        "Requirements Gate",
    ),
    ".agents/skills/delivery-orchestrator/references/stage-routing.md": (
        "Human Gate bundle inventory",
        "Requirements",
        "Plan",
        "Knowledge",
    ),
    ".agents/skills/implementation-execution/references/delivery-protocol.md": (
        "Human Gate bundle inventory",
        "implementation-outcome/v1",
        "Knowledge Candidate",
    ),
}
HUMAN_GATE_POINTER_INSTRUCTIONS = (
    ".agents/skills/bug-diagnosis/references/assessment-contract.md",
    ".agents/skills/delivery-orchestrator/SKILL.md",
    ".agents/skills/delivery-orchestrator/references/behavior-evaluation.md",
    ".agents/skills/delivery-orchestrator/references/workspace-and-run.md",
    ".agents/skills/requirements-discovery/SKILL.md",
    ".agents/skills/requirements-discovery/references/behavior-evaluation.md",
    ".agents/skills/technical-planning/SKILL.md",
    ".agents/skills/technical-planning/references/behavior-evaluation.md",
    ".agents/skills/technical-planning/references/ready-plan-contract.md",
)
HUMAN_GATE_ACTIVE_ROOTS = (
    ".agents/skills/requirements-discovery/",
    ".agents/skills/technical-planning/",
    ".agents/skills/delivery-orchestrator/",
    ".agents/skills/bug-diagnosis/",
    ".agents/skills/implementation-execution/",
    ".agents/skills/project-knowledge/",
)
HUMAN_GATE_ACTIVE_EXCLUSIONS = (
    "/scripts/behavior-evaluation-report.md",
)
CONTRADICTORY_HUMAN_GATE_PHRASES = (
    "完整展示",
    "展示完整diff",
    "完整顯示",
    "present all returned",
    "paste the complete payload into chat",
)
HUMAN_GATE_PRESENTATION_NEGATORS = (
    "不得",
    "不可",
    "禁止",
    "不要",
    "不應",
    "無須",
    "毋須",
    "never",
    "donot",
    "doesnot",
    "didnot",
    "mustnot",
    "shouldnot",
    "cannot",
    "cant",
    "isnot",
    "arenot",
    "wasnot",
    "werenot",
    "notto",
)
HUMAN_GATE_NEGATION_BOUNDARIES = (
    "however",
    "instead",
    "但是",
    "然而",
    "而是",
    "仍然",
    "仍要",
    "仍須",
    "but",
    "yet",
    "但",
    "卻",
)
HUMAN_GATE_SUMMARY_OBJECT_MARKERS = (
    "摘要和直接連結",
    "摘要與直接連結",
    "摘要及直接連結",
    "summaryanddirectlinks",
)
_GATE_ACTION = r"(?:展示|顯示|貼出|呈現|display(?:ed|ing|s)?|present(?:ed|ing|s)?|paste(?:d|ing|s)?|show(?:ed|ing|s)?)"
_GATE_COMPLETENESS = r"(?:完整|全部|所有|逐byte|每一byte|all|complete|entire|full|everybyte)"
_GATE_ARTIFACT = (
    r"(?:artifact|assessment|bytes?|candidate|content|diff|files?|outcome|output|"
    r"payload|plan|postimage|requirements?|results?|returns?|versions?|候選|產物|內容|"
    r"檔案|版本|評估|規劃|需求)"
)
_GATE_CONTEXT = re.compile(
    r"(?:核准|確認|同意|approval|approve|confirmation|chat|gate)"
)
_GATE_ACTION_RE = re.compile(_GATE_ACTION)
_GATE_COMPLETENESS_RE = re.compile(_GATE_COMPLETENESS)
_GATE_ARTIFACT_RE = re.compile(_GATE_ARTIFACT)
_SEMANTIC_GATE_CONTRADICTIONS = (
    re.compile(
        rf"{_GATE_COMPLETENESS}(?=.{{0,48}}{_GATE_ACTION})(?=.{{0,48}}{_GATE_ARTIFACT})"
    ),
    re.compile(rf"{_GATE_ACTION}(?=.{{0,48}}{_GATE_COMPLETENESS})(?=.{{0,48}}{_GATE_ARTIFACT})"),
    re.compile(rf"{_GATE_ARTIFACT}.{{0,48}}{_GATE_COMPLETENESS}.{{0,24}}{_GATE_ACTION}"),
)


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


def human_gate_active_instruction_paths(
    repository_files: Iterable[Path] | None = None,
) -> tuple[str, ...]:
    """Return every active Markdown instruction under a human-Gate owner root."""

    if repository_files is None:
        repository_files, _ = _eligible_repository_files()
    relatives: list[str] = []
    for path in repository_files:
        try:
            relative = path.relative_to(WORKSPACE).as_posix()
        except ValueError:
            continue
        if path.suffix.casefold() != ".md":
            continue
        if not relative.startswith(HUMAN_GATE_ACTIVE_ROOTS):
            continue
        if relative.endswith(HUMAN_GATE_ACTIVE_EXCLUSIONS):
            continue
        relatives.append(relative)
    return tuple(sorted(set(relatives)))


def _compact_gate_line(line: str) -> str:
    return re.sub(r"[\s`*_~]+", "", line.casefold())


def _gate_action_is_negated(compact: str, action_start: int) -> bool:
    """Return whether a local negator governs this display action."""

    prefix = compact[:action_start]
    boundary = max(
        (
            index + len(marker)
            for marker in HUMAN_GATE_NEGATION_BOUNDARIES
            if (index := prefix.rfind(marker)) >= 0
        ),
        default=0,
    )
    scope = prefix[boundary:]
    return any(
        (index := scope.rfind(marker)) >= 0
        and len(scope) - index - len(marker) <= 64
        for marker in HUMAN_GATE_PRESENTATION_NEGATORS
    )


def _contains_complete_artifact(text: str) -> bool:
    return bool(_GATE_COMPLETENESS_RE.search(text)) and bool(
        _GATE_ARTIFACT_RE.search(text)
    )


def _gate_action_targets_summary(
    compact: str,
    action: re.Match[str],
) -> bool:
    """Allow an action whose nearest object is the summary/link pair itself."""

    for marker in HUMAN_GATE_SUMMARY_OBJECT_MARKERS:
        marker_start = compact.find(marker)
        while marker_start >= 0:
            marker_end = marker_start + len(marker)
            if marker_end <= action.start():
                between = compact[marker_end : action.start()]
                full_object = compact[action.end() : action.end() + 64]
            elif marker_start >= action.end():
                between = compact[action.end() : marker_start]
                full_object = compact[max(0, action.start() - 64) : action.start()]
            else:
                between = ""
                full_object = ""
            if (
                len(between) <= 24
                and not _contains_complete_artifact(between)
                and not _contains_complete_artifact(full_object)
            ):
                return True
            marker_start = compact.find(marker, marker_end)
    return False


def _has_unnegated_gate_action(compact: str) -> bool:
    return any(
        not _gate_action_is_negated(compact, match.start())
        and not _gate_action_targets_summary(compact, match)
        for match in _GATE_ACTION_RE.finditer(compact)
    )


def contradictory_human_gate_instruction_lines(text: str) -> tuple[tuple[int, str], ...]:
    """Find affirmative instructions to put complete Gate payloads in Chat."""

    contradictions: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        clauses = re.split(r"[,，;；。.!?！？]+", line)
        for clause in clauses:
            compact = _compact_gate_line(clause)
            if not compact:
                continue
            exact_match = any(
                _compact_gate_line(phrase) in compact
                for phrase in CONTRADICTORY_HUMAN_GATE_PHRASES
            )
            semantic_match = bool(_GATE_CONTEXT.search(compact)) and any(
                pattern.search(compact) for pattern in _SEMANTIC_GATE_CONTRADICTIONS
            )
            if (exact_match or semantic_match) and _has_unnegated_gate_action(
                compact
            ):
                contradictions.append((line_number, line.strip()))
                break
    return tuple(contradictions)


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
        HUMAN_GATE_AUTHORITY,
        ".agents/skills/project-knowledge/scripts/knowledge_cli.py",
        ".agents/skills/project-knowledge/scripts/knowledge_benchmark.py",
        ".agents/skills/project-knowledge/scripts/compare_portability_reports.py",
        ".github/workflows/knowledge-portability.yml",
    )
    for relative in required_files:
        if not (WORKSPACE / relative).is_file():
            errors.append(f"required file missing: {relative}")

    authority = _read(HUMAN_GATE_AUTHORITY)
    errors.extend(
        _required_fragments(
            authority,
            (
                "<!-- authority: human-gate-review -->",
                "Summary-only Chat",
                "`gate`",
                "`summary`",
                "`risk_and_compatibility`",
                "`validation`",
                "`review_bundle`",
                "`identity`",
                "`prompt`",
                "Approve this exact review bundle or request modifications.",
                "LEGACY_RESEAL_REQUIRED",
                "Automatic validation",
            ),
            "human Gate authority",
        )
    )
    if authority.count("Approve this exact review bundle or request modifications.") != 1:
        errors.append("human Gate authority must define the canonical prompt exactly once")
    for relative, markers in HUMAN_GATE_OWNERS.items():
        owner = _read(relative)
        if HUMAN_GATE_AUTHORITY not in owner:
            errors.append(f"human Gate owner missing shared authority pointer: {relative}")
        for marker in markers:
            if marker not in owner:
                errors.append(
                    f"human Gate owner missing inventory marker {marker!r}: {relative}"
                )
    for relative in HUMAN_GATE_POINTER_INSTRUCTIONS:
        active = _read(relative)
        if HUMAN_GATE_AUTHORITY not in active:
            errors.append(f"human Gate active instruction missing shared authority pointer: {relative}")

    repository_files, inventory_errors = _eligible_repository_files()
    errors.extend(inventory_errors)
    for relative in human_gate_active_instruction_paths(repository_files):
        active = _read(relative)
        for line_number, line in contradictory_human_gate_instruction_lines(active):
            errors.append(
                "contradictory human Gate presentation instruction "
                f"at line {line_number}: {relative}: {line}"
            )

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
        "humanGateReview",
        "humanGateSummary",
        "humanGateClassification",
        "humanGateLintProjection",
        "humanGateAutomaticEvidence",
        "reviewFile",
        "promotion",
        "applyResult",
        "lint",
        "snapshot",
        "sourceRef",
    }
    missing_defs = expected_defs - set(definitions)
    if missing_defs:
        errors.append(f"knowledge schema definitions missing: {sorted(missing_defs)}")
    for name in (
        "page",
        "context",
        "candidate",
        "humanGateReview",
        "humanGateSummary",
        "promotion",
        "applyResult",
        "snapshot",
    ):
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
                'subcommands.add_parser("review")',
                'subcommands.add_parser("recover")',
                'arguments.command == "query"',
                'arguments.command == "candidate"',
                'arguments.command == "apply"',
                'apply.add_argument("--review-sha256", required=True)',
                "review_candidate",
                'candidate_ref=bootstrap_result["candidate_ref"]',
                "candidate_ref=repair_candidate_ref",
                "knowledge-error/v1",
                "known-secret-env",
                "sort_keys=True",
            ),
            "knowledge_cli.py",
        )
    )
    promotion = _read(
        ".agents/skills/project-knowledge/scripts/knowledge_promotion.py"
    )
    errors.extend(
        _required_fragments(
            promotion,
            (
                "_classification_projection(candidate)",
                "_lint_projection(target_bytes)",
                '"REVIEW_TARGET_COLLISION"',
                "seen_review_targets_casefolded",
            ),
            "knowledge_promotion.py",
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
