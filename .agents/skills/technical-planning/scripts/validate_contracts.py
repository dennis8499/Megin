#!/usr/bin/env python3
"""Producer-owned validation for ready-plan/v1 and shared JSON Schema helpers."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


AUTHORITY_FILES = {
    "planning-entrypoint": "technical-planning/SKILL.md",
    "ready-plan": "technical-planning/references/ready-plan-contract.md",
    "planning-state": "technical-planning/references/delivery-protocol.md",
}
READY_SCHEMA_SHA256 = "c3e90430e69acb6a06795f1855ab6fd045281ce555627061bd877c00d3f5c13b"
READY_ROOT_REQUIRED = {
    "schema",
    "candidate",
    "approval",
    "planning_baseline",
    "primary_plan",
    "artifacts",
    "sources",
    "contract_index",
    "commands",
    "work_packages",
    "revision_impact",
}

READY_DEF_REQUIRED = {
    "pathHash": {"path", "sha256"},
    "artifact": {"path", "role", "approval_status", "sha256"},
    "source": {"source_id", "kind", "location", "revision", "sha256", "plan_refs", "wp_refs"},
    "contract": {"contract_id", "kind", "source_refs", "wp_refs"},
    "command": {
        "command_id",
        "purpose",
        "status",
        "cwd",
        "command",
        "environment_prerequisites",
        "timeout_seconds",
        "network_policy",
        "allowed_writes",
        "external_side_effects",
        "success_criteria",
        "completeness_criteria",
        "absence_evidence",
    },
    "workPackage": {"wp_id", "blocked_by", "contract_refs", "source_refs", "command_refs"},
    "allowedWrite": {"path", "kind", "cleanup"},
    "externalEffect": {"target", "effect", "reversible", "authorization"},
    "absenceEvidence": {"probe", "outcome", "source_ref"},
    "bugAssessmentBinding": {"path", "sha256", "markdown_path", "markdown_sha256"},
    "partialSafeguards": {"reason", "proxy_bdd_refs", "proxy_test_refs", "residual_risks", "follow_up"},
    "bugContext": {
        "bug_id",
        "assessment",
        "reproduction_status",
        "root_cause_status",
        "root_cause_confidence",
        "verification_target",
        "original_reproduction_command_ref",
        "regression_bdd_refs",
        "regression_test_refs",
        "partial_safeguards",
    },
}

READY_OBJECT_REQUIRED = {
    "candidate": {"revision", "payload_sha256"},
    "approval": {"status", "actor", "confirmed_at", "evidence"},
    "planning_baseline": {"repo_id", "head_sha", "status_sha256"},
    "revision_impact": {"revision", "changes"},
}

LINK_RE = re.compile(r"!?(?<!\\)\[[^\]]*\]\(([^)]+)\)")
AUTHORITY_RE = re.compile(r"<!--\s*authority:\s*([a-z0-9-]+)\s*-->")
PARTIAL_OVERCLAIM_RE = re.compile(
    r"(?ix)(?:"
    r"\b(?:conclusive(?:ly)?|definitive(?:ly)?|certain(?:ly)?|remediated|validated|verified|confirmed|fixed|resolved|repaired|proven|eliminated|eradicated|corrected)\b"
    r"|\bno\s+longer\b"
    r"|\b(?:bug|defect|issue|symptom)\b.{0,20}\b(?:is|was)\s+(?:gone|absent|closed)\b"
    r"|\b(?:verified|confirmed|proven)\s+(?:(?:as|and)\s+|to\s+be\s+)?(?:fully\s+)?(?:fixed|resolved|repaired)\b"
    r"|\b(?:bug|defect|issue|symptom)\b.{0,32}\b(?:has\s+been|is|was)\s+(?:(?:now|already|successfully)\s+)*(?:fully\s+)?(?:fixed|resolved|repaired)\b"
    r"|\b(?:fixed|resolved|repaired)\s+(?:the\s+)?(?:bug|defect|issue|symptom)\b"
    r"|(?:BUG|錯誤|缺陷|問題|症狀)[^。；;\n]{0,24}(?:已(?:經)?(?:被)?(?:驗證|確認)(?:為|已)?|已(?:經)?)(?:完成)?(?:修復|解決|排除)"
    r"|(?:已|完全|徹底)[^。；;\n]{0,12}(?:修復|解決|排除|驗證|確認|消除|完成)"
    r")"
)
PARTIAL_REASON_UNCERTAINTY_RE = re.compile(
    r"(?ix)(?:\b(?:cannot|can\s+not|unable\s+to|not|never|intermittent|flaky|inconclusive|uncertain|unknown|low[- ]confidence|insufficient)\b|無法|未能|尚未|間歇|不穩定|不確定|未知|低信心|證據不足)"
)
PARTIAL_RISK_UNCERTAINTY_RE = re.compile(
    r"(?ix)(?:\b(?:may|might|could|risk|unknown|uncertain|inconclusive|unverified|intermittent|remain|persist)\b|可能|風險|未知|不確定|仍|尚未|未驗證|間歇)"
)
PARTIAL_FOLLOW_UP_ACTION_RE = re.compile(
    r"(?ix)(?:\b(?:verify|validate|test|run|check|observe|monitor|investigate|reproduce|measure|compare|collect)\b|confirm\s+whether|驗證|測試|執行|檢查|觀察|監控|調查|重現|量測|比對|蒐集|確認是否)"
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pointer(document: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise KeyError(f"unsupported non-local ref: {ref}")
    node = document
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def partial_overclaim(value: Any) -> bool:
    """Return whether partial-only prose asserts a conclusive fix."""
    return any(
        isinstance(candidate, str) and PARTIAL_OVERCLAIM_RE.search(candidate)
        for candidate in _walk(value)
    )


def partial_safeguard_prose_errors(safeguards: Any) -> list[str]:
    """Fail closed unless partial prose remains uncertain and action-oriented."""
    if not isinstance(safeguards, dict):
        return []
    errors: list[str] = []
    reason = safeguards.get("reason")
    if isinstance(reason, str) and reason and not PARTIAL_REASON_UNCERTAINTY_RE.search(reason):
        errors.append("partial reason lacks explicit uncertainty wording (overclaim risk)")
    residual_risks = safeguards.get("residual_risks")
    if isinstance(residual_risks, list):
        for index, value in enumerate(residual_risks):
            if isinstance(value, str) and value and not PARTIAL_RISK_UNCERTAINTY_RE.search(value):
                errors.append(
                    f"partial residual_risks[{index}] lacks an uncertainty or risk marker (overclaim risk)"
                )
    follow_up = safeguards.get("follow_up")
    if isinstance(follow_up, list):
        for index, value in enumerate(follow_up):
            if isinstance(value, str) and value and not PARTIAL_FOLLOW_UP_ACTION_RE.search(value):
                errors.append(
                    f"partial follow_up[{index}] lacks an explicit verification action (overclaim risk)"
                )
    return errors


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_instance(instance: Any, schema: dict[str, Any], definition: str | None = None) -> list[str]:
    """Validate the JSON-Schema subset used by these contracts without dependencies."""
    root = schema
    node = schema["$defs"][definition] if definition else schema
    errors: list[str] = []

    def check(value: Any, rule: dict[str, Any], location: str) -> None:
        if "$ref" in rule:
            try:
                check(value, _pointer(root, rule["$ref"]), location)
            except KeyError as exc:
                errors.append(f"{location}: {exc}")
            return

        for keyword in ("allOf",):
            for child in rule.get(keyword, []):
                check(value, child, location)

        for keyword in ("anyOf", "oneOf"):
            if keyword not in rule:
                continue
            matches = 0
            branch_messages: list[list[str]] = []
            for child in rule[keyword]:
                before = len(errors)
                check(value, child, location)
                branch_messages.append(errors[before:])
                del errors[before:]
                if not branch_messages[-1]:
                    matches += 1
            required_matches = 1 if keyword == "oneOf" else None
            if matches == 0 or (required_matches is not None and matches != required_matches):
                errors.append(f"{location}: {keyword} matched {matches} branches")

        if "if" in rule:
            before = len(errors)
            check(value, rule["if"], location)
            condition_matches = len(errors) == before
            del errors[before:]
            branch = rule.get("then" if condition_matches else "else")
            if branch:
                check(value, branch, location)

        if "const" in rule and value != rule["const"]:
            errors.append(f"{location}: expected const {rule['const']!r}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{location}: value {value!r} is outside enum")

        expected_types = rule.get("type")
        if expected_types:
            choices = [expected_types] if isinstance(expected_types, str) else expected_types
            if not any(_type_matches(value, choice) for choice in choices):
                errors.append(f"{location}: expected type {choices}, got {type(value).__name__}")
                return

        if isinstance(value, dict):
            for name in rule.get("required", []):
                if name not in value:
                    errors.append(f"{location}: missing required property {name}")
            properties = rule.get("properties", {})
            if rule.get("additionalProperties") is False:
                for name in value.keys() - properties.keys():
                    errors.append(f"{location}: unexpected property {name}")
            additional_rule = rule.get("additionalProperties")
            for name, child in value.items():
                child_rule = properties.get(name)
                if child_rule is None and isinstance(additional_rule, dict):
                    child_rule = additional_rule
                if child_rule:
                    check(child, child_rule, f"{location}.{name}")
            if len(value) < rule.get("minProperties", 0):
                errors.append(f"{location}: too few properties")

        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0):
                errors.append(f"{location}: too few items")
            if "maxItems" in rule and len(value) > rule["maxItems"]:
                errors.append(f"{location}: too many items")
            if "items" in rule:
                for index, child in enumerate(value):
                    check(child, rule["items"], f"{location}[{index}]")

        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0):
                errors.append(f"{location}: string is too short")
            if "pattern" in rule and not re.search(rule["pattern"], value):
                errors.append(f"{location}: does not match {rule['pattern']}")

        if isinstance(value, int) and not isinstance(value, bool) and "minimum" in rule:
            if value < rule["minimum"]:
                errors.append(f"{location}: below minimum {rule['minimum']}")

    check(instance, node, definition or "$")
    return errors


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def ready_payload_sha256(data: dict[str, Any]) -> str:
    payload = copy.deepcopy(data)
    payload.get("candidate", {}).pop("payload_sha256", None)
    payload["approval"] = {"status": "Candidate", "actor": None, "confirmed_at": None, "evidence": None}
    for artifact in payload.get("artifacts", []):
        artifact["approval_status"] = "Candidate"
    return canonical_sha256(payload)


def repository_path_error(value: Any, *, allow_dot: bool = False, allow_trailing_slash: bool = False) -> str | None:
    """Return why a manifest path cannot stay inside the canonical worktree."""
    if not isinstance(value, str) or not value:
        return "is empty or not a string"
    if value == ".":
        return None if allow_dot else "uses '.' outside command cwd"
    if "\\" in value:
        return "uses a backslash separator"
    if value.startswith("/") or ":" in value:
        return "is absolute, drive-relative, or URI-shaped"
    if value.endswith("/") and not allow_trailing_slash:
        return "has a trailing slash"
    candidate = value[:-1] if allow_trailing_slash and value.endswith("/") else value
    if any(segment in {"", ".", ".."} for segment in candidate.split("/")):
        return "contains an empty, '.', or '..' segment"
    return None


def validate_ready_cross_references(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def unique(items: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            value = item[key]
            if value in result:
                errors.append(f"ready: duplicate {label} {value}")
            result[value] = item
        return result

    artifacts = data.get("artifacts", [])
    artifact_paths = unique(artifacts, "path", "artifact path")
    for artifact in artifacts:
        reason = repository_path_error(artifact.get("path"))
        if reason:
            errors.append(f"ready: artifact path {artifact.get('path')!r} {reason}")
    primary_path = data.get("primary_plan", {}).get("path")
    reason = repository_path_error(primary_path)
    if reason:
        errors.append(f"ready: primary plan path {primary_path!r} {reason}")
    roles = [item.get("role") for item in artifacts]
    if roles.count("primary") != 1 or roles.count("handoff") != 1:
        errors.append("ready: artifact manifest needs exactly one primary and one handoff")
    approval = data.get("approval", {}).get("status")
    if any(item.get("approval_status") != approval for item in artifacts):
        errors.append("ready: artifact approval statuses differ from approval.status")
    if approval == "Ready":
        raw_time = data.get("approval", {}).get("confirmed_at")
        try:
            parsed_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            errors.append("ready: approval.confirmed_at is not an RFC 3339 date-time")
        else:
            if parsed_time.tzinfo is None:
                errors.append("ready: approval.confirmed_at has no timezone")
    primary = next((item for item in artifacts if item.get("role") == "primary"), None)
    if primary and data.get("primary_plan") != {"path": primary.get("path"), "sha256": primary.get("sha256")}:
        errors.append("ready: primary_plan does not match primary artifact")
    handoff = next((item for item in artifacts if item.get("role") == "handoff"), None)
    if handoff and handoff.get("sha256") is not None:
        errors.append("ready: handoff self hash must be null")
    if data.get("candidate", {}).get("payload_sha256") != ready_payload_sha256(data):
        errors.append("ready: Candidate payload digest does not match normalized handoff semantics")

    sources = unique(data.get("sources", []), "source_id", "source")
    contracts = unique(data.get("contract_index", []), "contract_id", "contract")
    commands = unique(data.get("commands", []), "command_id", "command")
    packages = unique(data.get("work_packages", []), "wp_id", "work package")

    required_purposes = {"bdd-discovery", "bdd-focused", "bdd-full", "tdd-focused", "related", "build-full", "test-full"}
    actual_purposes = {item.get("purpose") for item in commands.values()}
    if not required_purposes <= actual_purposes:
        errors.append(f"ready: missing command purposes {sorted(required_purposes - actual_purposes)}")

    family_kinds = {
        "BDD-FWK": "bdd-framework",
        "BOOT": "bootstrap",
        "BDD": "bdd-scenario",
        "TEST": "inner-test",
        "CMD": "command",
        "WP": "work-package",
    }

    def contract_family(contract_id: str) -> str | None:
        return next((family for family in family_kinds if contract_id.startswith(f"{family}-")), None)

    present_families: set[str] = set()
    for contract in contracts.values():
        family = contract_family(contract["contract_id"])
        if family is None:
            errors.append(f"ready: contract {contract['contract_id']} has no supported ID family")
            continue
        present_families.add(family)
        if contract.get("kind") != family_kinds[family]:
            errors.append(f"ready: contract {contract['contract_id']} kind does not match its ID family")
    required_families = {"BDD-FWK", "BDD", "TEST", "CMD", "WP"}
    if not required_families <= present_families:
        errors.append(f"ready: missing contract families {sorted(required_families - present_families)}")

    for source in sources.values():
        location = source.get("location", "")
        scheme = urlparse(location).scheme.lower()
        if scheme in {"chat", "conversation", "memory", "session", "tool"}:
            errors.append(f"ready: source {source['source_id']} uses a session-bound location")
        elif scheme == "file" or len(scheme) == 1:
            errors.append(f"ready: source {source['source_id']} uses a local location outside repository-path semantics")
        elif not scheme:
            reason = repository_path_error(location)
            if reason:
                errors.append(f"ready: source {source['source_id']} location {location!r} {reason}")
        if location in artifact_paths:
            artifact = artifact_paths[location]
            if artifact.get("role") != "supporting" or artifact.get("sha256") != source.get("sha256"):
                errors.append(f"ready: materialized source {source['source_id']} does not match its artifact hash")
        for wp_ref in source.get("wp_refs", []):
            if wp_ref not in packages:
                errors.append(f"ready: source {source['source_id']} references unknown {wp_ref}")
            elif source["source_id"] not in packages[wp_ref].get("source_refs", []):
                errors.append(f"ready: source {source['source_id']} and {wp_ref} mapping is not symmetric")
        source_wp_refs = set(source.get("wp_refs", []))
        for required_kind in ("bdd-scenario", "inner-test"):
            has_direct_shared_coverage = any(
                contract.get("kind") == required_kind
                and source["source_id"] in contract.get("source_refs", [])
                and bool(source_wp_refs.intersection(contract.get("wp_refs", [])))
                for contract in contracts.values()
            )
            if not has_direct_shared_coverage:
                errors.append(
                    f"ready: source {source['source_id']} has no direct "
                    f"{required_kind} contract sharing a WP"
                )
    for contract in contracts.values():
        for source_ref in contract.get("source_refs", []):
            if source_ref not in sources:
                errors.append(f"ready: contract {contract['contract_id']} references unknown {source_ref}")
        for wp_ref in contract.get("wp_refs", []):
            if wp_ref not in packages:
                errors.append(f"ready: contract {contract['contract_id']} references unknown {wp_ref}")
            elif contract["contract_id"] not in packages[wp_ref].get("contract_refs", []):
                errors.append(f"ready: contract {contract['contract_id']} and {wp_ref} mapping is not symmetric")
        if contract.get("kind") == "command":
            command_id = contract["contract_id"]
            if command_id not in commands:
                errors.append(f"ready: command contract {command_id} has no command object")
            for wp_ref in contract.get("wp_refs", []):
                if wp_ref in packages and command_id not in packages[wp_ref].get("command_refs", []):
                    errors.append(f"ready: command {command_id} and {wp_ref} command mapping is not symmetric")
    for command in commands.values():
        reason = repository_path_error(command.get("cwd"), allow_dot=True)
        if reason:
            errors.append(f"ready: command {command['command_id']} cwd {command.get('cwd')!r} {reason}")
        for allowed_write in command.get("allowed_writes", []):
            reason = repository_path_error(allowed_write.get("path"), allow_trailing_slash=True)
            if reason:
                errors.append(
                    f"ready: command {command['command_id']} allowed write {allowed_write.get('path')!r} {reason}"
                )
        if command["command_id"] not in contracts:
            errors.append(f"ready: command {command['command_id']} missing from contract index")
        elif contracts[command["command_id"]].get("kind") != "command":
            errors.append(f"ready: command {command['command_id']} has a non-command contract")
        expected_absence = bool(command.get("absence_evidence"))
        if (command.get("status") == "Proposed") != expected_absence:
            errors.append(f"ready: command {command['command_id']} has invalid absence evidence lifecycle")
        for evidence in command.get("absence_evidence", []):
            if evidence.get("source_ref") not in sources:
                errors.append(f"ready: command {command['command_id']} absence evidence has unknown source")

    bug_context = data.get("bug_context")
    bug_sources = [source for source in sources.values() if source.get("kind") == "bug"]
    bug_commands = [command for command in commands.values() if command.get("purpose") == "bug-reproduction"]
    if bug_context is None:
        if bug_sources or bug_commands:
            errors.append("ready: kind bug sources and bug-reproduction commands require bug_context")
    else:
        if len(bug_sources) != 1:
            errors.append("ready: bug_context requires exactly one kind bug assessment source")
        else:
            bug_source = bug_sources[0]
            assessment = bug_context.get("assessment", {})
            if (
                assessment.get("path") != bug_source.get("location")
                or assessment.get("sha256") != bug_source.get("sha256")
            ):
                errors.append("ready: bug_context assessment path/hash differs from kind bug source")
            bug_id = bug_context.get("bug_id")
            match = re.fullmatch(
                rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.json",
                str(assessment.get("path")),
            )
            markdown_match = re.fullmatch(
                rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.md",
                str(assessment.get("markdown_path")),
            )
            if (
                match is None
                or markdown_match is None
                or match.group(1) != markdown_match.group(1)
                or bug_source.get("revision") != (match.group(1) if match is not None else None)
            ):
                errors.append(
                    "ready: bug_context assessment paths must identify one bug revision using a canonical positive integer"
                )

        if not bug_commands:
            errors.append("ready: bug_context requires a bug-reproduction command")

        def validate_bug_contract_refs(field: str, expected_kind: str) -> None:
            for ref in bug_context.get(field, []):
                contract = contracts.get(ref)
                if contract is None:
                    errors.append(f"ready: bug_context {field} has unknown regression ref {ref}")
                elif contract.get("kind") != expected_kind:
                    errors.append(f"ready: bug_context {field} ref {ref} has wrong contract kind")
                elif bug_sources and bug_sources[0]["source_id"] not in contract.get("source_refs", []):
                    errors.append(f"ready: bug_context {field} ref {ref} is not owned by the bug source")

        validate_bug_contract_refs("regression_bdd_refs", "bdd-scenario")
        validate_bug_contract_refs("regression_test_refs", "inner-test")

        original_ref = bug_context.get("original_reproduction_command_ref")
        if original_ref is not None:
            original = commands.get(original_ref)
            if original is None or original.get("purpose") != "bug-reproduction":
                errors.append("ready: original reproduction command must reference purpose bug-reproduction")

        safeguards = bug_context.get("partial_safeguards", {})
        target = bug_context.get("verification_target")
        if target == "verified":
            if bug_context.get("reproduction_status") not in {"reproduced", "intermittent"}:
                errors.append("ready: verified target requires an original reproduced or intermittent symptom")
            if original_ref is None:
                errors.append("ready: verified target requires an original bug-reproduction command")
            if safeguards.get("reason") is not None or any(
                safeguards.get(field)
                for field in ("proxy_bdd_refs", "proxy_test_refs", "residual_risks", "follow_up")
            ):
                errors.append("ready: verified target must not carry partial safeguards")
        elif target == "partial":
            required_partial = {
                "reason": safeguards.get("reason"),
                "proxy_bdd_refs": safeguards.get("proxy_bdd_refs"),
                "proxy_test_refs": safeguards.get("proxy_test_refs"),
                "residual_risks": safeguards.get("residual_risks"),
                "follow_up": safeguards.get("follow_up"),
            }
            if any(not value for value in required_partial.values()):
                errors.append("ready: partial target requires reason, proxy red-green refs, residual risks and follow-up")
            for field in ("reason", "residual_risks", "follow_up"):
                if partial_overclaim(safeguards.get(field)):
                    errors.append(f"ready: partial {field} contains a verified-fix overclaim")
            errors.extend(
                f"ready: {error}"
                for error in partial_safeguard_prose_errors(safeguards)
            )
            if bug_context.get("root_cause_status") == "confirmed" or bug_context.get("root_cause_confidence") == "high":
                errors.append("ready: partial target must describe the approved low-confidence branch")
            for field, expected_kind in (("proxy_bdd_refs", "bdd-scenario"), ("proxy_test_refs", "inner-test")):
                for ref in safeguards.get(field, []):
                    contract = contracts.get(ref)
                    if contract is None:
                        errors.append(f"ready: partial {field} has unknown regression ref {ref}")
                    elif contract.get("kind") != expected_kind:
                        errors.append(f"ready: partial {field} ref {ref} has wrong contract kind")
                    elif bug_sources and bug_sources[0]["source_id"] not in contract.get("source_refs", []):
                        errors.append(f"ready: partial {field} ref {ref} is not owned by the bug source")
    for wp in packages.values():
        if wp["wp_id"] in wp.get("blocked_by", []):
            errors.append(f"ready: {wp['wp_id']} blocks itself")
        for ref in wp.get("blocked_by", []):
            if ref not in packages:
                errors.append(f"ready: {wp['wp_id']} has unknown blocker {ref}")
        for ref in wp.get("contract_refs", []):
            if ref not in contracts:
                errors.append(f"ready: {wp['wp_id']} has unknown contract {ref}")
            elif wp["wp_id"] not in contracts[ref].get("wp_refs", []):
                errors.append(f"ready: {wp['wp_id']} and contract {ref} mapping is not symmetric")
        for ref in wp.get("source_refs", []):
            if ref not in sources:
                errors.append(f"ready: {wp['wp_id']} has unknown source {ref}")
            elif wp["wp_id"] not in sources[ref].get("wp_refs", []):
                errors.append(f"ready: {wp['wp_id']} and source {ref} mapping is not symmetric")
        for ref in wp.get("command_refs", []):
            if ref not in commands:
                errors.append(f"ready: {wp['wp_id']} has unknown command {ref}")
            elif ref in contracts and wp["wp_id"] not in contracts[ref].get("wp_refs", []):
                errors.append(f"ready: {wp['wp_id']} and command {ref} mapping is not symmetric")
        if wp["wp_id"] not in contracts or contracts[wp["wp_id"]].get("kind") != "work-package":
            errors.append(f"ready: {wp['wp_id']} is missing its work-package contract")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(wp_id: str) -> None:
        if wp_id in visiting:
            errors.append(f"ready: work-package DAG contains a cycle at {wp_id}")
            return
        if wp_id in visited or wp_id not in packages:
            return
        visiting.add(wp_id)
        for dependency in packages[wp_id].get("blocked_by", []):
            visit(dependency)
        visiting.remove(wp_id)
        visited.add(wp_id)

    for wp_id in packages:
        visit(wp_id)

    known_plan_refs = {ref for source in sources.values() for ref in source.get("plan_refs", [])}
    known_impact_refs = set(sources) | set(contracts) | known_plan_refs
    global_command_purposes = {"bdd-discovery", "bdd-full", "build-full", "test-full", "governance", "ci"}
    global_contract_refs = {
        contract_id
        for contract_id, contract in contracts.items()
        if contract_family(contract_id) == "BDD-FWK" or len(set(contract.get("wp_refs", []))) > 1
    }
    global_contract_refs.update(
        command_id
        for command_id, command in commands.items()
        if command.get("purpose") in global_command_purposes
        or len(set(contracts.get(command_id, {}).get("wp_refs", []))) > 1
    )
    global_source_refs = {
        source_ref
        for contract_id in global_contract_refs
        for source_ref in contracts.get(contract_id, {}).get("source_refs", [])
    }
    global_source_refs.update(
        source_id for source_id, source in sources.items() if len(set(source.get("wp_refs", []))) > 1
    )
    global_plan_refs = {
        plan_ref
        for source_id in global_source_refs
        for plan_ref in sources.get(source_id, {}).get("plan_refs", [])
    }
    global_impact_refs = global_contract_refs | global_source_refs | global_plan_refs

    def downstream_closure(seed: set[str]) -> set[str]:
        closure = set(seed)
        changed = True
        while changed:
            changed = False
            for wp_id, package in packages.items():
                if wp_id not in closure and closure.intersection(package.get("blocked_by", [])):
                    closure.add(wp_id)
                    changed = True
        return closure

    for change in data.get("revision_impact", {}).get("changes", []):
        changed_ref = change.get("changed_ref")
        if changed_ref not in known_impact_refs:
            errors.append(f"ready: impact map has unknown ref {changed_ref}")
        for ref in change.get("affected_wp_refs", []):
            if ref not in packages:
                errors.append(f"ready: impact map has unknown work package {ref}")
        if change.get("scope") == "global-baseline" and set(change.get("affected_wp_refs", [])) != set(packages):
            errors.append("ready: global-baseline impact must enumerate every work package")
        if change.get("scope") == "wp-local":
            if changed_ref in global_impact_refs:
                errors.append(f"ready: {changed_ref} requires global-baseline impact")
            affected = set(change.get("affected_wp_refs", []))
            direct: set[str] = set()
            if changed_ref in sources:
                direct.update(sources[changed_ref].get("wp_refs", []))
            if changed_ref in contracts:
                direct.update(contracts[changed_ref].get("wp_refs", []))
            if changed_ref in packages:
                direct.add(changed_ref)
            for source in sources.values():
                if changed_ref in source.get("plan_refs", []):
                    direct.update(source.get("wp_refs", []))
            if not direct <= affected:
                errors.append(f"ready: wp-local impact for {changed_ref} omits direct work packages")
            closure = downstream_closure(affected)
            if closure != affected:
                errors.append(f"ready: wp-local impact for {changed_ref} omits downstream work packages")
    if data.get("revision_impact", {}).get("revision") != data.get("candidate", {}).get("revision"):
        errors.append("ready: revision impact map does not identify the Candidate revision")
    return errors


def _validate_schema_refs(schema: dict[str, Any], label: str, errors: list[str]) -> None:
    for node in _walk(schema):
        if isinstance(node, dict) and "$ref" in node:
            try:
                _pointer(schema, node["$ref"])
            except KeyError as exc:
                errors.append(f"{label}: unresolved $ref {node['$ref']}: {exc}")


def _required(node: dict[str, Any]) -> set[str]:
    return set(node.get("required", []))


def _validate_ready_schema(schema: dict[str, Any], errors: list[str]) -> None:
    if schema.get("properties", {}).get("schema", {}).get("const") != "ready-plan/v1":
        errors.append("ready schema: missing ready-plan/v1 const")
    if not READY_ROOT_REQUIRED <= _required(schema):
        errors.append(f"ready schema: missing root required fields {sorted(READY_ROOT_REQUIRED - _required(schema))}")
    for name, expected in READY_DEF_REQUIRED.items():
        actual = _required(schema.get("$defs", {}).get(name, {}))
        if not expected <= actual:
            errors.append(f"ready schema: {name} missing required fields {sorted(expected - actual)}")
    for name, expected in READY_OBJECT_REQUIRED.items():
        node = schema.get("properties", {}).get(name, {})
        actual = _required(node)
        if not expected <= actual:
            errors.append(f"ready schema: {name} missing required fields {sorted(expected - actual)}")

    defs = schema.get("$defs", {})
    role_enum = set(defs.get("artifact", {}).get("properties", {}).get("role", {}).get("enum", []))
    status_enum = set(defs.get("artifact", {}).get("properties", {}).get("approval_status", {}).get("enum", []))
    if role_enum != {"primary", "supporting", "handoff"}:
        errors.append("ready schema: artifact role enum drift")
    if status_enum != {"Candidate", "Ready"}:
        errors.append("ready schema: artifact approval_status enum drift")

    family_pattern = defs.get("contractId", {}).get("pattern", "")
    try:
        compiled = re.compile(family_pattern)
    except re.error as exc:
        errors.append(f"ready schema: invalid contract ID pattern: {exc}")
    else:
        for family in ("BDD-FWK", "BOOT", "BDD", "TEST", "CMD", "WP"):
            if not compiled.fullmatch(f"{family}-001"):
                errors.append(f"ready schema: contract ID family {family} is not resolvable")

    purpose_enum = set(defs.get("command", {}).get("properties", {}).get("purpose", {}).get("enum", []))
    required_purposes = set(schema.get("x-required-command-purposes", []))
    if "bdd-discovery" not in required_purposes or not required_purposes <= purpose_enum:
        errors.append("ready schema: required command purposes are incomplete or outside enum")
    if "bug-reproduction" not in purpose_enum:
        errors.append("ready schema: bug-reproduction purpose is missing")
    source_kind_enum = set(defs.get("source", {}).get("properties", {}).get("kind", {}).get("enum", []))
    if "bug" not in source_kind_enum:
        errors.append("ready schema: kind bug source is missing")
    bug_source_rules = defs.get("source", {}).get("allOf", [])
    if not any(
        rule.get("if", {}).get("properties", {}).get("kind", {}).get("const") == "bug"
        and rule.get("then", {}).get("properties", {}).get("revision", {}).get("pattern")
        == "^[1-9][0-9]*$"
        for rule in bug_source_rules
        if isinstance(rule, dict)
    ):
        errors.append("ready schema: kind bug source lacks a canonical positive revision rule")

    path_pattern = defs.get("normalizedPath", {}).get("pattern", "")
    try:
        path_re = re.compile(path_pattern)
    except re.error as exc:
        errors.append(f"ready schema: invalid normalized path pattern: {exc}")
    else:
        for value in (".", "docs/plans/plan.md", ".test-cache/"):
            if not path_re.fullmatch(value):
                errors.append(f"ready schema: normalized path pattern rejects valid value {value!r}")
        for value in ("../outside", "a/../outside", "a/./file", "/absolute", "C:/absolute", "a\\b", "a//b"):
            if path_re.fullmatch(value):
                errors.append(f"ready schema: normalized path pattern accepts unsafe value {value!r}")

    source_location = defs.get("source", {}).get("properties", {}).get("location", {})
    if source_location.get("$ref") != "#/$defs/sourceLocation":
        errors.append("ready schema: source.location does not use the sourceLocation contract")
    for value in ("../outside", "C:/absolute", "a\\b"):
        if not validate_instance(value, schema, "sourceLocation"):
            errors.append(f"ready schema: sourceLocation accepts unsafe local value {value!r}")

def _validate_links(skills_root: Path, errors: list[str]) -> None:
    for markdown in sorted(skills_root.glob("technical-planning/**/*.md")):
        for match in LINK_RE.finditer(markdown.read_text(encoding="utf-8")):
            raw = match.group(1).strip().strip("<>")
            target = raw.split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            if not (markdown.parent / unquote(target)).resolve().exists():
                errors.append(
                    f"broken local link: {markdown.relative_to(skills_root)} -> {target}"
                )


def _validate_authorities(skills_root: Path, errors: list[str]) -> None:
    found: dict[str, list[str]] = {}
    for markdown in sorted(skills_root.glob("technical-planning/**/*.md")):
        relative = markdown.relative_to(skills_root).as_posix()
        for name in AUTHORITY_RE.findall(markdown.read_text(encoding="utf-8")):
            found.setdefault(name, []).append(relative)
    for name, expected in AUTHORITY_FILES.items():
        actual = found.get(name, [])
        if actual != [expected]:
            errors.append(f"authority {name!r}: expected [{expected}], got {actual}")
    for name in found.keys() - AUTHORITY_FILES.keys():
        errors.append(f"unknown authority marker {name!r} in {found[name]}")


def _validate_structural_pointers(skills_root: Path, errors: list[str]) -> None:
    required_fragments = {
        "technical-planning/references/behavior-evaluation.md": [
            ".agents/skills/technical-planning/scripts/validate_contracts.py",
            ".agents/skills/technical-planning/scripts/test_validate_contracts.py",
        ],
        "technical-planning/agents/openai.yaml": [
            "allow_implicit_invocation: true",
            "$technical-planning",
        ],
    }
    for relative, fragments in required_fragments.items():
        path = skills_root / relative
        if not path.is_file():
            errors.append(f"missing structural pointer owner: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in text:
                errors.append(f"{relative}: missing structural pointer {fragment}")


def validate_all(skills_root: Path) -> list[str]:
    skills_root = skills_root.resolve()
    errors: list[str] = []
    ready_path = skills_root / "technical-planning/references/ready-plan.schema.json"
    if not ready_path.is_file():
        return [f"missing schema: {ready_path}"]
    if hashlib.sha256(ready_path.read_bytes()).hexdigest() != READY_SCHEMA_SHA256:
        errors.append("ready-plan/v1 schema bytes drifted")
    try:
        ready = _json(ready_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"schema parse failed: {exc}"]
    if not ready.get("$id"):
        errors.append("ready schema $id must be present")
    _validate_links(skills_root, errors)
    _validate_authorities(skills_root, errors)
    _validate_structural_pointers(skills_root, errors)
    _validate_schema_refs(ready, "ready schema", errors)
    _validate_ready_schema(ready, errors)
    return errors

def _default_skills_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=_default_skills_root())
    args = parser.parse_args(argv)
    errors = validate_all(args.skills_root)
    if errors:
        print(f"contract validation failed ({len(errors)}):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("technical-planning contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
