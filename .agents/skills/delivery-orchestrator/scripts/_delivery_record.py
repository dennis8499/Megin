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
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from _delivery_git import (
    RepositoryIdentity,
    RepositoryStateEvidence,
    _active_filter_drivers,
    _filter_disable_config,
    _git,
    _git_failure_error,
    destination_and_branch,
    probe_repository,
)
from _delivery_runtime import (
    DeliveryError,
    BUG_ID_RE,
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
    _stable_materialize_file,
    _stable_read_file,
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
    validate_bug_id,
    validate_work_id,
    workspace_label,
)


_CONTRACT_VALIDATOR: Any | None = None
_EXECUTION_VALIDATOR: Any | None = None
_READY_PLAN_SCHEMA: dict[str, Any] | None = None
_DELIVERY_RUN_SCHEMA: dict[str, Any] | None = None
_EXECUTION_RECORDS_SCHEMA: dict[str, Any] | None = None
_BUG_CONTRACT_VALIDATOR: Any | None = None
KNOWLEDGE_CANDIDATE_RE = re.compile(
    r"^knowledge:candidates/(promotion-[a-z0-9]+(?:-[a-z0-9]+)*)/candidate\.json$"
)
PRELIMINARY_REVIEW_REPORT_RE = re.compile(
    r"^reviews/[a-z0-9][a-z0-9._-]{2,127}/report\.json$"
)


_KNOWLEDGE_DELIVERY_MODULE: Any | None = None


def _lock_epoch(path: Path) -> str:
    """Fingerprint the exact lock file without trusting a redirected path."""
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise DeliveryError("delivery record lock is not a regular file", code="LOCK_FAILED")
        payload = path.read_bytes()
        after = path.lstat()
    except DeliveryError:
        raise
    except OSError as exc:
        raise DeliveryError(
            f"delivery record lock cannot be inspected: {path}",
            code="LOCK_FAILED",
        ) from exc

    def signature(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_ctime_ns,
            value.st_mtime_ns,
        )

    before_signature = signature(before)
    if before_signature != signature(after):
        raise DeliveryError("delivery record lock changed during inspection", code="LOCK_FAILED")
    return sha256_bytes(
        canonical_json(
            {
                "parent": canonical_path_text(path.parent),
                "name": path.name,
                "stat": before_signature,
            }
        )
        + b"\0"
        + payload
    )


def _validate_repository_state_evidence(
    identity: RepositoryIdentity,
    evidence: RepositoryStateEvidence,
    *,
    lock_path: Path,
    lock_epoch: str,
) -> None:
    current = evidence.identity
    if (
        current.repo_id != identity.repo_id
        or current.worktree_key != identity.worktree_key
        or canonical_path_text(current.canonical_worktree)
        != canonical_path_text(identity.canonical_worktree)
    ):
        raise DeliveryError(
            "repository identity changed while acquiring the delivery lock",
            code="WORKSPACE_DRIFT",
        )
    if _lock_epoch(lock_path) != lock_epoch:
        raise DeliveryError(
            "delivery record lock changed before state evidence was consumed",
            code="LOCK_FAILED",
        )


def _knowledge_delivery_module() -> Any:
    global _KNOWLEDGE_DELIVERY_MODULE
    if _KNOWLEDGE_DELIVERY_MODULE is not None:
        return _KNOWLEDGE_DELIVERY_MODULE
    scripts = Path(__file__).resolve().parents[2] / "project-knowledge" / "scripts"
    path = scripts / "knowledge_delivery.py"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("delivery_project_knowledge", path)
    if spec is None or spec.loader is None:
        raise DeliveryError(
            "project-knowledge delivery verifier is unavailable",
            code="INVALID_KNOWLEDGE_REVIEW",
        )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, RuntimeError) as exc:
        raise DeliveryError(
            "project-knowledge delivery verifier cannot be loaded",
            code="INVALID_KNOWLEDGE_REVIEW",
        ) from exc
    _KNOWLEDGE_DELIVERY_MODULE = module
    return module


def _verified_knowledge_snapshot(
    record: dict[str, Any],
    *,
    candidate_ref: str,
    payload_sha256: str,
) -> dict[str, Any]:
    module = _knowledge_delivery_module()
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    repo_id = module.knowledge_governance.repository_id(worktree)
    try:
        return module.build_knowledge_snapshot(
            str(worktree),
            sealed={
                "schema": "knowledge-candidate-seal/v1",
                "repo_id": repo_id,
                "candidate_ref": candidate_ref,
                "payload_sha256": payload_sha256,
                "status": "Candidate",
            },
        )
    except module.KnowledgeError as exc:
        raise DeliveryError(
            "knowledge Candidate or canonical tree cannot reproduce the reviewed snapshot",
            code="KNOWLEDGE_SNAPSHOT_DRIFT",
            details={"knowledge_error": exc.code},
        ) from exc


def _new_knowledge_gate(enabled_at: str) -> dict[str, Any]:
    return {
        "policy": "required",
        "enabled_at": enabled_at,
        "candidate_ref": None,
        "candidate_payload_sha256": None,
        "knowledge_snapshot_id": None,
        "knowledge_post_snapshot_id": None,
        "product_snapshot_id": None,
        "outcome_path": None,
        "outcome_sha256": None,
        "current_promotion_id": None,
        "promotions": [],
        "review": None,
    }


class _DuplicateBugJSONKey(ValueError):
    pass


def _strict_bug_json_object(
    raw: bytes,
    *,
    label: str,
    code: str,
    known_secret_values: Sequence[str] = (),
) -> dict[str, Any]:
    """Scan stable raw bytes before parsing and reject last-key-wins ambiguity."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise DeliveryError(f"{label} is not valid UTF-8 JSON", code=code) from exc
    if any(secret and secret in text for secret in known_secret_values) or _contains_sensitive_material(text):
        raise DeliveryError(f"{label} contains sensitive material", code=code)

    def reject_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise _DuplicateBugJSONKey("duplicate JSON object key")
            value[key] = item
        return value

    try:
        value = json.loads(text, object_pairs_hook=reject_duplicates)
    except _DuplicateBugJSONKey as exc:
        raise DeliveryError(f"{label} contains a duplicate JSON object key", code=code) from exc
    except json.JSONDecodeError as exc:
        raise DeliveryError(f"{label} is not readable JSON", code=code) from exc
    if not isinstance(value, dict):
        raise DeliveryError(f"{label} is not a JSON object", code=code)
    return value


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


def _bug_contract_validator() -> Any:
    """Load the diagnosis-owned assessment validator once."""
    global _BUG_CONTRACT_VALIDATOR
    if _BUG_CONTRACT_VALIDATOR is not None:
        return _BUG_CONTRACT_VALIDATOR
    module_path = (
        Path(__file__).resolve().parents[2]
        / "bug-diagnosis"
        / "scripts"
        / "validate_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("delivery_bug_contract_validator", module_path)
    if spec is None or spec.loader is None:
        raise DeliveryError("BUG assessment validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as exc:
        raise DeliveryError("BUG assessment validator cannot be loaded", code="CONTRACT_VALIDATOR_UNAVAILABLE") from exc
    _BUG_CONTRACT_VALIDATOR = module
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


def _validate_historical_ready_contract(handoff: dict[str, Any]) -> None:
    """Validate stable shape without retroactively applying newer producer rules."""

    schema_errors = _schema_errors(handoff, _ready_plan_schema())
    if schema_errors:
        raise DeliveryError(
            f"historical Ready handoff violates ready-plan/v1 schema ({len(schema_errors)} issue(s))",
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


def _snapshot_file(worktree: Path, relative: str) -> bytes:
    normalized = _normalized_repo_path(relative)
    lexical = worktree / Path(*normalized.split("/"))
    if _has_reparse_component(lexical, worktree):
        raise DeliveryError("snapshot input is missing or redirected", code="INVALID_IMPLEMENTATION_REF")
    try:
        return _stable_read_file(worktree, lexical)
    except DeliveryError as exc:
        raise DeliveryError("snapshot input is missing or redirected", code="INVALID_IMPLEMENTATION_REF") from exc


def _is_reparse_path(path: Path) -> bool:
    """Inspect one lexical component without following its redirect target."""
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return os.name == "nt" and bool(attributes & 0x400)


def _has_reparse_component(path: Path, root: Path) -> bool:
    """Reject lexical redirects before any resolve, stat-following, or read."""
    root_lexical = Path(os.path.abspath(root))
    path_lexical = Path(os.path.abspath(path))
    if _is_reparse_path(root_lexical):
        return True
    try:
        relative = path_lexical.relative_to(root_lexical)
    except ValueError:
        return True
    current = root_lexical
    for part in relative.parts:
        current = current / part
        if _is_reparse_path(current):
            return True
    try:
        path_lexical.resolve(strict=False).relative_to(root_lexical.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return True
    return False


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
            "sha256": sha256_bytes(_snapshot_file(worktree, artifact["path"])),
        }
        for artifact in ready.get("artifacts", [])
    ]
    ready_hashes.sort(key=lambda item: item["ref"])

    source_hashes: list[dict[str, str]] = []
    for source in ready.get("sources", []):
        location = source["location"]
        if urlparse(location).scheme:
            actual = source["sha256"]
        elif source.get("revision") == generation["base_sha"]:
            relative = _normalized_repo_path(location)
            base_source = _git(
                worktree,
                ["cat-file", "blob", f"{generation['base_sha']}:{relative}"],
                check=False,
            )
            if base_source.returncode != 0:
                raise DeliveryError(
                    "Ready base-revision source is unavailable",
                    code="INVALID_IMPLEMENTATION_REF",
                )
            actual = sha256_bytes(base_source.stdout)
        else:
            actual = sha256_bytes(_snapshot_file(worktree, location))
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
            ".",
            ":(exclude)docs/knowledge/**",
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
        if relative.startswith("docs/knowledge/"):
            continue
        unignored_files.append(
            {
                "path": relative,
                "sha256": sha256_bytes(_snapshot_file(worktree, relative)),
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
    known_secret_values: tuple[str, ...] = (),
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
                known_secret_values=known_secret_values,
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError, DeliveryError):
        return ["Complete implementation Ledger validation could not complete"]
    if ledger_schema_errors or ledger_semantic_errors:
        details = [*ledger_schema_errors, *ledger_semantic_errors]
        return [
            "Complete implementation Ledger violates its contract: "
            + "; ".join(dict.fromkeys(details))
        ]

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
        worktree = Path(generation["canonical_worktree"])
        handoff_path = worktree / Path(*current_handoff_path.split("/"))
        try:
            candidate = json.loads(_stable_read_file(worktree, handoff_path).decode("utf-8"))
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
                    known_secret_values=known_secret_values,
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

    bug_verification_binding = (
        record.get("bugs", {}).get("verification")
        if record.get("work_kind", "standard") == "bug"
        else None
    )
    bug_verification_valid = record.get("work_kind", "standard") != "bug"
    verification_record: dict[str, Any] | None = None
    if isinstance(bug_verification_binding, dict) and ready is not None:
        try:
            verification_relative = bug_verification_binding["path"]
            verification_bytes = _verify_repo_file(
                record,
                verification_relative,
                bug_verification_binding["sha256"],
            )
            candidate_verification = _strict_bug_json_object(
                verification_bytes,
                label="BUG verification",
                code="INVALID_BUG_VERIFICATION",
                known_secret_values=known_secret_values,
            )
            verification_record = candidate_verification
            verification_errors = list(
                validator.validate_instance(verification_record, schema, "bugVerification")
            )
            verification_errors.extend(
                validator.validate_bug_verification_against_ready(
                    verification_record,
                    ready,
                    expected_work_id=record["work_id"],
                    expected_handoff_path=str(current_handoff_path),
                    known_secret_values=known_secret_values,
                    raw_json_bytes=verification_bytes,
                    evidence_root=run_dir,
                    terminal_evidence_refs=terminal_refs,
                )
            )
            if verification_record.get("result") != bug_verification_binding.get("result"):
                verification_errors.append("result binding differs")
            bug_verification_valid = not verification_errors
        except (OSError, UnicodeError, json.JSONDecodeError, DeliveryError, AttributeError, KeyError, TypeError, ValueError):
            bug_verification_valid = False
    if not bug_verification_valid:
        errors.append("Complete BUG verification is missing, drifted, or invalid")

    knowledge_gate = record.get("knowledge_gate")
    knowledge_review = (
        knowledge_gate.get("review")
        if isinstance(knowledge_gate, dict)
        else None
    )
    preliminary_agent_id: str | None = None
    if isinstance(knowledge_review, dict):
        try:
            outcome_raw = _verify_repo_file(
                record,
                str(knowledge_gate.get("outcome_path")),
                str(knowledge_gate.get("outcome_sha256")),
            )
            outcome = _strict_bug_json_object(
                outcome_raw,
                label="knowledge gate implementation outcome",
                code="INVALID_KNOWLEDGE_REVIEW",
                known_secret_values=known_secret_values,
            )
            preliminary_ref = _ledger_relative_ref(
                outcome.get("review", {}).get("report_ref")
            )
            preliminary_path = (
                _ledger_evidence_path(run_dir, preliminary_ref)
                if preliminary_ref is not None
                else None
            )
            if preliminary_path is None:
                raise DeliveryError(
                    "preliminary review report is not persisted",
                    code="INVALID_KNOWLEDGE_REVIEW",
                )
            preliminary_report = _strict_bug_json_object(
                _stable_read_file(run_dir, preliminary_path),
                label="preliminary implementation review",
                code="INVALID_KNOWLEDGE_REVIEW",
                known_secret_values=known_secret_values,
            )
            candidate_agent_id = preliminary_report.get("attestation", {}).get(
                "agent_id"
            )
            if not isinstance(candidate_agent_id, str) or not candidate_agent_id:
                raise DeliveryError(
                    "preliminary review agent identity is invalid",
                    code="INVALID_KNOWLEDGE_REVIEW",
                )
            preliminary_agent_id = candidate_agent_id
        except (
            AttributeError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
            DeliveryError,
        ):
            errors.append(
                "Complete knowledge review lacks a persisted preliminary Reviewer identity"
            )

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
            report_errors.extend(
                validator.validate_execution_record_semantics(
                    report,
                    known_secret_values=known_secret_values,
                )
            )
            if ready is not None:
                report_errors.extend(
                    validator.validate_review_against_ready(
                        report,
                        ready,
                        known_secret_values,
                    )
                )
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
            isinstance(bug_verification_binding, dict)
            and (
                report.get("bug_verification_ref") != bug_verification_binding.get("path")
                or report.get("bug_verification_result") != bug_verification_binding.get("result")
            )
        ):
            report_errors.append("review BUG verification verdict differs from delivery binding")
        if isinstance(knowledge_review, dict) and (
            report.get("knowledge_snapshot_before")
            != knowledge_review.get("knowledge_snapshot_before")
            or report.get("knowledge_snapshot_after")
            != knowledge_review.get("knowledge_snapshot_after")
            or report.get("knowledge_candidate_ref")
            != knowledge_review.get("candidate_ref")
            or report.get("knowledge_candidate_payload_sha256")
            != knowledge_review.get("payload_sha256")
            or accepted_snapshot_id != knowledge_gate.get("product_snapshot_id")
        ):
            report_errors.append("review knowledge bindings differ from delivery gate")
        if isinstance(knowledge_review, dict) and (
            preliminary_agent_id is None
            or report.get("attestation", {}).get("agent_id")
            == preliminary_agent_id
        ):
            report_errors.append(
                "preliminary and final review agent identities must differ"
            )
        if verification_record is not None and (
            verification_record.get("implementation_review_ref") != relative
            or verification_record.get("full_verification") != report.get("command_outcomes")
        ):
            report_errors.append("BUG verification full outcomes differ from the accepted review")
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
    if isinstance(bug_verification_binding, dict) and bug_verification_binding.get("path") not in delivery_refs:
        errors.append("Complete delivery event does not reference BUG verification")
    knowledge_gate = record.get("knowledge_gate")
    if (
        isinstance(knowledge_gate, dict)
        and isinstance(knowledge_gate.get("review"), dict)
        and knowledge_gate.get("outcome_path") not in delivery_refs
    ):
        errors.append("Complete delivery event does not reference the reviewed implementation outcome")
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

    work_kind = record.get("work_kind", "standard")
    bugs = record.get("bugs")
    if bugs is not None and "work_kind" not in record:
        errors.append("delivery with BUG overlay must declare work_kind explicitly")
    bug_assessments: list[dict[str, Any]] = []
    if work_kind == "standard":
        if bugs is not None and not isinstance(bugs, dict):
            errors.append("standard delivery BUG overlay is not an object")
        elif isinstance(bugs, dict):
            if bugs.get("primary_bug_id") is not None or bugs.get("assessments"):
                errors.append("standard delivery cannot contain a primary BUG assessment")
            if bugs.get("verification") is not None:
                errors.append("standard delivery cannot contain primary BUG verification")
    elif work_kind == "bug":
        if not isinstance(bugs, dict):
            errors.append("bug delivery lacks bugs record")
        else:
            primary_bug_id = bugs.get("primary_bug_id")
            if not isinstance(primary_bug_id, str) or not BUG_ID_RE.fullmatch(primary_bug_id):
                errors.append("bug delivery primary_bug_id is invalid")
            raw_assessments = bugs.get("assessments", [])
            bug_assessments = raw_assessments if isinstance(raw_assessments, list) else []
            seen_assessment_paths: set[str] = set()
            for index, assessment in enumerate(bug_assessments, 1):
                if not isinstance(assessment, dict):
                    errors.append(f"bug assessment binding {index} is not an object")
                    continue
                bug_id = assessment.get("bug_id")
                match = re.fullmatch(
                    rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.json",
                    str(assessment.get("path", "")),
                )
                markdown_match = re.fullmatch(
                    rf"docs/bugs/{re.escape(str(bug_id))}/assessment-([1-9][0-9]*)\.md",
                    str(assessment.get("markdown_path", "")),
                )
                if match is None or markdown_match is None or match.group(1) != markdown_match.group(1):
                    errors.append(f"bug assessment binding {index} paths are not canonical")
                if assessment.get("path") in seen_assessment_paths:
                    errors.append(f"bug assessment binding {index} reuses a create-only path")
                seen_assessment_paths.add(str(assessment.get("path")))
                for field in ("sha256", "markdown_sha256", "requirements_sha256"):
                    if not SHA256_RE.fullmatch(str(assessment.get(field, ""))):
                        errors.append(f"bug assessment binding {index} has invalid {field}")
                refs = assessment.get("approval_evidence_refs")
                if (
                    not isinstance(refs, list)
                    or not refs
                    or len(refs) != len(set(refs))
                    or any(not isinstance(ref, str) or not EVIDENCE_REF_RE.fullmatch(ref) for ref in refs)
                ):
                    errors.append(f"bug assessment binding {index} approval refs are invalid")
            if record.get("phase") in {"planning", "implementation", "knowledge", "complete"}:
                if not bug_assessments or bug_assessments[0].get("bug_id") != primary_bug_id:
                    errors.append("bug delivery lacks its primary approved assessment")
    else:
        errors.append(f"unknown work_kind {work_kind!r}")

    if isinstance(bugs, dict):
        deferred = bugs.get("deferred", [])
        if not isinstance(deferred, list):
            errors.append("BUG deferred history is not an array")
            deferred = []
        histories: dict[str, list[dict[str, Any]]] = {}
        seen_deferred_paths: set[str] = set()
        for index, item in enumerate(deferred, 1):
            if not isinstance(item, dict):
                errors.append(f"deferred BUG event {index} is not an object")
                continue
            bug_id = str(item.get("bug_id", ""))
            histories.setdefault(bug_id, []).append(item)
            refs = item.get("host_evidence_refs")
            if (
                not BUG_ID_RE.fullmatch(bug_id)
                or not isinstance(refs, list)
                or not refs
                or len(refs) != len(set(refs))
                or any(
                    not isinstance(ref, str)
                    or not EVIDENCE_REF_RE.fullmatch(ref)
                    or _contains_sensitive_material(ref)
                    for ref in refs
                )
            ):
                errors.append(f"deferred BUG event {index} has invalid redacted evidence")
            relation = item.get("relation")
            status_value = item.get("status")
            sensitive = item.get("sensitive")
            redacted_summary = item.get("redacted_summary")
            human_reviewer = item.get("human_reviewer")
            if sensitive is True:
                if (
                    not isinstance(redacted_summary, str)
                    or not redacted_summary
                    or not isinstance(human_reviewer, str)
                    or not human_reviewer
                    or _contains_sensitive_material(redacted_summary)
                ):
                    errors.append(f"deferred BUG event {index} lacks safe sensitive-risk ownership")
            elif sensitive is False:
                if redacted_summary is not None or human_reviewer is not None:
                    errors.append(f"deferred BUG event {index} has unexpected sensitive-risk fields")
            else:
                errors.append(f"deferred BUG event {index} sensitive flag is invalid")
            artifact_values = (
                item.get("assessment_path"),
                item.get("assessment_sha256"),
                item.get("assessment_markdown_path"),
                item.get("assessment_markdown_sha256"),
            )
            if status_value == "pending" and any(value is not None for value in artifact_values):
                errors.append(f"deferred BUG event {index} pending state cannot bind assessment bytes")
            if status_value == "materialized":
                if not all(value is not None for value in artifact_values):
                    errors.append(f"deferred BUG event {index} materialized state lacks assessment binding")
                path = str(item.get("assessment_path", ""))
                markdown_path = str(item.get("assessment_markdown_path", ""))
                if (
                    re.fullmatch(rf"docs/bugs/{re.escape(bug_id)}/assessment-[1-9][0-9]*\.json", path) is None
                    or re.fullmatch(rf"docs/bugs/{re.escape(bug_id)}/assessment-[1-9][0-9]*\.md", markdown_path) is None
                    or path in seen_deferred_paths
                ):
                    errors.append(f"deferred BUG event {index} assessment paths are invalid or reused")
                seen_deferred_paths.add(path)
            expected_inbox_ref = f"bug-inbox:{bug_id}" if relation == "unrelated" else None
            if item.get("inbox_ref") != expected_inbox_ref:
                errors.append(f"deferred BUG event {index} inbox binding differs from relation")
        for bug_id, history in histories.items():
            if [item.get("sequence") for item in history] != list(range(1, len(history) + 1)):
                errors.append(f"deferred BUG {bug_id} sequence is not contiguous")
            if history and history[0].get("status") != "pending":
                errors.append(f"deferred BUG {bug_id} must start pending")
            if len(history) > 2 or (len(history) == 2 and history[1].get("status") != "materialized"):
                errors.append(f"deferred BUG {bug_id} history is not pending→materialized")
            if history and any(
                item.get("relation") != history[0].get("relation")
                or item.get("host_evidence_refs") != history[0].get("host_evidence_refs")
                or item.get("inbox_ref") != history[0].get("inbox_ref")
                or item.get("sensitive") is not history[0].get("sensitive")
                or item.get("redacted_summary") != history[0].get("redacted_summary")
                or item.get("human_reviewer") != history[0].get("human_reviewer")
                for item in history[1:]
            ):
                errors.append(f"deferred BUG {bug_id} routing evidence changed across append-only history")
        if record.get("phase") == "complete" and any(history[-1].get("status") == "pending" for history in histories.values() if history):
            errors.append("complete delivery has deferred BUG evidence that was not materialized")
        verification = bugs.get("verification")
        if verification is not None:
            primary_bug_id = bugs.get("primary_bug_id")
            expected_path = (
                f"docs/bugs/{primary_bug_id}/verifications/{record.get('work_id')}.json"
                if isinstance(primary_bug_id, str)
                else None
            )
            if (
                not isinstance(verification, dict)
                or verification.get("bug_id") != primary_bug_id
                or verification.get("path") != expected_path
                or not SHA256_RE.fullmatch(str(verification.get("sha256", "")))
                or verification.get("result") not in {"verified", "partial", "failed"}
            ):
                errors.append("BUG verification binding is invalid")
        if record.get("phase") == "complete" and (
            not isinstance(verification, dict) or verification.get("result") == "failed"
        ) and work_kind == "bug":
            errors.append("complete bug delivery requires non-failed BUG verification")

    phase = record.get("phase")
    status = record.get("status")
    if phase not in PHASE_TRANSITIONS:
        errors.append(f"unknown phase {phase!r}")
    if status not in STATUS_TRANSITIONS:
        errors.append(f"unknown status {status!r}")
    if (phase == "complete") != (status == "complete"):
        errors.append("phase/status complete must be paired")

    knowledge_gate = record.get("knowledge_gate")
    if isinstance(knowledge_gate, dict):
        candidate_ref = knowledge_gate.get("candidate_ref")
        candidate_payload = knowledge_gate.get("candidate_payload_sha256")
        if (candidate_ref is None) != (candidate_payload is None):
            errors.append("knowledge gate Candidate ref and payload must be paired")
        promotions = knowledge_gate.get("promotions", [])
        promotion_ids = [
            item.get("promotion_id")
            for item in promotions
            if isinstance(item, dict)
        ]
        receipt_paths = [
            item.get("receipt_path")
            for item in promotions
            if isinstance(item, dict)
        ]
        if len(promotion_ids) != len(set(promotion_ids)):
            errors.append("knowledge promotion IDs are not unique")
        if len(receipt_paths) != len(set(receipt_paths)):
            errors.append("knowledge promotion receipt paths are not unique")
        current_promotion_id = knowledge_gate.get("current_promotion_id")
        if current_promotion_id is not None and current_promotion_id not in promotion_ids:
            errors.append("knowledge current promotion does not identify a recorded receipt")
        review = knowledge_gate.get("review")
        review_dependent = (
            knowledge_gate.get("knowledge_snapshot_id"),
            knowledge_gate.get("knowledge_post_snapshot_id"),
            knowledge_gate.get("product_snapshot_id"),
            knowledge_gate.get("outcome_path"),
            knowledge_gate.get("outcome_sha256"),
        )
        if review is None:
            if any(value is not None for value in review_dependent):
                errors.append("knowledge gate has review-dependent fields without a review")
        elif isinstance(review, dict):
            if (
                any(value is None for value in review_dependent)
                or review.get("knowledge_snapshot_before")
                != review.get("knowledge_snapshot_after")
                or review.get("knowledge_snapshot_before")
                != knowledge_gate.get("knowledge_snapshot_id")
                or review.get("candidate_ref") != candidate_ref
                or review.get("payload_sha256") != candidate_payload
            ):
                errors.append("knowledge review bindings differ from the delivery gate")
        if phase == "knowledge" and not isinstance(review, dict):
            errors.append("knowledge phase lacks fresh review bindings")
        if phase == "complete":
            current_promotion = next(
                (
                    item
                    for item in promotions
                    if isinstance(item, dict)
                    and item.get("promotion_id") == current_promotion_id
                ),
                None,
            )
            if (
                not isinstance(review, dict)
                or not isinstance(current_promotion, dict)
                or current_promotion.get("stage") not in {"implementation", "bug"}
                or current_promotion.get("candidate_ref") != candidate_ref
                or current_promotion.get("payload_sha256") != candidate_payload
            ):
                errors.append("complete knowledge gate lacks its reviewed Ready promotion")

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

    for index, assessment in enumerate(bug_assessments, 1):
        requirement = next(
            (
                item
                for item in requirement_revisions
                if isinstance(item, dict) and item.get("path") == assessment.get("requirements_path")
            ),
            None,
        )
        if (
            requirement is None
            or requirement.get("sha256") != assessment.get("requirements_sha256")
            or requirement.get("approval_evidence_refs") != assessment.get("approval_evidence_refs")
        ):
            errors.append(f"bug assessment binding {index} differs from its Requirements approval")

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
        verification_fields = (
            item.get("bug_verification_ref"),
            item.get("bug_verification_sha256"),
            item.get("bug_verification_result"),
        )
        if any(value is not None for value in verification_fields) and not all(value is not None for value in verification_fields):
            errors.append(f"implementation run {index} has incomplete BUG verification binding")
        if all(value is not None for value in verification_fields):
            if (
                not isinstance(item.get("bug_verification_ref"), str)
                or not SHA256_RE.fullmatch(str(item.get("bug_verification_sha256", "")))
                or item.get("bug_verification_result") not in {"verified", "partial", "failed"}
            ):
                errors.append(f"implementation run {index} has invalid BUG verification binding")
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
        elif work_kind == "bug" and (
            not isinstance(bugs, dict)
            or not isinstance(bugs.get("verification"), dict)
            or current_run.get("bug_verification_ref") != bugs["verification"].get("path")
            or current_run.get("bug_verification_sha256") != bugs["verification"].get("sha256")
            or current_run.get("bug_verification_result") != bugs["verification"].get("result")
        ):
            errors.append("complete implementation run differs from BUG verification binding")
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
    *,
    work_kind: str | None = None,
    bug_id: str | None = None,
    knowledge_policy: str = "required",
) -> dict[str, Any]:
    if work_kind not in {None, "standard", "bug"}:
        raise DeliveryError("work_kind must be standard or bug", code="INVALID_WORK_KIND")
    if work_kind == "bug":
        if bug_id is None:
            raise DeliveryError("bug work requires bug_id", code="INVALID_BUG_ID")
        validate_bug_id(bug_id)
    elif bug_id is not None:
        raise DeliveryError("bug_id is only valid for bug work", code="INVALID_BUG_ID")
    if knowledge_policy not in {"required", "legacy"}:
        raise DeliveryError(
            "knowledge_policy must be required or legacy",
            code="INVALID_KNOWLEDGE_POLICY",
        )
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
    if knowledge_policy == "required":
        record["knowledge_gate"] = _new_knowledge_gate(now)
    if work_kind == "bug":
        record["work_kind"] = "bug"
        record["bugs"] = {
            "primary_bug_id": bug_id,
            "assessments": [],
            "deferred": [],
            "verification": None,
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


def _workspace_probe_for_evidence(
    generation: dict[str, Any],
    probe: dict[str, Any],
    *,
    evidence: RepositoryStateEvidence | None,
    lock_epoch: str | None,
) -> dict[str, Any]:
    if evidence is not None and evidence.matches(
        probe,
        canonical_worktree=generation["canonical_worktree"],
        lock_epoch=lock_epoch,
    ):
        return probe
    return probe_repository(generation["canonical_worktree"])


def _validate_ready_generation(
    record: dict[str, Any],
    probe: dict[str, Any],
    *,
    evidence: RepositoryStateEvidence | None = None,
    lock_epoch: str | None = None,
) -> None:
    generation = record["generations"][-1]
    if generation["status"] != "ready":
        return
    workspace = _workspace_probe_for_evidence(
        generation,
        probe,
        evidence=evidence,
        lock_epoch=lock_epoch,
    )
    if workspace["repo_id"] != record["repo_id"]:
        raise DeliveryError("delivery worktree repo_id differs from its record", code="WORKSPACE_DRIFT")
    if workspace["is_primary"]:
        raise DeliveryError("delivery record points at the primary worktree", code="WORKSPACE_DRIFT")
    if workspace["branch"] != generation["branch"]:
        raise DeliveryError("delivery branch differs from its record", code="WORKSPACE_DRIFT")
    if (
        evidence is not None
        and evidence.matches(
            workspace,
            canonical_worktree=generation["canonical_worktree"],
            lock_epoch=lock_epoch,
        )
        and evidence.merge_base is not None
        and evidence.merge_base[0] == generation["base_sha"]
    ):
        is_descendant = evidence.merge_base[1]
    else:
        ancestry = _git(
            generation["canonical_worktree"],
            ["merge-base", "--is-ancestor", generation["base_sha"], "HEAD"],
            check=False,
        )
        is_descendant = ancestry.returncode == 0
    if not is_descendant:
        raise DeliveryError("delivery HEAD no longer descends from its recorded base", code="WORKSPACE_DRIFT")
    listed = {
        canonical_path_text(str(item["worktree"]))
        for item in workspace["worktrees"]
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


def _verify_repo_file(
    record: dict[str, Any],
    relative: str,
    expected_sha256: str,
    *,
    worktree: Path | None = None,
) -> bytes:
    validate_sha256(expected_sha256, "artifact sha256")
    _normalized_repo_path(relative)
    worktree = worktree or Path(record["generations"][-1]["canonical_worktree"])
    lexical = worktree / Path(*relative.split("/"))
    if _has_reparse_component(lexical, worktree):
        raise DeliveryError("artifact path uses a symlink or reparse point", code="INVALID_PATH")
    value = _stable_read_file(worktree, lexical)
    actual = sha256_bytes(value)
    if actual != expected_sha256:
        raise DeliveryError(f"artifact hash differs for {relative}", code="ARTIFACT_DRIFT")
    return value


def _validated_knowledge_outcome(
    record: dict[str, Any],
    *,
    path: str,
    expected_sha256: str,
    known_secret_values: Sequence[str],
) -> tuple[str, str]:
    relative = _normalized_repo_path(path)
    outcome_root = f"{record['artifact_root']}/implementation"
    path_match = re.fullmatch(
        re.escape(outcome_root) + r"/outcome(?:-([1-9][0-9]*))?\.json",
        relative,
    )
    path_revision = 1 if path_match is not None and path_match.group(1) is None else (
        int(path_match.group(1)) if path_match is not None else 0
    )
    if path_match is None or path_revision < 1 or path_match.group(1) == "1":
        raise DeliveryError(
            "knowledge gate outcome is outside the Work ID implementation root",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    raw = _verify_repo_file(record, relative, expected_sha256)
    outcome = _strict_bug_json_object(
        raw,
        label="implementation outcome",
        code="INVALID_KNOWLEDGE_OUTCOME",
        known_secret_values=known_secret_values,
    )
    validator = _execution_validator()
    schema = _execution_records_schema()
    try:
        outcome_errors = list(
            validator.validate_instance(outcome, schema, "implementationOutcome")
        )
        outcome_errors.extend(
            validator.validate_execution_record_semantics(
                outcome,
                known_secret_values=tuple(known_secret_values),
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DeliveryError(
            "knowledge gate outcome validation could not complete",
            code="INVALID_KNOWLEDGE_OUTCOME",
        ) from exc
    current_run_id = record.get("implementations", {}).get("current_run_id")
    review = outcome.get("review", {})
    revision = outcome.get("revision")
    suffix = "" if revision == 1 else f"-{revision}"
    if (
        outcome_errors
        or outcome.get("work_id") != record.get("work_id")
        or outcome.get("implementation_run_id") != current_run_id
        or revision != path_revision
        or relative != f"{outcome_root}/outcome{suffix}.json"
        or review.get("verdict") != "APPROVED"
    ):
        raise DeliveryError(
            "knowledge gate outcome is not a valid reviewed record for the current run",
            code="INVALID_KNOWLEDGE_OUTCOME",
    )
    markdown = outcome.get("markdown", {})
    expected_markdown = f"{outcome_root}/outcome{suffix}.md"
    try:
        markdown_raw = _verify_repo_file(
            record,
            str(markdown.get("path", "")),
            str(markdown.get("sha256", "")),
        )
    except DeliveryError as exc:
        raise DeliveryError(
            "knowledge gate outcome Markdown is missing or drifted",
            code="INVALID_KNOWLEDGE_OUTCOME",
        ) from exc
    if markdown.get("path") != expected_markdown or not markdown_raw:
        raise DeliveryError(
            "knowledge gate outcome Markdown binding is invalid",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    for prior_revision in range(1, revision):
        prior_suffix = "" if prior_revision == 1 else f"-{prior_revision}"
        for extension in ("json", "md"):
            prior_relative = f"{outcome_root}/outcome{prior_suffix}.{extension}"
            prior_path = worktree / Path(*prior_relative.split("/"))
            if _has_reparse_component(prior_path, worktree) or not prior_path.is_file():
                raise DeliveryError(
                    "knowledge gate outcome revision history is incomplete",
                    code="INVALID_KNOWLEDGE_OUTCOME",
                )
    for change in outcome.get("changes", []):
        try:
            _verify_repo_file(record, change["path"], change["sha256"])
        except (KeyError, TypeError, DeliveryError) as exc:
            raise DeliveryError(
                "knowledge gate outcome changed-file hash is missing or drifted",
                code="INVALID_KNOWLEDGE_OUTCOME",
            ) from exc

    report_ref = review.get("report_ref")
    report_sha256 = review.get("report_sha256")
    if (
        not isinstance(current_run_id, str)
        or not isinstance(report_ref, str)
        or PRELIMINARY_REVIEW_REPORT_RE.fullmatch(report_ref) is None
        or _ledger_relative_ref(report_ref) != report_ref
        or not isinstance(report_sha256, str)
        or SHA256_RE.fullmatch(report_sha256) is None
    ):
        raise DeliveryError(
            "knowledge gate preliminary review binding is invalid",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    run_dir = canonical_path(_implementation_root() / "runs" / current_run_id)
    report_path = _ledger_evidence_path(run_dir, report_ref)
    if report_path is None:
        raise DeliveryError(
            "knowledge gate preliminary review report is not persisted",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    try:
        report_raw = _stable_read_file(run_dir, report_path)
    except DeliveryError as exc:
        raise DeliveryError(
            "knowledge gate preliminary review report could not be read stably",
            code="INVALID_KNOWLEDGE_OUTCOME",
        ) from exc
    if sha256_bytes(report_raw) != report_sha256:
        raise DeliveryError(
            "knowledge gate preliminary review report hash drifted",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    report = _strict_bug_json_object(
        report_raw,
        label="preliminary implementation review",
        code="INVALID_KNOWLEDGE_OUTCOME",
        known_secret_values=known_secret_values,
    )
    handoff_relative = record.get("plans", {}).get("current_handoff_path")
    plan_entry = next(
        (
            item
            for item in record.get("plans", {}).get("revisions", [])
            if item.get("handoff_path") == handoff_relative
            and item.get("status") == "Ready"
        ),
        None,
    )
    try:
        if not isinstance(handoff_relative, str) or not isinstance(plan_entry, dict):
            raise DeliveryError("current Ready handoff is absent", code="INVALID_HANDOFF")
        normalized_handoff = _normalized_repo_path(handoff_relative)
        handoff_path = worktree / Path(*normalized_handoff.split("/"))
        if _has_reparse_component(handoff_path, worktree):
            raise DeliveryError("Ready handoff path is redirected", code="INVALID_PATH")
        ready = _strict_bug_json_object(
            _stable_read_file(worktree, handoff_path),
            label="current Ready handoff",
            code="INVALID_HANDOFF",
            known_secret_values=known_secret_values,
        )
        _validate_ready_contract(ready)
        approval = ready.get("approval", {})
        candidate = ready.get("candidate", {})
        if (
            approval.get("status") != "Ready"
            or approval.get("evidence") not in plan_entry.get("approval_evidence_refs", [])
            or candidate.get("revision") != plan_entry.get("candidate_revision")
            or candidate.get("payload_sha256") != plan_entry.get("payload_sha256")
            or _ready_payload_sha256(ready) != plan_entry.get("payload_sha256")
        ):
            raise DeliveryError(
                "Ready handoff differs from the delivery plan binding",
                code="INVALID_HANDOFF",
            )
    except (AttributeError, KeyError, TypeError, ValueError, DeliveryError) as exc:
        raise DeliveryError(
            "knowledge gate cannot resolve the current Ready review contract",
            code="INVALID_KNOWLEDGE_OUTCOME",
        ) from exc
    report_errors = list(validator.validate_instance(report, schema, "reviewReport"))
    report_errors.extend(
        validator.validate_execution_record_semantics(
            report,
            known_secret_values=tuple(known_secret_values),
        )
    )
    report_errors.extend(
        validator.validate_review_against_ready(
            report,
            ready,
            tuple(known_secret_values),
        )
    )
    evidence_refs = review.get("evidence_refs", [])
    if (
        report.get("logical_ref") not in evidence_refs
        or len(evidence_refs) != 1
        or report.get("verdict") != review.get("verdict")
        or any(
            report.get(field) is not None
            for field in (
                "knowledge_snapshot_before",
                "knowledge_snapshot_after",
                "knowledge_candidate_ref",
                "knowledge_candidate_payload_sha256",
            )
        )
    ):
        report_errors.append("preliminary report differs from the outcome or is not preliminary")
    raw_refs = report.get("raw_output_refs", [])
    raw_ref_set = set(raw_refs) if isinstance(raw_refs, list) else set()
    if len(raw_ref_set) != len(raw_refs):
        report_errors.append("preliminary review raw output refs are duplicated")
    for raw_ref in raw_ref_set:
        normalized = _ledger_relative_ref(raw_ref) if isinstance(raw_ref, str) else None
        evidence_path = (
            _ledger_evidence_path(run_dir, normalized)
            if normalized is not None and normalized == raw_ref
            else None
        )
        if evidence_path is None:
            report_errors.append(f"preliminary review raw output is missing: {raw_ref}")
            continue
        try:
            _stable_read_file(run_dir, evidence_path)
        except DeliveryError:
            report_errors.append(f"preliminary review raw output drifted: {raw_ref}")
    report_commands = {
        item.get("command_id"): item
        for item in report.get("command_outcomes", [])
        if isinstance(item, dict)
    }
    for command in outcome.get("verification", []):
        reviewed = report_commands.get(command.get("command_id"))
        output_ref = reviewed.get("output_ref") if isinstance(reviewed, dict) else None
        if (
            not isinstance(reviewed, dict)
            or reviewed.get("outcome") != command.get("outcome")
            or not isinstance(output_ref, str)
            or output_ref not in command.get("evidence_refs", [])
            or output_ref not in raw_ref_set
        ):
            report_errors.append(
                f"outcome verification differs from preliminary report: {command.get('command_id')}"
            )
    if report_errors:
        raise DeliveryError(
            f"knowledge gate preliminary review violates its binding ({len(report_errors)} issue(s))",
            code="INVALID_KNOWLEDGE_OUTCOME",
        )
    return relative, expected_sha256


def _validated_knowledge_promotion_binding(
    record: dict[str, Any],
    *,
    promotion_id: str,
    receipt_path: str,
    receipt_sha256: str,
    candidate_ref: str,
    payload_sha256: str,
    approval_evidence: str,
    expected_stages: set[str],
    known_secret_values: Sequence[str],
) -> dict[str, Any]:
    candidate_match = KNOWLEDGE_CANDIDATE_RE.fullmatch(candidate_ref)
    validate_sha256(payload_sha256, "knowledge candidate payload_sha256")
    if candidate_match is None or candidate_match.group(1) != promotion_id:
        raise DeliveryError(
            "knowledge Candidate ref and promotion ID differ",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )
    approval = _logical_refs([approval_evidence], "knowledge approval")[0]
    relative = _normalized_repo_path(receipt_path)
    expected_path = f"docs/knowledge/meta/promotions/{promotion_id}.json"
    if relative != expected_path:
        raise DeliveryError(
            "knowledge promotion receipt path is not canonical",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )
    raw = _verify_repo_file(record, relative, receipt_sha256)
    receipt = _strict_bug_json_object(
        raw,
        label="knowledge promotion receipt",
        code="INVALID_KNOWLEDGE_PROMOTION",
        known_secret_values=known_secret_values,
    )
    receipt_approval = receipt.get("approval", {})
    lint = receipt.get("lint", {})
    raw_formal_paths = receipt.get("formal_paths")
    try:
        if not isinstance(raw_formal_paths, list) or any(
            not isinstance(value, str) for value in raw_formal_paths
        ):
            raise ValueError("formal_paths is not a string array")
        formal_paths = [_normalized_repo_path(value) for value in raw_formal_paths]
    except (DeliveryError, ValueError) as exc:
        raise DeliveryError(
            "knowledge promotion receipt has an invalid formal artifact manifest",
            code="INVALID_KNOWLEDGE_PROMOTION",
        ) from exc
    canonical_formal_paths = sorted(
        set(formal_paths),
        key=lambda value: value.encode("utf-8"),
    )
    if formal_paths != canonical_formal_paths:
        raise DeliveryError(
            "knowledge promotion receipt formal artifact manifest is not canonical",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )
    if (
        receipt.get("schema") != "knowledge-promotion/v1"
        or receipt.get("promotion_id") != promotion_id
        or receipt.get("stage") not in expected_stages
        or receipt.get("work_id") != record.get("work_id")
        or receipt.get("candidate_ref") != candidate_ref
        or receipt.get("payload_sha256") != payload_sha256
        or receipt_approval.get("evidence") != approval
        or not isinstance(receipt_approval.get("actor"), str)
        or not receipt_approval.get("actor")
        or lint.get("required_outcome") != "passed"
        or receipt.get("status") != "Ready"
    ):
        raise DeliveryError(
            "knowledge promotion receipt differs from the approved reviewed Candidate",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )
    knowledge_module = _knowledge_delivery_module()
    worktree = record["generations"][-1]["canonical_worktree"]
    if receipt["stage"] in {"requirements", "planning"}:
        try:
            stage_gate = knowledge_module.knowledge_workflow.validate_stage_promotion(
                worktree,
                work_id=str(record.get("work_id")),
                stage=receipt["stage"],
                receipt_path=relative,
                receipt_sha256=receipt_sha256,
                approval_evidence=approval,
            )
        except knowledge_module.KnowledgeError as exc:
            raise DeliveryError(
                "knowledge promotion receipt does not bind the owner-validated formal artifacts",
                code="INVALID_KNOWLEDGE_PROMOTION",
            ) from exc
        if stage_gate.get("formal_paths") != formal_paths:
            raise DeliveryError(
                "knowledge promotion receipt formal artifacts differ from the owner gate",
                code="INVALID_KNOWLEDGE_PROMOTION",
            )
    full_lint = knowledge_module.knowledge_governance.lint_repository(worktree)
    if full_lint.get("outcome") != "passed":
        raise DeliveryError(
            "knowledge repository does not pass full lint at completion",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )
    return {
        "promotion_id": promotion_id,
        "stage": receipt["stage"],
        "candidate_ref": candidate_ref,
        "payload_sha256": payload_sha256,
        "receipt_path": relative,
        "receipt_sha256": receipt_sha256,
        "approval_evidence": approval,
        "formal_paths": formal_paths,
        "status": "Ready",
    }


def _validated_bug_assessment_binding(
    record: dict[str, Any],
    *,
    bug_id: str,
    assessment_path: str,
    assessment_sha256: str,
    markdown_path: str,
    markdown_sha256: str,
    requirements_path: str,
    requirements_sha256: str,
    approval_refs: Sequence[str],
    known_secret_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    try:
        validate_bug_id(bug_id)
        assessment_path = _normalized_repo_path(assessment_path)
        markdown_path = _normalized_repo_path(markdown_path)
        validate_sha256(assessment_sha256, "BUG assessment sha256")
        validate_sha256(markdown_sha256, "BUG assessment Markdown sha256")
        sidecar_bytes = _verify_repo_file(record, assessment_path, assessment_sha256)
        _verify_repo_file(record, markdown_path, markdown_sha256)
    except DeliveryError as exc:
        raise DeliveryError(str(exc), code="INVALID_BUG_ASSESSMENT") from exc

    primary_bug_id = record.get("bugs", {}).get("primary_bug_id")
    if bug_id != primary_bug_id:
        raise DeliveryError("BUG assessment ID differs from delivery primary_bug_id", code="INVALID_BUG_ASSESSMENT")
    if any(item.get("path") == assessment_path for item in record.get("bugs", {}).get("assessments", [])):
        raise DeliveryError("BUG assessment path is create-only and already bound", code="INVALID_BUG_ASSESSMENT")

    worktree = Path(record["generations"][-1]["canonical_worktree"])
    try:
        data = _strict_bug_json_object(
            sidecar_bytes,
            label="BUG assessment sidecar",
            code="INVALID_BUG_ASSESSMENT",
            known_secret_values=known_secret_values,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DeliveryError) as exc:
        raise DeliveryError("BUG assessment sidecar is not readable JSON", code="INVALID_BUG_ASSESSMENT") from exc
    if not isinstance(data, dict):
        raise DeliveryError("BUG assessment sidecar is not an object", code="INVALID_BUG_ASSESSMENT")
    try:
        assessment_errors = _bug_contract_validator().validate_assessment(
            data,
            repository_root=worktree,
            sidecar_path=worktree / Path(*assessment_path.split("/")),
            sidecar_bytes=sidecar_bytes,
            known_secret_values=known_secret_values,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DeliveryError("BUG assessment validation could not complete", code="INVALID_BUG_ASSESSMENT") from exc
    if assessment_errors:
        raise DeliveryError(
            f"BUG assessment violates bug-assessment/v1 ({len(assessment_errors)} issue(s))",
            code="INVALID_BUG_ASSESSMENT",
        )
    if (
        data.get("bug_id") != bug_id
        or data.get("markdown", {}).get("path") != markdown_path
        or data.get("markdown", {}).get("sha256") != markdown_sha256
        or data.get("verdict") not in {"confirmed", "likely"}
        or data.get("disposition") != "delivery"
    ):
        raise DeliveryError("BUG assessment cannot enter bug delivery", code="INVALID_BUG_ASSESSMENT")
    return {
        "bug_id": bug_id,
        "path": assessment_path,
        "sha256": assessment_sha256,
        "markdown_path": markdown_path,
        "markdown_sha256": markdown_sha256,
        "requirements_path": requirements_path,
        "requirements_sha256": requirements_sha256,
        "approval_evidence_refs": list(approval_refs),
    }


def _validated_deferred_assessment(
    record: dict[str, Any],
    *,
    bug_id: str,
    relation: str,
    assessment_path: str,
    assessment_sha256: str,
    markdown_path: str,
    markdown_sha256: str,
    evidence_refs: Sequence[str],
    sensitive: bool,
    redacted_summary: str | None,
    human_reviewer: str | None,
    known_secret_values: tuple[str, ...] = (),
) -> tuple[str, str, str, str]:
    try:
        validate_bug_id(bug_id)
        assessment_path = _normalized_repo_path(assessment_path)
        markdown_path = _normalized_repo_path(markdown_path)
        validate_sha256(assessment_sha256, "deferred BUG assessment sha256")
        validate_sha256(markdown_sha256, "deferred BUG assessment Markdown sha256")
        sidecar_bytes = _verify_repo_file(record, assessment_path, assessment_sha256)
        _verify_repo_file(record, markdown_path, markdown_sha256)
    except DeliveryError as exc:
        raise DeliveryError(str(exc), code="INVALID_DEFERRED_BUG") from exc

    prior_paths = {
        item.get("assessment_path")
        for item in record.get("bugs", {}).get("deferred", [])
        if isinstance(item, dict) and item.get("assessment_path") is not None
    }
    if assessment_path in prior_paths:
        raise DeliveryError("deferred BUG assessment path is create-only and already bound", code="INVALID_DEFERRED_BUG")
    worktree = Path(record["generations"][-1]["canonical_worktree"])
    try:
        data = _strict_bug_json_object(
            sidecar_bytes,
            label="deferred BUG assessment",
            code="INVALID_DEFERRED_BUG",
            known_secret_values=known_secret_values,
        )
        assessment_errors = _bug_contract_validator().validate_assessment(
            data,
            repository_root=worktree,
            sidecar_path=worktree / Path(*assessment_path.split("/")),
            sidecar_bytes=sidecar_bytes,
            known_secret_values=known_secret_values,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError, DeliveryError) as exc:
        raise DeliveryError("deferred BUG assessment validation could not complete", code="INVALID_DEFERRED_BUG") from exc
    expected_disposition = {
        "current-scope": "current-run",
        "affecting-current-work": "upstream-reapproval",
        "unrelated": "deferred-inbox",
    }[relation]
    source = data.get("source", {})
    risk = data.get("risk", {})
    if (
        assessment_errors
        or data.get("bug_id") != bug_id
        or data.get("markdown", {}).get("path") != markdown_path
        or data.get("markdown", {}).get("sha256") != markdown_sha256
        or source.get("relation") != relation
        or source.get("work_id") != record.get("work_id")
        or data.get("disposition") != expected_disposition
        or risk.get("security_privacy_or_data_risk") is not sensitive
        or risk.get("redacted_summary") != redacted_summary
        or risk.get("human_reviewer") != human_reviewer
        or (sensitive and risk.get("secure_evidence_refs") != list(evidence_refs))
    ):
        raise DeliveryError("deferred BUG assessment differs from its routing contract", code="INVALID_DEFERRED_BUG")
    return assessment_path, assessment_sha256, markdown_path, markdown_sha256


def _create_global_bug_inbox(
    root: Path,
    record: dict[str, Any],
    *,
    bug_id: str,
    evidence_refs: Sequence[str],
    sensitive: bool,
    redacted_summary: str | None,
    human_reviewer: str | None,
) -> tuple[str, Path, dict[str, Any], bool]:
    inbox_ref = f"bug-inbox:{bug_id}"
    inbox_path = root / "repos" / record["repo_id"] / "bug-inbox" / f"{bug_id}.json"
    payload = {
        "schema": "bug-inbox/v1",
        "bug_id": bug_id,
        "source_work_id": record["work_id"],
        "relation": "unrelated",
        "status": "pending",
        "redacted_evidence_refs": list(evidence_refs),
        "risk": {
            "sensitive": sensitive,
            "redacted_summary": redacted_summary,
            "human_reviewer": human_reviewer,
        },
        "created_at": utc_now(),
    }

    def recover_existing(raw: bytes, cause: BaseException | None = None) -> tuple[str, Path, dict[str, Any], bool]:
        try:
            existing = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as read_exc:
            raise DeliveryError(
                "global BUG inbox entry already exists; allocate a collision suffix",
                code="BUG_INBOX_EXISTS",
            ) from read_exc
        expected_identity = {key: value for key, value in payload.items() if key != "created_at"}
        existing_identity = (
            {key: value for key, value in existing.items() if key != "created_at"}
            if isinstance(existing, dict)
            else None
        )
        if (
            existing_identity != expected_identity
            or not isinstance(existing, dict)
            or not _is_utc_datetime(existing.get("created_at"))
        ):
            raise DeliveryError(
                "global BUG inbox entry already exists; allocate a collision suffix",
                code="BUG_INBOX_EXISTS",
            ) from cause
        return inbox_ref, inbox_path, existing, False

    try:
        return recover_existing(_stable_read_file(root, inbox_path))
    except DeliveryError as exc:
        if exc.code != "MISSING_ARTIFACT":
            raise

    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    relative = inbox_path.relative_to(root).as_posix()
    try:
        created = _stable_materialize_file(root, relative, encoded, sha256_bytes(encoded))
    except DeliveryError as exc:
        if exc.code != "ARTIFACT_COLLISION":
            raise
        return recover_existing(_stable_read_file(root, inbox_path), exc)
    if not created:
        return recover_existing(_stable_read_file(root, inbox_path))
    return inbox_ref, inbox_path, payload, True


def _rollback_global_bug_inbox(
    root: Path,
    inbox_path: Path,
    payload: dict[str, Any],
) -> None:
    """Remove only the exact inbox bytes created by a failed run transition."""
    try:
        current = json.loads(_stable_read_file(root, inbox_path).decode("utf-8"))
    except (DeliveryError, UnicodeError, json.JSONDecodeError):
        return
    if current != payload or _has_reparse_component(inbox_path, root):
        return
    try:
        inbox_path.unlink()
    except FileNotFoundError:
        pass


def _validated_bug_verification_binding(
    record: dict[str, Any],
    *,
    implementation_run_id: str,
    path: str,
    expected_sha256: str,
    result: str,
    known_secret_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    bugs = record.get("bugs")
    bug_id = bugs.get("primary_bug_id") if isinstance(bugs, dict) else None
    if not isinstance(bug_id, str):
        raise DeliveryError("only a primary BUG delivery can bind BUG verification", code="INVALID_BUG_VERIFICATION")
    expected_path = f"docs/bugs/{bug_id}/verifications/{record['work_id']}.json"
    try:
        normalized = _normalized_repo_path(path)
        validate_sha256(expected_sha256, "BUG verification sha256")
        verification_bytes = _verify_repo_file(record, normalized, expected_sha256)
    except DeliveryError as exc:
        raise DeliveryError(str(exc), code="INVALID_BUG_VERIFICATION") from exc
    if normalized != expected_path:
        raise DeliveryError("BUG verification path is not canonical for this Work ID", code="INVALID_BUG_VERIFICATION")
    if result not in {"verified", "partial", "failed"}:
        raise DeliveryError("BUG verification result is invalid", code="INVALID_BUG_VERIFICATION")
    if bugs.get("verification") is not None:
        raise DeliveryError("BUG verification path is create-only and already bound", code="INVALID_BUG_VERIFICATION")

    worktree = Path(record["generations"][-1]["canonical_worktree"])
    handoff_relative = record.get("plans", {}).get("current_handoff_path")
    if not isinstance(handoff_relative, str):
        raise DeliveryError("BUG verification has no current Ready handoff", code="INVALID_BUG_VERIFICATION")
    try:
        verification = _strict_bug_json_object(
            verification_bytes,
            label="BUG verification",
            code="INVALID_BUG_VERIFICATION",
            known_secret_values=known_secret_values,
        )
        handoff = json.loads(
            _stable_read_file(
                worktree,
                worktree / Path(*handoff_relative.split("/")),
            ).decode("utf-8")
        )
        evidence_root = canonical_path(_implementation_root() / "runs" / implementation_run_id)
        ledger_path = _ledger_evidence_path(evidence_root, "run.json")
        if ledger_path is None:
            raise TypeError("implementation Ledger is absent")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        attempt = next(
            (
                item
                for item in ledger.get("attempts", [])
                if item.get("attempt_id") == ledger.get("current_attempt_id")
            ),
            None,
        )
        history = attempt.get("state_history", []) if isinstance(attempt, dict) else []
        terminal_evidence_refs = history[-1].get("evidence_refs", []) if history else []
        validator = _execution_validator()
        schema_errors = validator.validate_instance(
            verification,
            _execution_records_schema(),
            "bugVerification",
        )
        semantic_errors = validator.validate_bug_verification_against_ready(
            verification,
            handoff,
            expected_work_id=record["work_id"],
            expected_handoff_path=handoff_relative,
            known_secret_values=known_secret_values,
            raw_json_bytes=verification_bytes,
            evidence_root=evidence_root,
            terminal_evidence_refs=terminal_evidence_refs,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        DeliveryError,
    ) as exc:
        raise DeliveryError("BUG verification validation could not complete", code="INVALID_BUG_VERIFICATION") from exc
    if schema_errors or semantic_errors:
        raise DeliveryError(
            f"BUG verification violates bug-verification/v1 ({len(schema_errors) + len(semantic_errors)} issue(s))",
            code="INVALID_BUG_VERIFICATION",
        )
    if verification.get("bug_id") != bug_id or verification.get("result") != result:
        raise DeliveryError("BUG verification binding differs from persisted record", code="INVALID_BUG_VERIFICATION")
    return {
        "bug_id": bug_id,
        "path": normalized,
        "sha256": expected_sha256,
        "result": result,
    }


def _verify_ready_local_sources(
    record: dict[str, Any],
    handoff: dict[str, Any],
    materialized_paths: set[str],
    *,
    verify_current_sources: bool,
    source_generation: dict[str, Any] | None = None,
) -> None:
    generation = source_generation or record["generations"][-1]
    worktree = Path(generation["canonical_worktree"])
    base_sha = generation["base_sha"]
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
            if sha256_bytes(base_bytes.stdout) != expected:
                raise DeliveryError(
                    "local Ready source bytes differ from the recorded Git base",
                    code="SOURCE_NOT_MATERIALIZABLE",
                )
            continue
        if not verify_current_sources:
            continue
        try:
            source_bytes = _stable_read_file(
                worktree,
                worktree / Path(*relative.split("/")),
            )
        except DeliveryError as exc:
            raise DeliveryError("local Ready source is missing or escapes its worktree", code="SOURCE_DRIFT") from exc
        if sha256_bytes(source_bytes) != expected:
            raise DeliveryError("local Ready source hash differs from its manifest", code="SOURCE_DRIFT")


def _approved_upstream_materialization(
    record: dict[str, Any],
    *,
    verify_current_sources: bool = False,
    source_generation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read and verify only the approved upstream bytes for a later generation."""
    source_generation = source_generation or next(
        (
            generation
            for generation in reversed(record["generations"])
            if generation.get("status") == "ready"
        ),
        None,
    )
    if source_generation is None:
        raise DeliveryError(
            "delivery has no Ready generation to materialize",
            code="WORKSPACE_NOT_READY",
        )
    source_worktree = Path(source_generation["canonical_worktree"])
    materialization: dict[str, dict[str, Any]] = {}

    def include(relative: str, expected_sha256: str) -> None:
        value = _verify_repo_file(
            record,
            relative,
            expected_sha256,
            worktree=source_worktree,
        )
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

    if record.get("work_kind", "standard") == "bug":
        assessments = record.get("bugs", {}).get("assessments", [])
        if record.get("phase") in {"planning", "implementation", "complete"} and not assessments:
            raise DeliveryError("bug delivery lacks approved assessment materialization", code="INVALID_RECORD")
        for assessment in assessments:
            include(assessment["path"], assessment["sha256"])
            include(assessment["markdown_path"], assessment["markdown_sha256"])
    for item in record.get("bugs", {}).get("deferred", []):
        if isinstance(item, dict) and item.get("status") == "materialized":
            include(item["assessment_path"], item["assessment_sha256"])
            include(item["assessment_markdown_path"], item["assessment_markdown_sha256"])

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

    try:
        handoff_bytes = _stable_read_file(
            source_worktree,
            source_worktree / Path(*handoff_path.split("/")),
        )
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
        or baseline.get("head_sha") != source_generation["base_sha"]
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

    referenced_sources = {
        (_normalized_repo_path(source["location"]), source["revision"]): source["sha256"]
        for source in sources
        if not urlparse(source["location"]).scheme
    }
    for historical_entry in record["plans"]["revisions"]:
        historical_handoff_path = historical_entry["handoff_path"]
        if historical_handoff_path == handoff_path:
            continue
        historical_key_prefix = (
            historical_handoff_path,
            historical_entry["candidate_revision"],
        )
        referenced_historical_paths = {
            relative: expected
            for (relative, revision), expected in referenced_sources.items()
            if revision == historical_key_prefix[1]
        }
        if not referenced_historical_paths:
            continue
        try:
            historical_bytes = _stable_read_file(
                source_worktree,
                source_worktree / Path(*historical_handoff_path.split("/")),
            )
            historical = json.loads(historical_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DeliveryError(
                f"cannot read historical Ready handoff: {exc}",
                code="INVALID_HANDOFF",
            ) from exc
        if not isinstance(historical, dict):
            raise DeliveryError("historical handoff is not a JSON object", code="INVALID_HANDOFF")
        _validate_historical_ready_contract(historical)
        historical_approval = historical.get("approval", {})
        historical_candidate = historical.get("candidate", {})
        if (
            historical_entry.get("status") != "Ready"
            or not historical_entry.get("approval_evidence_refs")
            or historical_approval.get("status") != "Ready"
            or historical_approval.get("evidence")
            not in historical_entry["approval_evidence_refs"]
            or historical_candidate.get("revision")
            != historical_entry["candidate_revision"]
            or historical_candidate.get("payload_sha256")
            != historical_entry["payload_sha256"]
            or _ready_payload_sha256(historical)
            != historical_entry["payload_sha256"]
        ):
            raise DeliveryError(
                "historical Ready handoff differs from its approval record",
                code="INVALID_HANDOFF",
            )
        historical_root = historical_handoff_path.rsplit("/", 1)[0]
        historical_artifacts = historical.get("artifacts")
        if not isinstance(historical_artifacts, list):
            raise DeliveryError(
                "historical Ready handoff artifact manifest is missing",
                code="INVALID_HANDOFF",
            )
        historical_handoff_entries = 0
        for historical_artifact in historical_artifacts:
            if (
                not isinstance(historical_artifact, dict)
                or historical_artifact.get("approval_status") != "Ready"
            ):
                raise DeliveryError(
                    "historical plan artifact is not Ready",
                    code="INVALID_HANDOFF",
                )
            historical_relative = _normalized_repo_path(
                str(historical_artifact.get("path", ""))
            )
            if not historical_relative.startswith(f"{historical_root}/"):
                raise DeliveryError(
                    "historical plan artifact escapes its approved bundle",
                    code="INVALID_HANDOFF",
                )
            if historical_relative == historical_handoff_path:
                historical_handoff_entries += 1
                if (
                    historical_artifact.get("role") != "handoff"
                    or historical_artifact.get("sha256") is not None
                ):
                    raise DeliveryError(
                        "historical handoff self-manifest entry is invalid",
                        code="INVALID_HANDOFF",
                    )
                historical_expected = sha256_bytes(historical_bytes)
                include(historical_relative, historical_expected)
                continue
            if historical_relative not in referenced_historical_paths:
                continue
            else:
                historical_expected = historical_artifact.get("sha256")
                validate_sha256(
                    historical_expected,
                    f"historical artifact {historical_relative} sha256",
                )
            if referenced_historical_paths[historical_relative] != historical_expected:
                raise DeliveryError(
                    "historical Ready source differs from its approved artifact",
                    code="SOURCE_NOT_MATERIALIZABLE",
                )
            include(historical_relative, historical_expected)
        if historical_handoff_entries != 1:
            raise DeliveryError(
                "historical artifact manifest must identify its handoff exactly once",
                code="INVALID_HANDOFF",
            )

    _verify_ready_local_sources(
        record,
        handoff,
        set(materialization),
        verify_current_sources=verify_current_sources,
        source_generation=source_generation,
    )
    return [materialization[key] for key in sorted(materialization)]


def _materialize_approved_upstream(destination: Path, items: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for item in items:
        relative = _normalized_repo_path(item["path"])
        expected = item["sha256"]
        value = item["bytes"]
        _stable_materialize_file(destination, relative, value, expected)
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
    known_secret_values: tuple[str, ...] = (),
    probe_evidence: RepositoryStateEvidence | None = None,
    lock_epoch: str | None = None,
) -> dict[str, Any]:
    root = _validate_registry_root(root or default_registry_root())
    validate_work_id(work_id)
    if (
        probe_evidence is not None
        and probe_evidence.lock_epoch == lock_epoch
        and canonical_path_text(repo)
        == canonical_path_text(probe_evidence.identity.requested_path)
    ):
        probe = probe_evidence.as_probe()
    else:
        probe = probe_repository(repo)
        probe_evidence = None
    path = _record_path(run_directory(root, probe["repo_id"], work_id))
    record = load_record(path)
    if record["status"] == "complete":
        raise DeliveryError("Complete delivery records are frozen", code="COMPLETE_FROZEN")
    if record["generations"][-1]["status"] == "ready":
        _validate_ready_generation(
            record,
            probe,
            evidence=probe_evidence,
            lock_epoch=lock_epoch,
        )
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
    if status == "awaiting_user" and phase not in {"requirements", "planning", "knowledge"}:
        raise DeliveryError(
            "awaiting_user is only valid for requirements, planning, or knowledge",
            code="ILLEGAL_TRANSITION",
        )
    if (phase == "complete") != (status == "complete"):
        raise DeliveryError("complete phase and status must be paired", code="ILLEGAL_TRANSITION")

    known_secrets = tuple(
        value
        for value in known_secret_values
        if isinstance(value, str) and value
    )
    metadata_values = (
        *evidence_refs,
        *requirements_approval_refs,
        *plan_approval_refs,
        *deferred_bug_evidence_refs,
        deferred_bug_redacted_summary or "",
        deferred_bug_human_reviewer or "",
        implementation_ledger_ref or "",
        knowledge_candidate_ref or "",
        knowledge_outcome_path or "",
        knowledge_receipt_path or "",
        knowledge_approval_evidence or "",
    )
    if any(
        secret in value
        for value in metadata_values
        if isinstance(value, str)
        for secret in known_secrets
    ):
        raise DeliveryError(
            "transition metadata contains a known secret value",
            code="INVALID_EVIDENCE_REF",
        )
    known_secret_values = known_secrets

    knowledge_gate = record.get("knowledge_gate")
    if enable_knowledge:
        if knowledge_gate is not None:
            raise DeliveryError(
                "delivery already has a knowledge gate",
                code="KNOWLEDGE_GATE_ALREADY_ENABLED",
            )
        if (
            current_phase != "implementation"
            or (phase, status) != ("implementation", "active")
            or record.get("requirements", {}).get("current_path") is None
            or record.get("plans", {}).get("current_handoff_path") is None
        ):
            raise DeliveryError(
                "enable-knowledge requires implementation/active with approved requirements and plan",
                code="MISSING_KNOWLEDGE_GATE",
            )
        record["knowledge_gate"] = _new_knowledge_gate(utc_now())
        knowledge_gate = record["knowledge_gate"]

    if isinstance(knowledge_gate, dict):
        if current_phase == "implementation" and phase == "complete":
            raise DeliveryError(
                "required knowledge delivery cannot Complete directly from implementation",
                code="KNOWLEDGE_GATE_REQUIRED",
            )
    elif phase == "knowledge":
        raise DeliveryError(
            "legacy delivery has no knowledge overlay",
            code="MISSING_KNOWLEDGE_GATE",
        )

    review_values = (
        knowledge_snapshot_before,
        knowledge_snapshot_after,
        knowledge_product_snapshot_id,
        knowledge_outcome_path,
        knowledge_outcome_sha256,
    )
    review_supplied = any(value is not None for value in review_values)
    if review_supplied and (
        not all(value is not None for value in review_values)
        or knowledge_candidate_ref is None
        or knowledge_candidate_payload_sha256 is None
    ):
        raise DeliveryError(
            "knowledge review requires Candidate, dual snapshots, product snapshot, and outcome",
            code="INCOMPLETE_KNOWLEDGE_REVIEW",
        )
    promotion_values = (
        knowledge_promotion_id,
        knowledge_receipt_path,
        knowledge_receipt_sha256,
        knowledge_approval_evidence,
    )
    promotion_supplied = any(value is not None for value in promotion_values)
    if promotion_supplied and not all(value is not None for value in promotion_values):
        raise DeliveryError(
            "knowledge promotion requires ID, receipt path/hash, and approval evidence",
            code="INCOMPLETE_KNOWLEDGE_PROMOTION",
        )
    promotion_consumed = False

    pending_inbox: tuple[str, list[str], bool, str | None, str | None] | None = None

    if (current_phase, phase) == ("planning", "requirements"):
        record["plans"]["current_handoff_path"] = None
        record["implementations"]["current_run_id"] = None
    elif (current_phase, phase) == ("implementation", "planning"):
        record["plans"]["current_handoff_path"] = None
        record["implementations"]["current_run_id"] = None

    bug_assessment_values = (
        bug_assessment_id,
        bug_assessment_path,
        bug_assessment_sha256,
        bug_assessment_markdown_path,
        bug_assessment_markdown_sha256,
    )
    bug_assessment_supplied = any(value is not None for value in bug_assessment_values)
    if bug_assessment_supplied and not all(value is not None for value in bug_assessment_values):
        raise DeliveryError("BUG assessment binding requires ID, JSON/Markdown paths and hashes", code="INCOMPLETE_ARTIFACT_REF")

    deferred_values = (
        deferred_bug_id,
        deferred_bug_relation,
        deferred_bug_status,
    )
    deferred_supplied = (
        any(value is not None for value in deferred_values)
        or bool(deferred_bug_evidence_refs)
        or deferred_bug_sensitive
        or deferred_bug_redacted_summary is not None
        or deferred_bug_human_reviewer is not None
    )
    if deferred_supplied:
        if not all(value is not None for value in deferred_values) or not deferred_bug_evidence_refs:
            raise DeliveryError("deferred BUG requires ID, relation, status, and redacted host evidence", code="INCOMPLETE_ARTIFACT_REF")
        validate_bug_id(str(deferred_bug_id))
        if deferred_bug_relation not in {"current-scope", "affecting-current-work", "unrelated"}:
            raise DeliveryError("deferred BUG relation is invalid", code="INVALID_DEFERRED_BUG")
        if deferred_bug_status not in {"pending", "materialized"}:
            raise DeliveryError("deferred BUG status is invalid", code="INVALID_DEFERRED_BUG")
        deferred_refs = _logical_refs(deferred_bug_evidence_refs, "deferred BUG redacted evidence")
        if deferred_bug_sensitive:
            if not deferred_bug_redacted_summary or not deferred_bug_human_reviewer:
                raise DeliveryError(
                    "sensitive deferred BUG requires redacted summary and named human reviewer",
                    code="INVALID_DEFERRED_BUG",
                )
            if _contains_sensitive_material(deferred_bug_redacted_summary):
                raise DeliveryError("deferred BUG summary is not safely redacted", code="INVALID_DEFERRED_BUG")
        elif deferred_bug_redacted_summary is not None or deferred_bug_human_reviewer is not None:
            raise DeliveryError(
                "non-sensitive deferred BUG cannot claim sensitive review fields",
                code="INVALID_DEFERRED_BUG",
            )
        artifact_values = (
            deferred_bug_assessment_path,
            deferred_bug_assessment_sha256,
            deferred_bug_assessment_markdown_path,
            deferred_bug_assessment_markdown_sha256,
        )
        if deferred_bug_status == "pending" and any(value is not None for value in artifact_values):
            raise DeliveryError("pending deferred BUG cannot bind assessment bytes", code="INVALID_DEFERRED_BUG")
        if deferred_bug_status == "materialized" and not all(value is not None for value in artifact_values):
            raise DeliveryError("materialized deferred BUG requires JSON/Markdown paths and hashes", code="INCOMPLETE_ARTIFACT_REF")

        bugs = record.get("bugs")
        if bugs is None:
            bugs = {
                "primary_bug_id": None,
                "assessments": [],
                "deferred": [],
                "verification": None,
            }
            record["bugs"] = bugs
            if "work_kind" not in record:
                record["work_kind"] = "standard"
        history = [
            item
            for item in bugs.get("deferred", [])
            if isinstance(item, dict) and item.get("bug_id") == deferred_bug_id
        ]
        if deferred_bug_status == "pending":
            if history:
                code = "BUG_INBOX_EXISTS" if deferred_bug_relation == "unrelated" else "INVALID_DEFERRED_BUG"
                raise DeliveryError("deferred BUG ID is already registered", code=code)
            if current_phase != "implementation":
                raise DeliveryError("new deferred BUGs may only be registered during implementation", code="INVALID_DEFERRED_BUG")
            if deferred_bug_relation == "affecting-current-work":
                if (
                    phase != "planning"
                    or status != "active"
                    or implementation_status != "Awaiting upstream reapproval"
                ):
                    raise DeliveryError("affecting BUG requires Planning reapproval", code="BUG_REQUIRES_REAPPROVAL")
            elif phase != "implementation" or status != "active":
                raise DeliveryError("current-scope and unrelated BUGs stay in the current implementation run", code="INVALID_DEFERRED_BUG")
            inbox_ref = None
            if deferred_bug_relation == "unrelated":
                inbox_ref = f"bug-inbox:{deferred_bug_id}"
                pending_inbox = (
                    str(deferred_bug_id),
                    deferred_refs,
                    deferred_bug_sensitive,
                    deferred_bug_redacted_summary,
                    deferred_bug_human_reviewer,
                )
            entry = {
                "sequence": 1,
                "bug_id": deferred_bug_id,
                "relation": deferred_bug_relation,
                "status": "pending",
                "host_evidence_refs": deferred_refs,
                "sensitive": deferred_bug_sensitive,
                "redacted_summary": deferred_bug_redacted_summary,
                "human_reviewer": deferred_bug_human_reviewer,
                "assessment_path": None,
                "assessment_sha256": None,
                "assessment_markdown_path": None,
                "assessment_markdown_sha256": None,
                "inbox_ref": inbox_ref,
            }
        else:
            if len(history) != 1 or history[0].get("status") != "pending":
                raise DeliveryError("deferred BUG materialization requires one pending event", code="INVALID_DEFERRED_BUG")
            if deferred_bug_relation != history[0].get("relation") or deferred_refs != history[0].get("host_evidence_refs"):
                raise DeliveryError("deferred BUG routing evidence is append-only", code="INVALID_DEFERRED_BUG")
            if (
                deferred_bug_sensitive is not history[0].get("sensitive")
                or deferred_bug_redacted_summary != history[0].get("redacted_summary")
                or deferred_bug_human_reviewer != history[0].get("human_reviewer")
            ):
                raise DeliveryError("deferred BUG risk routing is append-only", code="INVALID_DEFERRED_BUG")
            allowed_phases = {"implementation"}
            if deferred_bug_relation == "affecting-current-work":
                allowed_phases.add("planning")
            if current_phase not in allowed_phases or phase != current_phase:
                raise DeliveryError("deferred BUG must materialize before leaving its current routing phase", code="INVALID_DEFERRED_BUG")
            normalized = _validated_deferred_assessment(
                record,
                bug_id=str(deferred_bug_id),
                relation=str(deferred_bug_relation),
                assessment_path=str(deferred_bug_assessment_path),
                assessment_sha256=str(deferred_bug_assessment_sha256),
                markdown_path=str(deferred_bug_assessment_markdown_path),
                markdown_sha256=str(deferred_bug_assessment_markdown_sha256),
                evidence_refs=deferred_refs,
                sensitive=deferred_bug_sensitive,
                redacted_summary=deferred_bug_redacted_summary,
                human_reviewer=deferred_bug_human_reviewer,
                known_secret_values=known_secret_values,
            )
            entry = {
                "sequence": 2,
                "bug_id": deferred_bug_id,
                "relation": deferred_bug_relation,
                "status": "materialized",
                "host_evidence_refs": deferred_refs,
                "sensitive": deferred_bug_sensitive,
                "redacted_summary": deferred_bug_redacted_summary,
                "human_reviewer": deferred_bug_human_reviewer,
                "assessment_path": normalized[0],
                "assessment_sha256": normalized[1],
                "assessment_markdown_path": normalized[2],
                "assessment_markdown_sha256": normalized[3],
                "inbox_ref": history[0].get("inbox_ref"),
            }
        bugs["deferred"].append(entry)

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
        bug_entry: dict[str, Any] | None = None
        if record.get("work_kind", "standard") == "bug":
            if not bug_assessment_supplied:
                raise DeliveryError(
                    "bug delivery Requirements approval must atomically bind its assessment",
                    code="MISSING_BUG_ASSESSMENT",
                )
            bug_entry = _validated_bug_assessment_binding(
                record,
                bug_id=str(bug_assessment_id),
                assessment_path=str(bug_assessment_path),
                assessment_sha256=str(bug_assessment_sha256),
                markdown_path=str(bug_assessment_markdown_path),
                markdown_sha256=str(bug_assessment_markdown_sha256),
                requirements_path=requirements_path,
                requirements_sha256=requirements_sha256,
                approval_refs=approval_refs,
                known_secret_values=known_secret_values,
            )
        elif bug_assessment_supplied:
            raise DeliveryError("standard delivery cannot bind a BUG assessment", code="INVALID_BUG_ASSESSMENT")
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
        if bug_entry is not None:
            record["bugs"]["assessments"].append(bug_entry)
        if isinstance(knowledge_gate, dict):
            if (
                not promotion_supplied
                or knowledge_candidate_ref is None
                or knowledge_candidate_payload_sha256 is None
            ):
                raise DeliveryError(
                    "required requirements approval lacks its Ready knowledge promotion",
                    code="MISSING_KNOWLEDGE_GATE",
                )
            if knowledge_approval_evidence not in approval_refs:
                raise DeliveryError(
                    "requirements and knowledge promotion must use the same approval evidence",
                    code="INVALID_KNOWLEDGE_PROMOTION",
                )
            promotion = _validated_knowledge_promotion_binding(
                record,
                promotion_id=str(knowledge_promotion_id),
                receipt_path=str(knowledge_receipt_path),
                receipt_sha256=str(knowledge_receipt_sha256),
                candidate_ref=knowledge_candidate_ref,
                payload_sha256=knowledge_candidate_payload_sha256,
                approval_evidence=str(knowledge_approval_evidence),
                expected_stages={"requirements"},
                known_secret_values=known_secret_values,
            )
            if promotion["receipt_path"] not in evidence_refs:
                raise DeliveryError(
                    "requirements event must reference its knowledge promotion receipt",
                    code="MISSING_KNOWLEDGE_GATE",
                )
            knowledge_gate["candidate_ref"] = promotion["candidate_ref"]
            knowledge_gate["candidate_payload_sha256"] = promotion["payload_sha256"]
            knowledge_gate["current_promotion_id"] = promotion["promotion_id"]
            knowledge_gate["promotions"].append(promotion)
            promotion_consumed = True

    elif bug_assessment_supplied:
        raise DeliveryError("BUG assessment must be bound with Requirements approval", code="MISSING_GATE")

    if any(value is not None for value in (handoff_path, candidate_revision, payload_sha256)) or plan_approval_refs:
        if handoff_path is None or candidate_revision is None or payload_sha256 is None or not plan_approval_refs:
            raise DeliveryError("Ready plan requires handoff, revision, payload hash, and approval evidence", code="INCOMPLETE_ARTIFACT_REF")
        if (phase, status) != ("implementation", "active"):
            raise DeliveryError("Ready plan must atomically advance to implementation/active", code="MISSING_GATE")
        handoff_path = _normalized_repo_path(handoff_path)
        revision = _plan_revision(handoff_path, record["artifact_root"])
        if revision is None:
            raise DeliveryError("handoff path is outside the Work ID plan root", code="INVALID_PATH")
        worktree = Path(record["generations"][-1]["canonical_worktree"])
        handoff_file = worktree / Path(*handoff_path.split("/"))
        try:
            handoff = json.loads(_stable_read_file(worktree, handoff_file).decode("utf-8"))
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
        if record.get("work_kind", "standard") == "bug":
            assessments = record.get("bugs", {}).get("assessments", [])
            current_assessment = assessments[-1] if assessments else None
            bug_context = handoff.get("bug_context")
            assessment_binding = bug_context.get("assessment", {}) if isinstance(bug_context, dict) else {}
            if (
                current_assessment is None
                or not isinstance(bug_context, dict)
                or bug_context.get("bug_id") != current_assessment.get("bug_id")
                or assessment_binding.get("path") != current_assessment.get("path")
                or assessment_binding.get("sha256") != current_assessment.get("sha256")
                or assessment_binding.get("markdown_path") != current_assessment.get("markdown_path")
                or assessment_binding.get("markdown_sha256") != current_assessment.get("markdown_sha256")
            ):
                raise DeliveryError(
                    "bug Ready plan must bind the current approved assessment",
                    code="INVALID_HANDOFF",
                )
        elif handoff.get("bug_context") is not None or any(
            source.get("kind") == "bug" for source in sources if isinstance(source, dict)
        ):
            raise DeliveryError(
                "standard delivery cannot acquire a primary BUG plan implicitly; use deferred assessment as an approved supporting source",
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
        if isinstance(knowledge_gate, dict):
            if (
                not promotion_supplied
                or knowledge_candidate_ref is None
                or knowledge_candidate_payload_sha256 is None
            ):
                raise DeliveryError(
                    "required plan approval lacks its Ready knowledge promotion",
                    code="MISSING_KNOWLEDGE_GATE",
                )
            if knowledge_approval_evidence not in approval_refs:
                raise DeliveryError(
                    "plan and knowledge promotion must use the same approval evidence",
                    code="INVALID_KNOWLEDGE_PROMOTION",
                )
            promotion = _validated_knowledge_promotion_binding(
                record,
                promotion_id=str(knowledge_promotion_id),
                receipt_path=str(knowledge_receipt_path),
                receipt_sha256=str(knowledge_receipt_sha256),
                candidate_ref=knowledge_candidate_ref,
                payload_sha256=knowledge_candidate_payload_sha256,
                approval_evidence=str(knowledge_approval_evidence),
                expected_stages={"planning"},
                known_secret_values=known_secret_values,
            )
            if promotion["receipt_path"] not in evidence_refs:
                raise DeliveryError(
                    "plan event must reference its knowledge promotion receipt",
                    code="MISSING_KNOWLEDGE_GATE",
                )
            knowledge_gate["candidate_ref"] = promotion["candidate_ref"]
            knowledge_gate["candidate_payload_sha256"] = promotion["payload_sha256"]
            knowledge_gate["current_promotion_id"] = promotion["promotion_id"]
            knowledge_gate["promotions"].append(promotion)
            promotion_consumed = True

    verification_values = (
        bug_verification_path,
        bug_verification_sha256,
        bug_verification_result,
    )
    verification_supplied = any(value is not None for value in verification_values)
    if verification_supplied and not all(value is not None for value in verification_values):
        raise DeliveryError("BUG verification requires path, hash, and result", code="INCOMPLETE_ARTIFACT_REF")
    if verification_supplied:
        if record.get("work_kind", "standard") == "bug" and bug_verification_result == "failed":
            raise DeliveryError(
                "failed BUG verification cannot enter a terminal knowledge gate",
                code="FAILED_BUG_VERIFICATION",
            )
        legacy_terminal = (
            not isinstance(knowledge_gate, dict)
            and (phase, status) == ("complete", "complete")
            and implementation_status == "Complete"
        )
        knowledge_review_terminal = (
            isinstance(knowledge_gate, dict)
            and current_phase == "implementation"
            and (phase, status) == ("knowledge", "active")
            and implementation_status == "Complete"
        )
        if not legacy_terminal and not knowledge_review_terminal:
            raise DeliveryError(
                "successful BUG verification may only bind at legacy Complete or the reviewed knowledge gate",
                code="INVALID_BUG_VERIFICATION",
            )

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
        verification_entry: dict[str, Any] | None = None
        if verification_supplied:
            if record.get("work_kind", "standard") != "bug":
                raise DeliveryError("standard delivery cannot bind BUG verification", code="INVALID_BUG_VERIFICATION")
            verification_entry = _validated_bug_verification_binding(
                record,
                implementation_run_id=implementation_run_id,
                path=str(bug_verification_path),
                expected_sha256=str(bug_verification_sha256),
                result=str(bug_verification_result),
                known_secret_values=known_secret_values,
            )
            entry.update(
                {
                    "bug_verification_ref": verification_entry["path"],
                    "bug_verification_sha256": verification_entry["sha256"],
                    "bug_verification_result": verification_entry["result"],
                }
            )
        existing = next(
            (item for item in record["implementations"]["runs"] if item["run_id"] == implementation_run_id),
            None,
        )
        if existing is not None:
            existing["ledger_ref"] = implementation_ledger_ref
            existing["status"] = implementation_status
            if verification_entry is not None:
                existing.update(
                    {
                        "bug_verification_ref": verification_entry["path"],
                        "bug_verification_sha256": verification_entry["sha256"],
                        "bug_verification_result": verification_entry["result"],
                    }
                )
        else:
            record["implementations"]["runs"].append(entry)
        record["implementations"]["current_run_id"] = implementation_run_id
        if verification_entry is not None:
            record["bugs"]["verification"] = verification_entry
    elif verification_supplied:
        raise DeliveryError("BUG verification must bind the implementation run atomically", code="INCOMPLETE_ARTIFACT_REF")

    if current_phase == "knowledge" and phase == "implementation":
        if not isinstance(knowledge_gate, dict) or implementation_status != "Active":
            raise DeliveryError(
                "product changes from knowledge require an Active implementation attempt",
                code="MISSING_GATE",
            )
        knowledge_gate.update(
            {
                "candidate_ref": None,
                "candidate_payload_sha256": None,
                "knowledge_snapshot_id": None,
                "knowledge_post_snapshot_id": None,
                "product_snapshot_id": None,
                "outcome_path": None,
                "outcome_sha256": None,
                "review": None,
            }
        )

    if review_supplied:
        if (
            not isinstance(knowledge_gate, dict)
            or current_phase != "implementation"
            or (phase, status) != ("knowledge", "active")
            or implementation_status != "Complete"
        ):
            raise DeliveryError(
                "reviewed knowledge bindings must atomically enter knowledge/active",
                code="INVALID_KNOWLEDGE_REVIEW",
            )
        candidate_match = KNOWLEDGE_CANDIDATE_RE.fullmatch(str(knowledge_candidate_ref))
        if candidate_match is None:
            raise DeliveryError(
                "reviewed knowledge Candidate ref is invalid",
                code="INVALID_KNOWLEDGE_REVIEW",
            )
        validate_sha256(
            str(knowledge_candidate_payload_sha256),
            "knowledge candidate payload_sha256",
        )
        for label, value in (
            ("knowledge_snapshot_before", str(knowledge_snapshot_before)),
            ("knowledge_snapshot_after", str(knowledge_snapshot_after)),
            ("knowledge_product_snapshot_id", str(knowledge_product_snapshot_id)),
        ):
            validate_sha256(value, label)
        if knowledge_snapshot_before != knowledge_snapshot_after:
            raise DeliveryError(
                "fresh review observed knowledge snapshot drift",
                code="KNOWLEDGE_SNAPSHOT_DRIFT",
            )
        verified_knowledge = _verified_knowledge_snapshot(
            record,
            candidate_ref=str(knowledge_candidate_ref),
            payload_sha256=str(knowledge_candidate_payload_sha256),
        )
        if verified_knowledge.get("snapshot_id") != knowledge_snapshot_before:
            raise DeliveryError(
                "caller-provided knowledge snapshot does not match the canonical tree and sealed Candidate",
                code="KNOWLEDGE_SNAPSHOT_DRIFT",
            )
        outcome_relative, outcome_sha = _validated_knowledge_outcome(
            record,
            path=str(knowledge_outcome_path),
            expected_sha256=str(knowledge_outcome_sha256),
            known_secret_values=known_secret_values,
        )
        knowledge_gate.update(
            {
                "candidate_ref": knowledge_candidate_ref,
                "candidate_payload_sha256": knowledge_candidate_payload_sha256,
                "knowledge_snapshot_id": knowledge_snapshot_before,
                "knowledge_post_snapshot_id": verified_knowledge["post_snapshot_id"],
                "product_snapshot_id": knowledge_product_snapshot_id,
                "outcome_path": outcome_relative,
                "outcome_sha256": outcome_sha,
                "review": {
                    "knowledge_snapshot_before": knowledge_snapshot_before,
                    "knowledge_snapshot_after": knowledge_snapshot_after,
                    "candidate_ref": knowledge_candidate_ref,
                    "payload_sha256": knowledge_candidate_payload_sha256,
                },
            }
        )
        current_run_id = record["implementations"]["current_run_id"]
        current_run = next(
            (
                item
                for item in record["implementations"]["runs"]
                if item["run_id"] == current_run_id
            ),
            None,
        )
        if current_run is None or current_run.get("status") != "Complete":
            raise DeliveryError(
                "knowledge review requires a Complete implementation run",
                code="MISSING_GATE",
            )
        review_errors = _complete_implementation_errors(
            record,
            current_run,
            evidence_refs,
            known_secret_values,
        )
        if review_errors:
            raise DeliveryError(
                "knowledge review bindings differ from persisted implementation evidence: "
                + "; ".join(review_errors),
                code="INVALID_KNOWLEDGE_REVIEW",
                details={"errors": review_errors},
            )
    elif current_phase == "implementation" and phase == "knowledge":
        raise DeliveryError(
            "entering knowledge requires reviewed Candidate, snapshots, and outcome",
            code="MISSING_KNOWLEDGE_GATE",
        )

    if current_phase == "knowledge" and phase == "knowledge" and status == "awaiting_user":
        if not isinstance(knowledge_gate, dict) or not isinstance(knowledge_gate.get("review"), dict):
            raise DeliveryError(
                "knowledge Candidate cannot be presented before fresh review",
                code="MISSING_KNOWLEDGE_GATE",
            )

    if current_phase == "knowledge" and phase == "complete":
        if not isinstance(knowledge_gate, dict) or current_status != "awaiting_user":
            raise DeliveryError(
                "knowledge completion requires the awaiting-user approval state",
                code="MISSING_KNOWLEDGE_GATE",
            )
        if not promotion_supplied:
            raise DeliveryError(
                "knowledge completion requires a persisted Ready promotion",
                code="MISSING_KNOWLEDGE_GATE",
            )
        promotion = _validated_knowledge_promotion_binding(
            record,
            promotion_id=str(knowledge_promotion_id),
            receipt_path=str(knowledge_receipt_path),
            receipt_sha256=str(knowledge_receipt_sha256),
            candidate_ref=str(knowledge_gate.get("candidate_ref")),
            payload_sha256=str(knowledge_gate.get("candidate_payload_sha256")),
            approval_evidence=str(knowledge_approval_evidence),
            expected_stages={"implementation", "bug"},
            known_secret_values=known_secret_values,
        )
        knowledge_module = _knowledge_delivery_module()
        actual_post_snapshot = knowledge_module.compute_knowledge_tree_snapshot(
            record["generations"][-1]["canonical_worktree"]
        )
        if (
            actual_post_snapshot.get("snapshot_id")
            != knowledge_gate.get("knowledge_post_snapshot_id")
        ):
            raise DeliveryError(
                "canonical knowledge differs from the reviewed Candidate postimage tree",
                code="KNOWLEDGE_SNAPSHOT_DRIFT",
            )
        if promotion["receipt_path"] not in evidence_refs:
            raise DeliveryError(
                "Complete event must reference the knowledge promotion receipt",
                code="MISSING_KNOWLEDGE_GATE",
            )
        knowledge_gate["promotions"].append(promotion)
        knowledge_gate["current_promotion_id"] = promotion["promotion_id"]
        promotion_consumed = True
    elif promotion_supplied and not promotion_consumed:
        raise DeliveryError(
            "knowledge promotion is not valid for this phase transition",
            code="INVALID_KNOWLEDGE_PROMOTION",
        )

    if phase == "planning" and current_phase == "requirements" and requirements_path is None:
        raise DeliveryError("planning requires a newly persisted Ready requirements revision", code="MISSING_GATE")
    if phase == "implementation" and current_phase == "planning" and handoff_path is None:
        raise DeliveryError("implementation requires the newly Ready plan and may not ask a third approval", code="MISSING_GATE")
    if phase == "complete":
        _approved_upstream_materialization(record)
        deferred_histories: dict[str, list[dict[str, Any]]] = {}
        for item in record.get("bugs", {}).get("deferred", []):
            if isinstance(item, dict):
                deferred_histories.setdefault(str(item.get("bug_id")), []).append(item)
        if any(history[-1].get("status") == "pending" for history in deferred_histories.values() if history):
            raise DeliveryError(
                "deferred BUG evidence must be materialized before terminal handoff",
                code="PENDING_BUG_EVIDENCE",
            )
        current_run_id = record["implementations"]["current_run_id"]
        current_run = next(
            (item for item in record["implementations"]["runs"] if item["run_id"] == current_run_id),
            None,
        )
        if current_run is None or current_run["status"] != "Complete":
            raise DeliveryError("delivery Complete requires a Complete implementation run", code="MISSING_GATE")
        if record.get("work_kind", "standard") == "bug":
            verification = record.get("bugs", {}).get("verification")
            if not isinstance(verification, dict) or (
                not isinstance(knowledge_gate, dict) and not verification_supplied
            ):
                raise DeliveryError("bug delivery Complete requires bug-verification/v1", code="MISSING_BUG_VERIFICATION")
            if verification.get("path") not in evidence_refs:
                raise DeliveryError("Complete event must reference BUG verification", code="MISSING_BUG_VERIFICATION")
        terminal_errors = _complete_implementation_errors(
            record,
            current_run,
            evidence_refs,
            known_secret_values,
        )
        if terminal_errors:
            raise DeliveryError(
                "delivery Complete requires persisted implementation Ledger and accepted review evidence",
                code="MISSING_GATE",
            )

    _append_event(record, kind=event, phase=phase, status=status, evidence_refs=evidence_refs)
    errors = validate_record(record)
    if errors:
        raise DeliveryError(f"transition would create an invalid record: {'; '.join(errors)}", code="INVALID_RECORD")
    inbox_creation: tuple[str, Path, dict[str, Any], bool] | None = None
    if pending_inbox is not None:
        inbox_creation = _create_global_bug_inbox(
            root,
            record,
            bug_id=pending_inbox[0],
            evidence_refs=pending_inbox[1],
            sensitive=pending_inbox[2],
            redacted_summary=pending_inbox[3],
            human_reviewer=pending_inbox[4],
        )
        created_ref = inbox_creation[0]
        if created_ref != f"bug-inbox:{pending_inbox[0]}":
            raise DeliveryError("global BUG inbox ref is not canonical", code="INVALID_DEFERRED_BUG")
    try:
        _atomic_write_json(path, record)
    except Exception:
        if inbox_creation is not None and inbox_creation[3]:
            try:
                persisted = load_record(path)
            except (DeliveryError, OSError):
                persisted = None
            persisted_history = (
                persisted.get("bugs", {}).get("deferred", [])
                if isinstance(persisted, dict)
                else []
            )
            persisted_bug = any(
                isinstance(item, dict) and item.get("bug_id") == pending_inbox[0]
                for item in persisted_history
            )
            if not persisted_bug:
                _rollback_global_bug_inbox(root, inbox_creation[1], inbox_creation[2])
        raise
    return _result(record, path, outcome="transitioned")
