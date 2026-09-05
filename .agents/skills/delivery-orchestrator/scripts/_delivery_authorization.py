#!/usr/bin/env python3
"""Read-only delivery phase authorization.

Authority: delivery-stage-authorization
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _delivery_git import probe_repository
from _delivery_record import (
    _approved_upstream_materialization,
    _record_path,
    _result,
    _validate_ready_generation,
    load_record,
)
from _delivery_runtime import (
    DeliveryError,
    _validate_registry_root,
    canonical_path_text,
    default_registry_root,
    validate_work_id,
)


AUTHORIZATION_SCHEMA = "delivery-stage-authorization/v1"
RESTRICTED_PHASES = frozenset({"requirements", "planning", "implementation"})


def _locate_from_probe(
    probe: dict[str, Any],
    root: Path,
    work_id: str | None,
) -> dict[str, Any]:
    """Locate one current delivery record without repeating the Git probe."""
    works_root = root / "repos" / probe["repo_id"] / "works"
    if work_id is not None:
        validate_work_id(work_id)
        candidates = [works_root / work_id]
    elif works_root.is_dir():
        candidates = sorted(
            (path for path in works_root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
    else:
        candidates = []

    records: list[tuple[dict[str, Any], Path]] = []
    for candidate in candidates:
        path = _record_path(candidate)
        if not path.is_file():
            if work_id is not None:
                raise DeliveryError(
                    "work_id registry is missing run.json",
                    code="INVALID_RECORD",
                )
            continue
        record = load_record(path)
        if record["work_id"] != candidate.name:
            raise DeliveryError(
                "work_id registry identity does not match the loaded record",
                code="INVALID_RECORD",
            )
        if record["repo_id"] == probe["repo_id"]:
            records.append((record, path))

    if work_id is None:
        records = [
            (record, path)
            for record, path in records
            if record["status"] != "complete"
        ]
    if not records:
        raise DeliveryError("no matching active delivery record", code="NOT_FOUND")
    if len(records) > 1:
        ids = [record["work_id"] for record, _ in records]
        raise DeliveryError(
            "multiple active delivery records require explicit selection",
            code="AMBIGUOUS_WORK",
            details={"work_ids": ids},
        )

    record, path = records[0]
    if record["generations"][-1]["status"] == "ready":
        _validate_ready_generation(record, probe)
        _approved_upstream_materialization(record)
    return _result(record, path, outcome="located")


def locate_workspace(
    repo: str | Path,
    *,
    root: Path | None = None,
    work_id: str | None = None,
) -> dict[str, Any]:
    """Locate a current delivery record without mutation."""
    registry = _validate_registry_root(root or default_registry_root())
    return _locate_from_probe(probe_repository(repo), registry, work_id)


def _routing_required(
    expected_phase: str,
    reason: str,
    located: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = None
    if located is not None:
        current = {
            key: located[key]
            for key in ("work_id", "generation", "phase", "status")
        }
    return {
        "schema": AUTHORIZATION_SCHEMA,
        "outcome": "routing_required",
        "expected_phase": expected_phase,
        "reason": reason,
        "route_to": "delivery-orchestrator",
        "current": current,
    }


def authorize_stage(
    repo: str | Path,
    expected_phase: str,
    *,
    root: Path | None = None,
    work_id: str | None = None,
) -> dict[str, Any]:
    """Authorize mutation only for the exact active phase and worktree."""
    if expected_phase not in RESTRICTED_PHASES:
        raise DeliveryError(
            "authorization phase must be requirements, planning, or implementation",
            code="INVALID_PHASE",
        )

    registry = _validate_registry_root(root or default_registry_root())
    probe = probe_repository(repo)
    try:
        located = _locate_from_probe(probe, registry, work_id)
    except DeliveryError as exc:
        if exc.code == "NOT_FOUND":
            return _routing_required(expected_phase, "no_active_delivery")
        raise

    if canonical_path_text(probe["canonical_worktree"]) != canonical_path_text(
        located["worktree"]
    ):
        return _routing_required(expected_phase, "wrong_worktree", located)
    if located["status"] != "active":
        return _routing_required(expected_phase, "inactive_status", located)
    if located["phase"] != expected_phase:
        return _routing_required(expected_phase, "wrong_phase", located)

    return {
        "schema": AUTHORIZATION_SCHEMA,
        "outcome": "authorized",
        "expected_phase": expected_phase,
        "record": located,
    }
