"""Required delivery knowledge gate and dual-snapshot contracts."""

from __future__ import annotations

import copy
import json
import stat
from pathlib import Path
from typing import Any

import knowledge_governance
import knowledge_workflow
from knowledge_governance import canonical_sha256
from knowledge_outcome import validate_implementation_outcome_result
from knowledge_query import (
    KnowledgeError,
    _eligible_paths,
    _metadata_is_redirect,
    _redirected,
    normalized_path,
    sha256_bytes,
)


def new_required_knowledge_gate(*, enabled_at: str) -> dict[str, Any]:
    if not isinstance(enabled_at, str) or "T" not in enabled_at:
        raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "enabled_at is invalid", exit_code=2)
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


def compute_product_snapshot(repo_value: str) -> dict[str, Any]:
    """Hash Git-eligible product files while deliberately excluding canonical knowledge."""

    repo = Path(repo_value).resolve()
    eligible = _eligible_paths(repo)
    files = [
        {
            "path": relative,
            "sha256": sha256_bytes((repo / Path(*relative.split("/"))).read_bytes()),
        }
        for relative in sorted(eligible, key=lambda value: value.encode("utf-8"))
        if not relative.startswith("docs/knowledge/")
    ]
    snapshot = {
        "schema": "knowledge-product-snapshot/v1",
        "files": files,
    }
    snapshot["snapshot_id"] = canonical_sha256(snapshot)
    return snapshot


def compute_knowledge_tree_snapshot(repo_value: str) -> dict[str, Any]:
    """Hash every Git-eligible canonical knowledge file, including uncommitted files."""

    repo = Path(repo_value).resolve()
    eligible = _eligible_paths(repo, ("docs/knowledge",))
    files = [
        {
            "path": relative,
            "sha256": sha256_bytes((repo / Path(*relative.split("/"))).read_bytes()),
        }
        for relative in sorted(eligible, key=lambda value: value.encode("utf-8"))
        if relative.startswith("docs/knowledge/")
    ]
    snapshot = {"schema": "knowledge-tree-snapshot/v1", "files": files}
    snapshot["snapshot_id"] = canonical_sha256(snapshot)
    return snapshot


def _candidate_path(
    repo_id: str,
    candidate_ref: str,
    *,
    registry_root: Path | None = None,
) -> Path:
    prefix = "knowledge:candidates/"
    suffix = "/candidate.json"
    if not candidate_ref.startswith(prefix) or not candidate_ref.endswith(suffix):
        raise KnowledgeError("CANDIDATE_REF_INVALID", "Candidate ref is invalid", exit_code=2)
    promotion_id = candidate_ref[len(prefix) : -len(suffix)]
    if not promotion_id.startswith("promotion-") or "/" in promotion_id or "\\" in promotion_id:
        raise KnowledgeError("CANDIDATE_REF_INVALID", "Candidate ref is invalid", exit_code=2)
    root = registry_root or knowledge_governance.default_registry_root()
    path = (
        root
        / "repos"
        / repo_id
        / "candidates"
        / promotion_id
        / "candidate.json"
    )
    if _redirected(path, root) or not path.is_file():
        raise KnowledgeError("CANDIDATE_MISSING", "sealed Candidate is unavailable", exit_code=3)
    return path


def _stable_registry_read(root: Path, path: Path) -> bytes:
    if _redirected(path, root):
        raise KnowledgeError("CANDIDATE_MISSING", "sealed Candidate is unavailable", exit_code=3)
    try:
        before = path.lstat()
        if _metadata_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            raise OSError("Candidate is not a regular file")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise KnowledgeError(
            "CANDIDATE_MISSING",
            "sealed Candidate is unavailable",
            exit_code=3,
        ) from exc
    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if (
        fingerprint_before != fingerprint_after
        or _metadata_is_redirect(after)
        or _redirected(path, root)
    ):
        raise KnowledgeError(
            "CANDIDATE_INVALID",
            "sealed Candidate changed while it was read",
            exit_code=3,
        )
    return raw


def build_knowledge_snapshot(
    repo_value: str,
    *,
    sealed: dict[str, Any],
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    repo_id = knowledge_governance.repository_id(repo)
    if (
        not isinstance(sealed, dict)
        or sealed.get("schema") != "knowledge-candidate-seal/v1"
        or sealed.get("repo_id") != repo_id
        or sealed.get("status") != "Candidate"
    ):
        raise KnowledgeError("CANDIDATE_INVALID", "sealed Candidate result is invalid", exit_code=2)
    candidate_ref = sealed.get("candidate_ref")
    registry_root = knowledge_governance.default_registry_root()
    candidate_path = _candidate_path(
        repo_id,
        str(candidate_ref),
        registry_root=registry_root,
    )
    try:
        candidate = json.loads(
            _stable_registry_read(registry_root, candidate_path).decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError("CANDIDATE_INVALID", "sealed Candidate is unreadable", exit_code=3) from exc
    from knowledge_promotion import _candidate_payload_sha256, _read_postimage

    payload = candidate.get("payload_sha256")
    if (
        candidate.get("schema") != "knowledge-candidate/v1"
        or payload != _candidate_payload_sha256(candidate)
        or payload != sealed.get("payload_sha256")
    ):
        raise KnowledgeError("CANDIDATE_DIGEST_DRIFT", "sealed Candidate digest drifted", exit_code=3)
    operations = candidate.get("operations")
    if not isinstance(operations, list):
        raise KnowledgeError("CANDIDATE_INVALID", "sealed Candidate operations are invalid", exit_code=2)
    current_tree = compute_knowledge_tree_snapshot(str(repo))
    expected_files = {item["path"]: item["sha256"] for item in current_tree["files"]}
    bound_operations: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise KnowledgeError("CANDIDATE_INVALID", "sealed Candidate operation is invalid", exit_code=2)
        relative = normalized_path(str(operation.get("path", "")))
        postimage = _read_postimage(candidate_path, operation)
        if relative.startswith("docs/knowledge/"):
            current_sha = expected_files.get(relative)
            if operation.get("kind") == "create" and current_sha is not None:
                raise KnowledgeError("CANDIDATE_PREIMAGE_DRIFT", f"create target exists: {relative}", exit_code=3)
            if operation.get("kind") == "update" and current_sha != operation.get("preimage_sha256"):
                raise KnowledgeError("CANDIDATE_PREIMAGE_DRIFT", f"update target drifted: {relative}", exit_code=3)
            expected_files[relative] = sha256_bytes(postimage)
        bound = copy.deepcopy(operation)
        bound["postimage_size"] = len(postimage)
        bound_operations.append(bound)
    expected_tree = {
        "schema": "knowledge-tree-snapshot/v1",
        "files": [
            {"path": path, "sha256": expected_files[path]}
            for path in sorted(expected_files, key=lambda value: value.encode("utf-8"))
        ],
    }
    expected_tree["snapshot_id"] = canonical_sha256(expected_tree)
    snapshot = {
        "schema": "knowledge-snapshot/v1",
        "repo_id": repo_id,
        "candidate_ref": candidate_ref,
        "payload_sha256": payload,
        "preimages": current_tree["files"],
        "postimages": expected_tree["files"],
        "operations": bound_operations,
        "pre_snapshot_id": current_tree["snapshot_id"],
        "post_snapshot_id": expected_tree["snapshot_id"],
    }
    snapshot["snapshot_id"] = canonical_sha256(snapshot)
    return snapshot


def _validate_outcome(repo: Path, outcome: dict[str, Any], work_id: str) -> None:
    record = validate_implementation_outcome_result(
        str(repo),
        outcome=outcome,
        expected_work_id=work_id,
    )
    if record.get("review", {}).get("verdict") != "APPROVED":
        raise KnowledgeError("OUTCOME_INVALID", "reviewed implementation outcome is invalid", exit_code=2)


def _validate_apply_result(
    repo: Path,
    applied: dict[str, Any],
    *,
    work_id: str,
    candidate_ref: str,
    payload_sha256: str,
    approval_evidence: str,
) -> dict[str, Any]:
    if not isinstance(applied, dict) or applied.get("schema") != "knowledge-apply/v1":
        raise KnowledgeError("PROMOTION_INVALID", "apply result is invalid", exit_code=2)
    promotion = applied.get("promotion")
    if (
        not isinstance(promotion, dict)
        or promotion.get("schema") != "knowledge-promotion/v1"
        or promotion.get("stage") not in {"implementation", "bug"}
        or promotion.get("work_id") != work_id
        or promotion.get("candidate_ref") != candidate_ref
        or promotion.get("payload_sha256") != payload_sha256
        or promotion.get("approval", {}).get("evidence") != approval_evidence
        or promotion.get("lint", {}).get("required_outcome") != "passed"
        or promotion.get("status") != "Ready"
        or applied.get("post_apply_lint", {}).get("outcome") != "passed"
    ):
        raise KnowledgeError("MISSING_KNOWLEDGE_GATE", "applied promotion differs from review", exit_code=3)
    relative = normalized_path(str(applied.get("receipt_path", "")))
    receipt = repo / Path(*relative.split("/"))
    if (
        not relative.startswith("docs/knowledge/meta/promotions/")
        or receipt.is_symlink()
        or not receipt.is_file()
        or sha256_bytes(receipt.read_bytes()) != applied.get("receipt_sha256")
    ):
        raise KnowledgeError("PROMOTION_DRIFT", "Ready receipt is missing or drifted", exit_code=3)
    try:
        persisted = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError("PROMOTION_INVALID", "Ready receipt is unreadable", exit_code=3) from exc
    if persisted != promotion:
        raise KnowledgeError("PROMOTION_DRIFT", "Ready receipt differs from apply result", exit_code=3)
    return promotion


def advance_knowledge_gate(
    record: dict[str, Any],
    *,
    action: str,
    repo_value: str | None = None,
    outcome: dict[str, Any] | None = None,
    sealed: dict[str, Any] | None = None,
    knowledge_snapshot_before: dict[str, Any] | None = None,
    knowledge_snapshot_after: dict[str, Any] | None = None,
    applied: dict[str, Any] | None = None,
    approval_evidence: str | None = None,
) -> dict[str, Any]:
    """Advance only the required implementation→knowledge→complete state sequence."""

    if not isinstance(record, dict) or record.get("knowledge_gate", {}).get("policy") != "required":
        raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "required knowledge overlay is missing", exit_code=2)
    current = copy.deepcopy(record)
    gate = current["knowledge_gate"]
    work_id = current.get("work_id")
    if action == "complete":
        raise KnowledgeError(
            "KNOWLEDGE_GATE_REQUIRED",
            "required delivery cannot Complete directly from implementation",
            exit_code=3,
            recoverable=True,
        )
    if action == "review-approved":
        if current.get("phase") != "implementation" or current.get("status") != "active":
            raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "review gate starts from implementation/active", exit_code=2)
        if repo_value is None or outcome is None or sealed is None:
            raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "review gate bindings are incomplete", exit_code=2)
        repo = Path(repo_value).resolve()
        _validate_outcome(repo, outcome, str(work_id))
        if (
            not isinstance(knowledge_snapshot_before, dict)
            or not isinstance(knowledge_snapshot_after, dict)
            or knowledge_snapshot_before != knowledge_snapshot_after
            or knowledge_snapshot_before.get("schema") != "knowledge-snapshot/v1"
            or knowledge_snapshot_before.get("candidate_ref") != sealed.get("candidate_ref")
            or knowledge_snapshot_before.get("payload_sha256") != sealed.get("payload_sha256")
            or not isinstance(knowledge_snapshot_before.get("post_snapshot_id"), str)
            or sealed.get("stage") not in {"implementation", "bug"}
            or sealed.get("work_id") != work_id
        ):
            raise KnowledgeError("KNOWLEDGE_SNAPSHOT_DRIFT", "reviewed knowledge snapshot is invalid", exit_code=3)
        product = compute_product_snapshot(str(repo))
        gate.update(
            {
                "candidate_ref": sealed["candidate_ref"],
                "candidate_payload_sha256": sealed["payload_sha256"],
                "knowledge_snapshot_id": knowledge_snapshot_before["snapshot_id"],
                "knowledge_post_snapshot_id": knowledge_snapshot_before["post_snapshot_id"],
                "product_snapshot_id": product["snapshot_id"],
                "outcome_path": outcome["path"],
                "outcome_sha256": outcome["sha256"],
                "review": {
                    "knowledge_snapshot_before": knowledge_snapshot_before["snapshot_id"],
                    "knowledge_snapshot_after": knowledge_snapshot_after["snapshot_id"],
                    "candidate_ref": sealed["candidate_ref"],
                    "payload_sha256": sealed["payload_sha256"],
                },
            }
        )
        current["phase"] = "knowledge"
        current["status"] = "awaiting_user"
        return current
    if action == "promotion-applied":
        if current.get("phase") != "knowledge" or current.get("status") != "awaiting_user":
            raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "promotion gate starts from knowledge/awaiting_user", exit_code=2)
        if repo_value is None or applied is None or not isinstance(approval_evidence, str):
            raise KnowledgeError("KNOWLEDGE_GATE_INVALID", "promotion gate bindings are incomplete", exit_code=2)
        repo = Path(repo_value).resolve()
        if compute_product_snapshot(str(repo))["snapshot_id"] != gate.get("product_snapshot_id"):
            raise KnowledgeError("PRODUCT_SNAPSHOT_DRIFT", "product bytes changed after review", exit_code=3)
        promotion = _validate_apply_result(
            repo,
            applied,
            work_id=str(work_id),
            candidate_ref=str(gate.get("candidate_ref")),
            payload_sha256=str(gate.get("candidate_payload_sha256")),
            approval_evidence=approval_evidence,
        )
        if (
            compute_knowledge_tree_snapshot(str(repo))["snapshot_id"]
            != gate.get("knowledge_post_snapshot_id")
        ):
            raise KnowledgeError(
                "KNOWLEDGE_SNAPSHOT_DRIFT",
                "canonical knowledge differs from the reviewed Candidate postimage tree",
                exit_code=3,
            )
        gate["current_promotion_id"] = promotion["promotion_id"]
        gate["promotions"].append(
            {
                "promotion_id": promotion["promotion_id"],
                "candidate_ref": promotion["candidate_ref"],
                "payload_sha256": promotion["payload_sha256"],
                "receipt_path": applied["receipt_path"],
                "receipt_sha256": applied["receipt_sha256"],
                "approval_evidence": approval_evidence,
                "status": "Ready",
            }
        )
        current["phase"] = "complete"
        current["status"] = "complete"
        return current
    raise KnowledgeError("KNOWLEDGE_GATE_INVALID", f"unknown gate action: {action}", exit_code=2)

