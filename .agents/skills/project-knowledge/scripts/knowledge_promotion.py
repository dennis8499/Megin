"""Transactional Candidate application and recovery."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Iterable

import knowledge_governance
from knowledge_query import (
    KnowledgeError,
    _eligible_paths,
    _metadata_is_redirect,
    _run,
    _verify_source_ref,
    normalized_path,
    sha256_bytes,
)


CANDIDATE_REF_RE = re.compile(
    r"^knowledge:candidates/(promotion-[a-z0-9-]+)/candidate\.json$"
)
SECRET_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:secret|token|password|passwd|credential|api[-_.]?key|private[-_.]?key)"
    r"\s*[:=]\s*\S{6,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b"
    r"|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    r")"
)
ALLOWED_DRAFT_STAGES = {
    "bootstrap",
    "bootstrap-quarantine",
    "requirements",
    "planning",
    "implementation",
    "bug",
    "lint-repair",
}
FINALIZER_HASH_SENTINEL = "0" * 64


class SimulatedCrash(BaseException):
    """Test-only crash boundary that intentionally leaves an in-progress journal."""


def _strict_object(raw: bytes, label: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise KnowledgeError(
            "CONTRACT_CORRUPT",
            f"{label} is not strict UTF-8 JSON",
            exit_code=2,
        ) from exc
    if not isinstance(value, dict):
        raise KnowledgeError("CONTRACT_CORRUPT", f"{label} is not an object", exit_code=2)
    return value


def _repo_registry(repo: Path) -> tuple[str, Path]:
    repo_id = knowledge_governance.repository_id(repo)
    root = knowledge_governance.default_registry_root() / "repos" / repo_id
    return repo_id, root


def _candidate_path(repo_root: Path, candidate_ref: str) -> Path:
    match = CANDIDATE_REF_RE.fullmatch(candidate_ref)
    if match is None:
        raise KnowledgeError(
            "CANDIDATE_REF_INVALID",
            "candidate ref is not canonical",
            exit_code=2,
        )
    candidate = repo_root / "candidates" / match.group(1) / "candidate.json"
    try:
        registry_root = repo_root.parents[1]
        candidate.relative_to(registry_root)
    except (IndexError, ValueError) as exc:
        raise KnowledgeError("CANDIDATE_REF_INVALID", "candidate ref escapes registry", exit_code=3) from exc
    if knowledge_governance._registry_path_redirected(registry_root, candidate):
        raise KnowledgeError("CANDIDATE_MISSING", "sealed candidate does not exist", exit_code=3)
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise KnowledgeError(
            "CANDIDATE_MISSING",
            "sealed candidate does not exist",
            exit_code=3,
        ) from exc
    if _metadata_is_redirect(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise KnowledgeError("CANDIDATE_MISSING", "sealed candidate does not exist", exit_code=3)
    return candidate


def _load_candidate(repo_root: Path, candidate_ref: str) -> tuple[dict[str, Any], Path]:
    path = _candidate_path(repo_root, candidate_ref)
    registry_root = repo_root.parents[1]
    raw = knowledge_governance._stable_registry_read(
        registry_root,
        path,
        missing_code="CANDIDATE_MISSING",
        invalid_code="CANDIDATE_INVALID",
        label="sealed Candidate",
    )
    candidate = _strict_object(raw, "knowledge Candidate")
    if candidate.get("schema") != "knowledge-candidate/v1" or candidate.get("status") != "Candidate":
        raise KnowledgeError("CANDIDATE_INVALID", "candidate lifecycle is invalid", exit_code=2)
    actual = candidate.get("payload_sha256")
    if actual != _candidate_payload_sha256(candidate):
        raise KnowledgeError(
            "CANDIDATE_DIGEST_DRIFT",
            "candidate payload digest differs from sealed content",
            exit_code=3,
        )
    return candidate, path


def _is_finalizer_path(candidate: dict[str, Any], relative: str) -> bool:
    promotion_id = str(candidate.get("promotion_id", ""))
    return relative in {
        "docs/knowledge/log.md",
        f"docs/knowledge/meta/promotions/{promotion_id}.json",
    }


def _candidate_payload_sha256(candidate: dict[str, Any]) -> str:
    """Hash the sealed payload while treating deterministic self-references canonically.

    The Ready receipt contains this digest and the log contains the receipt projection.
    Their operation hashes therefore cannot participate literally in their own digest.
    Paths, kinds, preimages, refs, approval binding, and every non-finalizer postimage hash
    remain covered; load/apply separately re-derive and byte-compare both finalizers.
    """

    normalized = copy.deepcopy(candidate)
    normalized.pop("payload_sha256", None)
    for operation in normalized.get("operations", []):
        if isinstance(operation, dict) and _is_finalizer_path(normalized, str(operation.get("path", ""))):
            operation["postimage_sha256"] = FINALIZER_HASH_SENTINEL
    return knowledge_governance.canonical_sha256(normalized)


def _redirected(path: Path, repo: Path) -> bool:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return True
    cursor = repo
    for part in relative.parts:
        cursor = cursor / part
        is_junction = getattr(cursor, "is_junction", lambda: False)
        if cursor.is_symlink() or is_junction():
            return True
        if not cursor.exists():
            break
    return False


def _formal_target_allowed(relative: str, stage: str | None, work_id: str | None) -> bool:
    if not isinstance(work_id, str) or not work_id:
        return False
    root = re.escape(f"docs/work/{work_id}")
    if stage == "requirements":
        return re.fullmatch(rf"{root}/requirements(?:-[2-9][0-9]*)?\.md", relative) is not None
    if stage == "planning":
        return re.fullmatch(rf"{root}/plan(?:-[2-9][0-9]*)?/[^/]+\.(?:md|json)", relative) is not None
    return False


def _target(
    repo: Path,
    raw: str,
    *,
    stage: str | None = None,
    work_id: str | None = None,
) -> tuple[str, Path]:
    relative = normalized_path(raw)
    if not relative.startswith("docs/knowledge/") and not _formal_target_allowed(
        relative,
        stage,
        work_id,
    ):
        raise KnowledgeError(
            "TARGET_NOT_ALLOWED",
            f"candidate target is outside the stage-approved roots: {relative}",
            exit_code=3,
        )
    lexical = repo / Path(*relative.split("/"))
    if _redirected(lexical, repo):
        raise KnowledgeError("TARGET_REDIRECTED", f"target is redirected: {relative}", exit_code=3)
    if lexical.exists() and lexical.stat().st_nlink > 1:
        raise KnowledgeError("TARGET_HARDLINKED", f"target has multiple hard links: {relative}", exit_code=3)
    return relative, lexical


def _read_postimage(candidate_path: Path, operation: dict[str, Any]) -> bytes:
    relative = normalized_path(str(operation.get("postimage_ref", "")))
    root = candidate_path.parent
    path = candidate_path.parent / Path(*relative.split("/"))
    try:
        path.relative_to(root)
        registry_root = candidate_path.parents[4]
    except (IndexError, ValueError) as exc:
        raise KnowledgeError("POSTIMAGE_REF_INVALID", "postimage escapes candidate", exit_code=3) from exc
    raw = knowledge_governance._stable_registry_read(
        registry_root,
        path,
        missing_code="POSTIMAGE_MISSING",
        invalid_code="POSTIMAGE_DRIFT",
        label="sealed postimage",
    )
    if sha256_bytes(raw) != operation.get("postimage_sha256"):
        raise KnowledgeError("POSTIMAGE_DRIFT", "sealed postimage hash drifted", exit_code=3)
    return raw


def _scan_secrets(raw: bytes, known_secret_values: Iterable[str], label: str) -> None:
    text = raw.decode("utf-8", errors="replace")
    if SECRET_RE.search(text) or any(value and value in text for value in known_secret_values):
        raise KnowledgeError(
            "SECRET_DETECTED",
            f"secret-like material was found in {label}",
            exit_code=3,
        )


def _write_json(path: Path, value: Any, *, create_only: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        with open(temporary, "xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if create_only:
            knowledge_governance._rename_path_create_only(
                temporary,
                path,
                unsafe_code="UNSAFE_PROMOTION",
                unsupported_message="atomic create-only promotion metadata is unsupported",
                filesystem_message="filesystem lacks atomic create-only promotion metadata",
            )
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_bytes(path: Path, value: bytes, *, create_only: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary, "xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if create_only:
            knowledge_governance._rename_path_create_only(
                temporary,
                path,
                unsafe_code="UNSAFE_PROMOTION",
                unsupported_message="atomic create-only promotion data is unsupported",
                filesystem_message="filesystem lacks atomic create-only promotion data",
            )
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _ready_promotions(repo: Path) -> list[dict[str, Any]]:
    eligible = _eligible_paths(repo)
    root = repo / "docs" / "knowledge" / "meta" / "promotions"
    promotions: list[dict[str, Any]] = []
    if not root.is_dir():
        return promotions
    for path in sorted(root.glob("*.json"), key=lambda item: item.as_posix().encode("utf-8")):
        relative = path.relative_to(repo).as_posix()
        if relative not in eligible or path.is_symlink():
            continue
        promotion = _strict_object(path.read_bytes(), "knowledge promotion receipt")
        if promotion.get("schema") != "knowledge-promotion/v1" or promotion.get("status") != "Ready":
            raise KnowledgeError(
                "PROMOTION_RECEIPT_INVALID",
                f"existing promotion receipt is invalid: {relative}",
                exit_code=3,
            )
        promotions.append(promotion)
    return promotions


def _unresolved_journals(repo_root: Path) -> list[Path]:
    journals = repo_root / "journals"
    if not journals.is_dir():
        return []
    unresolved: list[Path] = []
    for path in journals.glob("*/journal.json"):
        try:
            value = _strict_object(path.read_bytes(), "promotion journal")
        except KnowledgeError:
            unresolved.append(path)
            continue
        if value.get("status") == "in_progress":
            unresolved.append(path)
    return sorted(unresolved, key=lambda path: path.as_posix().encode("utf-8"))


def _lock_pid(lock_path: Path) -> int:
    try:
        text = lock_path.read_text(encoding="ascii").strip()
        match = re.fullmatch(r"pid=([1-9][0-9]*)", text)
    except (OSError, UnicodeError):
        match = None
    if match is None:
        raise KnowledgeError(
            "PROMOTION_LOCK_INVALID",
            "promotion lock does not contain a valid owner PID",
            exit_code=5,
            recoverable=False,
        )
    return int(match.group(1))


def _pid_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _raise_for_existing_lock(lock_path: Path) -> None:
    pid = _lock_pid(lock_path)
    if _pid_is_alive(pid):
        raise KnowledgeError(
            "PROMOTION_LOCKED",
            "another live promotion process owns the repository lock",
            exit_code=3,
            evidence_refs=[f"pid:{pid}"],
        )
    raise KnowledgeError(
        "RECOVERY_REQUIRED",
        "a dead promotion process left a stale lock; run recover",
        exit_code=5,
        evidence_refs=[f"pid:{pid}"],
        recoverable=True,
    )


def _check_ignore(repo: Path, relative: str) -> None:
    completed = _run(
        ["git", "check-ignore", "--no-index", "-q", "--", relative],
        cwd=repo,
        accepted={0, 1},
        code="GIT_UNAVAILABLE",
    )
    if completed.returncode == 0:
        raise KnowledgeError(
            "TARGET_IGNORED",
            f"candidate target is ignored by Git: {relative}",
            exit_code=3,
        )


def _validated_operations(
    repo: Path,
    candidate: dict[str, Any],
    candidate_path: Path,
    *,
    known_secret_values: Iterable[str],
) -> list[dict[str, Any]]:
    eligible = _eligible_paths(repo)
    for source in candidate.get("source_snapshot", []):
        _verify_source_ref(repo, source, eligible)
    operations = candidate.get("operations")
    if not isinstance(operations, list):
        raise KnowledgeError("CANDIDATE_INVALID", "candidate operations are invalid", exit_code=2)
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_casefolded: set[str] = set()
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise KnowledgeError("CANDIDATE_INVALID", "candidate operation is not an object", exit_code=2)
        if set(operation) != {
            "kind",
            "path",
            "preimage_sha256",
            "postimage_sha256",
            "postimage_ref",
        }:
            raise KnowledgeError(
                "CANDIDATE_INVALID",
                "candidate operation has unknown or missing fields",
                exit_code=2,
            )
        if operation.get("kind") not in {"create", "update"}:
            raise KnowledgeError("CANDIDATE_INVALID", "candidate operation kind is invalid", exit_code=2)
        relative, target = _target(
            repo,
            str(operation.get("path", "")),
            stage=str(candidate.get("stage", "")),
            work_id=str(candidate.get("work_id", "")),
        )
        if relative in seen:
            raise KnowledgeError("CANDIDATE_INVALID", "candidate target is duplicated", exit_code=2)
        folded = relative.casefold()
        if folded in seen_casefolded:
            raise KnowledgeError(
                "TARGET_CASE_COLLISION",
                "candidate targets collide under case-insensitive path rules",
                exit_code=3,
            )
        seen.add(relative)
        seen_casefolded.add(folded)
        _check_ignore(repo, relative)
        current = target.read_bytes() if target.is_file() else None
        expected = operation.get("preimage_sha256")
        if operation["kind"] == "create":
            if expected is not None or current is not None:
                raise KnowledgeError(
                    "PREIMAGE_DRIFT",
                    f"create target appeared after Candidate sealing: {relative}",
                    exit_code=3,
                    evidence_refs=[relative],
                    recoverable=True,
                )
        elif current is None or sha256_bytes(current) != expected:
            raise KnowledgeError(
                "PREIMAGE_DRIFT",
                f"update preimage drifted after Candidate sealing: {relative}",
                exit_code=3,
                evidence_refs=[relative],
                recoverable=True,
            )
        postimage = _read_postimage(candidate_path, operation)
        _scan_secrets(postimage, known_secret_values, relative)
        validated.append(
            {
                "index": index,
                "kind": operation["kind"],
                "relative": relative,
                "target": target,
                "preimage": current,
                "postimage": postimage,
                "postimage_sha256": sha256_bytes(postimage),
            }
        )
    return validated


def _assert_validated_preimages_current(
    repo: Path,
    candidate: dict[str, Any],
    operations: Iterable[dict[str, Any]],
) -> None:
    """Fail before journaling if target bytes changed after operation validation."""

    for item in operations:
        relative, target = _target(
            repo,
            item["relative"],
            stage=str(candidate.get("stage", "")),
            work_id=str(candidate.get("work_id", "")),
        )
        expected = item["preimage"]
        current = target.read_bytes() if target.is_file() else None
        if expected is None:
            drifted = target.exists()
        else:
            drifted = current != expected
        if drifted:
            raise KnowledgeError(
                "PREIMAGE_DRIFT",
                f"target changed during apply validation: {relative}",
                exit_code=3,
                evidence_refs=[relative],
                recoverable=True,
            )


def _assert_operation_preimage_current(
    repo: Path,
    candidate: dict[str, Any],
    item: dict[str, Any],
) -> None:
    """Recheck one target immediately before its atomic replacement."""

    relative, target = _target(
        repo,
        item["relative"],
        stage=str(candidate.get("stage", "")),
        work_id=str(candidate.get("work_id", "")),
    )
    expected = item["preimage"]
    current = target.read_bytes() if target.is_file() else None
    drifted = target.exists() if expected is None else current != expected
    if drifted:
        raise KnowledgeError(
            "PREIMAGE_DRIFT",
            f"target changed at the commit boundary: {relative}",
            exit_code=3,
            evidence_refs=[relative],
            recoverable=True,
        )


def _validate_stage_semantics(
    stage: str,
    work_id: str,
    operations: Iterable[dict[str, Any]],
    *,
    decision: str,
) -> None:
    if decision not in {"change", "no-change"}:
        raise KnowledgeError(
            "DRAFT_CONTRACT_INVALID",
            "Candidate decision must be change or no-change",
            exit_code=2,
        )
    expected_class = {"requirements": "required", "planning": "planned"}.get(stage)
    operation_list = list(operations)
    sidecars = [
        item
        for item in operation_list
        if item["relative"].startswith("docs/knowledge/meta/pages/")
        and item["relative"].endswith(".json")
    ]
    for item in sidecars:
        page = _strict_object(
            item["postimage"],
            f"knowledge page sidecar {item['relative']}",
        )
        contract_errors = knowledge_governance.knowledge_page_contract_errors(page)
        if contract_errors:
            raise KnowledgeError(
                "PAGE_CONTRACT_INVALID",
                f"knowledge page sidecar violates the closed contract: {item['relative']}",
                exit_code=2,
                evidence_refs=[item["relative"], *contract_errors[:3]],
            )
    formal = [item for item in operation_list if not item["relative"].startswith("docs/knowledge/")]
    content_operations = [
        item
        for item in operation_list
        if item["relative"] != "docs/knowledge/log.md"
        and not item["relative"].startswith("docs/knowledge/meta/promotions/")
    ]
    if expected_class is None:
        if formal:
            raise KnowledgeError(
                "TARGET_NOT_ALLOWED",
                "this stage cannot co-promote formal artifacts",
                exit_code=3,
            )
        if decision == "no-change" and content_operations:
            raise KnowledgeError(
                "NO_CHANGE_INVALID",
                "a no-change Candidate cannot contain knowledge content operations",
                exit_code=2,
            )
        if (
            decision == "change"
            and not content_operations
            and stage != "lint-repair"
        ):
            raise KnowledgeError(
                "KNOWLEDGE_DIFF_MISSING",
                "a change Candidate must contain knowledge content operations",
                exit_code=2,
            )
        return
    if not formal:
        raise KnowledgeError(
            "FORMAL_ARTIFACT_MISSING",
            f"{stage} Candidate must include the current Work ID formal artifact",
            exit_code=2,
        )
    for item in formal:
        if item["kind"] != "create" or not _formal_target_allowed(
            item["relative"],
            stage,
            work_id,
        ):
            raise KnowledgeError(
                "FORMAL_TARGET_INVALID",
                f"{stage} formal operations must be create-only and Work-ID confined",
                exit_code=3,
            )
    if decision == "no-change":
        knowledge_content = [
            item
            for item in content_operations
            if item["relative"].startswith("docs/knowledge/")
        ]
        if knowledge_content:
            raise KnowledgeError(
                "NO_CHANGE_INVALID",
                f"{stage} no-change Candidate cannot alter canonical knowledge content",
                exit_code=2,
            )
        return
    if not sidecars:
        raise KnowledgeError(
            "KNOWLEDGE_DIFF_MISSING",
            f"{stage} Candidate must contain a page sidecar or an explicit no-change decision",
            exit_code=2,
        )
    for item in sidecars:
        try:
            page = json.loads(item["postimage"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeError(
                "PAGE_CONTRACT_INVALID",
                "stage Candidate sidecar is not UTF-8 JSON",
                exit_code=2,
            ) from exc
        claims = page.get("claims") if isinstance(page, dict) else None
        if not isinstance(claims, list) or not claims:
            raise KnowledgeError(
                "PAGE_CONTRACT_INVALID",
                "stage Candidate sidecar has no claims",
                exit_code=2,
            )
        if any(
            not isinstance(claim, dict) or claim.get("evidence_class") != expected_class
            for claim in claims
        ):
            raise KnowledgeError(
                "EVIDENCE_CLASS_MISMATCH",
                f"{stage} knowledge claims must use evidence_class {expected_class}",
                exit_code=3,
            )


def seal_candidate_draft(
    repo_value: str,
    *,
    draft: dict[str, Any],
    approval_actor: str,
    approval_evidence: str,
    known_secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate untrusted full-postimage input and persist an immutable Candidate."""

    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    if not isinstance(draft, dict) or set(draft) != {
        "schema",
        "stage",
        "work_id",
        "decision",
        "source_snapshot",
        "operations",
    }:
        raise KnowledgeError(
            "DRAFT_CONTRACT_INVALID",
            "candidate draft has unknown or missing fields",
            exit_code=2,
        )
    if draft.get("schema") != "knowledge-candidate-draft/v1":
        raise KnowledgeError(
            "DRAFT_CONTRACT_INVALID",
            "candidate draft schema is invalid",
            exit_code=2,
        )
    stage = draft.get("stage")
    work_id = draft.get("work_id")
    decision = draft.get("decision")
    if (
        stage not in ALLOWED_DRAFT_STAGES
        or not isinstance(work_id, str)
        or not work_id.strip()
        or decision not in {"change", "no-change"}
    ):
        raise KnowledgeError(
            "DRAFT_CONTRACT_INVALID",
            "candidate stage, work_id, or decision is invalid",
            exit_code=2,
        )
    if (
        not isinstance(approval_actor, str)
        or not approval_actor.strip()
        or not isinstance(approval_evidence, str)
        or not approval_evidence.strip()
    ):
        raise KnowledgeError(
            "APPROVAL_BINDING_INVALID",
            "Candidate sealing requires the exact prospective approval binding",
            exit_code=2,
        )

    repo_id, repo_root = _repo_registry(repo)
    unresolved = _unresolved_journals(repo_root)
    if unresolved:
        raise KnowledgeError(
            "RECOVERY_REQUIRED",
            "an interrupted promotion must be recovered before sealing another Candidate",
            exit_code=5,
            evidence_refs=[path.relative_to(repo_root).as_posix() for path in unresolved],
            recoverable=True,
        )
    lock_path = repo_root / "promotion.lock"
    if lock_path.exists():
        _raise_for_existing_lock(lock_path)
    eligible = _eligible_paths(repo)
    sources = draft.get("source_snapshot")
    if not isinstance(sources, list):
        raise KnowledgeError("DRAFT_CONTRACT_INVALID", "source_snapshot must be an array", exit_code=2)
    source_snapshot: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            raise KnowledgeError("DRAFT_CONTRACT_INVALID", "source ref must be an object", exit_code=2)
        _verify_source_ref(repo, source, eligible)
        source_snapshot.append(copy.deepcopy(source))

    draft_operations = draft.get("operations")
    if not isinstance(draft_operations, list):
        raise KnowledgeError("DRAFT_CONTRACT_INVALID", "operations must be an array", exit_code=2)
    operations: list[dict[str, Any]] = []
    postimages: list[tuple[str, bytes]] = []
    affected_paths: list[str] = []
    displayed_postimages: list[dict[str, str]] = []
    seen: set[str] = set()
    seen_casefolded: set[str] = set()
    for index, operation in enumerate(draft_operations, 1):
        if not isinstance(operation, dict) or set(operation) != {"kind", "path", "postimage"}:
            raise KnowledgeError(
                "DRAFT_CONTRACT_INVALID",
                "draft operation has unknown or missing fields",
                exit_code=2,
            )
        kind = operation.get("kind")
        postimage_text = operation.get("postimage")
        if kind not in {"create", "update"} or not isinstance(postimage_text, str):
            raise KnowledgeError(
                "DRAFT_CONTRACT_INVALID",
                "draft operation kind or postimage is invalid",
                exit_code=2,
            )
        relative, target = _target(
            repo,
            str(operation.get("path", "")),
            stage=stage,
            work_id=work_id,
        )
        if relative == "docs/knowledge/log.md" or relative.startswith(
            "docs/knowledge/meta/promotions/"
        ):
            raise KnowledgeError(
                "FINALIZER_RESERVED",
                "promotion log and Ready receipt are generated sealed finalizers",
                exit_code=3,
            )
        if not relative.startswith("docs/knowledge/") and kind != "create":
            raise KnowledgeError(
                "FORMAL_UPDATE_FORBIDDEN",
                "requirements and planning formal artifacts are create-only",
                exit_code=3,
            )
        folded = relative.casefold()
        if relative in seen:
            raise KnowledgeError("DRAFT_CONTRACT_INVALID", "draft target is duplicated", exit_code=2)
        if folded in seen_casefolded:
            raise KnowledgeError(
                "TARGET_CASE_COLLISION",
                "draft targets collide under case-insensitive path rules",
                exit_code=3,
            )
        seen.add(relative)
        seen_casefolded.add(folded)
        _check_ignore(repo, relative)
        current = target.read_bytes() if target.is_file() else None
        if kind == "create" and current is not None:
            raise KnowledgeError(
                "DRAFT_PREIMAGE_INVALID",
                f"create target already exists: {relative}",
                exit_code=2,
            )
        if kind == "update" and current is None:
            raise KnowledgeError(
                "DRAFT_PREIMAGE_INVALID",
                f"update target does not exist: {relative}",
                exit_code=2,
            )
        postimage = postimage_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        _scan_secrets(postimage, known_secret_values, relative)
        suffix = Path(relative).suffix or ".txt"
        postimage_ref = f"postimages/{index:04d}{suffix}"
        operations.append(
            {
                "kind": kind,
                "path": relative,
                "preimage_sha256": sha256_bytes(current) if current is not None else None,
                "postimage_sha256": sha256_bytes(postimage),
                "postimage_ref": postimage_ref,
            }
        )
        postimages.append((postimage_ref, postimage))
        affected_paths.append(relative)
        displayed_postimages.append(
            {
                "path": relative,
                "postimage_sha256": sha256_bytes(postimage),
                "postimage": postimage.decode("utf-8"),
            }
        )

    _validate_stage_semantics(
        stage,
        work_id,
        [
            {
                "kind": operation["kind"],
                "relative": operation["path"],
                "postimage": postimage,
            }
            for operation, (_, postimage) in zip(operations, postimages)
        ],
        decision=str(decision),
    )
    formal_paths = sorted(
        (
            operation["path"]
            for operation in operations
            if not operation["path"].startswith("docs/knowledge/")
        ),
        key=lambda value: value.encode("utf-8"),
    )

    seed = {
        "repo_id": repo_id,
        "stage": stage,
        "work_id": work_id,
        "decision": decision,
        "approval": {
            "actor": approval_actor,
            "evidence": approval_evidence,
        },
        "source_snapshot": source_snapshot,
        "operations": operations,
    }
    promotion_id = f"promotion-{stage}-{knowledge_governance.canonical_sha256(seed)[:16]}"
    candidate_ref = f"knowledge:candidates/{promotion_id}/candidate.json"
    receipt_relative = f"docs/knowledge/meta/promotions/{promotion_id}.json"
    log_relative = "docs/knowledge/log.md"
    for relative in (log_relative, receipt_relative):
        _check_ignore(repo, relative)
    _, log_path = _target(repo, log_relative)
    _, receipt_path = _target(repo, receipt_relative)
    log_preimage = log_path.read_bytes() if log_path.is_file() else None
    if receipt_path.exists():
        raise KnowledgeError(
            "PROMOTION_EXISTS",
            "Ready promotion receipt already exists",
            exit_code=3,
        )

    log_ref = f"postimages/{len(operations) + 1:04d}.md"
    receipt_ref = f"postimages/{len(operations) + 2:04d}.json"
    operations.extend(
        [
            {
                "kind": "update" if log_preimage is not None else "create",
                "path": log_relative,
                "preimage_sha256": (
                    sha256_bytes(log_preimage) if log_preimage is not None else None
                ),
                "postimage_sha256": FINALIZER_HASH_SENTINEL,
                "postimage_ref": log_ref,
            },
            {
                "kind": "create",
                "path": receipt_relative,
                "preimage_sha256": None,
                "postimage_sha256": FINALIZER_HASH_SENTINEL,
                "postimage_ref": receipt_ref,
            },
        ]
    )
    candidate = {
        "schema": "knowledge-candidate/v1",
        "promotion_id": promotion_id,
        "stage": stage,
        "work_id": work_id,
        "decision": decision,
        "approval": {
            "actor": approval_actor,
            "evidence": approval_evidence,
        },
        "source_snapshot": source_snapshot,
        "operations": operations,
        "payload_sha256": "",
        "status": "Candidate",
    }
    candidate["payload_sha256"] = _candidate_payload_sha256(candidate)
    promotion = {
        "schema": "knowledge-promotion/v1",
        "promotion_id": promotion_id,
        "stage": stage,
        "work_id": work_id,
        "candidate_ref": candidate_ref,
        "payload_sha256": candidate["payload_sha256"],
        "decision": decision,
        "formal_paths": formal_paths,
        "approval": copy.deepcopy(candidate["approval"]),
        "lint": {"required_outcome": "passed"},
        "status": "Ready",
    }
    receipt_postimage = _json_bytes(promotion)
    log_postimage = knowledge_governance.render_promotion_log(
        [*_ready_promotions(repo), promotion]
    )
    operations[-2]["postimage_sha256"] = sha256_bytes(log_postimage)
    operations[-1]["postimage_sha256"] = sha256_bytes(receipt_postimage)
    if candidate["payload_sha256"] != _candidate_payload_sha256(candidate):
        raise KnowledgeError(
            "CANDIDATE_DIGEST_DRIFT",
            "deterministic finalizers changed the Candidate digest",
            exit_code=3,
        )
    for relative, value in (
        (log_relative, log_postimage),
        (receipt_relative, receipt_postimage),
    ):
        _scan_secrets(value, known_secret_values, relative)
    postimages.extend([(log_ref, log_postimage), (receipt_ref, receipt_postimage)])
    affected_paths.extend([log_relative, receipt_relative])
    displayed_postimages.extend(
        [
            {
                "path": log_relative,
                "postimage_sha256": sha256_bytes(log_postimage),
                "postimage": log_postimage.decode("utf-8"),
            },
            {
                "path": receipt_relative,
                "postimage_sha256": sha256_bytes(receipt_postimage),
                "postimage": receipt_postimage.decode("utf-8"),
            },
        ]
    )
    candidate_ref = knowledge_governance._persist_candidate(
        registry_root=knowledge_governance.default_registry_root(),
        repo_id=repo_id,
        candidate=candidate,
        postimages=postimages,
    )
    return {
        "schema": "knowledge-candidate-seal/v1",
        "repo_id": repo_id,
        "promotion_id": promotion_id,
        "stage": stage,
        "work_id": work_id,
        "candidate_ref": candidate_ref,
        "payload_sha256": candidate["payload_sha256"],
        "affected_paths": affected_paths,
        "postimages": displayed_postimages,
        "approval": copy.deepcopy(candidate["approval"]),
        "decision": decision,
        "status": "Candidate",
    }


def seal_candidate_file(
    repo_value: str,
    *,
    draft_path: str,
    approval_actor: str,
    approval_evidence: str,
    known_secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    path = Path(draft_path).resolve()
    if path.is_symlink() or not path.is_file():
        raise KnowledgeError("DRAFT_MISSING", "candidate draft file is missing or redirected", exit_code=2)
    draft = _strict_object(path.read_bytes(), "candidate draft")
    return seal_candidate_draft(
        repo_value,
        draft=draft,
        approval_actor=approval_actor,
        approval_evidence=approval_evidence,
        known_secret_values=known_secret_values,
    )


def _validated_finalizers(
    repo: Path,
    candidate: dict[str, Any],
    candidate_path: Path,
) -> dict[str, Any]:
    promotion_id = str(candidate.get("promotion_id", ""))
    candidate_ref = f"knowledge:candidates/{promotion_id}/candidate.json"
    log_relative = "docs/knowledge/log.md"
    receipt_relative = f"docs/knowledge/meta/promotions/{promotion_id}.json"
    operations = candidate.get("operations", [])
    log_operations = [
        operation
        for operation in operations
        if isinstance(operation, dict) and operation.get("path") == log_relative
    ]
    receipt_operations = [
        operation
        for operation in operations
        if isinstance(operation, dict) and operation.get("path") == receipt_relative
    ]
    if len(log_operations) != 1 or len(receipt_operations) != 1:
        raise KnowledgeError(
            "CANDIDATE_FINALIZER_INVALID",
            "Candidate must seal exactly one promotion log and one Ready receipt",
            exit_code=3,
        )
    approval = candidate.get("approval")
    if (
        not isinstance(approval, dict)
        or set(approval) != {"actor", "evidence"}
        or not all(isinstance(value, str) and value for value in approval.values())
        or candidate.get("decision") not in {"change", "no-change"}
    ):
        raise KnowledgeError(
            "CANDIDATE_FINALIZER_INVALID",
            "Candidate approval or decision binding is invalid",
            exit_code=3,
        )
    expected_promotion = {
        "schema": "knowledge-promotion/v1",
        "promotion_id": promotion_id,
        "stage": candidate.get("stage"),
        "work_id": candidate.get("work_id"),
        "candidate_ref": candidate_ref,
        "payload_sha256": candidate.get("payload_sha256"),
        "decision": candidate.get("decision"),
        "formal_paths": sorted(
            (
                str(operation.get("path"))
                for operation in operations
                if isinstance(operation, dict)
                and not str(operation.get("path", "")).startswith("docs/knowledge/")
            ),
            key=lambda value: value.encode("utf-8"),
        ),
        "approval": copy.deepcopy(approval),
        "lint": {"required_outcome": "passed"},
        "status": "Ready",
    }
    receipt_postimage = _read_postimage(candidate_path, receipt_operations[0])
    if receipt_postimage != _json_bytes(expected_promotion):
        raise KnowledgeError(
            "CANDIDATE_FINALIZER_INVALID",
            "sealed Ready receipt is not the deterministic Candidate projection",
            exit_code=3,
        )
    log_postimage = _read_postimage(candidate_path, log_operations[0])
    expected_log = knowledge_governance.render_promotion_log(
        [*_ready_promotions(repo), expected_promotion]
    )
    if log_postimage != expected_log:
        raise KnowledgeError(
            "CANDIDATE_FINALIZER_DRIFT",
            "sealed promotion log no longer matches current Ready receipts",
            exit_code=3,
            recoverable=True,
        )
    return expected_promotion


def _rename_create_only(source: Path, destination: Path) -> None:
    knowledge_governance._rename_path_create_only(
        source,
        destination,
        unsafe_code="UNSAFE_PROMOTION",
        unsupported_message="atomic promotion ownership transfer is unsupported",
        filesystem_message="filesystem lacks atomic promotion ownership transfer",
    )


def _restore_retired_path(retired: Path, target: Path) -> bool:
    try:
        _rename_create_only(retired, target)
    except FileExistsError:
        return False
    return True


def _raise_commit_preimage_drift(relative: str) -> None:
    raise KnowledgeError(
        "PREIMAGE_DRIFT",
        f"target changed at the atomic commit boundary: {relative}",
        exit_code=3,
        evidence_refs=[relative],
        recoverable=True,
    )


def _restore_commit_boundary_retirement(
    retired: Path,
    target: Path,
    relative: str,
    cause: BaseException,
) -> None:
    if _restore_retired_path(retired, target):
        return
    raise KnowledgeError(
        "RECOVERY_REQUIRED",
        "update preimage retirement could not be restored; run recover",
        exit_code=5,
        evidence_refs=[relative],
        recoverable=True,
    ) from cause


def _publish_operation_at_commit_boundary(
    item: dict[str, Any],
    temporary: Path,
    journal_dir: Path,
) -> None:
    target = item["target"]
    relative = item["relative"]
    expected = item["preimage"]
    if expected is None:
        try:
            _rename_create_only(temporary, target)
        except FileExistsError:
            _raise_commit_preimage_drift(relative)
        return

    retired = (
        journal_dir
        / "commit-boundary"
        / f"{item['index']:04d}.{uuid.uuid4().hex}.preimage"
    )
    retired.parent.mkdir(parents=True, exist_ok=True)
    try:
        _rename_create_only(target, retired)
    except FileNotFoundError:
        _raise_commit_preimage_drift(relative)

    try:
        captured = retired.read_bytes()
    except BaseException as exc:
        _restore_commit_boundary_retirement(retired, target, relative, exc)
        raise
    if captured != expected:
        drift = KnowledgeError(
            "PREIMAGE_DRIFT",
            f"target changed at the atomic commit boundary: {relative}",
            exit_code=3,
            evidence_refs=[relative],
            recoverable=True,
        )
        _restore_commit_boundary_retirement(retired, target, relative, drift)
        _raise_commit_preimage_drift(relative)
    try:
        _rename_create_only(temporary, target)
    except FileExistsError as exc:
        _restore_commit_boundary_retirement(retired, target, relative, exc)
        _raise_commit_preimage_drift(relative)
    except BaseException as exc:
        _restore_commit_boundary_retirement(retired, target, relative, exc)
        raise
    retired.unlink(missing_ok=True)


def _write_preimage_create_only(target: Path, preimage: bytes) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.rollback.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary, "xb") as stream:
            stream.write(preimage)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            _rename_create_only(temporary, target)
        except FileExistsError:
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _rollback(
    operations: list[dict[str, Any]],
    *,
    receipt_path: Path,
    staged: list[Path],
) -> None:
    for temporary in staged:
        temporary.unlink(missing_ok=True)
    conflicts: list[str] = []
    for item in reversed(operations):
        target = item["target"]
        preimage = item["preimage"]
        postimage_sha256 = item.get("postimage_sha256")
        if not isinstance(postimage_sha256, str):
            postimage_sha256 = sha256_bytes(item["postimage"])
        retired = target.parent / (
            f".{target.name}.rollback-current.{uuid.uuid4().hex}.tmp"
        )
        try:
            _rename_create_only(target, retired)
        except FileNotFoundError:
            retired = None

        if retired is None:
            if preimage is not None and not _write_preimage_create_only(target, preimage):
                conflicts.append(item["relative"])
            continue

        current = retired.read_bytes() if retired.is_file() else None
        current_sha256 = sha256_bytes(current) if current is not None else None
        if preimage is None:
            if current_sha256 == postimage_sha256:
                retired.unlink(missing_ok=True)
            else:
                _restore_retired_path(retired, target)
                conflicts.append(item["relative"])
            continue

        preimage_sha256 = sha256_bytes(preimage)
        if current_sha256 == preimage_sha256:
            if not _restore_retired_path(retired, target):
                conflicts.append(item["relative"])
            continue
        if current_sha256 != postimage_sha256:
            _restore_retired_path(retired, target)
            conflicts.append(item["relative"])
            continue
        if _write_preimage_create_only(target, preimage):
            retired.unlink(missing_ok=True)
        else:
            retired.unlink(missing_ok=True)
            conflicts.append(item["relative"])
    if conflicts:
        raise KnowledgeError(
            "ROLLBACK_CONFLICT",
            "rollback preserved targets changed independently after promotion writes",
            exit_code=5,
            evidence_refs=sorted(conflicts, key=lambda value: value.encode("utf-8")),
            recoverable=False,
        )


def apply_candidate(
    repo_value: str,
    *,
    candidate_ref: str,
    approval_actor: str,
    approval_evidence: str,
    known_secret_values: Iterable[str] = (),
    fault_at: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    if (
        not isinstance(approval_actor, str)
        or not approval_actor.strip()
        or not isinstance(approval_evidence, str)
        or not approval_evidence.strip()
    ):
        raise KnowledgeError("APPROVAL_MISSING", "approval actor and evidence are required", exit_code=2)
    repo_id, repo_root = _repo_registry(repo)
    unresolved = _unresolved_journals(repo_root)
    if unresolved:
        raise KnowledgeError(
            "RECOVERY_REQUIRED",
            "an interrupted promotion must be recovered first",
            exit_code=5,
            evidence_refs=[path.relative_to(repo_root).as_posix() for path in unresolved],
            recoverable=True,
        )
    candidate, candidate_path = _load_candidate(repo_root, candidate_ref)
    if candidate.get("approval") != {
        "actor": approval_actor,
        "evidence": approval_evidence,
    }:
        raise KnowledgeError(
            "APPROVAL_BINDING_DRIFT",
            "apply approval differs from the exact binding shown in the sealed Candidate",
            exit_code=3,
        )
    promotion = _validated_finalizers(repo, candidate, candidate_path)
    operations = _validated_operations(
        repo,
        candidate,
        candidate_path,
        known_secret_values=tuple(known_secret_values),
    )
    _validate_stage_semantics(
        str(candidate.get("stage", "")),
        str(candidate.get("work_id", "")),
        operations,
        decision=str(candidate.get("decision", "")),
    )
    promotion_id = candidate["promotion_id"]
    receipt_relative = f"docs/knowledge/meta/promotions/{promotion_id}.json"
    _, receipt_path = _target(repo, receipt_relative)
    if receipt_path.exists():
        raise KnowledgeError("PROMOTION_EXISTS", "Ready promotion receipt already exists", exit_code=3)

    repo_root.mkdir(parents=True, exist_ok=True)
    lock_path = repo_root / "promotion.lock"
    try:
        lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            _raise_for_existing_lock(lock_path)
        except KnowledgeError as lock_error:
            raise lock_error from exc
        raise AssertionError("existing lock classification unexpectedly returned") from exc
    journal_dir = repo_root / "journals" / f"{promotion_id}-{uuid.uuid4().hex[:12]}"
    staged: list[Path] = []
    applied: list[dict[str, Any]] = []
    created_parents: list[Path] = []
    crashed = False
    transaction_started = False
    journal = {
        "schema": "knowledge-journal/v1",
        "promotion_id": promotion_id,
        "candidate_ref": candidate_ref,
        "stage": candidate["stage"],
        "work_id": candidate["work_id"],
        "status": "in_progress",
        "operations": [
            {
                "kind": item["kind"],
                "path": item["relative"],
                "preimage_sha256": (
                    sha256_bytes(item["preimage"]) if item["preimage"] is not None else None
                ),
                "postimage_sha256": sha256_bytes(item["postimage"]),
                "backup_ref": (
                    f"backups/{item['index']:04d}.bin"
                    if item["preimage"] is not None
                    else None
                ),
            }
            for item in operations
        ],
    }
    try:
        os.write(lock_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_descriptor)
        os.close(lock_descriptor)
        lock_descriptor = -1
        unresolved_after_lock = _unresolved_journals(repo_root)
        if unresolved_after_lock:
            raise KnowledgeError(
                "RECOVERY_REQUIRED",
                "an interrupted promotion appeared before lock acquisition completed",
                exit_code=5,
                evidence_refs=[
                    path.relative_to(repo_root).as_posix()
                    for path in unresolved_after_lock
                ],
                recoverable=True,
            )
        promotion = _validated_finalizers(repo, candidate, candidate_path)
        operations = _validated_operations(
            repo,
            candidate,
            candidate_path,
            known_secret_values=tuple(known_secret_values),
        )
        _validate_stage_semantics(
            str(candidate.get("stage", "")),
            str(candidate.get("work_id", "")),
            operations,
            decision=str(candidate.get("decision", "")),
        )
        if receipt_path.exists():
            raise KnowledgeError("PROMOTION_EXISTS", "Ready promotion receipt already exists", exit_code=3)
        _assert_validated_preimages_current(repo, candidate, operations)
        journal_dir.mkdir(parents=True)
        for item in operations:
            if item["preimage"] is not None:
                backup = journal_dir / "backups" / f"{item['index']:04d}.bin"
                backup.parent.mkdir(parents=True, exist_ok=True)
                with open(backup, "xb") as stream:
                    stream.write(item["preimage"])
                    stream.flush()
                    os.fsync(stream.fileno())
        _write_json(journal_dir / "journal.json", journal, create_only=True)
        transaction_started = True
        if fault_at == "crash-after-journal":
            raise SimulatedCrash()
        for item in operations:
            parent = item["target"].parent
            missing: list[Path] = []
            cursor = parent
            while cursor != repo and not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            parent.mkdir(parents=True, exist_ok=True)
            created_parents.extend(reversed(missing))
            temporary = parent / f".{item['target'].name}.{promotion_id}.tmp"
            with open(temporary, "xb") as stream:
                stream.write(item["postimage"])
                stream.flush()
                os.fsync(stream.fileno())
            staged.append(temporary)
        for item, temporary in zip(operations, staged):
            if fault_at == f"before-replace-{item['index']}":
                raise OSError("injected replace fault")
            _assert_operation_preimage_current(repo, candidate, item)
            _publish_operation_at_commit_boundary(item, temporary, journal_dir)
            applied.append(item)
            if fault_at == "crash-after-log" and item["relative"] == "docs/knowledge/log.md":
                raise SimulatedCrash()
            if fault_at == "crash-after-receipt" and item["relative"] == receipt_relative:
                raise SimulatedCrash()
            if fault_at == f"crash-after-replace-{item['index']}":
                raise SimulatedCrash()
            if fault_at == f"after-replace-{item['index']}":
                raise OSError("injected replace fault")
        if fault_at == "before-lint":
            raise OSError("injected lint fault")
        lint = knowledge_governance.lint_repository(str(repo))
        if lint["outcome"] != "passed":
            raise KnowledgeError(
                "LINT_FAILED",
                "post-apply full lint did not pass",
                exit_code=3,
                recoverable=True,
            )
        if fault_at == "after-lint":
            raise OSError("injected post-lint fault")
        if receipt_path.read_bytes() != _json_bytes(promotion):
            raise KnowledgeError(
                "PROMOTION_DRIFT",
                "applied Ready receipt differs from the sealed Candidate",
                exit_code=3,
                recoverable=True,
            )
        final_lint = knowledge_governance.lint_repository(str(repo))
        if final_lint["outcome"] != "passed":
            raise KnowledgeError(
                "LINT_FAILED",
                "post-receipt full lint did not pass",
                exit_code=3,
                recoverable=True,
            )
        journal["status"] = "committed"
        _write_json(journal_dir / "journal.json", journal)
        _write_json(
            journal_dir / "committed.json",
            {
                "schema": "knowledge-commit/v1",
                "promotion_id": promotion_id,
                "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
            },
            create_only=True,
        )
        return {
            "schema": "knowledge-apply/v1",
            "promotion": promotion,
            "receipt_path": receipt_relative,
            "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
            "post_apply_lint": final_lint,
        }
    except SimulatedCrash:
        crashed = True
        raise
    except BaseException as exc:
        rollback_error: KnowledgeError | None = (
            exc
            if isinstance(exc, KnowledgeError) and exc.code == "RECOVERY_REQUIRED"
            else None
        )
        if transaction_started:
            try:
                _rollback(applied, receipt_path=receipt_path, staged=staged)
            except KnowledgeError as rollback_exc:
                rollback_error = rollback_exc
        else:
            for temporary in staged:
                temporary.unlink(missing_ok=True)
        for directory in reversed(created_parents):
            try:
                directory.rmdir()
            except OSError:
                pass
        if rollback_error is None:
            journal["status"] = "rolled_back"
        if journal_dir.exists():
            _write_json(journal_dir / "journal.json", journal)
        if rollback_error is not None:
            raise rollback_error from exc
        if isinstance(exc, KnowledgeError):
            raise
        raise KnowledgeError(
            "PROMOTION_FAILED",
            str(exc),
            exit_code=3,
            recoverable=True,
        ) from exc
    finally:
        if lock_descriptor >= 0:
            os.close(lock_descriptor)
        if not crashed:
            lock_path.unlink(missing_ok=True)


def _recover_repository_locked(repo_value: str) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    _, repo_root = _repo_registry(repo)
    unresolved = _unresolved_journals(repo_root)
    recovered: list[str] = []
    for journal_path in unresolved:
        journal = _strict_object(journal_path.read_bytes(), "promotion journal")
        if (
            journal.get("schema") != "knowledge-journal/v1"
            or journal.get("status") != "in_progress"
            or not isinstance(journal.get("operations"), list)
        ):
            raise KnowledgeError(
                "JOURNAL_INVALID",
                "unresolved promotion journal is invalid",
                exit_code=5,
                recoverable=False,
            )
        operations: list[dict[str, Any]] = []
        for index, entry in enumerate(journal.get("operations", [])):
            if not isinstance(entry, dict) or set(entry) != {
                "kind",
                "path",
                "preimage_sha256",
                "postimage_sha256",
                "backup_ref",
            }:
                raise KnowledgeError(
                    "JOURNAL_INVALID",
                    "journal operation has unknown or missing fields",
                    exit_code=5,
                )
            relative, target = _target(
                repo,
                entry["path"],
                stage=str(journal.get("stage", "")),
                work_id=str(journal.get("work_id", "")),
            )
            backup_ref = entry.get("backup_ref")
            preimage: bytes | None = None
            if backup_ref:
                normalized_backup = normalized_path(str(backup_ref))
                backup_root = journal_path.parent.resolve()
                backup_path = journal_path.parent / Path(*normalized_backup.split("/"))
                try:
                    backup_path.resolve().relative_to(backup_root)
                except (OSError, ValueError) as exc:
                    raise KnowledgeError(
                        "BACKUP_INVALID",
                        "journal backup escapes its transaction directory",
                        exit_code=5,
                    ) from exc
                if backup_path.is_symlink() or not backup_path.is_file():
                    raise KnowledgeError(
                        "BACKUP_INVALID",
                        "journal backup is missing or redirected",
                        exit_code=5,
                    )
                preimage = backup_path.read_bytes()
                if sha256_bytes(preimage) != entry.get("preimage_sha256"):
                    raise KnowledgeError(
                        "BACKUP_DRIFT",
                        "journal backup hash differs from its sealed preimage",
                        exit_code=5,
                    )
            elif entry.get("preimage_sha256") is not None:
                raise KnowledgeError(
                    "BACKUP_INVALID",
                    "update journal entry has no backup",
                    exit_code=5,
                )
            current = target.read_bytes() if target.is_file() else None
            current_sha = sha256_bytes(current) if current is not None else None
            allowed_states = {entry.get("preimage_sha256"), entry.get("postimage_sha256")}
            if current_sha not in allowed_states:
                raise KnowledgeError(
                    "RECOVERY_CONFLICT",
                    f"target changed independently after interrupted promotion: {relative}",
                    exit_code=5,
                    evidence_refs=[relative],
                    recoverable=False,
                )
            operations.append(
                {
                    "index": index,
                    "kind": entry["kind"],
                    "relative": relative,
                    "target": target,
                    "preimage": preimage,
                    "postimage": b"",
                    "postimage_sha256": entry["postimage_sha256"],
                }
            )
        receipt = (
            repo
            / "docs"
            / "knowledge"
            / "meta"
            / "promotions"
            / f"{journal['promotion_id']}.json"
        )
        journal_paths = {item["relative"] for item in operations}
        if receipt.exists() and receipt.relative_to(repo).as_posix() not in journal_paths:
            raise KnowledgeError(
                "RECOVERY_CONFLICT",
                "an interrupted promotion unexpectedly has a Ready receipt",
                exit_code=5,
                evidence_refs=[receipt.relative_to(repo).as_posix()],
                recoverable=False,
            )
        staged = [
            item["target"].parent
            / f".{item['target'].name}.{journal['promotion_id']}.tmp"
            for item in operations
        ]
        _rollback(operations, receipt_path=receipt, staged=staged)
        journal["status"] = "recovered"
        _write_json(journal_path, journal)
        recovered.append(journal["promotion_id"])
    return {
        "schema": "knowledge-recovery/v1",
        "outcome": "recovered" if recovered else "clean",
        "promotion_ids": recovered,
    }


def recover_repository(repo_value: str) -> dict[str, Any]:
    """Recover journals while holding a live lock that replaces only a dead owner."""

    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    _, repo_root = _repo_registry(repo)
    repo_root.mkdir(parents=True, exist_ok=True)
    recovery_lock = repo_root / "recovery.lock"
    promotion_lock = repo_root / "promotion.lock"
    recovery_descriptor = -1
    owns_promotion_lock = False
    try:
        try:
            recovery_descriptor = os.open(
                recovery_lock,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise KnowledgeError(
                "RECOVERY_LOCKED",
                "another recovery process is active",
                exit_code=5,
            ) from exc
        os.write(recovery_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(recovery_descriptor)
        os.close(recovery_descriptor)
        recovery_descriptor = -1

        if promotion_lock.exists():
            owner = _lock_pid(promotion_lock)
            if _pid_is_alive(owner):
                raise KnowledgeError(
                    "PROMOTION_LOCKED",
                    "cannot recover while the promotion owner is alive",
                    exit_code=5,
                    evidence_refs=[f"pid:{owner}"],
                )
            _write_bytes(
                promotion_lock,
                f"pid={os.getpid()}\n".encode("ascii"),
            )
            owns_promotion_lock = True
        else:
            try:
                descriptor = os.open(
                    promotion_lock,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError as exc:
                raise KnowledgeError(
                    "PROMOTION_LOCKED",
                    "promotion lock appeared while recovery was starting",
                    exit_code=5,
                ) from exc
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(f"pid={os.getpid()}\n".encode("ascii"))
                stream.flush()
                os.fsync(stream.fileno())
            owns_promotion_lock = True
        return _recover_repository_locked(str(repo))
    finally:
        if recovery_descriptor >= 0:
            os.close(recovery_descriptor)
        if owns_promotion_lock:
            try:
                if _lock_pid(promotion_lock) == os.getpid():
                    promotion_lock.unlink(missing_ok=True)
            except KnowledgeError:
                pass
        recovery_lock.unlink(missing_ok=True)
