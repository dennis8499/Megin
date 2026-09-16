#!/usr/bin/env python3
"""Portable SDLC v2 command line entry point.

The command intentionally has no third party dependencies.  It keeps runtime state in a
user state directory and only writes the target repository's opt-in ``.sdlc/config.json``
and approved delivery changes.  The CLI is a small, deterministic state machine; the
Codex skills provide the human and sub-agent orchestration around it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit


# Codex commonly runs on Windows machines whose console encoding is a local code page.
# The CLI is an automation surface, so make its JSON stream explicitly UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCHEMA = "delivery-run/v2"
CONFIG_SCHEMA = "sdlc-project/v1"
PLUGIN_VERSION = "0.1.0"
# v2 records are bound to the contract major version.  A newer compatible
# plugin may continue an older minor/patch record; it must never reinterpret a
# v1 record or a future record it does not understand.
PLUGIN_VERSION_PARTS = tuple(int(item) for item in PLUGIN_VERSION.split(".")[:3])
DIAGNOSIS_SCHEMA = "bug-diagnosis/v1"
WRITER_REPORT_SCHEMA = "sdlc-writer-report/v1"
REVIEW_REPORT_SCHEMA = "sdlc-review-report/v1"
KNOWLEDGE_REVIEW_SCHEMA = "sdlc-knowledge-review/v1"
WORK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_CLASSES = ("read_only", "small", "large", "bug")
APPROVAL_STAGES = ("integrated", "requirements", "plan")
DELIVERY_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "delivery-run-v2.schema.json"


class SdlcError(RuntimeError):
    """A user-actionable, fail-closed CLI error."""


def compatible_plugin_version(value: Any) -> bool:
    """Return whether this engine can safely continue a v2 record.

    Minor and patch updates keep the v2 state contract and may continue an
    in-flight record that was created by an earlier compatible plugin.  A
    different major version, malformed version, or future version remains
    blocked until an engine explicitly supporting that record is installed.
    """

    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        return False
    parts = tuple(int(item) for item in value.split("."))
    return parts[0] == PLUGIN_VERSION_PARTS[0] and parts <= PLUGIN_VERSION_PARTS


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value: Any) -> str:
    return digest_bytes(json_bytes(value))


def redact(value: str) -> str:
    """Remove common credential forms before output is persisted as evidence."""

    value = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+", r"\1<redacted>", value)
    value = re.sub(r"(?i)(\b(?:token|secret|password|passwd|api[_-]?key)\s*[:=]\s*)[^\s,;]+", r"\1<redacted>", value)
    # Environment assignments commonly use a product-specific prefix (for
    # example AWS_SECRET_ACCESS_KEY or MY_API_KEY). Match the whole variable
    # name but preserve it so diagnostics remain understandable.
    value = re.sub(
        r"(?im)(\b(?:[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY)[A-Z0-9_]*|TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|PRIVATE[_-]?KEY)\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        r"\1<redacted>",
        value,
    )
    value = re.sub(r"(https?://)([^/@\s]+):([^/@\s]+)@", r"\1<redacted>@", value)
    return value


def redact_value(value: Any) -> Any:
    """Recursively redact text before an external report is persisted."""

    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    return value


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def reserve_state_file(path: Path) -> None:
    """Reserve a new Work ID atomically so concurrent starts have one winner."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SdlcError(f"work ID already exists for this repository: {path.stem}; use resume") from exc
    try:
        os.close(descriptor)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise SdlcError(f"state/configuration not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SdlcError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SdlcError(f"JSON root must be an object: {path}")
    return value


def _json_pointer(root: Any, pointer: str) -> Any:
    """Resolve the local JSON pointers used by the bundled schema."""

    if not pointer.startswith("#/"):
        raise ValueError(f"only local schema references are supported: {pointer}")
    value = root
    for token in pointer[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        else:
            raise ValueError(f"schema reference does not exist: {pointer}")
    return value


def _json_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def validate_delivery_schema(instance: Any, schema_path: Path | None = None) -> list[str]:
    """Validate the v2 record with the dependency-free subset used by the schema.

    The plugin deliberately has no runtime dependencies.  This validator covers
    the JSON Schema keywords used in ``delivery-run-v2.schema.json`` so loading a
    state record applies the same structural contract as the checked-in schema.
    """

    try:
        schema = json.loads((schema_path or DELIVERY_SCHEMA_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot load delivery schema: {exc}"]
    errors: list[str] = []

    def check(value: Any, rule: dict[str, Any], path: str, root: dict[str, Any]) -> bool:
        if len(errors) >= 100:
            return False
        if "$ref" in rule:
            target = _json_pointer(root, str(rule["$ref"]))
            return check(value, target, path, root)
        valid = True
        if "const" in rule and value != rule["const"]:
            errors.append(f"{path}: must equal {rule['const']!r}")
            valid = False
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{path}: must be one of {rule['enum']!r}")
            valid = False
        if "type" in rule:
            types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            if not any(_json_type_matches(value, item) for item in types):
                errors.append(f"{path}: expected type {types!r}")
                return False
        if isinstance(value, str):
            if "minLength" in rule and len(value) < int(rule["minLength"]):
                errors.append(f"{path}: is shorter than minLength")
                valid = False
            if "maxLength" in rule and len(value) > int(rule["maxLength"]):
                errors.append(f"{path}: exceeds maxLength")
                valid = False
            if "pattern" in rule:
                try:
                    matched = re.search(str(rule["pattern"]), value) is not None
                except re.error as exc:
                    errors.append(f"{path}: invalid schema pattern: {exc}")
                    matched = False
                if not matched:
                    errors.append(f"{path}: does not match pattern {rule['pattern']!r}")
                    valid = False
            if rule.get("format") == "date-time":
                try:
                    _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{path}: is not an ISO date-time")
                    valid = False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                errors.append(f"{path}: is below minimum")
                valid = False
        if isinstance(value, list):
            if "minItems" in rule and len(value) < int(rule["minItems"]):
                errors.append(f"{path}: has too few items")
                valid = False
            if "maxItems" in rule and len(value) > int(rule["maxItems"]):
                errors.append(f"{path}: has too many items")
                valid = False
            if rule.get("uniqueItems"):
                encoded = [json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in value]
                if len(encoded) != len(set(encoded)):
                    errors.append(f"{path}: items must be unique")
                    valid = False
            item_rule = rule.get("items")
            if isinstance(item_rule, dict):
                for index, item in enumerate(value):
                    check(item, item_rule, f"{path}[{index}]", root)
        if isinstance(value, dict):
            required = rule.get("required", [])
            for key in required:
                if key not in value:
                    errors.append(f"{path}: missing required property {key!r}")
                    valid = False
            properties = rule.get("properties", {})
            for key, item in value.items():
                if key in properties:
                    check(item, properties[key], f"{path}.{key}", root)
                elif rule.get("additionalProperties") is False:
                    errors.append(f"{path}: additional property {key!r} is not allowed")
                    valid = False
                elif isinstance(rule.get("additionalProperties"), dict):
                    check(item, rule["additionalProperties"], f"{path}.{key}", root)
        alternatives = rule.get("anyOf")
        if isinstance(alternatives, list):
            snapshots: list[list[str]] = []
            for candidate in alternatives:
                before = len(errors)
                check(value, candidate, path, root)
                snapshots.append(errors[before:])
                del errors[before:]
            if not any(not item for item in snapshots):
                errors.append(f"{path}: does not satisfy anyOf")
                valid = False
        alternatives = rule.get("oneOf")
        if isinstance(alternatives, list):
            matches = 0
            for candidate in alternatives:
                before = len(errors)
                check(value, candidate, path, root)
                if len(errors) == before:
                    matches += 1
                del errors[before:]
            if matches != 1:
                errors.append(f"{path}: must satisfy exactly one oneOf branch")
                valid = False
        all_rules = rule.get("allOf")
        if isinstance(all_rules, list):
            for candidate in all_rules:
                check(value, candidate, path, root)
        if_rule = rule.get("if")
        if isinstance(if_rule, dict):
            before = len(errors)
            check(value, if_rule, path, root)
            condition_ok = len(errors) == before
            del errors[before:]
            branch = rule.get("then") if condition_ok else rule.get("else")
            if isinstance(branch, dict):
                check(value, branch, path, root)
        return valid

    check(instance, schema, "$", schema)
    return errors[:100]


def run_process(
    command: Sequence[str],
    cwd: Path,
    *,
    timeout: int = 60,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SdlcError(f"tool not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        output = redact((exc.stdout or "") + (exc.stderr or ""))
        raise SdlcError(f"command timed out after {timeout}s: {' '.join(command)}\n{output}") from exc
    if check and result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise SdlcError(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def git(cwd: Path, *arguments: str, check: bool = True, timeout: int = 60) -> str:
    result = run_process(("git", *arguments), cwd, timeout=timeout, check=False)
    if check and result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise SdlcError(f"git {' '.join(arguments)} failed ({result.returncode}) in {cwd}: {detail}")
    return result.stdout or ""


def git_bytes(cwd: Path, *arguments: str, check: bool = True, timeout: int = 60) -> bytes:
    """Run Git without decoding its output.

    A delivery snapshot is a digest of file bytes.  Decoding Git output before hashing
    would make the result dependent on the console code page on Windows, so the
    content snapshot path deliberately uses this byte-oriented helper.
    """

    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SdlcError("tool not found: git") from exc
    except subprocess.TimeoutExpired as exc:
        raise SdlcError(f"git command timed out after {timeout}s: git {' '.join(arguments)}") from exc
    if check and result.returncode != 0:
        detail = redact((result.stdout + result.stderr).decode("utf-8", errors="replace")).strip()
        raise SdlcError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result.stdout or b""


def require_git_repo(path: str | Path) -> Path:
    requested = Path(path).expanduser().resolve()
    if not requested.exists():
        raise SdlcError(f"repository path does not exist: {requested}")
    top = git(requested, "rev-parse", "--show-toplevel", check=True).strip()
    return Path(top).resolve()


def repo_identity(repo: Path) -> str:
    common = Path(git(repo, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = repo / common
    common = common.resolve()
    return digest_text(f"{repo}\n{common}")


def safe_remote_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "://" not in value:
        # SCP-like SSH URLs do not contain credentials in the normal form.  Keep them
        # only as a destination hint; never use them as a command argument for state.
        return value.split("?", 1)[0].split("#", 1)[0]
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    netloc = host
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def validate_remote_name(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    value = str(value).strip()
    # The portable contract stores a Git remote *name*, never an URL or credential.
    if value.startswith("-") or "@" in value or "://" in value or re.search(r"\s", value):
        raise SdlcError("remote must be a Git remote name; credentials and URLs are not stored")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value):
        raise SdlcError("remote contains unsupported characters")
    return value


def safe_ref(value: str) -> str:
    value = redact(str(value)).strip()
    if not value or "<redacted>" in value:
        return f"ref:digest-{digest_text(value)[:32]}"
    return value[:256]


def git_remote(repo: Path, name: str = "origin") -> str | None:
    value = git(repo, "remote", "get-url", name, check=False).strip()
    return safe_remote_url(value) if value else None


def remote_url_digest(repo: Path, name: str | None) -> str | None:
    if not name:
        return None
    value = git_remote(repo, name)
    return digest_text(value) if value else None


def current_branch(repo: Path) -> str:
    value = git(repo, "branch", "--show-current").strip()
    return value or "HEAD"


def validate_branch_name(value: str) -> str:
    value = str(value).strip()
    if (
        not value
        or value.startswith("-")
        or value.endswith(".")
        or value.endswith("/")
        or ".." in value
        or "@{" in value
        or re.search(r"[\s\x00-\x1f\\~^:?*\[]", value)
        or not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", value)
    ):
        raise SdlcError(f"base branch contains unsupported characters: {value!r}")
    return value


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def normalize_rel(value: str) -> str:
    value = str(value).strip().replace("\\", "/")
    if not value:
        raise SdlcError("paths cannot be empty")
    if value == ".":
        return "."
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise SdlcError(f"path must be relative to the worktree: {value}")
    pieces = value.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise SdlcError(f"path traversal is not allowed: {value}")
    return "/".join(pieces)


def normalize_paths(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = normalize_rel(value)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return sorted(result)


def allowed_path(path: str, allowed: Sequence[str]) -> bool:
    path = normalize_rel(path)
    compare_path = path.casefold() if os.name == "nt" else path
    for prefix in allowed:
        prefix = normalize_rel(prefix)
        compare_prefix = prefix.casefold() if os.name == "nt" else prefix
        if compare_prefix == "." or compare_path == compare_prefix or compare_path.startswith(compare_prefix + "/"):
            return True
    return False


def snapshot_bytes(path: Path) -> bytes:
    """Read a worktree entry without following a symlink outside the repository."""

    if path.is_symlink():
        return os.readlink(path).encode("utf-8", errors="surrogateescape")
    return path.read_bytes()


def working_tree_manifest(
    repo: Path, scope: Sequence[str] | None = None, *, exclude: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the content manifest used by all v2 snapshot and baseline checks."""

    requested = normalize_paths(scope or ["."])
    excluded = normalize_paths(exclude or []) if exclude else []
    listed = git_bytes(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    names = [item.decode("utf-8", errors="surrogateescape") for item in listed.split(b"\0") if item]
    paths: set[str] = set()
    for name in names:
        try:
            normalized = normalize_rel(name)
        except SdlcError:
            continue
        if any(allowed_path(normalized, [item]) for item in requested) and not any(allowed_path(normalized, [item]) for item in excluded):
            paths.add(normalized)
    # A directory scope includes files that are ignored by Git only when they
    # are already tracked; the explicit scope still remains bounded and
    # portable.
    if requested != ["."]:
        for prefix in requested:
            candidate = repo / prefix
            if candidate.is_file():
                paths.add(prefix)
            elif candidate.is_dir():
                for child in candidate.rglob("*"):
                    if child.is_file() and ".git" not in child.parts:
                        try:
                            child_path = normalize_rel(str(child.relative_to(repo)))
                            if not any(allowed_path(child_path, [item]) for item in excluded):
                                paths.add(child_path)
                        except SdlcError:
                            continue
    files: list[dict[str, Any]] = []
    for path in sorted(paths):
        absolute = repo / Path(path)
        if absolute.is_file() or absolute.is_symlink():
            try:
                data = snapshot_bytes(absolute)
            except OSError as exc:
                raise SdlcError(f"cannot read snapshot path {path}: {exc}") from exc
            files.append({"path": path, "sha256": digest_bytes(data), "size": len(data), "mode": stat.S_IMODE(absolute.lstat().st_mode)})
        else:
            # Keep deletions in the manifest so a delete cannot masquerade as
            # an unchanged tree.
            files.append({"path": path, "sha256": None, "size": 0, "mode": None})
    return files


def working_tree_snapshot(repo: Path, scope: Sequence[str] | None = None, *, exclude: Sequence[str] | None = None) -> str:
    """Return a deterministic digest of the current file content.

    ``git status`` only identifies paths.  It therefore cannot distinguish two edits
    to the same path.  The v2 contract records raw bytes for every tracked, deleted,
    and non-ignored untracked path (or the requested scope) and hashes that manifest.
    """

    requested = normalize_paths(scope or ["."])
    excluded = normalize_paths(exclude or []) if exclude else []
    files = working_tree_manifest(repo, requested, exclude=excluded)
    return digest_json({"scope": requested, "files": files})


def baseline_manifest_changed(assignment: dict[str, Any], repo: Path) -> list[str]:
    """Find previously dirty paths whose bytes changed during this assignment."""

    recorded = {
        item.get("path"): item
        for item in assignment.get("baseline_manifest", [])
        if isinstance(item, dict) and item.get("path")
    }
    if not recorded:
        return []
    current = {item.get("path"): item for item in working_tree_manifest(repo)}
    changed: list[str] = []
    for path, before in recorded.items():
        if current.get(path) != before:
            changed.append(path)
    return sorted(changed)


def status_paths(repo: Path) -> tuple[list[str], str]:
    raw = git(repo, "status", "--porcelain=v1", "-z", check=True)
    paths: list[str] = []
    parts = raw.split("\0")
    index = 0
    while index < len(parts):
        entry = parts[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            continue
        status = entry[:2]
        path = entry[3:]
        paths.append(path)
        # Rename/copy records contain the original path followed by the new path.
        if ("R" in status or "C" in status) and index < len(parts) and parts[index]:
            paths.append(parts[index])
            index += 1
    # Porcelain reports an untracked directory as ``dir/``.  It is a status
    # container rather than a file path; the snapshot manifest below expands
    # its contents where appropriate.
    normalized = sorted({normalize_rel(path.rstrip("/\\")) for path in paths if path.rstrip("/\\")})
    return normalized, working_tree_snapshot(repo)


def knowledge_snapshot(repo: Path, scope: Sequence[str]) -> str:
    return working_tree_snapshot(repo, scope)


def post_commit_product_recovery_allowed(state: dict[str, Any], worktree: Path) -> bool:
    """Allow a committed product to resume while only reviewed knowledge changes drift.

    A deferred knowledge conflict intentionally leaves a knowledge path dirty after the
    product commit.  Once that path is restored and reviewed (or promoted), the full
    tree digest changes again, so continuity is proven by the immutable product digest
    plus the reviewed knowledge snapshot rather than by accepting arbitrary edits.
    """

    knowledge = state.get("knowledge", {})
    scope = knowledge.get("scope", [])
    publication = state.get("publication", {})
    expected_product = publication.get("post_commit_product_snapshot")
    if not expected_product and knowledge.get("status") == "blocked" and knowledge.get("conflicts"):
        # Older interrupted commits may have persisted the full post-commit
        # snapshot before the product-only marker was added.  The immutable
        # review product snapshot is the equivalent recovery anchor.
        expected_product = state.get("review", {}).get("product_snapshot")
    if not scope or not expected_product:
        return False
    if working_tree_snapshot(worktree, exclude=scope) != expected_product:
        return False
    status = knowledge.get("status")
    if status == "blocked" and knowledge.get("conflicts"):
        return True
    if status not in ("reviewed", "promoted"):
        return False
    current_knowledge = knowledge_snapshot(worktree, scope)
    return current_knowledge in {
        knowledge.get("snapshot_before"),
        knowledge.get("snapshot_after"),
    }


def _knowledge_manifest(repo: Path, scope: Sequence[str]) -> list[dict[str, Any]]:
    requested = normalize_paths(scope)
    listed = git_bytes(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    names = [item.decode("utf-8", errors="surrogateescape") for item in listed.split(b"\0") if item]
    paths: set[str] = set()
    for name in names:
        try:
            normalized = normalize_rel(name)
        except SdlcError:
            continue
        if allowed_path(normalized, requested):
            paths.add(normalized)
    for prefix in requested:
        candidate = repo / prefix
        if candidate.is_file():
            paths.add(prefix)
        elif candidate.is_dir():
            for child in candidate.rglob("*"):
                if child.is_file() and ".git" not in child.parts:
                    try:
                        paths.add(normalize_rel(str(child.relative_to(repo))))
                    except SdlcError:
                        continue
    result: list[dict[str, Any]] = []
    for path in sorted(paths):
        absolute = repo / path
        if absolute.is_file() or absolute.is_symlink():
            raw = snapshot_bytes(absolute)
            text = raw.decode("utf-8", errors="replace")
            safe_text = redact(text)
            result.append({
                "path": path,
                "sha256": digest_bytes(raw),
                "size": len(raw),
                "content": safe_text,
                "redacted": safe_text != text,
            })
        else:
            result.append({"path": path, "sha256": None, "size": 0, "content": None, "redacted": False})
    return result


def create_knowledge_candidate(state: dict[str, Any], repo: Path) -> dict[str, Any]:
    scope = state.get("knowledge", {}).get("scope", [])
    if not scope:
        state["knowledge"]["status"] = "not_needed"
        return {}
    manifest = _knowledge_manifest(repo, scope)
    manifest_by_path = {item.get("path"): item for item in manifest}
    existing_path = state.get("knowledge", {}).get("candidate_path")
    existing_sha = state.get("knowledge", {}).get("candidate_sha256")
    if existing_path and existing_sha:
        candidate_path = Path(existing_path).expanduser().resolve()
        if candidate_path.exists() and digest_bytes(candidate_path.read_bytes()) == existing_sha:
            existing = read_json(candidate_path)
            if (
                existing.get("schema") == "knowledge-candidate/v2"
                and existing.get("work_id") == state.get("work_id")
                and existing.get("revision") == candidate_revision(state)
                and normalize_paths(existing.get("scope", [])) == normalize_paths(scope)
            ):
                existing_claims = {claim.get("path"): claim for claim in existing.get("claims", []) if isinstance(claim, dict)}
                same_sources = set(existing_claims) == set(manifest_by_path) and all(
                    existing_claims[path].get("sha256") == source.get("sha256")
                    and existing_claims[path].get("size") == source.get("size")
                    and existing_claims[path].get("content") == source.get("content")
                    and existing_claims[path].get("redacted") == source.get("redacted")
                    for path, source in manifest_by_path.items()
                )
                if same_sources:
                    return existing
    candidates = state.get("candidates") or {}
    sources = [f"request:{state['task']['request_sha256']}"]
    for name in ("design", "requirements", "plan"):
        candidate = candidates.get(name) or {}
        if candidate.get("sha256"):
            sources.append(f"{name}:{candidate['sha256']}")
    claims = []
    for claim in _knowledge_manifest(repo, scope):
        enriched = dict(claim)
        enriched["source_refs"] = list(sources)
        enriched["source_sha256"] = claim.get("sha256")
        claims.append(enriched)
    payload = {
        "schema": "knowledge-candidate/v2",
        "work_id": state["work_id"],
        "revision": candidate_revision(state),
        "scope": normalize_paths(scope),
        "sources": sources,
        "certainty": "supported",
        "claims": claims,
        "created_at": now(),
    }
    root = state_root(state["repo"]["repo_id"], state_target_repo(state, repo)) / state["repo"]["repo_id"] / state["work_id"] / "knowledge"
    # A changed source manifest gets a fresh, deterministic candidate file while
    # retaining the same approved Work ID/revision.  This is the recovery path
    # after a deferred knowledge conflict; the new candidate must be reviewed
    # before it can be promoted.
    path = root / f"candidate-{candidate_revision(state)}-{digest_json(manifest)[:16]}.json"
    write_json_atomic(path, payload)
    data = path.read_bytes()
    knowledge = state["knowledge"]
    knowledge.update({
        "candidate_path": str(path),
        "candidate_sha256": digest_bytes(data),
        "sources": sources,
        "certainty": "supported",
    })
    knowledge.update({
        "status": "pending",
        "snapshot_before": None,
        "snapshot_after": None,
        "lint": None,
        "conflicts": [],
        "reviewer_id": None,
        "reviewer_session": None,
        "report_path": None,
        "report_sha256": None,
        "promotion": None,
    })
    return payload


def lint_knowledge_candidate(state: dict[str, Any], repo: Path) -> tuple[dict[str, Any], list[str]]:
    knowledge = state.get("knowledge", {})
    candidate_path = knowledge.get("candidate_path")
    if not candidate_path:
        raise SdlcError("knowledge candidate is missing")
    path = Path(candidate_path).expanduser().resolve()
    if not path.exists():
        raise SdlcError(f"knowledge candidate is missing: {path}")
    raw = path.read_bytes()
    if digest_bytes(raw) != knowledge.get("candidate_sha256"):
        raise SdlcError("knowledge candidate digest drifted; review a new candidate")
    payload = read_json(path)
    errors: list[str] = []
    if payload.get("schema") != "knowledge-candidate/v2":
        errors.append("candidate schema must be knowledge-candidate/v2")
    if payload.get("work_id") != state.get("work_id"):
        errors.append("candidate work identity does not match")
    scope = normalize_paths(knowledge.get("scope", []))
    if normalize_paths(payload.get("scope", [])) != scope:
        errors.append("candidate scope does not match approved knowledge scope")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("knowledge candidate must contain at least one source reference")
        sources = []
    seen: set[str] = set()
    for claim in payload.get("claims", []):
        if not isinstance(claim, dict) or not claim.get("path"):
            errors.append("knowledge claims must contain a path")
            continue
        try:
            item = normalize_rel(claim["path"])
        except SdlcError:
            errors.append("knowledge claim contains an invalid path")
            continue
        if item in seen:
            errors.append(f"duplicate knowledge claim: {item}")
        seen.add(item)
        if not allowed_path(item, scope):
            errors.append(f"knowledge claim is outside approved scope: {item}")
        if claim.get("certainty") not in (None, "supported"):
            errors.append(f"unsupported certainty for knowledge claim: {item}")
        claim_sources = claim.get("source_refs")
        if not isinstance(claim_sources, list) or not claim_sources or any(source not in sources for source in claim_sources):
            errors.append(f"knowledge claim has unsupported source references: {item}")
        if claim.get("source_sha256") != claim.get("sha256"):
            errors.append(f"knowledge claim source digest is missing or inconsistent: {item}")
        target = repo / item
        if target.exists() or target.is_symlink():
            try:
                actual = digest_bytes(snapshot_bytes(target))
            except OSError:
                actual = None
            if actual != claim.get("sha256"):
                errors.append(f"knowledge claim source changed before review: {item}")
        elif claim.get("sha256") is not None:
            errors.append(f"knowledge claim source is missing: {item}")
        if claim.get("content") is not None and not claim.get("redacted") and digest_text(claim["content"]) != claim.get("sha256"):
            errors.append(f"knowledge claim content digest does not match source: {item}")
    return payload, errors


def validate_knowledge_record(state: dict[str, Any]) -> None:
    knowledge = state.get("knowledge", {})
    if knowledge.get("status") not in ("reviewed", "promoted"):
        return
    candidate_path = knowledge.get("candidate_path")
    if not candidate_path:
        raise SdlcError("reviewed knowledge has no candidate path")
    path = Path(candidate_path).expanduser().resolve()
    expected_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"]
    try:
        path.relative_to(expected_root)
    except ValueError as exc:
        raise SdlcError("knowledge candidate is outside the persistent work state") from exc
    if not path.exists() or digest_bytes(path.read_bytes()) != knowledge.get("candidate_sha256"):
        raise SdlcError("knowledge candidate digest drifted; review a new candidate")
    payload = read_json(path)
    if payload.get("schema") != "knowledge-candidate/v2" or payload.get("work_id") != state.get("work_id"):
        raise SdlcError("knowledge candidate identity drifted")
    if payload.get("revision") != candidate_revision(state):
        raise SdlcError("knowledge candidate revision drifted")
    report_path = Path(str(knowledge.get("report_path", ""))).expanduser().resolve()
    report_root = expected_root / "knowledge"
    try:
        report_path.relative_to(report_root)
    except ValueError as exc:
        raise SdlcError("knowledge review report is outside the persistent work state") from exc
    if not report_path.exists() or digest_bytes(report_path.read_bytes()) != knowledge.get("report_sha256"):
        raise SdlcError("knowledge review report is missing or drifted")
    report = read_json(report_path)
    if (
        report.get("schema") != KNOWLEDGE_REVIEW_SCHEMA
        or report.get("work_id") != state.get("work_id")
        or report.get("reviewer_id") != knowledge.get("reviewer_id")
        or report.get("reviewer_session") != knowledge.get("reviewer_session")
        or report.get("candidate_sha256") != knowledge.get("candidate_sha256")
        or normalize_paths(report.get("scope", [])) != normalize_paths(knowledge.get("scope", []))
        or report.get("status") != "reviewed"
    ):
        raise SdlcError("knowledge review report is not bound to the saved candidate")


def promote_knowledge(state: dict[str, Any], repo: Path) -> None:
    knowledge = state.get("knowledge", {})
    if not knowledge.get("scope"):
        knowledge["status"] = "not_needed"
        return
    if knowledge.get("status") not in ("reviewed", "promoted"):
        raise SdlcError("knowledge promotion requires a reviewed candidate")
    before = knowledge.get("snapshot_before") or knowledge_snapshot(repo, knowledge["scope"])
    current = knowledge_snapshot(repo, knowledge["scope"])
    if knowledge.get("snapshot_before") and current != before:
        knowledge["conflicts"] = [f"knowledge scope changed after review: {', '.join(knowledge.get('scope', []))}"]
        knowledge["status"] = "blocked"
        raise SdlcError("knowledge scope changed after review; obtain a fresh knowledge review")
    payload, errors = lint_knowledge_candidate(state, repo)
    if errors:
        knowledge["lint"] = {"status": "failed", "errors": errors}
        knowledge["status"] = "blocked"
        raise SdlcError("knowledge candidate lint failed: " + "; ".join(errors))
    written: list[str] = []
    skipped_redacted: list[str] = []
    planned_writes: list[tuple[str, Path, str]] = []
    for claim in payload.get("claims", []):
        item = claim.get("path")
        content = claim.get("content")
        if not item or content is None:
            continue
        if not allowed_path(item, state.get("approval", {}).get("scope", {}).get("allowed_paths", [])):
            knowledge["conflicts"] = [f"knowledge claim is outside approved write scope: {item}"]
            knowledge["status"] = "blocked"
            raise SdlcError(f"knowledge claim is outside approved write scope: {item}")
        target = repo / item
        if claim.get("redacted"):
            skipped_redacted.append(item)
            continue
        # The writer has already changed the approved knowledge path.  Rewriting the
        # exact reviewed bytes makes the promotion idempotent and provides a concrete
        # canonical write-back for a newly created file.
        if target.exists() or target.is_symlink():
            current_sha = digest_bytes(snapshot_bytes(target))
            if current_sha != claim.get("sha256"):
                knowledge["conflicts"] = [f"canonical knowledge changed after review: {item}"]
                knowledge["status"] = "blocked"
                raise SdlcError(f"canonical knowledge changed after review: {item}")
        if not target.exists() or target.read_text(encoding="utf-8", errors="replace") != content:
            planned_writes.append((item, target, content))
    # Complete all conflict checks before changing any canonical file.  A later
    # conflict must leave the product tree untouched so a knowledge-only dispute
    # can safely proceed to product delivery with an explicit pending item.
    for item, target, content in planned_writes:
        write_text_atomic(target, content)
        written.append(item)
    knowledge["lint"] = {"status": "passed", "errors": []}
    knowledge["conflicts"] = []
    knowledge["snapshot_after"] = knowledge_snapshot(repo, knowledge["scope"])
    knowledge["promotion"] = {"written": written, "skipped_redacted": skipped_redacted, "at": now()}
    knowledge["status"] = "promoted"


def state_root(repo_id: str, repo: Path) -> Path:
    configured = os.environ.get("SDLC_STATE_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = (Path(base) if base else Path.home()) / "sdlc" / "state"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "sdlc"
    root = root.resolve()
    try:
        root.relative_to(repo)
    except ValueError:
        return root
    raise SdlcError("SDLC_STATE_ROOT must be outside the target repository")


def state_target_repo(state: dict[str, Any], fallback: Path) -> Path:
    configured = state.get("repo", {}).get("path")
    return Path(configured).expanduser().resolve() if configured else fallback.resolve()


def state_directory(repo: Path) -> Path:
    return state_root(repo_identity(repo), repo) / repo_identity(repo)


def state_path(repo: Path, work_id: str) -> Path:
    return state_directory(repo) / f"{work_id}.json"


def diagnosis_directory(repo: Path) -> Path:
    return state_root(repo_identity(repo), repo) / repo_identity(repo) / "diagnoses"


def _external_path(value: str, repo: Path) -> Path:
    path = Path(value).expanduser()
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def _diagnosis_payload_digest(payload: dict[str, Any]) -> str:
    without_digest = dict(payload)
    without_digest.pop("record_sha256", None)
    return digest_json(without_digest)


def record_diagnosis(repo: Path, args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    """Run a read-only symptom oracle and persist an auditable assessment."""

    command_text = validate_command_text(args.diagnosis_command)
    before = working_tree_snapshot(repo)
    try:
        result = run_process(parse_command(command_text), repo, timeout=300, check=False)
    except SdlcError:
        raise
    after = working_tree_snapshot(repo)
    output = redact((result.stdout or "") + (result.stderr or ""))
    output_sha = digest_text(output)
    root = diagnosis_directory(repo)
    request_sha = digest_text(args.request)
    # Include the captured output digest so a repeated diagnosis never overwrites
    # evidence referenced by an earlier assessment for the same request.
    output_path = root / f"diagnosis-{request_sha[:16]}-{output_sha[:16]}.log"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output.encode("utf-8"))
    disposition = args.disposition
    if before != after:
        disposition = "blocked"
    payload: dict[str, Any] = {
        "schema": DIAGNOSIS_SCHEMA,
        "repo_id": repo_identity(repo),
        "request": redact(args.request),
        "request_sha256": request_sha,
        "command": command_text,
        "environment": [redact(value) for value in (args.environment or [])],
        "disposition": disposition,
        "hypothesis": redact(args.hypothesis),
        "exit_code": result.returncode,
        "output_sha256": output_sha,
        "output_bytes": len(output.encode("utf-8")),
        "evidence_path": str(output_path),
        "input_snapshot": before,
        "output_snapshot": after,
        "read_only": before == after,
        "created_at": now(),
    }
    payload["record_sha256"] = _diagnosis_payload_digest(payload)
    record_path = root / f"assessment-{request_sha[:16]}-{payload['record_sha256'][:16]}.json"
    write_json_atomic(record_path, payload)
    return payload, record_path


def load_diagnosis_assessment(
    value: str,
    repo: Path,
    request: str | None = None,
    *,
    request_sha256: str | None = None,
) -> tuple[dict[str, Any], Path]:
    path = _external_path(value, repo)
    payload = read_json(path)
    if payload.get("schema") != DIAGNOSIS_SCHEMA:
        raise SdlcError("diagnosis assessment must use bug-diagnosis/v1")
    schema_errors = validate_delivery_schema(payload, DELIVERY_SCHEMA_PATH.parent / "bug-diagnosis-v1.schema.json")
    if schema_errors:
        raise SdlcError(f"diagnosis assessment schema validation failed: {'; '.join(schema_errors[:8])}")
    if payload.get("repo_id") != repo_identity(repo):
        raise SdlcError("diagnosis assessment repository identity drifted")
    expected_request_sha = request_sha256 or digest_text(request or "")
    if payload.get("request_sha256") != expected_request_sha:
        raise SdlcError("diagnosis assessment belongs to a different request")
    if payload.get("disposition") not in ("confirmed", "likely", "partial", "not-a-bug", "blocked"):
        raise SdlcError("diagnosis assessment has an unsupported disposition")
    if not payload.get("command") or not payload.get("hypothesis"):
        raise SdlcError("diagnosis assessment must include the oracle command and root-cause hypothesis")
    if payload.get("record_sha256") != _diagnosis_payload_digest(payload):
        raise SdlcError("diagnosis assessment digest drifted")
    root = diagnosis_directory(repo)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SdlcError("diagnosis assessment is outside the persistent state") from exc
    evidence_path = _external_path(str(payload.get("evidence_path", "")), repo)
    try:
        evidence_path.relative_to(root)
    except ValueError as exc:
        raise SdlcError("diagnosis evidence is outside the persistent state") from exc
    if not evidence_path.exists() or not evidence_path.is_file():
        raise SdlcError("diagnosis evidence is missing")
    evidence = evidence_path.read_bytes()
    if digest_bytes(evidence) != payload.get("output_sha256") or len(evidence) != payload.get("output_bytes"):
        raise SdlcError("diagnosis evidence digest drifted")
    if payload.get("disposition") in ("confirmed", "likely") and (payload.get("input_snapshot") != payload.get("output_snapshot") or payload.get("read_only") is not True):
        raise SdlcError("diagnosis command changed the repository; repair authorization is unavailable")
    return payload, path


def load_external_report(value: str | None, repo: Path, *, label: str) -> tuple[dict[str, Any], Path, str]:
    if not value:
        raise SdlcError(f"{label} requires an external report file")
    path = _external_path(value, repo)
    payload = read_json(path)
    schema_files = {
        DIAGNOSIS_SCHEMA: "bug-diagnosis-v1.schema.json",
        WRITER_REPORT_SCHEMA: "sdlc-writer-report-v1.schema.json",
        REVIEW_REPORT_SCHEMA: "sdlc-review-report-v1.schema.json",
        KNOWLEDGE_REVIEW_SCHEMA: "sdlc-knowledge-review-v1.schema.json",
    }
    schema_name = schema_files.get(payload.get("schema"))
    if schema_name:
        schema_errors = validate_delivery_schema(payload, DELIVERY_SCHEMA_PATH.parent / schema_name)
        if schema_errors:
            raise SdlcError(f"{label} schema validation failed: {'; '.join(schema_errors[:8])}")
    return payload, path, digest_bytes(path.read_bytes())


def persist_report(state: dict[str, Any], repo: Path, payload: dict[str, Any], *, category: str, name: str) -> tuple[str, str]:
    root = state_root(state["repo"]["repo_id"], state_target_repo(state, repo)) / state["repo"]["repo_id"] / state["work_id"] / category
    destination = root / name
    sanitized = redact_value(payload)
    write_json_atomic(destination, sanitized)
    return str(destination), digest_bytes(destination.read_bytes())


def review_evidence_root(state: dict[str, Any], repo: Path) -> Path:
    return state_root(state["repo"]["repo_id"], state_target_repo(state, repo)) / state["repo"]["repo_id"] / state["work_id"] / "reviews" / "evidence"


def _path_is_under(path: Path, roots: Sequence[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _review_evidence_item_valid(
    item: Any,
    *,
    commands: Sequence[str],
    expected_snapshot: str,
    evidence_root: Path | None = None,
) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("status") not in ("passed", "verified"):
        return False
    command = str(item.get("command", "")).strip()
    if not command or command not in commands:
        return False
    output_sha = item.get("output_sha256")
    output_bytes = item.get("output_bytes")
    if not isinstance(output_sha, str) or not SHA256_RE.fullmatch(output_sha):
        return False
    if not isinstance(output_bytes, int) or isinstance(output_bytes, bool) or output_bytes < 0:
        return False
    if item.get("input_snapshot") != expected_snapshot or item.get("output_snapshot") != expected_snapshot:
        return False
    evidence_value = item.get("evidence_path")
    if not isinstance(evidence_value, str) or not evidence_value.strip():
        return False
    if evidence_root is None:
        return True
    evidence_path = Path(evidence_value).expanduser().resolve()
    try:
        evidence_path.relative_to(evidence_root)
    except ValueError:
        return False
    if not evidence_path.exists() or not evidence_path.is_file():
        return False
    raw = evidence_path.read_bytes()
    return digest_bytes(raw) == output_sha and len(raw) == output_bytes


def normalize_review_test_evidence(
    value: Any,
    *,
    commands: Sequence[str],
    expected_snapshot: str,
    source_path: Path,
    state: dict[str, Any],
    repo: Path,
) -> list[dict[str, Any]]:
    """Verify reviewer evidence and copy redacted output into persistent state."""

    if not isinstance(value, list) or not value:
        raise SdlcError("review report test evidence must be a non-empty array")
    evidence_root = review_evidence_root(state, repo).resolve()
    allowed_roots = (
        source_path.parent.resolve(),
        evidence_root,
        evidence_root.parent.resolve(),
    )
    normalized: list[dict[str, Any]] = []
    seen_sources: set[Path] = set()
    round_number = int(state.get("review", {}).get("round") or 0) + 1
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise SdlcError(f"review test evidence item is invalid: {index}")
        if item.get("status") not in ("passed", "verified"):
            raise SdlcError(f"review test evidence is not passing: {index}")
        command = str(item.get("command", "")).strip()
        if not command or command not in commands:
            raise SdlcError(f"review test evidence uses an unapproved command: {index}")
        output_sha = item.get("output_sha256")
        output_bytes = item.get("output_bytes")
        if not isinstance(output_sha, str) or not SHA256_RE.fullmatch(output_sha):
            raise SdlcError(f"review test evidence has an invalid output digest: {index}")
        if not isinstance(output_bytes, int) or isinstance(output_bytes, bool) or output_bytes < 0:
            raise SdlcError(f"review test evidence has an invalid output length: {index}")
        if item.get("input_snapshot") != expected_snapshot or item.get("output_snapshot") != expected_snapshot:
            raise SdlcError(f"review test evidence snapshot is stale: {index}")
        evidence_value = item.get("evidence_path")
        if not isinstance(evidence_value, str) or not evidence_value.strip():
            raise SdlcError(f"review test evidence is missing its raw output path: {index}")
        source_evidence = Path(evidence_value).expanduser()
        if not source_evidence.is_absolute():
            source_evidence = source_path.parent / source_evidence
        source_evidence = source_evidence.resolve()
        if source_evidence in seen_sources:
            raise SdlcError(f"review raw output is reused for multiple evidence items: {index}")
        seen_sources.add(source_evidence)
        if not _path_is_under(source_evidence, allowed_roots):
            raise SdlcError(f"review raw output is outside the report or persistent evidence roots: {index}")
        if not source_evidence.exists() or not source_evidence.is_file():
            raise SdlcError(f"review raw output is missing: {index}")
        # Evidence written by the controller is redacted before hashing.  This
        # keeps copied reviewer output safe while preserving exact byte-level
        # freshness and digest checks for the persisted artifact.
        raw = source_evidence.read_bytes()
        persisted = redact(raw.decode("utf-8", errors="replace")).encode("utf-8")
        if digest_bytes(persisted) != output_sha or len(persisted) != output_bytes:
            raise SdlcError(f"review raw output digest does not match the report: {index}")
        destination = evidence_root / f"review-{round_number}-{index}-{output_sha[:16]}.log"
        write_bytes_atomic(destination, persisted)
        normalized_item = dict(item)
        normalized_item.update({
            "command": command,
            "evidence_path": str(destination),
            "output_sha256": digest_bytes(persisted),
            "output_bytes": len(persisted),
            "input_snapshot": expected_snapshot,
            "output_snapshot": expected_snapshot,
        })
        normalized.append(normalized_item)
    return normalized


def _report_commands_passed(value: Any, commands: Sequence[str] | None = None) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, dict) or item.get("status") not in ("passed", "verified") or not str(item.get("command", "")).strip():
            return False
        if commands is not None and item.get("command") not in commands:
            return False
    return True


def _report_commands_cover(value: Any, groups: Sequence[Sequence[str]]) -> bool:
    """Require passing evidence for every non-empty test obligation group."""

    if not _report_commands_passed(value):
        return False
    passed = {str(item.get("command")) for item in value if isinstance(item, dict)}
    return all(not group or any(command in passed for command in group) for group in groups)


def approved_verification_commands(state: dict[str, Any]) -> list[str]:
    """Return the ordered, de-duplicated full verification plan.

    The project-level commands remain first for compatibility.  Each approved
    work package then contributes its focused, related, and full obligations so
    a verification record cannot claim success after running only one shortcut.
    """

    groups: list[Sequence[str]] = [state.get("approval", {}).get("scope", {}).get("test_commands", [])]
    for task in state.get("tasks", []):
        groups.extend(
            task.get(name, []) for name in ("focused_commands", "related_commands", "full_commands")
        )
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for command in group or []:
            text = str(command)
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def stable_finding_key(value: str) -> str:
    """Derive a deterministic key; a report may provide a key to survive wording edits."""

    normalized = re.sub(r"\s+", " ", redact(value).strip().casefold())
    normalized = re.sub(r"^\[(?:blocking|major|minor)\]\s*", "", normalized)
    return f"finding-{digest_text(normalized)[:24]}"


def finding_semantic_key(item: dict[str, Any]) -> str:
    """Derive a wording-bound identity for breaker comparisons.

    Reviewers may retain an explicit key across wording edits.  When a caller
    rotates that key, the normalized finding text still provides a stable
    fallback so the no-progress breaker cannot be bypassed by renaming a
    finding.  The explicit key remains part of the saved audit record.
    """

    return stable_finding_key(str(item.get("text", "")))


def capability_root(state: dict[str, Any], repo: Path) -> Path:
    return state_root(state["repo"]["repo_id"], state_target_repo(state, repo)) / state["repo"]["repo_id"] / state["work_id"] / "capabilities"


def register_capability(
    state: dict[str, Any],
    repo: Path,
    *,
    kind: str,
    identity: str,
    session_id: str,
    assignment_id: str | None = None,
    read_only: bool = False,
) -> tuple[str, str]:
    """Issue an observable, scoped capability record for a delegated session.

    The CLI cannot authenticate an external process on its own, but it can make
    every writer/reviewer handoff explicit, one-time, and bound to the approved
    state.  The record is kept outside the repository and its digest is embedded
    in the state/ticket so a caller cannot silently replace the identity later.
    """

    if kind not in ("writer", "reviewer") or not identity.strip() or not session_id.strip():
        raise SdlcError("capability identity and session are required")
    payload = {
        "schema": "sdlc-capability/v1",
        "work_id": state["work_id"],
        "repo_id": state["repo"]["repo_id"],
        "kind": kind,
        "identity": identity,
        "session_id": session_id,
        "assignment_id": assignment_id,
        "read_only": bool(read_only),
        "scope_digest": state["approval"].get("payload_sha256"),
        "issued_at": now(),
    }
    digest = digest_json(payload)
    payload["capability_sha256"] = digest
    filename_key = f"{assignment_id}-{digest[:16]}" if assignment_id else digest[:16]
    path = capability_root(state, repo) / f"{kind}-{filename_key}.json"
    write_json_atomic(path, payload)
    return str(path), digest


def validate_capability(
    path_value: str | None,
    expected_digest: str | None,
    state: dict[str, Any],
    *,
    kind: str | None = None,
    assignment_id: str | None = None,
    identity: str | None = None,
    session_id: str | None = None,
) -> None:
    if not path_value or not expected_digest:
        raise SdlcError("delegated capability record is missing")
    path = Path(path_value).expanduser().resolve()
    root = capability_root(state, Path(state["repo"]["path"]))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SdlcError("delegated capability is outside the persistent work state") from exc
    if not path.exists():
        raise SdlcError("delegated capability record is missing")
    payload = read_json(path)
    stored = payload.pop("capability_sha256", None)
    if stored != expected_digest or digest_json(payload) != expected_digest:
        raise SdlcError("delegated capability digest drifted")
    if payload.get("work_id") != state.get("work_id") or payload.get("repo_id") != state.get("repo", {}).get("repo_id"):
        raise SdlcError("delegated capability identity drifted")
    if kind and payload.get("kind") != kind:
        raise SdlcError("delegated capability kind drifted")
    if kind == "reviewer" and payload.get("read_only") is not True:
        raise SdlcError("reviewer capability must be read-only")
    if kind == "writer" and payload.get("read_only") is not False:
        raise SdlcError("writer capability cannot be read-only")
    if assignment_id and payload.get("assignment_id") != assignment_id:
        raise SdlcError("delegated capability assignment drifted")
    if identity and payload.get("identity") != identity:
        raise SdlcError("delegated capability identity drifted")
    if session_id and payload.get("session_id") != session_id:
        raise SdlcError("delegated capability session drifted")


def validate_work_id(work_id: str) -> str:
    if not WORK_ID_RE.fullmatch(work_id) or not (3 <= len(work_id) <= 64):
        raise SdlcError("work-id must be 3-64 lowercase letters, digits, and hyphens")
    return work_id


def make_work_id(request: str) -> str:
    words = re.findall(r"[a-z0-9]+", request.casefold())[:3]
    suffix = "-".join(words) or "delivery"
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return validate_work_id(f"work-{stamp}-{suffix}"[:64])


def explore_repository(repo: Path) -> dict[str, Any]:
    """Collect read-only repository evidence used by task routing."""

    tracked_raw = git(repo, "ls-files", "-z", check=False)
    tracked = [item for item in tracked_raw.split("\0") if item]
    changed_paths, snapshot = status_paths(repo)
    top_level = sorted({item.split("/", 1)[0] for item in tracked if item})
    manifests = [
        name for name in (
            "pyproject.toml", "setup.py", "package.json", "pnpm-workspace.yaml",
            "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Makefile",
        ) if (repo / name).exists()
    ]
    return {
        "repo_id": repo_identity(repo),
        "branch": current_branch(repo),
        "head_sha": git(repo, "rev-parse", "HEAD", check=False).strip() or None,
        "working_tree_snapshot": snapshot,
        "changed_paths": changed_paths,
        "tracked_file_count": len(tracked),
        "top_level_entries": top_level[:80],
        "manifests": manifests,
        "has_repository_skills": (repo / ".agents" / "skills").is_dir(),
    }


def classify(request: str, repo: Path | None = None) -> dict[str, Any]:
    text = request.strip()
    lowered = text.casefold()
    if not text:
        result = {"task_class": "large", "reason": "empty request has material uncertainty", "confidence": "low"}
        if repo is not None:
            result["exploration"] = explore_repository(repo)
        return result
    read_terms = (
        "explain", "evaluate", "assessment", "review", "audit", "diagnos", "inspect", "status",
        "解說", "評估", "診斷", "審查", "檢視", "檢查", "唯讀", "報告",
    )
    mutating_terms = ("fix", "implement", "change", "add", "update", "modify", "edit", "更新", "修改", "改", "修", "新增", "實作", "建立", "轉型")
    bug_terms = ("bug", "defect", "regression", "broken", "failure", "error", "錯誤", "故障", "異常", "問題", "失敗")
    large_terms = (
        "architecture", "architectural", "subsystem", "migration", "schema", "contract", "api", "dependency",
        "permission", "security", "cross-module", "platform", "framework", "new system", "database",
        "架構", "子系統", "遷移", "契約", "介面", "依賴", "權限", "跨模組", "資料庫", "平台", "完整轉型",
    )
    small_terms = ("typo", "wording", "format", "readme", "docs", "documentation", "isolated", "single file", "文字", "格式", "文件")
    if any(term in lowered for term in read_terms) and not any(term in lowered for term in mutating_terms):
        result = {"task_class": "read_only", "reason": "request asks for explanation, assessment, diagnosis, or review", "confidence": "high"}
        if repo is not None:
            result["exploration"] = explore_repository(repo)
        return result
    if any(term in lowered for term in bug_terms):
        result = {"task_class": "bug", "reason": "request describes an existing failure or suspected defect; diagnose before repair", "confidence": "medium", "requires_diagnosis": True}
        if repo is not None:
            result["exploration"] = explore_repository(repo)
        return result
    if any(term in lowered for term in large_terms):
        result = {"task_class": "large", "reason": "request may change architecture, contracts, data, permissions, dependencies, or multiple modules", "confidence": "high"}
        if repo is not None:
            result["exploration"] = explore_repository(repo)
        return result
    if any(term in lowered for term in small_terms) and not any(term in lowered for term in large_terms):
        result = {"task_class": "small", "reason": "request appears isolated with a clear, bounded result", "confidence": "medium"}
        if repo is not None:
            result["exploration"] = explore_repository(repo)
        return result
    result = {"task_class": "large", "reason": "scope or impact is not sufficiently bounded to prove a small task", "confidence": "low"}
    if repo is not None:
        result["exploration"] = explore_repository(repo)
    return result


def explicit_class(request: str, requested: str | None, repo: Path | None = None) -> dict[str, Any]:
    result = classify(request, repo)
    if not requested:
        return result
    if requested not in TASK_CLASSES:
        raise SdlcError(f"unsupported task class: {requested}")
    if result["task_class"] == "read_only" and requested != "read_only":
        raise SdlcError("a read-only explanation, assessment, diagnosis, or review cannot be forced into a mutating delivery class")
    if result["task_class"] == "bug" and requested in ("small", "large"):
        raise SdlcError("a suspected bug must complete read-only diagnosis before choosing a repair class")
    if requested == "small" and result["task_class"] == "large":
        raise SdlcError("cannot downgrade an uncertain or architectural request to small; narrow and re-approve it")
    if requested == "read_only" and result["task_class"] in ("small", "large", "bug"):
        raise SdlcError("a mutating request cannot be forced into read_only")
    result["task_class"] = requested
    result["reason"] = f"explicitly selected {requested}; original exploration: {result['reason']}"
    return result


def load_config(repo: Path, *, required: bool = True) -> dict[str, Any] | None:
    path = repo / ".sdlc" / "config.json"
    if not path.exists():
        if required:
            raise SdlcError(f"project is not initialized; run `sdlc init --repo {repo}`")
        return None
    config = read_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise SdlcError(f"unsupported project configuration schema in {path}")
    if config.get("repo_id") != repo_identity(repo):
        raise SdlcError(f"project configuration repository identity drifted: {path}")
    validate_remote_name(config.get("remote"))
    return config


def parse_command(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise SdlcError("test commands must be non-empty strings")
    try:
        if os.name == "nt":
            # ``shlex.split(..., posix=True)`` treats every backslash as an
            # escape.  That is correct for POSIX shells but turns a normal
            # Windows path such as ``.\\tests\\run.py`` into ``.testsrun.py``.
            # The command is later passed directly to ``CreateProcess`` by
            # subprocess, so a small Windows-compatible tokenizer is enough:
            # quotes group an argument and backslashes remain path characters.
            command: list[str] = []
            current: list[str] = []
            quote: str | None = None
            index = 0
            while index < len(value):
                char = value[index]
                if quote:
                    if char == quote:
                        quote = None
                    else:
                        current.append(char)
                elif char in ("'", '"'):
                    quote = char
                elif char.isspace():
                    if current:
                        command.append("".join(current))
                        current = []
                else:
                    current.append(char)
                index += 1
            if quote:
                raise ValueError("No closing quotation")
            if current:
                command.append("".join(current))
        else:
            command = shlex.split(value, posix=True)
    except ValueError as exc:
        raise SdlcError(f"cannot parse test command {value!r}: {exc}") from exc
    if not command:
        raise SdlcError("test commands must contain an executable")
    return command


def validate_command_text(value: str) -> str:
    if redact(value) != value:
        raise SdlcError("test commands must not contain credential-shaped values; use environment references")
    parse_command(value)
    return value


def repo_for_scope(config: dict[str, Any] | None) -> Path:
    if config and config.get("repo_path"):
        return Path(config["repo_path"]).expanduser().resolve()
    return Path.cwd().resolve()


def build_scope(args: argparse.Namespace, config: dict[str, Any] | None) -> dict[str, Any]:
    allowed = normalize_paths(getattr(args, "allowed_path", None) or [])
    commands = list(getattr(args, "test_command", None) or [])
    if not commands and config:
        commands = list(config.get("test_commands") or [])
    # Validate now, before an approval can bind an unusable command.
    for command in commands:
        validate_command_text(command)
    knowledge = normalize_paths(getattr(args, "knowledge_path", None) or [])
    if knowledge and any(not allowed_path(path, allowed) for path in knowledge):
        raise SdlcError("knowledge scope must be contained in the approved allowed paths")
    remote = getattr(args, "remote", None)
    if remote is None and config:
        remote = config.get("remote")
    remote = validate_remote_name(remote)
    if getattr(args, "base_branch", None):
        base_branch = args.base_branch
    elif config and config.get("base_branch"):
        base_branch = config["base_branch"]
    elif config and config.get("repo_path"):
        base_branch = current_branch(Path(config["repo_path"]))
    else:
        base_branch = current_branch(Path.cwd())
    base_branch = validate_branch_name(base_branch)
    title = getattr(args, "title", None) or getattr(args, "request", None) or "SDLC delivery"
    acceptance = [redact(value) for value in (getattr(args, "acceptance", None) or [title])]
    return {
        "acceptance": acceptance,
        "allowed_paths": allowed,
        "test_commands": commands,
        "knowledge_scope": knowledge,
        "publication": {"remote": remote, "remote_url_sha256": remote_url_digest(repo_for_scope(config), remote), "base_branch": base_branch, "title": redact(title)[:200]},
    }


def approval_args(args: argparse.Namespace) -> set[str]:
    values = set()
    for value in getattr(args, "approve", None) or []:
        value = value or "integrated"
        if value not in APPROVAL_STAGES:
            raise SdlcError(f"approval stage must be one of {', '.join(APPROVAL_STAGES)}")
        values.add(value)
    if getattr(args, "approval_ref", None):
        values.add("integrated")
    if getattr(args, "requirements_approval_ref", None):
        values.add("requirements")
    if getattr(args, "plan_approval_ref", None):
        values.add("plan")
    return values


def approval_refs(args: argparse.Namespace, stage: str) -> list[str]:
    value = {
        "integrated": getattr(args, "approval_ref", None),
        "requirements": getattr(args, "requirements_approval_ref", None),
        "plan": getattr(args, "plan_approval_ref", None),
    }.get(stage)
    if value:
        return [safe_ref(value)]
    if stage in approval_args(args):
        return [f"cli:{stage}:{digest_text(str(getattr(args, 'request', 'approval')))[:16]}"]
    return []


def append_event(state: dict[str, Any], kind: str, **details: Any) -> None:
    event = {"sequence": len(state.get("events", [])) + 1, "at": now(), "kind": kind}
    event.update(details)
    state.setdefault("events", []).append(event)


def save_state(state: dict[str, Any], path: Path) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = now()
    write_json_atomic(path, state)


def assignment_ticket_payload(state: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "work_id": state["work_id"],
        "assignment_id": assignment.get("assignment_id"),
        "task_id": assignment.get("task_id"),
        "state_revision": assignment.get("state_revision"),
        "writer_id": assignment.get("writer_id", assignment.get("writer")),
        "session_id": assignment.get("session_id", assignment.get("session")),
        "approval_digest": state["approval"].get("payload_sha256"),
        "acceptance": assignment.get("acceptance", []),
        "allowed_paths": assignment.get("allowed_paths", []),
        "forbidden_paths": assignment.get("forbidden_paths", []),
        "interfaces": assignment.get("interfaces", []),
        "focused_commands": assignment.get("focused_commands", []),
        "related_commands": assignment.get("related_commands", []),
        "full_commands": assignment.get("full_commands", []),
        "test_commands": assignment.get("test_commands", []),
        "blocked_by": assignment.get("blocked_by", []),
        "depends_on": assignment.get("depends_on", []),
        "baseline_paths": assignment.get("baseline_paths", []),
        "capability_sha256": assignment.get("capability_sha256"),
    }
    # The optional field preserves compatibility with v2 assignments created
    # before content manifests were introduced.
    if "baseline_manifest" in assignment:
        payload["baseline_manifest"] = assignment.get("baseline_manifest", [])
    return payload


def assignment_digest_payload(assignment: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "assignment_id", "task_id", "writer_id", "session_id", "state_revision",
        "acceptance", "allowed_paths", "forbidden_paths", "interfaces", "focused_commands",
        "related_commands", "full_commands", "test_commands", "blocked_by", "depends_on",
        "baseline_paths", "ticket_sha256", "capability_sha256", "writer_result_sha256",
    )
    payload = {key: assignment.get(key) for key in keys}
    if "baseline_manifest" in assignment:
        payload["baseline_manifest"] = assignment.get("baseline_manifest", [])
    return payload


def load_state(repo: Path, work_id: str) -> tuple[dict[str, Any], Path]:
    validate_work_id(work_id)
    path = state_path(repo, work_id)
    state = read_json(path)
    schema_errors = validate_delivery_schema(state)
    if schema_errors:
        raise SdlcError(f"state schema validation failed: {'; '.join(schema_errors[:8])}")
    if state.get("schema") != SCHEMA:
        raise SdlcError(f"state is not a delivery-run/v2 record: {path}")
    if state.get("plugin") != "sdlc" or not compatible_plugin_version(state.get("plugin_version")):
        raise SdlcError(
            f"state is bound to unsupported sdlc plugin {state.get('plugin_version')!r}; current engine is {PLUGIN_VERSION}"
        )
    if state.get("work_id") != work_id or state.get("repo", {}).get("repo_id") != repo_identity(repo):
        raise SdlcError(f"state identity mismatch: {path}")
    task_record = state.get("task", {})
    if task_record.get("task_class") == "bug":
        assessment = task_record.get("diagnosis_assessment")
        if not isinstance(assessment, dict) or not assessment.get("path") or not assessment.get("sha256"):
            raise SdlcError(f"bug run has no bound diagnosis assessment: {path}")
        assessment_payload, assessment_path = load_diagnosis_assessment(
            assessment["path"], repo, request_sha256=task_record.get("request_sha256"),
        )
        if digest_bytes(assessment_path.read_bytes()) != assessment.get("sha256"):
            raise SdlcError(f"diagnosis assessment binding drifted: {path}")
        if assessment_payload.get("disposition") != task_record.get("diagnosis"):
            raise SdlcError(f"diagnosis disposition drifted: {path}")
        if assessment.get("disposition") != assessment_payload.get("disposition") or assessment.get("hypothesis") != assessment_payload.get("hypothesis"):
            raise SdlcError(f"diagnosis assessment summary drifted: {path}")
    try:
        expected_payload = digest_json(candidate_payload(state))
    except (KeyError, TypeError) as exc:
        raise SdlcError(f"state is missing required approval fields: {path}") from exc
    if state.get("approval", {}).get("payload_sha256") != expected_payload:
        raise SdlcError(f"approval scope digest drifted; re-plan and create a new Work ID: {path}")
    approval = state.get("approval", {})
    expected_stage_digests = {}
    for stage in sorted(set(approval.get("approved_stages", []))):
        expected_stage_digests[stage] = digest_json({
            "stage": stage,
            "candidate_revision": candidate_revision(state),
            "policy": approval.get("policy"),
            "approval_status": approval.get("status"),
            "task_class": state.get("task", {}).get("task_class"),
            "repair_class": state.get("task", {}).get("repair_class"),
            "diagnosis": state.get("task", {}).get("diagnosis"),
            "scope": approval.get("scope"),
            "candidate": _candidate_summary(candidate_for_stage(state, stage)),
            "ref": (approval.get("refs") or {}).get(stage, []),
        })
    if approval.get("stage_digests") != expected_stage_digests:
        raise SdlcError(f"approval stage digest drifted; re-plan and create a new Work ID: {path}")
    scope = approval.get("scope", {})
    try:
        configured_base = validate_branch_name(scope.get("publication", {}).get("base_branch") or state.get("repo", {}).get("base_branch"))
    except SdlcError as exc:
        raise SdlcError(f"approved base branch is invalid: {path}") from exc
    if state.get("repo", {}).get("base_branch") != configured_base or state.get("publication", {}).get("base_branch") != configured_base:
        raise SdlcError(f"base branch binding drifted: {path}")
    if any(not allowed_path(item, scope.get("allowed_paths", [])) for item in scope.get("knowledge_scope", [])):
        raise SdlcError(f"knowledge scope is outside the approved write scope: {path}")
    task_ids = [task.get("id") for task in state.get("tasks", [])]
    if len(task_ids) != len(set(task_ids)) or any(not item for item in task_ids):
        raise SdlcError(f"work package identities are not unique: {path}")
    task_id_set = set(task_ids)
    for task in state.get("tasks", []):
        dependencies = list(task.get("depends_on", [])) + list(task.get("blocked_by", []))
        if task.get("id") in dependencies or any(dependency not in task_id_set for dependency in dependencies):
            raise SdlcError(f"work package dependency graph is invalid: {path}")
    dependency_graph = {
        task.get("id"): set(task.get("depends_on", [])) | set(task.get("blocked_by", []))
        for task in state.get("tasks", [])
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit_dependency(identifier: str) -> None:
        if identifier in visiting:
            raise SdlcError(f"work package dependency graph contains a cycle: {path}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in dependency_graph.get(identifier, set()):
            visit_dependency(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
    for identifier in dependency_graph:
        visit_dependency(identifier)
    validate_candidate_bundles(state)
    validate_knowledge_record(state)
    if state.get("repo", {}).get("path") != str(repo):
        raise SdlcError(f"repository path binding drifted: {path}")
    workspace = state.get("workspace", {})
    if workspace.get("worktree"):
        worktree = Path(workspace["worktree"]).resolve()
        if not worktree.exists():
            raise SdlcError(f"delivery worktree is missing: {worktree}")
        actual_top = Path(git(worktree, "rev-parse", "--show-toplevel").strip()).resolve()
        if actual_top != worktree:
            raise SdlcError(f"delivery worktree identity drifted: {worktree}")
        if workspace.get("branch") and current_branch(worktree) != workspace["branch"]:
            raise SdlcError(f"delivery branch identity drifted: {worktree}")
    assignments = state.get("assignments", [])
    for assignment in assignments:
        if assignment.get("task_id") not in task_id_set:
            raise SdlcError(f"writer assignment references an unknown work package: {assignment.get('assignment_id')}")
        task = task_for_id(state, assignment.get("task_id"))
        if not task or any(
            assignment.get(key) != task.get(key)
            for key in (
                "acceptance", "allowed_paths", "forbidden_paths", "interfaces", "focused_commands",
                "related_commands", "full_commands", "blocked_by", "depends_on", "evidence_path",
            )
        ):
            raise SdlcError(f"writer assignment does not match its approved work package: {assignment.get('assignment_id')}")
        if not assignment.get("ticket_sha256") or not assignment.get("assignment_sha256"):
            raise SdlcError(f"writer assignment is missing its authorization ticket: {assignment.get('assignment_id')}")
        if assignment.get("ticket_sha256"):
            expected_ticket = digest_json(assignment_ticket_payload(state, assignment))
            if expected_ticket != assignment.get("ticket_sha256"):
                raise SdlcError(f"writer assignment ticket drifted: {assignment.get('assignment_id')}")
            expected_assignment = digest_json(assignment_digest_payload(assignment))
            if assignment.get("assignment_sha256") != expected_assignment:
                raise SdlcError(f"writer assignment digest drifted: {assignment.get('assignment_id')}")
        validate_capability(
            assignment.get("capability_path"), assignment.get("capability_sha256"), state,
            kind="writer", assignment_id=assignment.get("assignment_id"),
            identity=assignment.get("writer_id"), session_id=assignment.get("session_id"),
        )
        if assignment.get("status") == "completed" and not assignment.get("writer_result"):
            raise SdlcError(f"completed writer assignment has no result report: {assignment.get('assignment_id')}")
        if assignment.get("status") == "active" and assignment.get("ticket_consumed"):
            raise SdlcError(f"active writer assignment has a consumed ticket: {assignment.get('assignment_id')}")
        if assignment.get("writer_result") is not None:
            if assignment.get("writer_result_sha256") != digest_json(assignment["writer_result"]):
                raise SdlcError(f"writer result digest drifted: {assignment.get('assignment_id')}")
            result = assignment["writer_result"]
            if (
                result.get("status") not in ("completed", "needs_revision", "blocked", "awaiting_upstream")
                or (assignment.get("status") == "completed" and result.get("status") != "completed")
                or (assignment.get("status") == "needs_revision" and result.get("status") != "needs_revision")
                or (assignment.get("status") == "blocked" and result.get("status") not in ("blocked", "awaiting_upstream"))
                or result.get("reported_by") != assignment.get("writer_id")
                or result.get("session_id") != assignment.get("session_id")
                or result.get("ticket_sha256") != assignment.get("ticket_sha256")
                or result.get("task_id") != assignment.get("task_id")
                or result.get("snapshot") != assignment.get("completion_snapshot")
            ):
                raise SdlcError(f"writer result is not bound to its assignment: {assignment.get('assignment_id')}")
            result_path = Path(assignment["writer_result"].get("evidence_path", "")).expanduser().resolve()
            evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
            try:
                result_path.relative_to(evidence_root)
            except ValueError as exc:
                raise SdlcError(f"writer result evidence is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            if not result_path.exists() or read_json(result_path) != assignment["writer_result"]:
                raise SdlcError(f"writer result evidence is missing or drifted: {assignment.get('assignment_id')}")
            report_path = Path(result.get("report_path", "")).expanduser().resolve()
            try:
                report_path.relative_to(evidence_root)
            except ValueError as exc:
                raise SdlcError(f"writer report is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            if not report_path.exists() or digest_bytes(report_path.read_bytes()) != result.get("report_sha256"):
                raise SdlcError(f"writer report evidence is missing or drifted: {assignment.get('assignment_id')}")
    review = state.get("review", {})
    if review.get("verdict"):
        assignment = next((item for item in assignments if item.get("assignment_id") == review.get("assignment_id")), None)
        if not assignment or review.get("assignment_sha256") != assignment.get("assignment_sha256"):
            raise SdlcError(f"review is not bound to an assignment: {path}")
        expected_review_ticket = digest_json({
            "work_id": state["work_id"],
            "assignment_id": assignment.get("assignment_id"),
            "assignment_sha256": assignment.get("assignment_sha256"),
            "snapshot": review.get("snapshot"),
            "product_snapshot": review.get("product_snapshot"),
            "round": review.get("round"),
            "reviewer_id": review.get("reviewer_id"),
            "reviewer_session": review.get("reviewer_session"),
            "verdict": review.get("verdict"),
            "findings": review.get("findings", []),
            "test_evidence": review.get("test_evidence", []),
            "no_progress_count": review.get("no_progress_count", 0),
            "review_report_sha256": review.get("report_sha256"),
            "reviewer_capability_sha256": review.get("reviewer_capability_sha256"),
        })
        if review.get("review_ticket_sha256") != expected_review_ticket:
            raise SdlcError(f"review ticket drifted: {path}")
        if review.get("reviewer_id") == assignment.get("writer_id") or review.get("reviewer_session") == assignment.get("session_id"):
            raise SdlcError(f"reviewer is not independent from the writer: {path}")
        validate_capability(
            review.get("reviewer_capability_path"), review.get("reviewer_capability_sha256"), state,
            kind="reviewer", assignment_id=review.get("assignment_id"),
            identity=review.get("reviewer_id"), session_id=review.get("reviewer_session"),
        )
        review_report_path = Path(str(review.get("report_path", ""))).expanduser().resolve()
        review_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "reviews"
        try:
            review_report_path.relative_to(review_root)
        except ValueError as exc:
            raise SdlcError(f"review report is outside the persistent work state: {path}") from exc
        if not review_report_path.exists() or digest_bytes(review_report_path.read_bytes()) != review.get("report_sha256"):
            raise SdlcError(f"review report evidence is missing or drifted: {path}")
        try:
            review_payload = read_json(review_report_path)
        except SdlcError as exc:
            raise SdlcError(f"review report evidence is invalid: {path}") from exc
        if (
            review_payload.get("schema") != REVIEW_REPORT_SCHEMA
            or review_payload.get("work_id") != state["work_id"]
            or review_payload.get("assignment_id") != assignment.get("assignment_id")
            or review_payload.get("assignment_sha256") != assignment.get("assignment_sha256")
            or review_payload.get("reviewer_id") != review.get("reviewer_id")
            or review_payload.get("reviewer_session") != review.get("reviewer_session")
            or review_payload.get("verdict") != review.get("verdict")
            or review_payload.get("snapshot") != review.get("snapshot")
            or review_payload.get("product_snapshot") != review.get("product_snapshot")
            or review_payload.get("findings", []) != review.get("findings", [])
            or review_payload.get("test_evidence", []) != review.get("test_evidence", [])
        ):
            raise SdlcError(f"review report is not bound to the saved review: {path}")
        review_commands = list(dict.fromkeys(
            list(assignment.get("focused_commands", []))
            + list(assignment.get("related_commands", []))
            + list(assignment.get("full_commands", []))
        ))
        if (
            not _report_commands_passed(review_payload.get("test_evidence"), review_commands)
            or not _report_commands_cover(
                review_payload.get("test_evidence"),
                [assignment.get("focused_commands", []), assignment.get("related_commands", []), assignment.get("full_commands", [])],
            )
        ):
            raise SdlcError(f"review test evidence does not cover the approved obligations: {path}")
        persisted_review_evidence_root = review_root / "evidence"
        seen_review_evidence: set[Path] = set()
        for item in review_payload.get("test_evidence", []):
            evidence_path = Path(str(item.get("evidence_path", ""))).expanduser().resolve()
            if evidence_path in seen_review_evidence:
                raise SdlcError(f"review raw test evidence is reused: {path}")
            seen_review_evidence.add(evidence_path)
            if not _review_evidence_item_valid(
                item,
                commands=review_commands,
                expected_snapshot=review.get("snapshot"),
                evidence_root=persisted_review_evidence_root,
            ):
                raise SdlcError(f"review raw test evidence is missing, stale, or drifted: {path}")
    verification = state.get("verification", {})
    if verification.get("record_sha256") != digest_json(verification_payload(verification)):
        raise SdlcError(f"verification evidence digest drifted: {path}")
    verification_commands = verification.get("commands", [])
    if not isinstance(verification_commands, list):
        raise SdlcError(f"verification command evidence is malformed: {path}")
    evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
    approved_commands = approved_verification_commands(state)
    legacy_commands = list(scope.get("test_commands", []))
    for index, record in enumerate(verification_commands, 1):
        if not isinstance(record, dict) or not record.get("evidence_path"):
            raise SdlcError(f"verification command evidence is missing: {path}")
        if index <= len(approved_commands) and record.get("command") != approved_commands[index - 1]:
            raise SdlcError(f"verification command evidence is not bound to the approved command: {path}")
        evidence_path = Path(record["evidence_path"]).expanduser().resolve()
        try:
            evidence_path.relative_to(evidence_root)
        except ValueError as exc:
            raise SdlcError(f"verification evidence is outside the persistent work state: {path}") from exc
        if not evidence_path.exists() or not evidence_path.is_file():
            raise SdlcError(f"verification raw output is missing: {path}")
        evidence_bytes = evidence_path.read_bytes()
        if digest_bytes(evidence_bytes) != record.get("output_sha256") or len(evidence_bytes) != record.get("output_bytes"):
            raise SdlcError(f"verification raw output drifted: {path}")
    recorded_commands = [item.get("command") for item in verification_commands]
    if verification.get("status") == "passed" and recorded_commands not in (approved_commands, legacy_commands):
        raise SdlcError(f"verification evidence does not cover every approved command: {path}")
    publication = state.get("publication", {})
    if publication.get("push_commit_sha") and publication.get("push_commit_sha") != publication.get("commit_sha"):
        raise SdlcError(f"publication push evidence is bound to a different commit: {path}")
    if publication.get("commit_sha"):
        if not workspace.get("worktree"):
            raise SdlcError(f"committed state has no delivery worktree: {path}")
        worktree = Path(workspace["worktree"]).resolve()
        if head_sha(worktree) != publication.get("commit_sha"):
            raise SdlcError(f"saved commit SHA no longer matches the delivery branch: {path}")
        expected_snapshot = publication.get("post_commit_snapshot")
        if not expected_snapshot:
            raise SdlcError(f"committed state is missing its post-commit snapshot: {path}")
        current_snapshot = working_tree_snapshot(worktree)
        if current_snapshot != expected_snapshot:
            if not post_commit_product_recovery_allowed(state, worktree):
                raise SdlcError(f"working tree drifted after the committed review: {path}")
    return state, path


def select_work_id(repo: Path, requested: str | None) -> str:
    if requested:
        return validate_work_id(requested)
    candidates: list[str] = []
    directory = state_directory(repo)
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                load_state(repo, path.stem)
            except SdlcError:
                continue
            candidates.append(path.stem)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SdlcError("no valid v2 run exists; provide --work-id or start a run")
    raise SdlcError("multiple v2 runs exist; provide --work-id: " + ", ".join(candidates))


def candidate_revision(state: dict[str, Any]) -> str:
    return str(state.get("approval", {}).get("candidate_revision") or "candidate-1")


def bump_candidate_revision(state: dict[str, Any]) -> None:
    current = candidate_revision(state)
    match = re.fullmatch(r"candidate-(\d+)", current)
    number = int(match.group(1)) + 1 if match else 2
    state["approval"]["candidate_revision"] = f"candidate-{number}"
    state["candidates"] = {"design": None, "requirements": None, "plan": None}


def _candidate_summary(candidate: dict[str, Any] | None, *, include_path: bool = False) -> dict[str, Any] | None:
    if not candidate:
        return None
    summary = {
        "revision": candidate.get("revision"),
        "sha256": candidate.get("sha256"),
        "source_sha256": candidate.get("source_sha256"),
        "status": candidate.get("status"),
        "source_refs": list(candidate.get("source_refs", [])),
    }
    if include_path:
        summary["path"] = candidate.get("path")
    return summary


def candidate_for_stage(state: dict[str, Any], stage: str) -> dict[str, Any] | None:
    candidates = state.get("candidates") or {}
    return candidates.get("design" if stage == "integrated" else stage)


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _candidate_source(repo: Path, value: str | None, generated: str) -> tuple[str, str, str | None]:
    """Return redacted candidate text, its source digest, and a source reference."""

    if not value:
        return generated, digest_text(generated), None
    source = Path(value).expanduser()
    if not source.is_absolute():
        source = (repo / source).resolve()
    else:
        source = source.resolve()
    if not source.exists() or not source.is_file():
        raise SdlcError(f"candidate source file does not exist: {source}")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise SdlcError(f"cannot read candidate source file {source}: {exc}") from exc
    text = redact(raw.decode("utf-8", errors="replace"))
    return text, digest_bytes(raw), f"file:{digest_text(str(source))[:32]}"


def _work_package_markdown(tasks: Sequence[dict[str, Any]]) -> str:
    lines: list[str] = []
    for task in tasks:
        lines.extend([
            f"### {task.get('id')}",
            f"- Acceptance: {'; '.join(task.get('acceptance', [])) or 'none'}",
            f"- Allowed paths: {', '.join(task.get('allowed_paths', [])) or 'none'}",
            f"- Forbidden paths: {', '.join(task.get('forbidden_paths', [])) or 'none'}",
            f"- Interfaces: {'; '.join(task.get('interfaces', [])) or 'none'}",
            f"- Focused tests: {'; '.join(task.get('focused_commands', [])) or 'none'}",
            f"- Related tests: {'; '.join(task.get('related_commands', [])) or 'none'}",
            f"- Full verification: {'; '.join(task.get('full_commands', [])) or 'none'}",
            f"- Depends on: {', '.join(task.get('depends_on', [])) or 'none'}",
            f"- Blocked by: {', '.join(task.get('blocked_by', [])) or 'none'}",
            "",
        ])
    return "\n".join(lines).rstrip()


def materialize_candidate_bundles(state: dict[str, Any], repo: Path, args: argparse.Namespace) -> None:
    """Persist the exact design/requirements/plan candidates bound by v2 approvals."""

    effective = state["task"].get("repair_class") if state["task"].get("task_class") == "bug" else state["task"].get("task_class")
    existing = state.get("candidates") or {}
    revision = candidate_revision(state)
    root = state_root(state["repo"]["repo_id"], state_target_repo(state, repo)) / state["repo"]["repo_id"] / state["work_id"] / "candidates"
    scope = state["approval"]["scope"]
    request = redact(state["task"].get("request", ""))
    package_text = _work_package_markdown(state.get("tasks", []))
    test_text = "\n".join(f"- {item}" for item in scope.get("test_commands", [])) or "- none configured"

    if effective != "large":
        if existing.get("design") and not getattr(args, "design_file", None):
            validate_candidate_bundles(state)
            return
        generated = (
            f"# Integrated design candidate {revision}\n\n"
            f"## Goal\n{request}\n\n"
            "## Acceptance\n" + "\n".join(f"- {item}" for item in scope.get("acceptance", [])) + "\n\n"
            "## In scope\n" + "\n".join(f"- {item}" for item in scope.get("allowed_paths", [])) + "\n\n"
            "## Out of scope\n- Any path outside the approved scope\n- New dependencies, migrations, permissions, or contracts unless explicitly approved\n\n"
            "## Work packages\n" + package_text + "\n\n"
            "## Test commands\n" + test_text + "\n\n"
            "## Steps\n- Implement the smallest approved change.\n- Run focused and related tests for each work package.\n- Obtain an independent review and full verification before delivery.\n\n"
            "## Knowledge and publication\n"
            f"- Knowledge scope: {', '.join(scope.get('knowledge_scope', [])) or 'none'}\n"
            f"- Publication remote: {scope.get('publication', {}).get('remote') or 'none'}\n"
            f"- Base branch: {scope.get('publication', {}).get('base_branch')}\n"
            f"- Draft PR title: {scope.get('publication', {}).get('title')}\n"
        )
        design_text, source_sha, source_ref = _candidate_source(repo, getattr(args, "design_file", None), generated)
        design_path = root / f"design-{revision}.md"
        write_text_atomic(design_path, design_text)
        state["candidates"] = {
            "design": {
                "path": str(design_path),
                "sha256": digest_text(design_text),
                "source_sha256": source_sha,
                "source_refs": [f"request:{state['task']['request_sha256']}"] + ([source_ref] if source_ref else []),
                "revision": revision,
                "status": "candidate",
            },
            "requirements": None,
            "plan": None,
        }
        return

    if existing.get("requirements") and existing.get("plan") and not getattr(args, "requirements_file", None) and not getattr(args, "plan_file", None):
        validate_candidate_bundles(state)
        return
    generated_requirements = (
        f"# Requirements candidate {revision}\n\n"
        f"Request: {request}\n\n"
        "## Approved outcome\n"
        + "\n".join(f"- {item}" for item in scope.get("acceptance", []))
        + "\n\n## In scope\n"
        + "\n".join(f"- {item}" for item in scope.get("allowed_paths", []))
        + "\n\n## Out of scope\n- Any path outside the approved scope\n- Unapproved dependency, data, permission, or contract changes\n\n"
        + "## Knowledge scope\n"
        + "\n".join(f"- {item}" for item in scope.get("knowledge_scope", []))
        + "\n\n## Publication target\n"
        + f"- Remote: {scope.get('publication', {}).get('remote') or 'none'}\n- Base branch: {scope.get('publication', {}).get('base_branch')}\n- Draft PR title: {scope.get('publication', {}).get('title')}\n"
        + "\n## Work packages and test obligations\n"
        + package_text
        + "\n"
    )
    req_text, req_source_sha, req_ref = _candidate_source(repo, getattr(args, "requirements_file", None), generated_requirements)
    req_path = root / f"requirements-{revision}.md"
    write_text_atomic(req_path, req_text)
    req_obj = {
        "path": str(req_path),
        "sha256": digest_text(req_text),
        "source_sha256": req_source_sha,
        "source_refs": [f"request:{state['task']['request_sha256']}"] + ([req_ref] if req_ref else []),
        "revision": revision,
        "status": "candidate",
    }
    generated_plan = (
        f"# Technical plan candidate {revision}\n\n"
        f"Requirements candidate: {req_obj['sha256']}\n\n"
        "## Execution plan\n"
        + package_text
        + "\n\n## Verification\n"
        + test_text
        + "\n\n## Knowledge and publication\n"
        + f"- Knowledge scope: {', '.join(scope.get('knowledge_scope', [])) or 'none'}\n"
        + f"- Remote: {scope.get('publication', {}).get('remote') or 'none'}\n"
        + f"- Base branch: {scope.get('publication', {}).get('base_branch')}\n"
        + f"- Draft PR title: {scope.get('publication', {}).get('title')}\n"
    )
    plan_text, plan_source_sha, plan_ref = _candidate_source(repo, getattr(args, "plan_file", None), generated_plan)
    plan_path = root / f"plan-{revision}.md"
    write_text_atomic(plan_path, plan_text)
    plan_obj = {
        "path": str(plan_path),
        "sha256": digest_text(plan_text),
        "source_sha256": plan_source_sha,
        "source_refs": [f"requirements:{req_obj['sha256']}"] + ([plan_ref] if plan_ref else []),
        "revision": revision,
        "status": "candidate",
    }
    state["candidates"] = {"design": None, "requirements": req_obj, "plan": plan_obj}


def validate_candidate_bundles(state: dict[str, Any]) -> None:
    """Fail closed if an approved requirements/plan candidate was replaced."""

    effective = state["task"].get("repair_class") if state["task"].get("task_class") == "bug" else state["task"].get("task_class")
    candidates = state.get("candidates") or {}
    names = ("requirements", "plan") if effective == "large" else ("design",)
    for name in names:
        candidate = candidates.get(name)
        if not isinstance(candidate, dict) or not candidate.get("path"):
            raise SdlcError(f"{effective}-task {name} candidate is missing")
        path = Path(candidate["path"]).expanduser().resolve()
        expected_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"]
        try:
            path.relative_to(expected_root)
        except ValueError as exc:
            raise SdlcError(f"{name} candidate is outside the persistent work state") from exc
        if not path.exists() or not path.is_file():
            raise SdlcError(f"{effective}-task {name} candidate is missing: {path}")
        try:
            actual = digest_bytes(path.read_bytes())
        except OSError as exc:
            raise SdlcError(f"cannot read {name} candidate: {path}") from exc
        if actual != candidate.get("sha256"):
            raise SdlcError(f"{name} candidate digest drifted; re-plan and create a new Work ID")
        if candidate.get("revision") != candidate_revision(state):
            raise SdlcError(f"{name} candidate revision is not the active revision")
        candidate_stage = "integrated" if name == "design" else name
        if state.get("approval", {}).get("status") == "approved" and candidate_stage in set(state.get("approval", {}).get("approved_stages", [])) and candidate.get("status") != "approved":
            raise SdlcError(f"{name} candidate is not marked approved")


def refresh_approval_digests(state: dict[str, Any]) -> None:
    approval = state["approval"]
    approval["payload_sha256"] = digest_json(candidate_payload(state))
    stage_digests: dict[str, str] = {}
    for stage in sorted(set(approval.get("approved_stages", []))):
        stage_digests[stage] = digest_json({
            "stage": stage,
            "candidate_revision": candidate_revision(state),
            "policy": approval.get("policy"),
            "approval_status": approval.get("status"),
            "task_class": state["task"].get("task_class"),
            "repair_class": state["task"].get("repair_class"),
            "diagnosis": state["task"].get("diagnosis"),
            "scope": approval.get("scope"),
            "candidate": _candidate_summary(candidate_for_stage(state, stage)),
            "ref": (approval.get("refs") or {}).get(stage, []),
        })
    approval["stage_digests"] = stage_digests


def candidate_payload(state: dict[str, Any]) -> dict[str, Any]:
    task = state["task"]
    approval = state["approval"]
    return {
        "work_id": state["work_id"],
        "task_class": task["task_class"],
        "repair_class": task.get("repair_class"),
        "request_sha256": task["request_sha256"],
        "request": task.get("request"),
        "classification": task.get("classification"),
        "diagnosis": task.get("diagnosis"),
        "diagnosis_assessment": task.get("diagnosis_assessment"),
        "candidate_revision": approval.get("candidate_revision"),
        "policy": approval.get("policy"),
        "approval_status": approval.get("status"),
        "approved_stages": sorted(approval.get("approved_stages", [])),
        "approval_refs": approval.get("refs", {}),
        "scope": approval["scope"],
        # Dispatch packages are part of the approved candidate.  Runtime task
        # status is deliberately omitted so completing a package does not alter
        # the authorization digest, while a path, interface, command, or
        # dependency edit does invalidate the candidate.
        "work_packages": [
            {
                key: task.get(key)
                for key in (
                    "id", "acceptance", "allowed_paths", "forbidden_paths", "interfaces",
                    "focused_commands", "related_commands", "full_commands", "evidence_path",
                    "blocked_by", "depends_on",
                )
            }
            for task in state.get("tasks", [])
        ],
        "candidates": {
            "design": _candidate_summary((state.get("candidates") or {}).get("design")),
            "requirements": _candidate_summary((state.get("candidates") or {}).get("requirements")),
            "plan": _candidate_summary((state.get("candidates") or {}).get("plan")),
        },
    }


def state_summary(state: dict[str, Any], path: Path) -> dict[str, Any]:
    assignment = state.get("assignments", [])
    current_assignment = assignment[-1] if assignment else None
    return {
        "schema": state.get("schema"),
        "work_id": state.get("work_id"),
        "task_class": state.get("task", {}).get("task_class"),
        "repair_class": state.get("task", {}).get("repair_class"),
        "diagnosis": state.get("task", {}).get("diagnosis"),
        "diagnosis_assessment": (state.get("task", {}).get("diagnosis_assessment") or {}).get("path"),
        "phase": state.get("phase"),
        "status": state.get("status"),
        "approval": state.get("approval", {}).get("status"),
        "approval_policy": state.get("approval", {}).get("policy"),
        "approval_stages": state.get("approval", {}).get("approved_stages", []),
        "candidate_revision": state.get("approval", {}).get("candidate_revision"),
        # Status is the operator-facing projection, so include direct links to
        # the immutable candidate files while keeping approval digests limited
        # to content/version summaries.
        "candidates": {name: _candidate_summary(value, include_path=True) for name, value in (state.get("candidates") or {}).items()},
        "completed": [task["id"] for task in state.get("tasks", []) if task.get("status") == "completed"],
        "tasks": state.get("tasks", []),
        "current": current_assignment,
        "review": state.get("review", {}).get("verdict"),
        "review_round": state.get("review", {}).get("round", 0),
        "review_no_progress_count": state.get("review", {}).get("no_progress_count", 0),
        "review_report": state.get("review", {}).get("report_path"),
        "verification": state.get("verification", {}).get("status"),
        "knowledge": state.get("knowledge", {}).get("status"),
        "knowledge_candidate": state.get("knowledge", {}).get("candidate_path"),
        "knowledge_report": state.get("knowledge", {}).get("report_path"),
        "knowledge_conflicts": state.get("knowledge", {}).get("conflicts", []),
        "publication": state.get("publication", {}).get("state"),
        "publication_reason": state.get("publication", {}).get("reason"),
        "next_action": state.get("next_action"),
        "worktree": state.get("workspace", {}).get("worktree"),
        "branch": state.get("workspace", {}).get("branch"),
        "commit": state.get("publication", {}).get("commit_sha"),
        "state_path": str(path),
        "updated_at": state.get("updated_at"),
    }


def emit(value: Any, args: argparse.Namespace | None = None) -> None:
    if args is not None and getattr(args, "text", False):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    item = json.dumps(item, ensure_ascii=False)
                print(f"{key}: {item}")
        else:
            print(value)
        return
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def create_worktree(repo: Path, work_id: str, base_sha: str) -> tuple[Path, str]:
    branch = f"delivery/{work_id}"
    parent = repo.parent / f"{repo.name}.worktrees"
    worktree = parent / work_id
    if worktree.exists():
        raise SdlcError(f"worktree already exists: {worktree}")
    if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).strip():
        raise SdlcError(f"delivery branch already exists: {branch}")
    parent.mkdir(parents=True, exist_ok=True)
    result = run_process(("git", "worktree", "add", "-b", branch, str(worktree), base_sha), repo, timeout=120)
    if result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise SdlcError(f"cannot create delivery worktree ({result.returncode}): {detail}")
    return worktree.resolve(), branch


def task_for_id(state: dict[str, Any], task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    return next((task for task in state.get("tasks", []) if task.get("id") == task_id), None)


def next_ready_task(state: dict[str, Any]) -> dict[str, Any] | None:
    for task in state.get("tasks", []):
        if task.get("status") != "pending":
            continue
        dependencies = list(task.get("depends_on", [])) + list(task.get("blocked_by", []))
        if all((task_for_id(state, dependency) or {}).get("status") == "completed" for dependency in dependencies):
            return task
    return None


def assignment_task(state: dict[str, Any], assignment: dict[str, Any] | None) -> dict[str, Any] | None:
    return task_for_id(state, (assignment or {}).get("task_id"))


def all_tasks_completed(state: dict[str, Any]) -> bool:
    return bool(state.get("tasks")) and all(task.get("status") == "completed" for task in state.get("tasks", []))


def _work_package_specs(args: argparse.Namespace, repo: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for value in getattr(args, "work_package_file", None) or []:
        path = _external_path(value, repo)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise SdlcError(f"work-package file is not valid JSON: {path}") from exc
        entries = data.get("work_packages") if isinstance(data, dict) and "work_packages" in data else data
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise SdlcError(f"work-package file must contain an object or array: {path}")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                raise SdlcError(f"work-package file contains an invalid entry: {path}")
            identifier = str(entry["id"]).strip()
            if identifier in specs:
                raise SdlcError(f"duplicate work-package specification: {identifier}")
            specs[identifier] = entry
    return specs


def build_work_packages(args: argparse.Namespace, scope: dict[str, Any], repo: Path) -> list[dict[str, Any]]:
    requested = list(getattr(args, "work_package", None) or ["WP-001"])
    specs = _work_package_specs(args, repo)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    previous: str | None = None
    for value in requested:
        identifier = str(value).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", identifier):
            raise SdlcError("work-package IDs must contain only letters, digits, dots, underscores, or hyphens")
        if identifier in seen:
            raise SdlcError(f"duplicate work package: {identifier}")
        seen.add(identifier)
        spec = specs.get(identifier, {})
        acceptance = [redact(str(item)) for item in (spec.get("acceptance") or [f"{item} ({identifier})" for item in scope["acceptance"]])]
        allowed = normalize_paths(spec.get("allowed_paths") or scope["allowed_paths"])
        if any(not allowed_path(item, scope["allowed_paths"]) for item in allowed):
            raise SdlcError(f"work package {identifier} is outside the approved allowed paths")
        forbidden = normalize_paths(spec.get("forbidden_paths") or [])
        if any(allowed_path(item, allowed) for item in forbidden):
            raise SdlcError(f"work package {identifier} forbidden paths overlap its allowed paths")
        interfaces = [redact(str(item)) for item in (spec.get("interfaces") or [])]
        focused = [validate_command_text(str(item)) for item in (spec.get("focused_commands") or scope["test_commands"])]
        related = [validate_command_text(str(item)) for item in (spec.get("related_commands") or scope["test_commands"])]
        full = [validate_command_text(str(item)) for item in (spec.get("full_commands") or scope["test_commands"])]
        if "blocked_by" in spec or "depends_on" in spec:
            for dependency_key in ("blocked_by", "depends_on"):
                raw_dependencies = spec.get(dependency_key)
                if raw_dependencies is not None and not isinstance(raw_dependencies, list):
                    raise SdlcError(f"work package {identifier} {dependency_key} must be an array")
            blocked_by = [str(item).strip() for item in (spec.get("blocked_by") or []) if str(item).strip()]
            depends_on = [str(item).strip() for item in (spec.get("depends_on") or []) if str(item).strip()]
        else:
            blocked_by = [previous] if previous else []
            depends_on = [previous] if previous else []
        result.append({
            "id": identifier,
            "status": "pending",
            "acceptance": acceptance,
            "allowed_paths": allowed,
            "forbidden_paths": forbidden,
            "interfaces": interfaces,
            "focused_commands": focused,
            "related_commands": related,
            "full_commands": full,
            "evidence_path": f"evidence/{identifier}",
            "blocked_by": blocked_by,
            "depends_on": depends_on,
        })
        previous = identifier
    unknown = sorted(set(specs) - seen)
    if unknown:
        raise SdlcError("work-package file contains packages not requested: " + ", ".join(unknown))
    known = {task["id"] for task in result}
    for task in result:
        dependencies = list(task.get("depends_on", [])) + list(task.get("blocked_by", []))
        if task["id"] in dependencies or any(item not in known for item in dependencies):
            raise SdlcError(f"work package {task['id']} has an invalid dependency")
    graph = {task["id"]: set(task.get("depends_on", [])) | set(task.get("blocked_by", [])) for task in result}
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise SdlcError("work-package dependency graph contains a cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in graph[identifier]:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
    for identifier in graph:
        visit(identifier)
    return result


def refresh_assignment_digest(assignment: dict[str, Any]) -> None:
    assignment["assignment_sha256"] = digest_json(assignment_digest_payload(assignment))


def _new_assignment(
    state: dict[str, Any],
    args: argparse.Namespace,
    assignment_id: str,
    writer: str | None = None,
    task_id: str | None = None,
    repo: Path | None = None,
) -> dict[str, Any]:
    writer_id = writer or getattr(args, "writer_id", None) or getattr(args, "writer", None) or "implementation-writer"
    session_id = f"writer:{writer_id}"
    task = task_for_id(state, task_id) or next_ready_task(state)
    if not task:
        raise SdlcError("no uncompleted work package is ready for assignment")
    baseline_repo = Path(state.get("workspace", {}).get("worktree") or (repo or state["repo"]["path"])).resolve()
    baseline_paths, _ = status_paths(baseline_repo) if baseline_repo.exists() else ([], "")
    baseline_manifest = (
        [item for item in working_tree_manifest(baseline_repo) if item.get("path") in set(baseline_paths)]
        if baseline_repo.exists() else []
    )
    capability_path = None
    capability_sha = None
    if repo is not None:
        capability_path, capability_sha = register_capability(
            state, repo, kind="writer", identity=writer_id, session_id=session_id,
            assignment_id=assignment_id, read_only=False,
        )
    assignment = {
        "assignment_id": assignment_id,
        "task_id": task["id"],
        "writer": writer_id,
        "writer_id": writer_id,
        "session": session_id,
        "session_id": session_id,
        "state_revision": state.get("revision", 0),
        "status": "active",
        "acceptance": list(task.get("acceptance", [])),
        "allowed_paths": list(task.get("allowed_paths", state["approval"]["scope"]["allowed_paths"])),
        "forbidden_paths": list(task.get("forbidden_paths", [])),
        "interfaces": list(task.get("interfaces", [])),
        "focused_commands": list(task.get("focused_commands", state["approval"]["scope"]["test_commands"])),
        "related_commands": list(task.get("related_commands", state["approval"]["scope"]["test_commands"])),
        "full_commands": list(task.get("full_commands", state["approval"]["scope"]["test_commands"])),
        "test_commands": list(task.get("full_commands", state["approval"]["scope"]["test_commands"])),
        "blocked_by": list(task.get("blocked_by", [])),
        "depends_on": list(task.get("depends_on", [])),
        "evidence_path": task.get("evidence_path") or f"evidence/{assignment_id}",
        "baseline_paths": baseline_paths,
        "baseline_manifest": baseline_manifest,
        "capability_path": capability_path,
        "capability_sha256": capability_sha,
        "writer_result_sha256": None,
        "writer_result": None,
        "created_at": now(),
        "ticket_consumed": False,
    }
    assignment["ticket_sha256"] = digest_json(assignment_ticket_payload(state, assignment))
    refresh_assignment_digest(assignment)
    return assignment


def ensure_assignment(state: dict[str, Any], args: argparse.Namespace, repo: Path | None = None) -> None:
    if state.get("assignments"):
        return
    task = next_ready_task(state)
    if not task:
        raise SdlcError("no uncompleted work package is ready for assignment")
    task["status"] = "active"
    assignment_id = f"assignment-{len(state.get('assignments', [])) + 1}"
    state.setdefault("assignments", []).append(_new_assignment(state, args, assignment_id, task_id=task["id"], repo=repo))


def append_assignment(state: dict[str, Any], args: argparse.Namespace, repo: Path | None = None, task_id: str | None = None) -> None:
    assignment_id = f"assignment-{len(state.get('assignments', [])) + 1}"
    previous = state.get("assignments", [])[-1] if state.get("assignments") else None
    writer = (previous or {}).get("writer_id", (previous or {}).get("writer"))
    requested = getattr(args, "writer_id", None) or getattr(args, "writer", None)
    if requested and writer and requested != writer:
        raise SdlcError("a review correction must return to the assigned implementation writer")
    if task_id is None and previous and previous.get("status") == "needs_revision":
        task_id = previous.get("task_id")
    if task_id is None:
        ready = next_ready_task(state)
        if not ready:
            raise SdlcError("no dependent work package is ready for assignment")
        task_id = ready["id"]
    task = task_for_id(state, task_id)
    if not task:
        raise SdlcError(f"unknown work package: {task_id}")
    if task.get("status") == "pending":
        task["status"] = "active"
    state.setdefault("assignments", []).append(_new_assignment(state, args, assignment_id, writer=writer, task_id=task_id, repo=repo))


def base_sha_for_state(repo: Path, state: dict[str, Any]) -> str:
    """Resolve the approved configured base branch before creating a worktree."""

    configured = (
        state.get("approval", {}).get("scope", {}).get("publication", {}).get("base_branch")
        or state.get("repo", {}).get("base_branch")
        or current_branch(repo)
    )
    branch = validate_branch_name(configured)
    candidates = [f"refs/heads/{branch}"]
    remote = state.get("approval", {}).get("scope", {}).get("publication", {}).get("remote")
    if remote:
        candidates.append(f"refs/remotes/{remote}/{branch}")
    candidates.append(branch)
    for ref in candidates:
        resolved = git(repo, "rev-parse", "--verify", ref, check=False).strip()
        if resolved:
            return resolved
    raise SdlcError(f"approved base branch does not exist: {branch}")


def activate_if_approved(state: dict[str, Any], repo: Path, args: argparse.Namespace) -> None:
    task_class = state["task"]["task_class"]
    repair_class = state["task"].get("repair_class")
    effective = repair_class if task_class == "bug" else task_class
    stages = set(state["approval"].get("approved_stages", []))
    needed = {"integrated"} if effective == "small" else {"requirements", "plan"}
    for stage in stages:
        candidate = candidate_for_stage(state, stage)
        if candidate:
            candidate["status"] = "approved"
    if not needed.issubset(stages):
        state["approval"]["status"] = "pending"
        state["phase"] = "requirements" if "requirements" not in stages else "planning"
        state["status"] = "awaiting_approval"
        state["next_action"] = "obtain " + ("integrated approval" if effective == "small" else ("requirements approval" if "requirements" not in stages else "technical-plan approval"))
        refresh_approval_digests(state)
        return
    if effective == "large":
        validate_candidate_bundles(state)
    if state.get("workspace", {}).get("worktree"):
        state["approval"]["status"] = "approved"
        if not state.get("publication", {}).get("commit_sha"):
            state["status"] = "active"
        else:
            state["status"] = "complete" if state.get("publication", {}).get("state") == "draft_pr_created" else "active"
            state["phase"] = "delivery"
        refresh_approval_digests(state)
        if not state.get("assignments") and not all_tasks_completed(state):
            state["phase"] = "implementation"
            ensure_assignment(state, args, repo)
        return
    base = base_sha_for_state(repo, state)
    worktree, branch = create_worktree(repo, state["work_id"], base)
    state["workspace"] = {"worktree": str(worktree), "branch": branch, "base_sha": base, "repo": str(repo), "created_at": now()}
    state["approval"]["status"] = "approved"
    state["phase"] = "implementation"
    state["status"] = "active"
    state["next_action"] = "implementation writer executes the next uncompleted work package"
    refresh_verification_digest(state)
    refresh_approval_digests(state)
    ensure_assignment(state, args, repo)
    append_event(state, "worktree_created", phase="implementation", status="active")


def make_state(repo: Path, work_id: str, request: str, classification: dict[str, Any], args: argparse.Namespace, config: dict[str, Any] | None) -> dict[str, Any]:
    task_class = classification["task_class"]
    repair_class = getattr(args, "repair_class", None)
    diagnosis_assessment: dict[str, Any] | None = None
    if task_class != "bug" and repair_class:
        raise SdlcError("--repair-class is only valid for a diagnosed bug")
    if task_class == "bug":
        diagnosis_file = getattr(args, "diagnosis_file", None)
        if not diagnosis_file:
            raise SdlcError("bug work requires a read-only --diagnosis-file assessment before a delivery state is created")
        diagnosis_payload, diagnosis_path = load_diagnosis_assessment(diagnosis_file, repo, request)
        if diagnosis_payload.get("disposition") not in ("confirmed", "likely"):
            raise SdlcError("only confirmed or likely diagnosis assessments can enter a repair workflow")
        if getattr(args, "diagnosis", None) and args.diagnosis != diagnosis_payload.get("disposition"):
            raise SdlcError("--diagnosis does not match the supplied assessment")
        diagnosis_assessment = {
            "path": str(diagnosis_path),
            "sha256": digest_bytes(diagnosis_path.read_bytes()),
            "disposition": diagnosis_payload.get("disposition"),
            "hypothesis": diagnosis_payload.get("hypothesis"),
            "evidence_path": diagnosis_payload.get("evidence_path"),
            "output_sha256": diagnosis_payload.get("output_sha256"),
        }
        repair_class = repair_class or ("large" if "large" in request.casefold() else "small")
        if repair_class not in ("small", "large"):
            raise SdlcError("bug repair class must be small or large")
    scope = build_scope(args, {**(config or {}), "repo_path": str(repo)})
    policy = "integrated" if (repair_class or task_class) == "small" else "requirements_and_plan"
    stages = approval_args(args)
    permitted_stages = {"integrated"} if policy == "integrated" else {"requirements", "plan"}
    unexpected_stages = stages - permitted_stages
    if unexpected_stages:
        raise SdlcError(f"approval stage(s) {', '.join(sorted(unexpected_stages))} do not apply to {policy} workflow")
    if policy == "requirements_and_plan" and "plan" in stages and "requirements" not in stages:
        raise SdlcError("large-change planning approval requires a prior requirements approval")
    if policy == "requirements_and_plan" and {"requirements", "plan"}.issubset(stages):
        raise SdlcError("large-change requirements and plan approvals must be separate resume transitions")
    # An explicit --approve without a value is represented as integrated by argparse.
    request_sha = digest_text(request)
    state: dict[str, Any] = {
        "schema": SCHEMA,
        "version": 2,
        "plugin": "sdlc",
        "plugin_version": PLUGIN_VERSION,
        "work_id": work_id,
        "revision": 0,
        "repo": {"repo_id": repo_identity(repo), "path": str(repo), "base_branch": scope["publication"]["base_branch"]},
        "task": {
            "request": redact(request),
            "request_sha256": request_sha,
            "task_class": task_class,
            "repair_class": repair_class,
            "classification": classification,
            "diagnosis": diagnosis_assessment.get("disposition") if diagnosis_assessment else None,
            "diagnosis_assessment": diagnosis_assessment,
        },
        "approval": {
            "policy": policy,
            "status": "pending",
            "candidate_revision": "candidate-1",
            "approved_stages": sorted(stages),
            "refs": {stage: approval_refs(args, stage) for stage in APPROVAL_STAGES},
            "scope": scope,
            "payload_sha256": "",
            "stage_digests": {},
            "created_at": now(),
        },
        "workspace": {"worktree": None, "branch": None, "base_sha": None, "repo": str(repo), "created_at": None},
        "phase": "requirements" if policy == "requirements_and_plan" else "implementation",
        "status": "awaiting_approval",
        "tasks": build_work_packages(args, scope, repo),
        "assignments": [],
        "review": {"verdict": None, "reviewer_id": None, "reviewer_session": None, "reviewer_capability_path": None, "reviewer_capability_sha256": None, "assignment_id": None, "assignment_sha256": None, "round": 0, "review_ticket_sha256": None, "snapshot": None, "product_snapshot": None, "paths": [], "findings": [], "no_progress_count": 0, "report_path": None, "report_sha256": None, "requirements_verdict": None, "quality_verdict": None, "test_evidence": []},
        "verification": {"status": "not_run", "commands": [], "snapshot": None, "record_sha256": None},
        "knowledge": {"scope": scope["knowledge_scope"], "status": "not_needed" if not scope["knowledge_scope"] else "pending", "candidate_path": None, "candidate_sha256": None, "sources": [], "certainty": None, "snapshot_before": None, "snapshot_after": None, "lint": None, "conflicts": [], "reviewer_id": None, "reviewer_session": None, "report_path": None, "report_sha256": None, "promotion": None},
        "candidates": {"design": None, "requirements": None, "plan": None},
        "publication": {"remote": scope["publication"]["remote"], "remote_url_sha256": scope["publication"].get("remote_url_sha256"), "base_branch": scope["publication"]["base_branch"], "title": scope["publication"]["title"], "state": "not_ready", "commit_sha": None, "push_commit_sha": None, "post_commit_snapshot": None, "post_commit_product_snapshot": None, "pr": None, "reason": None},
        "events": [],
        "next_action": "obtain integrated approval" if policy == "integrated" else "obtain requirements approval",
        "created_at": now(),
        "updated_at": now(),
    }
    refresh_verification_digest(state)
    refresh_approval_digests(state)
    append_event(state, "classified", phase=state["phase"], status=state["status"], task_class=task_class)
    return state


def apply_approval_inputs(state: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "work_package", None) or getattr(args, "work_package_file", None):
        raise SdlcError("dispatch packages are fixed when the Work ID is started; create a new Work ID to change them")
    if state["approval"]["status"] == "approved":
        if any(getattr(args, name, None) for name in ("allowed_path", "test_command", "knowledge_path", "acceptance", "design_file", "requirements_file", "plan_file", "remote", "base_branch", "title")):
            raise SdlcError("approved scope is immutable; create a new revision instead of changing it")
        return
    stages = approval_args(args)
    existing_stages = set(state["approval"].get("approved_stages", []))
    permitted_stages = {"integrated"} if state["approval"].get("policy") == "integrated" else {"requirements", "plan"}
    unexpected_stages = stages - permitted_stages
    if unexpected_stages:
        raise SdlcError(f"approval stage(s) {', '.join(sorted(unexpected_stages))} do not apply to {state['approval'].get('policy')} workflow")
    if state["approval"].get("policy") == "requirements_and_plan" and {"requirements", "plan"}.issubset(stages):
        raise SdlcError("large-change requirements and plan approvals must be separate resume transitions")
    if "plan" in stages and "requirements" not in stages and "requirements" not in existing_stages:
        raise SdlcError("large-change planning approval requires a prior requirements approval")
    if stages:
        state["approval"]["approved_stages"] = sorted(existing_stages | stages)
        for stage in stages:
            refs = approval_refs(args, stage)
            if refs:
                state["approval"].setdefault("refs", {})[stage] = refs
    scope = state["approval"]["scope"]
    proposed_allowed = normalize_paths(args.allowed_path) if getattr(args, "allowed_path", None) else scope.get("allowed_paths", [])
    proposed_commands = list(args.test_command) if getattr(args, "test_command", None) else scope.get("test_commands", [])
    for command in proposed_commands:
        validate_command_text(command)
    proposed_knowledge = normalize_paths(args.knowledge_path) if getattr(args, "knowledge_path", None) else scope.get("knowledge_scope", [])
    if proposed_knowledge and any(not allowed_path(path, proposed_allowed) for path in proposed_knowledge):
        raise SdlcError("knowledge scope must be contained in the approved allowed paths")
    proposed_acceptance = [redact(value) for value in args.acceptance] if getattr(args, "acceptance", None) else scope.get("acceptance", [])
    scope_changed = (
        proposed_allowed != scope.get("allowed_paths", [])
        or proposed_commands != scope.get("test_commands", [])
        or proposed_knowledge != scope.get("knowledge_scope", [])
        or proposed_acceptance != scope.get("acceptance", [])
        or bool(getattr(args, "design_file", None))
        or bool(getattr(args, "requirements_file", None))
        or bool(getattr(args, "plan_file", None))
        or (getattr(args, "remote", None) is not None and validate_remote_name(args.remote) != scope.get("publication", {}).get("remote"))
        or (getattr(args, "base_branch", None) is not None and args.base_branch != scope.get("publication", {}).get("base_branch"))
        or (getattr(args, "title", None) is not None and redact(args.title)[:200] != scope.get("publication", {}).get("title"))
    )
    if scope_changed:
        if getattr(args, "allowed_path", None):
            scope["allowed_paths"] = proposed_allowed
        if getattr(args, "test_command", None):
            scope["test_commands"] = proposed_commands
        if getattr(args, "knowledge_path", None):
            scope["knowledge_scope"] = proposed_knowledge
            state["knowledge"]["scope"] = scope["knowledge_scope"]
            state["knowledge"]["status"] = "pending" if scope["knowledge_scope"] else "not_needed"
            state["knowledge"]["reviewer_id"] = None
            state["knowledge"]["reviewer_session"] = None
            state["knowledge"]["report_path"] = None
            state["knowledge"]["report_sha256"] = None
        if getattr(args, "acceptance", None):
            scope["acceptance"] = proposed_acceptance
        if getattr(args, "remote", None) is not None:
            scope["publication"]["remote"] = validate_remote_name(args.remote)
            scope["publication"]["remote_url_sha256"] = remote_url_digest(Path(state["repo"]["path"]), scope["publication"]["remote"])
        if getattr(args, "base_branch", None) is not None:
            scope["publication"]["base_branch"] = validate_branch_name(args.base_branch)
        if getattr(args, "title", None) is not None:
            scope["publication"]["title"] = redact(args.title)[:200]
        state["publication"]["remote"] = scope["publication"].get("remote")
        state["publication"]["remote_url_sha256"] = scope["publication"].get("remote_url_sha256")
        state["publication"]["base_branch"] = scope["publication"].get("base_branch")
        state["publication"]["title"] = scope["publication"].get("title")
        # Any scope edit creates a new candidate revision and invalidates approvals
        # collected for the previous candidate.  The caller must approve again.
        bump_candidate_revision(state)
        state["approval"]["approved_stages"] = []
        state["approval"]["refs"] = {stage: [] for stage in APPROVAL_STAGES}
        state["approval"]["status"] = "pending"
        state["review"] = {"verdict": None, "reviewer_id": None, "reviewer_session": None, "reviewer_capability_path": None, "reviewer_capability_sha256": None, "assignment_id": None, "assignment_sha256": None, "round": 0, "review_ticket_sha256": None, "snapshot": None, "product_snapshot": None, "paths": [], "findings": [], "no_progress_count": 0, "report_path": None, "report_sha256": None, "requirements_verdict": None, "quality_verdict": None, "test_evidence": []}
    refresh_approval_digests(state)
    state["approval"]["status"] = "pending"
    refresh_approval_digests(state)


def cmd_classify(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo) if getattr(args, "repo", None) else None
    result = explicit_class(args.request, args.task_class, repo)
    result["request_sha256"] = digest_text(args.request)
    result["run_created"] = False
    emit(result, args)
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Run a read-only bug oracle without creating a delivery worktree/run."""

    repo = require_git_repo(args.repo)
    payload, path = record_diagnosis(repo, args)
    result = {
        "schema": DIAGNOSIS_SCHEMA,
        "repo": str(repo),
        "repo_id": payload["repo_id"],
        "request_sha256": payload["request_sha256"],
        "command": payload["command"],
        "disposition": payload["disposition"],
        "hypothesis": payload["hypothesis"],
        "output_sha256": payload["output_sha256"],
        "read_only": payload["read_only"],
        "assessment_path": str(path),
        "assessment_sha256": payload["record_sha256"],
        "evidence_path": payload["evidence_path"],
        "run_created": False,
        "next_action": "start a diagnosed repair with --diagnosis-file <assessment>" if payload["disposition"] in ("confirmed", "likely") else "resolve the diagnosis before requesting a repair",
    }
    emit(result, args)
    return 0 if payload["disposition"] != "blocked" else 2


def cmd_init(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    path = repo / ".sdlc" / "config.json"
    existing = path.exists()
    if existing and not args.force:
        config = load_config(repo, required=True)
        emit({"initialized": False, "already_initialized": True, "config_path": str(path), "config": config}, args)
        return 0
    base_branch = validate_branch_name(args.base_branch or current_branch(repo))
    commands = list(args.test_command or [])
    for command in commands:
        validate_command_text(command)
    if not commands:
        commands = ["python -m unittest discover"]
    remote = validate_remote_name(args.remote) if args.remote is not None else ("origin" if git_remote(repo, "origin") else None)
    config = {
        "schema": CONFIG_SCHEMA,
        "plugin": "sdlc",
        "plugin_version": PLUGIN_VERSION,
        "repo_id": repo_identity(repo),
        "repo_path": str(repo),
        "base_branch": base_branch,
        "test_commands": commands,
        "remote": remote,
        "state_root_policy": "user-state-outside-repository",
        "created_at": now(),
    }
    write_json_atomic(path, config)
    emit({"initialized": True, "config_path": str(path), "config": config, "state_root": str(state_root(config["repo_id"], repo))}, args)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    config = load_config(repo, required=True)
    classification = explicit_class(args.request, args.task_class, repo)
    if classification["task_class"] == "read_only":
        emit({**classification, "request_sha256": digest_text(args.request), "run_created": False, "next_action": "report evidence; no delivery run is created"}, args)
        return 0
    if classification["task_class"] == "bug":
        if not args.diagnosis_file:
            emit({**classification, "run_created": False, "next_action": "run `sdlc diagnose` and re-run with --diagnosis-file <assessment>"}, args)
            return 0
        assessment, assessment_path = load_diagnosis_assessment(args.diagnosis_file, repo, args.request)
        if assessment.get("disposition") == "not-a-bug":
            emit({**classification, "run_created": False, "diagnosis": assessment.get("disposition"), "assessment_path": str(assessment_path), "next_action": "no repair run is authorized; if behavior should change, submit a new small or large request"}, args)
            return 0
        if assessment.get("disposition") not in ("confirmed", "likely"):
            emit({**classification, "run_created": False, "diagnosis": assessment.get("disposition"), "assessment_path": str(assessment_path), "next_action": "resolve the blocked or partial diagnosis before starting repair"}, args)
            return 0
    work_id = validate_work_id(args.work_id) if args.work_id else make_work_id(args.request)
    path = state_path(repo, work_id)
    state = make_state(repo, work_id, args.request, classification, args, config)
    reserve_state_file(path)
    try:
        materialize_candidate_bundles(state, repo, args)
        refresh_approval_digests(state)
        save_state(state, path)
        activate_if_approved(state, repo, args)
        save_state(state, path)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    emit(state_summary(state, path), args)
    return 0


def verification_payload(verification: dict[str, Any]) -> dict[str, Any]:
    return {key: verification.get(key) for key in ("status", "commands", "snapshot", "verified_at", "error")}


def refresh_verification_digest(state: dict[str, Any]) -> None:
    verification = state.setdefault("verification", {})
    verification["record_sha256"] = digest_json(verification_payload(verification))


def invalidate_verification(state: dict[str, Any]) -> None:
    """Discard verification evidence whenever a writer/review revision changes the tree."""

    state["verification"] = {"status": "not_run", "commands": [], "snapshot": None}
    refresh_verification_digest(state)


def validate_writer_report(
    state: dict[str, Any], assignment: dict[str, Any], worktree: Path, args: argparse.Namespace,
) -> tuple[dict[str, Any], str, str]:
    payload, source_path, _ = load_external_report(getattr(args, "writer_report", None), worktree, label="writer completion")
    if payload.get("schema") != WRITER_REPORT_SCHEMA:
        raise SdlcError("writer report must use sdlc-writer-report/v1")
    expected_identity = {
        "work_id": state.get("work_id"),
        "assignment_id": assignment.get("assignment_id"),
        "assignment_sha256": assignment.get("assignment_sha256"),
        "writer_id": assignment.get("writer_id"),
        "session_id": assignment.get("session_id"),
        "ticket_sha256": assignment.get("ticket_sha256"),
    }
    for key, expected in expected_identity.items():
        if payload.get(key) != expected:
            raise SdlcError(f"writer report {key} is not bound to the current assignment")
    writer_status = payload.get("status")
    if writer_status not in ("completed", "needs_revision", "blocked", "awaiting_upstream"):
        raise SdlcError("writer report has an unsupported status")
    baseline_changes = baseline_manifest_changed(assignment, worktree)
    if baseline_changes:
        raise SdlcError(
            "writer changed a path that was already dirty before this assignment: "
            + ", ".join(baseline_changes)
        )
    changed_paths = normalize_paths(payload.get("changed_paths", []))
    forbidden = assignment.get("forbidden_paths", [])
    baseline_paths = set(normalize_paths(assignment.get("baseline_paths", [])))
    if any(
        item not in baseline_paths
        and (
            not allowed_path(item, assignment.get("allowed_paths", []))
            or any(allowed_path(item, [blocked]) for blocked in forbidden)
        )
        for item in changed_paths
    ):
        raise SdlcError("writer report contains paths outside the task-specific dispatch package")
    current_paths, _ = status_paths(worktree)
    current_violations = [
        item for item in current_paths
        if item not in baseline_paths
        and (
            not allowed_path(item, assignment.get("allowed_paths", []))
            or any(allowed_path(item, [blocked]) for blocked in forbidden)
        )
    ]
    if current_violations:
        raise SdlcError("writer changed paths outside the task-specific dispatch package: " + ", ".join(current_violations))
    if changed_paths != current_paths:
        raise SdlcError("writer report changed paths do not match the current worktree")
    snapshot = working_tree_snapshot(worktree)
    if payload.get("snapshot") != snapshot:
        raise SdlcError("writer report snapshot does not match the current worktree")
    if payload.get("changed_paths") is None or not isinstance(payload.get("changed_paths"), list):
        raise SdlcError("writer report must include changed paths")
    approved_commands = list(dict.fromkeys(
        list(assignment.get("focused_commands", []))
        + list(assignment.get("related_commands", []))
        + list(assignment.get("full_commands", []))
    ))
    if writer_status == "completed" and (
        not _report_commands_passed(payload.get("tests"), approved_commands)
        or not _report_commands_cover(
            payload.get("tests"),
            [assignment.get("focused_commands", []), assignment.get("related_commands", [])],
        )
    ):
        raise SdlcError("writer report must include passing focused and related test evidence")
    stored_path, stored_sha = persist_report(
        state, worktree, payload, category="evidence", name=f"{assignment['assignment_id']}-writer-report.json",
    )
    sanitized = redact_value(payload)
    sanitized["report_path"] = stored_path
    sanitized["report_sha256"] = stored_sha
    sanitized["source_path"] = str(source_path)
    return sanitized, stored_path, stored_sha


def validate_review_report(
    state: dict[str, Any], assignment: dict[str, Any], worktree: Path, args: argparse.Namespace,
    reviewer_id: str, reviewer_session: str, verdict: str, snapshot: str,
    product_snapshot: str,
) -> tuple[dict[str, Any], str, str]:
    if getattr(args, "finding", None) or getattr(args, "finding_key", None):
        raise SdlcError("review findings must be supplied by the external --review-report")
    payload, source_path, _ = load_external_report(getattr(args, "review_report", None), worktree, label="review")
    if payload.get("schema") != REVIEW_REPORT_SCHEMA:
        raise SdlcError("review report must use sdlc-review-report/v1")
    expected_identity = {
        "work_id": state.get("work_id"),
        "assignment_id": assignment.get("assignment_id"),
        "assignment_sha256": assignment.get("assignment_sha256"),
        "reviewer_id": reviewer_id,
        "reviewer_session": reviewer_session,
        "verdict": verdict,
        "snapshot": snapshot,
        "product_snapshot": product_snapshot,
    }
    for key, expected in expected_identity.items():
        if payload.get(key) != expected:
            raise SdlcError(f"review report {key} is not bound to the current assignment snapshot")
    report_paths = normalize_paths(payload.get("paths", []))
    current_paths, _ = status_paths(worktree)
    if report_paths != current_paths:
        raise SdlcError("review report paths do not match the current worktree")
    if payload.get("requirements_verdict") not in ("APPROVED", "CHANGES_REQUIRED", "BLOCKED"):
        raise SdlcError("review report must include a requirements verdict")
    if payload.get("quality_verdict") not in ("APPROVED", "CHANGES_REQUIRED", "BLOCKED"):
        raise SdlcError("review report must include a quality verdict")
    if verdict == "APPROVED" and (payload.get("requirements_verdict") != "APPROVED" or payload.get("quality_verdict") != "APPROVED"):
        raise SdlcError("an approved review requires both requirements and quality verdicts to be APPROVED")
    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raise SdlcError("review report findings must be an array")
    approved_commands = list(dict.fromkeys(
        list(assignment.get("focused_commands", []))
        + list(assignment.get("related_commands", []))
        + list(assignment.get("full_commands", []))
    ))
    normalized_test_evidence = normalize_review_test_evidence(
        payload.get("test_evidence"),
        commands=approved_commands,
        expected_snapshot=snapshot,
        source_path=source_path,
        state=state,
        repo=worktree,
    )
    if (
        not _report_commands_passed(normalized_test_evidence, approved_commands)
        or not _report_commands_cover(
            normalized_test_evidence,
            [assignment.get("focused_commands", []), assignment.get("related_commands", []), assignment.get("full_commands", [])],
        )
    ):
        raise SdlcError("review report must include passing focused, related, and full test evidence")
    normalized_findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_findings:
        if isinstance(item, str):
            item = {"key": stable_finding_key(item), "text": item}
        if not isinstance(item, dict) or not item.get("key") or not item.get("text"):
            raise SdlcError("each review finding must include a stable key and text")
        key = str(item["key"]).strip()
        if key in seen:
            raise SdlcError("review findings contain duplicate stable keys")
        seen.add(key)
        finding = {"key": key, "text": redact(str(item["text"]))}
        if item.get("severity") is not None:
            severity = str(item["severity"]).strip().lower()
            if severity not in ("blocking", "major", "minor", "advisory"):
                raise SdlcError("review finding severity is unsupported")
            finding["severity"] = severity
        for field in ("path", "evidence", "correction"):
            if item.get(field) is not None:
                finding[field] = redact(str(item[field]))
        normalized_findings.append(finding)
    if verdict == "APPROVED" and any(
        finding.get("severity") in ("blocking", "major") for finding in normalized_findings
    ):
        raise SdlcError("an APPROVED review cannot contain blocking or major findings")
    payload = dict(payload)
    payload["findings"] = normalized_findings
    payload["test_evidence"] = normalized_test_evidence
    stored_path, stored_sha = persist_report(
        state, worktree, payload, category="reviews", name=f"review-{int(state.get('review', {}).get('round') or 0) + 1}.json",
    )
    return payload, stored_path, stored_sha


def validate_knowledge_review_report(
    state: dict[str, Any], worktree: Path, args: argparse.Namespace,
    reviewer_id: str, reviewer_session: str, candidate_payload: dict[str, Any],
    snapshot_before: list[dict[str, Any]], snapshot_after: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str]:
    """Bind an independently produced knowledge review to the exact candidate."""

    payload, source_path, _ = load_external_report(
        getattr(args, "knowledge_report", None), worktree, label="knowledge review",
    )
    if payload.get("schema") != KNOWLEDGE_REVIEW_SCHEMA:
        raise SdlcError("knowledge report must use sdlc-knowledge-review/v1")
    expected = {
        "work_id": state.get("work_id"),
        "reviewer_id": reviewer_id,
        "reviewer_session": reviewer_session,
        "candidate_sha256": state.get("knowledge", {}).get("candidate_sha256"),
        "scope": normalize_paths(state.get("knowledge", {}).get("scope", [])),
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
        "status": "reviewed",
    }
    for key, value in expected.items():
        report_value = payload.get(key)
        if key == "scope":
            try:
                report_value = normalize_paths(report_value or [])
            except SdlcError:
                raise SdlcError("knowledge report scope is invalid")
        if report_value != value:
            raise SdlcError(f"knowledge report {key} is not bound to the current candidate")
    approved_commands = list(state.get("approval", {}).get("scope", {}).get("test_commands", []))
    if not _report_commands_passed(payload.get("test_evidence"), approved_commands):
        raise SdlcError("knowledge report must include passing evidence for an approved test command")
    claim_evidence = payload.get("claim_evidence", [])
    if not isinstance(claim_evidence, list) or len(claim_evidence) < len(candidate_payload.get("claims", [])):
        raise SdlcError("knowledge report must include evidence for every candidate claim")
    if claim_evidence and not _report_commands_passed(claim_evidence):
        raise SdlcError("knowledge claim evidence must be passing")
    claim_paths = {str(claim.get("path")) for claim in candidate_payload.get("claims", []) if claim.get("path")}
    reported_claim_paths = {str(item.get("path")) for item in claim_evidence if isinstance(item, dict) and item.get("path")}
    if claim_paths and not claim_paths.issubset(reported_claim_paths):
        raise SdlcError("knowledge report claim evidence does not cover every candidate path")
    sanitized = redact_value(payload)
    sanitized["scope"] = expected["scope"]
    sanitized["source_path"] = str(source_path)
    stored_path, stored_sha = persist_report(
        state, worktree, sanitized, category="knowledge", name="review.json",
    )
    return sanitized, stored_path, stored_sha


def record_verification(state: dict[str, Any], repo: Path) -> None:
    """Run every approved command and persist fresh, content-bound evidence."""

    commands = approved_verification_commands(state)
    if not commands:
        verification = {"status": "failed", "commands": [], "snapshot": None, "error": "approved verification has no test commands"}
        state["verification"] = verification
        refresh_verification_digest(state)
        raise SdlcError("verification requires at least one approved test command")
    outcomes: list[dict[str, Any]] = []
    try:
        for index, command in enumerate(commands, 1):
            outcomes.append(capture_test(repo, state, command, index))
    except SdlcError as exc:
        state["verification"] = {"status": "failed", "commands": outcomes, "snapshot": None, "error": redact(str(exc))}
        refresh_verification_digest(state)
        raise
    if any(item.get("outcome") != "passed" for item in outcomes):
        state["verification"] = {
            "status": "failed", "commands": outcomes, "snapshot": working_tree_snapshot(repo),
            "error": "one or more approved verification commands failed, were skipped, or changed the working tree",
        }
        refresh_verification_digest(state)
        raise SdlcError("one or more approved verification commands failed, were skipped, or changed the working tree")
    verification_snapshot = working_tree_snapshot(repo)
    review_snapshot = state.get("review", {}).get("snapshot")
    knowledge = state.get("knowledge", {})
    review = state.get("review", {})
    knowledge_only_recovery = bool(
        review_snapshot
        and review_snapshot != verification_snapshot
        and knowledge.get("status") == "blocked"
        and knowledge.get("conflicts")
        and knowledge.get("scope")
        and review.get("product_snapshot")
        and working_tree_snapshot(repo, exclude=knowledge.get("scope", [])) == review.get("product_snapshot")
    )
    if review_snapshot and review_snapshot != verification_snapshot and not knowledge_only_recovery:
        state["verification"] = {
            "status": "failed", "commands": outcomes, "snapshot": verification_snapshot,
            "error": "working tree changed after review; obtain a fresh review before verification",
        }
        refresh_verification_digest(state)
        raise SdlcError("working tree changed after review; obtain a fresh review before verification")
    state["verification"] = {
        "status": "passed", "commands": outcomes, "snapshot": verification_snapshot, "verified_at": now()
    }
    refresh_verification_digest(state)
    state["phase"] = "knowledge" if state["knowledge"].get("status") not in ("not_needed", "promoted") else "delivery"
    state["next_action"] = "review and promote the approved knowledge candidate" if state["knowledge"].get("status") not in ("not_needed", "promoted") else "finish the approved delivery"
    append_event(state, "verification_recorded", phase=state["phase"], status="active")


def apply_progress_flags(state: dict[str, Any], repo: Path, args: argparse.Namespace) -> None:
    worktree = Path(state["workspace"]["worktree"]) if state.get("workspace", {}).get("worktree") else repo
    if getattr(args, "writer_complete", False):
        if state.get("phase") != "implementation" or not state.get("assignments"):
            raise SdlcError("writer completion requires an active implementation assignment")
        if state["assignments"][-1].get("status") in ("needs_revision", "blocked"):
            append_assignment(state, args, repo)
        assignment = state["assignments"][-1]
        task = assignment_task(state, assignment)
        if not task:
            raise SdlcError("writer assignment references an unknown work package")
        if task.get("status") == "completed" and assignment.get("status") == "completed":
            _writer_identity(args, assignment)
            validate_capability(
                assignment.get("capability_path"), assignment.get("capability_sha256"), state,
                kind="writer", assignment_id=assignment.get("assignment_id"),
                identity=assignment.get("writer_id"), session_id=assignment.get("session_id"),
            )
            return
        _writer_identity(args, assignment)
        validate_capability(
            assignment.get("capability_path"), assignment.get("capability_sha256"), state,
            kind="writer", assignment_id=assignment.get("assignment_id"),
            identity=assignment.get("writer_id"), session_id=assignment.get("session_id"),
        )
        writer_report, report_path, report_sha = validate_writer_report(state, assignment, worktree, args)
        invalidate_verification(state)
        writer_status = writer_report.get("status")
        if writer_status != "completed":
            task_status = "needs_revision" if writer_status == "needs_revision" else "blocked"
            task["status"] = task_status
            assignment["status"] = task_status
            assignment["ticket_consumed"] = True
            assignment["completed_at"] = now()
            completion_snapshot = working_tree_snapshot(worktree)
            assignment["completion_snapshot"] = completion_snapshot
            result_path = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence" / f"{assignment['assignment_id']}-writer.json"
            writer_result = dict(writer_report)
            writer_result.update({
                "status": writer_status, "reported_by": assignment.get("writer_id"),
                "session_id": assignment.get("session_id"), "ticket_sha256": assignment.get("ticket_sha256"),
                "task_id": assignment.get("task_id"), "snapshot": completion_snapshot,
                "evidence_path": str(result_path), "report_path": report_path, "report_sha256": report_sha, "at": now(),
            })
            write_json_atomic(result_path, writer_result)
            assignment["writer_result"] = writer_result
            assignment["writer_result_sha256"] = digest_json(writer_result)
            refresh_assignment_digest(assignment)
            state["status"] = "active" if writer_status == "needs_revision" else "blocked"
            state["phase"] = "implementation"
            state["next_action"] = (
                "issue a new writer assignment after resolving the implementation finding"
                if writer_status == "needs_revision"
                else "resolve the writer blocker or missing upstream context before resuming"
            )
            append_event(state, f"writer_{writer_status}", phase="implementation", status=state["status"], assignment_id=assignment.get("assignment_id"), task_id=task.get("id"))
            return
        task["status"] = "completed"
        assignment["status"] = "completed"
        assignment["ticket_consumed"] = True
        assignment["completed_at"] = now()
        changed_paths, _ = status_paths(worktree)
        forbidden = assignment.get("forbidden_paths", [])
        baseline_paths = set(normalize_paths(assignment.get("baseline_paths", [])))
        violations = [
            item for item in changed_paths
            if item not in baseline_paths
            and (
                not allowed_path(item, assignment.get("allowed_paths", []))
                or any(allowed_path(item, [blocked]) for blocked in forbidden)
            )
        ]
        if violations:
            task["status"] = "needs_revision"
            assignment["status"] = "needs_revision"
            assignment["ticket_consumed"] = False
            assignment.pop("completed_at", None)
            state["status"] = "blocked"
            state["next_action"] = "return out-of-scope changes to the approved writer package"
            append_event(state, "writer_scope_blocked", phase="implementation", status="blocked", assignment_id=assignment.get("assignment_id"), paths=violations)
            raise SdlcError("writer changed paths outside the task-specific dispatch package: " + ", ".join(violations))
        completion_snapshot = working_tree_snapshot(worktree)
        assignment["completion_snapshot"] = completion_snapshot
        result_path = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence" / f"{assignment['assignment_id']}-writer.json"
        writer_result = dict(writer_report)
        writer_result.update({
            "status": "completed", "reported_by": assignment.get("writer_id"),
            "session_id": assignment.get("session_id"), "ticket_sha256": assignment.get("ticket_sha256"),
            "task_id": assignment.get("task_id"), "snapshot": completion_snapshot,
            "evidence_path": str(result_path), "report_path": report_path, "report_sha256": report_sha, "at": now(),
        })
        write_json_atomic(result_path, writer_result)
        assignment["writer_result"] = writer_result
        assignment["writer_result_sha256"] = digest_json(writer_result)
        refresh_assignment_digest(assignment)
        state["next_action"] = "obtain a fresh read-only review"
        append_event(state, "writer_completed", phase="implementation", status="active", assignment_id=assignment.get("assignment_id"), task_id=task.get("id"))

    review_verdict = getattr(args, "review_verdict", None)
    if getattr(args, "review_approved", False):
        review_verdict = "APPROVED"
    if review_verdict:
        assignment = state.get("assignments", [])[-1] if state.get("assignments") else None
        task = assignment_task(state, assignment)
        if not assignment or not task or task.get("status") != "completed":
            raise SdlcError("review approval requires the current writer to report completion first")
        reviewer = getattr(args, "reviewer_id", None)
        if not reviewer:
            raise SdlcError("an independent review must include --reviewer-id")
        if assignment.get("status") != "completed":
            raise SdlcError("review must reference the completed active assignment")
        writer_id = assignment.get("writer_id") or assignment.get("writer")
        reviewer_session = getattr(args, "reviewer_session", None) or f"reviewer:{reviewer}"
        if reviewer == writer_id or reviewer_session == (assignment.get("session_id") or assignment.get("session")):
            raise SdlcError("reviewer identity/session must be independent from the implementation writer")
        previous_review = state.get("review", {})
        if previous_review.get("reviewer_session") and reviewer_session == previous_review.get("reviewer_session"):
            raise SdlcError("each review round requires a fresh reviewer session")
        reviewer_capability_path, reviewer_capability_sha = register_capability(
            state, repo, kind="reviewer", identity=reviewer, session_id=reviewer_session,
            assignment_id=assignment.get("assignment_id"), read_only=True,
        )
        paths, snapshot = status_paths(worktree)
        completion_snapshot = assignment.get("completion_snapshot")
        if completion_snapshot and snapshot != completion_snapshot:
            raise SdlcError(
                "working tree changed after writer completion; obtain a new writer report before review"
            )
        product_snapshot = working_tree_snapshot(worktree, exclude=state.get("knowledge", {}).get("scope", []))
        round_number = int(state.get("review", {}).get("round") or 0) + 1
        review_report, review_report_path, review_report_sha = validate_review_report(
            state, assignment, worktree, args, reviewer, reviewer_session, review_verdict, snapshot, product_snapshot,
        )
        invalidate_verification(state)
        findings = list(review_report.get("findings", []))
        previous_review = state.get("review", {})
        previous_keys = sorted(
            item.get("key") for item in previous_review.get("findings", [])
            if isinstance(item, dict) and item.get("key")
        )
        current_keys = sorted(item["key"] for item in findings)
        previous_semantic_keys = sorted(
            finding_semantic_key(item) for item in previous_review.get("findings", [])
            if isinstance(item, dict) and item.get("text")
        )
        current_semantic_keys = sorted(finding_semantic_key(item) for item in findings if item.get("text"))
        same_unresolved_finding = (
            review_verdict == "CHANGES_REQUIRED"
            and previous_review.get("verdict") == "CHANGES_REQUIRED"
            and previous_review.get("snapshot") == snapshot
            and (previous_keys == current_keys or previous_semantic_keys == current_semantic_keys)
        )
        no_progress_count = int(previous_review.get("no_progress_count") or 0) + 1 if same_unresolved_finding else 0
        review_ticket = _review_ticket(
            state, assignment, snapshot, args, round_number, reviewer, reviewer_session,
            review_verdict, findings, review_report.get("test_evidence", []),
            reviewer_capability_sha, no_progress_count, review_report_sha, product_snapshot,
        )
        state["review"] = {
            "verdict": review_verdict, "reviewer_id": reviewer, "reviewer_session": reviewer_session,
            "reviewer_capability_path": reviewer_capability_path, "reviewer_capability_sha256": reviewer_capability_sha,
            "assignment_id": assignment.get("assignment_id"), "assignment_sha256": assignment.get("assignment_sha256"),
            "round": round_number, "review_ticket_sha256": review_ticket, "snapshot": snapshot, "paths": paths,
            "product_snapshot": product_snapshot,
            "findings": findings, "no_progress_count": no_progress_count, "reviewed_at": now(),
            "report_path": review_report_path, "report_sha256": review_report_sha,
            "requirements_verdict": review_report.get("requirements_verdict"),
            "quality_verdict": review_report.get("quality_verdict"),
            "test_evidence": review_report.get("test_evidence", []),
        }
        if review_verdict == "APPROVED":
            # A fresh review is also the explicit recovery action after a
            # previous reviewer blocker.  Do not leave a successfully resumed
            # run reporting the stale blocked status.
            state["status"] = "active"
            if all_tasks_completed(state):
                state["phase"] = "verification"
                state["next_action"] = "run the approved verification commands"
                append_event(state, "fresh_review_approved", phase="verification", status="active", task_id=task.get("id"))
            else:
                next_task = next_ready_task(state)
                if not next_task:
                    raise SdlcError("review approved a task but no dependent work package is ready")
                append_assignment(state, args, repo, task_id=next_task.get("id"))
                state["phase"] = "implementation"
                state["next_action"] = "implementation writer executes the next uncompleted work package"
                append_event(state, "fresh_review_approved", phase="implementation", status="active", task_id=task.get("id"))
        elif review_verdict == "CHANGES_REQUIRED":
            if no_progress_count >= 2:
                state["status"] = "blocked"
                state["phase"] = "implementation"
                state["next_action"] = "replace the unresolved review evidence or create a new approved plan"
                append_event(state, "review_no_progress_breaker", phase="implementation", status="blocked", task_id=task.get("id"), no_progress_count=no_progress_count)
                return
            task["status"] = "needs_revision"
            # Keep the historical completed assignment immutable.  A review
            # correction is represented by a new one-time assignment; changing
            # the old status would make its completed writer evidence disagree
            # with the report it records.
            # Issue the next one-time writer ticket as part of the reviewer
            # handoff.  The consumed ticket can never be reused to perform the
            # correction; the fresh assignment is visible in the review result.
            append_assignment(state, args, repo, task_id=task.get("id"))
            state["phase"] = "implementation"
            state["status"] = "active"
            state["next_action"] = "return findings to the same implementation writer"
            append_event(state, "fresh_review_changes_required", phase="implementation", status="active", task_id=task.get("id"))
        else:
            state["status"] = "blocked"
            state["phase"] = "verification"
            state["next_action"] = "resolve the reviewer blocker and resume with a fresh review"
            append_event(state, "fresh_review_blocked", phase="verification", status="blocked", task_id=task.get("id"))

    # ``--verified`` is retained as a compatibility spelling for a request to
    # verify now.  It always executes the approved commands and records their
    # output; it can never manufacture a successful evidence record.
    if getattr(args, "verified", False):
        record_verification(state, worktree)

    if getattr(args, "knowledge_reviewed", False):
        if not state.get("knowledge", {}).get("scope"):
            state["knowledge"]["status"] = "not_needed"
        else:
            if state.get("review", {}).get("verdict") != "APPROVED":
                raise SdlcError("knowledge review requires an approved fresh code review")
            if state.get("verification", {}).get("status") not in ("passed", "verified"):
                raise SdlcError("knowledge review requires fresh verification")
            reviewer = getattr(args, "reviewer_id", None)
            if not reviewer:
                raise SdlcError("a knowledge review must include --reviewer-id")
            assignment = state.get("assignments", [])[-1]
            writer_id = assignment.get("writer_id") or assignment.get("writer")
            if reviewer == writer_id:
                raise SdlcError("knowledge reviewer identity must be independent from the implementation writer")
            candidate = create_knowledge_candidate(state, worktree)
            payload, lint_errors = lint_knowledge_candidate(state, worktree)
            snapshot_before = knowledge_snapshot(worktree, state["knowledge"]["scope"])
            state["knowledge"]["snapshot_before"] = snapshot_before
            state["knowledge"]["snapshot_after"] = snapshot_before
            state["knowledge"]["lint"] = {"status": "passed" if not lint_errors else "failed", "errors": lint_errors}
            state["knowledge"]["conflicts"] = []
            if lint_errors:
                state["knowledge"]["status"] = "blocked"
                raise SdlcError("knowledge candidate lint failed: " + "; ".join(lint_errors))
            reviewer_session = getattr(args, "reviewer_session", None) or f"reviewer:{reviewer}"
            if reviewer_session == (assignment.get("session_id") or assignment.get("session")):
                raise SdlcError("knowledge reviewer session must be independent from the implementation writer")
            knowledge_report, knowledge_report_path, knowledge_report_sha = validate_knowledge_review_report(
                state, worktree, args, reviewer, reviewer_session, candidate, snapshot_before, snapshot_before,
            )
            state["knowledge"]["status"] = "reviewed"
            state["knowledge"]["reviewer_id"] = reviewer
            state["knowledge"]["reviewer_session"] = reviewer_session
            state["knowledge"]["report_path"] = knowledge_report_path
            state["knowledge"]["report_sha256"] = knowledge_report_sha
            state["knowledge"]["certainty"] = payload.get("certainty", "supported")
            append_event(state, "knowledge_reviewed", phase="knowledge", status="active")
    if getattr(args, "knowledge_promoted", False):
        if state.get("knowledge", {}).get("scope"):
            if state.get("knowledge", {}).get("status") == "promoted":
                return
            if state.get("knowledge", {}).get("status") != "reviewed":
                raise SdlcError("knowledge promotion requires a reviewed candidate")
            if state.get("verification", {}).get("status") not in ("passed", "verified"):
                raise SdlcError("knowledge promotion requires fresh verification")
            promote_knowledge(state, worktree)
            append_event(state, "knowledge_promoted", phase="delivery", status="active")
        else:
            state["knowledge"]["status"] = "not_needed"


def apply_escalation(state: dict[str, Any], args: argparse.Namespace) -> None:
    if not getattr(args, "escalate", False):
        return
    task = state["task"]
    current = task.get("repair_class") if task.get("task_class") == "bug" else task.get("task_class")
    if current != "small":
        raise SdlcError("only a small task can be escalated to the large-change path")
    state.setdefault("superseded_approvals", []).append({
        "policy": state["approval"].get("policy"),
        "stages": list(state["approval"].get("approved_stages", [])),
        "payload_sha256": state["approval"].get("payload_sha256"),
        "at": now(),
    })
    if task.get("task_class") == "bug":
        task["repair_class"] = "large"
    else:
        task["task_class"] = "large"
    task["escalated_from"] = "small"
    state["approval"]["policy"] = "requirements_and_plan"
    state["approval"]["status"] = "pending"
    bump_candidate_revision(state)
    state["approval"]["approved_stages"] = []
    state["approval"]["refs"] = {"integrated": [], "requirements": [], "plan": []}
    state["phase"] = "requirements"
    state["status"] = "awaiting_approval"
    state["review"] = {"verdict": None, "reviewer_id": None, "reviewer_session": None, "reviewer_capability_path": None, "reviewer_capability_sha256": None, "assignment_id": None, "assignment_sha256": None, "round": 0, "review_ticket_sha256": None, "snapshot": None, "product_snapshot": None, "paths": [], "findings": [], "no_progress_count": 0, "report_path": None, "report_sha256": None, "requirements_verdict": None, "quality_verdict": None, "test_evidence": []}
    state["assignments"] = []
    for task in state.get("tasks", []):
        task["status"] = "pending"
    refresh_approval_digests(state)
    state["next_action"] = "re-approve the expanded requirements and technical plan"
    append_event(state, "scope_escalated", phase="requirements", status="awaiting_approval")


def acquire_state_lock(path: Path) -> Path:
    """Acquire a short-lived cross-process lock for a state mutation."""

    lock = Path(str(path) + ".lock")
    descriptor = -1
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii", errors="ignore"))
        os.close(descriptor)
    except FileExistsError as exc:
        raise SdlcError(f"state mutation is already in progress: {path.stem}") from exc
    except Exception:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except Exception:
                pass
        try:
            os.unlink(lock)
        except OSError:
            pass
        raise
    return lock


def release_state_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _cmd_resume_locked(args: argparse.Namespace, repo: Path) -> int:
    load_config(repo, required=True)
    state, path = load_state(repo, args.work_id)
    if getattr(args, "request", "") and redact(args.request) != state.get("task", {}).get("request"):
        raise SdlcError("request differs from the approved Work ID candidate; start a new Work ID")
    apply_escalation(state, args)
    apply_approval_inputs(state, args)
    materialize_candidate_bundles(state, repo, args)
    refresh_approval_digests(state)
    activate_if_approved(state, repo, args)
    progress_repo = Path(state["workspace"]["worktree"]) if state.get("workspace", {}).get("worktree") else repo
    try:
        apply_progress_flags(state, progress_repo, args)
    except SdlcError:
        if state.get("verification", {}).get("status") == "failed":
            state["status"] = "blocked"
            state["phase"] = "verification"
        # Persist blocker, conflict, or handoff evidence before surfacing the
        # error.  Resume must never lose a reviewed candidate or a failed
        # verification merely because the command returned non-zero.
        save_state(state, path)
        raise
    if getattr(args, "publish", False) and state.get("publication", {}).get("commit_sha"):
        finish_publication(state, Path(state["workspace"]["worktree"]), args)
        state["phase"] = "delivery"
        state["status"] = "complete" if state.get("publication", {}).get("state") == "draft_pr_created" else "active"
    save_state(state, path)
    emit(state_summary(state, path), args)
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    args.work_id = select_work_id(repo, args.work_id)
    lock = acquire_state_lock(state_path(repo, args.work_id))
    try:
        return _cmd_resume_locked(args, repo)
    finally:
        release_state_lock(lock)


def _writer_identity(args: argparse.Namespace, assignment: dict[str, Any]) -> tuple[str, str]:
    requested = getattr(args, "writer_id", None)
    legacy = getattr(args, "writer", None)
    writer = requested or legacy or assignment.get("writer_id") or assignment.get("writer")
    expected = assignment.get("writer_id") or assignment.get("writer")
    if writer != expected:
        raise SdlcError("writer identity does not match the active assignment")
    ticket = getattr(args, "writer_ticket", None)
    if not ticket:
        raise SdlcError("writer completion requires the current assignment --writer-ticket")
    if ticket != assignment.get("ticket_sha256"):
        raise SdlcError("writer assignment ticket is invalid or already belongs to another assignment")
    if assignment.get("ticket_consumed"):
        raise SdlcError("writer assignment ticket has already been consumed")
    return str(writer), str(ticket)


def _review_ticket(
    state: dict[str, Any],
    assignment: dict[str, Any],
    snapshot: str,
    args: argparse.Namespace,
    round_number: int,
    reviewer_id: str,
    reviewer_session: str,
    verdict: str,
    findings: Sequence[dict[str, str]],
    test_evidence: Sequence[dict[str, Any]],
    reviewer_capability_sha256: str,
    no_progress_count: int,
    review_report_sha256: str,
    product_snapshot: str,
) -> str:
    expected = digest_json({
        "work_id": state["work_id"],
        "assignment_id": assignment.get("assignment_id"),
        "assignment_sha256": assignment.get("assignment_sha256"),
        "snapshot": snapshot,
        "product_snapshot": product_snapshot,
        "round": round_number,
        "reviewer_id": reviewer_id,
        "reviewer_session": reviewer_session,
        "verdict": verdict,
        "findings": list(findings),
        "test_evidence": list(test_evidence),
        "no_progress_count": no_progress_count,
        "review_report_sha256": review_report_sha256,
        "reviewer_capability_sha256": reviewer_capability_sha256,
    })
    supplied = getattr(args, "review_ticket", None)
    if supplied and supplied != "auto" and supplied != expected:
        raise SdlcError("review ticket is invalid or does not match the current assignment snapshot")
    return expected


def cmd_status(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    load_config(repo, required=False)
    directory = state_directory(repo)
    if args.work_id:
        state, path = load_state(repo, args.work_id)
        emit(state_summary(state, path), args)
        return 0
    records: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                state, validated_path = load_state(repo, path.stem)
                records.append(state_summary(state, validated_path))
            except SdlcError:
                invalid.append({"path": str(path), "reason": "invalid v2 state; inspect with doctor --work-id"})
    emit({"repo": str(repo), "repo_id": repo_identity(repo), "state_root": str(directory.parent), "runs": records, "invalid_runs": invalid}, args)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    requested = Path(args.repo).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    try:
        repo = require_git_repo(requested)
        checks.append({"name": "git_repository", "ok": True, "path": str(repo)})
    except SdlcError as exc:
        checks.append({"name": "git_repository", "ok": False, "detail": str(exc)})
        emit({"ok": False, "checks": checks}, args)
        return 1
    config_error = None
    try:
        config = load_config(repo, required=False)
    except SdlcError as exc:
        config = None
        config_error = str(exc)
    config_check = {"name": "project_config", "ok": config is not None, "path": str(repo / ".sdlc" / "config.json")}
    if config_error:
        config_check["detail"] = config_error
    checks.append(config_check)
    try:
        root = state_root(repo_identity(repo), repo)
        checks.append({"name": "state_root_outside_repo", "ok": True, "path": str(root)})
    except SdlcError as exc:
        checks.append({"name": "state_root_outside_repo", "ok": False, "detail": str(exc)})
    checks.append({"name": "python", "ok": True, "version": sys.version.split()[0]})
    checks.append({"name": "rg", "ok": shutil.which("rg") is not None})
    checks.append({"name": "git", "ok": shutil.which("git") is not None})
    checks.append({"name": "gh", "ok": shutil.which("gh") is not None, "optional": True})
    checks.append({"name": "portable_contract", "ok": DELIVERY_SCHEMA_PATH.exists(), "path": str(DELIVERY_SCHEMA_PATH)})
    runs = []
    invalid_runs = []
    try:
        directory = state_directory(repo)
    except SdlcError:
        directory = None
    if directory and directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                state, validated_path = load_state(repo, path.stem)
                runs.append(state_summary(state, validated_path))
            except SdlcError:
                invalid_runs.append({"path": str(path), "reason": "invalid v2 state"})
    if args.work_id:
        try:
            state, path = load_state(repo, args.work_id)
            runs = [state_summary(state, path)]
            checks.append({"name": "writer_assignment", "ok": (not state.get("assignments")) or bool(state["assignments"][-1].get("ticket_sha256")), "detail": "one ticketed writer assignment is present"})
            checks.append({"name": "state_mutation_lock", "ok": not Path(str(path) + ".lock").exists(), "detail": "no stale state mutation lock is present"})
            scope = state.get("approval", {}).get("scope", {})
            assignments = state.get("assignments", [])
            approved_paths = scope.get("allowed_paths", [])
            scope_ok = all(
                all(allowed_path(path, approved_paths) for path in item.get("allowed_paths", []))
                and all(allowed_path(path, approved_paths) for path in item.get("forbidden_paths", []))
                for item in assignments
            )
            checks.append({"name": "approved_scope_binding", "ok": scope_ok, "detail": "assignment paths stay within the approved scope"})
            approved_remote = state.get("publication", {}).get("remote")
            remote_ok = (not approved_remote) or remote_url_digest(repo, approved_remote) == state.get("publication", {}).get("remote_url_sha256")
            checks.append({"name": "publication_destination", "ok": remote_ok, "detail": "configured remote matches the approved destination"})
            if state.get("review", {}).get("verdict"):
                checks.append({"name": "independent_review_binding", "ok": bool(state["review"].get("review_ticket_sha256")) and state["review"].get("reviewer_id") != (assignments[-1].get("writer_id") if assignments else None), "detail": "review has a ticket and a distinct reviewer"})
        except SdlcError as exc:
            checks.append({"name": "requested_run", "ok": False, "detail": str(exc)})
    if invalid_runs:
        checks.append({"name": "v2_state_integrity", "ok": False, "invalid_runs": invalid_runs})
    ok = all(check["ok"] or check.get("optional") for check in checks)
    emit({"ok": ok, "repo": str(repo), "repo_id": repo_identity(repo), "checks": checks, "runs": runs, "invalid_runs": invalid_runs}, args)
    return 0 if ok else 1


def capture_test(repo: Path, state: dict[str, Any], command_text: str, index: int) -> dict[str, Any]:
    command = parse_command(command_text)
    input_snapshot = working_tree_snapshot(repo)
    result = run_process(command, repo, timeout=300, check=False)
    output_snapshot = working_tree_snapshot(repo)
    output = redact((result.stdout or "") + (result.stderr or ""))
    evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
    evidence_path = evidence_root / f"test-{index}.log"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    # Write bytes explicitly so the digest is identical on Windows and POSIX;
    # text-mode newline translation would otherwise turn ``\n`` into ``\r\n``.
    evidence_path.write_bytes(output.encode("utf-8"))
    skipped_count = len(re.findall(r"\b(?:skipped?|not[ -]?run|xfail)\b", output.casefold()))
    tree_changed = input_snapshot != output_snapshot
    outcome = "passed" if result.returncode == 0 and skipped_count == 0 and not tree_changed else "failed"
    return {
        "command": command_text,
        "outcome": outcome,
        "exit_code": result.returncode,
        "skipped_count": skipped_count,
        "output_sha256": digest_text(output),
        "output_bytes": len(output.encode("utf-8")),
        "evidence_path": str(evidence_path),
        "input_snapshot": input_snapshot,
        "output_snapshot": output_snapshot,
        "tree_changed": tree_changed,
        "at": now(),
    }


def verify_scope(repo: Path, allowed: Sequence[str]) -> list[str]:
    paths, _ = status_paths(repo)
    violations = [path for path in paths if not allowed_path(path, allowed)]
    if violations:
        raise SdlcError("working tree contains paths outside approved scope: " + ", ".join(violations))
    return paths


def recover_commit(state: dict[str, Any], repo: Path) -> bool:
    """Recover a commit made immediately before a process crash.

    A commit subject carrying the Work ID and a diff restricted to the approved
    paths is sufficient evidence to resume publication without creating a second
    commit.  Any ambiguous repository state remains blocked for manual review.
    """

    publication = state.get("publication", {})
    if publication.get("commit_sha"):
        return True
    # A crash may happen after the commit but before state persistence.  If
    # the worktree is dirty, however, the HEAD commit could coexist with
    # uncommitted product or knowledge edits; recovering it would falsely
    # claim those edits were delivered.  Leave that ambiguous state blocked.
    dirty_paths, _ = status_paths(repo)
    if dirty_paths:
        return False
    base = state.get("workspace", {}).get("base_sha")
    if not base:
        return False
    if head_sha(repo) == base:
        return False
    subject = git(repo, "log", "-1", "--format=%s", check=False).strip()
    prefix = f"sdlc({state['work_id']}):"
    if not subject.startswith(prefix):
        return False
    changed = [normalize_rel(item) for item in git(repo, "diff", "--name-only", f"{base}..HEAD", check=False).splitlines() if item.strip()]
    allowed = state["approval"]["scope"].get("allowed_paths", [])
    if not changed or any(not allowed_path(item, allowed) for item in changed):
        return False
    publication["commit_sha"] = head_sha(repo)
    publication["state"] = "committed"
    publication["changed_paths"] = changed
    publication["post_commit_snapshot"] = working_tree_snapshot(repo)
    knowledge = state.get("knowledge", {})
    publication["post_commit_product_snapshot"] = (
        working_tree_snapshot(repo, exclude=knowledge.get("scope", []))
        if knowledge.get("scope") and knowledge.get("status") == "blocked" and knowledge.get("conflicts")
        else None
    )
    append_event(state, "commit_recovered", phase="delivery", status="complete")
    return True


def finish_publication(state: dict[str, Any], repo: Path, args: argparse.Namespace) -> None:
    publication = state["publication"]
    if publication.get("commit_sha") and head_sha(repo) != publication.get("commit_sha"):
        raise SdlcError("saved commit SHA no longer matches the delivery branch; publication is blocked")
    if publication.get("state") == "draft_pr_created":
        state["next_action"] = "merge/deploy/cleanup require separate authorization"
        return
    requested_remote = validate_remote_name(getattr(args, "remote", None))
    approved_remote = publication.get("remote")
    if requested_remote and requested_remote != approved_remote:
        raise SdlcError("finish remote differs from the approved publication destination; re-approve the scope")
    remote = approved_remote
    branch = state["workspace"].get("branch")
    if remote:
        current_url_digest = remote_url_digest(repo, remote)
        if not current_url_digest or current_url_digest != publication.get("remote_url_sha256"):
            publication["state"] = "publication_pending"
            publication["reason"] = "approved Git remote URL is missing or has changed"
            state["next_action"] = "restore the approved remote destination, then rerun finish --publish"
            return
    # A configured approved remote is the normal automatic publication target.  The
    # explicit flag remains useful for retrying a previously pending handoff.
    if not args.publish and not remote:
        publication["state"] = "publication_pending"
        publication["reason"] = "no Git remote is configured"
        state["next_action"] = "configure an approved remote, then rerun finish --publish"
        return
    if not remote:
        publication["state"] = "publication_pending"
        publication["reason"] = "no Git remote is configured"
        state["next_action"] = "configure an approved remote, then rerun finish --publish"
        return
    # A successful push is persisted separately from the PR state.  If PR
    # creation fails, a later resume retries only the missing PR handoff rather
    # than pushing the same commit again.
    if publication.get("push_commit_sha") != publication.get("commit_sha"):
        result = run_process(("git", "push", remote, branch), repo, timeout=120, check=False)
        if result.returncode != 0:
            publication["state"] = "publication_pending"
            publication["reason"] = f"push failed with exit {result.returncode}"
            publication["push_output_sha256"] = digest_text(redact((result.stdout or "") + (result.stderr or "")))
            state["next_action"] = "fix remote/authentication/network and rerun finish --publish"
            return
        publication["push_commit_sha"] = publication.get("commit_sha")
    publication["state"] = "pushed"
    publication["reason"] = None
    if shutil.which("gh") is None:
        publication["state"] = "publication_pending"
        publication["reason"] = "GitHub CLI (gh) is unavailable after push"
        state["next_action"] = "install/authenticate gh and rerun finish --publish"
        return
    title = publication.get("title") or f"SDLC delivery {state['work_id']}"
    body = (
        f"SDLC delivery {state['work_id']}\n\n"
        f"Problem: {redact(state['task'].get('request', ''))}\n"
        "Result: approved implementation reviewed and verified\n"
        f"Verification: {state['verification'].get('status')}\n"
        f"Knowledge: {state['knowledge'].get('status')}\n"
        f"Knowledge conflicts: {', '.join(state['knowledge'].get('conflicts', [])) or 'none'}\n"
        f"Pending: {publication.get('reason') or 'none'}\n"
    )
    existing = run_process(("gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number,url,isDraft,headRefOid"), repo, timeout=60, check=False)
    if existing.returncode != 0:
        publication["state"] = "publication_pending"
        publication["reason"] = "could not inspect existing pull requests"
        publication["pr_output_sha256"] = digest_text(redact((existing.stdout or "") + (existing.stderr or "")))
        state["next_action"] = "fix GitHub CLI/authentication and rerun finish --publish"
        return
    try:
        prs = json.loads(existing.stdout or "[]")
    except (json.JSONDecodeError, TypeError):
        publication["state"] = "publication_pending"
        publication["reason"] = "GitHub CLI returned invalid pull-request data"
        publication["pr_output_sha256"] = digest_text(redact(existing.stdout or ""))
        state["next_action"] = "inspect GitHub CLI output and rerun finish --publish"
        return
    if not isinstance(prs, list):
        prs = []
    draft_prs = [item for item in prs if item.get("isDraft") is True and item.get("headRefOid") == publication.get("commit_sha")]
    if draft_prs:
        pr = draft_prs[0]
        publication["state"] = "draft_pr_created"
        publication["pr"] = {"number": pr.get("number"), "url": pr.get("url"), "reused": True}
        state["next_action"] = "merge/deploy/cleanup require separate authorization"
        return
    if isinstance(prs, list) and prs:
        publication["state"] = "publication_pending"
        publication["reason"] = "a non-draft pull request already uses this branch; review it manually"
        state["next_action"] = "resolve the existing pull request before retrying finish --publish"
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
        handle.write(body)
        body_path = handle.name
    try:
        created = run_process(("gh", "pr", "create", "--draft", "--base", publication.get("base_branch") or "main", "--head", branch, "--title", title, "--body-file", body_path), repo, timeout=120, check=False)
    finally:
        try:
            os.unlink(body_path)
        except OSError:
            pass
    if created.returncode != 0:
        publication["state"] = "publication_pending"
        publication["reason"] = f"draft PR creation failed with exit {created.returncode}"
        publication["pr_output_sha256"] = digest_text(redact((created.stdout or "") + (created.stderr or "")))
        state["next_action"] = "rerun finish --publish to retry draft PR creation"
    else:
        url = (created.stdout or "").strip().splitlines()[-1] if (created.stdout or "").strip() else None
        publication["state"] = "draft_pr_created"
        publication["pr"] = {"url": url, "reused": False}
        state["next_action"] = "merge/deploy/cleanup require separate authorization"


def _cmd_finish_locked(args: argparse.Namespace, repo: Path) -> int:
    state, path = load_state(repo, args.work_id)
    requested_remote = validate_remote_name(getattr(args, "remote", None))
    if requested_remote and requested_remote != state.get("publication", {}).get("remote"):
        raise SdlcError("finish remote differs from the approved publication destination; re-approve the scope")
    if not state.get("workspace", {}).get("worktree"):
        raise SdlcError("finish requires an approved run with a delivery worktree")
    worktree = Path(state["workspace"]["worktree"]).resolve()
    if not worktree.exists():
        raise SdlcError(f"delivery worktree is missing: {worktree}")
    # These flags represent evidence returned by independent sessions.  They never grant
    # write access; they only record the externally obtained verdict before preflight.
    if args.review_approved or args.review_verdict or args.verified or args.knowledge_reviewed or args.knowledge_promoted:
        try:
            apply_progress_flags(state, worktree, args)
        except SdlcError:
            if state.get("verification", {}).get("status") == "failed":
                state["status"] = "blocked"
                state["phase"] = "verification"
                save_state(state, path)
            raise
    if state.get("review", {}).get("verdict") != "APPROVED":
        raise SdlcError("finish is blocked until a fresh independent reviewer records APPROVED")
    if not all_tasks_completed(state):
        raise SdlcError("finish is blocked until every dependent work package has been reviewed")
    allowed = state["approval"]["scope"].get("allowed_paths", [])
    if not allowed:
        raise SdlcError("finish is blocked because approval has no allowed paths")
    knowledge_conflict_pending = bool(
        state["knowledge"].get("scope")
        and state["knowledge"].get("status") == "blocked"
        and state["knowledge"].get("conflicts")
    )
    if state["knowledge"].get("scope") and state["knowledge"].get("status") not in ("reviewed", "promoted") and not knowledge_conflict_pending:
        raise SdlcError("finish is blocked until the approved knowledge scope has a fresh review")
    if args.rerun_tests or state["verification"].get("status") not in ("passed", "verified"):
        try:
            record_verification(state, worktree)
        except SdlcError as exc:
            state["status"] = "blocked"
            state["phase"] = "verification"
            state["next_action"] = "fix the verification command or environment before retrying finish"
            append_event(state, "verification_blocked", phase="verification", status="blocked")
            save_state(state, path)
            raise
    if state["knowledge"].get("scope") and state["knowledge"].get("status") == "reviewed" and not args.knowledge_promoted:
        # Promotion is automatic only after the independent knowledge review and fresh
        # verification.  A caller can pass --knowledge-promoted for an already accepted
        # candidate; both paths remain bound to the original approved scope.
        try:
            promote_knowledge(state, worktree)
        except SdlcError:
            if state["knowledge"].get("status") == "blocked" and state["knowledge"].get("conflicts"):
                knowledge_conflict_pending = True
                state["next_action"] = "deliver the product and resolve the pending knowledge conflict before updating canonical knowledge"
                append_event(state, "knowledge_conflict_deferred", phase="delivery", status="active")
            else:
                state["status"] = "blocked"
                state["phase"] = "knowledge"
                state["next_action"] = "resolve the knowledge conflict and obtain a fresh review"
                append_event(state, "knowledge_promotion_blocked", phase="knowledge", status="blocked")
                save_state(state, path)
                raise
        append_event(state, "knowledge_promoted", phase="delivery", status="active")
    paths = verify_scope(worktree, allowed)
    current_snapshot = working_tree_snapshot(worktree)
    review = state.get("review", {})
    verification = state.get("verification", {})
    if verification.get("status") in ("passed", "verified") and verification.get("snapshot") != current_snapshot:
        product_scope = state.get("knowledge", {}).get("scope", [])
        product_snapshot = working_tree_snapshot(worktree, exclude=product_scope) if product_scope else None
        knowledge_only_drift = bool(
            knowledge_conflict_pending
            and product_scope
            and review.get("product_snapshot")
            and product_snapshot == review.get("product_snapshot")
        )
        if not knowledge_only_drift:
            state["status"] = "blocked"
            state["phase"] = "verification"
            state["next_action"] = "rerun the approved verification commands after the worktree returns to the reviewed snapshot"
            append_event(state, "verification_stale", phase="verification", status="blocked")
            save_state(state, path)
            raise SdlcError("verification evidence is stale for the current worktree; rerun the approved tests")
    if review.get("snapshot") and review["snapshot"] != current_snapshot:
        product_scope = state.get("knowledge", {}).get("scope", [])
        product_snapshot = working_tree_snapshot(worktree, exclude=product_scope) if product_scope else None
        if not product_scope or not review.get("product_snapshot") or product_snapshot != review.get("product_snapshot"):
            raise SdlcError("working tree changed after review; obtain a fresh review before finishing")
        if state.get("knowledge", {}).get("status") not in ("reviewed", "promoted") and not knowledge_conflict_pending:
            raise SdlcError("working tree changed after review outside an approved knowledge handoff")
        knowledge_conflict_pending = True
    publication = state["publication"]
    if publication.get("commit_sha"):
        expected = publication.get("post_commit_snapshot")
        if expected and expected != current_snapshot:
            knowledge_conflict = post_commit_product_recovery_allowed(state, worktree)
            if not knowledge_conflict:
                raise SdlcError("working tree changed after the committed review; create a new delivery run")
    else:
        recover_commit(state, worktree)
    publication = state["publication"]
    if publication.get("commit_sha"):
        # A prior process may have committed successfully before persisting state.
        # Reuse the recovered commit and continue with publication only.
        if not publication.get("post_commit_snapshot"):
            publication["post_commit_snapshot"] = current_snapshot
        if knowledge_conflict_pending and not publication.get("post_commit_product_snapshot"):
            publication["post_commit_product_snapshot"] = working_tree_snapshot(
                worktree, exclude=state.get("knowledge", {}).get("scope", [])
            )
    publication["state"] = "local_verified"
    append_event(state, "local_verified", phase="delivery", status="active")
    commit_allowed = list(allowed)
    if knowledge_conflict_pending:
        commit_allowed = [
            item for item in paths
            if not any(allowed_path(item, [knowledge_path]) for knowledge_path in state.get("knowledge", {}).get("scope", []))
        ]
    if not publication.get("commit_sha"):
        if not commit_allowed:
            raise SdlcError("finish found no product paths to commit while knowledge has a pending conflict")
        result = run_process(("git", "add", "-A", "--", *commit_allowed), worktree, timeout=60, check=False)
        if result.returncode != 0:
            raise SdlcError(f"git add failed ({result.returncode})")
        staged = git(worktree, "diff", "--cached", "--name-only", "-z").split("\0")
        staged = [normalize_rel(item) for item in staged if item]
        if not staged:
            raise SdlcError("finish found no approved changes to commit")
        if any(not allowed_path(item, allowed) for item in staged):
            raise SdlcError("git staging selected a path outside approved scope")
        title = publication.get("title") or state["task"]["request"]
        message = f"sdlc({state['work_id']}): {title[:160]}".replace("\n", " ")
        commit = run_process(("git", "commit", "-m", message), worktree, timeout=120, check=False)
        if commit.returncode != 0:
            raise SdlcError(f"git commit failed ({commit.returncode}): {redact((commit.stdout or '') + (commit.stderr or '')).strip()}")
        publication["commit_sha"] = head_sha(worktree)
        publication["state"] = "committed"
        publication["changed_paths"] = staged
        publication["post_commit_snapshot"] = working_tree_snapshot(worktree)
        publication["post_commit_product_snapshot"] = (
            working_tree_snapshot(worktree, exclude=state.get("knowledge", {}).get("scope", []))
            if knowledge_conflict_pending
            else None
        )
        append_event(state, "committed", phase="delivery", status="complete")
    finish_publication(state, worktree, args)
    state["phase"] = "delivery"
    state["status"] = "complete" if state.get("publication", {}).get("state") == "draft_pr_created" else "active"
    if knowledge_conflict_pending:
        state["next_action"] = "resolve the pending knowledge conflict and rerun the knowledge review"
    save_state(state, path)
    emit(state_summary(state, path), args)
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    args.work_id = select_work_id(repo, args.work_id)
    lock = acquire_state_lock(state_path(repo, args.work_id))
    try:
        return _cmd_finish_locked(args, repo)
    finally:
        release_state_lock(lock)


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--text", action="store_true", help="print a compact key/value report instead of JSON")


def add_repo(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="target Git repository")


def add_approval_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--approve", nargs="?", const="integrated", action="append", choices=APPROVAL_STAGES, help="record an approval stage")
    parser.add_argument("--approval-ref")
    parser.add_argument("--requirements-approval-ref")
    parser.add_argument("--plan-approval-ref")
    parser.add_argument("--allowed-path", action="append")
    parser.add_argument("--acceptance", action="append")
    parser.add_argument("--test-command", action="append")
    parser.add_argument("--knowledge-path", action="append")
    parser.add_argument("--remote")
    parser.add_argument("--base-branch")
    parser.add_argument("--writer")
    parser.add_argument("--writer-id")
    parser.add_argument("--writer-ticket")
    parser.add_argument("--work-package", action="append", help="ordered work-package ID; repeat to define dependent packages")
    parser.add_argument("--work-package-file", action="append", help="JSON file containing task-specific dispatch packages")
    parser.add_argument("--design-file")
    parser.add_argument("--requirements-file")
    parser.add_argument("--plan-file")
    parser.add_argument("--title")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdlc", description="Portable evidence-driven SDLC delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    classify_parser = sub.add_parser("classify", help="classify a request without mutation")
    classify_parser.add_argument("--request", required=True)
    classify_parser.add_argument("--repo", help="optional target Git repository for read-only exploration")
    classify_parser.add_argument("--task-class", choices=TASK_CLASSES)
    add_output(classify_parser)

    diagnose_parser = sub.add_parser("diagnose", help="run a read-only bug oracle and save an assessment")
    add_repo(diagnose_parser)
    diagnose_parser.add_argument("--request", required=True)
    diagnose_parser.add_argument("--command", dest="diagnosis_command", required=True, help="read-only symptom or regression command")
    diagnose_parser.add_argument("--disposition", required=True, choices=("confirmed", "likely", "partial", "not-a-bug", "blocked"))
    diagnose_parser.add_argument("--hypothesis", required=True, help="falsifiable root-cause hypothesis")
    diagnose_parser.add_argument("--environment", action="append", help="safe environment/context labels")
    add_output(diagnose_parser)

    init_parser = sub.add_parser("init", help="opt a target repository into the portable workflow")
    add_repo(init_parser)
    init_parser.add_argument("--base-branch")
    init_parser.add_argument("--test-command", action="append")
    init_parser.add_argument("--remote")
    init_parser.add_argument("--force", action="store_true")
    add_output(init_parser)

    start_parser = sub.add_parser("start", help="classify and create or save a delivery run")
    add_repo(start_parser)
    start_parser.add_argument("--request", required=True)
    start_parser.add_argument("--work-id")
    start_parser.add_argument("--task-class", choices=TASK_CLASSES)
    start_parser.add_argument("--repair-class", choices=("small", "large"))
    start_parser.add_argument("--diagnosis", choices=("confirmed", "likely", "not-a-bug"))
    start_parser.add_argument("--diagnosis-file", help="validated read-only bug assessment produced by sdlc diagnose")
    add_approval_options(start_parser)
    add_output(start_parser)

    resume_parser = sub.add_parser("resume", help="resume a saved run or record an approval/progress result")
    add_repo(resume_parser)
    resume_parser.add_argument("--work-id")
    resume_parser.add_argument("--request", default="")
    resume_parser.add_argument("--review-approved", action="store_true")
    resume_parser.add_argument("--review-verdict", choices=("APPROVED", "CHANGES_REQUIRED", "BLOCKED"))
    resume_parser.add_argument("--finding", action="append")
    resume_parser.add_argument("--finding-key", action="append", help="stable key paired with a --finding entry")
    resume_parser.add_argument("--reviewer-id")
    resume_parser.add_argument("--reviewer-session")
    resume_parser.add_argument("--review-ticket")
    resume_parser.add_argument("--writer-complete", action="store_true")
    resume_parser.add_argument("--writer-report", help="external signed-by-context writer completion report")
    resume_parser.add_argument("--review-report", help="external read-only reviewer report")
    resume_parser.add_argument("--knowledge-report", help="external knowledge reviewer report")
    resume_parser.add_argument("--knowledge-reviewed", action="store_true")
    resume_parser.add_argument("--knowledge-promoted", action="store_true")
    resume_parser.add_argument("--verified", action="store_true")
    resume_parser.add_argument("--publish", action="store_true", help="retry the approved publication handoff")
    resume_parser.add_argument("--escalate", action="store_true", help="upgrade a small task to the large-change gates")
    add_approval_options(resume_parser)
    add_output(resume_parser)

    status_parser = sub.add_parser("status", help="show resumable delivery state")
    add_repo(status_parser)
    status_parser.add_argument("--work-id")
    add_output(status_parser)

    doctor_parser = sub.add_parser("doctor", help="check tools, configuration, and state without mutation")
    add_repo(doctor_parser)
    doctor_parser.add_argument("--work-id")
    add_output(doctor_parser)

    finish_parser = sub.add_parser("finish", help="verify, commit, and optionally publish an approved run")
    add_repo(finish_parser)
    finish_parser.add_argument("--work-id")
    finish_parser.add_argument("--publish", action="store_true", help="push and create or reuse a draft PR")
    finish_parser.add_argument("--remote")
    finish_parser.add_argument("--review-approved", action="store_true")
    finish_parser.add_argument("--review-verdict", choices=("APPROVED", "CHANGES_REQUIRED", "BLOCKED"))
    finish_parser.add_argument("--finding", action="append")
    finish_parser.add_argument("--finding-key", action="append", help="stable key paired with a --finding entry")
    finish_parser.add_argument("--reviewer-id")
    finish_parser.add_argument("--reviewer-session")
    finish_parser.add_argument("--review-ticket")
    finish_parser.add_argument("--writer-id")
    finish_parser.add_argument("--writer-ticket")
    finish_parser.add_argument("--writer-complete", action="store_true")
    finish_parser.add_argument("--writer-report")
    finish_parser.add_argument("--review-report")
    finish_parser.add_argument("--knowledge-report")
    finish_parser.add_argument("--verified", action="store_true")
    finish_parser.add_argument("--rerun-tests", action="store_true")
    finish_parser.add_argument("--knowledge-reviewed", action="store_true")
    finish_parser.add_argument("--knowledge-promoted", action="store_true")
    add_output(finish_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return {
            "classify": cmd_classify,
            "diagnose": cmd_diagnose,
            "init": cmd_init,
            "start": cmd_start,
            "resume": cmd_resume,
            "status": cmd_status,
            "doctor": cmd_doctor,
            "finish": cmd_finish,
        }[args.command](args)
    except SdlcError as exc:
        print(f"sdlc: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("sdlc: interrupted; state was not reset", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
