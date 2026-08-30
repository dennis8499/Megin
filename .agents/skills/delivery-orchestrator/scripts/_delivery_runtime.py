#!/usr/bin/env python3
"""Private runtime primitives for delivery-orchestrator.

Authority: delivery-runtime
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "delivery-run/v1"
WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
EVENT_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
EVIDENCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}$")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:secret|token|password|passwd|credential|api[-_.]?key|private[-_.]?key)\s*[:=]\s*\S{6,}"
)
SECRET_SENTINEL_RE = re.compile(
    r"\b(?:[A-Z0-9]+_)*(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY)_[A-Z0-9_-]{6,}\b"
)
KNOWN_TOKEN_RE = re.compile(
    r"(?:\bAKIA[0-9A-Z]{16}\b|\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b)"
)
RESERVED_WINDOWS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
PHASE_TRANSITIONS = {
    "workspace": {"workspace", "requirements"},
    "requirements": {"requirements", "planning"},
    "planning": {"planning", "requirements", "implementation"},
    "implementation": {"implementation", "planning", "complete"},
    "complete": set(),
}
STATUS_TRANSITIONS = {
    "active": {"active", "awaiting_user", "blocked", "complete"},
    "awaiting_user": {"awaiting_user", "active", "blocked"},
    "blocked": {"blocked", "active"},
    "complete": set(),
}

class DeliveryError(RuntimeError):
    """A safe, user-actionable workflow failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "DELIVERY_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_utc_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _is_aware_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def canonical_path_text(path: str | Path) -> str:
    return os.path.normcase(str(canonical_path(path))).replace("\\", "/")


def path_key(path: str | Path) -> str:
    return sha256_bytes(canonical_path_text(path).encode("utf-8"))


def validate_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise DeliveryError(f"{label} must be a lowercase 64-character SHA-256", code="INVALID_DIGEST")


def validate_work_id(work_id: str) -> str:
    if not isinstance(work_id, str) or not WORK_ID_RE.fullmatch(work_id):
        raise DeliveryError(
            "work_id must be 3-64 lowercase ASCII kebab-case characters without empty segments",
            code="INVALID_WORK_ID",
        )
    if work_id in RESERVED_WINDOWS_NAMES:
        raise DeliveryError(f"work_id {work_id!r} is a reserved Windows device name", code="INVALID_WORK_ID")
    return work_id


def topic_slug(topic: str) -> str:
    normalized = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode("ascii").lower()
    words = [word for word in re.split(r"[^a-z0-9]+", normalized) if word][:5]
    if not words:
        words = ["general", "work"]
    elif len(words) == 1:
        words.append("work" if words[0] != "work" else "task")
    while len("-".join(words)) > 30:
        longest = max(range(len(words)), key=lambda index: len(words[index]))
        if len(words[longest]) <= 2:
            break
        words[longest] = words[longest][:-1]
    return "-".join(words)


def generate_work_id(repo_id: str, base_sha: str, request_sha256: str, topic: str) -> str:
    validate_sha256(repo_id, "repo_id")
    validate_sha256(request_sha256, "request_sha256")
    suffix = sha256_bytes(
        canonical_json(
            {
                "repo_id": repo_id,
                "initial_base_sha": base_sha,
                "request_sha256": request_sha256,
            }
        )
    )[:8]
    work_id = f"work-{date.today().strftime('%Y%m%d')}-{topic_slug(topic)}-{suffix}"
    if len(work_id) > 64:
        excess = len(work_id) - 64
        slug = topic_slug(topic)
        work_id = f"work-{date.today().strftime('%Y%m%d')}-{slug[:-excess]}-{suffix}"
    return validate_work_id(work_id)


def default_registry_root() -> Path:
    configured = os.environ.get("DELIVERY_ORCHESTRATOR_ROOT")
    root = canonical_path(configured) if configured else canonical_path(Path(tempfile.gettempdir()) / "delivery-orchestrator")
    return _validate_registry_root(root)


def registry_root(value: str | None) -> Path:
    return _validate_registry_root(canonical_path(value)) if value else default_registry_root()


def _validate_registry_root(root: str | Path) -> Path:
    canonical_root = canonical_path(root)
    host_temp = canonical_path(tempfile.gettempdir())
    if canonical_root != host_temp and not _is_relative_to(canonical_root, host_temp):
        raise DeliveryError("delivery registry must stay under the canonical host temp provider", code="UNSAFE_REGISTRY_ROOT")
    return canonical_root


def run_directory(root: Path, repo_id: str, work_id: str) -> Path:
    return root / "repos" / repo_id / "works" / work_id


def workspace_label(work_id: str, generation: int) -> str:
    return work_id if generation == 1 else f"{work_id}-r{generation}"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _exclusive_lock(path: Path) -> Iterable[None]:
    """Acquire a fail-closed host-temp lock without waiting or stealing."""
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise DeliveryError(f"delivery record is locked: {path}", code="RECORD_LOCKED") from exc
    except OSError as exc:
        raise DeliveryError(f"delivery record lock cannot be created: {path}: {exc}", code="LOCK_FAILED") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryError(f"cannot read delivery record {path}: {exc}", code="INVALID_RECORD") from exc
    if not isinstance(value, dict):
        raise DeliveryError(f"delivery record is not an object: {path}", code="INVALID_RECORD")
    return value


def _contains_sensitive_material(value: str) -> bool:
    return bool(
        SECRET_ASSIGNMENT_RE.search(value)
        or SECRET_SENTINEL_RE.search(value)
        or KNOWN_TOKEN_RE.search(value)
    )


def _logical_refs(values: Iterable[str], label: str) -> list[str]:
    refs = list(dict.fromkeys(values))
    if not refs or any(
        not isinstance(ref, str)
        or not EVIDENCE_REF_RE.fullmatch(ref)
        or _contains_sensitive_material(ref)
        for ref in refs
    ):
        raise DeliveryError(
            f"{label} requires non-secret logical refs using only letters, digits, ._:/#-",
            code="INVALID_EVIDENCE_REF",
        )
    return refs


def _normalized_repo_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise DeliveryError(f"path must be repository-relative and normalized: {value!r}", code="INVALID_PATH")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DeliveryError(f"path must not contain empty, dot, or traversal segments: {value!r}", code="INVALID_PATH")
    return value
