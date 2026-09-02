"""Bootstrap classification and Wiki governance primitives."""

from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from knowledge_query import (
    KnowledgeError,
    _eligible_paths,
    _metadata_is_redirect,
    _redirected as _path_redirected,
    _run,
    _verify_source_ref,
    normalized_path,
    sha256_bytes,
)


TERMINAL_STATES = {"ready", "approved", "complete", "verified", "partial"}
KNOWLEDGE_LIFECYCLES = {"current", "superseded", "contested", "stale"}
EVIDENCE_CLASSES = {"required", "planned", "observed", "verified", "partial"}
SUPPORT_MARKDOWN = {
    "docs/knowledge/index.md",
    "docs/knowledge/glossary.md",
    "docs/knowledge/log.md",
    "docs/knowledge/bootstrap/catalog.md",
}
CANDIDATE_STATES = {
    "candidate",
    "draft",
    "active",
    "awaiting_user",
    "pending",
    "insufficient-evidence",
}
STATUS_LINE = re.compile(
    r"(?im)^\s*(?:[-*+]\s*)?(?:status|state|verdict|result|(?:文件)?狀態)"
    r"\s*[:：]\s*`?([a-z0-9_-]+)"
)
CONFIRMER_LINE = re.compile(
    r"(?im)^\s*(?:[-*+]\s*)?(?:confirmed\s+by|approver|確認者)\s*[:：]\s*`?([^\s#`]+)"
)
REQUIREMENTS_PATH = re.compile(
    r"^docs/work/([^/]+)/requirements(?:-[2-9][0-9]*)?\.md$"
)
PLAN_BUNDLE_PATH = re.compile(
    r"^(docs/(?:work/[^/]+/plan(?:-[2-9][0-9]*)?|plans/[^/]+))/([^/]+\.(?:md|json))$"
)
_KNOWLEDGE_CONTRACT_RUNTIME: tuple[Any, dict[str, Any]] | None = None


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def default_registry_root() -> Path:
    host_temp = Path(tempfile.gettempdir()).resolve()
    lexical = host_temp / "project-knowledge"
    is_junction = getattr(lexical, "is_junction", lambda: False)
    if lexical.is_symlink() or is_junction():
        raise KnowledgeError(
            "UNSAFE_REGISTRY",
            "project-knowledge registry is redirected",
            exit_code=3,
        )
    resolved = lexical.resolve(strict=False)
    if resolved.parent != host_temp:
        raise KnowledgeError(
            "UNSAFE_REGISTRY",
            "project-knowledge registry is outside host temp",
            exit_code=3,
        )
    return resolved


def repository_id(repo: Path) -> str:
    common = _run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo,
        code="GIT_UNAVAILABLE",
    ).stdout.decode("utf-8", errors="strict").strip()
    canonical = os.path.normcase(str(Path(common).resolve())).replace("\\", "/")
    return sha256_bytes(canonical.encode("utf-8"))


def _registry_path_redirected(registry_root: Path, path: Path) -> bool:
    """Reject a redirected registry root or any redirected lexical component."""

    try:
        path.relative_to(registry_root)
    except ValueError:
        return True
    try:
        root_metadata = registry_root.lstat()
    except FileNotFoundError:
        root_metadata = None
    except OSError:
        return True
    if root_metadata is not None and (
        _metadata_is_redirect(root_metadata)
        or not stat.S_ISDIR(root_metadata.st_mode)
    ):
        return True
    return _path_redirected(path, registry_root)


def _assert_registry_path_safe(registry_root: Path, path: Path) -> None:
    if _registry_path_redirected(registry_root, path):
        raise KnowledgeError(
            "UNSAFE_REGISTRY",
            "project-knowledge registry contains a redirected component",
            exit_code=3,
        )


def _stable_registry_read(
    registry_root: Path,
    path: Path,
    *,
    missing_code: str,
    invalid_code: str,
    label: str,
) -> bytes:
    """Read one regular registry file and prove its identity stayed stable."""

    if _registry_path_redirected(registry_root, path):
        raise KnowledgeError(missing_code, f"{label} is unavailable", exit_code=3)
    try:
        before = path.lstat()
        if _metadata_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            raise OSError(f"{label} is not a regular file")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise KnowledgeError(missing_code, f"{label} is unavailable", exit_code=3) from exc
    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if (
        fingerprint_before != fingerprint_after
        or _metadata_is_redirect(after)
        or _registry_path_redirected(registry_root, path)
    ):
        raise KnowledgeError(
            invalid_code,
            f"{label} changed while it was read",
            exit_code=3,
        )
    return raw


def knowledge_page_contract_errors(page: Any) -> list[str]:
    """Validate the closed knowledge-page schema with the shared dependency-free engine."""

    global _KNOWLEDGE_CONTRACT_RUNTIME
    if _KNOWLEDGE_CONTRACT_RUNTIME is None:
        skills_root = Path(__file__).resolve().parents[2]
        script = skills_root / "technical-planning" / "scripts" / "validate_contracts.py"
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "knowledge-contracts.schema.json"
        )
        spec = importlib.util.spec_from_file_location(
            "knowledge_page_contract_validator",
            script,
        )
        if spec is None or spec.loader is None:
            return ["knowledge-page validator is unavailable"]
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
            return [f"knowledge-page validator cannot load: {exc}"]
        _KNOWLEDGE_CONTRACT_RUNTIME = (module, schema)
    module, schema = _KNOWLEDGE_CONTRACT_RUNTIME
    return module.validate_instance(page, schema, "page")


def _extract_json_state(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("status", "state", "verdict", "result"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate.casefold()
    for key in ("approval", "review"):
        candidate = _extract_json_state(value.get(key))
        if candidate is not None:
            return candidate
    return None


def _artifact_state(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise KnowledgeError(
            "SOURCE_UNREADABLE",
            f"cannot read bootstrap artifact: {path}",
            exit_code=3,
        ) from exc
    if path.suffix.casefold() == ".json":
        try:
            return _extract_json_state(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    match = STATUS_LINE.search(text)
    return match.group(1).casefold() if match else None


def _ready_plan_payload_sha256(handoff: dict[str, Any]) -> str:
    normalized = copy.deepcopy(handoff)
    normalized.get("candidate", {}).pop("payload_sha256", None)
    normalized["approval"] = {
        "status": "Candidate",
        "actor": None,
        "confirmed_at": None,
        "evidence": None,
    }
    for artifact in normalized.get("artifacts", []):
        if isinstance(artifact, dict):
            artifact["approval_status"] = "Candidate"
    return canonical_sha256(normalized)


def _ready_plan_contract_errors(handoff: dict[str, Any]) -> list[str]:
    skills_root = Path(__file__).resolve().parents[2]
    script = skills_root / "technical-planning" / "scripts" / "validate_contracts.py"
    schema_path = skills_root / "technical-planning" / "references" / "ready-plan.schema.json"
    spec = importlib.util.spec_from_file_location("knowledge_ready_plan_validator", script)
    if spec is None or spec.loader is None:
        return ["ready-plan validator is unavailable"]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        return [f"ready-plan validator cannot load: {exc}"]
    errors = module.validate_instance(handoff, schema)
    if not errors:
        errors.extend(module.validate_ready_cross_references(handoff))
    return errors


def _trusted_ready_plan_paths(repo: Path, handoff_relative: str) -> set[str]:
    """Return a verified owner manifest, or an empty set when any binding is weak."""

    handoff_path = repo / Path(*handoff_relative.split("/"))
    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    if (
        not isinstance(handoff, dict)
        or handoff.get("schema") != "ready-plan/v1"
        or _ready_plan_contract_errors(handoff)
    ):
        return set()
    approval = handoff.get("approval")
    candidate = handoff.get("candidate")
    artifacts = handoff.get("artifacts")
    if (
        not isinstance(approval, dict)
        or approval.get("status") != "Ready"
        or not isinstance(approval.get("actor"), str)
        or not approval.get("actor")
        or not isinstance(approval.get("evidence"), str)
        or not approval.get("evidence")
        or not isinstance(candidate, dict)
        or candidate.get("payload_sha256") != _ready_plan_payload_sha256(handoff)
        or not isinstance(artifacts, list)
    ):
        return set()
    try:
        confirmed = datetime.fromisoformat(str(approval.get("confirmed_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return set()
    if confirmed.tzinfo is None:
        return set()
    manifest: set[str] = set()
    primary: dict[str, Any] | None = None
    handoff_entry: dict[str, Any] | None = None
    bundle_root = handoff_relative.rsplit("/", 1)[0] + "/"
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "path",
            "role",
            "approval_status",
            "sha256",
        }:
            return set()
        relative = artifact.get("path")
        if (
            not isinstance(relative, str)
            or not relative.startswith(bundle_root)
            or "\\" in relative
            or any(segment in {"", ".", ".."} for segment in relative.split("/"))
            or artifact.get("approval_status") != "Ready"
            or relative in manifest
        ):
            return set()
        manifest.add(relative)
        if artifact.get("role") == "primary":
            if primary is not None:
                return set()
            primary = artifact
        if artifact.get("role") == "handoff":
            if handoff_entry is not None:
                return set()
            handoff_entry = artifact
        if relative == handoff_relative:
            if artifact.get("role") != "handoff" or artifact.get("sha256") is not None:
                return set()
            continue
        target = repo / Path(*relative.split("/"))
        expected = artifact.get("sha256")
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or target.is_symlink()
            or not target.is_file()
            or sha256_bytes(target.read_bytes()) != expected
        ):
            return set()
    primary_plan = handoff.get("primary_plan")
    if (
        primary is None
        or handoff_entry is None
        or handoff_entry.get("path") != handoff_relative
        or not isinstance(primary_plan, dict)
        or primary_plan != {
            "path": primary.get("path"),
            "sha256": primary.get("sha256"),
        }
    ):
        return set()
    return manifest


def classify_repository(repo: Path) -> dict[str, list[str]]:
    """Classify only owner-recognized terminal artifacts; never trust generic status JSON."""

    eligible = _eligible_paths(repo)
    document_paths = sorted(
        (
            relative
            for relative in eligible
            if relative.startswith("docs/")
            and not relative.startswith("docs/knowledge/")
            and Path(relative).suffix.casefold() in {".md", ".json"}
        ),
        key=lambda value: value.encode("utf-8"),
    )
    states = {
        relative: _artifact_state(repo / Path(*relative.split("/")))
        for relative in document_paths
    }
    result_sets: dict[str, set[str]] = {
        "terminal": set(),
        "candidate": set(),
        "conflict": set(),
        "unknown": set(),
    }
    assigned: set[str] = set()

    for relative in document_paths:
        if REQUIREMENTS_PATH.fullmatch(relative) is None:
            continue
        state = states[relative]
        raw = (repo / Path(*relative.split("/"))).read_text(encoding="utf-8")
        if state in TERMINAL_STATES and CONFIRMER_LINE.search(raw):
            result_sets["terminal"].add(relative)
        elif state in CANDIDATE_STATES:
            result_sets["candidate"].add(relative)
        else:
            result_sets["unknown"].add(relative)
        assigned.add(relative)

    bundles: dict[str, list[str]] = {}
    for relative in document_paths:
        match = PLAN_BUNDLE_PATH.fullmatch(relative)
        if match:
            bundles.setdefault(match.group(1), []).append(relative)
    for bundle_root, paths in bundles.items():
        handoff_relative = f"{bundle_root}/handoff.json"
        machine_state = states.get(handoff_relative)
        human_states = {
            states[path]
            for path in paths
            if path.endswith(".md") and states.get(path) is not None
        }
        if machine_state in TERMINAL_STATES and any(
            state in CANDIDATE_STATES for state in human_states
        ):
            result_sets["conflict"].update(paths)
        elif machine_state in CANDIDATE_STATES:
            result_sets["candidate"].update(paths)
        elif machine_state in TERMINAL_STATES:
            trusted = _trusted_ready_plan_paths(repo, handoff_relative)
            if trusted:
                result_sets["terminal"].update(trusted)
                result_sets["unknown"].update(set(paths) - trusted)
            else:
                result_sets["unknown"].update(paths)
        else:
            explicit_candidates = {
                path for path in paths if states.get(path) in CANDIDATE_STATES
            }
            result_sets["candidate"].update(explicit_candidates)
            result_sets["unknown"].update(set(paths) - explicit_candidates)
        assigned.update(paths)

    stem_groups: dict[str, list[str]] = {}
    for relative in document_paths:
        if relative not in assigned and states.get(relative) is not None:
            stem_groups.setdefault(relative.rsplit(".", 1)[0], []).append(relative)
    for paths in stem_groups.values():
        distinct = {states[path] for path in paths}
        if len(paths) > 1 and len(distinct) > 1:
            result_sets["conflict"].update(paths)
        else:
            result_sets["unknown"].update(paths)
        assigned.update(paths)

    result_sets["unknown"].update(set(document_paths) - assigned)
    return {
        key: sorted(values, key=lambda value: value.encode("utf-8"))
        for key, values in result_sets.items()
    }


def _status_source_ref(repo: Path, relative: str) -> dict[str, Any]:
    raw = (repo / Path(*relative.split("/"))).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    line_number = next(
        (
            index
            for index, line in enumerate(lines, 1)
            if STATUS_LINE.search(line)
        ),
        1,
    )
    excerpt = lines[line_number - 1].encode("utf-8") if lines else b""
    return {
        "path": relative,
        "sha256": sha256_bytes(raw),
        "locator": {"start_line": line_number, "end_line": line_number},
        "excerpt_sha256": sha256_bytes(excerpt),
    }


def _work_id(classification: dict[str, list[str]]) -> str:
    for relative in classification["terminal"]:
        match = re.match(r"docs/work/([^/]+)/", relative)
        if match:
            return match.group(1)
    return "bootstrap"


def _atomic_create(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise KnowledgeError(
            "CANDIDATE_EXISTS",
            f"sealed candidate path already exists: {path.name}",
            exit_code=3,
        ) from exc
    complete = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        complete = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not complete:
            path.unlink(missing_ok=True)


def _rename_path_create_only(
    source: Path,
    destination: Path,
    *,
    unsafe_code: str = "UNSAFE_REGISTRY",
    unsupported_message: str = "atomic create-only publication is unsupported on this platform",
    filesystem_message: str = "filesystem lacks atomic create-only publication",
) -> None:
    """Atomically rename one file or directory without replacing an existing name."""

    if os.name == "nt":
        os.rename(source, destination)
        return
    if not sys.platform.startswith("linux"):
        raise KnowledgeError(
            unsafe_code,
            unsupported_message,
            exit_code=3,
        )
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise KnowledgeError(
            unsafe_code,
            unsupported_message,
            exit_code=3,
        ) from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), os.fspath(destination))
    if error in {errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP}:
        raise KnowledgeError(
            unsafe_code,
            filesystem_message,
            exit_code=3,
        )
    raise OSError(error, os.strerror(error), os.fspath(destination))


def _publish_directory_create_only(source: Path, destination: Path) -> None:
    """Publish a staged Candidate directory with registry-specific fail-closed errors."""

    _rename_path_create_only(
        source,
        destination,
        unsafe_code="UNSAFE_REGISTRY",
        unsupported_message=(
            "Linux renameat2 is required for create-only Candidate publication"
            if sys.platform.startswith("linux")
            else "atomic create-only Candidate publication is unsupported on this platform"
        ),
        filesystem_message="filesystem lacks atomic create-only Candidate publication",
    )


def _persist_candidate(
    *,
    registry_root: Path,
    repo_id: str,
    candidate: dict[str, Any],
    postimages: list[tuple[str, bytes]],
) -> str:
    promotion_id = candidate["promotion_id"]
    candidates_root = registry_root / "repos" / repo_id / "candidates"
    _assert_registry_path_safe(registry_root, candidates_root)
    candidates_root.mkdir(parents=True, exist_ok=True)
    _assert_registry_path_safe(registry_root, candidates_root)
    final = candidates_root / promotion_id
    encoded = (
        json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _assert_registry_path_safe(registry_root, final)
    if final.is_dir():
        existing_candidate = final / "candidate.json"
        expected_postimages = {
            normalized_path(relative): value for relative, value in postimages
        }
        try:
            existing = _stable_registry_read(
                registry_root,
                existing_candidate,
                missing_code="CANDIDATE_EXISTS",
                invalid_code="UNSAFE_REGISTRY",
                label="sealed Candidate",
            )
            matches = existing == encoded
            for relative, value in expected_postimages.items():
                path = final / Path(*relative.split("/"))
                matches = matches and _stable_registry_read(
                    registry_root,
                    path,
                    missing_code="CANDIDATE_EXISTS",
                    invalid_code="UNSAFE_REGISTRY",
                    label="sealed Candidate postimage",
                ) == value
            if matches:
                return f"knowledge:candidates/{promotion_id}/candidate.json"
        except KnowledgeError as exc:
            if exc.code == "UNSAFE_REGISTRY":
                raise
        raise KnowledgeError(
            "CANDIDATE_EXISTS",
            "sealed candidate identifier already exists with different bytes",
            exit_code=3,
        )
    temporary = candidates_root / f".{promotion_id}.{uuid.uuid4().hex}.tmp"
    _assert_registry_path_safe(registry_root, temporary)
    temporary.mkdir()
    _assert_registry_path_safe(registry_root, temporary)
    try:
        for relative, value in postimages:
            destination = temporary / Path(*normalized_path(relative).split("/"))
            _assert_registry_path_safe(registry_root, destination)
            _atomic_create(destination, value)
            _stable_registry_read(
                registry_root,
                destination,
                missing_code="UNSAFE_REGISTRY",
                invalid_code="UNSAFE_REGISTRY",
                label="sealed Candidate postimage",
            )
        candidate_path = temporary / "candidate.json"
        _assert_registry_path_safe(registry_root, candidate_path)
        _atomic_create(candidate_path, encoded)
        _stable_registry_read(
            registry_root,
            candidate_path,
            missing_code="UNSAFE_REGISTRY",
            invalid_code="UNSAFE_REGISTRY",
            label="sealed Candidate",
        )
        _assert_registry_path_safe(registry_root, temporary)
        _assert_registry_path_safe(registry_root, final)
        try:
            _publish_directory_create_only(temporary, final)
        except FileExistsError as exc:
            raise KnowledgeError(
                "CANDIDATE_EXISTS",
                "sealed candidate already exists",
                exit_code=3,
            ) from exc
        _assert_registry_path_safe(registry_root, final)
    finally:
        if temporary.exists() and not _registry_path_redirected(registry_root, temporary):
            for child in sorted(
                temporary.rglob("*"),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            temporary.rmdir()
    return f"knowledge:candidates/{promotion_id}/candidate.json"


def _seal_repair_candidate(
    repo: Path,
    repairs: list[tuple[str, bytes | None, bytes]],
    *,
    approval_actor: str,
    approval_evidence: str,
) -> tuple[str | None, str | None]:
    if not repairs:
        return None, None
    operations: list[dict[str, str]] = []
    repairs_finalizer = False
    for relative, preimage, postimage in repairs:
        if relative == "docs/knowledge/log.md" or relative.startswith(
            "docs/knowledge/meta/promotions/"
        ):
            repairs_finalizer = True
            continue
        try:
            text = postimage.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeError(
                "REPAIR_POSTIMAGE_INVALID",
                f"repair postimage is not UTF-8 text: {relative}",
                exit_code=3,
            ) from exc
        operations.append(
            {
                "kind": "update" if preimage is not None else "create",
                "path": relative,
                "postimage": text,
            }
        )
    if not operations and not repairs_finalizer:
        return None, None
    from knowledge_promotion import seal_candidate_draft

    sealed = seal_candidate_draft(
        str(repo),
        draft={
            "schema": "knowledge-candidate-draft/v1",
            "stage": "lint-repair",
            "work_id": "repair",
            "decision": "change",
            "source_snapshot": [],
            "operations": operations,
        },
        approval_actor=approval_actor,
        approval_evidence=approval_evidence,
    )
    return sealed["candidate_ref"], sealed["payload_sha256"]


def _diagnostic(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def render_index(pages: list[dict[str, Any]]) -> bytes:
    """Build the deterministic, disposable Markdown index from page metadata."""

    rows: list[tuple[str, str, str, str]] = []
    for page in pages:
        content_path = page.get("content_path")
        page_id = page.get("page_id")
        title = page.get("title")
        lifecycle = page.get("lifecycle")
        if not all(isinstance(value, str) and value for value in (content_path, page_id, title, lifecycle)):
            continue
        try:
            content_path = normalized_path(content_path)
        except KnowledgeError:
            continue
        rows.append(
            (
                content_path,
                title.replace("\r", " ").replace("\n", " "),
                page_id,
                lifecycle,
            )
        )
    rows.sort(key=lambda row: (row[0].encode("utf-8"), row[2].encode("utf-8")))
    text = "# Knowledge Index\n\n" + "".join(
        f"- [{title}]({path}) — `{page_id}` — `{lifecycle}`\n"
        for path, title, page_id, lifecycle in rows
    )
    return text.encode("utf-8")


def render_promotion_log(promotions: list[dict[str, Any]]) -> bytes:
    """Build the deterministic promotion log from Ready receipts."""

    rows: list[tuple[str, str, str]] = []
    for promotion in promotions:
        promotion_id = promotion.get("promotion_id")
        candidate_ref = promotion.get("candidate_ref")
        payload_sha256 = promotion.get("payload_sha256")
        if (
            promotion.get("schema") == "knowledge-promotion/v1"
            and promotion.get("status") == "Ready"
            and all(
                isinstance(value, str) and value
                for value in (promotion_id, candidate_ref, payload_sha256)
            )
        ):
            rows.append((promotion_id, candidate_ref, payload_sha256))
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    text = "# Knowledge Promotion Log\n\n" + "".join(
        f"- `{promotion_id}` — `Ready` — `{candidate_ref}` — `{payload_sha256}`\n"
        for promotion_id, candidate_ref, payload_sha256 in rows
    )
    return text.encode("utf-8")


def lint_repository(
    repo_value: str,
    *,
    repair_approval_actor: str | None = None,
    repair_approval_evidence: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    eligible = _eligible_paths(repo)
    meta_root = repo / "docs" / "knowledge" / "meta" / "pages"
    diagnostics: list[dict[str, str]] = []
    repair_pages: dict[str, tuple[bytes, dict[str, Any]]] = {}
    page_records: list[dict[str, Any]] = []
    claims_by_id: dict[str, list[dict[str, Any]]] = {}
    pages_by_id: dict[str, list[dict[str, Any]]] = {}
    content_paths: set[str] = set()
    invalid_pages: set[str] = set()
    invalid_claims: set[tuple[str, int]] = set()

    if meta_root.is_dir():
        for sidecar_path in sorted(
            meta_root.glob("*.json"),
            key=lambda path: path.as_posix().encode("utf-8"),
        ):
            relative = sidecar_path.relative_to(repo).as_posix()
            if relative not in eligible:
                continue
            raw_sidecar = sidecar_path.read_bytes()
            try:
                page = json.loads(raw_sidecar.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                diagnostics.append(
                    _diagnostic("PAGE_JSON_INVALID", relative, "page sidecar is not valid UTF-8 JSON")
                )
                continue
            if not isinstance(page, dict) or page.get("schema") != "knowledge-page/v1":
                diagnostics.append(
                    _diagnostic("PAGE_CONTRACT_INVALID", relative, "page sidecar has an invalid schema")
                )
                continue
            contract_errors = knowledge_page_contract_errors(page)
            if contract_errors:
                diagnostics.append(
                    _diagnostic(
                        "PAGE_CONTRACT_INVALID",
                        relative,
                        "; ".join(contract_errors[:3]),
                    )
                )
                invalid_pages.add(relative)
            record: dict[str, Any] = {
                "relative": relative,
                "raw": raw_sidecar,
                "page": page,
                "content_ok": False,
                "claims": [],
            }
            page_records.append(record)
            page_id = page.get("page_id")
            if not isinstance(page_id, str) or not page_id:
                diagnostics.append(
                    _diagnostic("PAGE_ID_INVALID", relative, "page_id is missing")
                )
                invalid_pages.add(relative)
            else:
                pages_by_id.setdefault(page_id, []).append(record)
            if page.get("lifecycle") not in KNOWLEDGE_LIFECYCLES:
                diagnostics.append(
                    _diagnostic(
                        "LIFECYCLE_INVALID",
                        relative,
                        "page lifecycle is outside the closed vocabulary",
                    )
                )
                invalid_pages.add(relative)
            content_path = page.get("content_path")
            if not isinstance(content_path, str):
                diagnostics.append(
                    _diagnostic("CONTENT_PATH_INVALID", relative, "content_path is missing")
                )
                invalid_pages.add(relative)
            else:
                try:
                    normalized_content = normalized_path(content_path)
                    if not normalized_content.startswith("docs/knowledge/"):
                        raise KnowledgeError(
                            "UNSAFE_PATH",
                            "canonical content is outside docs/knowledge",
                            exit_code=3,
                        )
                    content_paths.add(normalized_content)
                    record["content_path"] = normalized_content
                    if normalized_content not in eligible:
                        raise OSError("content is ignored, missing, or redirected")
                    content_raw = (repo / Path(*normalized_content.split("/"))).read_bytes()
                except (KnowledgeError, OSError):
                    diagnostics.append(
                        _diagnostic("CONTENT_MISSING", relative, "canonical content is unavailable")
                    )
                    invalid_pages.add(relative)
                else:
                    if sha256_bytes(content_raw) != page.get("content_sha256"):
                        diagnostics.append(
                            _diagnostic(
                                "CONTENT_HASH_DRIFT",
                                relative,
                                "canonical content hash differs from its sidecar",
                            )
                        )
                        invalid_pages.add(relative)
                    else:
                        record["content_ok"] = True

            claims = page.get("claims")
            if not isinstance(claims, list) or not claims:
                diagnostics.append(
                    _diagnostic("CLAIMS_INVALID", relative, "claims must be a non-empty array")
                )
                invalid_pages.add(relative)
                continue
            needs_stale_repair = False
            for claim_index, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    diagnostics.append(
                        _diagnostic("CLAIM_CONTRACT_INVALID", relative, "claim is not an object")
                    )
                    invalid_claims.add((relative, claim_index))
                    continue
                claim_record = {
                    "relative": relative,
                    "index": claim_index,
                    "claim": claim,
                    "page_record": record,
                    "source_ok": True,
                }
                record["claims"].append(claim_record)
                claim_id = claim.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id:
                    diagnostics.append(
                        _diagnostic("CLAIM_ID_INVALID", relative, "claim_id is missing")
                    )
                    invalid_claims.add((relative, claim_index))
                    continue
                claims_by_id.setdefault(claim_id, []).append(claim_record)
                if claim.get("lifecycle") not in KNOWLEDGE_LIFECYCLES:
                    diagnostics.append(
                        _diagnostic(
                            "LIFECYCLE_INVALID",
                            relative,
                            f"{claim_id} lifecycle is outside the closed vocabulary",
                        )
                    )
                    invalid_claims.add((relative, claim_index))
                if claim.get("evidence_class") not in EVIDENCE_CLASSES:
                    diagnostics.append(
                        _diagnostic(
                            "EVIDENCE_CLASS_INVALID",
                            relative,
                            f"{claim_id} evidence_class is outside the closed vocabulary",
                        )
                    )
                    invalid_claims.add((relative, claim_index))
                sources = claim.get("source_refs")
                sources_ok = isinstance(sources, list) and bool(sources)
                if not sources_ok:
                    diagnostics.append(
                        _diagnostic("SOURCE_REF_MISSING", relative, f"{claim_id} has no source refs")
                    )
                else:
                    for source in sources:
                        if not isinstance(source, dict):
                            diagnostics.append(
                                _diagnostic(
                                    "SOURCE_REF_INVALID",
                                    relative,
                                    f"{claim_id}: source ref is not an object",
                                )
                            )
                            sources_ok = False
                            continue
                        try:
                            _verify_source_ref(repo, source, eligible)
                        except KnowledgeError as exc:
                            code = {
                                "SOURCE_DRIFT": "SOURCE_HASH_DRIFT",
                                "EXCERPT_DRIFT": "SOURCE_EXCERPT_DRIFT",
                                "SOURCE_INELIGIBLE": "SOURCE_INELIGIBLE",
                                "EVIDENCE_LOOP": "EVIDENCE_LOOP",
                            }.get(exc.code, "SOURCE_REF_INVALID")
                            diagnostics.append(_diagnostic(code, relative, f"{claim_id}: {exc}"))
                            sources_ok = False
                claim_record["source_ok"] = sources_ok
                if not sources_ok:
                    invalid_claims.add((relative, claim_index))
                    needs_stale_repair = True
            if needs_stale_repair and page.get("lifecycle") != "stale":
                repaired = copy.deepcopy(page)
                repaired["lifecycle"] = "stale"
                for claim in repaired["claims"]:
                    if isinstance(claim, dict):
                        claim["lifecycle"] = "stale"
                repair_pages[relative] = (raw_sidecar, repaired)

    for page_id, records in pages_by_id.items():
        if len(records) < 2:
            continue
        for record in records:
            relative = record["relative"]
            diagnostics.append(
                _diagnostic(
                    "PAGE_ID_DUPLICATE",
                    relative,
                    f"page_id is duplicated: {page_id}",
                )
            )
            invalid_pages.add(relative)

    for claim_id, records in claims_by_id.items():
        if len(records) < 2:
            continue
        for record in records:
            diagnostics.append(
                _diagnostic(
                    "CLAIM_ID_DUPLICATE",
                    record["relative"],
                    f"claim_id is duplicated: {claim_id}",
                )
            )
            invalid_claims.add((record["relative"], record["index"]))

    known_backlinks = content_paths | set(pages_by_id)
    for record in page_records:
        relative = record["relative"]
        backlinks = record["page"].get("backlinks")
        if not isinstance(backlinks, list):
            diagnostics.append(
                _diagnostic("BACKLINK_INVALID", relative, "backlinks must be an array")
            )
            invalid_pages.add(relative)
            continue
        for backlink in backlinks:
            normalized = backlink
            if isinstance(backlink, str) and "/" in backlink:
                try:
                    normalized = normalized_path(backlink)
                except KnowledgeError:
                    normalized = ""
            if not isinstance(normalized, str) or normalized not in known_backlinks:
                diagnostics.append(
                    _diagnostic(
                        "BACKLINK_MISSING",
                        relative,
                        f"backlink target is missing: {backlink!r}",
                    )
                )
                invalid_pages.add(relative)

    for relative in sorted(eligible, key=lambda value: value.encode("utf-8")):
        if (
            relative.startswith("docs/knowledge/")
            and relative.endswith(".md")
            and relative not in SUPPORT_MARKDOWN
            and relative not in content_paths
        ):
            diagnostics.append(
                _diagnostic(
                    "ORPHAN_PAGE",
                    relative,
                    "canonical Markdown page has no page sidecar",
                )
            )

    contested_claim_ids: set[str] = set()
    asymmetric_claim_keys: set[tuple[str, int]] = set()
    contradiction_pairs: set[tuple[str, str]] = set()
    unique_claims = {
        claim_id: records[0]
        for claim_id, records in claims_by_id.items()
        if len(records) == 1
    }
    for claim_id, record in unique_claims.items():
        claim = record["claim"]
        contradictions = claim.get("contradicts", [])
        if not isinstance(contradictions, list):
            diagnostics.append(
                _diagnostic(
                    "CONTRADICTION_INVALID",
                    record["relative"],
                    f"{claim_id} contradicts must be an array",
                )
            )
            key = (record["relative"], record["index"])
            asymmetric_claim_keys.add(key)
            invalid_claims.add(key)
            continue
        for target_id in contradictions:
            target_record = unique_claims.get(target_id)
            if (
                target_record is None
                or not isinstance(target_record["claim"].get("contradicts"), list)
                or claim_id not in target_record["claim"].get("contradicts", [])
            ):
                key = (record["relative"], record["index"])
                asymmetric_claim_keys.add(key)
                invalid_claims.add(key)
                diagnostics.append(
                    _diagnostic(
                        "CONTRADICTION_ASYMMETRIC",
                        record["relative"],
                        f"{claim_id} does not have a symmetric contradiction with {target_id}",
                    )
                )
                continue
            pair = tuple(sorted((claim_id, target_id)))
            contradiction_pairs.add(pair)
            contested_claim_ids.update(pair)
    for left, right in sorted(contradiction_pairs):
        relative = min(
            unique_claims[left]["relative"],
            unique_claims[right]["relative"],
            key=lambda value: value.encode("utf-8"),
        )
        diagnostics.append(
            _diagnostic(
                "CONTRADICTION_DECISION_REQUIRED",
                relative,
                f"{left} and {right} are both valid and require a human decision",
            )
        )
    for claim_id in contested_claim_ids:
        record = unique_claims[claim_id]
        relative = record["relative"]
        page_record = record["page_record"]
        raw_page = page_record["raw"]
        original_page = page_record["page"]
        current = repair_pages.get(relative, (raw_page, copy.deepcopy(original_page)))[1]
        current["lifecycle"] = "contested"
        for claim in current.get("claims", []):
            if isinstance(claim, dict) and claim.get("claim_id") in contested_claim_ids:
                claim["lifecycle"] = "contested"
        repair_pages[relative] = (raw_page, current)

    eligible_claim_ids: list[str] = []
    for claim_id, records in claims_by_id.items():
        if len(records) != 1 or claim_id in contested_claim_ids:
            continue
        record = records[0]
        key = (record["relative"], record["index"])
        page = record["page_record"]["page"]
        claim = record["claim"]
        if (
            key not in invalid_claims
            and key not in asymmetric_claim_keys
            and record["relative"] not in invalid_pages
            and record["source_ok"]
            and record["page_record"]["content_ok"]
            and page.get("lifecycle") == "current"
            and claim.get("lifecycle") == "current"
        ):
            eligible_claim_ids.append(claim_id)

    for relative in invalid_pages:
        repair_pages.pop(relative, None)

    repairs_by_path: dict[str, tuple[bytes | None, bytes]] = {
        relative: (
            raw,
            (
                json.dumps(repaired, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n"
            ).encode("utf-8"),
        )
        for relative, (raw, repaired) in repair_pages.items()
    }

    index_relative = "docs/knowledge/index.md"
    if page_records or index_relative in eligible:
        current_pages = [record["page"] for record in page_records]
        expected_index = render_index(current_pages)
        index_path = repo / "docs" / "knowledge" / "index.md"
        current_index = index_path.read_bytes() if index_relative in eligible else None
        if current_index != expected_index:
            diagnostics.append(
                _diagnostic(
                    "INDEX_DRIFT",
                    index_relative,
                    "index differs from the deterministic page metadata projection",
                )
            )
        proposed_pages = [
            repair_pages.get(record["relative"], (record["raw"], record["page"]))[1]
            for record in page_records
        ]
        proposed_index = render_index(proposed_pages)
        if current_index != proposed_index:
            repairs_by_path[index_relative] = (current_index, proposed_index)

    promotions: list[dict[str, Any]] = []
    promotions_root = repo / "docs" / "knowledge" / "meta" / "promotions"
    if promotions_root.is_dir():
        for receipt_path in sorted(
            promotions_root.glob("*.json"),
            key=lambda path: path.as_posix().encode("utf-8"),
        ):
            relative = receipt_path.relative_to(repo).as_posix()
            if relative not in eligible:
                continue
            try:
                promotion = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                diagnostics.append(
                    _diagnostic(
                        "PROMOTION_RECEIPT_INVALID",
                        relative,
                        "promotion receipt is not valid UTF-8 JSON",
                    )
                )
                continue
            if (
                not isinstance(promotion, dict)
                or promotion.get("schema") != "knowledge-promotion/v1"
                or promotion.get("status") != "Ready"
            ):
                diagnostics.append(
                    _diagnostic(
                        "PROMOTION_RECEIPT_INVALID",
                        relative,
                        "promotion receipt is not a Ready knowledge-promotion/v1",
                    )
                )
                continue
            promotions.append(promotion)

    log_relative = "docs/knowledge/log.md"
    if promotions or log_relative in eligible:
        expected_log = render_promotion_log(promotions)
        log_path = repo / "docs" / "knowledge" / "log.md"
        current_log = log_path.read_bytes() if log_relative in eligible else None
        if current_log != expected_log:
            diagnostics.append(
                _diagnostic(
                    "PROMOTION_LOG_DRIFT",
                    log_relative,
                    "promotion log differs from the deterministic Ready receipt projection",
                )
            )
            repairs_by_path[log_relative] = (current_log, expected_log)

    repairs = [
        (
            relative,
            preimage,
            postimage,
        )
        for relative, (preimage, postimage) in sorted(
            repairs_by_path.items(),
            key=lambda item: item[0].encode("utf-8"),
        )
    ]

    diagnostics.sort(
        key=lambda item: (
            item["code"],
            item["path"].encode("utf-8"),
            item["message"],
        )
    )
    eligible_claim_ids.sort()
    repo_id = repository_id(repo)
    repair_ref: str | None = None
    repair_payload: str | None = None
    if repairs and repair_approval_actor and repair_approval_evidence:
        repair_ref, repair_payload = _seal_repair_candidate(
            repo,
            repairs,
            approval_actor=repair_approval_actor,
            approval_evidence=repair_approval_evidence,
        )
    non_decision_diagnostics = [
        item
        for item in diagnostics
        if item["code"] != "CONTRADICTION_DECISION_REQUIRED"
    ]
    outcome = (
        "failed"
        if non_decision_diagnostics
        else "decision_required"
        if contradiction_pairs
        else "passed"
    )
    return {
        "schema": "knowledge-lint/v1",
        "outcome": outcome,
        "diagnostics": diagnostics,
        "eligible_claim_ids": eligible_claim_ids,
        "repo_id": repo_id,
        "repair_candidate_ref": repair_ref,
        "repair_candidate_payload_sha256": repair_payload,
    }


def _bootstrap_candidate_draft(
    repo: Path,
    classification: dict[str, list[str]],
) -> dict[str, Any]:
    source_paths = [*classification["terminal"], *classification["conflict"]]
    source_snapshot = [_status_source_ref(repo, relative) for relative in source_paths]
    source_by_path = {source["path"]: source for source in source_snapshot}
    pages: list[dict[str, Any]] = []
    operations: list[dict[str, str]] = []

    def operation(path: str, postimage: str) -> dict[str, str]:
        return {
            "kind": "update" if (repo / Path(*path.split("/"))).is_file() else "create",
            "path": path,
            "postimage": postimage,
        }

    def add_page(page: dict[str, Any], content: str) -> None:
        pages.append(page)
        operations.extend(
            [
                operation(str(page["content_path"]), content),
                operation(
                    f"docs/knowledge/meta/pages/{page['page_id']}.json",
                    json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                ),
            ]
        )

    if classification["terminal"]:
        content_path = "docs/knowledge/topics/bootstrap-trusted-artifacts.md"
        content = (
            "# Bootstrap Trusted Artifacts\n\n"
            "## trusted-terminal-artifacts\n\n"
            "Only owner-validated terminal artifacts are catalogued here.\n\n"
            + "".join(
                f"- `{relative}` — `{source_by_path[relative]['sha256']}`\n"
                for relative in classification["terminal"]
            )
        )
        add_page(
            {
                "schema": "knowledge-page/v1",
                "page_id": "page-bootstrap-trusted-artifacts",
                "content_path": content_path,
                "content_sha256": sha256_bytes(content.encode("utf-8")),
                "title": "Bootstrap Trusted Artifacts",
                "aliases": ["可信終態產物"],
                "tags": ["bootstrap", "observed"],
                "lifecycle": "current",
                "claims": [
                    {
                        "claim_id": f"claim-bootstrap-terminal-{index:04d}",
                        "evidence_class": "observed",
                        "lifecycle": "current",
                        "content_anchor": "trusted-terminal-artifacts",
                        "source_refs": [source_by_path[relative]],
                        "supersedes": [],
                        "contradicts": [],
                    }
                    for index, relative in enumerate(classification["terminal"], 1)
                ],
                "backlinks": [],
            },
            content,
        )

    if classification["conflict"]:
        content_path = "docs/knowledge/incidents/legacy-status-conflict.md"
        content = (
            "# Legacy Status Conflict\n\n"
            "## legacy-status-conflict\n\n"
            "The owner artifacts disagree. All claims remain contested until a human decision.\n\n"
            + "".join(
                f"- `{relative}`: `{_artifact_state(repo / Path(*relative.split('/'))) or 'unknown'}` "
                f"— `{source_by_path[relative]['sha256']}`\n"
                for relative in classification["conflict"]
            )
        )
        add_page(
            {
                "schema": "knowledge-page/v1",
                "page_id": "page-legacy-status-conflict",
                "content_path": content_path,
                "content_sha256": sha256_bytes(content.encode("utf-8")),
                "title": "Legacy Status Conflict",
                "aliases": ["舊版狀態衝突"],
                "tags": ["bootstrap", "incident", "decision-required"],
                "lifecycle": "contested",
                "claims": [
                    {
                        "claim_id": f"claim-bootstrap-conflict-{index:04d}",
                        "evidence_class": "observed",
                        "lifecycle": "contested",
                        "content_anchor": "legacy-status-conflict",
                        "source_refs": [source_by_path[relative]],
                        "supersedes": [],
                        "contradicts": [],
                    }
                    for index, relative in enumerate(classification["conflict"], 1)
                ],
                "backlinks": [],
            },
            content,
        )

    operations.extend(
        [
            operation(
                "docs/knowledge/glossary.md",
                "# Project Glossary\n\nCanonical terms are added through reviewed promotions.\n",
            ),
            operation("docs/knowledge/index.md", render_index(pages).decode("utf-8")),
        ]
    )
    return {
        "schema": "knowledge-candidate-draft/v1",
        "stage": "bootstrap",
        "work_id": _work_id(classification),
        "decision": "change",
        "source_snapshot": source_snapshot,
        "operations": operations,
    }


def bootstrap_repository(
    repo_value: str,
    *,
    approval_actor: str,
    approval_evidence: str,
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    classification = classify_repository(repo)
    from knowledge_promotion import seal_candidate_draft

    sealed = seal_candidate_draft(
        str(repo),
        draft=_bootstrap_candidate_draft(repo, classification),
        approval_actor=approval_actor,
        approval_evidence=approval_evidence,
    )
    return {
        "schema": "knowledge-bootstrap/v1",
        "repo_id": sealed["repo_id"],
        "classification": classification,
        "candidate_ref": sealed["candidate_ref"],
        "candidate_payload_sha256": sealed["payload_sha256"],
        "affected_paths": sealed["affected_paths"],
        "postimages": sealed["postimages"],
        "approval": sealed["approval"],
        "quarantine_candidate_ref": (
            sealed["candidate_ref"] if classification["conflict"] else None
        ),
        "quarantine_candidate_payload_sha256": (
            sealed["payload_sha256"] if classification["conflict"] else None
        ),
    }
