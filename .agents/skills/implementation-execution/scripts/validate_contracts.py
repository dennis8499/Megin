#!/usr/bin/env python3
"""Consumer-owned validation for execution records, review, and runtime docs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote


SKILLS_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
TECHNICAL_VALIDATOR_PATH = (
    SKILLS_ROOT_DEFAULT / "technical-planning" / "scripts" / "validate_contracts.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "implementation_shared_schema_validator", TECHNICAL_VALIDATOR_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot import {TECHNICAL_VALIDATOR_PATH}")
_shared = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_shared)

validate_instance = _shared.validate_instance
canonical_sha256 = _shared.canonical_sha256
_pointer = _shared._pointer
_walk = _shared._walk
_required = _shared._required
_validate_schema_refs = _shared._validate_schema_refs
partial_overclaim = _shared.partial_overclaim
partial_safeguard_prose_errors = _shared.partial_safeguard_prose_errors

EXECUTION_SCHEMA_SHA256 = "3ccb5203e141068d0d68bb9b58f528d2d342ef52f682bf88557cc5acea5c54f3"
AUTHORITY_FILES = {
    "implementation-entrypoint": "implementation-execution/SKILL.md",
    "execution-ledger": "implementation-execution/references/preflight-and-ledger.md",
    "execution-orchestrated-delivery": "implementation-execution/references/orchestrated-delivery.md",
    "execution-resume-revision": "implementation-execution/references/resume-and-revision.md",
    "execution-bootstrap": "implementation-execution/references/greenfield-bootstrap.md",
    "execution-loop": "implementation-execution/references/bdd-tdd-loop.md",
    "execution-review": "implementation-execution/references/reviewer-contract.md",
    "execution-quality": "implementation-execution/references/quality-contract.md",
    "execution-state": "implementation-execution/references/delivery-protocol.md",
}
EXECUTION_DEF_REQUIRED = {
    "ledger": {
        "schema",
        "run_id",
        "binding",
        "handoff_path",
        "capability_evidence_refs",
        "baseline_evidence_refs",
        "attempts",
        "current_attempt_id",
    },
    "snapshot": {
        "schema",
        "repo_id",
        "worktree_key",
        "base_sha",
        "head_sha",
        "ready_hashes",
        "source_hashes",
        "tracked_diff_sha256",
        "unignored_files",
        "snapshot_id",
    },
    "reviewReport": {
        "schema",
        "round",
        "verdict",
        "snapshot_before",
        "snapshot_after",
        "attestation",
        "command_outcomes",
        "raw_output_refs",
        "requirement_coverage",
        "findings",
        "summary",
    },
    "bugAssessmentBinding": {"path", "sha256", "markdown_path", "markdown_sha256"},
    "bugVerificationPlan": {"handoff_path", "candidate_revision", "verification_target"},
    "symptomEvidence": {"command_ref", "status", "evidence_refs"},
    "contractEvidence": {"bdd_refs", "test_refs", "red_evidence_refs", "green_evidence_refs"},
    "bugVerification": {
        "schema",
        "bug_id",
        "work_id",
        "result",
        "plan",
        "assessment",
        "original_reproduction",
        "regression",
        "proxy",
        "full_verification",
        "residual_risks",
        "follow_up",
        "implementation_review_ref",
        "summary",
        "created_at",
    },
    "outcomeChange": {"path", "sha256", "summary"},
    "outcomeVerification": {"command_id", "outcome", "evidence_refs"},
    "outcomeReview": {"verdict", "evidence_refs", "report_ref", "report_sha256"},
    "outcomeMarkdown": {"path", "sha256"},
    "bugOutcomeDetails": {
        "bug_id",
        "original_reproduction",
        "regression",
        "proxy",
        "residual_risks",
        "follow_up",
        "implementation_review_ref",
    },
    "implementationOutcome": {
        "schema",
        "work_id",
        "implementation_run_id",
        "revision",
        "work_kind",
        "result",
        "summary",
        "changes",
        "verification",
        "review",
        "known_deviations",
        "knowledge_decision",
        "bug_verification_ref",
        "bug",
        "markdown",
        "created_at",
    },
    "binding": {"repo_id", "canonical_worktree", "worktree_key", "branch", "initial_base_sha", "run_id"},
    "attempt": {"attempt_id", "candidate_revision", "state", "wp_states", "state_history"},
    "stateTransition": {"sequence", "from", "to", "evidence_refs"},
    "commandOutcome": {"command_id", "outcome", "exit_code", "failure_count", "skipped_count", "output_ref", "not_run_reason"},
    "reviewerAttestation": {"agent_id", "fresh_session", "read_only", "implementation_conversation_received", "delegation_used", "write_actions"},
    "findingKeyInputs": {"category", "source_refs", "affected_loci", "required_outcome"},
    "finding": {"finding_id", "finding_key", "key_inputs", "severity", "blocking", "message", "evidence_refs", "wp_refs", "bdd_refs", "test_refs"},
    "coverage": {"source_ref", "obligation_ref", "bdd_refs", "test_refs", "wp_refs", "code_evidence", "result"},
    "breakerFinding": {"finding_key", "consecutive_unresolved_rounds", "no_progress_rounds", "last_evidence_sha256"},
    "breaker": {"schema", "findings", "global_no_progress_rounds"},
}

EXPECTED_STATES = {
    "Preflight",
    "Executing",
    "Verifying",
    "Reviewing",
    "Fixing",
    "Complete",
    "Awaiting upstream reapproval",
    "Blocked",
}

EXPECTED_TRANSITIONS = {
    "Preflight": ["Executing", "Awaiting upstream reapproval", "Blocked"],
    "Executing": ["Verifying", "Awaiting upstream reapproval", "Blocked"],
    "Verifying": ["Reviewing", "Fixing", "Awaiting upstream reapproval", "Blocked"],
    "Reviewing": ["Complete", "Fixing", "Verifying", "Awaiting upstream reapproval", "Blocked"],
    "Fixing": ["Verifying", "Awaiting upstream reapproval", "Blocked"],
    "Complete": [],
    "Awaiting upstream reapproval": [],
    "Blocked": [],
}

REQUIRED_STATE_EDGES = {
    ("Preflight", "Executing"),
    ("Executing", "Verifying"),
    ("Verifying", "Reviewing"),
    ("Verifying", "Fixing"),
    ("Reviewing", "Complete"),
    ("Reviewing", "Fixing"),
    ("Reviewing", "Verifying"),
    ("Fixing", "Verifying"),
}

TERMINAL_ORDER = [
    "review_received",
    "snapshot_recomputed_before_persist",
    "snapshot_matched_before_persist",
    "report_persisted",
    "snapshot_recomputed_after_persist",
    "snapshot_matched_after_persist",
    "complete_appended",
]
TERMINAL_WITNESS_STEPS = TERMINAL_ORDER[:-1]
TERMINAL_WITNESS_REFS = [
    f"terminal/{sequence:02d}-{step}.json"
    for sequence, step in enumerate(TERMINAL_WITNESS_STEPS, 1)
]

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:secret|token|password|passwd|credential|api[-_.]?key|private[-_.]?key)\s*[:=]\s*\S{6,}"
)
SECRET_SENTINEL_RE = re.compile(
    r"\b(?:[A-Z0-9]+_)*(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY)_[A-Z0-9_-]{6,}\b"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
KNOWN_TOKEN_RE = re.compile(
    r"(?:\bAKIA[0-9A-Z]{16}\b|\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b)"
)
PARTIAL_VERIFICATION_SUMMARIES = frozenset(
    {
        "Proxy evidence passed; original symptom remains inconclusive.",
        "代理證據已通過；原始症狀仍無法確認。",
    }
)
PARTIAL_REVIEW_SUMMARIES = frozenset(
    {
        "Implementation approved; BUG verification is partial and the original symptom remains inconclusive.",
        "實作已核准；BUG 驗證結果為 partial，原始症狀仍無法確認。",
    }
)
COMPLETE_EXACT_REFS = {"source-manifest.json", "wp-ledger.json", "breaker.json"}

LINK_RE = re.compile(r"!?(?<!\\)\[[^\]]*\]\(([^)]+)\)")
AUTHORITY_RE = re.compile(r"<!--\s*authority:\s*([a-z0-9-]+)\s*-->")


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    if isinstance(value, dict):
        return [text for key, item in value.items() for text in (str(key), *_walk_strings(item))]
    return []


def validate_secret_free(
    value: Any,
    known_secret_values: tuple[str, ...] = (),
    *,
    label: str = "record",
) -> list[str]:
    """Reject exact known secrets and recognizable credential-shaped sentinels."""
    secrets = tuple(secret for secret in known_secret_values if isinstance(secret, str) and secret)
    for text in _walk_strings(value):
        if any(secret in text for secret in secrets):
            return [f"{label}: contains a known secret value"]
        if SECRET_ASSIGNMENT_RE.search(text) or SECRET_SENTINEL_RE.search(text) or KNOWN_TOKEN_RE.search(text):
            return [f"{label}: contains credential-shaped material"]
    return []


class _DuplicateRawJSONKey(ValueError):
    pass


def _reject_duplicate_raw_json_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateRawJSONKey("duplicate JSON object key")
        value[key] = item
    return value


def _raw_json_errors(
    raw: bytes,
    expected: dict[str, Any],
    known_secret_values: tuple[str, ...],
    *,
    label: str,
) -> list[str]:
    """Scan persisted bytes before parsing and reject ambiguous JSON objects."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return [f"{label}: raw JSON is not valid UTF-8"]
    errors = validate_secret_free(text, known_secret_values, label=f"{label} raw JSON")
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_raw_json_keys)
    except _DuplicateRawJSONKey:
        errors.append(f"{label}: raw JSON contains a duplicate object key")
    except json.JSONDecodeError:
        errors.append(f"{label}: raw JSON is invalid")
    else:
        if not isinstance(parsed, dict):
            errors.append(f"{label}: raw JSON is not an object")
        elif parsed != expected:
            errors.append(f"{label}: parsed record differs from raw JSON")
    return errors


def _canonical_evidence_ref(value: Any) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return "/".join(parts)


def _persisted_evidence_path(evidence_root: Path, relative: str) -> Path | None:
    root = evidence_root.resolve()
    is_junction = getattr(evidence_root, "is_junction", lambda: False)
    if evidence_root.is_symlink() or is_junction() or not root.is_dir():
        return None
    candidate = evidence_root.joinpath(*relative.split("/"))
    cursor = candidate
    while cursor != evidence_root:
        cursor_is_junction = getattr(cursor, "is_junction", lambda: False)
        if cursor.is_symlink() or cursor_is_junction():
            return None
        cursor = cursor.parent
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return resolved


def _read_json_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"terminal: {label} is not readable JSON")
        return None
    if not isinstance(value, dict):
        errors.append(f"terminal: {label} is not a JSON object")
        return None
    return value


def _execution_schema_document() -> dict[str, Any]:
    return json.loads(
        (Path(__file__).resolve().parents[1] / "references/execution-records.schema.json").read_text(
            encoding="utf-8"
        )
    )


def validate_terminal_evidence(
    ledger: dict[str, Any],
    evidence_root: Path,
    *,
    ready: dict[str, Any] | None = None,
    known_secret_values: tuple[str, ...] = (),
) -> list[str]:
    """Validate that a Complete terminal index names the exact persisted evidence set."""
    errors: list[str] = []
    attempts = ledger.get("attempts", [])
    attempt = next(
        (
            item
            for item in attempts
            if item.get("attempt_id") == ledger.get("current_attempt_id")
        ),
        None,
    )
    history = attempt.get("state_history", []) if isinstance(attempt, dict) else []
    if not history or attempt.get("state") != "Complete":
        return ["terminal: current Complete attempt is absent"]
    terminal_refs = history[-1].get("evidence_refs", [])
    support_refs = [
        *ledger.get("capability_evidence_refs", []),
        *ledger.get("baseline_evidence_refs", []),
    ]
    if not ledger.get("capability_evidence_refs"):
        errors.append("terminal: Complete requires persisted capability evidence")
    if not ledger.get("baseline_evidence_refs"):
        errors.append("terminal: Complete requires persisted baseline or absence evidence")
    raw_refs = [
        *terminal_refs,
        *support_refs,
        *[
            ref
            for transition in history[:-1]
            for ref in transition.get("evidence_refs", [])
            if isinstance(ref, str)
            and ref.startswith("integrity/")
            and ref.endswith("ready-source.json")
        ],
    ]
    terminal_ref_set = {ref for ref in terminal_refs if isinstance(ref, str)}
    paths: dict[str, Path] = {}
    for raw_ref in raw_refs:
        relative = _canonical_evidence_ref(raw_ref)
        if relative is None or relative != raw_ref:
            errors.append("terminal: evidence ref is not a canonical Ledger-relative path")
            continue
        if relative in paths:
            errors.append(f"terminal: duplicate evidence ref {relative}")
            continue
        path = _persisted_evidence_path(evidence_root, relative)
        if path is None:
            errors.append(f"terminal: evidence is not persisted: {relative}")
            continue
        paths[relative] = path
        try:
            raw = path.read_bytes()
        except OSError:
            errors.append(f"terminal: evidence is unreadable: {relative}")
            continue
        errors.extend(
            validate_secret_free(
                raw.decode("utf-8", errors="replace"),
                known_secret_values,
                label=f"terminal evidence {relative}",
            )
        )

    capability_refs = ledger.get("capability_evidence_refs", [])
    if capability_refs:
        capability_path = paths.get(capability_refs[0])
        capability = (
            _read_json_object(capability_path, "capability record", errors)
            if capability_path is not None
            else None
        )
        expected_capability = {
            "schema": "implementation-capability/v1",
            "run_id": ledger.get("run_id"),
            "checks": {
                "fresh_reviewer": "passed",
                "git_workspace": "passed",
                "toolchain": "passed",
            },
            "evidence_refs": capability_refs[1:],
        }
        if capability != expected_capability or not capability_refs[1:]:
            errors.append("terminal: capability evidence is not canonical or has no raw evidence")

    baseline_refs = ledger.get("baseline_evidence_refs", [])
    if baseline_refs:
        baseline_path = paths.get(baseline_refs[0])
        baseline = (
            _read_json_object(baseline_path, "baseline record", errors)
            if baseline_path is not None
            else None
        )
        if (
            baseline is None
            or baseline.get("schema") != "implementation-baseline/v1"
            or baseline.get("run_id") != ledger.get("run_id")
            or baseline.get("outcome") not in {"passed", "not_applicable"}
            or baseline.get("evidence_refs") != baseline_refs[1:]
            or not baseline_refs[1:]
            or set(baseline) != {"schema", "run_id", "outcome", "evidence_refs"}
        ):
            errors.append("terminal: baseline evidence is not canonical or has no raw evidence")

    expected_source_hashes = (
        sorted(
            (
                {"ref": item.get("source_id"), "sha256": item.get("sha256")}
                for item in ready.get("sources", [])
            ),
            key=lambda item: str(item["ref"]),
        )
        if ready is not None
        else None
    )
    integrity_context: dict[str, tuple[Any, Any]] = {}
    for transition in history:
        for ref in transition.get("evidence_refs", []):
            if (
                isinstance(ref, str)
                and ref.startswith("integrity/")
                and ref.endswith("ready-source.json")
            ):
                integrity_context[ref] = (
                    attempt.get("attempt_id"),
                    transition.get("sequence"),
                )
    for relative, (attempt_id, transition_sequence) in integrity_context.items():
        path = paths.get(relative)
        integrity = (
            _read_json_object(path, f"integrity witness {relative}", errors)
            if path is not None
            else None
        )
        if integrity is None:
            continue
        if (
            set(integrity)
            != {
                "schema",
                "scope",
                "attempt_id",
                "transition_sequence",
                "ready_sha256",
                "source_hashes",
            }
            or integrity.get("schema") != "implementation-integrity/v1"
            or integrity.get("scope") != relative
            or integrity.get("attempt_id") != attempt_id
            or integrity.get("transition_sequence") != transition_sequence
            or not SHA256_RE.fullmatch(str(integrity.get("ready_sha256", "")))
        ):
            errors.append(f"terminal: integrity witness is not canonical: {relative}")
            continue
        source_hashes = integrity.get("source_hashes")
        source_hash_items_valid = isinstance(source_hashes, list) and all(
            isinstance(item, dict)
            and set(item) == {"ref", "sha256"}
            and isinstance(item.get("ref"), str)
            and SHA256_RE.fullmatch(str(item.get("sha256", "")))
            for item in source_hashes
        )
        if (
            not source_hash_items_valid
            or source_hashes != sorted(source_hashes, key=lambda item: item["ref"])
            or len({item["ref"] for item in source_hashes}) != len(source_hashes)
        ):
            errors.append(f"terminal: integrity witness has invalid source hashes: {relative}")
        if ready is not None and (
            integrity.get("ready_sha256") != canonical_sha256(ready)
            or source_hashes != expected_source_hashes
        ):
            errors.append(f"terminal: integrity witness differs from Ready: {relative}")

    report_refs = sorted(
        ref
        for ref in paths
        if ref in terminal_ref_set and re.fullmatch(r"reviews/[^/]+/report\.json", ref)
    )
    if len(report_refs) != 1:
        errors.append("terminal: index must contain exactly one current review report")
        return errors
    report_ref = report_refs[0]
    report = _read_json_object(paths[report_ref], "review report", errors)
    if report is None:
        return errors
    execution_schema: dict[str, Any] | None = None
    try:
        execution_schema = _execution_schema_document()
        errors.extend(validate_instance(report, execution_schema, "reviewReport"))
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        errors.append("terminal: review schema validation could not complete")
    errors.extend(
        validate_execution_record_semantics(
            report,
            known_secret_values=known_secret_values,
        )
    )
    if ready is not None:
        errors.extend(validate_review_against_ready(report, ready, known_secret_values))
    if report.get("verdict") != "APPROVED":
        errors.append("terminal: Complete requires an APPROVED review report")

    review_root = report_ref.rsplit("/", 1)[0]
    raw_response_refs = {
        ref
        for ref in paths
        if ref in terminal_ref_set
        and re.fullmatch(re.escape(review_root) + r"/raw-response(?:\.[^/]+)?", ref)
    }
    if len(raw_response_refs) != 1:
        errors.append("terminal: index must persist exactly one current raw response")
    terminal_output_refs = {
        ref
        for ref in paths
        if ref in terminal_ref_set and ref.startswith(f"{review_root}/outputs/")
    }
    report_output_refs: set[str] = set()
    for raw_ref in report.get("raw_output_refs", []):
        relative = _canonical_evidence_ref(raw_ref)
        if relative is None or relative != raw_ref:
            errors.append("terminal: report raw_output_refs are not canonical Ledger paths")
            continue
        report_output_refs.add(relative)
    if terminal_output_refs != report_output_refs:
        errors.append("terminal: index does not equal every raw output named by the report")
    if any(not ref.startswith(f"{review_root}/outputs/") for ref in report_output_refs):
        errors.append("terminal: raw outputs are not scoped to the current review round")

    snapshot_refs = sorted(
        ref
        for ref in paths
        if ref in terminal_ref_set and ref.startswith("diffs/") and "snapshot" in ref
    )
    if len(snapshot_refs) != 1:
        errors.append("terminal: index must contain exactly one reviewed snapshot")
    else:
        snapshot = _read_json_object(paths[snapshot_refs[0]], "reviewed snapshot", errors)
        if snapshot is not None:
            try:
                if execution_schema is None:
                    raise ValueError("execution schema unavailable")
                errors.extend(validate_instance(snapshot, execution_schema, "snapshot"))
                errors.extend(validate_execution_record_semantics(snapshot))
            except (KeyError, TypeError, ValueError):
                errors.append("terminal: snapshot validation could not complete")
            snapshot_id = snapshot.get("snapshot_id")
            if report.get("snapshot_before") != snapshot_id or report.get("snapshot_after") != snapshot_id:
                errors.append("terminal: review snapshots do not identify the persisted snapshot")

    command_index_refs = sorted(
        ref
        for ref in paths
        if ref in terminal_ref_set and ref == "commands/full-verification.json"
    )
    if len(command_index_refs) != 1:
        errors.append("terminal: index must contain exactly one full command index")
    else:
        command_index = _read_json_object(
            paths[command_index_refs[0]],
            "full command index",
            errors,
        )
        entries = command_index.get("commands", []) if command_index is not None else []
        if not isinstance(entries, list) or not entries:
            errors.append("terminal: full command index has no main-executor commands")
            entries = []
        command_ids: list[Any] = []
        declared_main_outputs: set[str] = set()
        declared_main_output_list: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append("terminal: full command index contains a non-object command")
                continue
            command_ids.append(entry.get("command_id"))
            if not isinstance(entry.get("command_id"), str) or not entry.get("command_id"):
                errors.append("terminal: full command index has an invalid command ID")
            if (
                entry.get("outcome") != "passed"
                or entry.get("exit_code") != 0
                or entry.get("failure_count") != 0
                or entry.get("skipped_count") != 0
            ):
                errors.append(
                    f"terminal: main command {entry.get('command_id')} is not a complete pass"
                )
            for field in ("stdout_ref", "stderr_ref"):
                ref = entry.get(field)
                relative = _canonical_evidence_ref(ref)
                if (
                    relative is None
                    or relative != ref
                    or not relative.startswith("commands/sequence/")
                ):
                    errors.append(
                        f"terminal: main command {entry.get('command_id')} has invalid {field}"
                    )
                    continue
                declared_main_outputs.add(relative)
                declared_main_output_list.append(relative)
        if len(command_ids) != len(set(command_ids)):
            errors.append("terminal: full command index has duplicate command IDs")
        if len(declared_main_output_list) != len(declared_main_outputs):
            errors.append("terminal: main command raw output refs are reused")
        terminal_main_outputs = {
            ref
            for ref in paths
            if ref in terminal_ref_set and ref.startswith("commands/sequence/")
        }
        if terminal_main_outputs != declared_main_outputs:
            errors.append("terminal: index does not equal every main command raw output")
        if ready is not None:
            required_main_commands = {
                item.get("command_id")
                for item in ready.get("commands", [])
                if item.get("purpose")
                in {"build-full", "test-full", "bdd-full", "governance", "ci"}
            }
            if set(command_ids) != required_main_commands:
                errors.append("terminal: main command index differs from Ready full commands")

    witness_positions: list[int] = []
    for expected_ref in TERMINAL_WITNESS_REFS:
        if expected_ref not in terminal_ref_set:
            errors.append(f"terminal: ordering witness is missing: {expected_ref}")
            continue
        witness_positions.append(terminal_refs.index(expected_ref))
    if witness_positions != sorted(witness_positions):
        errors.append("terminal: ordering witnesses are not in canonical sequence")

    expected_witness_evidence = {
        "review_received": sorted(raw_response_refs),
        "snapshot_recomputed_before_persist": snapshot_refs,
        "snapshot_matched_before_persist": snapshot_refs,
        "report_persisted": [
            *sorted(raw_response_refs),
            *sorted(report_output_refs),
            report_ref,
        ],
        "snapshot_recomputed_after_persist": snapshot_refs,
        "snapshot_matched_after_persist": snapshot_refs,
    }
    for sequence, (step, relative) in enumerate(
        zip(TERMINAL_WITNESS_STEPS, TERMINAL_WITNESS_REFS),
        1,
    ):
        path = paths.get(relative)
        if path is None:
            continue
        witness = _read_json_object(path, f"ordering witness {step}", errors)
        if witness is None:
            continue
        if witness != {
            "sequence": sequence,
            "step": step,
            "evidence_refs": expected_witness_evidence[step],
        }:
            errors.append(f"terminal: ordering witness {step} is not canonical")

    if ready is not None:
        manifest_path = paths.get("source-manifest.json")
        if manifest_path is not None:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                manifest = None
            if manifest != ready.get("sources"):
                errors.append("terminal: source manifest differs from the Ready sources")
        wp_path = paths.get("wp-ledger.json")
        if wp_path is not None:
            try:
                wp_ledger = json.loads(wp_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                wp_ledger = None
            if wp_ledger != attempt.get("wp_states"):
                errors.append("terminal: WP Ledger differs from the Complete attempt")

    breaker_path = paths.get("breaker.json")
    if breaker_path is not None:
        breaker = _read_json_object(breaker_path, "breaker", errors)
        report_chain: list[dict[str, Any]] = []
        reviews_root = evidence_root / "reviews"
        if reviews_root.is_dir():
            for candidate in reviews_root.glob("*/report.json"):
                try:
                    relative = candidate.relative_to(evidence_root).as_posix()
                except ValueError:
                    continue
                persisted = _persisted_evidence_path(evidence_root, relative)
                if persisted is None:
                    errors.append("terminal: review report chain contains a redirected entry")
                    continue
                item = _read_json_object(persisted, f"review chain {relative}", errors)
                if item is not None:
                    report_chain.append(item)
        report_chain.sort(key=lambda item: item.get("round", 0))
        if breaker is not None:
            errors.extend(
                validate_execution_record_semantics(
                    breaker,
                    breaker_reports=report_chain,
                    known_secret_values=known_secret_values,
                )
            )
    return errors


def _complete_index_errors(attempt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    history = attempt.get("state_history", [])
    refs = history[-1].get("evidence_refs", []) if history else []
    ref_set = {ref for ref in refs if isinstance(ref, str)}
    missing_exact = COMPLETE_EXACT_REFS - ref_set
    if missing_exact:
        errors.append(f"ledger: Complete terminal index missing {sorted(missing_exact)}")
    missing_witnesses = set(TERMINAL_WITNESS_REFS) - ref_set
    if missing_witnesses:
        errors.append(
            f"ledger: Complete terminal index missing ordering witnesses {sorted(missing_witnesses)}"
        )
    required_predicates = {
        "full command index": lambda ref: ref == "commands/full-verification.json",
        "main command raw outputs": lambda ref: ref.startswith("commands/sequence/"),
        "reviewed diff snapshot": lambda ref: ref.startswith("diffs/") and "snapshot" in ref,
        "review raw response": lambda ref: ref.startswith("reviews/") and "/raw-response" in ref,
        "review raw outputs": lambda ref: ref.startswith("reviews/") and "/outputs/" in ref,
        "review report": lambda ref: ref.startswith("reviews/") and ref.endswith("/report.json"),
    }
    for label, predicate in required_predicates.items():
        if not any(predicate(ref) for ref in ref_set):
            errors.append(f"ledger: Complete terminal index missing {label}")
    for wp_id, state in attempt.get("wp_states", {}).items():
        if state != "Verified":
            errors.append(f"ledger: Complete requires {wp_id} to be Verified")
            continue
        for boundary in ("start", "complete"):
            expected = f"integrity/{wp_id}/{boundary}-ready-source.json"
            if expected not in ref_set:
                errors.append(f"ledger: Complete terminal index missing {expected}")
    return errors


def finding_key(key_inputs: dict[str, Any]) -> str:
    normalize_text = lambda value: " ".join(value.strip().split())
    normalized = {
        "category": normalize_text(key_inputs["category"]).lower(),
        "source_refs": sorted({normalize_text(item) for item in key_inputs["source_refs"]}),
        "affected_loci": sorted(
            {normalize_text(item).replace("\\", "/") for item in key_inputs["affected_loci"]}
        ),
        "required_outcome": normalize_text(key_inputs["required_outcome"]),
    }
    return canonical_sha256(normalized)


def validate_bug_verification_against_ready(
    record: dict[str, Any],
    ready: dict[str, Any],
    *,
    expected_work_id: str | None = None,
    expected_handoff_path: str | None = None,
    known_secret_values: tuple[str, ...] = (),
    raw_json_bytes: bytes | None = None,
    evidence_root: Path | None = None,
    terminal_evidence_refs: Sequence[str] | None = None,
) -> list[str]:
    """Validate a BUG result independently from implementation approval."""
    errors = validate_secret_free(
        [ready, record],
        known_secret_values,
        label="Ready/BUG verification records",
    )
    if raw_json_bytes is not None:
        errors.extend(
            _raw_json_errors(
                raw_json_bytes,
                record,
                known_secret_values,
                label="BUG verification",
            )
        )
    context = ready.get("bug_context")
    if not isinstance(context, dict):
        return [*errors, "BUG verification: Ready plan has no bug_context"]

    if record.get("schema") != "bug-verification/v1":
        errors.append("BUG verification: schema must be bug-verification/v1")
    if record.get("bug_id") != context.get("bug_id"):
        errors.append("BUG verification: bug_id differs from Ready bug_context")
    if expected_work_id is not None and record.get("work_id") != expected_work_id:
        errors.append("BUG verification: work_id differs from delivery run")
    plan = record.get("plan", {})
    if expected_handoff_path is not None and plan.get("handoff_path") != expected_handoff_path:
        errors.append("BUG verification: handoff_path differs from the approved Ready handoff")
    if plan.get("candidate_revision") != ready.get("candidate", {}).get("revision"):
        errors.append("BUG verification: candidate revision differs from Ready")
    target = context.get("verification_target")
    if plan.get("verification_target") != target:
        errors.append("BUG verification: verification target differs from Ready")
    if record.get("assessment") != context.get("assessment"):
        errors.append("BUG verification: assessment binding differs from Ready")
    assessment = context.get("assessment", {})
    bug_id = context.get("bug_id")
    assessment_match = re.fullmatch(
        rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.json",
        str(assessment.get("path")),
    )
    markdown_match = re.fullmatch(
        rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.md",
        str(assessment.get("markdown_path")),
    )
    if (
        assessment_match is None
        or markdown_match is None
        or assessment_match.group(1) != markdown_match.group(1)
    ):
        errors.append("BUG verification: Ready assessment revision must be a canonical positive integer")

    result = record.get("result")
    if result in {"verified", "partial"} and result != target:
        errors.append("BUG verification: successful result exceeds or differs from the approved target")

    regression = record.get("regression", {})
    if set(regression.get("bdd_refs", [])) != set(context.get("regression_bdd_refs", [])):
        errors.append("BUG verification: regression BDD refs differ from Ready")
    if set(regression.get("test_refs", [])) != set(context.get("regression_test_refs", [])):
        errors.append("BUG verification: regression TEST refs differ from Ready")

    full_outcomes = record.get("full_verification", [])
    full_ids = [outcome.get("command_id") for outcome in full_outcomes]
    if len(full_ids) != len(set(full_ids)):
        errors.append("BUG verification: duplicate full verification command")
    known_commands = {command.get("command_id") for command in ready.get("commands", [])}
    unknown = set(full_ids) - known_commands
    if unknown:
        errors.append(f"BUG verification: unknown full verification commands {sorted(unknown)}")
    required_purposes = {"build-full", "test-full", "bdd-full", "governance", "ci"}
    required_full = {
        command.get("command_id")
        for command in ready.get("commands", [])
        if command.get("purpose") in required_purposes
    }
    missing_full = required_full - set(full_ids)
    if missing_full:
        errors.append(f"BUG verification: missing full verification commands {sorted(missing_full)}")

    original = record.get("original_reproduction", {})
    pre_fix = original.get("pre_fix", {})
    post_fix = original.get("post_fix", {})
    proxy = record.get("proxy", {})
    safeguards = context.get("partial_safeguards", {})

    if result in {"verified", "partial"}:
        if not regression.get("red_evidence_refs"):
            errors.append("BUG verification: successful result requires regression red evidence")
        if not regression.get("green_evidence_refs"):
            errors.append("BUG verification: successful result requires regression green evidence")
        if any(outcome.get("outcome") != "passed" for outcome in full_outcomes):
            errors.append("BUG verification: successful result requires every full verification command to pass")

    if result == "verified":
        original_command = context.get("original_reproduction_command_ref")
        if (
            pre_fix.get("command_ref") != original_command
            or pre_fix.get("status") != "present"
            or not pre_fix.get("evidence_refs")
        ):
            errors.append("BUG verification: verified requires pre-fix original reproduction evidence with symptom present")
        if (
            post_fix.get("command_ref") != original_command
            or post_fix.get("status") != "absent"
            or not post_fix.get("evidence_refs")
        ):
            errors.append("BUG verification: verified requires post-fix original reproduction evidence with symptom absent")
        if any(proxy.get(field) for field in ("bdd_refs", "test_refs", "red_evidence_refs", "green_evidence_refs")):
            errors.append("BUG verification: verified must not substitute proxy evidence for the original symptom")
    elif result == "partial":
        if post_fix.get("status") not in {"inconclusive", "not-run"}:
            errors.append("BUG verification: partial must keep the original post-fix symptom result inconclusive")
        if not pre_fix.get("evidence_refs") or not post_fix.get("evidence_refs"):
            errors.append("BUG verification: partial requires original reproduction attempt evidence")
        if (
            set(proxy.get("bdd_refs", [])) != set(safeguards.get("proxy_bdd_refs", []))
            or set(proxy.get("test_refs", [])) != set(safeguards.get("proxy_test_refs", []))
            or not proxy.get("red_evidence_refs")
            or not proxy.get("green_evidence_refs")
        ):
            errors.append("BUG verification: partial requires the approved proxy red→green evidence")
        if not record.get("residual_risks") or not set(safeguards.get("residual_risks", [])).issubset(record.get("residual_risks", [])):
            errors.append("BUG verification: partial requires all approved residual risks")
        if not record.get("follow_up") or not set(safeguards.get("follow_up", [])).issubset(record.get("follow_up", [])):
            errors.append("BUG verification: partial requires all approved follow-up verification")
        partial_prose = {
            "Ready reason": safeguards.get("reason"),
            "Ready residual risks": safeguards.get("residual_risks"),
            "Ready follow-up": safeguards.get("follow_up"),
            "verification residual risks": record.get("residual_risks"),
            "verification follow-up": record.get("follow_up"),
        }
        for label, value in partial_prose.items():
            if partial_overclaim(value):
                errors.append(f"BUG verification: partial {label} contains a verified-fix overclaim")
        errors.extend(
            f"BUG verification: Ready {error}"
            for error in partial_safeguard_prose_errors(safeguards)
        )
        errors.extend(
            f"BUG verification: record {error}"
            for error in partial_safeguard_prose_errors(
                {
                    "reason": safeguards.get("reason"),
                    "residual_risks": record.get("residual_risks"),
                    "follow_up": record.get("follow_up"),
                }
            )
        )
        summary = record.get("summary")
        if summary not in PARTIAL_VERIFICATION_SUMMARIES:
            errors.append("BUG verification: partial summary must use canonical inconclusive wording")
    elif result == "failed":
        has_failure_signal = (
            post_fix.get("status") != "absent"
            or any(outcome.get("outcome") != "passed" for outcome in full_outcomes)
            or not regression.get("green_evidence_refs")
        )
        if not has_failure_signal:
            errors.append("BUG verification: failed requires a persisted failure signal")

    evidence_groups = [
        ("pre-fix original symptom", pre_fix.get("evidence_refs", [])),
        ("post-fix original symptom", post_fix.get("evidence_refs", [])),
        ("regression red", regression.get("red_evidence_refs", [])),
        ("regression green", regression.get("green_evidence_refs", [])),
        ("proxy red", proxy.get("red_evidence_refs", [])),
        ("proxy green", proxy.get("green_evidence_refs", [])),
        (
            "full command output",
            [
                outcome.get("output_ref")
                for outcome in full_outcomes
                if outcome.get("output_ref") is not None
            ],
        ),
        ("implementation review", [record.get("implementation_review_ref")]),
    ]
    canonical_refs: list[str] = []
    roles: dict[str, str] = {}
    for role, refs in evidence_groups:
        if not isinstance(refs, list):
            errors.append(f"BUG verification: {role} evidence refs are not an array")
            continue
        for raw_ref in refs:
            relative = _canonical_evidence_ref(raw_ref)
            if relative is None or relative != raw_ref:
                errors.append(f"BUG verification: {role} evidence ref is not a canonical Ledger path")
                continue
            if relative in roles:
                errors.append(
                    f"BUG verification: evidence ref {relative} is reused for {roles[relative]} and {role}"
                )
                continue
            roles[relative] = role
            canonical_refs.append(relative)

    if (evidence_root is None) != (terminal_evidence_refs is None):
        errors.append("BUG verification: terminal evidence root and index must be supplied together")
    if evidence_root is not None and terminal_evidence_refs is not None:
        terminal_set = {
            relative
            for raw_ref in terminal_evidence_refs
            for relative in [_canonical_evidence_ref(raw_ref)]
            if relative is not None and relative == raw_ref
        }
        for relative in canonical_refs:
            if relative not in terminal_set:
                errors.append(f"BUG verification: evidence is absent from terminal index: {relative}")
                continue
            path = _persisted_evidence_path(evidence_root, relative)
            if path is None:
                errors.append(f"BUG verification: evidence is not persisted: {relative}")
                continue
            try:
                materialized = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errors.append(f"BUG verification: evidence is unreadable: {relative}")
                continue
            errors.extend(
                validate_secret_free(
                    materialized,
                    known_secret_values,
                    label=f"BUG verification evidence {relative}",
                )
            )
    return errors


def validate_bug_dirty_paths(
    ready: dict[str, Any],
    dirty_paths: Sequence[str],
) -> list[str]:
    """Reject unapproved repository BUG evidence at implementation preflight."""
    context = ready.get("bug_context")
    allowed: set[str] = set()
    if isinstance(context, dict):
        assessment = context.get("assessment", {})
        allowed = {
            value
            for value in (assessment.get("path"), assessment.get("markdown_path"))
            if isinstance(value, str)
        }
    errors: list[str] = []
    for raw in dirty_paths:
        normalized = raw.replace("\\", "/")
        if normalized.startswith("docs/bugs/") and normalized not in allowed:
            errors.append(f"preflight: unauthorized BUG dirty path {normalized}")
    return errors


def validate_execution_record_semantics(
    data: dict[str, Any],
    *,
    known_secret_values: tuple[str, ...] = (),
    breaker_reports: list[dict[str, Any]] | None = None,
    evidence_root: Path | None = None,
    ready: dict[str, Any] | None = None,
) -> list[str]:
    """Check canonical identities and verdict invariants that JSON Schema cannot express."""
    errors: list[str] = validate_secret_free(
        data,
        known_secret_values,
        label=str(data.get("schema", "execution record")),
    )
    schema_name = data.get("schema")
    if schema_name == "implementation-ledger/v1":
        if data.get("run_id") != data.get("binding", {}).get("run_id"):
            errors.append("ledger: run_id differs from binding.run_id")
        attempts = data.get("attempts", [])
        attempt_ids = [attempt.get("attempt_id") for attempt in attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            errors.append("ledger: duplicate attempt_id")
        if data.get("current_attempt_id") not in set(attempt_ids):
            errors.append("ledger: current_attempt_id does not identify an attempt")
        complete_indices: list[int] = []
        used_integrity_refs: set[str] = set()
        for attempt_index, attempt in enumerate(attempts):
            history = attempt.get("state_history", [])
            sequences = [transition.get("sequence") for transition in history]
            if sequences != list(range(1, len(history) + 1)):
                errors.append(f"ledger: {attempt.get('attempt_id')} state transition sequence is not contiguous")
            previous: str | None = None
            for index, transition in enumerate(history):
                if transition.get("from") != previous:
                    errors.append(f"ledger: {attempt.get('attempt_id')} state history is discontinuous at {index + 1}")
                target = transition.get("to")
                if previous is None:
                    if target != "Preflight":
                        errors.append(f"ledger: {attempt.get('attempt_id')} must start at Preflight")
                elif target not in EXPECTED_TRANSITIONS.get(previous, []):
                    errors.append(f"ledger: illegal transition {previous} -> {target}")
                evidence_refs = transition.get("evidence_refs", [])
                integrity_refs = [
                    ref
                    for ref in evidence_refs
                    if isinstance(ref, str)
                    and ref.startswith("integrity/")
                    and ref.endswith("ready-source.json")
                ]
                if not integrity_refs:
                    errors.append(
                        f"ledger: {attempt.get('attempt_id')} transition {index + 1} lacks Ready/source rehash evidence"
                    )
                for ref in integrity_refs:
                    if ref in used_integrity_refs:
                        errors.append(
                            f"ledger: Ready/source rehash evidence is reused across transitions: {ref}"
                        )
                    used_integrity_refs.add(ref)
                previous = target
            if history and history[-1].get("to") != attempt.get("state"):
                errors.append(f"ledger: {attempt.get('attempt_id')} current state differs from history")
            if attempt.get("state") == "Complete":
                complete_indices.append(attempt_index)
                errors.extend(_complete_index_errors(attempt))
                if not data.get("baseline_evidence_refs"):
                    errors.append("ledger: Complete requires baseline or absence evidence")
        if complete_indices:
            if len(complete_indices) != 1:
                errors.append("ledger: a run may contain only one Complete attempt")
            complete_index = complete_indices[0]
            complete_attempt = attempts[complete_index]
            if complete_index != len(attempts) - 1:
                errors.append("ledger: Complete attempt is not frozen at the end of the run")
            if data.get("current_attempt_id") != complete_attempt.get("attempt_id"):
                errors.append("ledger: current_attempt_id moved away from the Complete attempt")
            if evidence_root is None:
                errors.append("ledger: Complete requires a persisted evidence root")
            else:
                errors.extend(
                    validate_terminal_evidence(
                        data,
                        evidence_root,
                        ready=ready,
                        known_secret_values=known_secret_values,
                    )
                )
    elif schema_name == "implementation-snapshot/v1":
        ready_refs = [item.get("ref") for item in data.get("ready_hashes", [])]
        source_refs = [item.get("ref") for item in data.get("source_hashes", [])]
        paths = [item.get("path") for item in data.get("unignored_files", [])]
        if ready_refs != sorted(ready_refs):
            errors.append("snapshot: ready_hashes are not sorted by ref")
        if source_refs != sorted(source_refs):
            errors.append("snapshot: source_hashes are not sorted by ref")
        if paths != sorted(paths, key=lambda value: value.encode("utf-8")):
            errors.append("snapshot: unignored_files are not sorted by UTF-8 path bytes")
        for label, values in (("ready ref", ready_refs), ("source ref", source_refs), ("unignored path", paths)):
            if len(values) != len(set(values)):
                errors.append(f"snapshot: duplicate {label}")
        payload = dict(data)
        actual = payload.pop("snapshot_id", None)
        if actual != canonical_sha256(payload):
            errors.append("snapshot: snapshot_id does not match canonical content")
    elif schema_name == "implementation-review/v1":
        bug_fields = (
            data.get("bug_verification_ref"),
            data.get("bug_verification_result"),
        )
        if any(value is not None for value in bug_fields) and not all(
            value is not None for value in bug_fields
        ):
            errors.append("review: BUG verification ref and result must be recorded together")
        knowledge_fields = (
            data.get("knowledge_snapshot_before"),
            data.get("knowledge_snapshot_after"),
            data.get("knowledge_candidate_ref"),
            data.get("knowledge_candidate_payload_sha256"),
        )
        if any(value is not None for value in knowledge_fields) and not all(
            value is not None for value in knowledge_fields
        ):
            errors.append("review: knowledge snapshots and Candidate binding must be recorded together")
        if all(value is not None for value in knowledge_fields) and (
            data.get("knowledge_snapshot_before") != data.get("knowledge_snapshot_after")
        ):
            errors.append("review: accepted knowledge snapshot must be identical before and after review")
        raw_ref_list = data.get("raw_output_refs", [])
        raw_refs = set(raw_ref_list)
        if len(raw_ref_list) != len(raw_refs):
            errors.append("review: duplicate raw_output_refs")
        outcomes = data.get("command_outcomes", [])
        outcome_output_refs = [
            outcome.get("output_ref")
            for outcome in outcomes
            if outcome.get("output_ref") is not None
        ]
        if len(outcome_output_refs) != len(set(outcome_output_refs)):
            errors.append("review: command outcomes reuse a raw output ref")
        for outcome in outcomes:
            output_ref = outcome.get("output_ref")
            if output_ref is not None and output_ref not in raw_refs:
                errors.append(f"review: {outcome.get('command_id')} output_ref is absent from raw_output_refs")
            if outcome.get("outcome") == "passed" and output_ref is None:
                errors.append(f"review: {outcome.get('command_id')} passed without a raw output ref")
        for finding in data.get("findings", []):
            key_inputs = finding.get("key_inputs", {})
            for field in ("source_refs", "affected_loci"):
                values = key_inputs.get(field, [])
                normalized_values = [
                    " ".join(value.strip().split()).replace("\\", "/")
                    for value in values
                    if isinstance(value, str)
                ]
                if len(normalized_values) != len(set(normalized_values)):
                    errors.append(
                        f"review: finding {finding.get('finding_id')} has duplicate normalized {field}"
                    )
            if finding.get("finding_key") != finding_key(key_inputs):
                errors.append(f"review: finding {finding.get('finding_id')} has a non-canonical finding_key")
        if data.get("snapshot_before") != data.get("snapshot_after"):
            errors.append("review: accepted report requires identical before/after snapshots")
        if data.get("verdict") == "APPROVED":
            if any(item.get("outcome") != "passed" for item in outcomes):
                errors.append("review: APPROVED requires every command outcome to be passed")
            if any(item.get("result") != "covered" for item in data.get("requirement_coverage", [])):
                errors.append("review: APPROVED requires complete covered requirement evidence")
            for item in data.get("requirement_coverage", []):
                if item.get("result") == "covered" and any(
                    not item.get(field)
                    for field in ("bdd_refs", "test_refs", "wp_refs", "code_evidence")
                ):
                    errors.append(
                        "review: covered obligation requires BDD, TEST, WP, and code evidence"
                    )
            if any(item.get("blocking") is True for item in data.get("findings", [])):
                errors.append("review: APPROVED cannot contain a blocking finding")
        if data.get("verdict") == "CHANGES_REQUIRED" and not any(
            item.get("blocking") is True for item in data.get("findings", [])
        ):
            errors.append("review: CHANGES_REQUIRED requires a blocking finding")
    elif schema_name == "bug-verification/v1":
        if ready is not None:
            errors.extend(
                validate_bug_verification_against_ready(
                    data,
                    ready,
                    known_secret_values=known_secret_values,
                )
            )
    elif schema_name == "implementation-outcome/v1":
        changes = data.get("changes", [])
        change_paths = [item.get("path") for item in changes if isinstance(item, dict)]
        if len(change_paths) != len(set(change_paths)):
            errors.append("outcome: duplicate changed path")
        if any(
            not isinstance(path, str) or path.startswith("docs/knowledge/")
            for path in change_paths
        ):
            errors.append("outcome: product changes cannot target canonical knowledge")
        work_id = data.get("work_id")
        revision = data.get("revision")
        suffix = "" if revision == 1 else f"-{revision}"
        expected_markdown = f"docs/work/{work_id}/implementation/outcome{suffix}.md"
        if data.get("markdown", {}).get("path") != expected_markdown:
            errors.append("outcome: Markdown path is not canonical for the Work ID")
        verification = data.get("verification", [])
        result = data.get("result")
        review = data.get("review", {})
        if result in {"complete", "verified"} and any(
            item.get("outcome") != "passed"
            for item in verification
            if isinstance(item, dict)
        ):
            errors.append("outcome: complete or verified requires every verification command to pass")
        if any(
            not isinstance(item, dict)
            or not item.get("evidence_refs")
            for item in verification
        ):
            errors.append("outcome: every verification command requires evidence")
        if result in {"complete", "verified", "partial"} and review.get("verdict") != "APPROVED":
            errors.append("outcome: accepted result requires APPROVED fresh review")
        if result == "failed" and review.get("verdict") == "APPROVED":
            errors.append("outcome: failed result cannot have APPROVED review")
        if any(
            not isinstance(ref, str)
            or re.fullmatch(r"review:fresh-review:[a-z0-9][a-z0-9._-]{2,127}", ref) is None
            for ref in review.get("evidence_refs", [])
        ):
            errors.append("outcome: review evidence ref is not a fresh-review logical ref")
        if len(review.get("evidence_refs", [])) != 1:
            errors.append("outcome: preliminary review requires exactly one logical ref")
        if data.get("work_kind") == "bug":
            bug = data.get("bug")
            if not isinstance(bug, dict):
                errors.append("outcome: BUG details are missing")
            elif result == "partial" and partial_overclaim(
                {
                    "summary": data.get("summary"),
                    "residual_risks": bug.get("residual_risks"),
                    "follow_up": bug.get("follow_up"),
                }
            ):
                errors.append("outcome: partial BUG contains a verified-fix overclaim")
            if result == "failed" and data.get("knowledge_decision") != "no-change":
                errors.append("outcome: failed BUG must use a no-change knowledge decision")
        elif data.get("bug") is not None or data.get("bug_verification_ref") is not None:
            errors.append("outcome: standard work cannot carry BUG bindings")
    elif schema_name == "implementation-breaker/v1":
        if breaker_reports is None:
            errors.append("breaker: persisted review report chain is required for semantic validation")
        else:
            errors.extend(validate_breaker_against_reports(data, breaker_reports, known_secret_values))
    return errors


def _blocking_findings(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        finding["finding_key"]: finding
        for finding in report.get("findings", [])
        if finding.get("blocking") is True and isinstance(finding.get("finding_key"), str)
    }


def _progress_evidence(report: dict[str, Any]) -> set[str]:
    evidence = {
        f"command-passed:{outcome.get('command_id')}"
        for outcome in report.get("command_outcomes", [])
        if outcome.get("outcome") == "passed"
    }
    evidence.update(
        ref
        for coverage in report.get("requirement_coverage", [])
        for ref in coverage.get("code_evidence", [])
        if isinstance(ref, str)
    )
    evidence.update(
        f"covered:{coverage.get('source_ref')}:{coverage.get('obligation_ref')}"
        for coverage in report.get("requirement_coverage", [])
        if coverage.get("result") == "covered"
    )
    return evidence


def _breaker_evidence_sha(report: dict[str, Any], finding_key_value: str) -> str:
    finding = _blocking_findings(report)[finding_key_value]
    payload = {
        "round": report.get("round"),
        "snapshot_after": report.get("snapshot_after"),
        "finding_key": finding_key_value,
        "key_inputs": finding.get("key_inputs"),
        "evidence_refs": sorted(finding.get("evidence_refs", [])),
        "command_outcomes": report.get("command_outcomes", []),
        "requirement_coverage": report.get("requirement_coverage", []),
    }
    return canonical_sha256(payload)


def validate_breaker_against_reports(
    breaker: dict[str, Any],
    reports: list[dict[str, Any]],
    known_secret_values: tuple[str, ...] = (),
) -> list[str]:
    """Recompute current breaker counters from the persisted report chain."""
    errors = validate_secret_free(
        [breaker, *reports],
        known_secret_values,
        label="breaker report chain",
    )
    if not reports:
        return [*errors, "breaker: report chain is empty"]
    rounds = [report.get("round") for report in reports]
    if rounds != list(range(1, len(reports) + 1)):
        errors.append("breaker: report rounds are not a complete contiguous chain")
    for report in reports:
        report_errors = validate_execution_record_semantics(
            report,
            known_secret_values=known_secret_values,
        )
        if report_errors:
            errors.append(f"breaker: report round {report.get('round')} is not semantically valid")

    blocking_by_round = [_blocking_findings(report) for report in reports]
    latest = blocking_by_round[-1]
    entries = breaker.get("findings", [])
    entry_keys = [entry.get("finding_key") for entry in entries]
    if len(entry_keys) != len(set(entry_keys)):
        errors.append("breaker: duplicate finding_key")
    if set(entry_keys) != set(latest):
        errors.append("breaker: current entries do not equal the latest blocking findings")

    transition_progress: list[bool] = []
    for index in range(1, len(reports)):
        previous_keys = set(blocking_by_round[index - 1])
        current_keys = set(blocking_by_round[index])
        new_semantic_evidence = bool(
            _progress_evidence(reports[index])
            - _progress_evidence(reports[index - 1])
        )
        progress = (
            len(current_keys) < len(previous_keys)
            or new_semantic_evidence
        )
        transition_progress.append(progress)
    global_no_progress = 0
    for progress in reversed(transition_progress):
        if progress:
            break
        global_no_progress += 1
    if breaker.get("global_no_progress_rounds") != global_no_progress:
        errors.append("breaker: global no-progress counter is not reproducible")

    for entry in entries:
        key = entry.get("finding_key")
        if key not in latest:
            continue
        consecutive = 0
        for findings in reversed(blocking_by_round):
            if key not in findings:
                break
            consecutive += 1
        key_no_progress = 0
        for index in range(len(reports) - 1, 0, -1):
            if key not in blocking_by_round[index] or key not in blocking_by_round[index - 1]:
                break
            if transition_progress[index - 1]:
                break
            key_no_progress += 1
        if entry.get("consecutive_unresolved_rounds") != consecutive:
            errors.append(f"breaker: {key} consecutive counter is not reproducible")
        if entry.get("no_progress_rounds") != key_no_progress:
            errors.append(f"breaker: {key} no-progress counter is not reproducible")
        if entry.get("last_evidence_sha256") != _breaker_evidence_sha(reports[-1], key):
            errors.append(f"breaker: {key} last evidence digest is not canonical")
    return errors


def validate_review_against_ready(
    report: dict[str, Any],
    ready: dict[str, Any],
    known_secret_values: tuple[str, ...] = (),
) -> list[str]:
    """Validate report coverage and full-command outcomes against its producer handoff."""
    errors: list[str] = validate_secret_free(
        [ready, report],
        known_secret_values,
        label="Ready/review records",
    )
    commands = {item["command_id"]: item for item in ready.get("commands", [])}
    review_purposes = {"build-full", "test-full", "bdd-full", "governance", "ci"}
    required_commands = {command_id for command_id, item in commands.items() if item.get("purpose") in review_purposes}
    outcome_ids = [item.get("command_id") for item in report.get("command_outcomes", [])]
    if len(outcome_ids) != len(set(outcome_ids)):
        errors.append("review: duplicate command outcome")
    unknown_commands = set(outcome_ids) - set(commands)
    if unknown_commands:
        errors.append(f"review: unknown command outcomes {sorted(unknown_commands)}")
    missing_commands = required_commands - set(outcome_ids)
    if missing_commands:
        errors.append(f"review: missing full command outcomes {sorted(missing_commands)}")

    bug_context = ready.get("bug_context")
    bug_ref = report.get("bug_verification_ref")
    bug_result = report.get("bug_verification_result")
    if isinstance(bug_context, dict):
        if not isinstance(bug_ref, str) or not bug_ref or bug_result is None:
            errors.append("review: BUG Ready plan requires a separate BUG verification ref and result")
        elif report.get("verdict") == "APPROVED" and bug_result == "failed":
            errors.append("review: APPROVED review cannot carry failed BUG verification")
        elif report.get("verdict") == "APPROVED" and bug_result != bug_context.get("verification_target"):
            errors.append("review: APPROVED BUG verification result differs from the approved target")
        if bug_result == "partial":
            if report.get("summary") not in PARTIAL_REVIEW_SUMMARIES:
                errors.append("review: partial review summary must use canonical inconclusive wording")
            public_claims = {
                "summary": report.get("summary"),
                "findings": [
                    {
                        "message": finding.get("message"),
                        "required_outcome": finding.get("key_inputs", {}).get("required_outcome"),
                    }
                    for finding in report.get("findings", [])
                    if isinstance(finding, dict)
                ],
            }
            if partial_overclaim(public_claims):
                errors.append("review: partial public claim contains a verified-fix overclaim")
    elif bug_ref is not None or bug_result is not None:
        errors.append("review: non-BUG Ready plan cannot carry BUG verification fields")

    sources = {item["source_id"]: item for item in ready.get("sources", [])}
    contracts = {item["contract_id"]: item for item in ready.get("contract_index", [])}
    packages = {item["wp_id"]: item for item in ready.get("work_packages", [])}
    expected_coverage = {
        (source_id, plan_ref)
        for source_id, source in sources.items()
        for plan_ref in source.get("plan_refs", [])
    }
    actual_coverage: set[tuple[str, str]] = set()
    for item in report.get("requirement_coverage", []):
        key = (item.get("source_ref"), item.get("obligation_ref"))
        if key in actual_coverage:
            errors.append(f"review: duplicate coverage entry {key}")
        actual_coverage.add(key)
        if key[0] not in sources or key[1] not in sources.get(key[0], {}).get("plan_refs", []):
            errors.append(f"review: coverage entry {key} is absent from the source manifest")
        source = sources.get(key[0], {})
        coverage_wp_refs = set(item.get("wp_refs", []))
        for ref, expected_kind in (
            *((ref, "bdd-scenario") for ref in item.get("bdd_refs", [])),
            *((ref, "inner-test") for ref in item.get("test_refs", [])),
        ):
            if ref not in contracts or contracts[ref].get("kind") != expected_kind:
                errors.append(f"review: coverage entry {key} has unknown {expected_kind} ref {ref}")
            elif (
                key[0] not in contracts[ref].get("source_refs", [])
                or not coverage_wp_refs.intersection(contracts[ref].get("wp_refs", []))
            ):
                errors.append(
                    f"review: coverage entry {key} misbinds {expected_kind} ref {ref}"
                )
        for ref in item.get("wp_refs", []):
            if ref not in packages:
                errors.append(f"review: coverage entry {key} has unknown work package {ref}")
            elif ref not in source.get("wp_refs", []) or key[0] not in packages[ref].get("source_refs", []):
                errors.append(f"review: coverage entry {key} misbinds work package {ref}")
    missing_coverage = expected_coverage - actual_coverage
    if missing_coverage:
        errors.append(f"review: missing source obligations {sorted(missing_coverage)}")
    for finding in report.get("findings", []):
        for ref in finding.get("key_inputs", {}).get("source_refs", []):
            if ref not in sources:
                errors.append(f"review: finding {finding.get('finding_id')} has unknown source {ref}")
        for ref, expected_kind in (
            *((ref, "bdd-scenario") for ref in finding.get("bdd_refs", [])),
            *((ref, "inner-test") for ref in finding.get("test_refs", [])),
        ):
            if ref not in contracts or contracts[ref].get("kind") != expected_kind:
                errors.append(f"review: finding {finding.get('finding_id')} has unknown {expected_kind} ref {ref}")
        for ref in finding.get("wp_refs", []):
            if ref not in packages:
                errors.append(f"review: finding {finding.get('finding_id')} has unknown work package {ref}")
    return errors


def _validate_execution_schema(schema: dict[str, Any], errors: list[str]) -> None:
    defs = schema.get("$defs", {})
    for name, expected in EXECUTION_DEF_REQUIRED.items():
        actual = _required(defs.get(name, {}))
        if not expected <= actual:
            errors.append(f"execution schema: {name} missing required fields {sorted(expected - actual)}")

    state_enum = set(defs.get("state", {}).get("enum", []))
    if state_enum != EXPECTED_STATES:
        errors.append(f"execution schema: state enum drift {sorted(state_enum ^ EXPECTED_STATES)}")
    transitions = schema.get("x-state-transitions", {})
    if set(transitions) != EXPECTED_STATES:
        errors.append("execution schema: transition sources do not equal state enum")
    if transitions != EXPECTED_TRANSITIONS:
        errors.append("execution schema: state transitions differ from the authoritative graph")
    edges = {(source, target) for source, targets in transitions.items() for target in targets}
    for source, target in edges:
        if target not in EXPECTED_STATES:
            errors.append(f"execution schema: transition {source} -> {target} targets unknown state")
    if not REQUIRED_STATE_EDGES <= edges:
        errors.append(f"execution schema: missing required state edges {sorted(REQUIRED_STATE_EDGES - edges)}")
    for state in EXPECTED_STATES - {"Complete", "Awaiting upstream reapproval", "Blocked"}:
        for terminal in ("Awaiting upstream reapproval", "Blocked"):
            if terminal not in transitions.get(state, []):
                errors.append(f"execution schema: incomplete state {state} cannot reach {terminal}")
    for terminal in ("Complete", "Awaiting upstream reapproval", "Blocked"):
        if transitions.get(terminal):
            errors.append(f"execution schema: terminal state {terminal} has outgoing transitions")

    wp_edges = {(source, target) for source, targets in schema.get("x-wp-state-transitions", {}).items() for target in targets}
    for edge in (("Invalidated", "Executing"), ("Executing", "Verified"), ("Verified", "Invalidated")):
        if edge not in wp_edges:
            errors.append(f"execution schema: missing WP transition {edge[0]} -> {edge[1]}")

    if schema.get("x-terminal-ordering") != TERMINAL_ORDER:
        errors.append("execution schema: terminal ordering drift")

    outcomes = set(defs.get("commandOutcome", {}).get("properties", {}).get("outcome", {}).get("enum", []))
    if outcomes != {"passed", "failed", "blocked", "not_run"}:
        errors.append("execution schema: command outcomes cannot represent every review result")
    for field in ("exit_code", "failure_count", "skipped_count"):
        types = defs.get("commandOutcome", {}).get("properties", {}).get(field, {}).get("type", [])
        if set(types) != {"integer", "null"}:
            errors.append(f"execution schema: {field} must be integer|null")
    if defs.get("finding", {}).get("properties", {}).get("blocking", {}).get("type") != "boolean":
        errors.append("execution schema: finding.blocking is not a boolean")
    severities = set(defs.get("finding", {}).get("properties", {}).get("severity", {}).get("enum", []))
    if "advisory" not in severities:
        errors.append("execution schema: advisory finding is not representable")

def _validate_links(skills_root: Path, errors: list[str]) -> None:
    for markdown in sorted(skills_root.glob("implementation-execution/**/*.md")):
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
    for markdown in sorted(skills_root.glob("implementation-execution/**/*.md")):
        relative = markdown.relative_to(skills_root).as_posix()
        for name in AUTHORITY_RE.findall(markdown.read_text(encoding="utf-8")):
            found.setdefault(name, []).append(relative)
    for name, expected in AUTHORITY_FILES.items():
        actual = found.get(name, [])
        if actual != [expected]:
            errors.append(f"authority {name!r}: expected [{expected}], got {actual}")
    for name in found.keys() - AUTHORITY_FILES.keys():
        errors.append(f"unknown authority marker {name!r} in {found[name]}")


def _validate_runtime_ownership(skills_root: Path, errors: list[str]) -> None:
    bundle = skills_root / "implementation-execution"
    for relative in (
        "scripts/validate_contracts.py",
        "scripts/test_validate_contracts.py",
        "scripts/behavior-evaluation-report.md",
    ):
        if not (bundle / relative).is_file():
            errors.append(f"implementation maintenance file missing: {relative}")
    skill = (bundle / "SKILL.md").read_text(encoding="utf-8")
    description_parts = skill.split("description:", 1)
    if len(description_parts) != 2 or not description_parts[1].lstrip().startswith("執行"):
        errors.append("implementation description must lead with 執行")
    yaml = (bundle / "agents/openai.yaml").read_text(encoding="utf-8")
    for fragment in (
        "allow_implicit_invocation: true",
        "$implementation-execution",
        'short_description: "執行',
    ):
        if fragment not in yaml:
            errors.append(f"implementation openai.yaml missing {fragment}")

    required_pointers = {
        "SKILL.md": [
            "references/orchestrated-delivery.md",
            "references/resume-and-revision.md",
            "references/greenfield-bootstrap.md",
        ],
        "references/preflight-and-ledger.md": [
            "../../technical-planning/references/ready-plan-contract.md",
            "../../technical-planning/references/ready-plan.schema.json",
            "orchestrated-delivery.md",
            "resume-and-revision.md",
        ],
        "references/bdd-tdd-loop.md": ["greenfield-bootstrap.md"],
        "references/behavior-evaluation.md": [
            ".agents/skills/implementation-execution/scripts/validate_contracts.py",
            ".agents/skills/implementation-execution/scripts/test_validate_contracts.py",
        ],
    }
    for relative, fragments in required_pointers.items():
        text = (bundle / relative).read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in text:
                errors.append(f"{relative}: missing branch pointer {fragment}")

    preflight = (bundle / "references/preflight-and-ledger.md").read_text(encoding="utf-8")
    if "current Ready requirements revision" in preflight:
        errors.append("preflight duplicates orchestrated delivery gate details")
    for fragment in (
        "秘密不得進入manifest、命令列或Ledger",
        "已知秘密值集合",
        "known_secret_values",
        "只遮蔽該秘密值",
        "另記redaction event",
        "每個WP開始／完成、global transition與snapshot前重算Ready／source hashes",
        "任何drift立即進入",
        "Complete transition另作terminal index",
        "integrity/<WP-ID>/start-ready-source.json",
        "未被其他transition重用",
        "canonical run root",
        "commands/full-verification.json",
        "terminal/01-review_received.json",
        "capability／baseline refs",
        "implementation-capability/v1",
        "implementation-integrity/v1",
        "Standard Ready不允許任何BUG dirty path",
    ):
        if fragment not in preflight:
            errors.append(f"preflight missing executor security/integrity semantic {fragment}")
    orchestrated = (bundle / "references/orchestrated-delivery.md").read_text(encoding="utf-8")
    if "已遮蔽的approval evidence refs非空" not in orchestrated:
        errors.append("orchestrated delivery gate does not require redacted approval evidence refs")
    loop = (bundle / "references/bdd-tdd-loop.md").read_text(encoding="utf-8")
    if "deterministic Unimplemented" in loop:
        errors.append("BDD/TDD loop duplicates greenfield bootstrap details")
    for fragment in ("BUG plan 分支", "不得再疊第二個猜測式patch", "current-scope", "全域BUG inbox"):
        if fragment not in loop:
            errors.append(f"BDD/TDD loop missing BUG execution semantic {fragment}")
    reviewer = (bundle / "references/reviewer-contract.md").read_text(encoding="utf-8")
    for fragment in (
        "implementation-snapshot/v1",
        "implementation-review/v1",
        "finding_key",
        "進展式熔斷",
        "每個covered obligation都有非空BDD、TEST、WP與code evidence",
        "直接擁有同一`source_ref`",
        "validator以round 1起連續保存的reports重算",
        "`output_ref`只是傳輸位置",
        "duplicate normalized refs",
        "raw_output_refs`自身也不得重複",
        "A→B→C無證據輪換",
        "bug_verification_ref",
        "Reviewer分別判定",
        "implementation-outcome/v1",
        "knowledge_snapshot_before",
        "knowledge_candidate_payload_sha256",
    ):
        if fragment not in reviewer:
            errors.append(f"reviewer authority missing shared semantic {fragment}")
    delivery = (bundle / "references/delivery-protocol.md").read_text(encoding="utf-8")
    for fragment in (
        "current round raw response、report宣告的每個raw output ref",
        "Ledger terminal index",
        "phantom ref",
        "terminal/<sequence>-<step>.json",
        "結果為`failed`",
        "未materialize",
        "knowledge/awaiting_user",
        "knowledge-promotion/v1",
    ):
        if fragment not in delivery:
            errors.append(f"delivery authority missing terminal persistence semantic {fragment}")

    behavior = (bundle / "references/behavior-evaluation.md").read_text(encoding="utf-8")
    for index in range(1, 11):
        if f"EVAL-{index:03d}" not in behavior:
            errors.append(f"behavior contract missing EVAL-{index:03d}")
    validator_source = (bundle / "scripts/validate_contracts.py").read_text(encoding="utf-8")
    for fragment in (
        "def validate_bug_verification_against_ready",
        "def validate_bug_dirty_paths",
        "partial summary must use canonical inconclusive wording",
        "evidence is absent from terminal index",
        "evidence is not persisted",
        "partial review summary must use canonical inconclusive wording",
        "partial public claim contains a verified-fix overclaim",
        "raw JSON contains a duplicate object key",
        "APPROVED review cannot carry failed BUG verification",
        "outcome: partial BUG contains a verified-fix overclaim",
        "review: knowledge snapshots and Candidate binding must be recorded together",
    ):
        if fragment not in validator_source:
            errors.append(f"implementation validator missing BUG semantic {fragment}")


def validate_all(skills_root: Path) -> list[str]:
    skills_root = skills_root.resolve()
    errors: list[str] = []
    execution_path = (
        skills_root / "implementation-execution/references/execution-records.schema.json"
    )
    if not execution_path.is_file():
        return [f"missing schema: {execution_path}"]
    if hashlib.sha256(execution_path.read_bytes()).hexdigest() != EXECUTION_SCHEMA_SHA256:
        errors.append("implementation-records schema bytes drifted")
    try:
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"schema parse failed: {exc}"]

    _validate_links(skills_root, errors)
    _validate_authorities(skills_root, errors)
    _validate_runtime_ownership(skills_root, errors)
    _validate_schema_refs(execution, "execution schema", errors)
    _validate_execution_schema(execution, errors)

    planning_validator = (
        skills_root / "technical-planning/scripts/validate_contracts.py"
    ).read_text(encoding="utf-8")
    for moved_name in (
        "EXECUTION_DEF_REQUIRED",
        "validate_execution_record_semantics",
        "validate_review_against_ready",
    ):
        if moved_name in planning_validator:
            errors.append(f"technical-planning still owns execution semantic {moved_name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, default=SKILLS_ROOT_DEFAULT)
    args = parser.parse_args(argv)
    errors = validate_all(args.skills_root)
    if errors:
        print(f"implementation contract validation failed ({len(errors)}):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("implementation-execution contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
