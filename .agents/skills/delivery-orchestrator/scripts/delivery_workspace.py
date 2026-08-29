#!/usr/bin/env python3
"""Safely create, locate, and advance delivery-orchestrator workspaces."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse


sys.dont_write_bytecode = True
SCHEMA = "delivery-run/v1"
WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA_RE = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
EVENT_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
EVIDENCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{0,255}$")
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
GIT_ENV_REMOVE = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_ATTR_SOURCE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_PARAMETERS",
    "GIT_DIR",
    "GIT_EXEC_PATH",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_QUARANTINE_PATH",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_TEMPLATE_DIR",
    "GIT_WORK_TREE",
}
GIT_ENV_PREFIX_REMOVE = (
    "GIT_CONFIG_KEY_",
    "GIT_CONFIG_VALUE_",
    "GIT_TRACE",
    "GIT_REDIRECT_",
)
FILTER_DRIVER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CONTRACT_VALIDATOR: Any | None = None
_READY_PLAN_SCHEMA: dict[str, Any] | None = None
_DELIVERY_RUN_SCHEMA: dict[str, Any] | None = None


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


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _git(
    repo: str | Path,
    args: Sequence[str],
    *,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    command = ["git", "-C", str(canonical_path(repo)), *args]
    environment = os.environ.copy()
    for name in list(environment):
        if name in GIT_ENV_REMOVE or any(name.startswith(prefix) for prefix in GIT_ENV_PREFIX_REMOVE):
            environment.pop(name, None)
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        command,
        env=environment,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise DeliveryError(
            f"git command failed ({completed.returncode}) while running a scoped repository operation",
            code="GIT_COMMAND_FAILED",
        )
    return completed


def _active_filter_drivers(repo: str | Path) -> list[str]:
    tracked = _git(repo, ["-c", "core.fsmonitor=false", "ls-files", "-z"]).stdout
    if not tracked:
        return []
    attributes = _git(
        repo,
        ["-c", "core.fsmonitor=false", "check-attr", "-z", "--stdin", "filter"],
        input_bytes=tracked,
    ).stdout
    fields = attributes.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 3 != 0:
        raise DeliveryError("git check-attr returned an invalid filter inventory", code="FILTER_PROBE_FAILED")
    drivers: set[str] = set()
    for index in range(0, len(fields), 3):
        value = fields[index + 2]
        if value in {b"unspecified", b"unset", b"set", b""}:
            continue
        try:
            driver = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise DeliveryError("non-ASCII Git filter driver cannot be disabled safely", code="UNSAFE_FILTER") from exc
        if not FILTER_DRIVER_RE.fullmatch(driver):
            raise DeliveryError("Git filter driver name cannot be disabled safely", code="UNSAFE_FILTER")
        drivers.add(driver)
    if len(drivers) > 128:
        raise DeliveryError("too many Git filter drivers to disable safely", code="UNSAFE_FILTER")
    return sorted(drivers)


def _filter_disable_config(drivers: Sequence[str]) -> list[str]:
    config = ["-c", "core.fsmonitor=false"]
    for driver in drivers:
        config.extend(
            [
                "-c",
                f"filter.{driver}.process=",
                "-c",
                f"filter.{driver}.smudge=",
                "-c",
                f"filter.{driver}.clean=",
                "-c",
                f"filter.{driver}.required=false",
            ]
        )
    return config


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


def _indexed_gitlinks(repo: str | Path) -> list[str]:
    output = _git(repo, ["-c", "core.fsmonitor=false", "ls-files", "--stage", "-z"]).stdout
    result: set[str] = set()
    for entry in output.split(b"\0"):
        if not entry:
            continue
        metadata, separator, raw_path = entry.partition(b"\t")
        if not separator or not metadata.startswith(b"160000 "):
            continue
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeliveryError("submodule path is not valid UTF-8", code="UNSAFE_SUBMODULE") from exc
        result.add(_normalized_repo_path(relative))
    return sorted(result, key=lambda value: value.encode("utf-8"))


def _strict_status(repo: str | Path, *, visited: set[str] | None = None, depth: int = 0) -> bytes:
    """Return empty only when this worktree and every initialized submodule are clean."""
    if depth > 32:
        raise DeliveryError("submodule nesting exceeds the safe probe limit", code="UNSAFE_SUBMODULE")
    top = canonical_path(repo)
    key = canonical_path_text(top)
    seen = set() if visited is None else visited
    if key in seen:
        raise DeliveryError("submodule graph contains a worktree cycle", code="UNSAFE_SUBMODULE")
    seen.add(key)
    try:
        filter_drivers = _active_filter_drivers(top)
        status = _git(
            top,
            [
                *_filter_disable_config(filter_drivers),
                "-c",
                "submodule.recurse=false",
                "status",
                "--porcelain=v2",
                "-z",
                "--untracked-files=all",
                "--ignore-submodules=dirty",
            ],
        ).stdout
        if status:
            return status
        for relative in _indexed_gitlinks(top):
            lexical = top / Path(*relative.split("/"))
            is_junction = getattr(lexical, "is_junction", lambda: False)
            if lexical.is_symlink() or is_junction():
                return b"submodule-unsafe\0" + relative.encode("utf-8")
            if not lexical.exists():
                continue
            if lexical.is_dir() and not any(lexical.iterdir()):
                continue
            child_top_result = _git(lexical, ["rev-parse", "--show-toplevel"], check=False)
            if child_top_result.returncode != 0:
                return b"submodule-invalid\0" + relative.encode("utf-8")
            child_top = canonical_path(_decode(child_top_result.stdout).strip())
            if canonical_path_text(child_top) != canonical_path_text(lexical):
                return b"submodule-redirected\0" + relative.encode("utf-8")
            child_status = _strict_status(child_top, visited=seen, depth=depth + 1)
            if child_status:
                return (
                    b"submodule-dirty\0"
                    + relative.encode("utf-8")
                    + b"\0"
                    + sha256_bytes(child_status).encode("ascii")
                )
        return b""
    finally:
        seen.remove(key)


def _parse_worktrees(output: bytes) -> list[dict[str, str | bool]]:
    records: list[dict[str, str | bool]] = []
    current: dict[str, str | bool] = {}
    for raw_line in _decode(output).splitlines():
        if not raw_line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = raw_line.partition(" ")
        current[key] = value if value else True
    if current:
        records.append(current)
    return records


def probe_repository(repo: str | Path) -> dict[str, Any]:
    requested = canonical_path(repo)
    bare = _git(requested, ["rev-parse", "--is-bare-repository"], check=False)
    if bare.returncode != 0:
        raise DeliveryError(f"not a Git repository: {requested}", code="NOT_A_REPOSITORY")
    if _decode(bare.stdout).strip() == "true":
        raise DeliveryError(f"bare repositories are not supported: {requested}", code="BARE_REPOSITORY")

    top = canonical_path(_decode(_git(requested, ["rev-parse", "--show-toplevel"]).stdout).strip())
    common_dir = canonical_path(
        _decode(_git(top, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).stdout).strip()
    )
    worktrees = _parse_worktrees(_git(top, ["worktree", "list", "--porcelain"]).stdout)
    if not worktrees or "worktree" not in worktrees[0]:
        raise DeliveryError("git worktree list did not identify a primary worktree", code="WORKTREE_PROBE_FAILED")
    primary = canonical_path(str(worktrees[0]["worktree"]))

    symbolic = _git(top, ["symbolic-ref", "--quiet", "HEAD"], check=False)
    branch_ref = _decode(symbolic.stdout).strip() if symbolic.returncode == 0 else None
    head_sha = _decode(_git(top, ["rev-parse", "HEAD"]).stdout).strip()
    status = _strict_status(top)
    repo_id = sha256_bytes(canonical_path_text(common_dir).encode("utf-8"))
    return {
        "repo_id": repo_id,
        "requested_path": str(requested),
        "canonical_worktree": str(top),
        "worktree_key": path_key(top),
        "primary_worktree": str(primary),
        "is_primary": canonical_path_text(top) == canonical_path_text(primary),
        "branch_ref": branch_ref,
        "branch": branch_ref.removeprefix("refs/heads/") if branch_ref else None,
        "attached": branch_ref is not None,
        "head_sha": head_sha,
        "strict_clean": status == b"",
        "status_sha256": sha256_bytes(status),
        "worktrees": worktrees,
    }


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


def destination_and_branch(primary: str | Path, work_id: str, generation: int) -> tuple[Path, str]:
    primary_path = canonical_path(primary)
    label = workspace_label(work_id, generation)
    lexical_container = primary_path.parent / f"{primary_path.name}.worktrees"
    is_junction = getattr(lexical_container, "is_junction", lambda: False)
    if lexical_container.is_symlink() or is_junction():
        raise DeliveryError("sibling worktree container must not be a symlink or junction", code="UNSAFE_DESTINATION")
    container = canonical_path(lexical_container)
    destination = canonical_path(container / label)
    if destination.parent != container:
        raise DeliveryError("computed worktree is not a direct child of the sibling container", code="UNSAFE_DESTINATION")
    if destination == primary_path or _is_relative_to(destination, primary_path) or _is_relative_to(primary_path, destination):
        raise DeliveryError("computed worktree overlaps the primary worktree", code="UNSAFE_DESTINATION")
    return destination, f"delivery/{label}"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _branch_exists(repo: str | Path, branch: str) -> bool:
    result = _git(repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False)
    if result.returncode not in (0, 1):
        raise DeliveryError("unable to determine whether the delivery branch exists", code="BRANCH_PROBE_FAILED")
    return result.returncode == 0


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


def _logical_refs(values: Iterable[str], label: str) -> list[str]:
    refs = list(dict.fromkeys(values))
    if not refs or any(not isinstance(ref, str) or not EVIDENCE_REF_RE.fullmatch(ref) for ref in refs):
        raise DeliveryError(
            f"{label} requires non-secret logical refs using only letters, digits, ._:/#-",
            code="INVALID_EVIDENCE_REF",
        )
    return refs


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
            or any(not isinstance(ref, str) or not EVIDENCE_REF_RE.fullmatch(ref) for ref in refs)
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
            or any(not isinstance(ref, str) or not EVIDENCE_REF_RE.fullmatch(ref) for ref in refs)
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
            or any(not isinstance(ref, str) or not EVIDENCE_REF_RE.fullmatch(ref) for ref in refs)
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
        if not isinstance(ledger_ref, str) or not EVIDENCE_REF_RE.fullmatch(ledger_ref):
            errors.append(f"implementation run {index} ledger_ref is invalid")

    if status == "complete":
        current_run_id = implementations.get("current_run_id") if isinstance(implementations, dict) else None
        current_run = next(
            (item for item in implementation_runs if isinstance(item, dict) and item.get("run_id") == current_run_id),
            None,
        )
        if current_run is None or current_run.get("status") != "Complete":
            errors.append("complete delivery lacks a Complete current implementation run")
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


def _assert_new_work_probe(probe: dict[str, Any]) -> None:
    if not probe["is_primary"]:
        raise DeliveryError("new work must start from the primary worktree", code="NOT_PRIMARY")
    if not probe["attached"]:
        raise DeliveryError("new work requires an attached primary HEAD", code="DETACHED_HEAD")
    if not probe["strict_clean"]:
        raise DeliveryError(
            "new work requires an empty porcelain-v2 status, including staged, unstaged, untracked, and submodule changes",
            code="DIRTY_PRIMARY",
        )


def _assert_no_collision(probe: dict[str, Any], destination: Path, branch: str) -> None:
    if os.path.lexists(destination):
        raise DeliveryError(f"delivery destination already exists: {destination}", code="PATH_COLLISION")
    if _branch_exists(probe["primary_worktree"], branch):
        raise DeliveryError(f"delivery branch already exists: {branch}", code="BRANCH_COLLISION")
    for item in probe["worktrees"]:
        if "worktree" in item and canonical_path_text(str(item["worktree"])) == canonical_path_text(destination):
            raise DeliveryError(f"delivery destination is already registered: {destination}", code="WORKTREE_COLLISION")


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


def start_workspace(
    repo: str | Path,
    work_id: str,
    request_sha256: str,
    *,
    root: Path | None = None,
    generation: int = 1,
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
        record = _new_record(primary_probe, work_id, request_sha256, destination, branch)
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
                raise DeliveryError("git worktree add failed; preserved Blocked evidence", code="WORKTREE_ADD_FAILED")

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
                _approved_upstream_materialization(record, verify_current_sources=True)
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


def _normalized_repo_path(value: str) -> str:
    if not value or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise DeliveryError(f"path must be repository-relative and normalized: {value!r}", code="INVALID_PATH")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DeliveryError(f"path must not contain empty, dot, or traversal segments: {value!r}", code="INVALID_PATH")
    return value


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
            exists_at_base = _git(
                worktree,
                ["cat-file", "-e", f"{base_sha}:{relative}"],
                check=False,
            )
            if exists_at_base.returncode != 0:
                raise DeliveryError(
                    "local Ready source is neither base-tracked nor an approved materialized artifact",
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

    _append_event(record, kind=event, phase=phase, status=status, evidence_refs=evidence_refs)
    errors = validate_record(record)
    if errors:
        raise DeliveryError(f"transition would create an invalid record: {'; '.join(errors)}", code="INVALID_RECORD")
    _atomic_write_json(path, record)
    return _result(record, path, outcome="transitioned")


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
    run_dir = run_directory(root, probe["repo_id"], work_id)
    if not _record_path(run_dir).is_file():
        raise DeliveryError("delivery record is missing", code="MISSING_RECORD")
    with _exclusive_lock(run_dir / "record.lock"):
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
            handoff_path=handoff_path,
            candidate_revision=candidate_revision,
            payload_sha256=payload_sha256,
            plan_approval_refs=plan_approval_refs,
            implementation_run_id=implementation_run_id,
            implementation_ledger_ref=implementation_ledger_ref,
            implementation_status=implementation_status,
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
    transition.add_argument("--handoff-path")
    transition.add_argument("--candidate-revision")
    transition.add_argument("--payload-sha256")
    transition.add_argument("--plan-approval-ref", action="append", default=[])
    transition.add_argument("--implementation-run-id")
    transition.add_argument("--implementation-ledger-ref")
    transition.add_argument("--implementation-status")
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
                handoff_path=args.handoff_path,
                candidate_revision=args.candidate_revision,
                payload_sha256=args.payload_sha256,
                plan_approval_refs=args.plan_approval_ref,
                implementation_run_id=args.implementation_run_id,
                implementation_ledger_ref=args.implementation_ledger_ref,
                implementation_status=args.implementation_status,
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
