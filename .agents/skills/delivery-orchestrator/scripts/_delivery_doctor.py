#!/usr/bin/env python3
"""Read-only diagnostics for delivery workspace continuity."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from _delivery_git import probe_repository
from _delivery_record import (
    _approved_upstream_materialization,
    _record_path,
    _validate_ready_generation,
    load_record,
)
from _delivery_runtime import (
    DeliveryError,
    _validate_registry_root,
    canonical_path,
    canonical_path_text,
    default_registry_root,
    validate_work_id,
)


DOCTOR_SCHEMA = "delivery-doctor/v1"
PROCESS_METRICS_SCHEMA = "delivery-process-metrics/v1"
CHECK_IDS = (
    "repository_identity",
    "registry",
    "record",
    "generation",
    "artifacts",
    "evidence",
    "recovery",
)
PHASES = ("workspace", "requirements", "planning", "implementation", "knowledge", "complete")
PHASE_RANK = {phase: index for index, phase in enumerate(PHASES)}
INVALID_REPOSITORY_CODES = frozenset({"NOT_A_REPOSITORY", "BARE_REPOSITORY"})
DIAGNOSTIC_MESSAGES = {
    "NO_ACTIVE_RUN": "No matching active delivery run is available.",
    "AMBIGUOUS_RUNS": "More than one active run exists; an explicit Work ID is required.",
    "RECORD_MISSING": "The selected Work ID directory has no delivery record.",
    "INVALID_RECORD": "The delivery record is missing required or trustworthy structure.",
    "IDENTITY_MISMATCH": "The requested repository or worktree differs from the recorded generation.",
    "ARTIFACT_DRIFT": "Approved artifact or source bytes no longer match their recorded hashes.",
    "EVIDENCE_MISSING": "Required approval or review evidence is not bound to the record.",
    "RECOVERY_REQUIRED": "An unfinished Project Knowledge transaction must be recovered first.",
    "ENVIRONMENT_UNAVAILABLE": "The environment cannot complete the requested read-only checks.",
    "INVALID_INPUT": "The doctor input is invalid.",
}
ACTION_TEXT = {
    "NO_ACTIVE_RUN": "Start a new governed Work ID and establish fresh requirements evidence.",
    "AMBIGUOUS_RUNS": "Choose one listed Work ID and run doctor again with --work-id.",
    "RECORD_MISSING": "Preserve the existing workspace and create a new Work ID; do not reconstruct approvals.",
    "INVALID_RECORD": "Preserve the record and workspace as evidence, then create a new governed Work ID.",
    "IDENTITY_MISMATCH": "Move to the recorded canonical worktree and repeat doctor before authorization.",
    "ARTIFACT_DRIFT": "Preserve current edits and return to the owning upstream stage for fresh approval.",
    "EVIDENCE_MISSING": "Create a new work path and revalidate the missing human evidence.",
    "RECOVERY_REQUIRED": "Run knowledge_cli.py recover --repo <recorded-worktree>, then repeat doctor.",
    "ENVIRONMENT_UNAVAILABLE": "Restore Git, filesystem, or repository access and repeat doctor.",
    "INVALID_INPUT": "Correct the input and repeat the read-only doctor command.",
}


def _new_report() -> dict[str, Any]:
    return {
        "schema": DOCTOR_SCHEMA,
        "outcome": "blocked",
        "work": None,
        "available_work_ids": [],
        "checks": [
            {"check_id": check_id, "outcome": "not_run", "diagnostic_codes": []}
            for check_id in CHECK_IDS
        ],
        "diagnostics": [],
        "next_actions": [],
        "process_metrics": {
            "schema": PROCESS_METRICS_SCHEMA,
            "outcome": "not_calculable",
            "event_count": 0,
            "phase_durations_seconds": {phase: None for phase in PHASES},
            "phase_return_count": None,
            "unavailable_fields": ["events"],
        },
    }


def _check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(item for item in report["checks"] if item["check_id"] == check_id)


def _set_check(
    report: dict[str, Any],
    check_id: str,
    outcome: str,
    code: str | None = None,
) -> None:
    item = _check(report, check_id)
    item["outcome"] = outcome
    if code is not None and code not in item["diagnostic_codes"]:
        item["diagnostic_codes"].append(code)


def _add_diagnostic(
    report: dict[str, Any],
    check_id: str,
    code: str,
    *,
    outcome: str = "blocked",
) -> None:
    if not any(
        item["code"] == code and item["check_id"] == check_id
        for item in report["diagnostics"]
    ):
        report["diagnostics"].append(
            {
                "code": code,
                "check_id": check_id,
                "message": DIAGNOSTIC_MESSAGES.get(code, "The check could not be completed safely."),
            }
        )
    _set_check(report, check_id, outcome, code)


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    codes = [item["code"] for item in report["diagnostics"]]
    if report.get("outcome") == "invalid":
        pass
    elif "ENVIRONMENT_UNAVAILABLE" in codes:
        report["outcome"] = "unavailable"
    elif codes:
        report["outcome"] = "blocked"
    else:
        report["outcome"] = "passed"

    seen: set[str] = set()
    actions: list[dict[str, str]] = []
    for code in codes:
        action_code = code if code in ACTION_TEXT else "INVALID_INPUT"
        if action_code in seen:
            continue
        seen.add(action_code)
        actions.append({"code": action_code, "action": ACTION_TEXT[action_code]})
    if not actions and report["work"] is not None:
        if report["work"]["status"] == "complete":
            actions.append(
                {
                    "code": "COMPLETE_FROZEN",
                    "action": "Keep this run read-only; create a new Work ID for further changes.",
                }
            )
        elif report["work"]["status"] == "blocked":
            actions.append(
                {
                    "code": "RESOLVE_CURRENT_BLOCKER",
                    "action": "Resolve the recorded blocker in the same phase, then repeat authorization.",
                }
            )
        else:
            actions.append(
                {
                    "code": "RESUME_CURRENT_RUN",
                    "action": "Run the current phase read-only authorization from the recorded worktree.",
                }
            )
    report["next_actions"] = actions
    return report


def doctor_exit_code(report: dict[str, Any]) -> int:
    return {
        "passed": 0,
        "invalid": 2,
        "blocked": 3,
        "unavailable": 4,
    }.get(str(report.get("outcome")), 4)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def summarize_process_metrics(events: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": PROCESS_METRICS_SCHEMA,
        "outcome": "not_calculable",
        "event_count": len(events) if isinstance(events, list) else 0,
        "phase_durations_seconds": {phase: None for phase in PHASES},
        "phase_return_count": None,
        "unavailable_fields": [],
    }
    if not isinstance(events, list) or not events:
        result["unavailable_fields"] = ["events"]
        return result

    totals: dict[str, float] = {}
    returns = 0
    valid_transitions = True
    for event in events:
        if not isinstance(event, dict):
            valid_transitions = False
            continue
        before = event.get("from_phase")
        after = event.get("to_phase")
        if before in PHASE_RANK and after in PHASE_RANK and PHASE_RANK[after] < PHASE_RANK[before]:
            returns += 1
        elif after not in PHASE_RANK:
            valid_transitions = False

    for current, following in zip(events, events[1:]):
        if not isinstance(current, dict) or not isinstance(following, dict):
            continue
        phase = current.get("to_phase")
        started = _parse_time(current.get("at"))
        ended = _parse_time(following.get("at"))
        if phase not in PHASE_RANK or started is None or ended is None or ended < started:
            continue
        totals[phase] = totals.get(phase, 0.0) + (ended - started).total_seconds()

    for phase, duration in totals.items():
        result["phase_durations_seconds"][phase] = round(duration, 6)
    final_event = events[-1]
    if isinstance(final_event, dict):
        active_phase = final_event.get("to_phase")
        if active_phase in PHASE_RANK and active_phase != "complete":
            result["phase_durations_seconds"][active_phase] = None
    result["phase_return_count"] = returns if valid_transitions else None
    result["unavailable_fields"] = [
        f"phase_durations_seconds.{phase}"
        for phase, duration in result["phase_durations_seconds"].items()
        if duration is None
    ]
    if result["phase_return_count"] is None:
        result["unavailable_fields"].append("phase_return_count")
    result["outcome"] = "calculated" if not result["unavailable_fields"] else "partially_calculable"
    return result


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


def _stable_load_record(path: Path) -> dict[str, Any]:
    if _is_redirect(path):
        raise DeliveryError("delivery record is redirected", code="INVALID_RECORD")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise OSError("record is not a regular file")
        record = load_record(path)
        after = path.lstat()
    except (OSError, FileNotFoundError) as exc:
        raise DeliveryError("delivery record is unavailable", code="INVALID_RECORD") from exc
    fingerprints = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_size,
        item.st_mtime_ns,
    )
    if fingerprints(before) != fingerprints(after) or _is_redirect(path):
        raise DeliveryError("delivery record changed while read", code="INVALID_RECORD")
    return record


def _raw_record(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _missing_evidence_bindings(record: dict[str, Any]) -> bool:
    requirements = record.get("requirements")
    if isinstance(requirements, dict) and requirements.get("current_path") is not None:
        current = requirements.get("current_path")
        entries = requirements.get("revisions")
        match = next(
            (
                item
                for item in entries
                if isinstance(item, dict) and item.get("path") == current and item.get("status") == "Ready"
            ),
            None,
        ) if isinstance(entries, list) else None
        if not isinstance(match, dict) or not match.get("approval_evidence_refs"):
            return True

    plans = record.get("plans")
    if isinstance(plans, dict) and plans.get("current_handoff_path") is not None:
        current = plans.get("current_handoff_path")
        entries = plans.get("revisions")
        match = next(
            (
                item
                for item in entries
                if isinstance(item, dict)
                and item.get("handoff_path") == current
                and item.get("status") == "Ready"
            ),
            None,
        ) if isinstance(entries, list) else None
        if not isinstance(match, dict) or not match.get("approval_evidence_refs"):
            return True

    knowledge = record.get("knowledge_gate")
    if isinstance(knowledge, dict):
        promotions = knowledge.get("promotions")
        if isinstance(promotions, list) and any(
            not isinstance(item, dict) or not item.get("approval_evidence")
            for item in promotions
        ):
            return True
    return False


def _knowledge_recovery_count(repo_id: str) -> int:
    host_temp = canonical_path(tempfile.gettempdir())
    knowledge_root = host_temp / "project-knowledge"
    if _is_redirect(knowledge_root):
        raise OSError("project-knowledge registry is redirected")
    journals = knowledge_root / "repos" / repo_id / "journals"
    if not journals.is_dir():
        return 0
    if _is_redirect(journals):
        raise OSError("project-knowledge journals are redirected")
    unresolved = 0
    for path in sorted(journals.glob("*/journal.json"), key=lambda item: item.as_posix()):
        if _is_redirect(path):
            unresolved += 1
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            unresolved += 1
            continue
        if not isinstance(value, dict) or value.get("status") == "in_progress":
            unresolved += 1
    return unresolved


def _candidate_directories(works_root: Path) -> list[Path]:
    if not works_root.is_dir():
        return []
    if _is_redirect(works_root):
        raise OSError("delivery works registry is redirected")
    return sorted(
        (path for path in works_root.iterdir() if path.is_dir() and not _is_redirect(path)),
        key=lambda path: path.name,
    )


def _invalid_report(code: str, check_id: str = "registry") -> dict[str, Any]:
    report = _new_report()
    report["outcome"] = "invalid"
    _add_diagnostic(report, check_id, code if code in DIAGNOSTIC_MESSAGES else "INVALID_INPUT")
    return _finalize(report)


def doctor_workspace(
    repo: str | Path,
    *,
    root: str | Path | None = None,
    work_id: str | None = None,
) -> dict[str, Any]:
    """Diagnose one delivery run without creating locks, registries, or artifacts."""
    report = _new_report()
    try:
        if work_id is not None:
            validate_work_id(work_id)
        registry = _validate_registry_root(root if root is not None else default_registry_root())
    except DeliveryError as exc:
        return _invalid_report(exc.code)

    try:
        probe = probe_repository(repo)
    except DeliveryError as exc:
        if exc.code in INVALID_REPOSITORY_CODES:
            return _invalid_report(exc.code, "repository_identity")
        _add_diagnostic(report, "repository_identity", "ENVIRONMENT_UNAVAILABLE", outcome="unavailable")
        return _finalize(report)
    except OSError:
        _add_diagnostic(report, "repository_identity", "ENVIRONMENT_UNAVAILABLE", outcome="unavailable")
        return _finalize(report)
    _set_check(report, "repository_identity", "passed")

    works_root = registry / "repos" / probe["repo_id"] / "works"
    try:
        if work_id is not None:
            requested = works_root / work_id
            candidates = [requested] if requested.is_dir() and not _is_redirect(requested) else []
            if not candidates:
                _add_diagnostic(report, "registry", "NO_ACTIVE_RUN")
                _set_check(report, "record", "not_run")
        else:
            candidates = _candidate_directories(works_root)
        if candidates:
            _set_check(report, "registry", "passed")
        elif _check(report, "registry")["outcome"] == "not_run":
            _add_diagnostic(report, "registry", "NO_ACTIVE_RUN")
    except OSError:
        _add_diagnostic(report, "registry", "ENVIRONMENT_UNAVAILABLE", outcome="unavailable")
        candidates = []

    records: list[tuple[dict[str, Any], Path]] = []
    for candidate in candidates:
        try:
            validate_work_id(candidate.name)
        except DeliveryError:
            _add_diagnostic(report, "record", "INVALID_RECORD")
            continue
        record_path = _record_path(candidate)
        if not record_path.is_file() or _is_redirect(record_path):
            _add_diagnostic(report, "record", "RECORD_MISSING")
            continue
        raw = _raw_record(record_path)
        if raw is not None and _missing_evidence_bindings(raw):
            _add_diagnostic(report, "evidence", "EVIDENCE_MISSING")
        try:
            record = _stable_load_record(record_path)
        except DeliveryError:
            _add_diagnostic(report, "record", "INVALID_RECORD")
            continue
        if record.get("work_id") != candidate.name:
            _add_diagnostic(report, "record", "INVALID_RECORD")
            continue
        if record.get("repo_id") != probe["repo_id"]:
            _add_diagnostic(report, "generation", "IDENTITY_MISMATCH")
            continue
        if work_id is None and record.get("status") == "complete":
            continue
        records.append((record, record_path))

    report["available_work_ids"] = sorted(record["work_id"] for record, _ in records)
    if len(records) > 1:
        _add_diagnostic(report, "record", "AMBIGUOUS_RUNS")
        return _finish_recovery(report, probe["repo_id"])
    if not records:
        if candidates and _check(report, "record")["outcome"] == "not_run":
            _add_diagnostic(report, "record", "NO_ACTIVE_RUN")
        return _finish_recovery(report, probe["repo_id"])

    record, record_path = records[0]
    _set_check(report, "record", "passed")
    generation = record["generations"][-1]
    report["work"] = {
        "work_id": record["work_id"],
        "generation": generation["generation"],
        "phase": record["phase"],
        "status": record["status"],
        "worktree": generation["canonical_worktree"],
        "branch": generation["branch"],
        "base_sha": generation["base_sha"],
        "record_path": str(record_path),
    }
    report["process_metrics"] = summarize_process_metrics(record.get("events"))

    requested_matches = canonical_path_text(probe["canonical_worktree"]) == canonical_path_text(
        generation["canonical_worktree"]
    )
    generation_valid = True
    try:
        _validate_ready_generation(record, probe)
    except (DeliveryError, OSError):
        generation_valid = False
    if not requested_matches or not generation_valid:
        _add_diagnostic(report, "generation", "IDENTITY_MISMATCH")
    else:
        _set_check(report, "generation", "passed")

    if generation_valid:
        try:
            _approved_upstream_materialization(record, verify_current_sources=True)
        except (DeliveryError, OSError):
            _add_diagnostic(report, "artifacts", "ARTIFACT_DRIFT")
        else:
            _set_check(report, "artifacts", "passed")
    else:
        _set_check(report, "artifacts", "not_run")

    if _missing_evidence_bindings(record):
        _add_diagnostic(report, "evidence", "EVIDENCE_MISSING")
    elif _check(report, "evidence")["outcome"] == "not_run":
        _set_check(report, "evidence", "passed")
    return _finish_recovery(report, probe["repo_id"])


def _finish_recovery(report: dict[str, Any], repo_id: str) -> dict[str, Any]:
    try:
        unresolved = _knowledge_recovery_count(repo_id)
    except OSError:
        _add_diagnostic(report, "recovery", "ENVIRONMENT_UNAVAILABLE", outcome="unavailable")
    else:
        if unresolved:
            _add_diagnostic(report, "recovery", "RECOVERY_REQUIRED")
        else:
            _set_check(report, "recovery", "passed")
    return _finalize(report)
