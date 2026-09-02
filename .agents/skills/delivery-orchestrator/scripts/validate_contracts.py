#!/usr/bin/env python3
"""Owner and integration validation for delivery-orchestrator."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[2]
DELIVERY_SCHEMA_SHA256 = "e6973b241c4f754407f1667b1baaf7f263c6112f0fcf8165b935c01d482a5425"
EXPECTED_PHASE_TRANSITIONS = {
    "workspace": {"workspace", "requirements"},
    "requirements": {"requirements", "planning"},
    "planning": {"planning", "requirements", "implementation"},
    "implementation": {"implementation", "planning", "knowledge", "complete"},
    "knowledge": {"knowledge", "implementation", "complete"},
    "complete": set(),
}
EXPECTED_STATUS_TRANSITIONS = {
    "active": {"active", "awaiting_user", "blocked", "complete"},
    "awaiting_user": {"awaiting_user", "active", "blocked", "complete"},
    "blocked": {"blocked", "active"},
    "complete": set(),
}
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/workspace-and-run.md",
    "references/workspace-creation.md",
    "references/stage-routing.md",
    "references/delivery-run.schema.json",
    "references/behavior-evaluation.md",
    "scripts/_delivery_runtime.py",
    "scripts/_delivery_git.py",
    "scripts/_delivery_record.py",
    "scripts/delivery_workspace.py",
    "scripts/_delivery_test_support.py",
    "scripts/test_delivery_worktree.py",
    "scripts/test_delivery_safety.py",
    "scripts/test_delivery_transitions.py",
    "scripts/test_delivery_workspace.py",
    "scripts/test_validate_contracts.py",
    "scripts/capture_behavior_evidence.py",
    "scripts/behavior-evaluation-report.md",
    "scripts/context-load-report.md",
}
AUTHORITY_OWNERS = {
    "delivery-entrypoint": "SKILL.md",
    "delivery-run": "references/workspace-and-run.md",
    "delivery-workspace-creation": "references/workspace-creation.md",
    "delivery-routing": "references/stage-routing.md",
}
LINK_RE = re.compile(r"!?(?<!\\)\[[^\]]*\]\(([^)]+)\)")
AUTHORITY_RE = re.compile(r"<!--\s*authority:\s*([a-z0-9-]+)\s*-->")


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


def _local_target(source: Path, raw: str) -> Path | None:
    target = raw.strip().strip("<>")
    parsed = urlparse(target)
    if parsed.scheme or target.startswith("#"):
        return None
    path = unquote(parsed.path)
    return (source.parent / path).resolve(strict=False) if path else None


def _load_module(path: Path, name: str) -> Any:
    script_dir = str(path.parent)
    sys.path.insert(0, script_dir)
    try:
        for private in ("_delivery_runtime", "_delivery_git", "_delivery_record"):
            sys.modules.pop(private, None)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot import {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(script_dir)


def _validate_schema(bundle: Path, helper: Any, errors: list[str]) -> None:
    schema_path = bundle / "references/delivery-run.schema.json"
    if hashlib.sha256(schema_path.read_bytes()).hexdigest() != DELIVERY_SCHEMA_SHA256:
        errors.append("delivery-run/v1 schema bytes drifted")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"delivery schema parse failed: {exc}")
        return
    if schema.get("properties", {}).get("schema", {}).get("const") != "delivery-run/v1":
        errors.append("delivery schema discriminator drifted")
    if schema.get("additionalProperties") is not False:
        errors.append("delivery schema root must reject additional properties")
    if set(schema.get("properties", {}).get("work_kind", {}).get("enum", [])) != {"standard", "bug"}:
        errors.append("delivery schema work_kind overlay drifted")
    bug_set = schema.get("$defs", {}).get("bugSet", {})
    if not {"primary_bug_id", "assessments", "deferred", "verification"} <= set(bug_set.get("required", [])):
        errors.append("delivery schema bugSet is incomplete")
    deferred_bug = schema.get("$defs", {}).get("deferredBug", {})
    if not {
        "sequence",
        "bug_id",
        "relation",
        "status",
        "host_evidence_refs",
        "sensitive",
        "redacted_summary",
        "human_reviewer",
        "assessment_path",
        "assessment_sha256",
        "assessment_markdown_path",
        "assessment_markdown_sha256",
        "inbox_ref",
    } <= set(deferred_bug.get("required", [])):
        errors.append("delivery schema deferred BUG append-only contract is incomplete")
    verification = schema.get("$defs", {}).get("bugVerificationBinding", {})
    if not {"bug_id", "path", "sha256", "result"} <= set(verification.get("required", [])):
        errors.append("delivery schema BUG verification binding is incomplete")
    knowledge_gate = schema.get("$defs", {}).get("knowledgeGate", {})
    if not {
        "policy",
        "enabled_at",
        "candidate_ref",
        "candidate_payload_sha256",
        "knowledge_snapshot_id",
        "knowledge_post_snapshot_id",
        "product_snapshot_id",
        "outcome_path",
        "outcome_sha256",
        "current_promotion_id",
        "promotions",
        "review",
    } <= set(knowledge_gate.get("required", [])):
        errors.append("delivery schema knowledge gate is incomplete")
    knowledge_promotion = schema.get("$defs", {}).get("knowledgePromotion", {})
    if "formal_paths" not in set(knowledge_promotion.get("required", [])):
        errors.append("delivery schema knowledge promotion omits formal_paths")
    if {
        key: set(value)
        for key, value in schema.get("x-phase-transitions", {}).items()
    } != EXPECTED_PHASE_TRANSITIONS:
        errors.append("delivery schema phase transitions drifted")
    if {
        key: set(value)
        for key, value in schema.get("x-status-transitions", {}).items()
    } != EXPECTED_STATUS_TRANSITIONS:
        errors.append("delivery schema status transitions drifted")
    if helper.PHASE_TRANSITIONS != EXPECTED_PHASE_TRANSITIONS:
        errors.append("facade phase transitions drifted")
    if helper.STATUS_TRANSITIONS != EXPECTED_STATUS_TRANSITIONS:
        errors.append("facade status transitions drifted")

    with tempfile.TemporaryDirectory(prefix="delivery-schema-") as temporary:
        primary = Path(temporary) / "project"
        destination, branch = helper.destination_and_branch(primary, "sample-work", 1)
        probe = {
            "repo_id": "0" * 64,
            "primary_worktree": str(primary.resolve()),
            "head_sha": "1" * 40,
        }
        record = helper._new_record(
            probe,
            "sample-work",
            "2" * 64,
            destination,
            branch,
        )
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
            errors.append(f"facade rejects its sample record: {semantic_errors}")
        extended = dict(record)
        extended["unexpected"] = "redacted"
        if not helper.validate_record(extended):
            errors.append("record validation accepts unknown fields")

        planning_path = (
            bundle.parent / "technical-planning/scripts/validate_contracts.py"
        )
        planning = _load_module(planning_path, "delivery_ready_validator")
        instance_errors = planning.validate_instance(record, schema)
        if instance_errors:
            errors.append(f"delivery schema rejects sample record: {instance_errors}")


def _validate_runtime(bundle: Path, helper: Any, errors: list[str]) -> None:
    scripts = bundle / "scripts"
    runtime_paths = [
        scripts / "delivery_workspace.py",
        scripts / "_delivery_runtime.py",
        scripts / "_delivery_git.py",
        scripts / "_delivery_record.py",
    ]
    sources = {path.name: path.read_text(encoding="utf-8") for path in runtime_paths}
    aggregate = "\n".join(sources.values())
    try:
        trees = {name: ast.parse(source) for name, source in sources.items()}
    except SyntaxError as exc:
        errors.append(f"delivery runtime syntax error: {exc}")
        return

    literal_strings = {
        node.value
        for tree in trees.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for forbidden in (
        "stash",
        "reset",
        "clean",
        "commit",
        "push",
        "checkout",
        "switch",
        "worktree remove",
        "worktree prune",
        "-B",
        "-f",
        "--force",
    ):
        if forbidden in literal_strings:
            errors.append(f"runtime contains forbidden Git operation literal {forbidden!r}")
    if "shell=True" in aggregate.replace(" ", ""):
        errors.append("runtime must not invoke a shell")
    if re.search(r"safe\.directory\s*=", aggregate, re.IGNORECASE):
        errors.append("runtime must not bypass Git safe.directory")

    git_source = sources["_delivery_git.py"]
    for fragment in (
        'environment["LC_ALL"] = "C"',
        'environment["LANG"] = "C"',
        'environment["LANGUAGE"] = "C"',
        "detected dubious ownership",
        "safe.directory",
        '"GIT_CONFIG_COUNT"',
        'environment["GIT_NO_LAZY_FETCH"] = "1"',
        'environment["GIT_NO_REPLACE_OBJECTS"] = "1"',
        '"--ignore-submodules=dirty"',
        'f"filter.{driver}.process="',
        'child_error.code == "GIT_TRUST_REQUIRED"',
    ):
        if fragment not in git_source:
            errors.append(f"Git authority missing safety primitive {fragment!r}")

    runtime_source = sources["_delivery_runtime.py"]
    for fragment in (
        "SECRET_ASSIGNMENT_RE",
        "SECRET_SENTINEL_RE",
        "KNOWN_TOKEN_RE",
        "_contains_sensitive_material(ref)",
        "def _known_secret_values_from_env",
    ):
        if fragment not in runtime_source:
            errors.append(f"runtime authority missing secret-ref guard {fragment!r}")
    for fragment in ("def _atomic_create_json", "os.O_CREAT | os.O_EXCL | os.O_WRONLY"):
        if fragment not in runtime_source:
            errors.append(f"runtime authority missing create-only persistence primitive {fragment!r}")
    if runtime_source.count("os.O_CREAT | os.O_EXCL | os.O_WRONLY") < 2:
        errors.append("runtime authority no longer protects both inbox creation and record locking with O_EXCL")

    record_source = sources["_delivery_record.py"]
    for fragment in (
        "_schema_errors(record, _delivery_run_schema())",
        "_validate_ready_contract(handoff)",
        "_validate_historical_ready_contract(historical)",
        "approval_evidence_refs",
        "_approved_upstream_materialization",
        '"cat-file", "blob"',
        "sha256_bytes(base_bytes.stdout) != expected",
        "_complete_implementation_errors",
        'validate_instance(ledger, schema, "ledger")',
        "validator.validate_review_against_ready(",
        "Complete delivery event does not reference the accepted review",
        "_current_implementation_snapshot",
        '"diff",',
        '"--binary",',
        '"--full-index",',
        '"--no-ext-diff",',
        '"--no-textconv",',
        '"ls-files", "--others", "--exclude-standard", "-z"',
        'candidate_snapshot == current_snapshot',
        'report.get("snapshot_before") == accepted_snapshot_id',
        "Complete delivery event does not reference the canonical snapshot",
        "_bug_contract_validator",
        "MISSING_BUG_ASSESSMENT",
        "bug Ready plan must bind the current approved assessment",
        "validate_bug_verification_against_ready",
        "MISSING_BUG_VERIFICATION",
        "failed BUG verification cannot enter a terminal knowledge gate",
        "PENDING_BUG_EVIDENCE",
        "BUG_REQUIRES_REAPPROVAL",
        "BUG_INBOX_EXISTS",
        "successful BUG verification may only bind at legacy Complete or the reviewed knowledge gate",
        "required knowledge delivery cannot Complete directly from implementation",
        "review knowledge bindings differ from delivery gate",
        "knowledge promotion receipt differs from the approved reviewed Candidate",
        "knowledge_module.knowledge_workflow.validate_stage_promotion",
        '"formal_paths": formal_paths',
        "preliminary and final review agent identities must differ",
        "known_secret_values=known_secret_values",
        "sidecar_bytes=sidecar_bytes",
        "raw_json_bytes=verification_bytes",
        "terminal_evidence_refs=terminal_refs",
    ):
        if fragment not in record_source:
            errors.append(f"record authority missing semantic primitive {fragment!r}")
    if record_source.count("validator.validate_review_against_ready(") < 2:
        errors.append(
            "record authority missing semantic primitive for every Ready-bound review consumer"
        )
    if record_source.count('"cat-file", "blob"') < 2:
        errors.append(
            "record authority missing semantic primitive for both raw-base blob probes"
        )
    if record_source.count("sidecar_bytes=sidecar_bytes") < 2:
        errors.append("record authority does not forward raw BUG assessment bytes to both consumers")
    if record_source.count("raw_json_bytes=verification_bytes") < 2:
        errors.append("record authority does not forward raw BUG verification bytes to both consumers")

    creation = (bundle / "references/workspace-creation.md").read_text(encoding="utf-8")
    if "recorded-base blob並核對manifest SHA" not in creation:
        errors.append("workspace creation contract omits pre-mutation recorded-base byte verification")
    routing = (bundle / "references/stage-routing.md").read_text(encoding="utf-8")
    for fragment in (
        "implementation-execution/runs/<run_id>/run.json",
        "schema-valid `APPROVED` report",
        "重算當下`implementation-snapshot/v1`",
    ):
        if fragment not in routing:
            errors.append(f"routing contract omits terminal evidence semantic {fragment}")

    facade_source = sources["delivery_workspace.py"]
    facade_tree = trees["delivery_workspace.py"]
    facade_defs = {
        node.name
        for node in facade_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    expected_defs = {
        "start_workspace",
        "locate_workspace",
        "transition_record",
        "probe_command",
        "_parser",
        "main",
    }
    if facade_defs != expected_defs:
        errors.append(f"public facade definitions drifted: {sorted(facade_defs ^ expected_defs)}")
    if len(facade_source.splitlines()) > 760:
        errors.append("public facade is no longer a thin orchestration/CLI layer")
    for fragment in (
        '"worktree",',
        '"add",',
        '"--no-track",',
        '"stdout_sha256": sha256_bytes(completed.stdout)',
        "_git_failure_error(",
        '"--known-secret-env"',
        '"--enable-knowledge"',
        '"--knowledge-candidate-ref"',
    ):
        if fragment not in facade_source:
            errors.append(f"public facade missing creation primitive {fragment!r}")

    parser = helper._parser()
    action = next(
        (
            item
            for item in parser._actions
            if item.__class__.__name__ == "_SubParsersAction"
        ),
        None,
    )
    commands = set(action.choices) if action is not None else set()
    if commands != {"probe", "start", "locate", "transition"}:
        errors.append(f"public CLI commands drifted: {sorted(commands)}")
    if helper.probe_repository.__module__ != "_delivery_git":
        errors.append("probe_repository is not owned by _delivery_git")
    if helper.validate_record.__module__ != "_delivery_record":
        errors.append("validate_record is not owned by _delivery_record")

    completed = subprocess.CompletedProcess(
        ["git"],
        128,
        stdout=b"",
        stderr=(
            b"fatal: detected dubious ownership in repository at 'SECRET_SENTINEL'\n"
            b"git config --global --add safe.directory SECRET_SENTINEL\n"
        ),
    )
    trust = helper._git_failure_error(
        completed,
        fallback_code="NOT_A_REPOSITORY",
        fallback_message="not a Git repository",
    )
    if trust.code != "GIT_TRUST_REQUIRED":
        errors.append("Git trust failure is not classified precisely")
    if "SECRET_SENTINEL" in str(trust):
        errors.append("Git trust failure reflects raw stderr")
    ordinary = helper._git_failure_error(
        subprocess.CompletedProcess(["git"], 128, stdout=b"", stderr=b"fatal: other\n"),
        fallback_code="NOT_A_REPOSITORY",
        fallback_message="not a Git repository",
    )
    if ordinary.code != "NOT_A_REPOSITORY":
        errors.append("ordinary Git failure lost its compatible fallback code")


def validate_all(skills_root: Path | None = None) -> list[str]:
    root = (skills_root or DEFAULT_SKILLS_ROOT).resolve()
    bundle = root / "delivery-orchestrator"
    errors: list[str] = []

    for relative in sorted(REQUIRED_FILES):
        if not (bundle / relative).is_file():
            errors.append(f"missing required file: {relative}")
    if errors:
        return errors

    authorities: dict[str, list[str]] = {}
    for markdown in sorted(bundle.rglob("*.md")):
        relative = markdown.relative_to(bundle).as_posix()
        text = markdown.read_text(encoding="utf-8")
        if "TODO" in text or "TBD" in text:
            errors.append(f"unfinished marker: {relative}")
        for marker in AUTHORITY_RE.findall(text):
            authorities.setdefault(marker, []).append(relative)
        for raw in LINK_RE.findall(text):
            target = _local_target(markdown, raw)
            if target is not None and not target.exists():
                errors.append(f"broken local link in {relative}: {raw}")
    for authority, owner in AUTHORITY_OWNERS.items():
        actual = authorities.get(authority, [])
        if actual != [owner]:
            errors.append(f"authority {authority}: expected [{owner}], got {actual}")
    for authority, owners in sorted(authorities.items()):
        if len(owners) > 1:
            errors.append(f"duplicate authority {authority}: {owners}")

    frontmatter = _frontmatter(bundle / "SKILL.md")
    if frontmatter.get("name") != "delivery-orchestrator":
        errors.append("delivery SKILL.md name drifted")
    description = frontmatter.get("description", "")
    if not description.startswith("交付"):
        errors.append("delivery description must lead with 交付")
    for discriminator in ("新功能", "修錯", "純解說", "plan-only"):
        if discriminator not in description:
            errors.append(f"delivery description lacks discriminator {discriminator}")

    yaml = (bundle / "agents/openai.yaml").read_text(encoding="utf-8")
    for fragment in (
        "allow_implicit_invocation: true",
        "$delivery-orchestrator",
        'short_description: "交付',
    ):
        if fragment not in yaml:
            errors.append(f"delivery openai.yaml missing {fragment}")

    behavior = (bundle / "references/behavior-evaluation.md").read_text(encoding="utf-8")
    for index in range(1, 11):
        if f"EVAL-DEL-{index:03d}" not in behavior:
            errors.append(f"behavior contract missing EVAL-DEL-{index:03d}")

    implementation = root / "implementation-execution"
    for relative in (
        "SKILL.md",
        "references/orchestrated-delivery.md",
        "references/quality-contract.md",
        "references/behavior-evaluation.md",
    ):
        path = implementation / relative
        if not path.is_file() or "delivery-run/v1" not in path.read_text(encoding="utf-8"):
            errors.append(f"implementation delivery integration missing: {relative}")

    try:
        helper = _load_module(
            bundle / "scripts/delivery_workspace.py",
            "delivery_workspace_validator_target",
        )
    except Exception as exc:
        errors.append(f"cannot import delivery facade: {exc}")
        return errors
    _validate_schema(bundle, helper, errors)
    _validate_runtime(bundle, helper, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    args = parser.parse_args(argv)
    errors = validate_all(args.skills_root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("delivery-orchestrator contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
