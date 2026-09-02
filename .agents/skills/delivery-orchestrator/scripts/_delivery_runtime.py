#!/usr/bin/env python3
"""Private runtime primitives for delivery-orchestrator.

Authority: delivery-runtime
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "delivery-run/v1"
WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
BUG_ID_RE = re.compile(r"^(?=.{7,64}$)bug-[a-z0-9]+(?:-[a-z0-9]+)*$")
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
SECRET_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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
    "implementation": {"implementation", "planning", "knowledge", "complete"},
    "knowledge": {"knowledge", "implementation", "complete"},
    "complete": set(),
}
STATUS_TRANSITIONS = {
    "active": {"active", "awaiting_user", "blocked", "complete"},
    "awaiting_user": {"awaiting_user", "active", "blocked", "complete"},
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


def validate_bug_id(bug_id: str) -> str:
    if not isinstance(bug_id, str) or not BUG_ID_RE.fullmatch(bug_id):
        raise DeliveryError(
            "bug_id must be 7-64 lowercase ASCII kebab-case characters beginning with bug-",
            code="INVALID_BUG_ID",
        )
    return bug_id


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


def _atomic_create_json(path: Path, value: Any) -> None:
    """Persist a JSON object exactly once without an overwrite race."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise DeliveryError(f"create-only JSON path already exists: {path}", code="CREATE_ONLY_EXISTS") from exc
    complete = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        complete = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not complete:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


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


def _known_secret_values_from_env(raw_names: Iterable[str]) -> tuple[str, ...]:
    """Resolve exact-value scan inputs without placing secret bytes in CLI args or records."""
    names = tuple(raw_names)
    if len(names) != len(set(names)):
        raise DeliveryError("known-secret environment names must be unique", code="INVALID_SECRET_SCAN_INPUT")
    values: list[str] = []
    for name in names:
        if not SECRET_ENV_NAME_RE.fullmatch(name):
            raise DeliveryError("known-secret environment name is invalid", code="INVALID_SECRET_SCAN_INPUT")
        value = os.environ.get(name)
        if not value:
            raise DeliveryError("known-secret environment value is unavailable", code="MISSING_SECRET_SCAN_INPUT")
        values.append(value)
    return tuple(values)


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


def _lexical_relative_parts(root: Path, path: Path) -> tuple[Path, Path, tuple[str, ...]]:
    """Return lexical components without resolving or dereferencing either path."""
    lexical_root = Path(os.path.abspath(root))
    lexical_path = Path(os.path.abspath(path))
    try:
        relative = lexical_path.relative_to(lexical_root)
    except ValueError as exc:
        raise DeliveryError("path escapes its trusted root", code="INVALID_PATH") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise DeliveryError("path must identify a child of its trusted root", code="INVALID_PATH")
    return lexical_root, lexical_path, relative.parts


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _CREATE_NEW = 1
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_BEGIN = 0
    _ERROR_FILE_NOT_FOUND = 2
    _ERROR_PATH_NOT_FOUND = 3
    _ERROR_FILE_EXISTS = 80
    _ERROR_ALREADY_EXISTS = 183

    class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    _KERNEL32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
    ]
    _KERNEL32.GetFileInformationByHandle.restype = wintypes.BOOL
    _KERNEL32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _KERNEL32.ReadFile.restype = wintypes.BOOL
    _KERNEL32.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _KERNEL32.WriteFile.restype = wintypes.BOOL
    _KERNEL32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _KERNEL32.FlushFileBuffers.restype = wintypes.BOOL
    _KERNEL32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    ]
    _KERNEL32.SetFilePointerEx.restype = wintypes.BOOL
    _KERNEL32.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, wintypes.LPVOID]
    _KERNEL32.CreateDirectoryW.restype = wintypes.BOOL


def _windows_error(path: Path) -> OSError:
    error = ctypes.get_last_error()
    return OSError(error, ctypes.FormatError(error), str(path))


def _windows_close(handle: int | None) -> None:
    if handle not in {None, _INVALID_HANDLE_VALUE}:
        _KERNEL32.CloseHandle(handle)


def _windows_open_nofollow(
    path: Path,
    *,
    directory: bool,
    desired_access: int,
    share_mode: int,
    creation: int = 3,
) -> int:
    flags = _FILE_FLAG_OPEN_REPARSE_POINT
    if directory:
        flags |= _FILE_FLAG_BACKUP_SEMANTICS
    handle = _KERNEL32.CreateFileW(
        str(path),
        desired_access,
        share_mode,
        None,
        creation,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        raise _windows_error(path)
    info = _BY_HANDLE_FILE_INFORMATION()
    if not _KERNEL32.GetFileInformationByHandle(handle, ctypes.byref(info)):
        error = _windows_error(path)
        _windows_close(handle)
        raise error
    if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        _windows_close(handle)
        raise DeliveryError("path uses a symlink or reparse point", code="INVALID_PATH")
    is_directory = bool(info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY)
    if is_directory != directory:
        _windows_close(handle)
        code = "ARTIFACT_COLLISION" if directory else "MISSING_ARTIFACT"
        raise DeliveryError("path component has the wrong file type", code=code)
    return handle


def _windows_read_handle(handle: int, path: Path) -> bytes:
    chunks: list[bytes] = []
    buffer = ctypes.create_string_buffer(1024 * 1024)
    while True:
        count = wintypes.DWORD()
        if not _KERNEL32.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
            raise _windows_error(path)
        if count.value == 0:
            return b"".join(chunks)
        chunks.append(buffer.raw[: count.value])


def _windows_write_handle(handle: int, path: Path, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        chunk = value[offset : offset + 1024 * 1024]
        buffer = ctypes.create_string_buffer(chunk, len(chunk))
        count = wintypes.DWORD()
        if not _KERNEL32.WriteFile(handle, buffer, len(chunk), ctypes.byref(count), None):
            raise _windows_error(path)
        if count.value == 0:
            raise OSError("zero-byte write while materializing approved upstream")
        offset += count.value
    if not _KERNEL32.FlushFileBuffers(handle):
        raise _windows_error(path)
    position = ctypes.c_longlong()
    if not _KERNEL32.SetFilePointerEx(handle, 0, ctypes.byref(position), _FILE_BEGIN):
        raise _windows_error(path)


def _stable_read_file(root: Path, path: Path) -> bytes:
    """Read one regular file while every lexical component is held no-follow."""
    lexical_root, lexical_path, parts = _lexical_relative_parts(root, path)
    if os.name == "nt":
        handles: list[int] = []
        current = lexical_root
        try:
            handles.append(
                _windows_open_nofollow(
                    current,
                    directory=True,
                    desired_access=_FILE_READ_ATTRIBUTES,
                    share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
                )
            )
            for part in parts[:-1]:
                current = current / part
                handles.append(
                    _windows_open_nofollow(
                        current,
                        directory=True,
                        desired_access=_FILE_READ_ATTRIBUTES,
                        share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
                    )
                )
            file_handle = _windows_open_nofollow(
                lexical_path,
                directory=False,
                desired_access=_GENERIC_READ,
                share_mode=_FILE_SHARE_READ,
            )
            handles.append(file_handle)
            return _windows_read_handle(file_handle, lexical_path)
        except DeliveryError:
            raise
        except OSError as exc:
            code = "MISSING_ARTIFACT" if (getattr(exc, "winerror", None) or exc.errno) in {
                _ERROR_FILE_NOT_FOUND,
                _ERROR_PATH_NOT_FOUND,
            } else "INVALID_PATH"
            raise DeliveryError(f"cannot safely read artifact: {lexical_path}", code=code) from exc
        finally:
            for handle in reversed(handles):
                _windows_close(handle)

    descriptors: list[int] = []
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        current = os.open(lexical_root, os.O_RDONLY | os.O_DIRECTORY | nofollow)
        descriptors.append(current)
        for part in parts[:-1]:
            current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current)
            descriptors.append(current)
        file_descriptor = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
        descriptors.append(file_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise DeliveryError("artifact is not a regular file", code="MISSING_ARTIFACT")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except DeliveryError:
        raise
    except FileNotFoundError as exc:
        raise DeliveryError(f"artifact does not exist: {lexical_path}", code="MISSING_ARTIFACT") from exc
    except OSError as exc:
        raise DeliveryError(f"cannot safely read artifact: {lexical_path}", code="INVALID_PATH") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _stable_materialize_file(root: Path, relative: str, value: bytes, expected_sha256: str) -> bool:
    """Create or verify an approved file without following a redirected component."""
    normalized = _normalized_repo_path(relative)
    validate_sha256(expected_sha256, "materialized artifact sha256")
    if sha256_bytes(value) != expected_sha256:
        raise DeliveryError(f"approved upstream in-memory bytes drifted: {relative}", code="ARTIFACT_DRIFT")
    lexical_root, lexical_path, parts = _lexical_relative_parts(
        root,
        Path(os.path.abspath(root)) / Path(*normalized.split("/")),
    )
    if os.name == "nt":
        handles: list[int] = []
        current = lexical_root
        file_handle: int | None = None
        created = False
        complete = False
        try:
            handles.append(
                _windows_open_nofollow(
                    current,
                    directory=True,
                    desired_access=_FILE_READ_ATTRIBUTES,
                    share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
                )
            )
            for part in parts[:-1]:
                current = current / part
                try:
                    directory_handle = _windows_open_nofollow(
                        current,
                        directory=True,
                        desired_access=_FILE_READ_ATTRIBUTES,
                        share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
                    )
                except OSError as exc:
                    if (getattr(exc, "winerror", None) or exc.errno) not in {_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND}:
                        raise
                    if not _KERNEL32.CreateDirectoryW(str(current), None):
                        error = ctypes.get_last_error()
                        if error != _ERROR_ALREADY_EXISTS:
                            raise _windows_error(current)
                    directory_handle = _windows_open_nofollow(
                        current,
                        directory=True,
                        desired_access=_FILE_READ_ATTRIBUTES,
                        share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
                    )
                handles.append(directory_handle)
            try:
                file_handle = _windows_open_nofollow(
                    lexical_path,
                    directory=False,
                    desired_access=_GENERIC_READ | _GENERIC_WRITE,
                    share_mode=0,
                    creation=_CREATE_NEW,
                )
                created = True
            except OSError as exc:
                if (getattr(exc, "winerror", None) or exc.errno) not in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
                    raise
                file_handle = _windows_open_nofollow(
                    lexical_path,
                    directory=False,
                    desired_access=_GENERIC_READ,
                    share_mode=_FILE_SHARE_READ,
                )
            handles.append(file_handle)
            if created:
                _windows_write_handle(file_handle, lexical_path, value)
            actual = _windows_read_handle(file_handle, lexical_path)
            if sha256_bytes(actual) != expected_sha256:
                code = "ARTIFACT_DRIFT" if created else "ARTIFACT_COLLISION"
                raise DeliveryError(f"materialized upstream hash differs: {relative}", code=code)
            complete = True
            return created
        except DeliveryError:
            raise
        except OSError as exc:
            raise DeliveryError(f"cannot safely materialize approved upstream: {relative}", code="INVALID_PATH") from exc
        finally:
            if file_handle is not None and handles and handles[-1] == file_handle:
                _windows_close(handles.pop())
            if created and not complete:
                try:
                    lexical_path.unlink()
                except OSError:
                    pass
            for handle in reversed(handles):
                _windows_close(handle)

    descriptors: list[int] = []
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    file_descriptor: int | None = None
    created = False
    complete = False
    try:
        current = os.open(lexical_root, os.O_RDONLY | os.O_DIRECTORY | nofollow)
        descriptors.append(current)
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current)
            except FileNotFoundError:
                os.mkdir(part, dir_fd=current)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=current)
            descriptors.append(child)
            current = child
        try:
            file_descriptor = os.open(
                parts[-1],
                os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
                0o666,
                dir_fd=current,
            )
            created = True
        except FileExistsError:
            file_descriptor = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current)
        descriptors.append(file_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise DeliveryError("approved upstream target is not a regular file", code="ARTIFACT_COLLISION")
        if created:
            offset = 0
            while offset < len(value):
                offset += os.write(file_descriptor, value[offset:])
            os.fsync(file_descriptor)
            os.lseek(file_descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        if sha256_bytes(b"".join(chunks)) != expected_sha256:
            code = "ARTIFACT_DRIFT" if created else "ARTIFACT_COLLISION"
            raise DeliveryError(f"materialized upstream hash differs: {relative}", code=code)
        complete = True
        return created
    except DeliveryError:
        raise
    except OSError as exc:
        raise DeliveryError(f"cannot safely materialize approved upstream: {relative}", code="INVALID_PATH") from exc
    finally:
        if created and not complete and descriptors:
            try:
                os.unlink(parts[-1], dir_fd=descriptors[-2] if len(descriptors) > 1 else descriptors[0])
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)
