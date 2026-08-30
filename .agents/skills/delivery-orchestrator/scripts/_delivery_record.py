#!/usr/bin/env python3
"""Private delivery record, approval, and materialization contracts.

Authority: delivery-record
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from _delivery_git import (
    _active_filter_drivers,
    _filter_disable_config,
    _git,
    _git_failure_error,
    destination_and_branch,
    probe_repository,
)
from _delivery_runtime import (
    DeliveryError,
    EVIDENCE_REF_RE,
    EVENT_RE,
    GIT_SHA_RE,
    PHASE_TRANSITIONS,
    SCHEMA,
    SHA256_RE,
    STATUS_TRANSITIONS,
    WORK_ID_RE,
    _atomic_write_json,
    _contains_sensitive_material,
    _is_aware_datetime,
    _is_relative_to,
    _is_utc_datetime,
    _logical_refs,
    _normalized_repo_path,
    _read_json,
    _validate_registry_root,
    canonical_json,
    canonical_path,
    canonical_path_text,
    default_registry_root,
    path_key,
    run_directory,
    sha256_bytes,
    utc_now,
    validate_sha256,
    validate_work_id,
    workspace_label,
)


_CONTRACT_VALIDATOR: Any | None = None
_EXECUTION_VALIDATOR: Any | None = None
_READY_PLAN_SCHEMA: dict[str, Any] | None = None
_DELIVERY_RUN_SCHEMA: dict[str, Any] | None = None
_EXECUTION_RECORDS_SCHEMA: dict[str, Any] | None = None

def _contract_validator() -> Any:
    """Load the producer-owned standard-library contract validator once."""
    global _CONTRACT_VALIDATOR
    if _CONTRACT_VALIDATOR is not None:
        return _CONTRACT_VALIDATOR
    module_path = (
        Path(__file__).resolve().parents[2]
        / "technical-planning"
        / "scripts"
        / "validate_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("delivery_contract_validator", module_path)
    if spec is None or spec.loader is None:
        raise DeliveryError("contract validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise DeliveryError("contract validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE") from exc
    _CONTRACT_VALIDATOR = module
    return module


def _execution_validator() -> Any:
    """Load the consumer-owned execution validator for terminal evidence."""
    global _EXECUTION_VALIDATOR
    if _EXECUTION_VALIDATOR is not None:
        return _EXECUTION_VALIDATOR
    module_path = (
        Path(__file__).resolve().parents[2]
        / "implementation-execution"
        / "scripts"
        / "validate_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("delivery_execution_validator", module_path)
    if spec is None or spec.loader is None:
        raise DeliveryError("execution validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise DeliveryError("execution validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE") from exc
    _EXECUTION_VALIDATOR = module
    return module


def _load_schema(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"{label} schema cannot be loaded", code="CONTRACT_SCHEMA_UNAVAILABLE") from exc
    if not isinstance(value, dict):
        raise DeliveryError(f"{label} schema is not an object", code="CONTRACT_SCHEMA_UNAVAILABLE")
    return value


def _ready_plan_schema() -> dict[str, Any]:
    global _READY_PLAN_SCHEMA
    if _READY_PLAN_SCHEMA is None:
        _READY_PLAN_SCHEMA = _load_schema(
            Path(__file__).resolve().parents[2]
            / "technical-planning"
            / "references"
            / "ready-plan.schema.json",
            label="ready-plan/v1",
        )
    return _READY_PLAN_SCHEMA


def _delivery_run_schema() -> dict[str, Any]:
    global _DELIVERY_RUN_SCHEMA
    if _DELIVERY_RUN_SCHEMA is None:
        _DELIVERY_RUN_SCHEMA = _load_schema(
            Path(__file__).resolve().parents[1] / "references" / "delivery-run.schema.json",
            label=SCHEMA,
        )
    return _DELIVERY_RUN_SCHEMA


def _execution_records_schema() -> dict[str, Any]:
    global _EXECUTION_RECORDS_SCHEMA
    if _EXECUTION_RECORDS_SCHEMA is None:
        _EXECUTION_RECORDS_SCHEMA = _load_schema(
            Path(__file__).resolve().parents[2]
            / "implementation-execution"
            / "references"
            / "execution-records.schema.json",
            label="implementation-records",
        )
    return _EXECUTION_RECORDS_SCHEMA


def _schema_errors(value: Any, schema: dict[str, Any]) -> list[str]:
    try:
        return list(_contract_validator().validate_instance(value, schema))
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DeliveryError("contract validation could not complete", code="CONTRACT_VALIDATOR_UNAVAILABLE") from exc


def _validate_ready_contract(handoff: dict[str, Any]) -> None:
    schema_errors = _schema_errors(handoff, _ready_plan_schema())
    if schema_errors:
        raise DeliveryError(
            f"Ready handoff violates ready-plan/v1 schema ({len(schema_errors)} issue(s))",
            code="INVALID_HANDOFF",
        )
    try:
        cross_errors = list(_contract_validator().validate_ready_cross_references(handoff))
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DeliveryError("Ready handoff cross-reference validation could not complete", code="INVALID_HANDOFF") from exc
    if cross_errors:
        raise DeliveryError(
            f"Ready handoff violates producer cross-reference rules ({len(cross_errors)} issue(s))",
            code="INVALID_HANDOFF",
        )


def _append_event(
    record: dict[str, Any],
    *,
    kind: str,
    phase: str,
    status: str,
    evidence_refs: Iterable[str],
) -> None:
    if not EVENT_RE.fullmatch(kind):
        raise DeliveryError(f"invalid event kind: {kind!r}", code="INVALID_EVENT")
    try:
        refs = _logical_refs(evidence_refs, "event")
    except DeliveryError as exc:
        raise DeliveryError(str(exc), code="INVALID_EVENT") from exc
    events = record["events"]
    events.append(
        {
            "sequence": len(events) + 1,
            "at": utc_now(),
            "kind": kind,
            "from_phase": record["phase"] if events else None,
            "to_phase": phase,
            "from_status": record["status"] if events else None,
            "to_status": status,
            "evidence_refs": refs,
        }
    )
    record["phase"] = phase
    record["status"] = status
    record["updated_at"] = events[-1]["at"]


def _implementation_root() -> Path:
    host_temp = canonical_path(tempfile.gettempdir())
    lexical_root = host_temp / "implementation-execution"
    is_junction = getattr(lexical_root, "is_junction", lambda: False)
    if lexical_root.is_symlink() or is_junction():
        raise DeliveryError("implementation Ledger root is redirected", code="INVALID_IMPLEMENTATION_REF")
    root = canonical_path(lexical_root)
    if root.parent != host_temp:
        raise DeliveryError("implementation Ledger root is outside host temp", code="INVALID_IMPLEMENTATION_REF")
    runs = root / "runs"
    runs_is_junction = getattr(runs, "is_junction", lambda: False)
    if runs.is_symlink() or runs_is_junction():
        raise DeliveryError("implementation runs root is redirected", code="INVALID_IMPLEMENTATION_REF")
    return root


def _ledger_relative_ref(value: str) -> str | None:
    relative = value
    for prefix in ("implementation:", "ledger:"):
        if relative.startswith(prefix):
            relative = relative[len(prefix):]
            break
    if ":" in relative:
        return None
    try:
        return _normalized_repo_path(relative)
    except DeliveryError:
        return None


def _ledger_evidence_path(run_dir: Path, relative: str) -> Path | None:
    candidate = run_dir / Path(*relative.split("/"))
    cursor = candidate
    while cursor != run_dir:
        is_junction = getattr(cursor, "is_junction", lambda: False)
        if cursor.is_symlink() or is_junction():
            return None
        cursor = cursor.parent
    resolved = canonical_path(candidate)
    if not _is_relative_to(resolved, run_dir) or not resolved.is_file():
        return None
    return resolved


def _snapshot_file(worktree: Path, relative: str) -> Path:
    normalized = _normalized_repo_path(relative)
    lexical = worktree / Path(*normalized.split("/"))
    is_junction = getattr(lexical, "is_junction", lambda: False)
    resolved = canonical_path(lexical)
    if (
        lexical.is_symlink()
        or is_junction()
        or not _is_relative_to(resolved, worktree)
        or not resolved.is_file()
    ):
        raise DeliveryError("snapshot input is missing or redirected", code="INVALID_IMPLEMENTATION_REF")
    return resolved


def _current_implementation_snapshot(
    record: dict[str, Any],
    ready: dict[str, Any],
) -> dict[str, Any]:
    """Recompute implementation-snapshot/v1 from the current delivery worktree."""
    generation = record["generations"][-1]
    worktree = canonical_path(generation["canonical_worktree"])
    ready_hashes = [
        {
            "ref": _normalized_repo_path(artifact["path"]),
            "sha256": sha256_bytes(
                _snapshot_file(worktree, artifact["path"]).read_bytes()
            ),
        }
        for artifact in ready.get("artifacts", [])
    ]
    ready_hashes.sort(key=lambda item: item["ref"])

    source_hashes: list[dict[str, str]] = []
    for source in ready.get("sources", []):
        location = source["location"]
        if urlparse(location).scheme:
            actual = source["sha256"]
        else:
            actual = sha256_bytes(
                _snapshot_file(worktree, location).read_bytes()
            )
        if actual != source["sha256"]:
            raise DeliveryError("Ready source drifted before Complete", code="INVALID_IMPLEMENTATION_REF")
        source_hashes.append({"ref": source["source_id"], "sha256": actual})
    source_hashes.sort(key=lambda item: item["ref"])

    tracked_diff = _git(
        worktree,
        [
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            "--no-textconv",
            generation["base_sha"],
            "--",
        ],
    ).stdout
    raw_unignored = _git(
        worktree,
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ).stdout
    raw_paths = [raw for raw in raw_unignored.split(b"\0") if raw]
    unignored_files: list[dict[str, str]] = []
    for raw_path in sorted(raw_paths):
        try:
            relative = _normalized_repo_path(raw_path.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise DeliveryError(
                "unignored snapshot path is not UTF-8",
                code="INVALID_IMPLEMENTATION_REF",
            ) from exc
        unignored_files.append(
            {
                "path": relative,
                "sha256": sha256_bytes(
                    _snapshot_file(worktree, relative).read_bytes()
                ),
            }
        )
    unignored_files.sort(key=lambda item: item["path"].encode("utf-8"))
    head_sha = _git(worktree, ["rev-parse", "HEAD"]).stdout.decode("ascii").strip()
    snapshot = {
        "schema": "implementation-snapshot/v1",
        "repo_id": record["repo_id"],
        "worktree_key": generation["worktree_key"],
        "base_sha": generation["base_sha"],
        "head_sha": head_sha,
        "ready_hashes": ready_hashes,
        "source_hashes": source_hashes,
        "tracked_diff_sha256": sha256_bytes(tracked_diff),
        "unignored_files": unignored_files,
    }
    snapshot["snapshot_id"] = sha256_bytes(canonical_json(snapshot))
    return snapshot


def _complete_implementation_errors(
    record: dict[str, Any],
    current_run: dict[str, Any],
    delivery_evidence_refs: Sequence[str],
) -> list[str]:
    """Verify a persisted Complete Ledger and the accepted review it names."""
    errors: list[str] = []
    run_id = str(current_run.get("run_id", ""))
    if not SHA256_RE.fullmatch(run_id):
        return ["Complete implementation run ID is invalid"]
    try:
        root = _implementation_root()
    except DeliveryError:
        return ["Complete implementation Ledger root is invalid"]
    runs_root = canonical_path(root / "runs")
    run_dir_lexical = root / "runs" / run_id
    is_junction = getattr(run_dir_lexical, "is_junction", lambda: False)
    if run_dir_lexical.is_symlink() or is_junction():
        return ["Complete implementation run directory is redirected"]
    run_dir = canonical_path(run_dir_lexical)
    if run_dir.parent != runs_root:
        return ["Complete implementation run directory is not canonical"]
    ledger_path = _ledger_evidence_path(run_dir, "run.json")
    if ledger_path is None:
        return ["Complete implementation Ledger is not persisted"]
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["Complete implementation Ledger is unreadable"]
    if not isinstance(ledger, dict):
        return ["Complete implementation Ledger is not an object"]

    try:
        validator = _execution_validator()
        schema = _execution_records_schema()
        ledger_schema_errors = list(validator.validate_instance(ledger, schema, "ledger"))
        ledger_semantic_errors = list(
            validator.validate_execution_record_semantics(
                ledger,
                evidence_root=run_dir,
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError, DeliveryError):
        return ["Complete implementation Ledger validation could not complete"]
    if ledger_schema_errors or ledger_semantic_errors:
        return ["Complete implementation Ledger violates its contract"]

    generation = record["generations"][-1]
    binding = ledger.get("binding", {})
    current_handoff_path = record.get("plans", {}).get("current_handoff_path")
    current_plan = next(
        (
            item
            for item in record.get("plans", {}).get("revisions", [])
            if item.get("handoff_path") == current_handoff_path
        ),
        None,
    )
    if (
        ledger.get("run_id") != run_id
        or binding.get("run_id") != run_id
        or binding.get("repo_id") != record.get("repo_id")
        or binding.get("canonical_worktree") != generation.get("canonical_worktree")
        or binding.get("worktree_key") != generation.get("worktree_key")
        or binding.get("branch") != generation.get("branch")
        or binding.get("initial_base_sha") != generation.get("base_sha")
        or ledger.get("handoff_path") != current_handoff_path
        or current_plan is None
    ):
        errors.append("Complete implementation Ledger binding differs from delivery state")

    attempts = ledger.get("attempts", [])
    current_attempt = next(
        (
            item
            for item in attempts
            if item.get("attempt_id") == ledger.get("current_attempt_id")
        ),
        None,
    )
    history = current_attempt.get("state_history", []) if isinstance(current_attempt, dict) else []
    terminal = history[-1] if history else None
    if (
        not isinstance(current_attempt, dict)
        or current_attempt.get("state") != "Complete"
        or current_attempt.get("candidate_revision") != current_plan.get("candidate_revision")
        or not isinstance(terminal, dict)
        or terminal.get("from") != "Reviewing"
        or terminal.get("to") != "Complete"
    ):
        errors.append("Complete implementation attempt lacks a legal terminal transition")
        terminal_refs: list[str] = []
    else:
        terminal_refs = terminal.get("evidence_refs", [])

    ready: dict[str, Any] | None = None
    if isinstance(current_handoff_path, str):
        handoff_path = canonical_path(
            Path(generation["canonical_worktree"])
            / Path(*current_handoff_path.split("/"))
        )
        if _is_relative_to(handoff_path, canonical_path(generation["canonical_worktree"])) and handoff_path.is_file():
            try:
                candidate = json.loads(handoff_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    _validate_ready_contract(candidate)
                    ready = candidate
            except (OSError, UnicodeError, json.JSONDecodeError, DeliveryError):
                ready = None
    if ready is None:
        errors.append("Complete implementation review has no valid Ready handoff")
    else:
        try:
            ready_terminal_errors = list(
                validator.validate_terminal_evidence(
                    ledger,
                    run_dir,
                    ready=ready,
                )
            )
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            ready_terminal_errors = ["validation could not complete"]
        if ready_terminal_errors:
            errors.append("Complete terminal evidence differs from the Ready handoff")

    persisted_paths: dict[str, Path] = {}
    for raw_ref in terminal_refs:
        if not isinstance(raw_ref, str):
            errors.append("Complete terminal evidence ref is invalid")
            continue
        relative = _ledger_relative_ref(raw_ref)
        if relative is None:
            errors.append("Complete terminal evidence ref is not Ledger-relative")
            continue
        evidence_path = _ledger_evidence_path(run_dir, relative)
        if evidence_path is None:
            errors.append("Complete terminal evidence is not persisted")
            continue
        persisted_paths[relative] = evidence_path

    accepted_snapshot_paths: set[str] = set()
    accepted_snapshot_id: str | None = None
    if ready is not None:
        try:
            current_snapshot = _current_implementation_snapshot(record, ready)
        except (OSError, UnicodeError, DeliveryError):
            current_snapshot = None
            errors.append("Complete workspace snapshot could not be recomputed")
        if current_snapshot is not None:
            for relative, evidence_path in persisted_paths.items():
                try:
                    candidate_snapshot = json.loads(evidence_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
                if not isinstance(candidate_snapshot, dict) or candidate_snapshot.get("schema") != "implementation-snapshot/v1":
                    continue
                try:
                    snapshot_errors = list(
                        validator.validate_instance(candidate_snapshot, schema, "snapshot")
                    )
                    snapshot_errors.extend(
                        validator.validate_execution_record_semantics(candidate_snapshot)
                    )
                except (AttributeError, KeyError, TypeError, ValueError):
                    continue
                if not snapshot_errors and candidate_snapshot == current_snapshot:
                    accepted_snapshot_paths.add(relative)
                    accepted_snapshot_id = candidate_snapshot["snapshot_id"]
    if not accepted_snapshot_paths:
        errors.append("Complete transition lacks the canonical current workspace snapshot")

    approved_review_paths: set[str] = set()
    for relative, evidence_path in persisted_paths.items():
        try:
            report = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or report.get("schema") != "implementation-review/v1":
            continue
        try:
            report_errors = list(validator.validate_instance(report, schema, "reviewReport"))
            report_errors.extend(validator.validate_execution_record_semantics(report))
            if ready is not None:
                report_errors.extend(validator.validate_review_against_ready(report, ready))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        raw_output_paths = {
            normalized
            for ref in report.get("raw_output_refs", [])
            if isinstance(ref, str)
            for normalized in [_ledger_relative_ref(ref)]
            if normalized is not None
        }
        if raw_output_paths != set(report.get("raw_output_refs", [])):
            report_errors.append("review raw output refs are not canonical Ledger paths")
        if not raw_output_paths <= set(persisted_paths):
            report_errors.append("review raw outputs are not all persisted")
        if (
            not report_errors
            and report.get("verdict") == "APPROVED"
            and accepted_snapshot_id is not None
            and report.get("snapshot_before") == accepted_snapshot_id
            and report.get("snapshot_after") == accepted_snapshot_id
        ):
            approved_review_paths.add(relative)
    if not approved_review_paths:
        errors.append("Complete implementation transition lacks a persisted accepted review")

    delivery_refs = set(delivery_evidence_refs)
    delivery_paths = {
        relative
        for ref in delivery_refs
        if isinstance(ref, str)
        for relative in [_ledger_relative_ref(ref)]
        if relative is not None
    }
    if current_run.get("ledger_ref") not in delivery_refs:
        errors.append("Complete delivery event does not reference the implementation Ledger")
    if approved_review_paths and not approved_review_paths & delivery_paths:
        errors.append("Complete delivery event does not reference the accepted review")
    if accepted_snapshot_paths and not accepted_snapshot_paths & delivery_paths:
        errors.append("Complete delivery event does not reference the canonical snapshot")
    return errors


def validate_record(record: dict[str, Any]) -> list[str]:
    schema_errors = _schema_errors(record, _delivery_run_schema())
    if schema_errors:
        return [f"delivery-run/v1 schema violation ({len(schema_errors)} issue(s))"]
    errors: list[str] = []
    required = {
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
    missing = required - set(record)
    if missing:
        return [f"missing required fields: {sorted(missing)}"]
    if record.get("schema") != SCHEMA:
        errors.append("schema is not delivery-run/v1")
    try:
        validate_work_id(record.get("work_id", ""))
    except DeliveryError as exc:
        errors.append(str(exc))
    for field in ("request_sha256", "repo_id"):
        if not SHA256_RE.fullmatch(str(record.get(field, ""))):
            errors.append(f"{field} is not SHA-256")
    if not GIT_SHA_RE.fullmatch(str(record.get("initial_base_sha", ""))):
        errors.append("initial_base_sha is not a lowercase Git object ID")
    work_id = record.get("work_id")
    if record.get("artifact_root") != f"docs/work/{work_id}":
        errors.append("artifact_root does not match work_id")
    primary_worktree = record.get("primary_worktree")
    if not isinstance(primary_worktree, str) or not primary_worktree:
        errors.append("primary_worktree is missing")

    phase = record.get("phase")
    status = record.get("status")
    if phase not in PHASE_TRANSITIONS:
        errors.append(f"unknown phase {phase!r}")
    if status not in STATUS_TRANSITIONS:
        errors.append(f"unknown status {status!r}")
    if (phase == "complete") != (status == "complete"):
        errors.append("phase/status complete must be paired")

    generations = record.get("generations")
    if not isinstance(generations, list) or not generations:
        errors.append("generations must be a non-empty array")
        generations = []
    numbers = [item.get("generation") for item in generations if isinstance(item, dict)]
    if numbers != list(range(1, len(generations) + 1)):
        errors.append("generation numbers are not contiguous")
    if record.get("current_generation") != (numbers[-1] if numbers else None):
        errors.append("current_generation is not the last generation")
    for item in generations:
        if not isinstance(item, dict):
            errors.append("generation entry is not an object")
            continue
        number = item.get("generation")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            errors.append("generation number is invalid")
            continue
        expected_branch = f"delivery/{workspace_label(str(work_id), number)}" if isinstance(number, int) else None
        if item.get("branch") != expected_branch:
            errors.append(f"generation {number} branch is not canonical")
        canonical_worktree = item.get("canonical_worktree")
        if not isinstance(canonical_worktree, str) or not canonical_worktree:
            errors.append(f"generation {number} canonical_worktree is missing")
        elif item.get("worktree_key") != path_key(canonical_worktree):
            errors.append(f"generation {number} worktree_key is not canonical")
        elif (
            isinstance(primary_worktree, str)
            and primary_worktree
            and isinstance(work_id, str)
            and WORK_ID_RE.fullmatch(work_id)
        ):
            expected_worktree, _ = destination_and_branch(primary_worktree, str(work_id), number)
            if canonical_path_text(canonical_worktree) != canonical_path_text(expected_worktree):
                errors.append(f"generation {number} worktree path is not canonical")
        if not GIT_SHA_RE.fullmatch(str(item.get("base_sha", ""))):
            errors.append(f"generation {number} base_sha is invalid")
        if item.get("status") not in {"reserved", "ready", "blocked"}:
            errors.append(f"generation {number} has invalid status")
        if not _is_utc_datetime(item.get("created_at")):
            errors.append(f"generation {number} created_at is not UTC RFC 3339")
    if generations and generations[0].get("base_sha") != record.get("initial_base_sha"):
        errors.append("first generation base differs from initial_base_sha")

    events = record.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty array")
        events = []
    previous_phase: str | None = None
    previous_status: str | None = None
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            errors.append(f"event {index} is not an object")
            continue
        if event.get("sequence") != index:
            errors.append(f"event {index} sequence is not contiguous")
        if not _is_utc_datetime(event.get("at")):
            errors.append(f"event {index} at is not UTC RFC 3339")
        if event.get("from_phase") != previous_phase or event.get("from_status") != previous_status:
            errors.append(f"event {index} history is discontinuous")
        target_phase = event.get("to_phase")
        target_status = event.get("to_status")
        if not EVENT_RE.fullmatch(str(event.get("kind", ""))):
            errors.append(f"event {index} kind is invalid")
        refs = event.get("evidence_refs")
        if (
            not isinstance(refs, list)
            or not refs
            or len(refs) != len(set(refs))
            or any(
                not isinstance(ref, str)
                or not EVIDENCE_REF_RE.fullmatch(ref)
                or _contains_sensitive_material(ref)
                for ref in refs
            )
        ):
            errors.append(f"event {index} evidence refs are invalid")
        if previous_phase is None:
            if target_phase != "workspace" or target_status != "active":
                errors.append("first event must enter workspace/active")
        else:
            if target_phase not in PHASE_TRANSITIONS.get(previous_phase, set()):
                errors.append(f"illegal phase transition {previous_phase} -> {target_phase}")
            if target_status not in STATUS_TRANSITIONS.get(previous_status or "", set()):
                errors.append(f"illegal status transition {previous_status} -> {target_status}")
            if previous_status == "blocked" and target_status == "active" and target_phase != previous_phase:
                errors.append("blocked recovery must remain in the same phase")
        previous_phase = target_phase
        previous_status = target_status
    if events and (previous_phase != phase or previous_status != status):
        errors.append("current phase/status differs from event history")
    if events and record.get("updated_at") != events[-1].get("at"):
        errors.append("updated_at differs from the last event")
    elif not events and not _is_utc_datetime(record.get("updated_at")):
        errors.append("updated_at is not UTC RFC 3339")

    requirements = record.get("requirements", {})
    plans = record.get("plans", {})
    implementations = record.get("implementations", {})
    for label, container, current_key, item_key in (
        ("requirements", requirements, "current_path", "path"),
        ("plans", plans, "current_handoff_path", "handoff_path"),
        ("implementations", implementations, "current_run_id", "run_id"),
    ):
        revisions = container.get("revisions" if label != "implementations" else "runs", []) if isinstance(container, dict) else []
        current = container.get(current_key) if isinstance(container, dict) else None
        values = [item.get(item_key) for item in revisions if isinstance(item, dict)]
        if current is not None and current not in values:
            errors.append(f"{label} current ref does not identify a recorded revision")

    requirement_revisions = requirements.get("revisions", []) if isinstance(requirements, dict) else []
    previous_requirement_revision = 0
    for index, item in enumerate(requirement_revisions, 1):
        if not isinstance(item, dict):
            errors.append(f"requirements revision {index} is not an object")
            continue
        revision = _requirements_revision(str(item.get("path", "")), str(record.get("artifact_root", "")))
        if revision is None or revision <= previous_requirement_revision:
            errors.append(f"requirements revision {index} path is not canonical")
        else:
            previous_requirement_revision = revision
        if not SHA256_RE.fullmatch(str(item.get("sha256", ""))) or item.get("status") != "Ready":
            errors.append(f"requirements revision {index} is not Ready with a valid hash")
        refs = item.get("approval_evidence_refs")
        if (
            not isinstance(refs, list)
            or not refs
            or len(refs) != len(set(refs))
            or any(
                not isinstance(ref, str)
                or not EVIDENCE_REF_RE.fullmatch(ref)
                or _contains_sensitive_material(ref)
                for ref in refs
            )
        ):
            errors.append(f"requirements revision {index} approval refs are invalid")

    plan_revisions = plans.get("revisions", []) if isinstance(plans, dict) else []
    previous_plan_revision = 0
    for index, item in enumerate(plan_revisions, 1):
        if not isinstance(item, dict):
            errors.append(f"plan revision {index} is not an object")
            continue
        revision = _plan_revision(str(item.get("handoff_path", "")), str(record.get("artifact_root", "")))
        if revision is None or revision <= previous_plan_revision:
            errors.append(f"plan revision {index} path is not canonical")
        else:
            previous_plan_revision = revision
        if not SHA256_RE.fullmatch(str(item.get("payload_sha256", ""))) or item.get("status") != "Ready":
            errors.append(f"plan revision {index} is not Ready with a valid payload hash")
        refs = item.get("approval_evidence_refs")
        if (
            not isinstance(refs, list)
            or not refs
            or len(refs) != len(set(refs))
            or any(
                not isinstance(ref, str)
                or not EVIDENCE_REF_RE.fullmatch(ref)
                or _contains_sensitive_material(ref)
                for ref in refs
            )
        ):
            errors.append(f"plan revision {index} approval refs are invalid")

    implementation_runs = implementations.get("runs", []) if isinstance(implementations, dict) else []
    seen_run_ids: set[str] = set()
    for index, item in enumerate(implementation_runs, 1):
        if not isinstance(item, dict):
            errors.append(f"implementation run {index} is not an object")
            continue
        run_id = str(item.get("run_id", ""))
        if not SHA256_RE.fullmatch(run_id) or run_id in seen_run_ids:
            errors.append(f"implementation run {index} has invalid or duplicate run_id")
        seen_run_ids.add(run_id)
        if item.get("status") not in {"Active", "Complete", "Awaiting upstream reapproval", "Blocked"}:
            errors.append(f"implementation run {index} has invalid status")
        ledger_ref = item.get("ledger_ref")
        if (
            not isinstance(ledger_ref, str)
            or not EVIDENCE_REF_RE.fullmatch(ledger_ref)
            or _contains_sensitive_material(ledger_ref)
        ):
            errors.append(f"implementation run {index} ledger_ref is invalid")

    if status == "complete":
        current_run_id = implementations.get("current_run_id") if isinstance(implementations, dict) else None
        current_run = next(
            (item for item in implementation_runs if isinstance(item, dict) and item.get("run_id") == current_run_id),
            None,
        )
        if current_run is None or current_run.get("status") != "Complete":
            errors.append("complete delivery lacks a Complete current implementation run")
        elif events:
            errors.extend(
                _complete_implementation_errors(
                    record,
                    current_run,
                    events[-1].get("evidence_refs", []),
                )
            )
    return errors


def load_record(path: Path) -> dict[str, Any]:
    record = _read_json(path)
    errors = validate_record(record)
    if errors:
        raise DeliveryError(f"invalid delivery record {path}: {'; '.join(errors)}", code="INVALID_RECORD")
    return record


def _record_path(run_dir: Path) -> Path:
    return run_dir / "run.json"


def _new_record(
    probe: dict[str, Any],
    work_id: str,
    request_sha256: str,
    destination: Path,
    branch: str,
) -> dict[str, Any]:
    now = utc_now()
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "work_id": work_id,
        "request_sha256": request_sha256,
        "repo_id": probe["repo_id"],
        "primary_worktree": probe["primary_worktree"],
        "initial_base_sha": probe["head_sha"],
        "artifact_root": f"docs/work/{work_id}",
        "phase": "workspace",
        "status": "active",
        "current_generation": 1,
        "generations": [
            {
                "generation": 1,
                "canonical_worktree": str(destination),
                "worktree_key": path_key(destination),
                "branch": branch,
                "base_sha": probe["head_sha"],
                "status": "reserved",
                "created_at": now,
            }
        ],
        "requirements": {"current_path": None, "revisions": []},
        "plans": {"current_handoff_path": None, "revisions": []},
        "implementations": {"current_run_id": None, "runs": []},
        "events": [],
        "updated_at": now,
    }
    _append_event(
        record,
        kind="workspace_reserved",
        phase="workspace",
        status="active",
        evidence_refs=["evidence/probe.json"],
    )
    return record


def _probe_evidence(probe: dict[str, Any], destination: Path, branch: str, generation: int) -> dict[str, Any]:
    return {
        "repo_id": probe["repo_id"],
        "primary_worktree": probe["primary_worktree"],
        "requested_worktree": probe["canonical_worktree"],
        "is_primary": probe["is_primary"],
        "attached": probe["attached"],
        "branch": probe["branch"],
        "head_sha": probe["head_sha"],
        "strict_clean": probe["strict_clean"],
        "status_sha256": probe["status_sha256"],
        "destination": str(destination),
        "delivery_branch": branch,
        "generation": generation,
    }


def _validate_ready_generation(record: dict[str, Any], probe: dict[str, Any]) -> None:
    generation = record["generations"][-1]
    if generation["status"] != "ready":
        return
    workspace = probe_repository(generation["canonical_worktree"])
    if workspace["repo_id"] != record["repo_id"]:
        raise DeliveryError("delivery worktree repo_id differs from its record", code="WORKSPACE_DRIFT")
    if workspace["is_primary"]:
        raise DeliveryError("delivery record points at the primary worktree", code="WORKSPACE_DRIFT")
    if workspace["branch"] != generation["branch"]:
        raise DeliveryError("delivery branch differs from its record", code="WORKSPACE_DRIFT")
    ancestry = _git(
        generation["canonical_worktree"],
        ["merge-base", "--is-ancestor", generation["base_sha"], "HEAD"],
        check=False,
    )
    if ancestry.returncode != 0:
        raise DeliveryError("delivery HEAD no longer descends from its recorded base", code="WORKSPACE_DRIFT")
    listed = {
        canonical_path_text(str(item["worktree"]))
        for item in probe["worktrees"]
        if "worktree" in item
    }
    if canonical_path_text(generation["canonical_worktree"]) not in listed:
        raise DeliveryError("delivery worktree is absent from git worktree list", code="WORKSPACE_DRIFT")


def _requirements_revision(path: str, artifact_root: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(artifact_root)}/requirements(?:-([2-9][0-9]*))?\.md", path)
    if not match:
        return None
    return int(match.group(1)) if match.group(1) else 1


def _plan_revision(path: str, artifact_root: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(artifact_root)}/plan(?:-([2-9][0-9]*))?/handoff\.json", path)
    if not match:
        return None
    return int(match.group(1)) if match.group(1) else 1


def _revision_path(artifact_root: str, kind: str, revision: int) -> str:
    suffix = "" if revision == 1 else f"-{revision}"
    if kind == "requirements":
        return f"{artifact_root}/requirements{suffix}.md"
    return f"{artifact_root}/plan{suffix}/handoff.json"


def _assert_smallest_available_revision(
    record: dict[str, Any],
    *,
    kind: str,
    candidate_path: str,
    revision: int,
    recorded_paths: set[str],
) -> None:
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    for number in range(1, revision):
        relative = _revision_path(record["artifact_root"], kind, number)
        if relative in recorded_paths:
            continue
        candidate = worktree / Path(*relative.split("/"))
        occupied = candidate.parent.exists() if kind == "plan" else os.path.lexists(candidate)
        if not occupied:
            raise DeliveryError(
                f"{candidate_path} is not the smallest available revision; use {relative}",
                code="INVALID_REVISION",
            )


def _ready_payload_sha256(handoff: dict[str, Any]) -> str:
    normalized = copy.deepcopy(handoff)
    normalized.get("candidate", {}).pop("payload_sha256", None)
    normalized["approval"] = {"status": "Candidate", "actor": None, "confirmed_at": None, "evidence": None}
    for artifact in normalized.get("artifacts", []):
        if isinstance(artifact, dict):
            artifact["approval_status"] = "Candidate"
    return sha256_bytes(canonical_json(normalized))


def _verify_repo_file(record: dict[str, Any], relative: str, expected_sha256: str) -> None:
    validate_sha256(expected_sha256, "artifact sha256")
    _normalized_repo_path(relative)
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    path = canonical_path(worktree / Path(*relative.split("/")))
    if not _is_relative_to(path, canonical_path(worktree)):
        raise DeliveryError("artifact path escapes the delivery worktree", code="INVALID_PATH")
    if not path.is_file():
        raise DeliveryError(f"artifact does not exist: {relative}", code="MISSING_ARTIFACT")
    actual = sha256_bytes(path.read_bytes())
    if actual != expected_sha256:
        raise DeliveryError(f"artifact hash differs for {relative}", code="ARTIFACT_DRIFT")


def _verify_ready_local_sources(
    record: dict[str, Any],
    handoff: dict[str, Any],
    materialized_paths: set[str],
    *,
    verify_current_sources: bool,
) -> None:
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    base_sha = record["generations"][-1]["base_sha"]
    filter_drivers = _active_filter_drivers(worktree) if verify_current_sources else []
    for source in handoff["sources"]:
        location = source["location"]
        if urlparse(location).scheme:
            continue
        relative = _normalized_repo_path(location)
        expected = source["sha256"]
        validate_sha256(expected, "source sha256")
        if relative not in materialized_paths:
            base_bytes = _git(
                worktree,
                ["cat-file", "blob", f"{base_sha}:{relative}"],
                check=False,
            )
            if base_bytes.returncode != 0:
                raise _git_failure_error(
                    base_bytes,
                    fallback_code="SOURCE_NOT_MATERIALIZABLE",
                    fallback_message=(
                        "local Ready source is neither base-tracked nor an approved materialized artifact"
                    ),
                )
            if not verify_current_sources and sha256_bytes(base_bytes.stdout) != expected:
                raise DeliveryError(
                    "local Ready source bytes differ from the recorded Git base",
                    code="SOURCE_NOT_MATERIALIZABLE",
                )
        if not verify_current_sources:
            continue
        path = canonical_path(worktree / Path(*relative.split("/")))
        if not _is_relative_to(path, canonical_path(worktree)) or not path.is_file():
            raise DeliveryError("local Ready source is missing or escapes its worktree", code="SOURCE_DRIFT")
        if sha256_bytes(path.read_bytes()) != expected:
            raise DeliveryError("local Ready source hash differs from its manifest", code="SOURCE_DRIFT")
        if relative not in materialized_paths:
            source_status = _git(
                worktree,
                [
                    *_filter_disable_config(filter_drivers),
                    "status",
                    "--porcelain=v2",
                    "-z",
                    "--untracked-files=all",
                    "--ignore-submodules=none",
                    "--",
                    relative,
                ],
            ).stdout
            if source_status:
                raise DeliveryError(
                    "non-artifact Ready source differs from the recorded Git base",
                    code="SOURCE_NOT_MATERIALIZABLE",
                )


def _approved_upstream_materialization(
    record: dict[str, Any],
    *,
    verify_current_sources: bool = False,
) -> list[dict[str, Any]]:
    """Read and verify only the approved upstream bytes for a later generation."""
    source_worktree = Path(record["generations"][-1]["canonical_worktree"])
    materialization: dict[str, dict[str, Any]] = {}

    def include(relative: str, expected_sha256: str) -> None:
        _verify_repo_file(record, relative, expected_sha256)
        path = source_worktree / Path(*relative.split("/"))
        value = path.read_bytes()
        existing = materialization.get(relative)
        item = {"path": relative, "sha256": expected_sha256, "bytes": value}
        if existing is not None and (existing["sha256"] != expected_sha256 or existing["bytes"] != value):
            raise DeliveryError(f"approved upstream path has conflicting bytes: {relative}", code="ARTIFACT_COLLISION")
        materialization[relative] = item

    requirements_path = record["requirements"]["current_path"]
    requirements_entry = next(
        (
            item
            for item in record["requirements"]["revisions"]
            if item["path"] == requirements_path and item["status"] == "Ready"
        ),
        None,
    )
    if requirements_path is not None:
        if requirements_entry is None or not requirements_entry.get("approval_evidence_refs"):
            raise DeliveryError("current requirements lack a Ready approved revision", code="INVALID_RECORD")
        include(requirements_path, requirements_entry["sha256"])

    handoff_path = record["plans"]["current_handoff_path"]
    if handoff_path is None:
        return [materialization[key] for key in sorted(materialization)]
    plan_entry = next(
        (
            item
            for item in record["plans"]["revisions"]
            if item["handoff_path"] == handoff_path and item["status"] == "Ready"
        ),
        None,
    )
    if plan_entry is None or not plan_entry.get("approval_evidence_refs"):
        raise DeliveryError("current handoff lacks a Ready approved revision", code="INVALID_RECORD")
    if requirements_entry is not None and set(plan_entry["approval_evidence_refs"]) & set(
        requirements_entry["approval_evidence_refs"]
    ):
        raise DeliveryError("requirements and plan approval evidence are not distinct", code="INVALID_RECORD")

    handoff_file = source_worktree / Path(*handoff_path.split("/"))
    try:
        handoff_bytes = handoff_file.read_bytes()
        handoff = json.loads(handoff_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"cannot read current Ready handoff: {exc}", code="INVALID_HANDOFF") from exc
    if not isinstance(handoff, dict) or handoff.get("schema") != "ready-plan/v1":
        raise DeliveryError("current handoff is not ready-plan/v1", code="INVALID_HANDOFF")
    _validate_ready_contract(handoff)
    approval = handoff.get("approval", {})
    if (
        approval.get("status") != "Ready"
        or not isinstance(approval.get("actor"), str)
        or not approval.get("actor")
        or not _is_aware_datetime(approval.get("confirmed_at"))
        or approval.get("evidence") not in plan_entry["approval_evidence_refs"]
    ):
        raise DeliveryError("current handoff approval differs from delivery record", code="INVALID_HANDOFF")
    baseline = handoff.get("planning_baseline", {})
    if (
        baseline.get("repo_id") != record["repo_id"]
        or baseline.get("head_sha") != record["generations"][-1]["base_sha"]
    ):
        raise DeliveryError("current handoff planning baseline differs from delivery generation", code="INVALID_HANDOFF")
    candidate = handoff.get("candidate", {})
    if (
        candidate.get("revision") != plan_entry["candidate_revision"]
        or candidate.get("payload_sha256") != plan_entry["payload_sha256"]
        or _ready_payload_sha256(handoff) != plan_entry["payload_sha256"]
    ):
        raise DeliveryError("current handoff Candidate digest differs from delivery record", code="INVALID_HANDOFF")
    sources = handoff.get("sources")
    if not isinstance(sources, list) or requirements_entry is None:
        raise DeliveryError("current handoff cannot bind current requirements", code="INVALID_HANDOFF")
    spec_sources = [source for source in sources if source.get("kind") == "spec"]
    if (
        len(spec_sources) != 1
        or spec_sources[0].get("location") != requirements_entry["path"]
        or spec_sources[0].get("sha256") != requirements_entry["sha256"]
    ):
        raise DeliveryError("current handoff spec source differs from current requirements", code="INVALID_HANDOFF")

    plan_root = handoff_path.rsplit("/", 1)[0]
    artifacts = handoff.get("artifacts")
    if not isinstance(artifacts, list):
        raise DeliveryError("current handoff artifact manifest is missing", code="INVALID_HANDOFF")
    handoff_manifest_entries = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("approval_status") != "Ready":
            raise DeliveryError("current plan artifact is not Ready", code="INVALID_HANDOFF")
        relative = _normalized_repo_path(str(artifact.get("path", "")))
        if not relative.startswith(f"{plan_root}/"):
            raise DeliveryError("current plan artifact escapes the approved plan bundle", code="INVALID_HANDOFF")
        if relative == handoff_path:
            handoff_manifest_entries += 1
            if artifact.get("role") != "handoff" or artifact.get("sha256") is not None:
                raise DeliveryError("handoff self-manifest entry is invalid", code="INVALID_HANDOFF")
            continue
        expected = artifact.get("sha256")
        validate_sha256(expected, f"artifact {relative} sha256")
        include(relative, expected)
    if handoff_manifest_entries != 1:
        raise DeliveryError("artifact manifest must identify current handoff exactly once", code="INVALID_HANDOFF")
    actual_handoff_sha = sha256_bytes(handoff_bytes)
    materialization[handoff_path] = {
        "path": handoff_path,
        "sha256": actual_handoff_sha,
        "bytes": handoff_bytes,
    }
    _verify_ready_local_sources(
        record,
        handoff,
        set(materialization),
        verify_current_sources=verify_current_sources,
    )
    return [materialization[key] for key in sorted(materialization)]


def _materialize_approved_upstream(destination: Path, items: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    canonical_destination = canonical_path(destination)
    for item in items:
        relative = _normalized_repo_path(item["path"])
        target = canonical_path(canonical_destination / Path(*relative.split("/")))
        if not _is_relative_to(target, canonical_destination):
            raise DeliveryError("approved upstream target escapes the new worktree", code="INVALID_PATH")
        expected = item["sha256"]
        value = item["bytes"]
        if sha256_bytes(value) != expected:
            raise DeliveryError(f"approved upstream in-memory bytes drifted: {relative}", code="ARTIFACT_DRIFT")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or sha256_bytes(target.read_bytes()) != expected:
                raise DeliveryError(f"new generation path would be overwritten: {relative}", code="ARTIFACT_COLLISION")
        else:
            try:
                with target.open("xb") as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError as exc:
                raise DeliveryError(f"new generation path appeared concurrently: {relative}", code="ARTIFACT_COLLISION") from exc
        if sha256_bytes(target.read_bytes()) != expected:
            raise DeliveryError(f"materialized upstream hash differs: {relative}", code="ARTIFACT_DRIFT")
        evidence.append({"path": relative, "sha256": expected})
    return evidence


def _result(record: dict[str, Any], record_path: Path, *, outcome: str) -> dict[str, Any]:
    generation = record["generations"][-1]
    return {
        "outcome": outcome,
        "schema": record["schema"],
        "work_id": record["work_id"],
        "phase": record["phase"],
        "status": record["status"],
        "generation": generation["generation"],
        "worktree": generation["canonical_worktree"],
        "branch": generation["branch"],
        "base_sha": generation["base_sha"],
        "artifact_root": record["artifact_root"],
        "record_path": str(record_path),
    }


def _transition_record_unlocked(
    repo: str | Path,
    work_id: str,
    phase: str,
    status: str,
    event: str,
    evidence_refs: Sequence[str],
    *,
    root: Path | None = None,
    requirements_path: str | None = None,
    requirements_sha256: str | None = None,
    requirements_approval_refs: Sequence[str] = (),
    handoff_path: str | None = None,
    candidate_revision: str | None = None,
    payload_sha256: str | None = None,
    plan_approval_refs: Sequence[str] = (),
    implementation_run_id: str | None = None,
    implementation_ledger_ref: str | None = None,
    implementation_status: str | None = None,
) -> dict[str, Any]:
    root = _validate_registry_root(root or default_registry_root())
    validate_work_id(work_id)
    probe = probe_repository(repo)
    path = _record_path(run_directory(root, probe["repo_id"], work_id))
    record = load_record(path)
    if record["status"] == "complete":
        raise DeliveryError("Complete delivery records are frozen", code="COMPLETE_FROZEN")
    if record["generations"][-1]["status"] == "ready":
        _validate_ready_generation(record, probe)
    if record["generations"][-1]["status"] != "ready" and status != "blocked":
        raise DeliveryError("current generation is not ready", code="WORKSPACE_NOT_READY")
    current_phase = record["phase"]
    current_status = record["status"]
    if phase not in PHASE_TRANSITIONS.get(current_phase, set()):
        raise DeliveryError(f"illegal phase transition {current_phase} -> {phase}", code="ILLEGAL_TRANSITION")
    if status not in STATUS_TRANSITIONS.get(current_status, set()):
        raise DeliveryError(f"illegal status transition {current_status} -> {status}", code="ILLEGAL_TRANSITION")
    if current_status == "blocked" and status == "active" and phase != current_phase:
        raise DeliveryError("blocked recovery must remain in the same phase", code="ILLEGAL_TRANSITION")
    if status == "awaiting_user" and phase not in {"requirements", "planning"}:
        raise DeliveryError("awaiting_user is only valid for requirements or planning", code="ILLEGAL_TRANSITION")
    if (phase == "complete") != (status == "complete"):
        raise DeliveryError("complete phase and status must be paired", code="ILLEGAL_TRANSITION")

    if (current_phase, phase) == ("planning", "requirements"):
        record["plans"]["current_handoff_path"] = None
        record["implementations"]["current_run_id"] = None
    elif (current_phase, phase) == ("implementation", "planning"):
        record["plans"]["current_handoff_path"] = None
        record["implementations"]["current_run_id"] = None

    if any(value is not None for value in (requirements_path, requirements_sha256)) or requirements_approval_refs:
        if requirements_path is None or requirements_sha256 is None or not requirements_approval_refs:
            raise DeliveryError("Ready requirements require path, hash, and approval evidence", code="INCOMPLETE_ARTIFACT_REF")
        if (phase, status) != ("planning", "active"):
            raise DeliveryError("Ready requirements must atomically advance to planning/active", code="MISSING_GATE")
        requirements_path = _normalized_repo_path(requirements_path)
        revision = _requirements_revision(requirements_path, record["artifact_root"])
        if revision is None:
            raise DeliveryError("requirements path is outside the Work ID artifact root", code="INVALID_PATH")
        _verify_repo_file(record, requirements_path, requirements_sha256)
        approval_refs = _logical_refs(requirements_approval_refs, "requirements approval")
        entry = {
            "path": requirements_path,
            "sha256": requirements_sha256,
            "status": "Ready",
            "approval_evidence_refs": approval_refs,
        }
        existing = next(
            (item for item in record["requirements"]["revisions"] if item["path"] == requirements_path),
            None,
        )
        if existing is not None:
            raise DeliveryError(
                "an approved requirements revision cannot be reused as a new approval",
                code="ARTIFACT_ALREADY_APPROVED",
            )
        _assert_smallest_available_revision(
            record,
            kind="requirements",
            candidate_path=requirements_path,
            revision=revision,
            recorded_paths={item["path"] for item in record["requirements"]["revisions"]},
        )
        record["requirements"]["revisions"].append(entry)
        record["requirements"]["current_path"] = requirements_path

    if any(value is not None for value in (handoff_path, candidate_revision, payload_sha256)) or plan_approval_refs:
        if handoff_path is None or candidate_revision is None or payload_sha256 is None or not plan_approval_refs:
            raise DeliveryError("Ready plan requires handoff, revision, payload hash, and approval evidence", code="INCOMPLETE_ARTIFACT_REF")
        if (phase, status) != ("implementation", "active"):
            raise DeliveryError("Ready plan must atomically advance to implementation/active", code="MISSING_GATE")
        handoff_path = _normalized_repo_path(handoff_path)
        revision = _plan_revision(handoff_path, record["artifact_root"])
        if revision is None:
            raise DeliveryError("handoff path is outside the Work ID plan root", code="INVALID_PATH")
        handoff_file = Path(record["generations"][-1]["canonical_worktree"]) / Path(*handoff_path.split("/"))
        try:
            handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DeliveryError(f"cannot read Ready handoff: {exc}", code="INVALID_HANDOFF") from exc
        if not isinstance(handoff, dict):
            raise DeliveryError("handoff is not a JSON object", code="INVALID_HANDOFF")
        _validate_ready_contract(handoff)
        approval = handoff.get("approval", {})
        if (
            handoff.get("schema") != "ready-plan/v1"
            or approval.get("status") != "Ready"
            or not isinstance(approval.get("actor"), str)
            or not approval.get("actor")
            or not _is_aware_datetime(approval.get("confirmed_at"))
        ):
            raise DeliveryError("handoff is not a Ready ready-plan/v1", code="INVALID_HANDOFF")
        baseline = handoff.get("planning_baseline", {})
        if (
            baseline.get("repo_id") != record["repo_id"]
            or baseline.get("head_sha") != record["generations"][-1]["base_sha"]
        ):
            raise DeliveryError("handoff planning baseline differs from current delivery generation", code="INVALID_HANDOFF")
        if handoff.get("candidate", {}).get("revision") != candidate_revision:
            raise DeliveryError("handoff candidate revision differs", code="INVALID_HANDOFF")
        if handoff.get("candidate", {}).get("payload_sha256") != payload_sha256:
            raise DeliveryError("handoff payload digest differs", code="INVALID_HANDOFF")
        validate_sha256(payload_sha256, "payload_sha256")
        if _ready_payload_sha256(handoff) != payload_sha256:
            raise DeliveryError("handoff payload digest does not match its canonical bytes", code="INVALID_HANDOFF")
        approval_refs = _logical_refs(plan_approval_refs, "plan approval")
        if approval.get("evidence") not in approval_refs:
            raise DeliveryError("plan approval evidence differs between handoff and delivery record", code="INVALID_HANDOFF")
        current_requirements_path = record["requirements"]["current_path"]
        current_requirements = next(
            (
                item
                for item in record["requirements"]["revisions"]
                if item["path"] == current_requirements_path and item["status"] == "Ready"
            ),
            None,
        )
        if current_requirements is None:
            raise DeliveryError("Ready plan has no current approved requirements binding", code="MISSING_GATE")
        if set(approval_refs) & set(current_requirements["approval_evidence_refs"]):
            raise DeliveryError("requirements and plan require distinct approval evidence", code="INVALID_HANDOFF")
        sources = handoff.get("sources")
        if not isinstance(sources, list):
            raise DeliveryError("handoff sources must be an array", code="INVALID_HANDOFF")
        spec_sources = [source for source in sources if source.get("kind") == "spec"]
        if (
            len(spec_sources) != 1
            or spec_sources[0].get("location") != current_requirements["path"]
            or spec_sources[0].get("sha256") != current_requirements["sha256"]
        ):
            raise DeliveryError(
                "handoff must contain exactly one kind: spec source matching current requirements path and hash",
                code="INVALID_HANDOFF",
            )
        entry = {
            "handoff_path": handoff_path,
            "candidate_revision": candidate_revision,
            "payload_sha256": payload_sha256,
            "status": "Ready",
            "approval_evidence_refs": approval_refs,
        }
        existing = next(
            (item for item in record["plans"]["revisions"] if item["handoff_path"] == handoff_path),
            None,
        )
        if existing is not None:
            raise DeliveryError(
                "an approved plan revision cannot be reused as a new approval",
                code="ARTIFACT_ALREADY_APPROVED",
            )
        _assert_smallest_available_revision(
            record,
            kind="plan",
            candidate_path=handoff_path,
            revision=revision,
            recorded_paths={item["handoff_path"] for item in record["plans"]["revisions"]},
        )
        record["plans"]["revisions"].append(entry)
        record["plans"]["current_handoff_path"] = handoff_path
        _approved_upstream_materialization(record, verify_current_sources=True)

    if any(value is not None for value in (implementation_run_id, implementation_ledger_ref, implementation_status)):
        if implementation_run_id is None or implementation_ledger_ref is None or implementation_status is None:
            raise DeliveryError("implementation ref requires run ID, Ledger ref, and status", code="INCOMPLETE_ARTIFACT_REF")
        validate_sha256(implementation_run_id, "implementation_run_id")
        try:
            implementation_ledger_ref = _logical_refs([implementation_ledger_ref], "implementation Ledger")[0]
        except DeliveryError as exc:
            raise DeliveryError(str(exc), code="INVALID_IMPLEMENTATION_REF") from exc
        if implementation_status not in {"Active", "Complete", "Awaiting upstream reapproval", "Blocked"}:
            raise DeliveryError("invalid implementation status", code="INVALID_IMPLEMENTATION_REF")
        entry = {
            "run_id": implementation_run_id,
            "ledger_ref": implementation_ledger_ref,
            "status": implementation_status,
        }
        existing = next(
            (item for item in record["implementations"]["runs"] if item["run_id"] == implementation_run_id),
            None,
        )
        if existing is not None:
            existing["ledger_ref"] = implementation_ledger_ref
            existing["status"] = implementation_status
        else:
            record["implementations"]["runs"].append(entry)
        record["implementations"]["current_run_id"] = implementation_run_id

    if phase == "planning" and current_phase == "requirements" and requirements_path is None:
        raise DeliveryError("planning requires a newly persisted Ready requirements revision", code="MISSING_GATE")
    if phase == "implementation" and current_phase == "planning" and handoff_path is None:
        raise DeliveryError("implementation requires the newly Ready plan and may not ask a third approval", code="MISSING_GATE")
    if phase == "complete":
        _approved_upstream_materialization(record)
        current_run_id = record["implementations"]["current_run_id"]
        current_run = next(
            (item for item in record["implementations"]["runs"] if item["run_id"] == current_run_id),
            None,
        )
        if current_run is None or current_run["status"] != "Complete":
            raise DeliveryError("delivery Complete requires a Complete implementation run", code="MISSING_GATE")
        terminal_errors = _complete_implementation_errors(record, current_run, evidence_refs)
        if terminal_errors:
            raise DeliveryError(
                "delivery Complete requires persisted implementation Ledger and accepted review evidence",
                code="MISSING_GATE",
            )

    _append_event(record, kind=event, phase=phase, status=status, evidence_refs=evidence_refs)
    errors = validate_record(record)
    if errors:
        raise DeliveryError(f"transition would create an invalid record: {'; '.join(errors)}", code="INVALID_RECORD")
    _atomic_write_json(path, record)
    return _result(record, path, outcome="transitioned")
