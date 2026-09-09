"""Deterministic, read-only retrieval for repository-local knowledge."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


INELIGIBLE_SEGMENTS = {
    ".git",
    ".knowledge-test-tmp",
    ".tgrep",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "vendor",
    "dist",
    "build",
}
INELIGIBLE_LIFECYCLES = {"stale", "contested", "superseded"}
MAX_FIXED_PATTERN_BYTES = 8 * 1024 * 1024
INDEX_SEARCH_MIN_TRACKED_PATHS = 10_000
INDEX_SEARCH_MAX_DIRTY_PATHS = 256
INDEX_SEARCH_MAX_DIRTY_BYTES = 24 * 1024
MAX_QUERY_TERMS = 48
TGREP_STATE_SCHEMA = "tgrep-index-state/v1"
TGREP_RESULT_SCHEMA = "tgrep-index/v1"
TGREP_STATE_RELATIVE = ".tgrep/state.json"
TGREP_INDEX_RELATIVE = ".tgrep"
TGREP_EXPECTED_VERSION = "1.0.4"
TGREP_MAX_COMMAND_BYTES = 24 * 1024
TGREP_INDEX_FILES = (
    "meta.json",
    "index.bin",
    "lookup.bin",
    "files.bin",
    "files-extra.bin",
    "filestamps.json",
)
TGREP_INDEX_PARAMETERS: dict[str, Any] = {
    "exclude": [".git", ".tgrep"],
    "hidden": True,
    "root": ".",
}
TGREP_STATUS_RE = re.compile(
    r"(?m)^Index status for .+\r?\n"
    r"\s+Files:\s+\d+\r?\n"
    r"\s+Trigrams:\s+\d+\r?$"
)
CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
OWNER_CONTRACT_PATH_RE = re.compile(
    r"^\.agents/skills/[^/]+/references/[^/]+\.md$"
)
AUTHORITY_MARKER_RE = re.compile(
    r"<!--\s*authority:\s*([a-z][a-z0-9._-]*)\s*-->",
    flags=re.IGNORECASE,
)
CJK_DOMAIN_ALIASES_V1: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "速度",
        ("驗證", "完整套件", "命令", "本機", "效能", "validation"),
    ),
    (
        "流程",
        ("交付流程", "執行", "驗證", "workflow"),
    ),
    (
        "審查",
        ("reviewer", "preliminary", "final", "初審", "終審", "驗證"),
    ),
    (
        "實作完成",
        ("implementation", "outcome", "candidate", "snapshot"),
    ),
)
SEMANTIC_ATTRIBUTE_PATTERN = re.compile(
    rb"(^|[ \t])(?:filter(?:=|[ \t]|$)|ident(?:[ \t]|$)|working-tree-encoding(?:=|[ \t]|$))",
    flags=re.IGNORECASE | re.MULTILINE,
)


class KnowledgeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int,
        evidence_refs: Iterable[str] = (),
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.evidence_refs = list(evidence_refs)
        self.recoverable = recoverable


@dataclass(frozen=True)
class Match:
    path: str
    line_number: int
    line_text: str


SearchCacheKey = tuple[str, tuple[str, ...], tuple[str, ...]]
IndexFingerprint = tuple[int, int, int, int, int, int]


class MatchCacheFingerprint(str):
    """String-compatible cache key with the dirty-byte token captured beside it."""

    dirty_fingerprint: str
    dirty_paths: tuple[str, ...]
    attribute_paths: tuple[str, ...]
    tracked_count: int

    def __new__(
        cls,
        value: str,
        dirty_fingerprint: str,
        dirty_paths: tuple[str, ...],
        attribute_paths: tuple[str, ...],
        tracked_count: int,
    ) -> MatchCacheFingerprint:
        instance = str.__new__(cls, value)
        instance.dirty_fingerprint = dirty_fingerprint
        instance.dirty_paths = dirty_paths
        instance.attribute_paths = attribute_paths
        instance.tracked_count = tracked_count
        return instance


@dataclass(frozen=True)
class MatchCacheSnapshot:
    fingerprint: str
    dirty_fingerprint: str
    index_path: Path
    index_fingerprint: IndexFingerprint
    dirty_paths: tuple[str, ...]
    attribute_paths: tuple[str, ...]
    tracked_count: int


@dataclass
class MatchCacheEntry:
    snapshot: MatchCacheSnapshot
    matches: dict[SearchCacheKey, tuple[Match, ...]]


_MATCH_CACHE: dict[str, MatchCacheEntry] = {}


PageSnapshot = tuple[str, dict[str, Any], str]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_path(value: str) -> str:
    path = value.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if (
        not path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise KnowledgeError(
            "UNSAFE_PATH",
            f"repository path is not normalized: {value!r}",
            exit_code=3,
        )
    return path


def _run(
    command: list[str],
    *,
    cwd: Path,
    accepted: set[int] = {0},
    code: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            input=input_bytes,
            check=False,
            shell=False,
        )
    except OSError as exc:
        raise KnowledgeError(code, str(exc), exit_code=4) from exc
    if completed.returncode not in accepted:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise KnowledgeError(code, message or "command failed", exit_code=4)
    return completed


def _require_dependencies() -> None:
    missing = [name for name in ("git", "rg") if shutil.which(name) is None]
    if missing:
        raise KnowledgeError(
            "DEPENDENCY_MISSING",
            f"required executable is unavailable: {', '.join(missing)}",
            exit_code=4,
        )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _tgrep_binary_path(repo: Path) -> Path | None:
    """Resolve only the repository-bundled Windows executable."""

    if os.name != "nt":
        return None
    candidate = repo / "tgrep.exe"
    try:
        metadata = candidate.lstat()
    except OSError:
        return None
    if (
        _metadata_is_redirect(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or _redirected(candidate, repo)
    ):
        return None
    return candidate


def _stable_file_sha256(path: Path, repo: Path | None = None) -> str | None:
    try:
        before = path.lstat()
    except OSError:
        return None
    if (
        _metadata_is_redirect(before)
        or not stat.S_ISREG(before.st_mode)
        or (repo is not None and _redirected(path, repo))
    ):
        return None
    try:
        raw = path.read_bytes()
        after = path.lstat()
    except OSError:
        return None
    if (
        _metadata_is_redirect(after)
        or not stat.S_ISREG(after.st_mode)
        or _regular_file_fingerprint(before) != _regular_file_fingerprint(after)
    ):
        return None
    return sha256_bytes(raw)


def _tgrep_binary_version(binary: Path, repo: Path) -> str | None:
    try:
        completed = _run(
            [str(binary), "--version"],
            cwd=repo,
            code="TGREP_UNAVAILABLE",
        )
    except (KnowledgeError, OSError):
        return None
    try:
        text = completed.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    match = re.search(r"(?:^|\n)tgrep\s+([^\s\r\n]+)", text)
    return match.group(1) if match else None


def _tgrep_state_path(repo: Path) -> Path:
    return repo / Path(*TGREP_STATE_RELATIVE.split("/"))


def _tgrep_index_path(repo: Path) -> Path:
    return repo / Path(*TGREP_INDEX_RELATIVE.split("/"))


def _tgrep_index_fingerprint(index_path: Path) -> str | None:
    """Hash every index byte except the state sidecar itself."""

    try:
        metadata = index_path.lstat()
    except OSError:
        return None
    if (
        _metadata_is_redirect(metadata)
        or not stat.S_ISDIR(metadata.st_mode)
        or _redirected(index_path, index_path.parent)
    ):
        return None
    digest = hashlib.sha256()
    try:
        files = sorted(index_path.rglob("*"), key=lambda value: value.relative_to(index_path).as_posix().encode("utf-8"))
    except OSError:
        return None
    for path in files:
        try:
            relative = path.relative_to(index_path).as_posix()
            current = path.lstat()
        except OSError:
            return None
        if relative == Path(TGREP_STATE_RELATIVE).name:
            continue
        if _metadata_is_redirect(current):
            return None
        if stat.S_ISDIR(current.st_mode):
            continue
        if not stat.S_ISREG(current.st_mode) or _redirected(path, index_path):
            return None
        try:
            raw = path.read_bytes()
            after = path.lstat()
        except OSError:
            return None
        if (
            _metadata_is_redirect(after)
            or not stat.S_ISREG(after.st_mode)
            or _regular_file_fingerprint(current) != _regular_file_fingerprint(after)
        ):
            return None
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(hashlib.sha256(raw).digest())
    return digest.hexdigest()


def _tgrep_index_complete(index_path: Path) -> bool:
    try:
        if any(not (index_path / relative).is_file() for relative in TGREP_INDEX_FILES):
            return False
        meta_path = index_path / "meta.json"
        if _metadata_is_redirect(meta_path.lstat()):
            return False
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(metadata, dict)
        and metadata.get("complete") is True
        and metadata.get("version") == 2
    )


def _tgrep_index_status(binary: Path, repo: Path, index_path: Path) -> bool:
    """Require tgrep itself to report a usable index before publishing state."""

    try:
        completed = _run(
            [
                str(binary),
                "status",
                "--index-path",
                str(index_path),
                ".",
            ],
            cwd=repo,
            code="TGREP_INDEX_STATUS_FAILED",
        )
    except (KnowledgeError, OSError):
        return False
    try:
        output = completed.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return TGREP_STATUS_RE.search(output) is not None


def _tgrep_control_fingerprint(repo: Path) -> str | None:
    """Capture repository-local ignore/attribute inputs that affect the walker."""

    try:
        tracked = _run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
            ],
            cwd=repo,
            code="GIT_UNAVAILABLE",
        ).stdout
        configured = _run(
            ["git", "config", "--path", "--get", "core.excludesfile"],
            cwd=repo,
            accepted={0, 1},
            code="GIT_UNAVAILABLE",
        ).stdout.strip()
    except (KnowledgeError, OSError):
        return None
    candidates = {
        ".gitignore",
        ".gitattributes",
        ".ignore",
        ".rgignore",
        ".git/info/exclude",
        ".git/info/attributes",
    }
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        try:
            relative = normalized_path(raw.decode("utf-8"))
        except (UnicodeDecodeError, KnowledgeError):
            continue
        if Path(relative).name in {".gitignore", ".gitattributes", ".ignore", ".rgignore"}:
            candidates.add(relative)
    digest = hashlib.sha256()
    for relative in sorted(candidates, key=lambda value: value.encode("utf-8")):
        path = repo / Path(*relative.split("/"))
        raw = b"missing"
        if path.is_file() and not _redirected(path, repo):
            try:
                raw = path.read_bytes()
            except OSError:
                return None
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(hashlib.sha256(raw).digest())
    digest.update(b"core.excludesfile")
    digest.update(configured)
    return digest.hexdigest()


def _tgrep_repository_snapshot(repo: Path) -> dict[str, Any] | None:
    """Return a stable Git/worktree identity plus a full dirty overlay token."""

    try:
        head = _run(
            ["git", "rev-parse", "HEAD"], cwd=repo, code="GIT_UNAVAILABLE"
        ).stdout.decode("ascii").strip()
        branch_result = _run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            cwd=repo,
            accepted={0, 1},
            code="GIT_UNAVAILABLE",
        )
        branch = (
            branch_result.stdout.decode("utf-8", errors="strict").strip()
            if branch_result.returncode == 0
            else "HEAD"
        )
        staged = _run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "--stage",
                "-v",
                "-z",
                "--",
            ],
            cwd=repo,
            code="GIT_UNAVAILABLE",
        ).stdout
        dirty = _match_cache_dirty_inventory(repo)
        dirty_paths = _normalized_dirty_paths(dirty)
        dirty_fingerprint = _dirty_fingerprint(repo, dirty)
        control_fingerprint = _tgrep_control_fingerprint(repo)
    except (KnowledgeError, UnicodeError, OSError):
        return None
    if dirty_paths is None or dirty_fingerprint is None or control_fingerprint is None:
        return None
    repository = {
        "branch": branch,
        "canonical_worktree": str(repo.resolve()),
        "dirty_fingerprint": dirty_fingerprint,
        "git_index_sha256": sha256_bytes(staged),
        "head": head,
        "control_fingerprint": control_fingerprint,
        "dirty_paths": list(dirty_paths),
    }
    repository["snapshot_sha256"] = sha256_bytes(
        _canonical_json_bytes(repository)
    )
    return repository


def _tgrep_load_state(repo: Path) -> dict[str, Any] | None:
    path = _tgrep_state_path(repo)
    try:
        metadata = path.lstat()
        if (
            _metadata_is_redirect(metadata)
            or not stat.S_ISREG(metadata.st_mode)
            or _redirected(path, repo)
        ):
            return None
        raw = path.read_bytes()
        after = path.lstat()
    except OSError:
        return None
    if (
        _metadata_is_redirect(after)
        or not stat.S_ISREG(after.st_mode)
        or _regular_file_fingerprint(metadata) != _regular_file_fingerprint(after)
    ):
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _tgrep_state_is_valid(repo: Path, state: dict[str, Any] | None = None) -> bool:
    try:
        return _tgrep_state_is_valid_unchecked(repo, state)
    except (KnowledgeError, OSError, UnicodeError, TypeError, ValueError):
        return False


def _tgrep_state_is_valid_unchecked(
    repo: Path,
    state: dict[str, Any] | None = None,
) -> bool:
    """Fail closed without ever exposing tgrep stderr to the query caller."""

    if os.name != "nt":
        return False
    state = state if state is not None else _tgrep_load_state(repo)
    if not isinstance(state, dict) or state.get("schema") != TGREP_STATE_SCHEMA or state.get("ready") is not True:
        return False
    binary = _tgrep_binary_path(repo)
    if binary is None:
        return False
    binary_state = state.get("binary")
    if not isinstance(binary_state, dict):
        return False
    if binary_state.get("path") != "tgrep.exe":
        return False
    binary_sha = _stable_file_sha256(binary, repo)
    if binary_sha is None or binary_sha != binary_state.get("sha256"):
        return False
    version = _tgrep_binary_version(binary, repo)
    if version is None or version != binary_state.get("version"):
        return False
    index_state = state.get("index")
    index_path = _tgrep_index_path(repo)
    if (
        not isinstance(index_state, dict)
        or index_state.get("path") != TGREP_INDEX_RELATIVE
        or not _tgrep_index_complete(index_path)
    ):
        return False
    index_fingerprint = _tgrep_index_fingerprint(index_path)
    if index_fingerprint is None or index_fingerprint != index_state.get("fingerprint"):
        return False
    parameters = state.get("parameters")
    if parameters != TGREP_INDEX_PARAMETERS:
        return False
    repository = state.get("repository_snapshot")
    if not isinstance(repository, dict):
        return False
    stored_snapshot = repository.get("snapshot_sha256")
    stored_without_digest = {
        key: value for key, value in repository.items() if key != "snapshot_sha256"
    }
    if (
        not isinstance(stored_snapshot, str)
        or sha256_bytes(_canonical_json_bytes(stored_without_digest)) != stored_snapshot
    ):
        return False
    current = _tgrep_repository_snapshot(repo)
    if current is None:
        return False
    stable_keys = (
        "branch",
        "canonical_worktree",
        "git_index_sha256",
        "head",
        "control_fingerprint",
    )
    if any(current.get(key) != repository.get(key) for key in stable_keys):
        return False
    if current.get("snapshot_sha256") != stored_snapshot:
        return False
    source = state.get("source_fingerprint")
    if not isinstance(source, dict):
        return False
    source_digest = source.get("sha256")
    source_without_digest = {key: value for key, value in source.items() if key != "sha256"}
    return (
        isinstance(source_digest, str)
        and sha256_bytes(_canonical_json_bytes(source_without_digest)) == source_digest
        and source.get("repository_snapshot_sha256") == stored_snapshot
        and source.get("index_fingerprint") == index_fingerprint
    )


def _write_tgrep_state(path: Path, state: dict[str, Any]) -> None:
    """Publish the ready sidecar only after its complete bytes are durable."""

    if path.name != Path(TGREP_STATE_RELATIVE).name:
        raise ValueError("unexpected tgrep state path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".tgrep-state-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _tgrep_search_command(
    repo: Path,
    *,
    patterns: Sequence[str],
    roots: Sequence[str],
    fixed_strings: bool,
    index_path: Path,
) -> list[str]:
    binary = _tgrep_binary_path(repo) or (repo / "tgrep.exe")
    command = [
        str(binary),
        "--no-heading",
        "--line-number",
        "--with-filename",
        "--null",
        "--ignore-case",
        "--color",
        "never",
        "--glob",
        "!.git/**",
        "--glob",
        "!.tgrep/**",
        "--index-path",
        str(index_path),
    ]
    if fixed_strings:
        command.extend(["--fixed-strings", "--max-count", "1"])
    for pattern in patterns:
        command.extend(["--regexp", pattern])
    command.extend(["--", *roots])
    return command


def _redirected(path: Path, repo: Path) -> bool:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return True
    cursor = repo
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for part in relative.parts:
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            break
        except OSError:
            return True
        if stat.S_ISLNK(metadata.st_mode) or (
            reparse_flag
            and getattr(metadata, "st_file_attributes", 0) & reparse_flag
        ):
            return True
    return False


def _metadata_is_redirect(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        reparse_flag
        and getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _directory_fingerprint(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_ctime_ns,
    )


def _eligible_paths(repo: Path, pathspecs: Sequence[str] = ()) -> set[str]:
    command = [
        "git",
        "-c",
        "core.quotepath=false",
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    if pathspecs:
        command.extend(["--", *pathspecs])
    output = _run(
        command,
        cwd=repo,
        code="GIT_UNAVAILABLE",
    ).stdout
    candidates: list[str] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            candidate = normalized_path(raw.decode("utf-8"))
        except (UnicodeDecodeError, KnowledgeError):
            continue
        if any(part in INELIGIBLE_SEGMENTS for part in candidate.split("/")):
            continue
        candidates.append(candidate)

    paths: set[str] = set()
    parent_states: dict[Path, tuple[int, int, int, int, int] | None] = {}
    for candidate in candidates:
        parts = candidate.split("/")
        cursor = repo
        parent_safe = True
        for part in parts[:-1]:
            cursor = cursor / part
            if cursor not in parent_states:
                try:
                    metadata = cursor.lstat()
                except OSError:
                    parent_states[cursor] = None
                else:
                    parent_states[cursor] = (
                        _directory_fingerprint(metadata)
                        if stat.S_ISDIR(metadata.st_mode)
                        and not _metadata_is_redirect(metadata)
                        else None
                    )
            if parent_states[cursor] is None:
                parent_safe = False
                break
        if not parent_safe:
            continue
        lexical = cursor / parts[-1]
        try:
            metadata = lexical.lstat()
        except OSError:
            continue
        if _metadata_is_redirect(metadata) or not stat.S_ISREG(metadata.st_mode):
            continue
        paths.add(candidate)

    for parent, expected in parent_states.items():
        if expected is None:
            continue
        try:
            current = parent.lstat()
        except OSError as exc:
            raise KnowledgeError(
                "SOURCE_INELIGIBLE",
                "repository directory changed during eligibility scan",
                exit_code=3,
            ) from exc
        if (
            _metadata_is_redirect(current)
            or not stat.S_ISDIR(current.st_mode)
            or _directory_fingerprint(current) != expected
        ):
            raise KnowledgeError(
                "SOURCE_INELIGIBLE",
                "repository directory changed during eligibility scan",
                exit_code=3,
            )
    return paths


def _query_terms(query: str) -> list[str]:
    folded = query.casefold().strip()
    if not folded:
        raise KnowledgeError(
            "INVALID_QUERY",
            "query must contain non-whitespace text",
            exit_code=2,
        )
    terms: list[str] = []
    terms.extend(re.findall(r"[a-z0-9_.-]+", folded))
    for run in CJK_RUN_RE.findall(folded):
        terms.append(run)
        for width in (2, 3):
            if len(run) < width:
                continue
            terms.extend(run[index : index + width] for index in range(len(run) - width + 1))
    for trigger, aliases in CJK_DOMAIN_ALIASES_V1:
        if trigger in folded:
            terms.extend(aliases)
    return list(dict.fromkeys(terms))[:MAX_QUERY_TERMS]


def _owner_contract_intent(query: str) -> bool:
    compact = re.sub(r"\s+", "", query.casefold())
    return bool(
        ("流程" in compact and "速度" in compact)
        or (
            "審查" in compact
            and any(token in compact for token in ("兩次", "为什么", "為什麼", "實作完成"))
        )
    )


def _query_pattern(query: str, terms: list[str]) -> str:
    values = [query.casefold().strip(), *terms]
    escaped = [re.escape(value).replace(r"\ ", " ") for value in dict.fromkeys(values)]
    return "(?:" + ")|(?:".join(escaped) + ")"


def _regular_file_fingerprint(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _merge_nul_path_streams(*streams: bytes) -> bytes:
    records = sorted(
        {
            value
            for stream in streams
            for value in stream.split(b"\0")
            if value
        }
    )
    return b"\0".join(records) + (b"\0" if records else b"")


def _staged_inventory_metadata(
    staged: bytes,
) -> tuple[int, tuple[str, ...]] | None:
    staged_records = [record for record in staged.split(b"\0") if record]
    attribute_paths: list[str] = []
    seen_paths: set[bytes] = set()
    for record in staged_records:
        if not record.startswith(b"H "):
            return None
        tab = record.find(b"\t")
        if tab <= 2 or tab == len(record) - 1:
            return None
        raw_path = record[tab + 1 :]
        if raw_path in seen_paths:
            return None
        seen_paths.add(raw_path)
        try:
            relative = normalized_path(raw_path.decode("utf-8"))
        except (UnicodeDecodeError, KnowledgeError):
            return None
        if relative == ".gitattributes" or relative.endswith("/.gitattributes"):
            attribute_paths.append(relative)
    return len(staged_records), tuple(sorted(attribute_paths))


def _match_cache_dirty_inventory(repo: Path) -> bytes:
    tracked_dirty = _run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "diff-files",
            "--name-only",
            "-z",
            "--",
        ],
        cwd=repo,
        code="GIT_UNAVAILABLE",
    ).stdout
    untracked = _run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
        ],
        cwd=repo,
        code="GIT_UNAVAILABLE",
    ).stdout
    return _merge_nul_path_streams(tracked_dirty, untracked)


def _update_dirty_digests(
    repo: Path,
    dirty: bytes,
    digests: Sequence[Any],
) -> bool:
    for raw_path in sorted({value for value in dirty.split(b"\0") if value}):
        try:
            relative = normalized_path(raw_path.decode("utf-8"))
        except (UnicodeDecodeError, KnowledgeError):
            return False
        lexical = repo / Path(*relative.split("/"))
        for digest in digests:
            digest.update(len(raw_path).to_bytes(8, "big"))
            digest.update(raw_path)
        if _redirected(lexical, repo):
            return False
        try:
            before = lexical.lstat()
        except FileNotFoundError:
            for digest in digests:
                digest.update(b"missing")
            continue
        except OSError:
            return False
        if _metadata_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            return False
        try:
            raw = lexical.read_bytes()
            after = lexical.lstat()
        except OSError:
            return False
        if (
            _metadata_is_redirect(after)
            or not stat.S_ISREG(after.st_mode)
            or _regular_file_fingerprint(after) != _regular_file_fingerprint(before)
        ):
            return False
        raw_digest = hashlib.sha256(raw).digest()
        for digest in digests:
            digest.update(raw_digest)
    return True


def _dirty_fingerprint(repo: Path, dirty: bytes) -> str | None:
    digest = hashlib.sha256()
    digest.update(b"dirty")
    digest.update(len(dirty).to_bytes(8, "big"))
    digest.update(dirty)
    if not _update_dirty_digests(repo, dirty, (digest,)):
        return None
    return digest.hexdigest()


def _normalized_dirty_paths(dirty: bytes) -> tuple[str, ...] | None:
    paths: list[str] = []
    for raw_path in sorted({value for value in dirty.split(b"\0") if value}):
        try:
            paths.append(normalized_path(raw_path.decode("utf-8")))
        except (UnicodeDecodeError, KnowledgeError):
            return None
    return tuple(paths)


def _match_cache_fingerprint(repo: Path) -> MatchCacheFingerprint | None:
    staged = _run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "ls-files",
            "--stage",
            "-v",
            "-z",
            "--",
        ],
        cwd=repo,
        code="GIT_UNAVAILABLE",
    ).stdout
    staged_metadata = _staged_inventory_metadata(staged)
    if staged_metadata is None:
        return None
    tracked_count, attribute_paths = staged_metadata
    dirty = _match_cache_dirty_inventory(repo)
    dirty_paths = _normalized_dirty_paths(dirty)
    if dirty_paths is None:
        return None
    digest = hashlib.sha256()
    for label, value in ((b"staged", staged), (b"dirty", dirty)):
        digest.update(label)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    dirty_digest = hashlib.sha256()
    dirty_digest.update(b"dirty")
    dirty_digest.update(len(dirty).to_bytes(8, "big"))
    dirty_digest.update(dirty)
    if not _update_dirty_digests(repo, dirty, (digest, dirty_digest)):
        return None
    return MatchCacheFingerprint(
        digest.hexdigest(),
        dirty_digest.hexdigest(),
        dirty_paths,
        attribute_paths,
        tracked_count,
    )


def _match_cache_dirty_fingerprint(repo: Path) -> str | None:
    dirty = _match_cache_dirty_inventory(repo)
    return _dirty_fingerprint(repo, dirty)


def _match_cache_index_fingerprint(index_path: Path) -> IndexFingerprint | None:
    try:
        metadata = index_path.lstat()
    except OSError:
        return None
    if _metadata_is_redirect(metadata) or not stat.S_ISREG(metadata.st_mode):
        return None
    return _regular_file_fingerprint(metadata)


def _match_cache_index_snapshot(repo: Path) -> tuple[Path, IndexFingerprint] | None:
    git_metadata = repo / ".git"
    try:
        git_metadata_stat = git_metadata.lstat()
    except OSError:
        git_metadata_stat = None
    if (
        git_metadata_stat is not None
        and stat.S_ISDIR(git_metadata_stat.st_mode)
        and not _metadata_is_redirect(git_metadata_stat)
    ):
        index_path = git_metadata / "index"
    else:
        raw_path = _run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                "index",
            ],
            cwd=repo,
            code="GIT_UNAVAILABLE",
        ).stdout
        try:
            path_text = raw_path.decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
        if not path_text or "\0" in path_text or "\r" in path_text or "\n" in path_text:
            return None
        index_path = Path(path_text)
        if not index_path.is_absolute():
            index_path = repo / index_path
    fingerprint = _match_cache_index_fingerprint(index_path)
    if fingerprint is None:
        return None
    return index_path, fingerprint


def _capture_match_cache_snapshot(
    repo: Path,
    cached: MatchCacheSnapshot | None,
) -> MatchCacheSnapshot | None:
    """Reuse a verified staged snapshot while independently checking dirty bytes."""

    if cached is not None:
        before_index = _match_cache_index_fingerprint(cached.index_path)
        if before_index == cached.index_fingerprint:
            dirty_fingerprint = _match_cache_dirty_fingerprint(repo)
            after_index = _match_cache_index_fingerprint(cached.index_path)
            if (
                after_index == cached.index_fingerprint
                and dirty_fingerprint == cached.dirty_fingerprint
            ):
                return cached

    index_snapshot = _match_cache_index_snapshot(repo)
    captured = _match_cache_fingerprint(repo)
    if not isinstance(captured, MatchCacheFingerprint) or index_snapshot is None:
        return None
    index_path, index_fingerprint = index_snapshot
    if _match_cache_index_fingerprint(index_path) != index_fingerprint:
        return None
    return MatchCacheSnapshot(
        fingerprint=str(captured),
        dirty_fingerprint=captured.dirty_fingerprint,
        index_path=index_path,
        index_fingerprint=index_fingerprint,
        dirty_paths=captured.dirty_paths,
        attribute_paths=captured.attribute_paths,
        tracked_count=captured.tracked_count,
    )


def _attribute_file_allows_index_search(path: Path, repo: Path | None = None) -> bool:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if (
        _metadata_is_redirect(before)
        or not stat.S_ISREG(before.st_mode)
        or (repo is not None and _redirected(path, repo))
        or before.st_size > 1024 * 1024
    ):
        return False
    try:
        raw = path.read_bytes()
        after = path.lstat()
    except OSError:
        return False
    return (
        _regular_file_fingerprint(before) == _regular_file_fingerprint(after)
        and b"\0" not in raw
        and SEMANTIC_ATTRIBUTE_PATTERN.search(raw) is None
    )


def _index_search_is_safe(repo: Path, snapshot: MatchCacheSnapshot) -> bool:
    if any(
        path == ".gitattributes" or path.endswith("/.gitattributes")
        for path in snapshot.dirty_paths
    ):
        return False
    git_metadata = repo / ".git"
    try:
        git_metadata_stat = git_metadata.lstat()
    except OSError:
        return False
    if not stat.S_ISDIR(git_metadata_stat.st_mode) or _metadata_is_redirect(git_metadata_stat):
        return False
    try:
        configured_attributes = _run(
            ["git", "config", "--path", "--get", "core.attributesFile"],
            cwd=repo,
            accepted={0, 1},
            code="GIT_UNAVAILABLE",
        ).stdout
        if configured_attributes.strip():
            return False
    except KnowledgeError:
        return False
    for relative in snapshot.attribute_paths:
        if not _attribute_file_allows_index_search(
            repo / Path(*relative.split("/")),
            repo,
        ):
            return False
    return _attribute_file_allows_index_search(
        snapshot.index_path.parent / "info" / "attributes"
    )


class QuerySearchSession:
    """Invocation-local search cache guarded by one pre/post repository fingerprint."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.repo_key = str(repo)
        cached = _MATCH_CACHE.get(self.repo_key)
        self._snapshot = _capture_match_cache_snapshot(
            repo,
            cached.snapshot if cached is not None else None,
        )
        self.fingerprint = (
            self._snapshot.fingerprint if self._snapshot is not None else None
        )
        self.dirty_paths = (
            self._snapshot.dirty_paths if self._snapshot is not None else ()
        )
        self.tgrep_state = _tgrep_load_state(repo)
        self.tgrep_search_enabled = _tgrep_state_is_valid(repo, self.tgrep_state)
        state_dirty_paths: tuple[str, ...] = ()
        if self.tgrep_search_enabled and isinstance(self.tgrep_state, dict):
            repository = self.tgrep_state.get("repository_snapshot")
            if isinstance(repository, dict):
                values = repository.get("dirty_paths", [])
                if isinstance(values, list):
                    state_dirty_paths = tuple(
                        value
                        for value in values
                        if isinstance(value, str)
                    )
        self.tgrep_dirty_paths = tuple(
            sorted(
                set(self.dirty_paths).union(state_dirty_paths),
                key=lambda value: value.encode("utf-8"),
            )
        )
        self.tgrep_index_path = _tgrep_index_path(repo)
        self.tgrep_index_fingerprint = (
            _tgrep_index_fingerprint(self.tgrep_index_path)
            if self.tgrep_search_enabled
            else None
        )
        dirty_path_bytes = sum(len(path.encode("utf-8")) + 1 for path in self.dirty_paths)
        self.index_search_enabled = bool(
            self._snapshot is not None
            and self._snapshot.tracked_count >= INDEX_SEARCH_MIN_TRACKED_PATHS
            and len(self.dirty_paths) <= INDEX_SEARCH_MAX_DIRTY_PATHS
            and dirty_path_bytes <= INDEX_SEARCH_MAX_DIRTY_BYTES
            and _index_search_is_safe(repo, self._snapshot)
        )
        self._matches = (
            dict(cached.matches)
            if self.fingerprint is not None
            and cached is not None
            and cached.snapshot.fingerprint == self.fingerprint
            else {}
        )
        self._pending: dict[SearchCacheKey, tuple[Match, ...]] = {}
        self._validated = False

    def lookup(self, key: SearchCacheKey) -> tuple[Match, ...] | None:
        if key in self._pending:
            return self._pending[key]
        return self._matches.get(key)

    def remember(self, key: SearchCacheKey, matches: list[Match]) -> None:
        if self.fingerprint is not None:
            self._pending[key] = tuple(matches)

    def validate(self) -> None:
        if self._validated:
            return
        if self.fingerprint is not None and self._snapshot is not None:
            index_unchanged = (
                _match_cache_index_fingerprint(self._snapshot.index_path)
                == self._snapshot.index_fingerprint
            )
            after_dirty = _match_cache_dirty_fingerprint(self.repo)
            if (
                not index_unchanged
                or after_dirty != self._snapshot.dirty_fingerprint
            ):
                raise KnowledgeError(
                    "SOURCE_DRIFT",
                    "repository bytes changed during search",
                    exit_code=3,
                    recoverable=True,
                )
            if (
                self.tgrep_search_enabled
                and self.tgrep_index_fingerprint is not None
                and _tgrep_index_fingerprint(self.tgrep_index_path)
                != self.tgrep_index_fingerprint
            ):
                raise KnowledgeError(
                    "SOURCE_DRIFT",
                    "tgrep index changed during search",
                    exit_code=3,
                    recoverable=True,
                )
            if len(_MATCH_CACHE) >= 8 and self.repo_key not in _MATCH_CACHE:
                _MATCH_CACHE.pop(next(iter(_MATCH_CACHE)))
            self._matches.update(self._pending)
            _MATCH_CACHE[self.repo_key] = MatchCacheEntry(
                snapshot=self._snapshot,
                matches=self._matches,
            )
        self._validated = True


def _parse_rg_matches(output: bytes) -> list[Match]:
    matches: list[Match] = []
    cursor = 0
    while cursor < len(output):
        path_end = output.find(b"\0", cursor)
        record_end = output.find(b"\n", path_end + 1)
        if path_end < cursor or record_end < 0:
            raise KnowledgeError(
                "RG_OUTPUT_INVALID",
                "ripgrep emitted an invalid NUL-delimited record",
                exit_code=4,
            )
        record = output[path_end + 1 : record_end]
        number_end = record.find(b":")
        if number_end <= 0:
            raise KnowledgeError(
                "RG_OUTPUT_INVALID",
                "ripgrep emitted an invalid line record",
                exit_code=4,
            )
        try:
            path_text = output[cursor:path_end].decode("utf-8")
            line_number = int(record[:number_end].decode("ascii"))
            line_text = record[number_end + 1 :].decode("utf-8").rstrip("\r")
        except (UnicodeDecodeError, ValueError):
            raise KnowledgeError(
                "RG_OUTPUT_INVALID",
                "ripgrep emitted an invalid UTF-8 match record",
                exit_code=4,
            )
        try:
            path = normalized_path(path_text)
        except KnowledgeError:
            cursor = record_end + 1
            continue
        matches.append(Match(path=path, line_number=line_number, line_text=line_text))
        cursor = record_end + 1
    matches.sort(key=lambda item: (item.path.encode("utf-8"), item.line_number))
    return matches


def _parse_tgrep_matches(output: bytes) -> list[Match]:
    """Parse tgrep's requested NUL format and its v1.0.4 line fallback."""

    # Keep the NUL parser as the preferred wire format.  tgrep 1.0.4 accepts
    # ``--null`` but, for the ripgrep-compatible CLI, currently emits the
    # regular ``path:line:text`` representation.  Supporting both keeps the
    # adapter fail-closed without weakening the command contract.
    if b"\0" in output:
        return _parse_rg_matches(output)

    matches: list[Match] = []
    records = output.split(b"\n")
    if records and records[-1] == b"":
        records.pop()
    for record in records:
        if not record:
            raise KnowledgeError(
                "TGREP_OUTPUT_INVALID",
                "tgrep emitted an empty line record",
                exit_code=4,
            )
        record = record.rstrip(b"\r")
        # Use the first path/line separator.  Match text commonly contains
        # JSON timestamps such as ``:2026-09-01T13:00:00``; a greedy path
        # expression would incorrectly absorb the real line number.
        separator = re.match(rb"^(.+?):([0-9]+):(.*)$", record)
        if separator is None:
            raise KnowledgeError(
                "TGREP_OUTPUT_INVALID",
                "tgrep emitted an invalid line record",
                exit_code=4,
            )
        try:
            path_text = separator.group(1).decode("utf-8")
            line_number = int(separator.group(2).decode("ascii"))
            line_text = separator.group(3).decode("utf-8").rstrip("\r")
        except (UnicodeDecodeError, ValueError):
            raise KnowledgeError(
                "TGREP_OUTPUT_INVALID",
                "tgrep emitted an invalid UTF-8 match record",
                exit_code=4,
            )
        try:
            path = normalized_path(path_text)
        except KnowledgeError:
            continue
        matches.append(Match(path=path, line_number=line_number, line_text=line_text))
    matches.sort(key=lambda item: (item.path.encode("utf-8"), item.line_number))
    return matches


def _tgrep_search(
    repo: Path,
    *,
    patterns: Sequence[str],
    roots: Sequence[str],
    fixed_strings: bool,
    index_path: Path,
) -> list[Match] | None:
    """Run tgrep; ``None`` means the caller must use the rg fallback."""

    if not patterns:
        return []
    command = _tgrep_search_command(
        repo,
        patterns=patterns,
        roots=roots,
        fixed_strings=fixed_strings,
        index_path=index_path,
    )
    command_bytes = sum(len(value.encode("utf-8")) + 1 for value in command)
    if command_bytes > TGREP_MAX_COMMAND_BYTES:
        return None
    try:
        completed = _run(
            command,
            cwd=repo,
            accepted={0, 1},
            code="TGREP_UNAVAILABLE",
        )
    except (KnowledgeError, OSError):
        return None
    if completed.returncode == 1:
        return []
    try:
        return _parse_tgrep_matches(completed.stdout)
    except KnowledgeError:
        return None


def _discard_tgrep_state(repo: Path) -> None:
    path = _tgrep_state_path(repo)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def tgrep_index_repository(repo_value: str, *, force: bool = False) -> dict[str, Any]:
    """Explicitly build and publish the repository-local tgrep index."""

    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError(
            "REPOSITORY_MISSING",
            "repository root does not exist",
            exit_code=4,
        )
    if os.name != "nt":
        raise KnowledgeError(
            "TGREP_UNSUPPORTED_PLATFORM",
            "tgrep.exe index is supported only on Windows",
            exit_code=4,
        )
    binary = _tgrep_binary_path(repo)
    if binary is None:
        raise KnowledgeError(
            "TGREP_BINARY_MISSING",
            "repository-bundled tgrep.exe is missing or redirected",
            exit_code=4,
        )
    binary_sha = _stable_file_sha256(binary, repo)
    version = _tgrep_binary_version(binary, repo)
    if binary_sha is None or version is None:
        raise KnowledgeError(
            "TGREP_UNAVAILABLE",
            "repository-bundled tgrep.exe could not be verified",
            exit_code=4,
        )
    if version != TGREP_EXPECTED_VERSION:
        raise KnowledgeError(
            "TGREP_VERSION_UNSUPPORTED",
            f"expected tgrep {TGREP_EXPECTED_VERSION}, found {version}",
            exit_code=4,
        )
    if not force:
        existing = _tgrep_load_state(repo)
        if _tgrep_state_is_valid(repo, existing):
            assert existing is not None
            return {
                "schema": TGREP_RESULT_SCHEMA,
                "status": "ready",
                "rebuilt": False,
                "state_path": TGREP_STATE_RELATIVE,
                "binary": existing.get("binary"),
                "parameters": existing.get("parameters"),
                "repository_snapshot": existing.get("repository_snapshot"),
                "source_fingerprint": existing.get("source_fingerprint"),
                "index": existing.get("index"),
            }
    before = _tgrep_repository_snapshot(repo)
    if before is None:
        raise KnowledgeError(
            "TGREP_SNAPSHOT_FAILED",
            "could not capture repository snapshot before indexing",
            exit_code=3,
            recoverable=True,
        )
    _discard_tgrep_state(repo)
    command = [
        str(binary),
        "index",
        "--hidden",
        "--exclude",
        ".git",
        "--exclude",
        ".tgrep",
    ]
    if force:
        command.append("--force")
    command.append(".")
    try:
        _run(
            command,
            cwd=repo,
            code="TGREP_INDEX_FAILED",
        )
    except (KnowledgeError, OSError) as exc:
        _discard_tgrep_state(repo)
        if isinstance(exc, KnowledgeError):
            raise
        raise KnowledgeError(
            "TGREP_INDEX_FAILED",
            "tgrep index command failed",
            exit_code=4,
        ) from exc
    after = _tgrep_repository_snapshot(repo)
    after_binary_sha = _stable_file_sha256(binary, repo)
    after_version = _tgrep_binary_version(binary, repo)
    index_path = _tgrep_index_path(repo)
    index_fingerprint = _tgrep_index_fingerprint(index_path)
    index_status_ok = _tgrep_index_status(binary, repo, index_path)
    if (
        after is None
        or after != before
        or after_binary_sha != binary_sha
        or after_version != version
        or not _tgrep_index_complete(index_path)
        or index_fingerprint is None
        or not index_status_ok
    ):
        _discard_tgrep_state(repo)
        code = (
            "TGREP_INDEX_STATUS_INVALID"
            if not index_status_ok
            else "TGREP_REPOSITORY_CHANGED"
        )
        message = (
            "tgrep status did not report a complete index"
            if not index_status_ok
            else "repository or tgrep binary changed while building the index"
        )
        raise KnowledgeError(
            code,
            message,
            exit_code=3,
            recoverable=True,
        )
    source = {
        "dirty_paths": after.get("dirty_paths", []),
        "index_fingerprint": index_fingerprint,
        "repository_snapshot_sha256": after["snapshot_sha256"],
    }
    source["sha256"] = sha256_bytes(_canonical_json_bytes(source))
    state = {
        "schema": TGREP_STATE_SCHEMA,
        "ready": True,
        "binary": {
            "path": "tgrep.exe",
            "sha256": binary_sha,
            "version": version,
        },
        "index": {
            "path": TGREP_INDEX_RELATIVE,
            "fingerprint": index_fingerprint,
        },
        "parameters": copy.deepcopy(TGREP_INDEX_PARAMETERS),
        "repository_snapshot": after,
        "source_fingerprint": source,
    }
    try:
        _write_tgrep_state(_tgrep_state_path(repo), state)
    except OSError as exc:
        _discard_tgrep_state(repo)
        raise KnowledgeError(
            "TGREP_STATE_WRITE_FAILED",
            "could not publish tgrep index state",
            exit_code=4,
        ) from exc
    if not _tgrep_state_is_valid(repo, state):
        _discard_tgrep_state(repo)
        raise KnowledgeError(
            "TGREP_STATE_INVALID",
            "published tgrep index state could not be verified",
            exit_code=3,
            recoverable=True,
        )
    return {
        "schema": TGREP_RESULT_SCHEMA,
        "status": "ready",
        "rebuilt": True,
        "state_path": TGREP_STATE_RELATIVE,
        "binary": state["binary"],
        "parameters": state["parameters"],
        "repository_snapshot": state["repository_snapshot"],
        "source_fingerprint": state["source_fingerprint"],
        "index": state["index"],
    }


def _parse_git_grep_matches(output: bytes) -> list[Match]:
    matches: list[Match] = []
    cursor = 0
    while cursor < len(output):
        path_end = output.find(b"\0", cursor)
        number_end = output.find(b"\0", path_end + 1)
        record_end = output.find(b"\n", number_end + 1)
        if path_end < cursor or number_end <= path_end + 1 or record_end < 0:
            raise KnowledgeError(
                "GIT_OUTPUT_INVALID",
                "git grep emitted an invalid NUL-delimited record",
                exit_code=4,
            )
        try:
            path = normalized_path(output[cursor:path_end].decode("utf-8"))
            line_number = int(output[path_end + 1 : number_end].decode("ascii"))
            line_text = output[number_end + 1 : record_end].decode("utf-8").rstrip("\r")
        except (UnicodeDecodeError, ValueError, KnowledgeError) as exc:
            raise KnowledgeError(
                "GIT_OUTPUT_INVALID",
                "git grep emitted an invalid UTF-8 match record",
                exit_code=4,
            ) from exc
        matches.append(Match(path=path, line_number=line_number, line_text=line_text))
        cursor = record_end + 1
    matches.sort(key=lambda item: (item.path.encode("utf-8"), item.line_number))
    return matches


def _rg_matches(
    repo: Path,
    pattern: str,
    *,
    roots: Sequence[str] = (".",),
    session: QuerySearchSession | None = None,
) -> list[Match]:
    owned_session = session is None
    active_session = session or QuerySearchSession(repo)
    cache_key: SearchCacheKey = ("regex", (pattern,), tuple(roots))
    cached_matches = active_session.lookup(cache_key)
    if cached_matches is not None:
        matches = list(cached_matches)
        if owned_session:
            active_session.validate()
        return matches
    threads = min(16, max(4, os.cpu_count() or 4))
    completed = _run(
        [
            "rg",
            "--threads",
            str(threads),
            "--no-heading",
            "--line-number",
            "--with-filename",
            "--null",
            "--ignore-case",
            "--hidden",
            "--color",
            "never",
            "--glob",
            "!.git/**",
            "--regexp",
            pattern,
            *roots,
        ],
        cwd=repo,
        accepted={0, 1},
        code="RG_UNAVAILABLE",
    )
    matches = _parse_rg_matches(completed.stdout)
    active_session.remember(cache_key, matches)
    if owned_session:
        active_session.validate()
    return matches


def _path_is_under_roots(path: str, roots: Sequence[str]) -> bool:
    for root in roots:
        if root == ".":
            return True
        try:
            normalized_root = normalized_path(root).rstrip("/")
        except KnowledgeError:
            continue
        if path == normalized_root or path.startswith(normalized_root + "/"):
            return True
    return False


def _dirty_overlay_paths(
    repo: Path,
    dirty_paths: Sequence[str],
    roots: Sequence[str],
) -> tuple[str, ...]:
    candidates = tuple(
        path
        for path in dirty_paths
        if _path_is_under_roots(path, roots)
        and not any(part in INELIGIBLE_SEGMENTS for part in path.split("/"))
    )
    if not candidates:
        return ()
    eligible = _eligible_paths(repo, candidates)
    return tuple(
        sorted(
            (path for path in candidates if path in eligible),
            key=lambda value: value.encode("utf-8"),
        )
    )


def _tgrep_worktree_matches(
    repo: Path,
    patterns: Sequence[str],
    *,
    roots: Sequence[str],
    fixed_strings: bool,
    session: QuerySearchSession,
) -> list[Match] | None:
    """Search indexed bytes, then read every changed path as a direct overlay."""

    if not session.tgrep_search_enabled:
        return None
    overlay_paths = _dirty_overlay_paths(
        repo,
        session.tgrep_dirty_paths,
        roots,
    )
    indexed = _tgrep_search(
        repo,
        patterns=patterns,
        roots=roots,
        fixed_strings=fixed_strings,
        index_path=session.tgrep_index_path,
    )
    if indexed is None:
        return None
    indexed = [match for match in indexed if match.path not in overlay_paths]
    if overlay_paths:
        overlay = _tgrep_search(
            repo,
            patterns=patterns,
            roots=overlay_paths,
            fixed_strings=fixed_strings,
            index_path=session.tgrep_index_path,
        )
        if overlay is None:
            return None
    else:
        overlay = []
    unique = {
        (match.path, match.line_number, match.line_text): match
        for match in [*indexed, *overlay]
    }
    return sorted(
        unique.values(),
        key=lambda item: (item.path.encode("utf-8"), item.line_number),
    )


def _search_worktree_regex(
    repo: Path,
    pattern: str,
    *,
    roots: Sequence[str] = (".",),
    session: QuerySearchSession | None = None,
) -> list[Match]:
    """Use tgrep when its verified index is available, otherwise use rg."""

    owned_session = session is None
    active_session = session or QuerySearchSession(repo)
    cache_key: SearchCacheKey = ("regex", (pattern,), tuple(roots))
    cached_matches = active_session.lookup(cache_key)
    if cached_matches is not None:
        matches = list(cached_matches)
        if owned_session:
            active_session.validate()
        return matches
    matches = _tgrep_worktree_matches(
        repo,
        [pattern],
        roots=roots,
        fixed_strings=False,
        session=active_session,
    )
    if matches is None:
        matches = _rg_matches(repo, pattern, roots=roots, session=active_session)
    active_session.remember(cache_key, matches)
    if owned_session:
        active_session.validate()
    return matches


def _git_index_fixed_matches(
    repo: Path,
    encoded_patterns: Sequence[bytes],
    *,
    roots: Sequence[str],
) -> list[Match]:
    threads = min(16, max(4, os.cpu_count() or 4))
    completed = _run(
        [
            "git",
            "-c",
            "core.quotepath=false",
            "grep",
            "--cached",
            "--ignore-case",
            "--line-number",
            "--full-name",
            "--null",
            "--fixed-strings",
            "-I",
            "--threads",
            str(threads),
            "--no-color",
            "-m",
            "1",
            "-f",
            "-",
            "--",
            *roots,
        ],
        cwd=repo,
        accepted={0, 1},
        code="GIT_UNAVAILABLE",
        input_bytes=b"\n".join(encoded_patterns) + b"\n",
    )
    return _parse_git_grep_matches(completed.stdout)


def _rg_fixed_worktree_matches(
    repo: Path,
    encoded_patterns: Sequence[bytes],
    *,
    roots: Sequence[str],
) -> list[Match]:
    threads = min(16, max(4, os.cpu_count() or 4))
    completed = _run(
        [
            "rg",
            "--threads",
            str(threads),
            "--no-heading",
            "--line-number",
            "--with-filename",
            "--null",
            "--ignore-case",
            "--hidden",
            "--color",
            "never",
            "--glob",
            "!.git/**",
            "--fixed-strings",
            "--file",
            "-",
            "--max-count",
            "1",
            "--",
            *roots,
        ],
        cwd=repo,
        accepted={0, 1},
        code="RG_UNAVAILABLE",
        input_bytes=b"\n".join(encoded_patterns) + b"\n",
    )
    return _parse_rg_matches(completed.stdout)


def _index_and_dirty_fixed_matches(
    repo: Path,
    encoded_patterns: Sequence[bytes],
    *,
    roots: Sequence[str],
    session: QuerySearchSession,
) -> list[Match]:
    dirty_paths = set(session.dirty_paths)
    matches = [
        match
        for match in _git_index_fixed_matches(repo, encoded_patterns, roots=roots)
        if match.path not in dirty_paths
    ]
    overlay_paths = _dirty_overlay_paths(repo, session.dirty_paths, roots)
    if overlay_paths:
        matches.extend(
            _rg_fixed_worktree_matches(
                repo,
                encoded_patterns,
                roots=overlay_paths,
            )
        )
    unique = {
        (match.path, match.line_number, match.line_text): match
        for match in matches
    }
    return sorted(
        unique.values(),
        key=lambda item: (item.path.encode("utf-8"), item.line_number),
    )


def _rg_fixed_matches(
    repo: Path,
    patterns: Iterable[str],
    *,
    roots: Sequence[str],
    session: QuerySearchSession | None = None,
) -> list[Match]:
    normalized_patterns = tuple(
        sorted(
            {value for value in patterns if isinstance(value, str) and value},
            key=lambda value: value.encode("utf-8"),
        )
    )
    if not normalized_patterns:
        return []
    encoded_patterns = [value.encode("utf-8") for value in normalized_patterns]
    payload_size = sum(len(value) + 1 for value in encoded_patterns)
    safe_stdin = payload_size <= MAX_FIXED_PATTERN_BYTES and all(
        not any(marker in value for marker in (b"\0", b"\r", b"\n"))
        for value in encoded_patterns
    )
    if not safe_stdin:
        matches: list[Match] = []
        for offset in range(0, len(normalized_patterns), 64):
            batch = normalized_patterns[offset : offset + 64]
            pattern = "(?:" + ")|(?:".join(re.escape(value) for value in batch) + ")"
            matches.extend(_rg_matches(repo, pattern, roots=roots, session=session))
        return matches

    owned_session = session is None
    active_session = session or QuerySearchSession(repo)
    cache_key: SearchCacheKey = ("fixed", normalized_patterns, tuple(roots))
    cached_matches = active_session.lookup(cache_key)
    if cached_matches is not None:
        matches = list(cached_matches)
        if owned_session:
            active_session.validate()
        return matches
    if active_session.index_search_enabled:
        if getattr(active_session, "tgrep_search_enabled", False):
            overlay_paths = _dirty_overlay_paths(
                repo,
                active_session.tgrep_dirty_paths,
                roots,
            )
            clean_matches = _git_index_fixed_matches(
                repo,
                encoded_patterns,
                roots=roots,
            )
            clean_matches = [
                match for match in clean_matches if match.path not in overlay_paths
            ]
            overlay_matches = _tgrep_search(
                repo,
                patterns=normalized_patterns,
                roots=overlay_paths,
                fixed_strings=True,
                index_path=active_session.tgrep_index_path,
            ) if overlay_paths else []
            if overlay_matches is None:
                matches = _index_and_dirty_fixed_matches(
                    repo,
                    encoded_patterns,
                    roots=roots,
                    session=active_session,
                )
            else:
                matches = clean_matches + overlay_matches
        else:
            matches = _index_and_dirty_fixed_matches(
                repo,
                encoded_patterns,
                roots=roots,
                session=active_session,
            )
    elif getattr(active_session, "tgrep_search_enabled", False):
        matches = _tgrep_worktree_matches(
            repo,
            normalized_patterns,
            roots=roots,
            fixed_strings=True,
            session=active_session,
        )
        if matches is None:
            matches = _rg_fixed_worktree_matches(
                repo,
                encoded_patterns,
                roots=roots,
            )
    else:
        matches = _rg_fixed_worktree_matches(
            repo,
            encoded_patterns,
            roots=roots,
        )
    active_session.remember(cache_key, matches)
    if owned_session:
        active_session.validate()
    return matches


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(
            "CONTRACT_CORRUPT",
            f"{label} is not readable JSON",
            exit_code=2,
            evidence_refs=[label],
        ) from exc
    if not isinstance(value, dict):
        raise KnowledgeError(
            "CONTRACT_CORRUPT",
            f"{label} is not an object",
            exit_code=2,
            evidence_refs=[label],
        )
    return value


def _read_eligible(repo: Path, relative: str, eligible: set[str]) -> bytes:
    path = normalized_path(relative)
    if path not in eligible:
        raise KnowledgeError(
            "SOURCE_INELIGIBLE",
            f"source is not tracked or unignored: {path}",
            exit_code=3,
            evidence_refs=[path],
        )
    lexical = repo / Path(*path.split("/"))
    if _redirected(lexical, repo):
        raise KnowledgeError(
            "SOURCE_INELIGIBLE",
            f"source is redirected or missing: {path}",
            exit_code=3,
            evidence_refs=[path],
        )
    try:
        before = lexical.lstat()
        if _metadata_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            raise KnowledgeError(
                "SOURCE_INELIGIBLE",
                f"source is redirected or missing: {path}",
                exit_code=3,
                evidence_refs=[path],
            )
        raw = lexical.read_bytes()
        after = lexical.lstat()
    except FileNotFoundError as exc:
        raise KnowledgeError(
            "SOURCE_DRIFT",
            f"source disappeared while it was read: {path}",
            exit_code=3,
            evidence_refs=[path],
            recoverable=True,
        ) from exc
    except OSError as exc:
        raise KnowledgeError(
            "SOURCE_DRIFT",
            f"source could not be read stably: {path}",
            exit_code=3,
            evidence_refs=[path],
            recoverable=True,
        ) from exc
    if (
        _redirected(lexical, repo)
        or _metadata_is_redirect(after)
        or not stat.S_ISREG(after.st_mode)
        or _regular_file_fingerprint(after) != _regular_file_fingerprint(before)
    ):
        raise KnowledgeError(
            "SOURCE_DRIFT",
            f"source changed while it was read: {path}",
            exit_code=3,
            evidence_refs=[path],
            recoverable=True,
        )
    return raw


def _verify_source_ref(repo: Path, source: dict[str, Any], eligible: set[str]) -> dict[str, Any]:
    required = {"path", "sha256", "locator", "excerpt_sha256"}
    if set(source) != required:
        raise KnowledgeError(
            "CONTRACT_CORRUPT",
            "source ref has unknown or missing fields",
            exit_code=2,
        )
    path = normalized_path(str(source["path"]))
    if path.startswith("docs/knowledge/"):
        raise KnowledgeError(
            "EVIDENCE_LOOP",
            "canonical knowledge cannot cite itself as raw evidence",
            exit_code=3,
            evidence_refs=[path],
        )
    raw = _read_eligible(repo, path, eligible)
    if sha256_bytes(raw) != source["sha256"]:
        raise KnowledgeError(
            "SOURCE_DRIFT",
            f"source hash drifted: {path}",
            exit_code=3,
            evidence_refs=[path],
            recoverable=True,
        )
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise KnowledgeError("SOURCE_ENCODING", f"source is not UTF-8: {path}", exit_code=3) from exc
    locator = source["locator"]
    if not isinstance(locator, dict) or set(locator) != {"start_line", "end_line"}:
        raise KnowledgeError("CONTRACT_CORRUPT", "source locator is invalid", exit_code=2)
    start = locator["start_line"]
    end = locator["end_line"]
    lines = text.splitlines()
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 1
        or end < start
        or end > len(lines)
    ):
        raise KnowledgeError("CONTRACT_CORRUPT", f"source locator is out of range: {path}", exit_code=2)
    excerpt = "\n".join(lines[start - 1 : end]).encode("utf-8")
    if sha256_bytes(excerpt) != source["excerpt_sha256"]:
        raise KnowledgeError(
            "EXCERPT_DRIFT",
            f"source excerpt drifted: {path}",
            exit_code=3,
            evidence_refs=[path],
            recoverable=True,
        )
    return copy.deepcopy(source)


def _match_reasons(
    query: str,
    terms: list[str],
    *,
    title: str,
    aliases: list[str],
    claim_id: str | None,
    text: str,
    tags: list[str],
    stage: str,
) -> tuple[int, list[str]]:
    folded_query = query.casefold().strip()
    folded_title = title.casefold()
    folded_aliases = {alias.casefold() for alias in aliases}
    haystack = "\n".join([folded_title, *folded_aliases, claim_id or "", text.casefold()])
    score = 0
    reasons: list[str] = []
    if folded_query == folded_title:
        score += 300
        reasons.append("title-exact")
    if folded_query in folded_aliases:
        score += 260
        reasons.append("alias-exact")
    if claim_id is not None and folded_query == claim_id.casefold():
        score += 240
        reasons.append("claim-id-exact")
    if folded_query in haystack:
        score += 180
        reasons.append("phrase")
    for term in terms:
        if term in haystack:
            score += 20
            reasons.append(f"term:{term}")
    if not reasons:
        return 0, []
    if stage in tags:
        score += 40
        reasons.append(f"stage:{stage}")
    return score, reasons


def _page_registry(
    repo: Path,
    eligible: set[str],
    sidecar_paths: Iterable[str] | None = None,
) -> list[PageSnapshot]:
    """Load page sidecars once; query-time content validation remains lazy."""

    meta_root = repo / "docs" / "knowledge" / "meta" / "pages"
    if not meta_root.is_dir():
        return []
    if sidecar_paths is None:
        relatives = [
            path.relative_to(repo).as_posix()
            for path in meta_root.glob("*.json")
        ]
    else:
        relatives = list(dict.fromkeys(sidecar_paths))
    pages: list[PageSnapshot] = []
    for sidecar_relative in sorted(relatives, key=lambda value: value.encode("utf-8")):
        if sidecar_relative not in eligible:
            continue
        raw = _read_eligible(repo, sidecar_relative, eligible)
        pages.append(
            (
                sidecar_relative,
                _load_json(raw, sidecar_relative),
                sha256_bytes(raw),
            )
        )
    return pages


def _sidecar_reference_paths(
    repo: Path,
    values: Iterable[str],
    *,
    session: QuerySearchSession | None = None,
) -> set[str]:
    """Find page contracts that name matched paths or contradiction targets."""

    root = repo / "docs" / "knowledge" / "meta" / "pages"
    if not root.is_dir():
        return set()
    normalized_values = sorted(
        {value for value in values if isinstance(value, str) and value},
        key=lambda value: value.encode("utf-8"),
    )
    paths: set[str] = set()
    for match in _rg_fixed_matches(
        repo,
        normalized_values,
        roots=("docs/knowledge/meta/pages",),
        session=session,
    ):
        if match.path.startswith("docs/knowledge/meta/pages/") and match.path.endswith(".json"):
            paths.add(match.path)
    return paths


def _query_pages_and_eligibility(
    repo: Path,
    matches: list[Match],
    *,
    session: QuerySearchSession,
) -> tuple[set[str], list[PageSnapshot]]:
    """Verify only query-relevant page contracts and their contradiction closure."""

    matched_paths = {
        match.path
        for match in matches
        if not any(part in INELIGIBLE_SEGMENTS for part in match.path.split("/"))
    }
    direct_sidecars = {
        path
        for path in matched_paths
        if path.startswith("docs/knowledge/meta/pages/") and path.endswith(".json")
    }
    sidecar_eligible = _eligible_paths(
        repo,
        sorted(direct_sidecars, key=lambda value: value.encode("utf-8")),
    ) if direct_sidecars else set()
    pages = _page_registry(repo, sidecar_eligible, direct_sidecars)
    covered_paths = {
        value
        for _, page, _ in pages
        for value in [
            page.get("content_path"),
            *[
                source.get("path")
                for claim in page.get("claims", [])
                if isinstance(claim, dict)
                for source in claim.get("source_refs", [])
                if isinstance(source, dict)
            ],
        ]
        if isinstance(value, str)
    }
    unresolved_matches = matched_paths - direct_sidecars - covered_paths
    referenced_sidecars = _sidecar_reference_paths(
        repo,
        unresolved_matches,
        session=session,
    )
    if referenced_sidecars:
        referenced_eligible = _eligible_paths(
            repo,
            sorted(referenced_sidecars, key=lambda value: value.encode("utf-8")),
        )
        pages.extend(_page_registry(repo, referenced_eligible, referenced_sidecars))
        sidecar_eligible.update(referenced_eligible)
    sidecar_paths = direct_sidecars | referenced_sidecars

    target_claim_ids = {
        target
        for _, page, _ in pages
        for claim in page.get("claims", [])
        if isinstance(claim, dict)
        for target in claim.get("contradicts", [])
        if isinstance(target, str) and target
    }
    target_sidecars = _sidecar_reference_paths(
        repo,
        target_claim_ids,
        session=session,
    ) - sidecar_paths
    if target_sidecars:
        target_eligible = _eligible_paths(
            repo,
            sorted(target_sidecars, key=lambda value: value.encode("utf-8")),
        )
        pages.extend(_page_registry(repo, target_eligible, target_sidecars))
        sidecar_eligible.update(target_eligible)

    referenced_paths: set[str] = set()
    for _, page, _ in pages:
        content_path = page.get("content_path")
        if isinstance(content_path, str):
            referenced_paths.add(content_path)
        for claim in page.get("claims", []):
            if not isinstance(claim, dict):
                continue
            for source in claim.get("source_refs", []):
                if isinstance(source, dict) and isinstance(source.get("path"), str):
                    referenced_paths.add(source["path"])
    referenced_eligible = _eligible_paths(
        repo,
        sorted(referenced_paths, key=lambda value: value.encode("utf-8")),
    ) if referenced_paths else set()
    return matched_paths | sidecar_eligible | referenced_eligible, pages


def _canonical_results(
    repo: Path,
    eligible: set[str],
    pages: list[PageSnapshot],
    matches: list[Match],
    query: str,
    terms: list[str],
    stage: str,
    blocked_claim_ids: set[str],
) -> list[dict[str, Any]]:
    match_lines: dict[str, int] = {}
    for match in matches:
        match_lines.setdefault(match.path, match.line_number)
    results: list[dict[str, Any]] = []
    matched_paths = set(match_lines)
    for sidecar_relative, page, _ in pages:
        if page.get("schema") != "knowledge-page/v1":
            raise KnowledgeError("CONTRACT_CORRUPT", f"unknown page schema: {sidecar_relative}", exit_code=2)
        if page.get("lifecycle") in INELIGIBLE_LIFECYCLES:
            continue
        content_path = normalized_path(str(page.get("content_path", "")))
        if sidecar_relative not in matched_paths and content_path not in matched_paths:
            continue
        content_raw = _read_eligible(repo, content_path, eligible)
        if sha256_bytes(content_raw) != page.get("content_sha256"):
            raise KnowledgeError(
                "PAGE_DRIFT",
                f"canonical page hash drifted: {content_path}",
                exit_code=3,
                evidence_refs=[content_path],
                recoverable=True,
            )
        try:
            content = content_raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeError("PAGE_ENCODING", f"page is not UTF-8: {content_path}", exit_code=3) from exc
        title = str(page.get("title", ""))
        aliases = page.get("aliases", [])
        tags = page.get("tags", [])
        claims = page.get("claims", [])
        if not isinstance(aliases, list) or not isinstance(tags, list) or not isinstance(claims, list):
            raise KnowledgeError("CONTRACT_CORRUPT", f"page collections are invalid: {sidecar_relative}", exit_code=2)
        for claim in claims:
            if not isinstance(claim, dict) or claim.get("lifecycle") in INELIGIBLE_LIFECYCLES:
                continue
            claim_id = str(claim.get("claim_id", ""))
            if claim_id in blocked_claim_ids:
                continue
            source_refs = claim.get("source_refs")
            if not claim_id or not isinstance(source_refs, list) or not source_refs:
                raise KnowledgeError("CONTRACT_CORRUPT", f"claim is incomplete: {sidecar_relative}", exit_code=2)
            bonus, reasons = _match_reasons(
                query,
                terms,
                title=title,
                aliases=[str(value) for value in aliases],
                claim_id=claim_id,
                text=content,
                tags=[str(value) for value in tags],
                stage=stage,
            )
            if not reasons:
                continue
            try:
                verified_refs = [
                    _verify_source_ref(repo, source, eligible)
                    for source in source_refs
                ]
            except KnowledgeError as exc:
                if exc.code in {"SOURCE_DRIFT", "SOURCE_INELIGIBLE"}:
                    continue
                raise
            results.append(
                {
                    "authority": "canonical",
                    "lifecycle": "current",
                    "match_reasons": reasons,
                    "path": content_path,
                    "start_line": match_lines.get(content_path, 1),
                    "claim_id": claim_id,
                    "score": 1000 + bonus,
                    "source_refs": verified_refs,
                }
            )
    return results


def _raw_results(
    repo: Path,
    eligible: set[str],
    matches: list[Match],
    query: str,
    terms: list[str],
    stage: str,
    blocked_source_paths: set[str],
) -> list[dict[str, Any]]:
    first_matches: dict[str, Match] = {}
    for match in matches:
        if (
            match.path not in eligible
            or match.path.startswith("docs/knowledge/")
            or match.path in blocked_source_paths
            or any(part in INELIGIBLE_SEGMENTS for part in match.path.split("/"))
        ):
            continue
        first_matches.setdefault(match.path, match)
    results: list[dict[str, Any]] = []
    for path, match in first_matches.items():
        raw = _read_eligible(repo, path, eligible)
        if b"\0" in raw[:4096]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        bonus, reasons = _match_reasons(
            query,
            terms,
            title=Path(path).stem.replace("-", " "),
            aliases=[],
            claim_id=None,
            text=text,
            tags=[],
            stage=stage,
        )
        if not reasons:
            continue
        authority_markers = AUTHORITY_MARKER_RE.findall(text)
        owner_contract = bool(
            OWNER_CONTRACT_PATH_RE.fullmatch(path)
            and len(authority_markers) == 1
            and _owner_contract_intent(query)
        )
        if owner_contract:
            bonus += 300
            reasons.append("owner-contract")
        excerpt = match.line_text.encode("utf-8")
        source_ref = {
            "path": path,
            "sha256": sha256_bytes(raw),
            "locator": {"start_line": match.line_number, "end_line": match.line_number},
            "excerpt_sha256": sha256_bytes(excerpt),
        }
        results.append(
            {
                "authority": "owner-contract" if owner_contract else "raw",
                "lifecycle": "current",
                "match_reasons": reasons,
                "path": path,
                "start_line": match.line_number,
                "claim_id": None,
                "score": (900 if owner_contract else 400) + bonus,
                "source_refs": [source_ref],
            }
        )
    return results


def _validate_result_snapshot(
    repo: Path,
    eligible: set[str],
    pages: list[PageSnapshot],
    results: list[dict[str, Any]],
) -> None:
    """Re-read returned bytes and canonical metadata before exposing cached results."""

    for result in results:
        path = normalized_path(str(result.get("path", "")))
        try:
            if result.get("authority") == "canonical":
                claim_id = result.get("claim_id")
                bindings = [
                    (sidecar_relative, page, sidecar_sha256)
                    for sidecar_relative, page, sidecar_sha256 in pages
                    if any(
                        isinstance(claim, dict)
                        and claim.get("claim_id") == claim_id
                        for claim in page.get("claims", [])
                    )
                ]
                if len(bindings) != 1:
                    raise KnowledgeError(
                        "CONTRACT_CORRUPT",
                        f"canonical result has no unique page binding: {path}",
                        exit_code=2,
                        evidence_refs=[path],
                    )
                sidecar_relative, page, sidecar_sha256 = bindings[0]
                if sha256_bytes(_read_eligible(repo, sidecar_relative, eligible)) != sidecar_sha256:
                    raise KnowledgeError(
                        "PAGE_DRIFT",
                        f"canonical result sidecar drifted: {sidecar_relative}",
                        exit_code=3,
                        evidence_refs=[sidecar_relative],
                        recoverable=True,
                    )
                expected = page.get("content_sha256")
                if normalized_path(str(page.get("content_path", ""))) != path or not isinstance(expected, str):
                    raise KnowledgeError(
                        "CONTRACT_CORRUPT",
                        f"canonical result page binding is invalid: {path}",
                        exit_code=2,
                        evidence_refs=[sidecar_relative],
                    )
                if sha256_bytes(_read_eligible(repo, path, eligible)) != expected:
                    raise KnowledgeError(
                        "PAGE_DRIFT",
                        f"canonical result page drifted: {path}",
                        exit_code=3,
                        evidence_refs=[path],
                        recoverable=True,
                    )
            source_refs = result.get("source_refs")
            if not isinstance(source_refs, list) or not source_refs:
                raise KnowledgeError(
                    "CONTRACT_CORRUPT",
                    f"query result has no source refs: {path}",
                    exit_code=2,
                    evidence_refs=[path],
                )
            for source in source_refs:
                if not isinstance(source, dict):
                    raise KnowledgeError(
                        "CONTRACT_CORRUPT",
                        f"query result source ref is invalid: {path}",
                        exit_code=2,
                        evidence_refs=[path],
                    )
                _verify_source_ref(repo, source, eligible)
        except KnowledgeError as exc:
            raise KnowledgeError(
                "SOURCE_DRIFT",
                f"query result bytes changed before return: {path}",
                exit_code=3,
                evidence_refs=exc.evidence_refs or [path],
                recoverable=True,
            ) from exc


def _conflict_registry(
    pages: list[PageSnapshot],
) -> tuple[set[str], set[str]]:
    claims: dict[str, dict[str, Any]] = {}
    for _, page, _ in pages:
        for claim in page.get("claims", []):
            if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str):
                continue
            claims[claim["claim_id"]] = claim
    blocked_claims: set[str] = set()
    blocked_sources: set[str] = set()
    for claim_id, claim in claims.items():
        contradictions = claim.get("contradicts", [])
        if not isinstance(contradictions, list):
            continue
        for target_id in contradictions:
            target = claims.get(target_id)
            target_links = target.get("contradicts", []) if isinstance(target, dict) else []
            if not isinstance(target, dict) or claim_id not in target_links:
                blocked_claims.add(claim_id)
                continue
            blocked_claims.update({claim_id, target_id})
    for claim_id in blocked_claims:
        claim = claims.get(claim_id, {})
        for source in claim.get("source_refs", []):
            if isinstance(source, dict) and isinstance(source.get("path"), str):
                try:
                    blocked_sources.add(normalized_path(source["path"]))
                except KnowledgeError:
                    continue
    return blocked_claims, blocked_sources


def query_repository(repo_value: str, *, stage: str, query: str) -> dict[str, Any]:
    _require_dependencies()
    terms = _query_terms(query)
    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    pattern = _query_pattern(query, terms)
    session = QuerySearchSession(repo)
    if session.index_search_enabled:
        matches = _rg_fixed_matches(
            repo,
            [query.casefold().strip(), *terms],
            roots=(".",),
            session=session,
        )
    else:
        matches = _search_worktree_regex(repo, pattern, session=session)
    eligible, pages = _query_pages_and_eligibility(repo, matches, session=session)
    blocked_claims, blocked_sources = _conflict_registry(pages)
    canonical = _canonical_results(
        repo,
        eligible,
        pages,
        matches,
        query,
        terms,
        stage,
        blocked_claims,
    )
    results = [
        *canonical,
        *_raw_results(
            repo,
            eligible,
            matches,
            query,
            terms,
            stage,
            blocked_sources,
        ),
    ]
    results.sort(
        key=lambda item: (
            -int(item["score"]),
            str(item["path"]).encode("utf-8"),
            int(item["start_line"]),
            str(item["claim_id"] or ""),
        )
    )
    selected_results = results[:5]
    _validate_result_snapshot(repo, eligible, pages, selected_results)
    session.validate()
    context = {
        "schema": "knowledge-context/v1",
        "stage": stage,
        "query": query.strip(),
        "results": selected_results,
        "diagnostics": [
            f"eligible:{len(eligible)}",
            f"canonical:{len(canonical)}",
            f"raw:{max(0, len(results) - len(canonical))}",
            f"contested:{len(blocked_claims)}",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return context
