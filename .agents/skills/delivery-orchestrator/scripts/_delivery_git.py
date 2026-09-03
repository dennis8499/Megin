#!/usr/bin/env python3
"""Private hardened Git probes for delivery-orchestrator.

Authority: delivery-git
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from _delivery_runtime import (
    DeliveryError,
    _is_relative_to,
    _normalized_repo_path,
    canonical_path,
    canonical_path_text,
    path_key,
    sha256_bytes,
    workspace_label,
)


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
_TRUST_FAILURE_MARKERS = (b"detected dubious ownership", b"safe.directory")


@dataclass(frozen=True)
class RepositoryIdentity:
    """Immutable repository identity captured by one scoped Git probe."""

    requested_path: str
    canonical_worktree: str
    worktree_key: str
    common_dir: str
    repo_id: str
    head_sha: str


@dataclass(frozen=True)
class RepositoryStateEvidence:
    """Immutable provenance for a full repository state observation."""

    identity: RepositoryIdentity
    lock_epoch: str | None
    primary_worktree: str
    branch_ref: str | None
    status: bytes
    worktrees: tuple[tuple[tuple[str, str | bool], ...], ...]
    filter_drivers: tuple[tuple[str, tuple[str, ...]], ...]
    submodules: tuple[tuple[str, tuple[str, ...]], ...]
    hooks_executed: bool = False
    trust_validated: bool = True
    merge_base: tuple[str, bool] | None = None

    def as_probe(self) -> dict[str, Any]:
        """Return the existing mutable public probe shape without exposing tokens."""
        top = self.identity.canonical_worktree
        branch_ref = self.branch_ref
        return {
            "repo_id": self.identity.repo_id,
            "requested_path": self.identity.requested_path,
            "canonical_worktree": top,
            "worktree_key": self.identity.worktree_key,
            "primary_worktree": self.primary_worktree,
            "is_primary": canonical_path_text(top)
            == canonical_path_text(self.primary_worktree),
            "branch_ref": branch_ref,
            "branch": branch_ref.removeprefix("refs/heads/") if branch_ref else None,
            "attached": branch_ref is not None,
            "head_sha": self.identity.head_sha,
            "strict_clean": self.status == b"",
            "status_sha256": sha256_bytes(self.status),
            "worktrees": [dict(items) for items in self.worktrees],
        }

    def matches(
        self,
        probe: dict[str, Any],
        *,
        canonical_worktree: str | Path,
        lock_epoch: str | None,
    ) -> bool:
        """Accept reuse only for the exact path, identity, HEAD, and lock epoch."""
        expected_path = canonical_path_text(canonical_worktree)
        return (
            self.lock_epoch == lock_epoch
            and canonical_path_text(self.identity.canonical_worktree) == expected_path
            and canonical_path_text(str(probe.get("canonical_worktree", "")))
            == expected_path
            and probe.get("worktree_key") == self.identity.worktree_key
            and probe.get("repo_id") == self.identity.repo_id
            and probe.get("head_sha") == self.identity.head_sha
        )


@dataclass
class _StrictStatusCollector:
    filter_drivers: list[tuple[str, tuple[str, ...]]]
    submodules: list[tuple[str, tuple[str, ...]]]


def _git_failure_error(
    completed: subprocess.CompletedProcess[bytes],
    *,
    fallback_code: str,
    fallback_message: str,
) -> DeliveryError:
    """Classify fixed-locale Git failures without reflecting raw output."""
    stderr = completed.stderr.lower()
    if all(marker in stderr for marker in _TRUST_FAILURE_MARKERS):
        return DeliveryError(
            "Git repository trust is required; authorize an unsandboxed retry "
            "without changing safe.directory.",
            code="GIT_TRUST_REQUIRED",
        )
    return DeliveryError(fallback_message, code=fallback_code)


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
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    environment["LANGUAGE"] = "C"
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
        raise _git_failure_error(
            completed,
            fallback_code="GIT_COMMAND_FAILED",
            fallback_message=(
                f"git command failed ({completed.returncode}) "
                "while running a scoped repository operation"
            ),
        )
    return completed


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _active_filter_drivers(
    repo: str | Path,
    *,
    tracked: bytes | None = None,
) -> list[str]:
    if tracked is None:
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


def _index_inventory(repo: str | Path) -> tuple[bytes, list[str]]:
    """Return tracked paths and gitlinks from one stage-aware index scan."""
    output = _git(repo, ["-c", "core.fsmonitor=false", "ls-files", "--stage", "-z"]).stdout
    tracked_paths: list[bytes] = []
    seen_paths: set[bytes] = set()
    result: set[str] = set()
    for entry in output.split(b"\0"):
        if not entry:
            continue
        metadata, separator, raw_path = entry.partition(b"\t")
        if not separator:
            raise DeliveryError("git ls-files returned an invalid index inventory", code="STATUS_PROBE_FAILED")
        if raw_path not in seen_paths:
            tracked_paths.append(raw_path)
            seen_paths.add(raw_path)
        if not metadata.startswith(b"160000 "):
            continue
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DeliveryError("submodule path is not valid UTF-8", code="UNSAFE_SUBMODULE") from exc
        result.add(_normalized_repo_path(relative))
    tracked = b"\0".join(tracked_paths)
    if tracked:
        tracked += b"\0"
    return tracked, sorted(result, key=lambda value: value.encode("utf-8"))


def _indexed_gitlinks(repo: str | Path) -> list[str]:
    return _index_inventory(repo)[1]


def _strict_status(
    repo: str | Path,
    *,
    visited: set[str] | None = None,
    depth: int = 0,
    collector: _StrictStatusCollector | None = None,
) -> bytes:
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
        tracked, gitlinks = _index_inventory(top)
        filter_drivers = _active_filter_drivers(top, tracked=tracked)
        if collector is not None:
            collector.filter_drivers.append((key, tuple(filter_drivers)))
            collector.submodules.append((key, tuple(gitlinks)))
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
        for relative in gitlinks:
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
                child_error = _git_failure_error(
                    child_top_result,
                    fallback_code="UNSAFE_SUBMODULE",
                    fallback_message="initialized submodule is not a valid repository",
                )
                if child_error.code == "GIT_TRUST_REQUIRED":
                    raise child_error
                return b"submodule-invalid\0" + relative.encode("utf-8")
            child_top = canonical_path(_decode(child_top_result.stdout).strip())
            if canonical_path_text(child_top) != canonical_path_text(lexical):
                return b"submodule-redirected\0" + relative.encode("utf-8")
            child_status = _strict_status(
                child_top,
                visited=seen,
                depth=depth + 1,
                collector=collector,
            )
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


def probe_repository_identity(repo: str | Path) -> RepositoryIdentity:
    """Capture repository location and HEAD, batching the normal Git path."""
    requested = canonical_path(repo)
    identity = _git(
        requested,
        [
            "rev-parse",
            "--is-bare-repository",
            "--show-toplevel",
            "--path-format=absolute",
            "--git-common-dir",
            "HEAD",
        ],
        check=False,
    )
    fields = _decode(identity.stdout).splitlines()
    if identity.returncode == 0 and len(fields) == 4 and fields[0] in {"false", "true"}:
        bare_value, top_value, common_value, head_sha = fields
    else:
        # The fallback preserves precise not-a-repository/bare errors and paths
        # containing line separators. The common, budgeted case remains one call.
        bare = _git(requested, ["rev-parse", "--is-bare-repository"], check=False)
        if bare.returncode != 0:
            raise _git_failure_error(
                bare,
                fallback_code="NOT_A_REPOSITORY",
                fallback_message=f"not a Git repository: {requested}",
            )
        bare_value = _decode(bare.stdout).strip()
        if bare_value == "true":
            raise DeliveryError(
                f"bare repositories are not supported: {requested}",
                code="BARE_REPOSITORY",
            )
        top_value = _decode(
            _git(requested, ["rev-parse", "--show-toplevel"]).stdout
        ).strip()
        top = canonical_path(top_value)
        common_value = _decode(
            _git(
                top,
                ["rev-parse", "--path-format=absolute", "--git-common-dir"],
            ).stdout
        ).strip()
        head_sha = _decode(_git(top, ["rev-parse", "HEAD"]).stdout).strip()
    if bare_value == "true":
        raise DeliveryError(
            f"bare repositories are not supported: {requested}",
            code="BARE_REPOSITORY",
        )
    if bare_value != "false":
        raise DeliveryError(
            "git rev-parse returned an invalid repository identity",
            code="WORKTREE_PROBE_FAILED",
        )

    top = canonical_path(top_value)
    common_dir = canonical_path(common_value)
    return RepositoryIdentity(
        requested_path=str(requested),
        canonical_worktree=str(top),
        worktree_key=path_key(top),
        common_dir=str(common_dir),
        repo_id=sha256_bytes(canonical_path_text(common_dir).encode("utf-8")),
        head_sha=head_sha,
    )


def probe_repository_state(
    repo: str | Path,
    *,
    lock_epoch: str | None = None,
) -> RepositoryStateEvidence:
    identity = probe_repository_identity(repo)
    top = Path(identity.canonical_worktree)

    worktrees = _parse_worktrees(_git(top, ["worktree", "list", "--porcelain"]).stdout)
    if not worktrees or "worktree" not in worktrees[0]:
        raise DeliveryError("git worktree list did not identify a primary worktree", code="WORKTREE_PROBE_FAILED")
    primary = canonical_path(str(worktrees[0]["worktree"]))

    symbolic = _git(top, ["symbolic-ref", "--quiet", "HEAD"], check=False)
    branch_ref = _decode(symbolic.stdout).strip() if symbolic.returncode == 0 else None
    collector = _StrictStatusCollector(filter_drivers=[], submodules=[])
    status = _strict_status(top, collector=collector)
    return RepositoryStateEvidence(
        identity=identity,
        lock_epoch=lock_epoch,
        primary_worktree=str(primary),
        branch_ref=branch_ref,
        status=status,
        worktrees=tuple(tuple(item.items()) for item in worktrees),
        filter_drivers=tuple(collector.filter_drivers),
        submodules=tuple(collector.submodules),
    )


def probe_repository(repo: str | Path) -> dict[str, Any]:
    return probe_repository_state(repo).as_probe()


def _branch_exists(repo: str | Path, branch: str) -> bool:
    result = _git(repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False)
    if result.returncode not in (0, 1):
        raise _git_failure_error(
            result,
            fallback_code="BRANCH_PROBE_FAILED",
            fallback_message="unable to determine whether the delivery branch exists",
        )
    return result.returncode == 0


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
