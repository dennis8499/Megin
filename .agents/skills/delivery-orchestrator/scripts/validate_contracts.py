#!/usr/bin/env python3
"""Development-only static validation for delivery-orchestrator contracts."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


sys.dont_write_bytecode = True
SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_ROOT.parent
SCHEMA_PATH = SKILL_ROOT / "references" / "delivery-run.schema.json"
HELPER_PATH = SKILL_ROOT / "scripts" / "delivery_workspace.py"

EXPECTED_REQUIRED = {
    "schema",
    "work_id",
    "request_sha256",
    "repo_id",
    "primary_worktree",
    "initial_base_sha",
    "artifact_root",
    "phase",
    "status",
    "current_generation",
    "generations",
    "requirements",
    "plans",
    "implementations",
    "events",
    "updated_at",
}
EXPECTED_PHASE_TRANSITIONS = {
    "workspace": {"workspace", "requirements"},
    "requirements": {"requirements", "planning"},
    "planning": {"planning", "requirements", "implementation"},
    "implementation": {"implementation", "planning", "complete"},
    "complete": set(),
}
EXPECTED_STATUS_TRANSITIONS = {
    "active": {"active", "awaiting_user", "blocked", "complete"},
    "awaiting_user": {"awaiting_user", "active", "blocked"},
    "blocked": {"blocked", "active"},
    "complete": set(),
}
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/workspace-and-run.md",
    "references/stage-routing.md",
    "references/delivery-run.schema.json",
    "references/behavior-evaluation.md",
    "scripts/delivery_workspace.py",
    "scripts/test_delivery_workspace.py",
    "scripts/behavior-evaluation-report.md",
}
LINK_RE = re.compile(r"!?(?<!\\)\[[^\]]*\]\(([^)]+)\)")
AUTHORITY_RE = re.compile(r"<!--\s*authority:\s*([a-z0-9-]+)\s*-->")


def _load_module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def _markdown_files() -> Iterable[Path]:
    yield from SKILL_ROOT.rglob("*.md")


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _local_link_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    parsed = urlparse(target)
    if parsed.scheme or target.startswith("#"):
        return None
    path_text = unquote(parsed.path)
    if not path_text:
        return None
    return (source.parent / path_text).resolve(strict=False)


def _schema_errors(schema: dict[str, Any], helper: Any) -> list[str]:
    errors: list[str] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema must use JSON Schema draft 2020-12")
    if schema.get("properties", {}).get("schema", {}).get("const") != "delivery-run/v1":
        errors.append("schema discriminator is not delivery-run/v1")
    if set(schema.get("required", [])) != EXPECTED_REQUIRED:
        errors.append("schema root required fields drifted")
    if schema.get("additionalProperties") is not False:
        errors.append("schema root must reject additional properties")

    definitions = schema.get("$defs", {})
    phases = set(definitions.get("phase", {}).get("enum", []))
    statuses = set(definitions.get("status", {}).get("enum", []))
    if phases != set(EXPECTED_PHASE_TRANSITIONS):
        errors.append("schema phase enum drifted")
    if statuses != set(EXPECTED_STATUS_TRANSITIONS):
        errors.append("schema status enum drifted")

    schema_phase_transitions = {
        key: set(value) for key, value in schema.get("x-phase-transitions", {}).items()
    }
    schema_status_transitions = {
        key: set(value) for key, value in schema.get("x-status-transitions", {}).items()
    }
    if schema_phase_transitions != EXPECTED_PHASE_TRANSITIONS:
        errors.append("schema phase transitions drifted")
    if schema_status_transitions != EXPECTED_STATUS_TRANSITIONS:
        errors.append("schema status transitions drifted")
    if helper.PHASE_TRANSITIONS != EXPECTED_PHASE_TRANSITIONS:
        errors.append("helper phase transitions drifted")
    if helper.STATUS_TRANSITIONS != EXPECTED_STATUS_TRANSITIONS:
        errors.append("helper status transitions drifted")
    if helper.SCHEMA != "delivery-run/v1":
        errors.append("helper schema discriminator drifted")

    for definition in ("generation", "artifactRevision", "planRevision", "implementationRun", "event"):
        if definitions.get(definition, {}).get("additionalProperties") is not False:
            errors.append(f"schema definition {definition} must reject additional properties")
    for definition in ("artifactRevision", "planRevision"):
        if definitions.get(definition, {}).get("properties", {}).get("status", {}).get("const") != "Ready":
            errors.append(f"schema definition {definition} must represent persisted Ready revisions only")
        approval = definitions.get(definition, {}).get("properties", {}).get("approval_evidence_refs", {})
        if approval.get("minItems") != 1 or approval.get("uniqueItems") is not True:
            errors.append(f"schema definition {definition} must require unique approval evidence")
    if definitions.get("event", {}).get("properties", {}).get("evidence_refs", {}).get("minItems") != 1:
        errors.append("event evidence refs must be non-empty")
    if definitions.get("implementationRun", {}).get("properties", {}).get("ledger_ref", {}).get("$ref") != "#/$defs/evidenceRef":
        errors.append("implementation ledger refs must use redacted evidence-ref syntax")
    normalized_path_pattern = definitions.get("normalizedPath", {}).get("pattern", "")
    try:
        normalized_path_re = re.compile(normalized_path_pattern)
    except re.error as exc:
        errors.append(f"normalized path pattern is invalid: {exc}")
    else:
        for safe in ("docs/work/sample/requirements.md", "docs/work/sample/plan/handoff.json"):
            if normalized_path_re.fullmatch(safe) is None:
                errors.append(f"normalized path pattern rejects safe path {safe!r}")
        for unsafe in ("../escape", "./escape", "docs/./escape", "C:/escape", "/escape", "a\\b", "a//b", "https://example.invalid/x"):
            if normalized_path_re.fullmatch(unsafe) is not None:
                errors.append(f"normalized path pattern accepts unsafe path {unsafe!r}")

    with tempfile.TemporaryDirectory(prefix="delivery-schema-test-") as temporary:
        primary = Path(temporary) / "project"
        destination, branch = helper.destination_and_branch(primary, "sample-work", 1)
        probe = {
            "repo_id": "0" * 64,
            "primary_worktree": str(primary.resolve()),
            "head_sha": "1" * 40,
        }
        record = helper._new_record(probe, "sample-work", "2" * 64, destination, branch)
        record["generations"][0]["status"] = "ready"
        helper._append_event(
            record,
            kind="workspace_created",
            phase="workspace",
            status="active",
            evidence_refs=["evidence/worktree.json"],
        )
        semantic_errors = helper.validate_record(record)
        if semantic_errors:
            errors.append(f"helper rejects its own sample record: {semantic_errors}")
        extended = dict(record)
        extended["unexpected"] = "redacted fixture value"
        if not helper.validate_record(extended):
            errors.append("helper runtime validation accepts unknown record fields")

        planning_validator_path = SKILLS_ROOT / "technical-planning" / "scripts" / "validate_contracts.py"
        if planning_validator_path.is_file():
            planning_validator = _load_module(planning_validator_path, "delivery_planning_validator")
            instance_errors = planning_validator.validate_instance(record, schema)
            if instance_errors:
                errors.append(f"schema rejects helper sample record: {instance_errors}")
        else:
            errors.append("technical-planning schema validator is missing")
    return errors


def _helper_errors(helper: Any) -> list[str]:
    errors: list[str] = []
    source = HELPER_PATH.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"helper syntax error: {exc}"]

    literal_strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for forbidden in ("stash", "reset", "clean", "commit", "push", "checkout", "switch", "worktree remove", "worktree prune", "-B", "-f", "--force"):
        if forbidden in literal_strings:
            errors.append(f"helper contains forbidden Git operation literal {forbidden!r}")
    if "shell=True" in source.replace(" ", ""):
        errors.append("helper must not invoke a shell")
    required_fragments = (
        '"worktree",\n                "add",\n                "--no-track",\n                "-b"',
        'environment["GIT_OPTIONAL_LOCKS"] = "0"',
        'environment["GIT_NO_LAZY_FETCH"] = "1"',
        'f"core.hooksPath={disabled_hooks.as_posix()}"',
        'f"filter.{driver}.process="',
        'status = _strict_status(top)',
        '"--ignore-submodules=dirty"',
        '"stdout_sha256": sha256_bytes(completed.stdout)',
        '_validate_ready_contract(handoff)',
        '_schema_errors(record, _delivery_run_schema())',
        'run_dir.mkdir()',
        'os.O_CREAT | os.O_EXCL',
    )
    for fragment in required_fragments:
        if fragment not in source:
            errors.append(f"helper is missing safety primitive {fragment!r}")
    for forbidden_fragment in (
        '"stdout": _decode(completed.stdout)',
        '"stderr": _decode(completed.stderr)',
    ):
        if forbidden_fragment in source:
            errors.append("helper persists raw Git command output")

    parser = helper._parser()
    subparser_action = next(
        (action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"),
        None,
    )
    commands = set(subparser_action.choices) if subparser_action is not None else set()
    if commands != {"probe", "start", "locate", "transition"}:
        errors.append(f"helper public commands drifted: {sorted(commands)}")

    for valid in ("abc", "work-a1", "a" * 64):
        try:
            helper.validate_work_id(valid)
        except helper.DeliveryError as exc:
            errors.append(f"helper rejected valid Work ID {valid!r}: {exc}")
    for invalid in ("ab", "UPPER", "bad/id", "bad-", "bad--id", "con", "a" * 65):
        try:
            helper.validate_work_id(invalid)
        except helper.DeliveryError:
            pass
        else:
            errors.append(f"helper accepted invalid Work ID {invalid!r}")
    slug_words = helper.topic_slug("one").split("-")
    if not 2 <= len(slug_words) <= 5:
        errors.append("default topic slug is not two to five words")
    return errors


def validate_all() -> list[str]:
    errors: list[str] = []
    for relative in sorted(REQUIRED_FILES):
        if not (SKILL_ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    frontmatter = _frontmatter(SKILL_ROOT / "SKILL.md")
    if frontmatter.get("name") != "delivery-orchestrator":
        errors.append("SKILL.md name must be delivery-orchestrator")
    description = frontmatter.get("description", "")
    for expected in ("新", "修錯", "純解說", "plan-only"):
        if expected not in description:
            errors.append(f"SKILL.md description lacks invocation discriminator {expected!r}")

    authorities: dict[str, list[str]] = {}
    for markdown in _markdown_files():
        text = markdown.read_text(encoding="utf-8")
        if "TODO" in text or "TBD" in text:
            errors.append(f"unfinished marker in {markdown.relative_to(SKILL_ROOT)}")
        for authority in AUTHORITY_RE.findall(text):
            authorities.setdefault(authority, []).append(markdown.relative_to(SKILL_ROOT).as_posix())
        for raw_target in LINK_RE.findall(text):
            target = _local_link_target(markdown, raw_target)
            if target is not None and not target.exists():
                errors.append(
                    f"broken local link in {markdown.relative_to(SKILL_ROOT)}: {raw_target}"
                )
    for authority in ("delivery-run", "delivery-routing"):
        if len(authorities.get(authority, [])) != 1:
            errors.append(f"authority {authority!r} must have exactly one owner")

    yaml_text = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "allow_implicit_invocation: true" not in yaml_text:
        errors.append("openai.yaml must allow implicit invocation")
    if "$delivery-orchestrator" not in yaml_text:
        errors.append("openai.yaml default prompt must name $delivery-orchestrator")

    implementation_files = [
        SKILLS_ROOT / "implementation-execution" / "SKILL.md",
        SKILLS_ROOT / "implementation-execution" / "references" / "preflight-and-ledger.md",
        SKILLS_ROOT / "implementation-execution" / "references" / "quality-contract.md",
        SKILLS_ROOT / "implementation-execution" / "references" / "behavior-evaluation.md",
    ]
    for path in implementation_files:
        if not path.is_file() or "delivery-run/v1" not in path.read_text(encoding="utf-8"):
            errors.append(f"implementation integration is missing from {path.relative_to(SKILLS_ROOT)}")
    behavior = (SKILL_ROOT / "references" / "behavior-evaluation.md").read_text(encoding="utf-8")
    for index in range(1, 9):
        if f"EVAL-DEL-{index:03d}" not in behavior:
            errors.append(f"missing EVAL-DEL-{index:03d}")

    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot parse delivery schema: {exc}")
        return errors
    try:
        helper = _load_module(HELPER_PATH, "delivery_workspace_validator_target")
    except Exception as exc:  # noqa: BLE001 - validator must report import failures
        errors.append(f"cannot import workspace helper: {exc}")
        return errors
    errors.extend(_schema_errors(schema, helper))
    errors.extend(_helper_errors(helper))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    errors = validate_all()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("delivery-orchestrator contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
