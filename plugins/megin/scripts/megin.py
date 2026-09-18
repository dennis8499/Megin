#!/usr/bin/env python3
"""Portable Megin v2 command line entry point.

The command intentionally has no third party dependencies.  It keeps runtime state in a
user state directory and only writes the target repository's opt-in ``.megin/config.json``
and approved delivery changes.  The CLI is a small, deterministic state machine; the
Codex skills provide the human and sub-agent orchestration around it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import errno
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
CONFIG_SCHEMA = "megin-project/v1"
MIGRATION_SCHEMA = "megin-migration/v1"
PLUGIN_VERSION = "0.3.0"
# v2 records are bound to the contract major version.  A newer compatible
# plugin may continue an older minor/patch record; it must never reinterpret a
# v1 record or a future record it does not understand.
PLUGIN_VERSION_PARTS = tuple(int(item) for item in PLUGIN_VERSION.split(".")[:3])
DIAGNOSIS_SCHEMA = "bug-diagnosis/v1"
WRITER_REPORT_SCHEMA = "megin-writer-report/v1"
REVIEW_REPORT_SCHEMA = "megin-review-report/v1"
KNOWLEDGE_REVIEW_SCHEMA = "megin-knowledge-review/v1"
# These legacy identifiers are intentionally limited to the one-time migration
# compatibility layer; normal Megin commands never accept them as identities.
LEGACY_CONFIG_SCHEMA = "sdlc-project/v1"
LEGACY_WRITER_REPORT_SCHEMA = "sdlc-writer-report/v1"
LEGACY_REVIEW_REPORT_SCHEMA = "sdlc-review-report/v1"
LEGACY_KNOWLEDGE_REVIEW_SCHEMA = "sdlc-knowledge-review/v1"
LEGACY_CAPABILITY_SCHEMA = "sdlc-capability/v1"
WORK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TASK_CLASSES = ("read_only", "small", "large", "bug")
APPROVAL_STAGES = ("integrated", "requirements", "plan")
WORKSPACE_MODES = ("current", "worktree")
FINISH_MODES = ("unstaged", "commit", "draft-pr")
DELIVERY_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "delivery-run-v2.schema.json"


class MeginError(RuntimeError):
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
        raise MeginError(f"work ID already exists for this repository: {path.stem}; use resume") from exc
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
        raise MeginError(f"state/configuration not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MeginError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MeginError(f"JSON root must be an object: {path}")
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
        raise MeginError(f"tool not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        output = redact((exc.stdout or "") + (exc.stderr or ""))
        raise MeginError(f"command timed out after {timeout}s: {' '.join(command)}\n{output}") from exc
    if check and result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise MeginError(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")
    return result


def git(cwd: Path, *arguments: str, check: bool = True, timeout: int = 60) -> str:
    result = run_process(("git", *arguments), cwd, timeout=timeout, check=False)
    if check and result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise MeginError(f"git {' '.join(arguments)} failed ({result.returncode}) in {cwd}: {detail}")
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
        raise MeginError("tool not found: git") from exc
    except subprocess.TimeoutExpired as exc:
        raise MeginError(f"git command timed out after {timeout}s: git {' '.join(arguments)}") from exc
    if check and result.returncode != 0:
        detail = redact((result.stdout + result.stderr).decode("utf-8", errors="replace")).strip()
        raise MeginError(f"git {' '.join(arguments)} failed ({result.returncode}): {detail}")
    return result.stdout or b""


def require_git_repo(path: str | Path) -> Path:
    requested = Path(path).expanduser().resolve()
    if not requested.exists():
        raise MeginError(f"repository path does not exist: {requested}")
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
        raise MeginError("remote must be a Git remote name; credentials and URLs are not stored")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", value):
        raise MeginError("remote contains unsupported characters")
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


def git_remotes(repo: Path) -> list[str]:
    """Return configured remote names without contacting any remote."""

    return [item.strip() for item in git(repo, "remote", check=False).splitlines() if item.strip()]


def remote_default_branches(repo: Path) -> list[tuple[str, str]]:
    """Return locally cached symbolic default branches for configured remotes."""

    defaults: list[tuple[str, str]] = []
    for remote in git_remotes(repo):
        symbolic = git(
            repo, "symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD", check=False,
        ).strip()
        prefix = f"refs/remotes/{remote}/"
        if not symbolic.startswith(prefix):
            continue
        candidate = symbolic[len(prefix):]
        if candidate and git(
            repo, "show-ref", "--verify", f"refs/remotes/{remote}/{candidate}", check=False,
        ).strip():
            defaults.append((remote, candidate))
    return defaults


def default_base_branch(repo: Path) -> str:
    """Choose a stable project base branch without assuming the current checkout.

    A repository may call its primary branch ``main`` or ``master``.  Prefer the
    remote's symbolic default when it is available, then a local conventional
    branch, and finally the current branch for repositories that use another
    name.  This function is read-only and never fetches or changes branches.
    """

    remote_defaults = remote_default_branches(repo)
    remote_branches = sorted({branch for _, branch in remote_defaults})
    if len(remote_branches) > 1:
        raise MeginError("base branch is ambiguous across remote defaults; specify --base-branch explicitly")
    if remote_branches:
        return remote_branches[0]
    conventional = [
        candidate for candidate in ("main", "master")
        if git(repo, "show-ref", "--verify", f"refs/heads/{candidate}", check=False).strip()
    ]
    if len(conventional) > 1:
        raise MeginError("base branch is ambiguous; specify --base-branch as main or master")
    if conventional:
        return conventional[0]
    local_branches = [
        item.strip() for item in git(repo, "for-each-ref", "refs/heads", "--format=%(refname:short)", check=False).splitlines()
        if item.strip()
    ]
    if len(local_branches) == 1:
        return local_branches[0]
    if len(local_branches) > 1:
        raise MeginError("base branch is ambiguous; specify --base-branch explicitly")
    branch = current_branch(repo)
    return branch if branch != "HEAD" else "main"


def resolve_base_sha(repo: Path, branch: str, remote: str | None = None) -> str:
    """Resolve the approved base ref without fetching or changing checkout state."""

    refs = [f"refs/heads/{branch}"]
    remote_names = [remote] if remote else []
    remote_names.extend(item for item in git_remotes(repo) if item not in remote_names)
    for remote_name in remote_names:
        refs.append(f"refs/remotes/{remote_name}/{branch}")
    refs.append(branch)
    for ref in refs:
        resolved = git(repo, "rev-parse", "--verify", ref, check=False).strip()
        if re.fullmatch(r"[a-f0-9]{40}", resolved):
            return resolved
    raise MeginError(f"approved base branch does not exist: {branch}")


def workspace_status(repo: Path) -> tuple[list[str], bool]:
    """Return dirty paths and whether the index contains staged changes."""

    paths, _ = status_paths(repo)
    staged = bool(git(repo, "diff", "--cached", "--name-only", check=False).strip())
    return paths, staged


def ensure_megin_excluded(repo: Path) -> Path:
    """Keep repository-local Megin runtime metadata out of product changes."""

    try:
        exclude_path = Path(git(repo, "rev-parse", "--git-path", "info/exclude").strip())
        if not exclude_path.is_absolute():
            exclude_path = (repo / exclude_path).resolve()
        existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""
        entries = {line.strip() for line in existing.splitlines() if line.strip() and not line.lstrip().startswith("#")}
        if ".megin/" not in entries and ".megin" not in entries:
            exclude_path.parent.mkdir(parents=True, exist_ok=True)
            separator = "" if not existing or existing.endswith("\n") else "\n"
            exclude_path.write_text(existing + separator + ".megin/\n", encoding="utf-8")
        return exclude_path
    except OSError as exc:
        raise MeginError(f"cannot update local Git exclude for .megin metadata: {exc}") from exc


def ensure_clean_start(repo: Path) -> None:
    """Reject dirty source checkouts before any new workspace is acquired."""

    paths, staged = workspace_status(repo)
    unexpected = [item for item in paths if item != ".megin/config.json"]
    if unexpected or staged:
        detail = ", ".join(unexpected[:8]) or "staged changes"
        raise MeginError(
            "new work requires a clean starting checkout; preserve or resolve these changes first: "
            + detail
        )


def create_current_branch(
    repo: Path,
    work_id: str,
    base_sha: str,
    base_branch: str,
    branch_prefix: str = "feat",
    remote: str | None = None,
) -> tuple[Path, str]:
    """Create the approved feature branch in the caller's current work directory.

    Branch creation is deliberately conservative: the directory must be clean,
    the base branch must be checked out, and its HEAD must still match the
    approved digest.  We never stash, reset, merge, rebase, or discard user data.
    """

    ensure_clean_start(repo)
    branch = f"{branch_prefix}/{work_id}"
    if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).strip():
        raise MeginError(f"feature branch already exists: {branch}")
    # Check the approved ref before switching the caller's checkout.  If the
    # base advanced after approval, leave the user's original branch untouched
    # and require a new candidate instead of switching and then failing.
    resolved_base = resolve_base_sha(repo, base_branch, remote)
    if resolved_base != base_sha:
        raise MeginError("approved base branch changed since the candidate was created; refresh the candidate and approve again")
    if current_branch(repo) != base_branch:
        local_base = git(repo, "show-ref", "--verify", f"refs/heads/{base_branch}", check=False).strip()
        if not local_base:
            candidate_remotes = [remote] if remote else []
            candidate_remotes.extend(item for item in git_remotes(repo) if item not in candidate_remotes)
            remote_ref = next(
                (
                    f"{candidate}/{base_branch}"
                    for candidate in candidate_remotes
                    if git(repo, "show-ref", "--verify", f"refs/remotes/{candidate}/{base_branch}", check=False).strip()
                ),
                None,
            )
            if remote_ref is None:
                raise MeginError(f"approved base branch does not exist locally: {base_branch}")
            switched = run_process(("git", "switch", "-c", base_branch, "--track", remote_ref), repo, timeout=60, check=False)
        else:
            switched = run_process(("git", "switch", base_branch), repo, timeout=60, check=False)
        if switched.returncode != 0:
            raise MeginError(f"cannot switch to approved base branch {base_branch}: {redact((switched.stdout or '') + (switched.stderr or '')).strip()}")
    if head_sha(repo) != base_sha:
        raise MeginError("approved base branch changed since the candidate was created; refresh the candidate and approve again")
    created = run_process(("git", "switch", "-c", branch), repo, timeout=60, check=False)
    if created.returncode != 0:
        raise MeginError(f"cannot create feature branch {branch}: {redact((created.stdout or '') + (created.stderr or '')).strip()}")
    return repo.resolve(), branch


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
        raise MeginError(f"base branch contains unsupported characters: {value!r}")
    return value


def validate_branch_prefix(value: str) -> str:
    prefix = str(value).strip()
    if len(prefix) > 40:
        raise MeginError(f"branch prefix contains unsupported characters: {prefix!r}")
    try:
        validate_branch_name(prefix)
    except MeginError as exc:
        raise MeginError(f"branch prefix contains unsupported characters: {prefix!r}") from exc
    if any(not part or part.startswith(".") or part.endswith(".") for part in prefix.split("/")):
        raise MeginError(f"branch prefix contains unsupported characters: {prefix!r}")
    return prefix


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def normalize_rel(value: str) -> str:
    value = str(value).strip().replace("\\", "/")
    if not value:
        raise MeginError("paths cannot be empty")
    if value == ".":
        return "."
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise MeginError(f"path must be relative to the worktree: {value}")
    pieces = value.split("/")
    if any(piece in ("", ".", "..") for piece in pieces):
        raise MeginError(f"path traversal is not allowed: {value}")
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
        except MeginError:
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
                        except MeginError:
                            continue
    files: list[dict[str, Any]] = []
    for path in sorted(paths):
        absolute = repo / Path(path)
        if absolute.is_file() or absolute.is_symlink():
            try:
                data = snapshot_bytes(absolute)
            except OSError as exc:
                raise MeginError(f"cannot read snapshot path {path}: {exc}") from exc
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
        except MeginError:
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
                    except MeginError:
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
        raise MeginError("knowledge candidate is missing")
    path = Path(candidate_path).expanduser().resolve()
    if not path.exists():
        raise MeginError(f"knowledge candidate is missing: {path}")
    raw = path.read_bytes()
    if digest_bytes(raw) != knowledge.get("candidate_sha256"):
        raise MeginError("knowledge candidate digest drifted; review a new candidate")
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
        except MeginError:
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
        raise MeginError("reviewed knowledge has no candidate path")
    path = Path(candidate_path).expanduser().resolve()
    expected_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"]
    try:
        path.relative_to(expected_root)
    except ValueError as exc:
        raise MeginError("knowledge candidate is outside the persistent work state") from exc
    if not path.exists() or digest_bytes(path.read_bytes()) != knowledge.get("candidate_sha256"):
        raise MeginError("knowledge candidate digest drifted; review a new candidate")
    payload = read_json(path)
    if payload.get("schema") != "knowledge-candidate/v2" or payload.get("work_id") != state.get("work_id"):
        raise MeginError("knowledge candidate identity drifted")
    if payload.get("revision") != candidate_revision(state):
        raise MeginError("knowledge candidate revision drifted")
    report_path = Path(str(knowledge.get("report_path", ""))).expanduser().resolve()
    report_root = expected_root / "knowledge"
    try:
        report_path.relative_to(report_root)
    except ValueError as exc:
        raise MeginError("knowledge review report is outside the persistent work state") from exc
    if not report_path.exists() or digest_bytes(report_path.read_bytes()) != knowledge.get("report_sha256"):
        raise MeginError("knowledge review report is missing or drifted")
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
        raise MeginError("knowledge review report is not bound to the saved candidate")


def promote_knowledge(state: dict[str, Any], repo: Path) -> None:
    knowledge = state.get("knowledge", {})
    if not knowledge.get("scope"):
        knowledge["status"] = "not_needed"
        return
    if knowledge.get("status") not in ("reviewed", "promoted"):
        raise MeginError("knowledge promotion requires a reviewed candidate")
    before = knowledge.get("snapshot_before") or knowledge_snapshot(repo, knowledge["scope"])
    current = knowledge_snapshot(repo, knowledge["scope"])
    if knowledge.get("snapshot_before") and current != before:
        knowledge["conflicts"] = [f"knowledge scope changed after review: {', '.join(knowledge.get('scope', []))}"]
        knowledge["status"] = "blocked"
        raise MeginError("knowledge scope changed after review; obtain a fresh knowledge review")
    payload, errors = lint_knowledge_candidate(state, repo)
    if errors:
        knowledge["lint"] = {"status": "failed", "errors": errors}
        knowledge["status"] = "blocked"
        raise MeginError("knowledge candidate lint failed: " + "; ".join(errors))
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
            raise MeginError(f"knowledge claim is outside approved write scope: {item}")
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
                raise MeginError(f"canonical knowledge changed after review: {item}")
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
    configured = os.environ.get("MEGIN_STATE_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = (Path(base) if base else Path.home()) / "megin" / "state"
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "megin"
    root = root.resolve()
    try:
        root.relative_to(repo)
    except ValueError:
        return root
    raise MeginError("MEGIN_STATE_ROOT must be outside the target repository")


def _migration_is_redirect(path: Path) -> bool:
    """Return whether a migration input is a symlink or Windows reparse point."""

    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    attributes = int(getattr(value, "st_file_attributes", 0))
    reparse_point = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return path.is_symlink() or bool(attributes & reparse_point)


def _migration_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(value.st_mode),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
        int(value.st_dev),
        int(value.st_ino),
    )


def _migration_read(path: Path) -> bytes:
    """Read one stable, regular migration input without following redirects."""

    if _migration_is_redirect(path):
        raise MeginError(f"migration refuses symlink or reparse-point input: {path}")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise MeginError(f"migration input is not a regular file: {path}")
        payload = path.read_bytes()
        after = path.lstat()
    except MeginError:
        raise
    except OSError as exc:
        raise MeginError(f"migration cannot read {path}: {exc}") from exc
    if _migration_signature(before) != _migration_signature(after):
        raise MeginError(f"migration input changed during inspection: {path}")
    return payload


def _migration_files(root: Path) -> list[tuple[str, bytes]]:
    """List a legacy state subtree while rejecting locks, redirects, and drift."""

    if not root.exists() and not root.is_symlink():
        return []
    if _migration_is_redirect(root):
        raise MeginError(f"migration refuses a redirected state root: {root}")
    if not root.is_dir():
        raise MeginError(f"migration state root is not a directory: {root}")

    result: list[tuple[str, bytes]] = []

    def on_error(error: OSError) -> None:
        raise MeginError(f"migration cannot inspect state root {root}: {error}") from error

    for current, directories, files in os.walk(root, topdown=True, followlinks=False, onerror=on_error):
        current_path = Path(current)
        directories.sort()
        files.sort()
        for name in directories:
            child = current_path / name
            if _migration_is_redirect(child):
                raise MeginError(f"migration refuses symlink or reparse-point directory: {child}")
        for name in files:
            child = current_path / name
            if name == ".lock" or name.endswith(".lock"):
                raise MeginError(f"migration is blocked by an active lock: {child}")
            result.append((child.relative_to(root).as_posix(), _migration_read(child)))
    return result


def _migration_reject_redirect_ancestors(path: Path, label: str) -> None:
    """Reject a configured path that crosses a symlink or reparse point."""

    candidate = path.expanduser()
    for ancestor in (candidate, *candidate.parents):
        if _migration_is_redirect(ancestor):
            raise MeginError(f"migration refuses redirected {label}: {ancestor}")


def _migration_root(
    repo: Path,
    explicit: str | None,
    environment: str,
    product_name: str,
) -> Path:
    configured = explicit or os.environ.get(environment)
    if configured:
        root = Path(configured).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = (Path(base) if base else Path.home()) / product_name / "state"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        root = base / product_name
    _migration_reject_redirect_ancestors(root, "state root")
    root = root.resolve()
    try:
        root.relative_to(repo)
    except ValueError:
        return root
    raise MeginError(f"{environment} must be outside the target repository")


def _migration_rewrite_path(value: Any, source_root: Path, target_root: Path) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return value
    try:
        relative = candidate.resolve().relative_to(source_root.resolve())
    except ValueError:
        return value
    return str((target_root / relative).resolve())


_MIGRATION_PATH_KEYS = {
    "path", "repo", "repo_path", "worktree", "state_root", "evidence_path",
    "candidate_path", "report_path", "reviewer_capability_path", "capability_path",
    "requirements_path", "handoff_path", "assessment_path", "source_path",
}


def _migration_rewrite_paths(value: Any, source_root: Path, target_root: Path, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            name: _migration_rewrite_paths(item, source_root, target_root, name)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_migration_rewrite_paths(item, source_root, target_root, key) for item in value]
    if key in _MIGRATION_PATH_KEYS or (key and key.endswith("_path")):
        return _migration_rewrite_path(value, source_root, target_root)
    return value


_MIGRATION_SCHEMA_RENAMES = {
    LEGACY_CONFIG_SCHEMA: CONFIG_SCHEMA,
    LEGACY_WRITER_REPORT_SCHEMA: WRITER_REPORT_SCHEMA,
    LEGACY_REVIEW_REPORT_SCHEMA: REVIEW_REPORT_SCHEMA,
    LEGACY_KNOWLEDGE_REVIEW_SCHEMA: KNOWLEDGE_REVIEW_SCHEMA,
    LEGACY_CAPABILITY_SCHEMA: "megin-capability/v1",
}


def _migration_json_kind(payload: dict[str, Any]) -> str:
    schema = payload.get("schema")
    if schema == SCHEMA and isinstance(payload.get("plugin"), str):
        return "state"
    if schema in {
        LEGACY_WRITER_REPORT_SCHEMA, LEGACY_REVIEW_REPORT_SCHEMA,
        LEGACY_KNOWLEDGE_REVIEW_SCHEMA, WRITER_REPORT_SCHEMA,
        REVIEW_REPORT_SCHEMA, KNOWLEDGE_REVIEW_SCHEMA,
    }:
        return "report"
    if schema in {LEGACY_CAPABILITY_SCHEMA, "megin-capability/v1"}:
        return "capability"
    if schema == DIAGNOSIS_SCHEMA:
        return "diagnosis"
    if schema == "knowledge-candidate/v2":
        return "candidate"
    return "opaque"


def _migration_transform_payload(
    payload: dict[str, Any], source_root: Path, target_root: Path,
) -> tuple[dict[str, Any], str]:
    kind = _migration_json_kind(payload)
    transformed = _migration_rewrite_paths(payload, source_root, target_root)
    if kind == "state":
        transformed = dict(transformed)
        transformed["plugin"] = "megin"
        transformed["plugin_version"] = PLUGIN_VERSION
        for assignment in transformed.get("assignments", []) or []:
            if not isinstance(assignment, dict):
                continue
            writer_result = assignment.get("writer_result")
            if isinstance(writer_result, dict) and writer_result.get("schema") in _MIGRATION_SCHEMA_RENAMES:
                writer_result["schema"] = _MIGRATION_SCHEMA_RENAMES[writer_result["schema"]]
    elif kind in {"report", "capability"}:
        transformed = dict(transformed)
        schema = transformed.get("schema")
        if schema in _MIGRATION_SCHEMA_RENAMES:
            transformed["schema"] = _MIGRATION_SCHEMA_RENAMES[schema]
    elif kind == "opaque":
        return payload, kind
    if kind == "capability":
        transformed = dict(transformed)
        transformed.pop("capability_sha256", None)
        transformed["capability_sha256"] = digest_json(transformed)
    elif kind == "diagnosis" and "record_sha256" in transformed:
        transformed = dict(transformed)
        transformed.pop("record_sha256", None)
        transformed["record_sha256"] = digest_json(transformed)
    return transformed, kind


def _migration_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return None
    return candidate.resolve()


def _migration_file_digest(value: Any) -> str | None:
    path = _migration_path(value)
    if path is None or not path.exists() or not path.is_file():
        return None
    return digest_bytes(_migration_read(path))


def _migration_manifest(files: Sequence[tuple[str, bytes]]) -> list[dict[str, Any]]:
    return [
        {"path": relative, "sha256": digest_bytes(data), "size": len(data)}
        for relative, data in files
    ]


def _migration_verify_config_snapshot(path: Path, expected: bytes) -> None:
    if _migration_read(path) != expected:
        raise MeginError(f"legacy configuration changed during migration: {path}")


def _migration_verify_state_snapshot(
    root: Path, expected_present: bool, expected_manifest: Sequence[dict[str, Any]],
) -> None:
    current_present = root.exists() or root.is_symlink()
    if current_present != expected_present:
        raise MeginError(f"legacy state presence changed during migration: {root}")
    current_manifest = _migration_manifest(_migration_files(root))
    if current_manifest != list(expected_manifest):
        raise MeginError(f"legacy state changed during migration: {root}")


def _migration_rebind_report(
    path_value: Any, schema: str, assignment_sha256: str | None, ticket_sha256: str | None = None,
) -> str | None:
    path = _migration_path(path_value)
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(_migration_read(path).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MeginError(f"migrated report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise MeginError(f"migrated report root must be an object: {path}")
    payload_schema = payload.get("schema")
    if payload_schema in _MIGRATION_SCHEMA_RENAMES:
        payload_schema = _MIGRATION_SCHEMA_RENAMES[payload_schema]
    if payload_schema != schema:
        raise MeginError(f"migrated report schema does not match its state binding: {path}")
    payload["schema"] = schema
    if assignment_sha256 is not None:
        payload["assignment_sha256"] = assignment_sha256
    if ticket_sha256 is not None and "ticket_sha256" in payload:
        payload["ticket_sha256"] = ticket_sha256
    write_json_atomic(path, payload)
    return digest_bytes(_migration_read(path))


def _migration_refresh_review_ticket(state: dict[str, Any]) -> None:
    review = state.get("review", {})
    if not review.get("verdict"):
        return
    assignment = next(
        (item for item in state.get("assignments", []) if item.get("assignment_id") == review.get("assignment_id")),
        None,
    )
    if not assignment:
        return
    review["assignment_sha256"] = assignment.get("assignment_sha256")
    review["review_ticket_sha256"] = digest_json({
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


def _migration_refresh_state(state: dict[str, Any]) -> None:
    """Rebind every derived digest after state-owned paths or identities move."""

    task_assessment = (state.get("task", {}) or {}).get("diagnosis_assessment") or {}
    if task_assessment.get("path"):
        assessment_sha = _migration_file_digest(task_assessment.get("path"))
        if assessment_sha:
            task_assessment["sha256"] = assessment_sha

    candidates = state.get("candidates", {}) or {}
    for candidate in candidates.values():
        if isinstance(candidate, dict) and candidate.get("path"):
            candidate_sha = _migration_file_digest(candidate.get("path"))
            if candidate_sha:
                candidate["sha256"] = candidate_sha

    knowledge = state.get("knowledge", {}) or {}
    if knowledge.get("candidate_path"):
        candidate_sha = _migration_file_digest(knowledge.get("candidate_path"))
        if candidate_sha:
            knowledge["candidate_sha256"] = candidate_sha
    if knowledge.get("report_path"):
        report_sha = _migration_file_digest(knowledge.get("report_path"))
        if report_sha:
            knowledge["report_sha256"] = report_sha

    for assignment in state.get("assignments", []) or []:
        capability_path = _migration_path(assignment.get("capability_path"))
        if capability_path and capability_path.exists():
            try:
                capability = json.loads(_migration_read(capability_path).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise MeginError(f"migrated capability is not valid JSON: {capability_path}") from exc
            if isinstance(capability, dict) and capability.get("capability_sha256"):
                assignment["capability_sha256"] = capability["capability_sha256"]
        writer_result = assignment.get("writer_result")
        if isinstance(writer_result, dict):
            report_sha = _migration_file_digest(writer_result.get("report_path"))
            if report_sha:
                writer_result["report_sha256"] = report_sha
            assignment["writer_result_sha256"] = digest_json(writer_result)
        assignment["ticket_sha256"] = digest_json(assignment_ticket_payload(state, assignment))
        refresh_assignment_digest(assignment)

    review = state.get("review", {}) or {}
    if review.get("report_path"):
        report_sha = _migration_file_digest(review.get("report_path"))
        if report_sha:
            review["report_sha256"] = report_sha
    reviewer_capability_path = _migration_path(review.get("reviewer_capability_path"))
    if reviewer_capability_path and reviewer_capability_path.exists():
        try:
            capability = json.loads(_migration_read(reviewer_capability_path).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MeginError(f"migrated capability is not valid JSON: {reviewer_capability_path}") from exc
        if isinstance(capability, dict) and capability.get("capability_sha256"):
            review["reviewer_capability_sha256"] = capability["capability_sha256"]
    _migration_refresh_review_ticket(state)
    refresh_verification_digest(state)
    refresh_approval_digests(state)
    # Approval digests are part of assignment tickets. Rebind the tickets a
    # second time after refreshing approval/candidate-derived values so a path
    # move cannot leave a valid-looking but stale writer ticket behind.
    for assignment in state.get("assignments", []) or []:
        assignment["ticket_sha256"] = digest_json(assignment_ticket_payload(state, assignment))
        writer_result = assignment.get("writer_result")
        if isinstance(writer_result, dict):
            report_sha = _migration_rebind_report(
                writer_result.get("report_path"), WRITER_REPORT_SCHEMA, None, assignment["ticket_sha256"],
            )
            if report_sha:
                writer_result["report_sha256"] = report_sha
            writer_result["ticket_sha256"] = assignment["ticket_sha256"]
            assignment["writer_result_sha256"] = digest_json(writer_result)
            evidence_path = _migration_path(writer_result.get("evidence_path"))
            if evidence_path and evidence_path.exists():
                # The persisted writer result is a derived binding artifact;
                # keep it byte-for-byte equal to the state copy after tickets
                # and report digests are refreshed.
                write_json_atomic(evidence_path, writer_result)
        refresh_assignment_digest(assignment)
    review = state.get("review", {}) or {}
    if review.get("verdict"):
        assignment = next(
            (item for item in state.get("assignments", []) if item.get("assignment_id") == review.get("assignment_id")),
            None,
        )
        if assignment:
            report_sha = _migration_rebind_report(
                review.get("report_path"), REVIEW_REPORT_SCHEMA, assignment["assignment_sha256"],
            )
            if report_sha:
                review["report_sha256"] = report_sha
    _migration_refresh_review_ticket(state)


def _migration_transform_tree(root: Path, source_root: Path, target_root: Path) -> list[str]:
    state_paths: list[Path] = []
    for relative, _ in _migration_files(root):
        path = root / Path(relative)
        if path.suffix.casefold() != ".json":
            continue
        try:
            payload = json.loads(_migration_read(path).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MeginError(f"migration JSON is malformed: {path}") from exc
        if not isinstance(payload, dict):
            raise MeginError(f"migration JSON root must be an object: {path}")
        transformed, kind = _migration_transform_payload(payload, source_root, target_root)
        if kind != "opaque":
            write_json_atomic(path, transformed)
        if kind == "state":
            state_paths.append(path)

    work_ids: list[str] = []
    for path in state_paths:
        state = read_json(path)
        work_id = validate_work_id(str(state.get("work_id", "")))
        # During the second pass the state references already point at the
        # final destination, while the staged files still live in root.parent.
        # Temporarily resolve those references back to the physical staging
        # root while recalculating derived digests, then restore final paths.
        physical = _migration_rewrite_paths(state, target_root, root.parent)
        _migration_refresh_state(physical)
        state = _migration_rewrite_paths(physical, root.parent, target_root)
        # The state subtree is still staged under ``root.parent`` at this
        # point, but its references now name the eventual target root.  Keep
        # the persisted writer evidence at its physical staging path while
        # storing the final path values inside it; otherwise the state and
        # evidence would disagree after the subtree is published.
        physical_assignments = {
            item.get("assignment_id"): item
            for item in physical.get("assignments", []) or []
            if isinstance(item, dict)
        }
        for assignment in state.get("assignments", []) or []:
            if not isinstance(assignment, dict):
                continue
            writer_result = assignment.get("writer_result")
            physical_assignment = physical_assignments.get(assignment.get("assignment_id"))
            physical_result = physical_assignment.get("writer_result") if physical_assignment else None
            if not isinstance(writer_result, dict) or not isinstance(physical_result, dict):
                continue
            evidence_path = _migration_path(physical_result.get("evidence_path"))
            if evidence_path and evidence_path.exists():
                write_json_atomic(evidence_path, writer_result)
        write_json_atomic(path, state)
        work_ids.append(work_id)
    return sorted(set(work_ids))


def _migration_existing_work_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    work_ids: list[str] = []
    for relative, raw in _migration_files(root):
        path = root / Path(relative)
        if path.parent != root or path.suffix.casefold() != ".json":
            continue
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MeginError(f"existing Megin state is malformed: {path}") from exc
        if isinstance(payload, dict) and payload.get("schema") == SCHEMA:
            work_ids.append(validate_work_id(str(payload.get("work_id", ""))))
    return sorted(set(work_ids))


def _migration_validate_state_root(root: Path, repo: Path, work_ids: Sequence[str]) -> None:
    previous = os.environ.get("MEGIN_STATE_ROOT")
    os.environ["MEGIN_STATE_ROOT"] = str(root)
    try:
        for work_id in work_ids:
            load_state(repo, work_id)
    finally:
        if previous is None:
            os.environ.pop("MEGIN_STATE_ROOT", None)
        else:
            os.environ["MEGIN_STATE_ROOT"] = previous


def _migration_config(repo: Path, path: Path) -> tuple[dict[str, Any], bytes]:
    if _migration_is_redirect(path.parent):
        raise MeginError(f"migration refuses redirected legacy configuration: {path.parent}")
    raw = _migration_read(path)
    try:
        config = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MeginError(f"legacy project configuration is malformed: {path}") from exc
    if not isinstance(config, dict):
        raise MeginError(f"legacy project configuration must be a JSON object: {path}")
    if config.get("schema") != LEGACY_CONFIG_SCHEMA or config.get("plugin") != "sdlc":
        raise MeginError(f"unsupported legacy project configuration: {path}")
    if config.get("repo_id") != repo_identity(repo):
        raise MeginError(f"legacy project configuration repository identity drifted: {path}")
    configured_repo = config.get("repo_path")
    if configured_repo and Path(str(configured_repo)).expanduser().resolve() != repo:
        raise MeginError(f"legacy project configuration points to a different repository: {path}")
    validate_remote_name(config.get("remote"))
    for command in config.get("test_commands", []) or []:
        validate_command_text(str(command))
    migrated = dict(config)
    migrated["schema"] = CONFIG_SCHEMA
    migrated["plugin"] = "megin"
    migrated["plugin_version"] = PLUGIN_VERSION
    return migrated, raw


def cmd_migrate(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    try:
        result = _run_migration(args, repo)
    except MeginError as exc:
        source_root = target_root = None
        try:
            source_root = _migration_root(repo, args.from_state_root, "SDLC_STATE_ROOT", "sdlc")
            target_root = _migration_root(repo, args.to_state_root, "MEGIN_STATE_ROOT", "megin")
        except MeginError:
            pass
        emit(_migration_result(repo, "blocked", source_root, target_root, None, conflicts=[str(exc)]), args)
        return 3
    emit(result, args)
    return 0


def _migration_result(
    repo: Path,
    status: str,
    source_root: Path | None,
    target_root: Path | None,
    migration_id: str | None,
    work_ids: Sequence[str] = (),
    file_count: int = 0,
    conflicts: Sequence[str] = (),
    backup: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    return {
        "schema": MIGRATION_SCHEMA,
        "status": status,
        "repo": str(repo),
        "source": {"config": str(repo / ".sdlc" / "config.json"), "state_root": str(source_root) if source_root else None},
        "target": {"config": str(repo / ".megin" / "config.json"), "state_root": str(target_root) if target_root else None},
        "migration_id": migration_id,
        "backup": backup,
        "work_ids": list(work_ids),
        "file_count": int(file_count),
        "conflicts": [redact(str(item)) for item in conflicts],
    }


def _run_migration(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    legacy_dir = repo / ".sdlc"
    target_dir = repo / ".megin"
    legacy_config = legacy_dir / "config.json"
    target_config = target_dir / "config.json"
    legacy_present = legacy_dir.exists() or legacy_dir.is_symlink()
    target_present = target_dir.exists() or target_dir.is_symlink()

    if target_present and _migration_is_redirect(target_dir):
        raise MeginError(f"migration destination is a symlink or reparse point: {target_dir}")
    if legacy_present and _migration_is_redirect(legacy_dir):
        raise MeginError(f"legacy configuration is a symlink or reparse point: {legacy_dir}")
    if not legacy_present:
        if not target_present:
            raise MeginError(f"legacy project configuration was not found: {legacy_config}")
        try:
            config = load_config(repo, required=True)
        except MeginError as exc:
            raise MeginError(f"Megin configuration exists but is invalid: {target_config}") from exc
        source_root = _migration_root(repo, args.from_state_root, "SDLC_STATE_ROOT", "sdlc")
        target_root = _migration_root(repo, args.to_state_root, "MEGIN_STATE_ROOT", "megin")
        old_state = source_root / repo_identity(repo)
        if old_state.exists() and _migration_files(old_state):
            raise MeginError(f"legacy state remains after configuration migration: {old_state}")
        target_state = target_root / repo_identity(repo)
        work_ids = _migration_existing_work_ids(target_state)
        _migration_validate_state_root(target_root, repo, work_ids)
        return _migration_result(repo, "already_migrated", source_root, target_root, None, work_ids)

    if not legacy_config.exists() or not legacy_config.is_file():
        raise MeginError(f"legacy project configuration is missing: {legacy_config}")
    if target_present:
        raise MeginError(f"migration destination already exists: {target_dir}")
    migrated_config, config_raw = _migration_config(repo, legacy_config)
    repo_id = repo_identity(repo)
    source_root = _migration_root(repo, args.from_state_root, "SDLC_STATE_ROOT", "sdlc")
    target_root = _migration_root(repo, args.to_state_root, "MEGIN_STATE_ROOT", "megin")
    source_state = source_root / repo_id
    target_state = target_root / repo_id
    if source_root == target_root and target_state.exists():
        # Same-root migrations intentionally stage and swap the repository-id subtree.
        pass
    elif target_state.exists() or target_state.is_symlink():
        raise MeginError(f"migration state destination already exists: {target_state}")
    source_state_present = source_state.exists() or source_state.is_symlink()
    source_files = _migration_files(source_state)
    manifest = _migration_manifest(source_files)
    migration_id = digest_json({"config_sha256": digest_bytes(config_raw), "state": manifest})
    state_backup = source_root / f"{repo_id}.sdlc-migrated-{migration_id}"
    config_backup = repo / f".sdlc.migrated-{migration_id}"
    if source_state.exists() and state_backup.exists():
        raise MeginError(f"migration backup already exists: {state_backup}")
    if config_backup.exists():
        raise MeginError(f"migration backup already exists: {config_backup}")

    if args.dry_run:
        stage_root = Path(tempfile.mkdtemp(prefix="megin-migration-dry-run-"))
        try:
            stage_state = stage_root / repo_id
            stage_state.mkdir(parents=True, exist_ok=True)
            for relative, data in source_files:
                write_bytes_atomic(stage_state / Path(relative), data)
            work_ids = _migration_transform_tree(stage_state, source_root, stage_root)
            _migration_validate_state_root(stage_root, repo, work_ids)
            return _migration_result(
                repo, "dry_run", source_root, target_root, migration_id, work_ids,
                len(source_files) + 1,
                backup={"config": str(config_backup), "state": str(state_backup) if source_state.exists() else None},
            )
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)

    target_root.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{repo_id}.megin-migration-", dir=str(target_root.parent)))
    stage_state = stage_root / repo_id
    state_published = False
    config_started = False
    try:
        stage_state.mkdir(parents=True, exist_ok=True)
        for relative, data in source_files:
            write_bytes_atomic(stage_state / Path(relative), data)
        work_ids = _migration_transform_tree(stage_state, source_root, stage_root)
        _migration_verify_config_snapshot(legacy_config, config_raw)
        _migration_verify_state_snapshot(source_state, source_state_present, manifest)
        _migration_validate_state_root(stage_root, repo, work_ids)
        _migration_transform_tree(stage_state, stage_root, target_root)

        if source_state_present:
            target_root.mkdir(parents=True, exist_ok=True)
            os.replace(source_state, state_backup)
            os.replace(stage_state, target_state)
            state_published = True
            # The second staging pass rebases state-owned paths to their final
            # destination before the subtree is published.  Refresh the
            # path-sensitive bindings once the files are physically at that
            # destination so persisted evidence, report bytes, and assignment
            # digests all describe the same final tree.
            for work_id in work_ids:
                published_path = target_state / f"{work_id}.json"
                published_state = read_json(published_path)
                _migration_refresh_state(published_state)
                write_json_atomic(published_path, published_state)
            _migration_validate_state_root(target_root, repo, work_ids)

        _migration_verify_config_snapshot(legacy_config, config_raw)
        os.replace(legacy_dir, config_backup)
        config_started = True
        target_dir.mkdir(parents=False, exist_ok=False)
        write_json_atomic(target_config, migrated_config)
        load_config(repo, required=True)
        return _migration_result(
            repo, "migrated", source_root, target_root, migration_id, work_ids,
            len(source_files) + 1,
            backup={"config": str(config_backup), "state": str(state_backup) if state_backup.exists() else None},
        )
    except Exception as exc:
        recovery: list[str] = []
        failed_state = target_root / f"{repo_id}.megin-failed-{migration_id}"
        failed_config = repo / f".megin.failed-{migration_id}"
        try:
            if state_published and target_state.exists():
                os.replace(target_state, failed_state)
                recovery.append(str(failed_state))
            if source_state.exists() is False and state_backup.exists():
                os.replace(state_backup, source_state)
                recovery.append(str(source_state))
            if config_started and target_dir.exists() and not legacy_dir.exists():
                os.replace(target_dir, failed_config)
                recovery.append(str(failed_config))
            if legacy_dir.exists() is False and config_backup.exists():
                os.replace(config_backup, legacy_dir)
                recovery.append(str(legacy_dir))
        except OSError as recovery_error:
            recovery.append(f"recovery-error: {recovery_error}")
        detail = f"migration failed safely: {exc}"
        if recovery:
            detail += "; recovery artifacts: " + ", ".join(recovery)
        raise MeginError(detail) from exc
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def state_target_repo(state: dict[str, Any], fallback: Path) -> Path:
    configured = state.get("repo", {}).get("path")
    return Path(configured).expanduser().resolve() if configured else fallback.resolve()


def state_directory(repo: Path) -> Path:
    return state_root(repo_identity(repo), repo) / repo_identity(repo)


def state_path(repo: Path, work_id: str) -> Path:
    return state_directory(repo) / f"{work_id}.json"


def workspace_binding_path(repo: Path) -> Path:
    """Return the repository-level lock used to serialize current workspaces."""

    return state_directory(repo) / ".workspace-binding"


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
    except MeginError:
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
        raise MeginError("diagnosis assessment must use bug-diagnosis/v1")
    schema_errors = validate_delivery_schema(payload, DELIVERY_SCHEMA_PATH.parent / "bug-diagnosis-v1.schema.json")
    if schema_errors:
        raise MeginError(f"diagnosis assessment schema validation failed: {'; '.join(schema_errors[:8])}")
    if payload.get("repo_id") != repo_identity(repo):
        raise MeginError("diagnosis assessment repository identity drifted")
    expected_request_sha = request_sha256 or digest_text(request or "")
    if payload.get("request_sha256") != expected_request_sha:
        raise MeginError("diagnosis assessment belongs to a different request")
    if payload.get("disposition") not in ("confirmed", "likely", "partial", "not-a-bug", "blocked"):
        raise MeginError("diagnosis assessment has an unsupported disposition")
    if not payload.get("command") or not payload.get("hypothesis"):
        raise MeginError("diagnosis assessment must include the oracle command and root-cause hypothesis")
    if payload.get("record_sha256") != _diagnosis_payload_digest(payload):
        raise MeginError("diagnosis assessment digest drifted")
    root = diagnosis_directory(repo)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise MeginError("diagnosis assessment is outside the persistent state") from exc
    evidence_path = _external_path(str(payload.get("evidence_path", "")), repo)
    try:
        evidence_path.relative_to(root)
    except ValueError as exc:
        raise MeginError("diagnosis evidence is outside the persistent state") from exc
    if not evidence_path.exists() or not evidence_path.is_file():
        raise MeginError("diagnosis evidence is missing")
    evidence = evidence_path.read_bytes()
    if digest_bytes(evidence) != payload.get("output_sha256") or len(evidence) != payload.get("output_bytes"):
        raise MeginError("diagnosis evidence digest drifted")
    if payload.get("disposition") in ("confirmed", "likely") and (payload.get("input_snapshot") != payload.get("output_snapshot") or payload.get("read_only") is not True):
        raise MeginError("diagnosis command changed the repository; repair authorization is unavailable")
    return payload, path


def load_external_report(value: str | None, repo: Path, *, label: str) -> tuple[dict[str, Any], Path, str]:
    if not value:
        raise MeginError(f"{label} requires an external report file")
    path = _external_path(value, repo)
    payload = read_json(path)
    schema_files = {
        DIAGNOSIS_SCHEMA: "bug-diagnosis-v1.schema.json",
        WRITER_REPORT_SCHEMA: "megin-writer-report-v1.schema.json",
        REVIEW_REPORT_SCHEMA: "megin-review-report-v1.schema.json",
        KNOWLEDGE_REVIEW_SCHEMA: "megin-knowledge-review-v1.schema.json",
    }
    schema_name = schema_files.get(payload.get("schema"))
    if schema_name:
        schema_errors = validate_delivery_schema(payload, DELIVERY_SCHEMA_PATH.parent / schema_name)
        if schema_errors:
            raise MeginError(f"{label} schema validation failed: {'; '.join(schema_errors[:8])}")
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
        raise MeginError("review report test evidence must be a non-empty array")
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
            raise MeginError(f"review test evidence item is invalid: {index}")
        if item.get("status") not in ("passed", "verified"):
            raise MeginError(f"review test evidence is not passing: {index}")
        command = str(item.get("command", "")).strip()
        if not command or command not in commands:
            raise MeginError(f"review test evidence uses an unapproved command: {index}")
        output_sha = item.get("output_sha256")
        output_bytes = item.get("output_bytes")
        if not isinstance(output_sha, str) or not SHA256_RE.fullmatch(output_sha):
            raise MeginError(f"review test evidence has an invalid output digest: {index}")
        if not isinstance(output_bytes, int) or isinstance(output_bytes, bool) or output_bytes < 0:
            raise MeginError(f"review test evidence has an invalid output length: {index}")
        if item.get("input_snapshot") != expected_snapshot or item.get("output_snapshot") != expected_snapshot:
            raise MeginError(f"review test evidence snapshot is stale: {index}")
        evidence_value = item.get("evidence_path")
        if not isinstance(evidence_value, str) or not evidence_value.strip():
            raise MeginError(f"review test evidence is missing its raw output path: {index}")
        source_evidence = Path(evidence_value).expanduser()
        if not source_evidence.is_absolute():
            source_evidence = source_path.parent / source_evidence
        source_evidence = source_evidence.resolve()
        if source_evidence in seen_sources:
            raise MeginError(f"review raw output is reused for multiple evidence items: {index}")
        seen_sources.add(source_evidence)
        if not _path_is_under(source_evidence, allowed_roots):
            raise MeginError(f"review raw output is outside the report or persistent evidence roots: {index}")
        if not source_evidence.exists() or not source_evidence.is_file():
            raise MeginError(f"review raw output is missing: {index}")
        # Evidence written by the controller is redacted before hashing.  This
        # keeps copied reviewer output safe while preserving exact byte-level
        # freshness and digest checks for the persisted artifact.
        raw = source_evidence.read_bytes()
        persisted = redact(raw.decode("utf-8", errors="replace")).encode("utf-8")
        if digest_bytes(persisted) != output_sha or len(persisted) != output_bytes:
            raise MeginError(f"review raw output digest does not match the report: {index}")
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
        raise MeginError("capability identity and session are required")
    payload = {
        "schema": "megin-capability/v1",
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
        raise MeginError("delegated capability record is missing")
    path = Path(path_value).expanduser().resolve()
    root = capability_root(state, Path(state["repo"]["path"]))
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise MeginError("delegated capability is outside the persistent work state") from exc
    if not path.exists():
        raise MeginError("delegated capability record is missing")
    payload = read_json(path)
    stored = payload.pop("capability_sha256", None)
    if stored != expected_digest or digest_json(payload) != expected_digest:
        raise MeginError("delegated capability digest drifted")
    if payload.get("work_id") != state.get("work_id") or payload.get("repo_id") != state.get("repo", {}).get("repo_id"):
        raise MeginError("delegated capability identity drifted")
    if kind and payload.get("kind") != kind:
        raise MeginError("delegated capability kind drifted")
    if kind == "reviewer" and payload.get("read_only") is not True:
        raise MeginError("reviewer capability must be read-only")
    if kind == "writer" and payload.get("read_only") is not False:
        raise MeginError("writer capability cannot be read-only")
    if assignment_id and payload.get("assignment_id") != assignment_id:
        raise MeginError("delegated capability assignment drifted")
    if identity and payload.get("identity") != identity:
        raise MeginError("delegated capability identity drifted")
    if session_id and payload.get("session_id") != session_id:
        raise MeginError("delegated capability session drifted")


def validate_work_id(work_id: str) -> str:
    if not WORK_ID_RE.fullmatch(work_id) or not (3 <= len(work_id) <= 64):
        raise MeginError("work-id must be 3-64 lowercase letters, digits, and hyphens")
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


def load_routing_evidence(
    path_value: str,
    request: str | None,
    repo: Path | None,
    *,
    request_sha256: str | None = None,
    verify_head: bool = True,
) -> dict[str, Any]:
    """Read and validate a read-only routing record produced during exploration."""

    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise MeginError(f"routing evidence file does not exist: {path}")
    try:
        payload = read_json(path)
    except Exception as exc:
        raise MeginError(f"routing evidence is not valid JSON: {path}") from exc
    if payload.get("schema") != "megin-routing/v1":
        raise MeginError("routing evidence must use schema megin-routing/v1")
    required_keys = {"schema", "request_sha256", "repo_id", "head_sha", "intent", "sources", "risks", "open_questions"}
    missing_keys = sorted(required_keys - set(payload))
    if missing_keys:
        raise MeginError("routing evidence is missing required fields: " + ", ".join(missing_keys))
    allowed_keys = required_keys | {"task_class", "generated_at"}
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        raise MeginError("routing evidence contains unsupported fields: " + ", ".join(unknown_keys))
    if not SHA256_RE.fullmatch(str(payload.get("request_sha256", ""))):
        raise MeginError("routing evidence request_sha256 is invalid")
    if not SHA256_RE.fullmatch(str(payload.get("repo_id", ""))):
        raise MeginError("routing evidence repo_id is invalid")
    if not re.fullmatch(r"[a-f0-9]{40}", str(payload.get("head_sha", ""))):
        raise MeginError("routing evidence head_sha is invalid")
    expected_request_sha256 = request_sha256 or digest_text(request or "")
    if payload.get("request_sha256") != expected_request_sha256:
        raise MeginError("routing evidence request digest does not match the current request")
    if repo is not None:
        if payload.get("repo_id") != repo_identity(repo):
            raise MeginError("routing evidence repository identity does not match the target repository")
        if verify_head and payload.get("head_sha") != head_sha(repo):
            raise MeginError("routing evidence is stale for the current repository HEAD")
    intent = payload.get("intent")
    if intent not in ("read_only", "mutate", "ambiguous"):
        raise MeginError("routing evidence intent must be read_only, mutate, or ambiguous")
    suggested = payload.get("task_class")
    if suggested is not None and suggested not in TASK_CLASSES:
        raise MeginError(f"routing evidence task_class is unsupported: {suggested}")
    if "generated_at" in payload and not isinstance(payload.get("generated_at"), str):
        raise MeginError("routing evidence generated_at must be a string when present")
    if not isinstance(payload.get("sources"), list) or not isinstance(payload.get("risks"), list) or not isinstance(payload.get("open_questions"), list):
        raise MeginError("routing evidence sources, risks, and open_questions must be arrays")
    if any(not isinstance(item, str) for key in ("sources", "risks", "open_questions") for item in payload.get(key, [])):
        raise MeginError("routing evidence source, risk, and question entries must be strings")
    return {
        "schema": payload["schema"],
        "path": str(path),
        "sha256": digest_bytes(path.read_bytes()),
        "request_sha256": payload["request_sha256"],
        "repo_id": payload.get("repo_id"),
        "head_sha": payload.get("head_sha"),
        "intent": intent,
        "task_class": suggested,
        "sources": [redact(str(item)) for item in payload.get("sources", [])],
        "risks": [redact(str(item)) for item in payload.get("risks", [])],
        "open_questions": [redact(str(item)) for item in payload.get("open_questions", [])],
    }


def _classification_term_present(text: str, term: str) -> bool:
    """Match English routing terms as words while keeping CJK phrases intact."""

    if re.fullmatch(r"[a-z0-9]+(?:[ -][a-z0-9]+)*", term):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
    return term in text


def classify(request: str, repo: Path | None = None, routing_file: str | None = None) -> dict[str, Any]:
    """Classify intent before impact, keeping explanation words from implying a bug.

    This remains a conservative heuristic.  A routing evidence file can add
    repository-bound evidence, but it cannot authorize a write by itself.
    """

    text = request.strip()
    lowered = text.casefold()
    routing = load_routing_evidence(routing_file, request, repo) if routing_file else None
    if not text:
        result = {"task_class": "large", "reason": "empty request has material uncertainty", "confidence": "low", "needs_clarification": True}
    else:
        explicit_read = any(_classification_term_present(lowered, term) for term in (
            "explain", "evaluate", "assessment", "review", "audit", "inspect", "check", "status", "plan", "advice",
            "recommend", "recommendation", "suggest", "compare", "provide advice", "read-only", "without changing", "說明", "如何", "怎麼",
            "不要修改", "不修改", "不需修改", "不必修改", "只分析", "只檢查", "僅檢視", "提供建議", "計畫書",
            "解說", "說明", "分析", "評估", "審查", "檢視", "檢查", "唯讀", "報告",
        ))
        hard_change_terms = (
            "fix", "repair", "resolve", "correct", "debug", "troubleshoot", "implement", "change", "add", "update", "modify", "edit", "refactor", "build", "create",
            "remove", "delete", "upgrade", "integrate", "修復", "修正", "實作", "新增", "更新", "修改",
            "建立", "改寫", "重構", "轉型", "加入", "移除", "刪除", "升級", "整合", "排除", "除錯",
        )
        soft_change_terms = ("improve", "enhance", "support", "enable", "改善", "優化", "調整", "支援", "啟用")
        soft_change = any(_classification_term_present(lowered, term) for term in soft_change_terms)
        explicit_no_change = bool(
            re.search(
                r"(?:do not|don't|without|no changes?|不要|不(?:要|需|必)|無需|不必).{0,20}(?:change|modify|edit|fix|write|修改|變更|改|修|寫)",
                lowered,
            )
            or re.search(r"\bno changes?\b|不要修改|不修改|不需修改|不必修改|無需修改", lowered)
        )
        # Do not let the word "修改" in "不要修改" turn a read-only request
        # into a mutation.  Keep a positive verb elsewhere in the sentence so
        # genuinely contradictory requests still stop for clarification.
        change_context = lowered
        if explicit_no_change:
            change_context = re.sub(
                r"(?:do not|don't|without|no changes?|不要|不(?:要|需|必|修改|變更|改|修|寫)|無需|不必)[^.!?;，。！？]{0,24}",
                " ",
                lowered,
            )
        hard_change = any(_classification_term_present(change_context, term) for term in hard_change_terms)
        has_change = hard_change or soft_change
        plan_or_advice = any(_classification_term_present(lowered, term) for term in (
            "plan only", "provide a plan", "recommend", "suggest", "provide advice", "plan", "explain", "how to", "計畫", "規劃", "建議", "方案", "如何", "怎麼",
        ))
        direct_action = bool(re.search(
            r"^(?:please\s+|i\s+want\s+to\s+|we\s+need\s+to\s+)?(?:fix|repair|resolve|correct|debug|troubleshoot|implement|change|add|update|modify|edit|refactor|build|create|remove|delete|upgrade|integrate)\b",
            lowered,
        )) or bool(re.search(r"^(?:請|需要|希望)?\s*(?:修復|修正|實作|新增|更新|修改|建立|改寫|重構|轉型|加入|移除|刪除|升級|整合)", text))
        # Planning/advice language describes a possible change but does not
        # authorize it.  A direct imperative still wins, while a soft term
        # such as "improve" is enough to route a plainly mutating request.
        modification_requested = has_change and not explicit_no_change and not (explicit_read and plan_or_advice and not direct_action)
        contradictory_intent = bool(explicit_no_change and hard_change)
        mixed_intent = bool(
            explicit_read
            and hard_change
            and not explicit_no_change
            and not direct_action
            and any(term in lowered for term in (" and ", " then ", " after ", "並", "然後", "接著", "再"))
        )
        # An explanation that happens to mention error/API/bug terminology is
        # still read-only unless the user asks to repair the behavior.
        bug_request = (
            any(_classification_term_present(lowered, term) for term in ("bug", "defect", "regression", "broken", "failure", "error"))
            or any(_classification_term_present(lowered, term) for term in ("錯誤", "故障", "問題", "失敗", "修復錯誤", "修正錯誤", "修復故障", "修正問題", "修復異常", "修復 bug"))
        ) and modification_requested
        docs_only = any(_classification_term_present(lowered, term) for term in ("readme", "documentation", "docs", "文件", "文檔")) and not any(
            _classification_term_present(lowered, term) for term in ("runtime", "behavior", "行為", "程式", "功能", "schema", "contract", "契約", "介面契約", "資料庫", "migration", "遷移")
        )
        large_terms = (
            "architecture", "architectural", "subsystem", "migration", "schema", "contract", "api", "dependency",
            "permission", "security", "cross-module", "platform", "framework", "new system", "database",
            "架構", "子系統", "遷移", "契約", "介面", "依賴", "權限", "跨模組", "資料庫", "平台", "完整轉型",
        )
        has_large_impact = any(_classification_term_present(lowered, term) for term in large_terms)
        if routing and routing["intent"] == "read_only":
            result = {"task_class": "read_only", "reason": "routing evidence marks the request as read-only", "confidence": "high"}
        elif routing and routing["intent"] == "ambiguous":
            result = {"task_class": "large", "reason": "routing evidence contains unresolved intent or scope questions", "confidence": "low", "needs_clarification": True}
        elif contradictory_intent or mixed_intent:
            result = {"task_class": "large", "reason": "request mixes read-only exploration with a mutation; clarify the intended next action", "confidence": "low", "needs_clarification": True}
        elif not modification_requested and (explicit_read or not has_change):
            result = {"task_class": "read_only", "reason": "request asks for explanation, assessment, planning, or review without a product mutation", "confidence": "high" if explicit_read else "medium"}
        elif routing and routing["intent"] == "mutate" and routing.get("task_class") in ("small", "large", "bug"):
            suggested = routing["task_class"]
            result = {
                "task_class": suggested,
                "reason": "repository-bound routing evidence supplies the requested mutation class",
                "confidence": "high",
            }
            if routing.get("open_questions"):
                result["needs_clarification"] = True
                result["reason"] = "routing evidence still contains open questions; clarify them before mutation"
            if suggested == "bug":
                result["requires_diagnosis"] = True
        elif bug_request:
            result = {"task_class": "bug", "reason": "request asks to repair an existing failure; diagnose before repair", "confidence": "medium", "requires_diagnosis": True}
        elif has_large_impact and not docs_only:
            result = {"task_class": "large", "reason": "request may change architecture, contracts, data, permissions, dependencies, or multiple modules", "confidence": "high"}
        elif docs_only or any(_classification_term_present(lowered, term) for term in ("typo", "wording", "format", "文字", "格式", "單一檔案", "single file")):
            result = {"task_class": "small", "reason": "request appears isolated with a clear, bounded result", "confidence": "medium"}
        else:
            result = {"task_class": "large", "reason": "scope or impact is not sufficiently bounded to prove a small task", "confidence": "low", "needs_clarification": True}
        result["modification_requested"] = modification_requested
    if routing:
        result["routing_evidence"] = routing
        result["routing_evidence_sha256"] = routing["sha256"]
        if routing.get("risks"):
            result["routing_risks"] = routing["risks"]
        if routing.get("open_questions"):
            result["open_questions"] = routing["open_questions"]
    if repo is not None:
        result["exploration"] = explore_repository(repo)
    return result


def explicit_class(request: str, requested: str | None, repo: Path | None = None, routing_file: str | None = None) -> dict[str, Any]:
    result = classify(request, repo, routing_file)
    if not requested:
        return result
    if requested not in TASK_CLASSES:
        raise MeginError(f"unsupported task class: {requested}")
    if result["task_class"] == "read_only" and requested != "read_only":
        raise MeginError("a read-only explanation, assessment, diagnosis, or review cannot be forced into a mutating delivery class")
    if result["task_class"] == "bug" and requested in ("small", "large"):
        raise MeginError("a suspected bug must complete read-only diagnosis before choosing a repair class")
    if requested == "small" and result["task_class"] == "large":
        raise MeginError("cannot downgrade an uncertain or architectural request to small; narrow and re-approve it")
    if requested == "read_only" and result["task_class"] in ("small", "large", "bug"):
        raise MeginError("a mutating request cannot be forced into read_only")
    if result.get("needs_clarification") and requested in ("small", "large", "bug"):
        raise MeginError("routing evidence or request intent is unresolved; clarify the request before selecting a mutating class")
    result["task_class"] = requested
    result["reason"] = f"explicitly selected {requested}; original exploration: {result['reason']}"
    return result


def load_config(repo: Path, *, required: bool = True) -> dict[str, Any] | None:
    path = repo / ".megin" / "config.json"
    if not path.exists():
        legacy = repo / ".sdlc" / "config.json"
        if legacy.exists():
            raise MeginError(
                f"legacy project configuration found at {legacy}; run `megin migrate --repo {repo}`"
            )
        if required:
            raise MeginError(f"project is not initialized; run `megin init --repo {repo}`")
        return None
    config = read_json(path)
    if config.get("schema") != CONFIG_SCHEMA:
        raise MeginError(f"unsupported project configuration schema in {path}")
    if config.get("repo_id") != repo_identity(repo):
        raise MeginError(f"project configuration repository identity drifted: {path}")
    validate_remote_name(config.get("remote"))
    if config.get("workspace_mode") is not None and config.get("workspace_mode") not in WORKSPACE_MODES:
        raise MeginError(f"project configuration workspace_mode is unsupported: {config.get('workspace_mode')}")
    if config.get("finish_mode") is not None and config.get("finish_mode") not in FINISH_MODES:
        raise MeginError(f"project configuration finish_mode is unsupported: {config.get('finish_mode')}")
    if config.get("branch_prefix") is not None:
        try:
            validate_branch_prefix(config.get("branch_prefix"))
        except MeginError as exc:
            raise MeginError(f"project configuration branch_prefix is unsupported: {config.get('branch_prefix')!r}") from exc
    return config


def parse_command(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise MeginError("test commands must be non-empty strings")
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
        raise MeginError(f"cannot parse test command {value!r}: {exc}") from exc
    if not command:
        raise MeginError("test commands must contain an executable")
    return command


def validate_command_text(value: str) -> str:
    if redact(value) != value:
        raise MeginError("test commands must not contain credential-shaped values; use environment references")
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
        raise MeginError("knowledge scope must be contained in the approved allowed paths")
    remote = getattr(args, "remote", None)
    if remote is None and config:
        remote = config.get("remote")
    remote = validate_remote_name(remote)
    if getattr(args, "base_branch", None):
        base_branch = args.base_branch
    elif config and config.get("base_branch"):
        base_branch = config["base_branch"]
    else:
        base_branch = default_base_branch(repo_for_scope(config))
    base_branch = validate_branch_name(base_branch)
    workspace_mode = getattr(args, "workspace_mode", None)
    if workspace_mode is None and config:
        workspace_mode = config.get("workspace_mode")
    # Explicit task-class invocations are the legacy automation spelling. Keep
    # the historical worktree/commit path only when neither new destination
    # flag is present; selecting either mode opts into the v0.3 defaults for
    # the other field as well. Natural-language starts always use current /
    # unstaged unless project configuration says otherwise.
    legacy_invocation = bool(
        getattr(args, "task_class", None)
        and getattr(args, "workspace_mode", None) is None
        and getattr(args, "finish_mode", None) is None
        and not (config or {}).get("workspace_mode")
        and not (config or {}).get("finish_mode")
    )
    if workspace_mode is None:
        workspace_mode = "worktree" if legacy_invocation else "current"
    if workspace_mode not in WORKSPACE_MODES:
        raise MeginError(f"workspace mode must be one of {', '.join(WORKSPACE_MODES)}")
    finish_mode = getattr(args, "finish_mode", None)
    if finish_mode is None and config:
        finish_mode = config.get("finish_mode")
    if finish_mode is None:
        finish_mode = "commit" if legacy_invocation else "unstaged"
    if finish_mode not in FINISH_MODES:
        raise MeginError(f"finish mode must be one of {', '.join(FINISH_MODES)}")
    branch_prefix = validate_branch_prefix(getattr(args, "branch_prefix", None) or (config or {}).get("branch_prefix") or "feat")
    base_sha = resolve_base_sha(repo_for_scope(config), base_branch, remote)
    title = getattr(args, "title", None) or getattr(args, "request", None) or "Megin delivery"
    acceptance = [redact(value) for value in (getattr(args, "acceptance", None) or [title])]
    return {
        "acceptance": acceptance,
        "allowed_paths": allowed,
        "test_commands": commands,
        "knowledge_scope": knowledge,
        "publication": {
            "remote": remote,
            "remote_url_sha256": remote_url_digest(repo_for_scope(config), remote),
            "base_branch": base_branch,
            "base_sha": base_sha,
            "title": redact(title)[:200],
            "workspace_mode": workspace_mode,
            "finish_mode": finish_mode,
            "branch_prefix": branch_prefix,
        },
    }


def approval_args(args: argparse.Namespace) -> set[str]:
    values = set()
    for value in getattr(args, "approve", None) or []:
        value = value or "integrated"
        if value not in APPROVAL_STAGES:
            raise MeginError(f"approval stage must be one of {', '.join(APPROVAL_STAGES)}")
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
        raise MeginError(f"state schema validation failed: {'; '.join(schema_errors[:8])}")
    if state.get("schema") != SCHEMA:
        raise MeginError(f"state is not a delivery-run/v2 record: {path}")
    if state.get("plugin") != "megin" or not compatible_plugin_version(state.get("plugin_version")):
        raise MeginError(
            f"state is bound to unsupported megin plugin {state.get('plugin_version')!r}; current engine is {PLUGIN_VERSION}"
        )
    if state.get("work_id") != work_id or state.get("repo", {}).get("repo_id") != repo_identity(repo):
        raise MeginError(f"state identity mismatch: {path}")
    routing_record = (state.get("task", {}).get("classification") or {}).get("routing_evidence")
    if routing_record:
        checked_routing = load_routing_evidence(
            routing_record.get("path", ""),
            state.get("task", {}).get("request", ""),
            repo,
            request_sha256=state.get("task", {}).get("request_sha256"),
            verify_head=False,
        )
        if checked_routing.get("sha256") != routing_record.get("sha256"):
            raise MeginError(f"routing evidence binding drifted; re-run read-only exploration: {path}")
        if routing_record.get("head_sha") and checked_routing.get("head_sha") != routing_record.get("head_sha"):
            raise MeginError(f"routing evidence source changed; re-run read-only exploration: {path}")
    task_record = state.get("task", {})
    if task_record.get("task_class") == "bug":
        assessment = task_record.get("diagnosis_assessment")
        if not isinstance(assessment, dict) or not assessment.get("path") or not assessment.get("sha256"):
            raise MeginError(f"bug run has no bound diagnosis assessment: {path}")
        assessment_payload, assessment_path = load_diagnosis_assessment(
            assessment["path"], repo, request_sha256=task_record.get("request_sha256"),
        )
        if digest_bytes(assessment_path.read_bytes()) != assessment.get("sha256"):
            raise MeginError(f"diagnosis assessment binding drifted: {path}")
        if assessment_payload.get("disposition") != task_record.get("diagnosis"):
            raise MeginError(f"diagnosis disposition drifted: {path}")
        if assessment.get("disposition") != assessment_payload.get("disposition") or assessment.get("hypothesis") != assessment_payload.get("hypothesis"):
            raise MeginError(f"diagnosis assessment summary drifted: {path}")
    try:
        expected_payload = digest_json(candidate_payload(state))
    except (KeyError, TypeError) as exc:
        raise MeginError(f"state is missing required approval fields: {path}") from exc
    if state.get("approval", {}).get("payload_sha256") != expected_payload:
        raise MeginError(f"approval scope digest drifted; re-plan and create a new Work ID: {path}")
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
        raise MeginError(f"approval stage digest drifted; re-plan and create a new Work ID: {path}")
    scope = approval.get("scope", {})
    try:
        configured_base = validate_branch_name(scope.get("publication", {}).get("base_branch") or state.get("repo", {}).get("base_branch"))
    except MeginError as exc:
        raise MeginError(f"approved base branch is invalid: {path}") from exc
    if state.get("repo", {}).get("base_branch") != configured_base or state.get("publication", {}).get("base_branch") != configured_base:
        raise MeginError(f"base branch binding drifted: {path}")
    approved_base_sha = scope.get("publication", {}).get("base_sha")
    if approved_base_sha is not None and not re.fullmatch(r"[a-f0-9]{40}", str(approved_base_sha)):
        raise MeginError(f"approved base SHA is invalid: {path}")
    if approved_base_sha is not None and state.get("publication", {}).get("base_sha") not in (None, approved_base_sha):
        raise MeginError(f"base SHA binding drifted: {path}")
    finish_mode = state.get("publication", {}).get("finish_mode") or scope.get("publication", {}).get("finish_mode")
    if finish_mode == "unstaged" and state.get("publication", {}).get("commit_sha"):
        raise MeginError(f"unstaged publication cannot contain a commit SHA: {path}")
    if state.get("publication", {}).get("state") == "delivered_unstaged" and finish_mode != "unstaged":
        raise MeginError(f"delivered_unstaged state requires finish_mode=unstaged: {path}")
    if any(not allowed_path(item, scope.get("allowed_paths", [])) for item in scope.get("knowledge_scope", [])):
        raise MeginError(f"knowledge scope is outside the approved write scope: {path}")
    task_ids = [task.get("id") for task in state.get("tasks", [])]
    if len(task_ids) != len(set(task_ids)) or any(not item for item in task_ids):
        raise MeginError(f"work package identities are not unique: {path}")
    task_id_set = set(task_ids)
    for task in state.get("tasks", []):
        dependencies = list(task.get("depends_on", [])) + list(task.get("blocked_by", []))
        if task.get("id") in dependencies or any(dependency not in task_id_set for dependency in dependencies):
            raise MeginError(f"work package dependency graph is invalid: {path}")
    dependency_graph = {
        task.get("id"): set(task.get("depends_on", [])) | set(task.get("blocked_by", []))
        for task in state.get("tasks", [])
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit_dependency(identifier: str) -> None:
        if identifier in visiting:
            raise MeginError(f"work package dependency graph contains a cycle: {path}")
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
        raise MeginError(f"repository path binding drifted: {path}")
    workspace = state.get("workspace", {})
    if workspace.get("worktree"):
        worktree = Path(workspace["worktree"]).resolve()
        if not worktree.exists():
            raise MeginError(f"delivery worktree is missing: {worktree}")
        actual_top = Path(git(worktree, "rev-parse", "--show-toplevel").strip()).resolve()
        if actual_top != worktree:
            raise MeginError(f"delivery worktree identity drifted: {worktree}")
        if workspace.get("mode") == "current" and worktree != repo.resolve():
            raise MeginError(f"current workspace path drifted: {worktree}")
        if workspace.get("branch") and current_branch(worktree) != workspace["branch"]:
            raise MeginError(f"delivery branch identity drifted: {worktree}")
        if approved_base_sha and workspace.get("base_sha") not in (None, approved_base_sha):
            raise MeginError(f"workspace base SHA binding drifted: {worktree}")
    assignments = state.get("assignments", [])
    for assignment in assignments:
        if assignment.get("task_id") not in task_id_set:
            raise MeginError(f"writer assignment references an unknown work package: {assignment.get('assignment_id')}")
        task = task_for_id(state, assignment.get("task_id"))
        if not task or any(
            assignment.get(key) != task.get(key)
            for key in (
                "acceptance", "allowed_paths", "forbidden_paths", "interfaces", "focused_commands",
                "related_commands", "full_commands", "blocked_by", "depends_on", "evidence_path",
            )
        ):
            raise MeginError(f"writer assignment does not match its approved work package: {assignment.get('assignment_id')}")
        if not assignment.get("ticket_sha256") or not assignment.get("assignment_sha256"):
            raise MeginError(f"writer assignment is missing its authorization ticket: {assignment.get('assignment_id')}")
        if assignment.get("ticket_sha256"):
            expected_ticket = digest_json(assignment_ticket_payload(state, assignment))
            if expected_ticket != assignment.get("ticket_sha256"):
                raise MeginError(f"writer assignment ticket drifted: {assignment.get('assignment_id')}")
            expected_assignment = digest_json(assignment_digest_payload(assignment))
            if assignment.get("assignment_sha256") != expected_assignment:
                raise MeginError(f"writer assignment digest drifted: {assignment.get('assignment_id')}")
        validate_capability(
            assignment.get("capability_path"), assignment.get("capability_sha256"), state,
            kind="writer", assignment_id=assignment.get("assignment_id"),
            identity=assignment.get("writer_id"), session_id=assignment.get("session_id"),
        )
        if assignment.get("status") == "completed" and not assignment.get("writer_result"):
            raise MeginError(f"completed writer assignment has no result report: {assignment.get('assignment_id')}")
        if assignment.get("status") == "active" and assignment.get("ticket_consumed"):
            raise MeginError(f"active writer assignment has a consumed ticket: {assignment.get('assignment_id')}")
        if assignment.get("writer_result") is not None:
            if assignment.get("writer_result_sha256") != digest_json(assignment["writer_result"]):
                raise MeginError(f"writer result digest drifted: {assignment.get('assignment_id')}")
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
                raise MeginError(f"writer result is not bound to its assignment: {assignment.get('assignment_id')}")
            result_path = Path(assignment["writer_result"].get("evidence_path", "")).expanduser().resolve()
            evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
            try:
                result_path.relative_to(evidence_root)
            except ValueError as exc:
                raise MeginError(f"writer result evidence is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            if not result_path.exists() or read_json(result_path) != assignment["writer_result"]:
                raise MeginError(f"writer result evidence is missing or drifted: {assignment.get('assignment_id')}")
            report_path = Path(result.get("report_path", "")).expanduser().resolve()
            try:
                report_path.relative_to(evidence_root)
            except ValueError as exc:
                raise MeginError(f"writer report is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            if not report_path.exists() or digest_bytes(report_path.read_bytes()) != result.get("report_sha256"):
                raise MeginError(f"writer report evidence is missing or drifted: {assignment.get('assignment_id')}")
    review = state.get("review", {})
    if review.get("verdict"):
        assignment = next((item for item in assignments if item.get("assignment_id") == review.get("assignment_id")), None)
        if not assignment or review.get("assignment_sha256") != assignment.get("assignment_sha256"):
            raise MeginError(f"review is not bound to an assignment: {path}")
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
            raise MeginError(f"review ticket drifted: {path}")
        if review.get("reviewer_id") == assignment.get("writer_id") or review.get("reviewer_session") == assignment.get("session_id"):
            raise MeginError(f"reviewer is not independent from the writer: {path}")
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
            raise MeginError(f"review report is outside the persistent work state: {path}") from exc
        if not review_report_path.exists() or digest_bytes(review_report_path.read_bytes()) != review.get("report_sha256"):
            raise MeginError(f"review report evidence is missing or drifted: {path}")
        try:
            review_payload = read_json(review_report_path)
        except MeginError as exc:
            raise MeginError(f"review report evidence is invalid: {path}") from exc
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
            raise MeginError(f"review report is not bound to the saved review: {path}")
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
            raise MeginError(f"review test evidence does not cover the approved obligations: {path}")
        persisted_review_evidence_root = review_root / "evidence"
        seen_review_evidence: set[Path] = set()
        for item in review_payload.get("test_evidence", []):
            evidence_path = Path(str(item.get("evidence_path", ""))).expanduser().resolve()
            if evidence_path in seen_review_evidence:
                raise MeginError(f"review raw test evidence is reused: {path}")
            seen_review_evidence.add(evidence_path)
            if not _review_evidence_item_valid(
                item,
                commands=review_commands,
                expected_snapshot=review.get("snapshot"),
                evidence_root=persisted_review_evidence_root,
            ):
                raise MeginError(f"review raw test evidence is missing, stale, or drifted: {path}")
    verification = state.get("verification", {})
    if verification.get("record_sha256") != digest_json(verification_payload(verification)):
        raise MeginError(f"verification evidence digest drifted: {path}")
    verification_commands = verification.get("commands", [])
    if not isinstance(verification_commands, list):
        raise MeginError(f"verification command evidence is malformed: {path}")
    evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
    approved_commands = approved_verification_commands(state)
    legacy_commands = list(scope.get("test_commands", []))
    for index, record in enumerate(verification_commands, 1):
        if not isinstance(record, dict) or not record.get("evidence_path"):
            raise MeginError(f"verification command evidence is missing: {path}")
        if index <= len(approved_commands) and record.get("command") != approved_commands[index - 1]:
            raise MeginError(f"verification command evidence is not bound to the approved command: {path}")
        evidence_path = Path(record["evidence_path"]).expanduser().resolve()
        try:
            evidence_path.relative_to(evidence_root)
        except ValueError as exc:
            raise MeginError(f"verification evidence is outside the persistent work state: {path}") from exc
        if not evidence_path.exists() or not evidence_path.is_file():
            raise MeginError(f"verification raw output is missing: {path}")
        evidence_bytes = evidence_path.read_bytes()
        if digest_bytes(evidence_bytes) != record.get("output_sha256") or len(evidence_bytes) != record.get("output_bytes"):
            raise MeginError(f"verification raw output drifted: {path}")
    recorded_commands = [item.get("command") for item in verification_commands]
    if verification.get("status") == "passed" and recorded_commands not in (approved_commands, legacy_commands):
        raise MeginError(f"verification evidence does not cover every approved command: {path}")
    publication = state.get("publication", {})
    if publication.get("push_commit_sha") and publication.get("push_commit_sha") != publication.get("commit_sha"):
        raise MeginError(f"publication push evidence is bound to a different commit: {path}")
    if publication.get("commit_sha"):
        if not workspace.get("worktree"):
            raise MeginError(f"committed state has no delivery worktree: {path}")
        worktree = Path(workspace["worktree"]).resolve()
        if head_sha(worktree) != publication.get("commit_sha"):
            raise MeginError(f"saved commit SHA no longer matches the delivery branch: {path}")
        expected_snapshot = publication.get("post_commit_snapshot")
        if not expected_snapshot:
            raise MeginError(f"committed state is missing its post-commit snapshot: {path}")
        current_snapshot = working_tree_snapshot(worktree)
        if current_snapshot != expected_snapshot:
            if not post_commit_product_recovery_allowed(state, worktree):
                raise MeginError(f"working tree drifted after the committed review: {path}")
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
            except MeginError:
                continue
            candidates.append(path.stem)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise MeginError("no valid v2 run exists; provide --work-id or start a run")
    raise MeginError("multiple v2 runs exist; provide --work-id: " + ", ".join(candidates))


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
        raise MeginError(f"candidate source file does not exist: {source}")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise MeginError(f"cannot read candidate source file {source}: {exc}") from exc
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
    classification = state.get("task", {}).get("classification") or {}
    routing_risks = list(classification.get("routing_risks", []))
    open_questions = list(classification.get("open_questions", []))
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
            "## Risks and open questions\n"
            + "\n".join(f"- Risk: {item}" for item in routing_risks)
            + ("\n" if routing_risks else "")
            + "\n".join(f"- Question: {item}" for item in open_questions)
            + ("- none\n" if not routing_risks and not open_questions else "")
            + "\n"
            "## Work packages\n" + package_text + "\n\n"
            "## Test commands\n" + test_text + "\n\n"
            "## Steps\n- Implement the smallest approved change.\n- Run focused and related tests for each work package.\n- Obtain an independent review and full verification before delivery.\n\n"
            "## Knowledge and publication\n"
            f"- Knowledge scope: {', '.join(scope.get('knowledge_scope', [])) or 'none'}\n"
            f"- Publication remote: {scope.get('publication', {}).get('remote') or 'none'}\n"
            f"- Base branch: {scope.get('publication', {}).get('base_branch')}\n"
            f"- Base SHA: {scope.get('publication', {}).get('base_sha')}\n"
            f"- Workspace mode: {scope.get('publication', {}).get('workspace_mode')}\n"
            f"- Finish mode: {scope.get('publication', {}).get('finish_mode')}\n"
            f"- Feature branch: {scope.get('publication', {}).get('branch_prefix')}/<work-id>\n"
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
        + "## Risks and open questions\n"
        + "\n".join(f"- Risk: {item}" for item in routing_risks)
        + ("\n" if routing_risks else "")
        + "\n".join(f"- Question: {item}" for item in open_questions)
        + ("- none\n" if not routing_risks and not open_questions else "")
        + "\n"
        + "## Knowledge scope\n"
        + "\n".join(f"- {item}" for item in scope.get("knowledge_scope", []))
        + "\n\n## Publication target\n"
        + f"- Remote: {scope.get('publication', {}).get('remote') or 'none'}\n- Base branch: {scope.get('publication', {}).get('base_branch')}\n- Base SHA: {scope.get('publication', {}).get('base_sha')}\n- Workspace mode: {scope.get('publication', {}).get('workspace_mode')}\n- Finish mode: {scope.get('publication', {}).get('finish_mode')}\n- Feature branch: {scope.get('publication', {}).get('branch_prefix')}/<work-id>\n- Draft PR title: {scope.get('publication', {}).get('title')}\n"
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
        + f"- Base SHA: {scope.get('publication', {}).get('base_sha')}\n"
        + f"- Workspace mode: {scope.get('publication', {}).get('workspace_mode')}\n"
        + f"- Finish mode: {scope.get('publication', {}).get('finish_mode')}\n"
        + f"- Feature branch: {scope.get('publication', {}).get('branch_prefix')}/<work-id>\n"
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
            raise MeginError(f"{effective}-task {name} candidate is missing")
        path = Path(candidate["path"]).expanduser().resolve()
        expected_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"]
        try:
            path.relative_to(expected_root)
        except ValueError as exc:
            raise MeginError(f"{name} candidate is outside the persistent work state") from exc
        if not path.exists() or not path.is_file():
            raise MeginError(f"{effective}-task {name} candidate is missing: {path}")
        try:
            actual = digest_bytes(path.read_bytes())
        except OSError as exc:
            raise MeginError(f"cannot read {name} candidate: {path}") from exc
        if actual != candidate.get("sha256"):
            raise MeginError(f"{name} candidate digest drifted; re-plan and create a new Work ID")
        if candidate.get("revision") != candidate_revision(state):
            raise MeginError(f"{name} candidate revision is not the active revision")
        candidate_stage = "integrated" if name == "design" else name
        if state.get("approval", {}).get("status") == "approved" and candidate_stage in set(state.get("approval", {}).get("approved_stages", [])) and candidate.get("status") != "approved":
            raise MeginError(f"{name} candidate is not marked approved")


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
        "routing_risks": (state.get("task", {}).get("classification") or {}).get("routing_risks", []),
        "open_questions": (state.get("task", {}).get("classification") or {}).get("open_questions", []),
        "phase": state.get("phase"),
        "status": state.get("status"),
        "approval": state.get("approval", {}).get("status"),
        "approval_policy": state.get("approval", {}).get("policy"),
        "approval_stages": state.get("approval", {}).get("approved_stages", []),
        "approval_digest": state.get("approval", {}).get("payload_sha256"),
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
        "workspace_mode": state.get("workspace", {}).get("mode") or state.get("publication", {}).get("workspace_mode"),
        "finish_mode": state.get("publication", {}).get("finish_mode"),
        "base_branch": state.get("workspace", {}).get("base_branch") or state.get("publication", {}).get("base_branch"),
        "base_sha": state.get("workspace", {}).get("base_sha") or state.get("publication", {}).get("base_sha"),
        "suggested_commit": state.get("publication", {}).get("suggested_commit"),
        "delivered_snapshot": state.get("publication", {}).get("delivered_snapshot"),
        "changed_paths": state.get("publication", {}).get("changed_paths", []),
        "next_action": state.get("next_action"),
        "worktree": state.get("workspace", {}).get("worktree"),
        "branch": state.get("workspace", {}).get("branch"),
        "commit": state.get("publication", {}).get("commit_sha"),
        "state_path": str(path),
        "updated_at": state.get("updated_at"),
    }


def emit(value: Any, args: argparse.Namespace | None = None) -> None:
    if args is not None and getattr(args, "human", False):
        print(human_summary(value))
        return
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


def human_summary(value: Any) -> str:
    """Render a concise operator-facing report without nested state JSON."""

    if not isinstance(value, dict):
        return str(value)
    lines: list[str] = []
    labels = {"read_only": "唯讀", "small": "小任務", "large": "大型變更", "bug": "疑似 BUG"}
    if value.get("task_class"):
        lines.append(f"分類：{labels.get(value['task_class'], value['task_class'])}")
        if value.get("reason"):
            lines.append(f"判定：{value['reason']}")
    if value.get("confidence"):
        lines.append(f"信心：{value['confidence']}")
    if "run_created" in value:
        lines.append(f"建立 run：{'是' if value['run_created'] else '否'}")
    if value.get("needs_clarification"):
        lines.append("需要釐清：是")
    if value.get("work_id"):
        lines.append(f"Work ID：{value['work_id']}")
    if value.get("status"):
        lines.append(f"狀態：{value['status']}")
    if value.get("phase"):
        lines.append(f"階段：{value['phase']}")
    if value.get("approval"):
        lines.append(f"核准：{value['approval']}")
    if value.get("workspace_mode"):
        lines.append(f"工作目錄模式：{value['workspace_mode']}")
    if value.get("finish_mode"):
        lines.append(f"交付模式：{value['finish_mode']}")
    if value.get("branch"):
        lines.append(f"分支：{value['branch']}")
    if value.get("worktree"):
        lines.append(f"工作路徑：{value['worktree']}")
    if value.get("base_branch"):
        lines.append(f"基底分支：{value['base_branch']}")
    if value.get("base_sha"):
        lines.append(f"基底 SHA：{value['base_sha']}")
    if value.get("routing_risks"):
        lines.append(f"風險：{'; '.join(str(item) for item in value['routing_risks'])}")
    if value.get("open_questions"):
        lines.append(f"待決問題：{'; '.join(str(item) for item in value['open_questions'])}")
    tasks = value.get("tasks")
    if isinstance(tasks, list):
        paths = sorted({path for task in tasks if isinstance(task, dict) for path in task.get("allowed_paths", [])})
        if paths:
            lines.append(f"主要變更：{', '.join(paths)}")
    current = value.get("current")
    if isinstance(current, dict):
        task_id = current.get("task_id") or current.get("assignment_id")
        writer = current.get("writer_id") or current.get("writer")
        if task_id or writer:
            lines.append(f"目前工作：{task_id or 'unknown'}；writer：{writer or 'unknown'}")
    if value.get("completed"):
        lines.append(f"已完成：{', '.join(str(item) for item in value['completed'])}")
    if value.get("review"):
        lines.append(f"審查：{value['review']}")
    if value.get("verification"):
        lines.append(f"驗證：{value['verification']}")
    if value.get("publication"):
        lines.append(f"交付：{value['publication']}")
    if value.get("knowledge"):
        lines.append(f"知識：{value['knowledge']}")
    if value.get("knowledge_conflicts"):
        lines.append(f"知識待決：{'; '.join(str(item) for item in value['knowledge_conflicts'])}")
    if value.get("commit"):
        lines.append(f"Commit：{value['commit']}")
    candidates = value.get("candidates")
    if isinstance(candidates, dict):
        for name, candidate in candidates.items():
            if isinstance(candidate, dict) and candidate.get("path"):
                lines.append(f"候選文件（{name}）：{candidate['path']}")
    if value.get("changed_paths"):
        lines.append(f"交付檔案：{', '.join(str(item) for item in value['changed_paths'])}")
    if value.get("suggested_commit"):
        lines.append("建議 commit：")
        lines.append(str(value["suggested_commit"]))
    if value.get("next_action"):
        lines.append(f"下一步：{value['next_action']}")
    if value.get("state_path"):
        lines.append(f"狀態檔：{value['state_path']}")
    if not lines:
        for key in ("initialized", "already_initialized", "ok", "next_action"):
            if key in value:
                lines.append(f"{key}：{value[key]}")
    return "\n".join(lines)


def create_worktree(repo: Path, work_id: str, base_sha: str) -> tuple[Path, str]:
    branch = f"delivery/{work_id}"
    parent = repo.parent / f"{repo.name}.worktrees"
    worktree = parent / work_id
    if worktree.exists():
        raise MeginError(f"worktree already exists: {worktree}")
    if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).strip():
        raise MeginError(f"delivery branch already exists: {branch}")
    parent.mkdir(parents=True, exist_ok=True)
    result = run_process(("git", "worktree", "add", "-b", branch, str(worktree), base_sha), repo, timeout=120)
    if result.returncode != 0:
        detail = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise MeginError(f"cannot create delivery worktree ({result.returncode}): {detail}")
    return worktree.resolve(), branch


def assert_current_workspace_available(repo: Path, work_id: str) -> None:
    """Prevent two active v2 runs from writing the same checkout."""

    try:
        directory = state_directory(repo)
    except MeginError:
        return
    if not directory.exists():
        return
    target = repo.resolve()
    for path in directory.glob("*.json"):
        if path.stem == work_id:
            continue
        try:
            candidate = read_json(path)
        except Exception:
            continue
        workspace = candidate.get("workspace") or {}
        workspace_path = workspace.get("repo") or workspace.get("worktree")
        if workspace.get("mode") != "current" or not workspace_path:
            continue
        try:
            same_repo = Path(workspace_path).resolve() == target
        except OSError:
            same_repo = False
        # A pending candidate has not acquired a writer workspace yet and may
        # coexist with another discussion.  Once a workspace exists, active
        # and blocked runs retain the single-writer reservation until they are
        # explicitly completed or abandoned.
        bound = bool(workspace.get("worktree"))
        if same_repo and (candidate.get("status") in ("active", "blocked") or (bound and candidate.get("status") == "awaiting_approval")):
            raise MeginError(
                f"current workspace is already bound to active Work ID {path.stem}; "
                "resume or complete that run before starting another writer"
            )


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
            raise MeginError(f"work-package file is not valid JSON: {path}") from exc
        entries = data.get("work_packages") if isinstance(data, dict) and "work_packages" in data else data
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            raise MeginError(f"work-package file must contain an object or array: {path}")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                raise MeginError(f"work-package file contains an invalid entry: {path}")
            identifier = str(entry["id"]).strip()
            if identifier in specs:
                raise MeginError(f"duplicate work-package specification: {identifier}")
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
            raise MeginError("work-package IDs must contain only letters, digits, dots, underscores, or hyphens")
        if identifier in seen:
            raise MeginError(f"duplicate work package: {identifier}")
        seen.add(identifier)
        spec = specs.get(identifier, {})
        acceptance = [redact(str(item)) for item in (spec.get("acceptance") or [f"{item} ({identifier})" for item in scope["acceptance"]])]
        allowed = normalize_paths(spec.get("allowed_paths") or scope["allowed_paths"])
        if any(not allowed_path(item, scope["allowed_paths"]) for item in allowed):
            raise MeginError(f"work package {identifier} is outside the approved allowed paths")
        forbidden = normalize_paths(spec.get("forbidden_paths") or [])
        if any(allowed_path(item, allowed) for item in forbidden):
            raise MeginError(f"work package {identifier} forbidden paths overlap its allowed paths")
        interfaces = [redact(str(item)) for item in (spec.get("interfaces") or [])]
        focused = [validate_command_text(str(item)) for item in (spec.get("focused_commands") or scope["test_commands"])]
        related = [validate_command_text(str(item)) for item in (spec.get("related_commands") or scope["test_commands"])]
        full = [validate_command_text(str(item)) for item in (spec.get("full_commands") or scope["test_commands"])]
        if "blocked_by" in spec or "depends_on" in spec:
            for dependency_key in ("blocked_by", "depends_on"):
                raw_dependencies = spec.get(dependency_key)
                if raw_dependencies is not None and not isinstance(raw_dependencies, list):
                    raise MeginError(f"work package {identifier} {dependency_key} must be an array")
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
        raise MeginError("work-package file contains packages not requested: " + ", ".join(unknown))
    known = {task["id"] for task in result}
    for task in result:
        dependencies = list(task.get("depends_on", [])) + list(task.get("blocked_by", []))
        if task["id"] in dependencies or any(item not in known for item in dependencies):
            raise MeginError(f"work package {task['id']} has an invalid dependency")
    graph = {task["id"]: set(task.get("depends_on", [])) | set(task.get("blocked_by", [])) for task in result}
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise MeginError("work-package dependency graph contains a cycle")
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


def rebind_assignment_authorizations(state: dict[str, Any], repo: Path) -> None:
    """Reissue writer handoffs after a publication-only candidate rebind.

    Changing finish mode changes the approval digest, so the old assignment
    ticket cannot remain valid.  The implementation result itself is retained;
    only its controller-owned ticket binding is refreshed.
    """

    evidence_root = state_root(state["repo"]["repo_id"], repo) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
    for assignment in state.get("assignments", []):
        writer_id = assignment.get("writer_id") or assignment.get("writer")
        session_id = assignment.get("session_id") or assignment.get("session")
        capability_path, capability_sha = register_capability(
            state,
            repo,
            kind="writer",
            identity=writer_id,
            session_id=session_id,
            assignment_id=assignment.get("assignment_id"),
            read_only=False,
        )
        assignment["capability_path"] = capability_path
        assignment["capability_sha256"] = capability_sha
        assignment["ticket_sha256"] = digest_json(assignment_ticket_payload(state, assignment))
        writer_result = assignment.get("writer_result")
        if isinstance(writer_result, dict):
            writer_result["ticket_sha256"] = assignment["ticket_sha256"]
            result_path = Path(str(writer_result.get("evidence_path", ""))).expanduser().resolve()
            try:
                result_path.relative_to(evidence_root.resolve())
            except ValueError as exc:
                raise MeginError(f"writer result evidence is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            report_path = Path(str(writer_result.get("report_path", ""))).expanduser().resolve()
            try:
                report_path.relative_to(evidence_root.resolve())
            except ValueError as exc:
                raise MeginError(f"writer report is outside the persistent work state: {assignment.get('assignment_id')}") from exc
            if report_path.exists():
                report = read_json(report_path)
                if report.get("schema") != WRITER_REPORT_SCHEMA:
                    raise MeginError(f"writer report schema is not compatible with the current state: {assignment.get('assignment_id')}")
                if "ticket_sha256" in report:
                    report["ticket_sha256"] = assignment["ticket_sha256"]
                    write_json_atomic(report_path, report)
                    writer_result["report_sha256"] = digest_bytes(report_path.read_bytes())
            write_json_atomic(result_path, writer_result)
            assignment["writer_result_sha256"] = digest_json(writer_result)
        refresh_assignment_digest(assignment)


def assignment_authorizations_current(state: dict[str, Any]) -> bool:
    return all(
        digest_json(assignment_ticket_payload(state, assignment)) == assignment.get("ticket_sha256")
        for assignment in state.get("assignments", [])
    )


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
        raise MeginError("no uncompleted work package is ready for assignment")
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
        raise MeginError("no uncompleted work package is ready for assignment")
    task["status"] = "active"
    assignment_id = f"assignment-{len(state.get('assignments', [])) + 1}"
    state.setdefault("assignments", []).append(_new_assignment(state, args, assignment_id, task_id=task["id"], repo=repo))


def append_assignment(state: dict[str, Any], args: argparse.Namespace, repo: Path | None = None, task_id: str | None = None) -> None:
    assignment_id = f"assignment-{len(state.get('assignments', [])) + 1}"
    previous = state.get("assignments", [])[-1] if state.get("assignments") else None
    writer = (previous or {}).get("writer_id", (previous or {}).get("writer"))
    requested = getattr(args, "writer_id", None) or getattr(args, "writer", None)
    if requested and writer and requested != writer:
        raise MeginError("a review correction must return to the assigned implementation writer")
    if task_id is None and previous and previous.get("status") == "needs_revision":
        task_id = previous.get("task_id")
    if task_id is None:
        ready = next_ready_task(state)
        if not ready:
            raise MeginError("no dependent work package is ready for assignment")
        task_id = ready["id"]
    task = task_for_id(state, task_id)
    if not task:
        raise MeginError(f"unknown work package: {task_id}")
    if task.get("status") == "pending":
        task["status"] = "active"
    state.setdefault("assignments", []).append(_new_assignment(state, args, assignment_id, writer=writer, task_id=task_id, repo=repo))


def base_sha_for_state(repo: Path, state: dict[str, Any]) -> str:
    """Resolve the approved configured base branch before creating a worktree."""

    approved_sha = state.get("approval", {}).get("scope", {}).get("publication", {}).get("base_sha")
    if approved_sha:
        if not re.fullmatch(r"[a-f0-9]{40}", str(approved_sha)):
            raise MeginError("approved base SHA is invalid")
        return str(approved_sha)
    configured = (
        state.get("approval", {}).get("scope", {}).get("publication", {}).get("base_branch")
        or state.get("repo", {}).get("base_branch")
        or current_branch(repo)
    )
    branch = validate_branch_name(configured)
    remote = state.get("approval", {}).get("scope", {}).get("publication", {}).get("remote")
    return resolve_base_sha(repo, branch, remote)


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
        bound_workspace = Path(state["workspace"]["worktree"]).resolve()
        if not bound_workspace.exists():
            raise MeginError(f"approved delivery workspace is missing: {bound_workspace}")
        bound_branch = state.get("workspace", {}).get("branch")
        if bound_branch and current_branch(bound_workspace) != bound_branch:
            raise MeginError("approved workspace branch changed; stop before dispatching another writer")
        expected_head = state.get("publication", {}).get("commit_sha") or state.get("workspace", {}).get("base_sha")
        if expected_head and head_sha(bound_workspace) != expected_head:
            raise MeginError(
                "approved workspace HEAD changed; stop before dispatching another writer and inspect the snapshot"
            )
        if not state.get("assignments") and not all_tasks_completed(state):
            dirty_paths, _ = status_paths(bound_workspace)
            if dirty_paths:
                raise MeginError(
                    "approved workspace changed before the first writer dispatch; inspect the external changes before writing"
                )
        previous_approval_digest = state["approval"].get("payload_sha256")
        state["approval"]["status"] = "approved"
        if not state.get("publication", {}).get("commit_sha"):
            state["status"] = "active"
            state["phase"] = "implementation"
        else:
            state["status"] = "complete" if state.get("publication", {}).get("state") == "draft_pr_created" else "active"
            state["phase"] = "delivery"
        refresh_approval_digests(state)
        if state.get("assignments") and previous_approval_digest != state["approval"].get("payload_sha256"):
            rebind_assignment_authorizations(state, repo)
        if not state.get("assignments") and not all_tasks_completed(state):
            state["phase"] = "implementation"
            ensure_assignment(state, args, repo)
        elif not state.get("publication", {}).get("commit_sha") and all_tasks_completed(state):
            state["next_action"] = "obtain a fresh independent review"
        return
    base = base_sha_for_state(repo, state)
    publication = state["approval"].get("scope", {}).get("publication", {})
    workspace_mode = publication.get("workspace_mode") or state.get("workspace", {}).get("mode")
    if workspace_mode is None:
        # Pre-0.3 v2 records did not carry a workspace mode.  Preserve their
        # historical isolated-worktree contract when a newer engine resumes
        # them; only a new candidate gets the current-directory default.
        workspace_mode = "worktree"
    base_branch = publication.get("base_branch") or state.get("repo", {}).get("base_branch") or default_base_branch(repo)
    branch_prefix = publication.get("branch_prefix") or "feat"
    approved_remote = publication.get("remote")
    if resolve_base_sha(repo, base_branch, approved_remote) != base:
        raise MeginError("approved base branch changed since the candidate was created; refresh the candidate and approve again")
    if workspace_mode == "current":
        ensure_clean_start(repo)
        assert_current_workspace_available(repo, state["work_id"])
        worktree, branch = create_current_branch(
            repo, state["work_id"], base, base_branch, branch_prefix, approved_remote,
        )
    else:
        worktree, branch = create_worktree(repo, state["work_id"], base)
    state["workspace"] = {
        "mode": workspace_mode,
        "worktree": str(worktree),
        "branch": branch,
        "base_branch": base_branch,
        "base_sha": base,
        "repo": str(repo),
        "created_at": now(),
    }
    state["approval"]["status"] = "approved"
    state["phase"] = "implementation"
    state["status"] = "active"
    state["next_action"] = "implementation writer executes the next uncompleted work package"
    refresh_verification_digest(state)
    refresh_approval_digests(state)
    ensure_assignment(state, args, repo)
    append_event(
        state,
        "workspace_created" if workspace_mode == "current" else "worktree_created",
        phase="implementation",
        status="active",
    )


def make_state(repo: Path, work_id: str, request: str, classification: dict[str, Any], args: argparse.Namespace, config: dict[str, Any] | None) -> dict[str, Any]:
    task_class = classification["task_class"]
    repair_class = getattr(args, "repair_class", None)
    diagnosis_assessment: dict[str, Any] | None = None
    if task_class != "bug" and repair_class:
        raise MeginError("--repair-class is only valid for a diagnosed bug")
    if task_class == "bug":
        diagnosis_file = getattr(args, "diagnosis_file", None)
        if not diagnosis_file:
            raise MeginError("bug work requires a read-only --diagnosis-file assessment before a delivery state is created")
        diagnosis_payload, diagnosis_path = load_diagnosis_assessment(diagnosis_file, repo, request)
        if diagnosis_payload.get("disposition") not in ("confirmed", "likely"):
            raise MeginError("only confirmed or likely diagnosis assessments can enter a repair workflow")
        if getattr(args, "diagnosis", None) and args.diagnosis != diagnosis_payload.get("disposition"):
            raise MeginError("--diagnosis does not match the supplied assessment")
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
            raise MeginError("bug repair class must be small or large")
    scope = build_scope(args, {**(config or {}), "repo_path": str(repo)})
    policy = "integrated" if (repair_class or task_class) == "small" else "requirements_and_plan"
    stages = approval_args(args)
    permitted_stages = {"integrated"} if policy == "integrated" else {"requirements", "plan"}
    unexpected_stages = stages - permitted_stages
    if unexpected_stages:
        raise MeginError(f"approval stage(s) {', '.join(sorted(unexpected_stages))} do not apply to {policy} workflow")
    if policy == "requirements_and_plan" and "plan" in stages and "requirements" not in stages:
        raise MeginError("large-change planning approval requires a prior requirements approval")
    if policy == "requirements_and_plan" and {"requirements", "plan"}.issubset(stages):
        raise MeginError("large-change requirements and plan approvals must be separate resume transitions")
    # An explicit --approve without a value is represented as integrated by argparse.
    request_sha = digest_text(request)
    state: dict[str, Any] = {
        "schema": SCHEMA,
        "version": 2,
        "plugin": "megin",
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
        "workspace": {
            "mode": scope["publication"].get("workspace_mode", "current"),
            "worktree": None,
            "branch": None,
            "base_branch": scope["publication"].get("base_branch"),
            "base_sha": None,
            "repo": str(repo),
            "created_at": None,
        },
        "phase": "requirements" if policy == "requirements_and_plan" else "implementation",
        "status": "awaiting_approval",
        "tasks": build_work_packages(args, scope, repo),
        "assignments": [],
        "review": {"verdict": None, "reviewer_id": None, "reviewer_session": None, "reviewer_capability_path": None, "reviewer_capability_sha256": None, "assignment_id": None, "assignment_sha256": None, "round": 0, "review_ticket_sha256": None, "snapshot": None, "product_snapshot": None, "paths": [], "findings": [], "no_progress_count": 0, "report_path": None, "report_sha256": None, "requirements_verdict": None, "quality_verdict": None, "test_evidence": []},
        "verification": {"status": "not_run", "commands": [], "snapshot": None, "record_sha256": None},
        "knowledge": {"scope": scope["knowledge_scope"], "status": "not_needed" if not scope["knowledge_scope"] else "pending", "candidate_path": None, "candidate_sha256": None, "sources": [], "certainty": None, "snapshot_before": None, "snapshot_after": None, "lint": None, "conflicts": [], "reviewer_id": None, "reviewer_session": None, "report_path": None, "report_sha256": None, "promotion": None},
        "candidates": {"design": None, "requirements": None, "plan": None},
        "publication": {
            "remote": scope["publication"]["remote"],
            "remote_url_sha256": scope["publication"].get("remote_url_sha256"),
            "base_branch": scope["publication"]["base_branch"],
            "base_sha": scope["publication"].get("base_sha"),
            "title": scope["publication"]["title"],
            "workspace_mode": scope["publication"].get("workspace_mode", "current"),
            "finish_mode": scope["publication"].get("finish_mode", "unstaged"),
            "branch_prefix": scope["publication"].get("branch_prefix", "feat"),
            "state": "not_ready",
            "commit_sha": None,
            "push_commit_sha": None,
            "post_commit_snapshot": None,
            "post_commit_product_snapshot": None,
            "delivered_snapshot": None,
            "changed_paths": [],
            "suggested_commit": None,
            "pr": None,
            "reason": None,
        },
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
    finish_mode_rebind = False
    if getattr(args, "work_package", None) or getattr(args, "work_package_file", None):
        raise MeginError("dispatch packages are fixed when the Work ID is started; create a new Work ID to change them")
    if getattr(args, "routing_file", None):
        checked = load_routing_evidence(
            args.routing_file,
            state.get("task", {}).get("request", ""),
            Path(state["repo"]["path"]),
            request_sha256=state.get("task", {}).get("request_sha256"),
            verify_head=False,
        )
        bound = (state.get("task", {}).get("classification") or {}).get("routing_evidence") or {}
        if checked.get("sha256") != bound.get("sha256"):
            raise MeginError("routing evidence differs from the approved Work ID candidate; create a new Work ID")
    if state["approval"]["status"] == "approved":
        scope_inputs = ("allowed_path", "test_command", "knowledge_path", "acceptance", "design_file", "requirements_file", "plan_file", "remote", "base_branch", "workspace_mode", "finish_mode", "branch_prefix", "title")
        only_finish_rebind = (
            bool(getattr(args, "finish_mode", None))
            and state.get("publication", {}).get("state") == "delivered_unstaged"
            and getattr(args, "finish_mode", None) != state.get("publication", {}).get("finish_mode")
            and not any(getattr(args, name, None) for name in scope_inputs if name != "finish_mode")
        )
        finish_mode_rebind = only_finish_rebind
        if any(getattr(args, name, None) for name in scope_inputs) and not only_finish_rebind:
            raise MeginError("approved scope is immutable; create a new revision instead of changing it")
        if not only_finish_rebind:
            return
    stages = approval_args(args)
    existing_stages = set(state["approval"].get("approved_stages", []))
    permitted_stages = {"integrated"} if state["approval"].get("policy") == "integrated" else {"requirements", "plan"}
    unexpected_stages = stages - permitted_stages
    if unexpected_stages:
        raise MeginError(f"approval stage(s) {', '.join(sorted(unexpected_stages))} do not apply to {state['approval'].get('policy')} workflow")
    if state["approval"].get("policy") == "requirements_and_plan" and {"requirements", "plan"}.issubset(stages):
        raise MeginError("large-change requirements and plan approvals must be separate resume transitions")
    if "plan" in stages and "requirements" not in stages and "requirements" not in existing_stages:
        raise MeginError("large-change planning approval requires a prior requirements approval")
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
        raise MeginError("knowledge scope must be contained in the approved allowed paths")
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
        or (getattr(args, "workspace_mode", None) is not None and args.workspace_mode != scope.get("publication", {}).get("workspace_mode"))
        or (getattr(args, "finish_mode", None) is not None and args.finish_mode != scope.get("publication", {}).get("finish_mode"))
        or (getattr(args, "branch_prefix", None) is not None and args.branch_prefix != scope.get("publication", {}).get("branch_prefix"))
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
        if getattr(args, "remote", None) is not None or getattr(args, "base_branch", None) is not None:
            scope["publication"]["base_sha"] = resolve_base_sha(
                Path(state["repo"]["path"]),
                scope["publication"]["base_branch"],
                scope["publication"].get("remote"),
            )
        if getattr(args, "workspace_mode", None) is not None:
            if args.workspace_mode not in WORKSPACE_MODES:
                raise MeginError(f"workspace mode must be one of {', '.join(WORKSPACE_MODES)}")
            scope["publication"]["workspace_mode"] = args.workspace_mode
        if getattr(args, "finish_mode", None) is not None:
            if args.finish_mode not in FINISH_MODES:
                raise MeginError(f"finish mode must be one of {', '.join(FINISH_MODES)}")
            scope["publication"]["finish_mode"] = args.finish_mode
        if getattr(args, "branch_prefix", None) is not None:
            scope["publication"]["branch_prefix"] = validate_branch_prefix(args.branch_prefix)
        if getattr(args, "title", None) is not None:
            scope["publication"]["title"] = redact(args.title)[:200]
        state["publication"]["remote"] = scope["publication"].get("remote")
        state["publication"]["remote_url_sha256"] = scope["publication"].get("remote_url_sha256")
        state["publication"]["base_branch"] = scope["publication"].get("base_branch")
        state["publication"]["base_sha"] = scope["publication"].get("base_sha")
        # Do not fill new mode fields into an old v2 candidate just because a
        # path or command was edited.  Missing fields carry the historical
        # worktree/commit semantics until the caller explicitly selects a new
        # destination.
        for key in ("workspace_mode", "finish_mode", "branch_prefix"):
            if key in scope["publication"]:
                state["publication"][key] = scope["publication"][key]
        state["publication"]["title"] = scope["publication"].get("title")
        if finish_mode_rebind:
            state["publication"]["state"] = "not_ready"
            state["publication"]["commit_sha"] = None
            state["publication"]["push_commit_sha"] = None
            state["publication"]["post_commit_snapshot"] = None
            state["publication"]["post_commit_product_snapshot"] = None
            state["publication"]["delivered_snapshot"] = None
            state["publication"]["suggested_commit"] = None
            state["publication"]["changed_paths"] = []
            state["publication"]["pr"] = None
            state["publication"]["reason"] = None
            invalidate_verification(state)
            state["phase"] = "implementation"
            state["status"] = "active"
            state["next_action"] = "obtain a fresh independent review after re-approving the delivery mode"
            append_event(state, "finish_mode_rebound", phase="implementation", status="active")
        # Any scope edit creates a new candidate revision and invalidates approvals
        # collected for the previous candidate.  The caller must approve again.
        bump_candidate_revision(state)
        state["approval"]["approved_stages"] = []
        state["approval"]["refs"] = {stage: [] for stage in APPROVAL_STAGES}
        state["approval"]["status"] = "pending"
        state["review"] = {"verdict": None, "reviewer_id": None, "reviewer_session": None, "reviewer_capability_path": None, "reviewer_capability_sha256": None, "assignment_id": None, "assignment_sha256": None, "round": 0, "review_ticket_sha256": None, "snapshot": None, "product_snapshot": None, "paths": [], "findings": [], "no_progress_count": 0, "report_path": None, "report_sha256": None, "requirements_verdict": None, "quality_verdict": None, "test_evidence": []}
    refresh_approval_digests(state)
    if finish_mode_rebind:
        rebind_assignment_authorizations(state, Path(state["repo"]["path"]))
    state["approval"]["status"] = "pending"
    refresh_approval_digests(state)


def cmd_classify(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo) if getattr(args, "repo", None) else None
    result = explicit_class(args.request, args.task_class, repo, getattr(args, "routing_file", None))
    result["request_sha256"] = digest_text(args.request)
    result["run_created"] = False
    if result.get("needs_clarification"):
        result["next_action"] = "clarify the request intent, scope, or unresolved routing questions; no delivery run is created"
    emit(result, args)
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Run a read-only bug oracle without creating a delivery workspace/run."""

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
    path = repo / ".megin" / "config.json"
    ensure_megin_excluded(repo)
    existing = path.exists()
    if existing and not args.force:
        config = load_config(repo, required=True)
        emit({"initialized": False, "already_initialized": True, "config_path": str(path), "config": config}, args)
        return 0
    base_branch = validate_branch_name(args.base_branch or default_base_branch(repo))
    commands = list(args.test_command or [])
    for command in commands:
        validate_command_text(command)
    if not commands:
        commands = ["python -m unittest discover"]
    remote = validate_remote_name(args.remote) if args.remote is not None else ("origin" if git_remote(repo, "origin") else None)
    workspace_mode = args.workspace_mode or "current"
    finish_mode = args.finish_mode or "unstaged"
    if workspace_mode not in WORKSPACE_MODES:
        raise MeginError(f"workspace mode must be one of {', '.join(WORKSPACE_MODES)}")
    if finish_mode not in FINISH_MODES:
        raise MeginError(f"finish mode must be one of {', '.join(FINISH_MODES)}")
    branch_prefix = validate_branch_prefix(args.branch_prefix or "feat")
    config = {
        "schema": CONFIG_SCHEMA,
        "plugin": "megin",
        "plugin_version": PLUGIN_VERSION,
        "repo_id": repo_identity(repo),
        "repo_path": str(repo),
        "base_branch": base_branch,
        "branch_prefix": branch_prefix,
        "test_commands": commands,
        "remote": remote,
        "state_root_policy": "user-state-outside-repository",
        "created_at": now(),
    }
    if args.workspace_mode is not None:
        config["workspace_mode"] = workspace_mode
    if args.finish_mode is not None:
        config["finish_mode"] = finish_mode
    write_json_atomic(path, config)
    emit({"initialized": True, "config_path": str(path), "config": config, "state_root": str(state_root(config["repo_id"], repo))}, args)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    classification = explicit_class(args.request, args.task_class, repo, getattr(args, "routing_file", None))
    if classification.get("needs_clarification"):
        emit({**classification, "request_sha256": digest_text(args.request), "run_created": False, "next_action": "clarify the request intent, scope, or unresolved routing questions"}, args)
        return 0
    if classification["task_class"] == "read_only":
        emit({**classification, "request_sha256": digest_text(args.request), "run_created": False, "next_action": "report evidence; no delivery run is created"}, args)
        return 0
    if classification["task_class"] == "bug":
        if not args.diagnosis_file:
            emit({**classification, "run_created": False, "next_action": "run `megin diagnose` and re-run with --diagnosis-file <assessment>"}, args)
            return 0
        assessment, assessment_path = load_diagnosis_assessment(args.diagnosis_file, repo, args.request)
        if assessment.get("disposition") == "not-a-bug":
            emit({**classification, "run_created": False, "diagnosis": assessment.get("disposition"), "assessment_path": str(assessment_path), "next_action": "no repair run is authorized; if behavior should change, submit a new small or large request"}, args)
            return 0
        if assessment.get("disposition") not in ("confirmed", "likely"):
            emit({**classification, "run_created": False, "diagnosis": assessment.get("disposition"), "assessment_path": str(assessment_path), "next_action": "resolve the blocked or partial diagnosis before starting repair"}, args)
            return 0
    config = load_config(repo, required=True)
    ensure_megin_excluded(repo)
    work_id = validate_work_id(args.work_id) if args.work_id else make_work_id(args.request)
    path = state_path(repo, work_id)
    state = make_state(repo, work_id, args.request, classification, args, config)
    reserve_state_file(path)
    binding_lock: Path | None = None
    try:
        materialize_candidate_bundles(state, repo, args)
        refresh_approval_digests(state)
        save_state(state, path)
        workspace_mode = state.get("approval", {}).get("scope", {}).get("publication", {}).get("workspace_mode")
        if workspace_mode == "current":
            workspace_binding_path(repo).parent.mkdir(parents=True, exist_ok=True)
            binding_lock = acquire_state_lock(workspace_binding_path(repo))
        activate_if_approved(state, repo, args)
        save_state(state, path)
    except Exception:
        # Activation may have created a branch/worktree before the second
        # state write.  Preserve that evidence so a later resume can prove and
        # recover the same Work ID; only remove an unactivated reservation.
        if state.get("workspace", {}).get("worktree"):
            try:
                save_state(state, path)
            except Exception:
                pass
        else:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        if binding_lock is not None:
            release_state_lock(binding_lock)
    result = state_summary(state, path)
    result["run_created"] = True
    emit(result, args)
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
        raise MeginError("writer report must use megin-writer-report/v1")
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
            raise MeginError(f"writer report {key} is not bound to the current assignment")
    writer_status = payload.get("status")
    if writer_status not in ("completed", "needs_revision", "blocked", "awaiting_upstream"):
        raise MeginError("writer report has an unsupported status")
    baseline_changes = baseline_manifest_changed(assignment, worktree)
    if baseline_changes:
        raise MeginError(
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
        raise MeginError("writer report contains paths outside the task-specific dispatch package")
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
        raise MeginError("writer changed paths outside the task-specific dispatch package: " + ", ".join(current_violations))
    if changed_paths != current_paths:
        raise MeginError("writer report changed paths do not match the current worktree")
    snapshot = working_tree_snapshot(worktree)
    if payload.get("snapshot") != snapshot:
        raise MeginError("writer report snapshot does not match the current worktree")
    if payload.get("changed_paths") is None or not isinstance(payload.get("changed_paths"), list):
        raise MeginError("writer report must include changed paths")
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
        raise MeginError("writer report must include passing focused and related test evidence")
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
        raise MeginError("review findings must be supplied by the external --review-report")
    payload, source_path, _ = load_external_report(getattr(args, "review_report", None), worktree, label="review")
    if payload.get("schema") != REVIEW_REPORT_SCHEMA:
        raise MeginError("review report must use megin-review-report/v1")
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
            raise MeginError(f"review report {key} is not bound to the current assignment snapshot")
    report_paths = normalize_paths(payload.get("paths", []))
    current_paths, _ = status_paths(worktree)
    if report_paths != current_paths:
        raise MeginError("review report paths do not match the current worktree")
    if payload.get("requirements_verdict") not in ("APPROVED", "CHANGES_REQUIRED", "BLOCKED"):
        raise MeginError("review report must include a requirements verdict")
    if payload.get("quality_verdict") not in ("APPROVED", "CHANGES_REQUIRED", "BLOCKED"):
        raise MeginError("review report must include a quality verdict")
    if verdict == "APPROVED" and (payload.get("requirements_verdict") != "APPROVED" or payload.get("quality_verdict") != "APPROVED"):
        raise MeginError("an approved review requires both requirements and quality verdicts to be APPROVED")
    raw_findings = payload.get("findings", [])
    if not isinstance(raw_findings, list):
        raise MeginError("review report findings must be an array")
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
        raise MeginError("review report must include passing focused, related, and full test evidence")
    normalized_findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_findings:
        if isinstance(item, str):
            item = {"key": stable_finding_key(item), "text": item}
        if not isinstance(item, dict) or not item.get("key") or not item.get("text"):
            raise MeginError("each review finding must include a stable key and text")
        key = str(item["key"]).strip()
        if key in seen:
            raise MeginError("review findings contain duplicate stable keys")
        seen.add(key)
        finding = {"key": key, "text": redact(str(item["text"]))}
        if item.get("severity") is not None:
            severity = str(item["severity"]).strip().lower()
            if severity not in ("blocking", "major", "minor", "advisory"):
                raise MeginError("review finding severity is unsupported")
            finding["severity"] = severity
        for field in ("path", "evidence", "correction"):
            if item.get(field) is not None:
                finding[field] = redact(str(item[field]))
        normalized_findings.append(finding)
    if verdict == "APPROVED" and any(
        finding.get("severity") in ("blocking", "major") for finding in normalized_findings
    ):
        raise MeginError("an APPROVED review cannot contain blocking or major findings")
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
        raise MeginError("knowledge report must use megin-knowledge-review/v1")
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
            except MeginError:
                raise MeginError("knowledge report scope is invalid")
        if report_value != value:
            raise MeginError(f"knowledge report {key} is not bound to the current candidate")
    approved_commands = list(state.get("approval", {}).get("scope", {}).get("test_commands", []))
    if not _report_commands_passed(payload.get("test_evidence"), approved_commands):
        raise MeginError("knowledge report must include passing evidence for an approved test command")
    claim_evidence = payload.get("claim_evidence", [])
    if not isinstance(claim_evidence, list) or len(claim_evidence) < len(candidate_payload.get("claims", [])):
        raise MeginError("knowledge report must include evidence for every candidate claim")
    if claim_evidence and not _report_commands_passed(claim_evidence):
        raise MeginError("knowledge claim evidence must be passing")
    claim_paths = {str(claim.get("path")) for claim in candidate_payload.get("claims", []) if claim.get("path")}
    reported_claim_paths = {str(item.get("path")) for item in claim_evidence if isinstance(item, dict) and item.get("path")}
    if claim_paths and not claim_paths.issubset(reported_claim_paths):
        raise MeginError("knowledge report claim evidence does not cover every candidate path")
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
        raise MeginError("verification requires at least one approved test command")
    outcomes: list[dict[str, Any]] = []
    try:
        for index, command in enumerate(commands, 1):
            outcomes.append(capture_test(repo, state, command, index))
    except MeginError as exc:
        state["verification"] = {"status": "failed", "commands": outcomes, "snapshot": None, "error": redact(str(exc))}
        refresh_verification_digest(state)
        raise
    if any(item.get("outcome") != "passed" for item in outcomes):
        state["verification"] = {
            "status": "failed", "commands": outcomes, "snapshot": working_tree_snapshot(repo),
            "error": "one or more approved verification commands failed, were skipped, or changed the working tree",
        }
        refresh_verification_digest(state)
        raise MeginError("one or more approved verification commands failed, were skipped, or changed the working tree")
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
        raise MeginError("working tree changed after review; obtain a fresh review before verification")
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
            raise MeginError("writer completion requires an active implementation assignment")
        if state["assignments"][-1].get("status") in ("needs_revision", "blocked"):
            append_assignment(state, args, repo)
        assignment = state["assignments"][-1]
        task = assignment_task(state, assignment)
        if not task:
            raise MeginError("writer assignment references an unknown work package")
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
            raise MeginError("writer changed paths outside the task-specific dispatch package: " + ", ".join(violations))
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
            raise MeginError("review approval requires the current writer to report completion first")
        reviewer = getattr(args, "reviewer_id", None)
        if not reviewer:
            raise MeginError("an independent review must include --reviewer-id")
        if assignment.get("status") != "completed":
            raise MeginError("review must reference the completed active assignment")
        writer_id = assignment.get("writer_id") or assignment.get("writer")
        reviewer_session = getattr(args, "reviewer_session", None) or f"reviewer:{reviewer}"
        if reviewer == writer_id or reviewer_session == (assignment.get("session_id") or assignment.get("session")):
            raise MeginError("reviewer identity/session must be independent from the implementation writer")
        previous_review = state.get("review", {})
        if previous_review.get("reviewer_session") and reviewer_session == previous_review.get("reviewer_session"):
            raise MeginError("each review round requires a fresh reviewer session")
        reviewer_capability_path, reviewer_capability_sha = register_capability(
            state, repo, kind="reviewer", identity=reviewer, session_id=reviewer_session,
            assignment_id=assignment.get("assignment_id"), read_only=True,
        )
        paths, snapshot = status_paths(worktree)
        completion_snapshot = assignment.get("completion_snapshot")
        if completion_snapshot and snapshot != completion_snapshot:
            raise MeginError(
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
                    raise MeginError("review approved a task but no dependent work package is ready")
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
                raise MeginError("knowledge review requires an approved fresh code review")
            if state.get("verification", {}).get("status") not in ("passed", "verified"):
                raise MeginError("knowledge review requires fresh verification")
            reviewer = getattr(args, "reviewer_id", None)
            if not reviewer:
                raise MeginError("a knowledge review must include --reviewer-id")
            assignment = state.get("assignments", [])[-1]
            writer_id = assignment.get("writer_id") or assignment.get("writer")
            if reviewer == writer_id:
                raise MeginError("knowledge reviewer identity must be independent from the implementation writer")
            candidate = create_knowledge_candidate(state, worktree)
            payload, lint_errors = lint_knowledge_candidate(state, worktree)
            snapshot_before = knowledge_snapshot(worktree, state["knowledge"]["scope"])
            state["knowledge"]["snapshot_before"] = snapshot_before
            state["knowledge"]["snapshot_after"] = snapshot_before
            state["knowledge"]["lint"] = {"status": "passed" if not lint_errors else "failed", "errors": lint_errors}
            state["knowledge"]["conflicts"] = []
            if lint_errors:
                state["knowledge"]["status"] = "blocked"
                raise MeginError("knowledge candidate lint failed: " + "; ".join(lint_errors))
            reviewer_session = getattr(args, "reviewer_session", None) or f"reviewer:{reviewer}"
            if reviewer_session == (assignment.get("session_id") or assignment.get("session")):
                raise MeginError("knowledge reviewer session must be independent from the implementation writer")
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
                raise MeginError("knowledge promotion requires a reviewed candidate")
            if state.get("verification", {}).get("status") not in ("passed", "verified"):
                raise MeginError("knowledge promotion requires fresh verification")
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
        raise MeginError("only a small task can be escalated to the large-change path")
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


def _process_liveness(pid: int) -> str:
    """Return alive, dead, or unknown without assuming ownership of a process."""

    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return "alive" if re.search(rf"(?<!\d){pid}(?!\d)", result.stdout or "") else "dead"
        except (OSError, subprocess.SubprocessError):
            return "unknown"
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        return "unknown"
    except OSError as exc:
        return "dead" if exc.errno == errno.ESRCH else "unknown"
    return "alive"


def inspect_state_lock(lock: Path) -> dict[str, Any]:
    """Describe a lock without mutating it; used by acquisition and doctor."""

    result: dict[str, Any] = {"path": str(lock), "state": "missing", "pid": None, "created_at": None}
    if not lock.exists():
        return result
    result["state"] = "unknown"
    try:
        raw = lock.read_bytes()
    except OSError as exc:
        result["detail"] = f"cannot read lock: {exc}"
        return result
    result["raw"] = raw
    payload: dict[str, Any] | None = None
    try:
        decoded = json.loads(raw.decode("utf-8"))
        if isinstance(decoded, dict):
            payload = decoded
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if payload is not None:
        pid = payload.get("pid")
        result["created_at"] = payload.get("created_at")
    else:
        legacy = raw.decode("ascii", errors="ignore").strip()
        pid = int(legacy) if legacy.isdigit() else None
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        result["detail"] = "lock owner is missing or malformed"
        return result
    result["pid"] = pid
    liveness = _process_liveness(pid)
    result["state"] = "active" if liveness == "alive" else "stale" if liveness == "dead" else "unknown"
    if liveness == "unknown":
        result["detail"] = "lock owner could not be verified"
    return result


def acquire_state_lock(path: Path) -> Path:
    """Acquire a short-lived cross-process lock, recovering only dead owners."""

    lock = Path(str(path) + ".lock")
    for _ in range(2):
        descriptor = -1
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = json_bytes({"pid": os.getpid(), "created_at": now()})
            os.write(descriptor, payload)
            os.close(descriptor)
            return lock
        except FileExistsError as exc:
            info = inspect_state_lock(lock)
            if info.get("state") == "stale":
                try:
                    if lock.read_bytes() == info.get("raw"):
                        lock.unlink()
                        continue
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
            raise MeginError(
                f"state mutation is already in progress: {path.stem} ({info.get('state', 'unknown')} lock)"
            ) from exc
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
    raise MeginError(f"state mutation is already in progress: {path.stem} (lock race)")


def release_state_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _cmd_resume_locked(args: argparse.Namespace, repo: Path) -> int:
    load_config(repo, required=True)
    state, path = load_state(repo, args.work_id)
    if getattr(args, "request", "") and redact(args.request) != state.get("task", {}).get("request"):
        raise MeginError("request differs from the approved Work ID candidate; start a new Work ID")
    apply_escalation(state, args)
    apply_approval_inputs(state, args)
    materialize_candidate_bundles(state, repo, args)
    refresh_approval_digests(state)
    if state.get("assignments") and not assignment_authorizations_current(state):
        rebind_assignment_authorizations(state, repo)
    workspace_mode = (
        state.get("workspace", {}).get("mode")
        or state.get("approval", {}).get("scope", {}).get("publication", {}).get("workspace_mode")
    )
    binding_lock: Path | None = None
    try:
        if workspace_mode == "current":
            workspace_binding_path(repo).parent.mkdir(parents=True, exist_ok=True)
            binding_lock = acquire_state_lock(workspace_binding_path(repo))
        activate_if_approved(state, repo, args)
    finally:
        if binding_lock is not None:
            release_state_lock(binding_lock)
    progress_repo = Path(state["workspace"]["worktree"]) if state.get("workspace", {}).get("worktree") else repo
    if (
        state.get("workspace", {}).get("mode") == "current"
        and state.get("workspace", {}).get("base_sha")
        and not state.get("publication", {}).get("commit_sha")
        and head_sha(progress_repo) != state["workspace"].get("base_sha")
    ):
        raise MeginError("current workspace HEAD changed after approval; stop and inspect the snapshot before writing")
    try:
        apply_progress_flags(state, progress_repo, args)
    except MeginError:
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
        raise MeginError("writer identity does not match the active assignment")
    ticket = getattr(args, "writer_ticket", None)
    if not ticket:
        raise MeginError("writer completion requires the current assignment --writer-ticket")
    if ticket != assignment.get("ticket_sha256"):
        raise MeginError("writer assignment ticket is invalid or already belongs to another assignment")
    if assignment.get("ticket_consumed"):
        raise MeginError("writer assignment ticket has already been consumed")
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
        raise MeginError("review ticket is invalid or does not match the current assignment snapshot")
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
            except MeginError:
                invalid.append({"path": str(path), "reason": "invalid v2 state; inspect with doctor --work-id"})
    emit({"repo": str(repo), "repo_id": repo_identity(repo), "state_root": str(directory.parent), "runs": records, "invalid_runs": invalid}, args)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    requested = Path(args.repo).expanduser().resolve()
    checks: list[dict[str, Any]] = []
    try:
        repo = require_git_repo(requested)
        checks.append({"name": "git_repository", "ok": True, "path": str(repo)})
    except MeginError as exc:
        checks.append({"name": "git_repository", "ok": False, "detail": str(exc)})
        emit({"ok": False, "checks": checks}, args)
        return 1
    config_error = None
    try:
        config = load_config(repo, required=False)
    except MeginError as exc:
        config = None
        config_error = str(exc)
    config_check = {"name": "project_config", "ok": config is not None, "path": str(repo / ".megin" / "config.json")}
    if config_error:
        config_check["detail"] = config_error
    checks.append(config_check)
    try:
        root = state_root(repo_identity(repo), repo)
        checks.append({"name": "state_root_outside_repo", "ok": True, "path": str(root)})
    except MeginError as exc:
        checks.append({"name": "state_root_outside_repo", "ok": False, "detail": str(exc)})
    checks.append({"name": "python", "ok": True, "version": sys.version.split()[0]})
    checks.append({"name": "rg", "ok": shutil.which("rg") is not None})
    checks.append({"name": "git", "ok": shutil.which("git") is not None})
    checks.append({"name": "gh", "ok": shutil.which("gh") is not None, "optional": True})
    checks.append({"name": "portable_contract", "ok": DELIVERY_SCHEMA_PATH.exists(), "path": str(DELIVERY_SCHEMA_PATH)})
    binding_lock = Path(str(workspace_binding_path(repo)) + ".lock")
    binding_info = inspect_state_lock(binding_lock)
    checks.append({
        "name": "workspace_binding_lock",
        "ok": binding_info.get("state") == "missing",
        "state": binding_info.get("state"),
        "path": str(binding_lock),
        "pid": binding_info.get("pid"),
        "created_at": binding_info.get("created_at"),
        "detail": binding_info.get("detail"),
    })
    runs = []
    invalid_runs = []
    try:
        directory = state_directory(repo)
    except MeginError:
        directory = None
    if directory and directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                state, validated_path = load_state(repo, path.stem)
                runs.append(state_summary(state, validated_path))
            except MeginError:
                invalid_runs.append({"path": str(path), "reason": "invalid v2 state"})
    if args.work_id:
        try:
            state, path = load_state(repo, args.work_id)
            runs = [state_summary(state, path)]
            checks.append({"name": "writer_assignment", "ok": (not state.get("assignments")) or bool(state["assignments"][-1].get("ticket_sha256")), "detail": "one ticketed writer assignment is present"})
            lock_info = inspect_state_lock(Path(str(path) + ".lock"))
            checks.append({
                "name": "state_mutation_lock",
                "ok": lock_info.get("state") == "missing",
                "state": lock_info.get("state"),
                "path": lock_info.get("path"),
                "pid": lock_info.get("pid"),
                "created_at": lock_info.get("created_at"),
                "detail": lock_info.get("detail") or "no state mutation lock is present",
            })
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
        except MeginError as exc:
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
        raise MeginError("working tree contains paths outside approved scope: " + ", ".join(violations))
    return paths


def suggested_commit_message(state: dict[str, Any], repo: Path, paths: Sequence[str]) -> str:
    """Derive a reviewable commit suggestion from the approved request and diff."""

    title = str(
        state.get("approval", {}).get("scope", {}).get("publication", {}).get("title")
        or state.get("task", {}).get("request")
        or "update project"
    ).strip().replace("\n", " ")
    title = re.sub(r"\s+", " ", title)[:100]
    task_class = state.get("task", {}).get("task_class")
    prefix = "fix" if task_class == "bug" else "feat"
    body = [
        f"{prefix}(megin): {title}",
        "",
        f"Work ID: {state.get('work_id')}",
        f"Changed paths: {', '.join(paths) if paths else 'none'}",
        "",
        "Validated by Megin review and the approved verification commands.",
    ]
    return "\n".join(body)


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
    prefix = f"megin({state['work_id']}):"
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
    if not getattr(args, "publish", False):
        return
    publication = state["publication"]
    if publication.get("commit_sha") and head_sha(repo) != publication.get("commit_sha"):
        raise MeginError("saved commit SHA no longer matches the delivery branch; publication is blocked")
    if publication.get("state") == "draft_pr_created":
        state["next_action"] = "merge/deploy/cleanup require separate authorization"
        return
    requested_remote = validate_remote_name(getattr(args, "remote", None))
    approved_remote = publication.get("remote")
    if requested_remote and requested_remote != approved_remote:
        raise MeginError("finish remote differs from the approved publication destination; re-approve the scope")
    remote = approved_remote
    branch = state["workspace"].get("branch")
    if remote:
        current_url_digest = remote_url_digest(repo, remote)
        if not current_url_digest or current_url_digest != publication.get("remote_url_sha256"):
            publication["state"] = "publication_pending"
            publication["reason"] = "approved Git remote URL is missing or has changed"
            state["next_action"] = "restore the approved remote destination, then rerun finish --publish"
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
    title = publication.get("title") or f"Megin delivery {state['work_id']}"
    body = (
        f"Megin delivery {state['work_id']}\n\n"
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
        raise MeginError("finish remote differs from the approved publication destination; re-approve the scope")
    workspace = state.get("workspace", {})
    if not workspace.get("worktree"):
        raise MeginError("finish requires an approved run with a delivery workspace")
    worktree = Path(workspace["worktree"]).resolve()
    if not worktree.exists():
        raise MeginError(f"delivery workspace is missing: {worktree}")
    stored_finish_mode = state.get("publication", {}).get("finish_mode")
    # States created before v0.3 retain their historical commit semantics.  A
    # new flag must not silently reinterpret an old worktree as an unstaged
    # delivery; start a new v0.3 run when the destination needs to change.
    if stored_finish_mode is None:
        requested_finish_mode = getattr(args, "finish_mode", None)
        if requested_finish_mode and requested_finish_mode != "commit":
            raise MeginError("legacy v2 state is bound to commit delivery; start a new run to select another finish mode")
        finish_mode = "commit"
    else:
        finish_mode = stored_finish_mode
    if getattr(args, "finish_mode", None) and stored_finish_mode and args.finish_mode != stored_finish_mode:
        raise MeginError("finish mode differs from the approved delivery destination; start a new approved run")
    if finish_mode not in FINISH_MODES:
        raise MeginError(f"unsupported finish mode: {finish_mode}")
    workspace_mode = workspace.get("mode") or ("current" if worktree == repo.resolve() else "worktree")
    if workspace_mode == "current":
        if current_branch(worktree) != workspace.get("branch"):
            raise MeginError("current workspace branch changed after approval; return to the approved feature branch before finishing")
        if workspace.get("base_sha") and head_sha(worktree) != workspace.get("base_sha") and not state.get("publication", {}).get("commit_sha"):
            if finish_mode in ("commit", "draft-pr") and recover_commit(state, worktree):
                publication = state["publication"]
            else:
                raise MeginError("current workspace HEAD changed after approval; create a new Work ID or restore the approved snapshot")
    if finish_mode == "unstaged" and getattr(args, "publish", False):
        raise MeginError("unstaged finish mode cannot publish; choose commit or draft-pr and approve that delivery mode")
    if finish_mode == "draft-pr":
        args.publish = True
    # These flags represent evidence returned by independent sessions.  They never grant
    # write access; they only record the externally obtained verdict before preflight.
    if args.review_approved or args.review_verdict or args.verified or args.knowledge_reviewed or args.knowledge_promoted:
        try:
            apply_progress_flags(state, worktree, args)
        except MeginError:
            if state.get("verification", {}).get("status") == "failed":
                state["status"] = "blocked"
                state["phase"] = "verification"
                save_state(state, path)
            raise
    if state.get("review", {}).get("verdict") != "APPROVED":
        raise MeginError("finish is blocked until a fresh independent reviewer records APPROVED")
    if not all_tasks_completed(state):
        raise MeginError("finish is blocked until every dependent work package has been reviewed")
    allowed = state["approval"]["scope"].get("allowed_paths", [])
    if not allowed:
        raise MeginError("finish is blocked because approval has no allowed paths")
    knowledge_conflict_pending = bool(
        state["knowledge"].get("scope")
        and state["knowledge"].get("status") == "blocked"
        and state["knowledge"].get("conflicts")
    )
    if state["knowledge"].get("scope") and state["knowledge"].get("status") not in ("reviewed", "promoted") and not knowledge_conflict_pending:
        raise MeginError("finish is blocked until the approved knowledge scope has a fresh review")
    if args.rerun_tests or state["verification"].get("status") not in ("passed", "verified"):
        try:
            record_verification(state, worktree)
        except MeginError as exc:
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
        except MeginError:
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
            raise MeginError("verification evidence is stale for the current worktree; rerun the approved tests")
    if review.get("snapshot") and review["snapshot"] != current_snapshot:
        product_scope = state.get("knowledge", {}).get("scope", [])
        product_snapshot = working_tree_snapshot(worktree, exclude=product_scope) if product_scope else None
        if not product_scope or not review.get("product_snapshot") or product_snapshot != review.get("product_snapshot"):
            raise MeginError("working tree changed after review; obtain a fresh review before finishing")
        if state.get("knowledge", {}).get("status") not in ("reviewed", "promoted") and not knowledge_conflict_pending:
            raise MeginError("working tree changed after review outside an approved knowledge handoff")
        knowledge_conflict_pending = True
    publication = state["publication"]
    if finish_mode == "unstaged" and publication.get("state") == "delivered_unstaged":
        staged = git(worktree, "diff", "--cached", "--name-only", check=False).strip()
        if staged:
            raise MeginError("unstaged delivery changed because the index now contains staged paths")
        approved_base = state.get("workspace", {}).get("base_sha") or publication.get("base_sha")
        if approved_base and head_sha(worktree) != approved_base:
            raise MeginError("unstaged delivery found a HEAD change after delivery; Megin will not rewrite or reset it")
        current_snapshot = working_tree_snapshot(worktree)
        if publication.get("delivered_snapshot") != current_snapshot:
            raise MeginError("working tree changed after unstaged delivery; obtain a fresh review and verification")
        emit(state_summary(state, path), args)
        return 0
    if finish_mode == "unstaged":
        staged = git(worktree, "diff", "--cached", "--name-only", check=False).strip()
        if staged:
            state["status"] = "blocked"
            state["phase"] = "delivery"
            state["next_action"] = "unstage the approved changes or choose an explicitly approved commit finish mode"
            save_state(state, path)
            raise MeginError("unstaged finish mode found staged changes; Megin will not alter the index")
        if publication.get("commit_sha"):
            raise MeginError("unstaged finish mode cannot continue after a commit was created")
        approved_base = state.get("workspace", {}).get("base_sha") or publication.get("base_sha")
        if approved_base and head_sha(worktree) != approved_base:
            state["status"] = "blocked"
            state["phase"] = "delivery"
            state["next_action"] = "inspect the external commit and start a new approved delivery or restore the approved base"
            save_state(state, path)
            raise MeginError("unstaged delivery found a HEAD change after approval; Megin will not rewrite or reset it")
        changed_paths = verify_scope(worktree, state["approval"]["scope"].get("allowed_paths", []))
        if not changed_paths:
            raise MeginError("finish found no approved changes to deliver")
        current_snapshot = working_tree_snapshot(worktree)
        publication["state"] = "delivered_unstaged"
        publication["changed_paths"] = changed_paths
        publication["delivered_snapshot"] = current_snapshot
        publication["suggested_commit"] = suggested_commit_message(state, worktree, changed_paths)
        publication["reason"] = None
        state["phase"] = "delivery"
        state["status"] = "complete"
        state["next_action"] = "review the unstaged diff and use the suggested commit message when you are ready"
        append_event(state, "delivered_unstaged", phase="delivery", status="complete", paths=changed_paths)
        save_state(state, path)
        emit(state_summary(state, path), args)
        return 0
    if publication.get("commit_sha"):
        expected = publication.get("post_commit_snapshot")
        if expected and expected != current_snapshot:
            knowledge_conflict = post_commit_product_recovery_allowed(state, worktree)
            if not knowledge_conflict:
                raise MeginError("working tree changed after the committed review; create a new delivery run")
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
            raise MeginError("finish found no product paths to commit while knowledge has a pending conflict")
        result = run_process(("git", "add", "-A", "--", *commit_allowed), worktree, timeout=60, check=False)
        if result.returncode != 0:
            raise MeginError(f"git add failed ({result.returncode})")
        staged = git(worktree, "diff", "--cached", "--name-only", "-z").split("\0")
        staged = [normalize_rel(item) for item in staged if item]
        if not staged:
            raise MeginError("finish found no approved changes to commit")
        if any(not allowed_path(item, allowed) for item in staged):
            raise MeginError("git staging selected a path outside approved scope")
        title = publication.get("title") or state["task"]["request"]
        message = f"megin({state['work_id']}): {title[:160]}".replace("\n", " ")
        commit = run_process(("git", "commit", "-m", message), worktree, timeout=120, check=False)
        if commit.returncode != 0:
            raise MeginError(f"git commit failed ({commit.returncode}): {redact((commit.stdout or '') + (commit.stderr or '')).strip()}")
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
    if getattr(args, "publish", False):
        finish_publication(state, worktree, args)
    else:
        publication["state"] = "committed"
        publication["reason"] = None
        state["next_action"] = "local commit created; use an explicitly authorized --publish retry if publication is required"
    state["phase"] = "delivery"
    state["status"] = "active" if knowledge_conflict_pending or state.get("publication", {}).get("state") == "publication_pending" else "complete"
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
    parser.add_argument("--human", action="store_true", help="print a concise operator-facing summary")


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
    parser.add_argument("--workspace-mode", choices=WORKSPACE_MODES, help="use the current checkout or an isolated worktree")
    parser.add_argument("--finish-mode", choices=FINISH_MODES, help="leave changes unstaged, create a local commit, or publish a draft PR")
    parser.add_argument("--branch-prefix", help="feature branch prefix for current-directory mode")
    parser.add_argument("--routing-file", help="validated megin-routing/v1 evidence from read-only exploration")
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
    parser = argparse.ArgumentParser(prog="megin", description="Portable evidence-driven Megin delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    classify_parser = sub.add_parser("classify", help="classify a request without mutation")
    classify_parser.add_argument("--request", required=True)
    classify_parser.add_argument("--repo", help="optional target Git repository for read-only exploration")
    classify_parser.add_argument("--task-class", choices=TASK_CLASSES)
    classify_parser.add_argument("--routing-file")
    add_output(classify_parser)

    diagnose_parser = sub.add_parser("diagnose", help="run a read-only bug oracle and save an assessment")
    add_repo(diagnose_parser)
    diagnose_parser.add_argument("--request", required=True)
    diagnose_parser.add_argument("--command", dest="diagnosis_command", required=True, help="read-only symptom or regression command")
    diagnose_parser.add_argument("--disposition", required=True, choices=("confirmed", "likely", "partial", "not-a-bug", "blocked"))
    diagnose_parser.add_argument("--hypothesis", required=True, help="falsifiable root-cause hypothesis")
    diagnose_parser.add_argument("--environment", action="append", help="safe environment/context labels")
    add_output(diagnose_parser)

    migrate_parser = sub.add_parser("migrate", help="migrate a legacy sdlc project to Megin")
    add_repo(migrate_parser)
    migrate_parser.add_argument("--from-state-root", help="legacy sdlc state root")
    migrate_parser.add_argument("--to-state-root", help="new Megin state root")
    migrate_parser.add_argument("--dry-run", action="store_true", help="validate and report without publishing changes")
    add_output(migrate_parser)

    init_parser = sub.add_parser("init", help="opt a target repository into the portable workflow")
    add_repo(init_parser)
    init_parser.add_argument("--base-branch")
    init_parser.add_argument("--workspace-mode", choices=WORKSPACE_MODES)
    init_parser.add_argument("--finish-mode", choices=FINISH_MODES)
    init_parser.add_argument("--branch-prefix")
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
    start_parser.add_argument("--diagnosis-file", help="validated read-only bug assessment produced by megin diagnose")
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

    finish_parser = sub.add_parser("finish", help="verify and deliver an approved run")
    add_repo(finish_parser)
    finish_parser.add_argument("--work-id")
    finish_parser.add_argument("--publish", action="store_true", help="explicitly push and create or reuse a draft PR")
    finish_parser.add_argument("--remote")
    finish_parser.add_argument("--finish-mode", choices=FINISH_MODES)
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
            "migrate": cmd_migrate,
            "init": cmd_init,
            "start": cmd_start,
            "resume": cmd_resume,
            "status": cmd_status,
            "doctor": cmd_doctor,
            "finish": cmd_finish,
        }[args.command](args)
    except MeginError as exc:
        print(f"megin: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("megin: interrupted; state was not reset", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
