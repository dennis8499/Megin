#!/usr/bin/env python3
"""Safely create, locate, and advance delivery-orchestrator workspaces.

This public facade preserves the probe/start/locate/transition CLI and success
JSON contract. Private modules own runtime, Git, and record semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _delivery_runtime import (  # noqa: E402
    DeliveryError,
    BUG_ID_RE,
    EVIDENCE_REF_RE,
    EVENT_RE,
    GIT_SHA_RE,
    PHASE_TRANSITIONS,
    RESERVED_WINDOWS_NAMES,
    SCHEMA,
    SHA256_RE,
    STATUS_TRANSITIONS,
    WORK_ID_RE,
    _atomic_write_json,
    _exclusive_lock,
    _is_aware_datetime,
    _is_relative_to,
    _is_utc_datetime,
    _known_secret_values_from_env,
    _logical_refs,
    _normalized_repo_path,
    _read_json,
    _validate_registry_root,
    canonical_json,
    canonical_path,
    canonical_path_text,
    default_registry_root,
    generate_work_id,
    path_key,
    registry_root,
    run_directory,
    sha256_bytes,
    topic_slug,
    utc_now,
    validate_sha256,
    validate_bug_id,
    validate_work_id,
    workspace_label,
)
from _delivery_git import (  # noqa: E402
    FILTER_DRIVER_RE,
    GIT_ENV_PREFIX_REMOVE,
    GIT_ENV_REMOVE,
    _active_filter_drivers,
    _assert_new_work_probe,
    _assert_no_collision,
    _branch_exists,
    _decode,
    _filter_disable_config,
    _git,
    _git_failure_error,
    _indexed_gitlinks,
    _parse_worktrees,
    _strict_status,
    destination_and_branch,
    probe_repository,
    probe_repository_identity,
    probe_repository_state,
)
from _delivery_record import (  # noqa: E402
    _append_event,
    _approved_upstream_materialization,
    _contract_validator,
    _current_implementation_snapshot,
    _delivery_run_schema,
    _lock_epoch,
    _materialize_approved_upstream,
    _new_record,
    _plan_revision,
    _probe_evidence,
    _ready_payload_sha256,
    _ready_plan_schema,
    _record_path,
    _requirements_revision,
    _result,
    _schema_errors,
    _transition_record_unlocked,
    _validate_historical_ready_contract,
    _validate_repository_state_evidence,
    _validate_ready_contract,
    _validate_ready_generation,
    load_record,
    validate_record,
)


def start_workspace(
    repo: str | Path,
    work_id: str,
    request_sha256: str,
    *,
    root: Path | None = None,
    generation: int = 1,
    work_kind: str | None = None,
    bug_id: str | None = None,
    knowledge_policy: str = "required",
) -> dict[str, Any]:
    work_id = validate_work_id(work_id)
    validate_sha256(request_sha256, "request_sha256")
    if generation < 1:
        raise DeliveryError("generation must be at least 1", code="INVALID_GENERATION")
    root = _validate_registry_root(root or default_registry_root())
    requested_probe = probe_repository(repo)
    primary_probe = probe_repository(requested_probe["primary_worktree"])
    destination, branch = destination_and_branch(primary_probe["primary_worktree"], work_id, generation)
    run_dir = run_directory(root, primary_probe["repo_id"], work_id)
    record_path = _record_path(run_dir)
    materialization: list[dict[str, Any]] = []

    if generation == 1 and run_dir.exists():
        record = load_record(record_path)
        if record["repo_id"] != primary_probe["repo_id"] or record["request_sha256"] != request_sha256:
            raise DeliveryError("existing work_id registry belongs to different inputs", code="REGISTRY_COLLISION")
        recorded_kind = record.get("work_kind", "standard")
        if work_kind is not None and recorded_kind != work_kind:
            raise DeliveryError("existing work_id has a different work_kind", code="REGISTRY_COLLISION")
        if bug_id is not None and record.get("bugs", {}).get("primary_bug_id") != bug_id:
            raise DeliveryError("existing work_id has a different bug_id", code="REGISTRY_COLLISION")
        _validate_ready_generation(record, primary_probe)
        if record["generations"][-1]["status"] == "ready":
            _approved_upstream_materialization(record)
            return _result(record, record_path, outcome="existing")
        raise DeliveryError("existing work_id reservation is incomplete or blocked", code="REGISTRY_COLLISION")

    if not primary_probe["attached"]:
        raise DeliveryError("delivery workspace creation requires an attached primary HEAD", code="DETACHED_HEAD")

    if generation == 1:
        _assert_new_work_probe(requested_probe)
        _assert_no_collision(primary_probe, destination, branch)
        record = _new_record(
            primary_probe,
            work_id,
            request_sha256,
            destination,
            branch,
            work_kind=work_kind,
            bug_id=bug_id,
            knowledge_policy=knowledge_policy,
        )
        record_errors = validate_record(record)
        if record_errors:
            raise DeliveryError(
                f"initial delivery record is invalid ({len(record_errors)} issue(s))",
                code="INVALID_RECORD",
            )
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_dir.mkdir()
        except FileExistsError as exc:
            raise DeliveryError("another caller won the work_id reservation", code="REGISTRY_COLLISION") from exc
        try:
            (run_dir / "evidence").mkdir()
            _atomic_write_json(
                run_dir / "evidence" / "probe.json",
                _probe_evidence(primary_probe, destination, branch, generation),
            )
            _atomic_write_json(record_path, record)
        except OSError as exc:
            raise DeliveryError(
                f"registry reservation could not be persisted; no Git mutation was attempted: {exc}",
                code="REGISTRY_WRITE_FAILED",
            ) from exc
    else:
        if not record_path.is_file():
            raise DeliveryError("later generation requires an existing delivery record", code="MISSING_RECORD")

    with _exclusive_lock(run_dir / "record.lock"):
        if generation > 1:
            record = load_record(record_path)
            if record["status"] == "complete":
                raise DeliveryError("Complete delivery records cannot add a generation", code="COMPLETE_FROZEN")
            if record["repo_id"] != primary_probe["repo_id"] or record["request_sha256"] != request_sha256:
                raise DeliveryError("delivery record belongs to different inputs", code="REGISTRY_COLLISION")
            recorded_kind = record.get("work_kind", "standard")
            if work_kind is not None and recorded_kind != work_kind:
                raise DeliveryError("later generation work_kind differs from its record", code="REGISTRY_COLLISION")
            if bug_id is not None and record.get("bugs", {}).get("primary_bug_id") != bug_id:
                raise DeliveryError("later generation bug_id differs from its record", code="REGISTRY_COLLISION")
            if generation != record["current_generation"] + 1:
                raise DeliveryError("generation must be the next contiguous number", code="INVALID_GENERATION")
            if primary_probe["head_sha"] != record["generations"][-1]["base_sha"]:
                raise DeliveryError(
                    "primary HEAD differs from the approved delivery base; re-establish an approved base before generation",
                    code="GENERATION_BASE_DRIFT",
                )
            materialization = _approved_upstream_materialization(record)
            _assert_no_collision(primary_probe, destination, branch)
            reservation = run_dir / "generation-reservations" / str(generation)
            reservation.parent.mkdir(parents=True, exist_ok=True)
            try:
                reservation.mkdir()
            except FileExistsError as exc:
                raise DeliveryError("generation reservation already exists", code="REGISTRY_COLLISION") from exc
            record["current_generation"] = generation
            record["generations"].append(
                {
                    "generation": generation,
                    "canonical_worktree": str(destination),
                    "worktree_key": path_key(destination),
                    "branch": branch,
                    "base_sha": primary_probe["head_sha"],
                    "status": "reserved",
                    "created_at": utc_now(),
                }
            )
            _append_event(
                record,
                kind="generation_reserved",
                phase=record["phase"],
                status=record["status"],
                evidence_refs=[f"evidence/probe-r{generation}.json"],
            )
            record_errors = validate_record(record)
            if record_errors:
                raise DeliveryError(
                    f"generation reservation is invalid ({len(record_errors)} issue(s))",
                    code="INVALID_RECORD",
                )
            try:
                _atomic_write_json(
                    run_dir / "evidence" / f"probe-r{generation}.json",
                    _probe_evidence(primary_probe, destination, branch, generation),
                )
                _atomic_write_json(record_path, record)
            except OSError as exc:
                raise DeliveryError(
                    f"generation reservation could not be persisted; no Git mutation was attempted: {exc}",
                    code="REGISTRY_WRITE_FAILED",
                ) from exc

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            disabled_hooks = run_dir / "disabled-hooks"
            if not disabled_hooks.exists():
                disabled_hooks.mkdir()
            is_junction = getattr(disabled_hooks, "is_junction", lambda: False)
            if disabled_hooks.is_symlink() or is_junction() or not disabled_hooks.is_dir():
                raise DeliveryError("disabled hooks path is not a private directory", code="UNSAFE_GIT_CONFIGURATION")
            if any(disabled_hooks.iterdir()):
                raise DeliveryError("disabled hooks path is not empty", code="UNSAFE_GIT_CONFIGURATION")
            filter_drivers = _active_filter_drivers(primary_probe["primary_worktree"])
            safe_config = [
                "-c",
                f"core.hooksPath={disabled_hooks.as_posix()}",
                "-c",
                "core.sparseCheckout=false",
                "-c",
                "submodule.recurse=false",
                "-c",
                "gc.auto=0",
                "-c",
                "maintenance.auto=false",
                *_filter_disable_config(filter_drivers),
            ]
            command = [
                *safe_config,
                "worktree",
                "add",
                "--no-track",
                "-b",
                branch,
                str(destination),
                primary_probe["head_sha"],
            ]
            completed = _git(primary_probe["primary_worktree"], command, check=False)
            command_evidence = {
                "operation": "git-worktree-add",
                "argv_sha256": sha256_bytes(canonical_json(["git", *command])),
                "destination_key": path_key(destination),
                "branch": branch,
                "base_sha": primary_probe["head_sha"],
                "safety_controls": {
                    "empty_hooks_path": True,
                    "fsmonitor_disabled": True,
                    "lazy_fetch_disabled": True,
                    "replace_objects_disabled": True,
                    "submodule_recursion_disabled": True,
                    "filter_driver_count": len(filter_drivers),
                },
                "exit_code": completed.returncode,
                "stdout_sha256": sha256_bytes(completed.stdout),
                "stdout_bytes": len(completed.stdout),
                "stderr_sha256": sha256_bytes(completed.stderr),
                "stderr_bytes": len(completed.stderr),
            }
            command_ref = f"evidence/worktree-add-r{generation}.json"
            _atomic_write_json(run_dir / command_ref, command_evidence)
            if completed.returncode != 0:
                raise _git_failure_error(
                    completed,
                    fallback_code="WORKTREE_ADD_FAILED",
                    fallback_message="git worktree add failed; preserved Blocked evidence",
                )

            fresh_primary_probe = probe_repository(primary_probe["primary_worktree"])
            workspace = probe_repository(destination)
            generation_record = record["generations"][-1]
            listed = {
                canonical_path_text(str(item["worktree"]))
                for item in fresh_primary_probe["worktrees"]
                if "worktree" in item
            }
            checks = {
                "repo_id": workspace["repo_id"] == primary_probe["repo_id"],
                "non_primary": not workspace["is_primary"],
                "branch": workspace["branch"] == branch,
                "head": workspace["head_sha"] == primary_probe["head_sha"],
                "strict_clean": workspace["strict_clean"],
                "registered": canonical_path_text(destination) in listed,
            }
            verification_ref = f"evidence/worktree-verify-r{generation}.json"
            _atomic_write_json(run_dir / verification_ref, checks)
            if not all(checks.values()):
                raise DeliveryError("created worktree failed post-creation verification", code="WORKTREE_VERIFY_FAILED")
            event_refs = [command_ref, verification_ref]
            if generation > 1:
                materialization_plan_ref = f"evidence/upstream-plan-r{generation}.json"
                _atomic_write_json(
                    run_dir / materialization_plan_ref,
                    [{"path": item["path"], "sha256": item["sha256"]} for item in materialization],
                )
                copied = _materialize_approved_upstream(destination, materialization)
                materialization_result_ref = f"evidence/upstream-materialized-r{generation}.json"
                _atomic_write_json(run_dir / materialization_result_ref, copied)
                _approved_upstream_materialization(
                    record,
                    verify_current_sources=True,
                    source_generation=generation_record,
                )
                event_refs.extend([materialization_plan_ref, materialization_result_ref])
            generation_record["status"] = "ready"
            _append_event(
                record,
                kind="workspace_created" if generation == 1 else "generation_created",
                phase=record["phase"],
                status=record["status"],
                evidence_refs=event_refs,
            )
            record_errors = validate_record(record)
            if record_errors:
                raise DeliveryError(
                    f"created workspace record is invalid ({len(record_errors)} issue(s))",
                    code="INVALID_RECORD",
                )
            _atomic_write_json(record_path, record)
            return _result(record, record_path, outcome="created")
        except (OSError, DeliveryError) as exc:
            record["generations"][-1]["status"] = "blocked"
            failure_ref = f"evidence/workspace-failure-r{generation}.json"
            try:
                _atomic_write_json(
                    run_dir / failure_ref,
                    {"code": getattr(exc, "code", "OS_ERROR"), "message": str(exc), "at": utc_now()},
                )
                _append_event(
                    record,
                    kind="workspace_creation_failed",
                    phase=record["phase"],
                    status="blocked",
                    evidence_refs=[failure_ref],
                )
                record_errors = validate_record(record)
                if record_errors:
                    raise DeliveryError(
                        f"Blocked workspace record is invalid ({len(record_errors)} issue(s))",
                        code="INVALID_RECORD",
                    )
                _atomic_write_json(record_path, record)
            except OSError as evidence_exc:
                raise DeliveryError(
                    f"workspace failed and Blocked evidence could not be persisted: {evidence_exc}; original: {exc}",
                    code="EVIDENCE_WRITE_FAILED",
                ) from evidence_exc
            if isinstance(exc, DeliveryError):
                raise
            raise DeliveryError(f"workspace creation failed: {exc}", code="WORKSPACE_CREATE_FAILED") from exc


def locate_workspace(repo: str | Path, *, root: Path | None = None, work_id: str | None = None) -> dict[str, Any]:
    root = _validate_registry_root(root or default_registry_root())
    probe = probe_repository(repo)
    works_root = root / "repos" / probe["repo_id"] / "works"
    if work_id is not None:
        validate_work_id(work_id)
        candidates = [works_root / work_id]
    elif works_root.is_dir():
        candidates = sorted((path for path in works_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    else:
        candidates = []

    records: list[tuple[dict[str, Any], Path]] = []
    for candidate in candidates:
        path = _record_path(candidate)
        if not path.is_file():
            if work_id is not None:
                raise DeliveryError("work_id registry is missing run.json", code="INVALID_RECORD")
            continue
        record = load_record(path)
        if record["repo_id"] == probe["repo_id"]:
            records.append((record, path))

    if work_id is None:
        records = [(record, path) for record, path in records if record["status"] != "complete"]
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


def transition_record(
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
    bug_assessment_id: str | None = None,
    bug_assessment_path: str | None = None,
    bug_assessment_sha256: str | None = None,
    bug_assessment_markdown_path: str | None = None,
    bug_assessment_markdown_sha256: str | None = None,
    deferred_bug_id: str | None = None,
    deferred_bug_relation: str | None = None,
    deferred_bug_status: str | None = None,
    deferred_bug_evidence_refs: Sequence[str] = (),
    deferred_bug_sensitive: bool = False,
    deferred_bug_redacted_summary: str | None = None,
    deferred_bug_human_reviewer: str | None = None,
    deferred_bug_assessment_path: str | None = None,
    deferred_bug_assessment_sha256: str | None = None,
    deferred_bug_assessment_markdown_path: str | None = None,
    deferred_bug_assessment_markdown_sha256: str | None = None,
    handoff_path: str | None = None,
    candidate_revision: str | None = None,
    payload_sha256: str | None = None,
    plan_approval_refs: Sequence[str] = (),
    implementation_run_id: str | None = None,
    implementation_ledger_ref: str | None = None,
    implementation_status: str | None = None,
    bug_verification_path: str | None = None,
    bug_verification_sha256: str | None = None,
    bug_verification_result: str | None = None,
    enable_knowledge: bool = False,
    knowledge_candidate_ref: str | None = None,
    knowledge_candidate_payload_sha256: str | None = None,
    knowledge_snapshot_before: str | None = None,
    knowledge_snapshot_after: str | None = None,
    knowledge_product_snapshot_id: str | None = None,
    knowledge_outcome_path: str | None = None,
    knowledge_outcome_sha256: str | None = None,
    knowledge_promotion_id: str | None = None,
    knowledge_receipt_path: str | None = None,
    knowledge_receipt_sha256: str | None = None,
    knowledge_approval_evidence: str | None = None,
    known_secret_values: Sequence[str] = (),
) -> dict[str, Any]:
    root = _validate_registry_root(root or default_registry_root())
    validate_work_id(work_id)
    identity = probe_repository_identity(repo)
    run_dir = run_directory(root, identity.repo_id, work_id)
    if not _record_path(run_dir).is_file():
        raise DeliveryError("delivery record is missing", code="MISSING_RECORD")
    lock_path = run_dir / "record.lock"
    with _exclusive_lock(lock_path):
        lock_epoch = _lock_epoch(lock_path)
        probe_evidence = probe_repository_state(repo, lock_epoch=lock_epoch)
        _validate_repository_state_evidence(
            identity,
            probe_evidence,
            lock_path=lock_path,
            lock_epoch=lock_epoch,
        )
        return _transition_record_unlocked(
            repo,
            work_id,
            phase,
            status,
            event,
            evidence_refs,
            root=root,
            requirements_path=requirements_path,
            requirements_sha256=requirements_sha256,
            requirements_approval_refs=requirements_approval_refs,
            bug_assessment_id=bug_assessment_id,
            bug_assessment_path=bug_assessment_path,
            bug_assessment_sha256=bug_assessment_sha256,
            bug_assessment_markdown_path=bug_assessment_markdown_path,
            bug_assessment_markdown_sha256=bug_assessment_markdown_sha256,
            deferred_bug_id=deferred_bug_id,
            deferred_bug_relation=deferred_bug_relation,
            deferred_bug_status=deferred_bug_status,
            deferred_bug_evidence_refs=deferred_bug_evidence_refs,
            deferred_bug_sensitive=deferred_bug_sensitive,
            deferred_bug_redacted_summary=deferred_bug_redacted_summary,
            deferred_bug_human_reviewer=deferred_bug_human_reviewer,
            deferred_bug_assessment_path=deferred_bug_assessment_path,
            deferred_bug_assessment_sha256=deferred_bug_assessment_sha256,
            deferred_bug_assessment_markdown_path=deferred_bug_assessment_markdown_path,
            deferred_bug_assessment_markdown_sha256=deferred_bug_assessment_markdown_sha256,
            handoff_path=handoff_path,
            candidate_revision=candidate_revision,
            payload_sha256=payload_sha256,
            plan_approval_refs=plan_approval_refs,
            implementation_run_id=implementation_run_id,
            implementation_ledger_ref=implementation_ledger_ref,
            implementation_status=implementation_status,
            bug_verification_path=bug_verification_path,
            bug_verification_sha256=bug_verification_sha256,
            bug_verification_result=bug_verification_result,
            enable_knowledge=enable_knowledge,
            knowledge_candidate_ref=knowledge_candidate_ref,
            knowledge_candidate_payload_sha256=knowledge_candidate_payload_sha256,
            knowledge_snapshot_before=knowledge_snapshot_before,
            knowledge_snapshot_after=knowledge_snapshot_after,
            knowledge_product_snapshot_id=knowledge_product_snapshot_id,
            knowledge_outcome_path=knowledge_outcome_path,
            knowledge_outcome_sha256=knowledge_outcome_sha256,
            knowledge_promotion_id=knowledge_promotion_id,
            knowledge_receipt_path=knowledge_receipt_path,
            knowledge_receipt_sha256=knowledge_receipt_sha256,
            knowledge_approval_evidence=knowledge_approval_evidence,
            known_secret_values=tuple(known_secret_values),
            probe_evidence=probe_evidence,
            lock_epoch=lock_epoch,
        )


def probe_command(args: argparse.Namespace) -> dict[str, Any]:
    probe = probe_repository(args.repo)
    result = {
        key: probe[key]
        for key in (
            "repo_id",
            "canonical_worktree",
            "worktree_key",
            "primary_worktree",
            "is_primary",
            "branch",
            "attached",
            "head_sha",
            "strict_clean",
            "status_sha256",
        )
    }
    if args.topic is not None or args.request_sha256 is not None:
        if args.topic is None or args.request_sha256 is None:
            raise DeliveryError("suggested Work ID requires both --topic and --request-sha256", code="INCOMPLETE_ID_INPUT")
        result["suggested_work_id"] = generate_work_id(
            probe["repo_id"], probe["head_sha"], args.request_sha256, args.topic
        )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="Inspect a repository without mutation")
    probe.add_argument("--repo", required=True)
    probe.add_argument("--topic")
    probe.add_argument("--request-sha256")

    start = subparsers.add_parser("start", help="Create or idempotently locate a delivery worktree")
    start.add_argument("--repo", required=True)
    start.add_argument("--work-id", required=True)
    start.add_argument("--request-sha256", required=True)
    start.add_argument("--generation", type=int, default=1)
    start.add_argument("--work-kind", choices=["standard", "bug"])
    start.add_argument("--bug-id")
    start.add_argument("--registry-root")

    locate = subparsers.add_parser("locate", help="Locate an active delivery record")
    locate.add_argument("--repo", required=True)
    locate.add_argument("--work-id")
    locate.add_argument("--registry-root")

    transition = subparsers.add_parser("transition", help="Atomically append a delivery phase event")
    transition.add_argument("--repo", required=True)
    transition.add_argument("--work-id", required=True)
    transition.add_argument("--phase", choices=sorted(PHASE_TRANSITIONS), required=True)
    transition.add_argument("--status", choices=sorted(STATUS_TRANSITIONS), required=True)
    transition.add_argument("--event", required=True)
    transition.add_argument("--evidence-ref", action="append", required=True)
    transition.add_argument("--registry-root")
    transition.add_argument("--requirements-path")
    transition.add_argument("--requirements-sha256")
    transition.add_argument("--requirements-approval-ref", action="append", default=[])
    transition.add_argument("--bug-assessment-id")
    transition.add_argument("--bug-assessment-path")
    transition.add_argument("--bug-assessment-sha256")
    transition.add_argument("--bug-assessment-markdown-path")
    transition.add_argument("--bug-assessment-markdown-sha256")
    transition.add_argument("--deferred-bug-id")
    transition.add_argument("--deferred-bug-relation", choices=["current-scope", "affecting-current-work", "unrelated"])
    transition.add_argument("--deferred-bug-status", choices=["pending", "materialized"])
    transition.add_argument("--deferred-bug-evidence-ref", action="append", default=[])
    transition.add_argument("--deferred-bug-sensitive", action="store_true")
    transition.add_argument("--deferred-bug-redacted-summary")
    transition.add_argument("--deferred-bug-human-reviewer")
    transition.add_argument("--deferred-bug-assessment-path")
    transition.add_argument("--deferred-bug-assessment-sha256")
    transition.add_argument("--deferred-bug-assessment-markdown-path")
    transition.add_argument("--deferred-bug-assessment-markdown-sha256")
    transition.add_argument("--handoff-path")
    transition.add_argument("--candidate-revision")
    transition.add_argument("--payload-sha256")
    transition.add_argument("--plan-approval-ref", action="append", default=[])
    transition.add_argument("--implementation-run-id")
    transition.add_argument("--implementation-ledger-ref")
    transition.add_argument("--implementation-status")
    transition.add_argument("--bug-verification-path")
    transition.add_argument("--bug-verification-sha256")
    transition.add_argument("--bug-verification-result", choices=["verified", "partial", "failed"])
    transition.add_argument("--enable-knowledge", action="store_true")
    transition.add_argument("--knowledge-candidate-ref")
    transition.add_argument("--knowledge-candidate-payload-sha256")
    transition.add_argument("--knowledge-snapshot-before")
    transition.add_argument("--knowledge-snapshot-after")
    transition.add_argument("--knowledge-product-snapshot-id")
    transition.add_argument("--knowledge-outcome-path")
    transition.add_argument("--knowledge-outcome-sha256")
    transition.add_argument("--knowledge-promotion-id")
    transition.add_argument("--knowledge-receipt-path")
    transition.add_argument("--knowledge-receipt-sha256")
    transition.add_argument("--knowledge-approval-evidence")
    transition.add_argument("--known-secret-env", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "probe":
            result = probe_command(args)
        elif args.command == "start":
            result = start_workspace(
                args.repo,
                args.work_id,
                args.request_sha256,
                root=registry_root(args.registry_root),
                generation=args.generation,
                work_kind=args.work_kind,
                bug_id=args.bug_id,
            )
        elif args.command == "locate":
            result = locate_workspace(
                args.repo,
                root=registry_root(args.registry_root),
                work_id=args.work_id,
            )
        else:
            result = transition_record(
                args.repo,
                args.work_id,
                args.phase,
                args.status,
                args.event,
                args.evidence_ref,
                root=registry_root(args.registry_root),
                requirements_path=args.requirements_path,
                requirements_sha256=args.requirements_sha256,
                requirements_approval_refs=args.requirements_approval_ref,
                bug_assessment_id=args.bug_assessment_id,
                bug_assessment_path=args.bug_assessment_path,
                bug_assessment_sha256=args.bug_assessment_sha256,
                bug_assessment_markdown_path=args.bug_assessment_markdown_path,
                bug_assessment_markdown_sha256=args.bug_assessment_markdown_sha256,
                deferred_bug_id=args.deferred_bug_id,
                deferred_bug_relation=args.deferred_bug_relation,
                deferred_bug_status=args.deferred_bug_status,
                deferred_bug_evidence_refs=args.deferred_bug_evidence_ref,
                deferred_bug_sensitive=args.deferred_bug_sensitive,
                deferred_bug_redacted_summary=args.deferred_bug_redacted_summary,
                deferred_bug_human_reviewer=args.deferred_bug_human_reviewer,
                deferred_bug_assessment_path=args.deferred_bug_assessment_path,
                deferred_bug_assessment_sha256=args.deferred_bug_assessment_sha256,
                deferred_bug_assessment_markdown_path=args.deferred_bug_assessment_markdown_path,
                deferred_bug_assessment_markdown_sha256=args.deferred_bug_assessment_markdown_sha256,
                handoff_path=args.handoff_path,
                candidate_revision=args.candidate_revision,
                payload_sha256=args.payload_sha256,
                plan_approval_refs=args.plan_approval_ref,
                implementation_run_id=args.implementation_run_id,
                implementation_ledger_ref=args.implementation_ledger_ref,
                implementation_status=args.implementation_status,
                bug_verification_path=args.bug_verification_path,
                bug_verification_sha256=args.bug_verification_sha256,
                bug_verification_result=args.bug_verification_result,
                enable_knowledge=args.enable_knowledge,
                knowledge_candidate_ref=args.knowledge_candidate_ref,
                knowledge_candidate_payload_sha256=args.knowledge_candidate_payload_sha256,
                knowledge_snapshot_before=args.knowledge_snapshot_before,
                knowledge_snapshot_after=args.knowledge_snapshot_after,
                knowledge_product_snapshot_id=args.knowledge_product_snapshot_id,
                knowledge_outcome_path=args.knowledge_outcome_path,
                knowledge_outcome_sha256=args.knowledge_outcome_sha256,
                knowledge_promotion_id=args.knowledge_promotion_id,
                knowledge_receipt_path=args.knowledge_receipt_path,
                knowledge_receipt_sha256=args.knowledge_receipt_sha256,
                knowledge_approval_evidence=args.knowledge_approval_evidence,
                known_secret_values=_known_secret_values_from_env(args.known_secret_env),
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except DeliveryError as exc:
        payload: dict[str, Any] = {"error": exc.code, "message": str(exc)}
        if exc.details is not None:
            payload["details"] = exc.details
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            json.dumps(
                {"error": "OS_ERROR", "message": f"host filesystem operation failed: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
