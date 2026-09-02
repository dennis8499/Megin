#!/usr/bin/env python3
"""Owner validation and pure helpers for bug-assessment/v1."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "references" / "assessment.schema.json"
SCHEMA_SHA256 = "a61608a17930c5f747bd986f709b54d8d3c6f5e8a3be2b1e591bd6b2094a0134"
BUG_ID_RE = re.compile(r"^(?=.{7,64}$)bug-[a-z0-9]+(?:-[a-z0-9]+)*$")
WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
EVAL_RE = re.compile(r"^## (EVAL-BUG-[0-9]{3})\s+—\s+(.+)$", re.MULTILINE)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:secret|token|password|passwd|credential|api[-_.]?key|private[-_.]?key)[\"']?\s*[:=]\s*[\"']?\S{6,}"
)
SECRET_SENTINEL_RE = re.compile(
    r"\b(?:[A-Z0-9]+_)*(?:SECRET|TOKEN|PASSWORD|CREDENTIAL|API_KEY|PRIVATE_KEY)_[A-Z0-9_-]{6,}\b"
)
KNOWN_TOKEN_RE = re.compile(
    r"(?:\bAKIA[0-9A-Z]{16}\b|\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b)"
)
REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/diagnosis-loop.md",
    "references/assessment-contract.md",
    "references/assessment-template.md",
    "references/assessment.schema.json",
    "references/behavior-evaluation.md",
    "scripts/test_validate_contracts.py",
    "scripts/behavior-evaluation-report.md",
}


class _UnsafeAssessmentPath(OSError):
    pass


class _DuplicateAssessmentKey(ValueError):
    pass


def _reject_duplicate_assessment_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateAssessmentKey("duplicate JSON object key")
        value[key] = item
    return value


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _GENERIC_READ = 0x80000000
    _FILE_READ_ATTRIBUTES = 0x0080
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

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


def _stable_assessment_read(repository_root: Path, path: Path) -> bytes:
    """Read a regular file while holding every lexical component no-follow."""
    root = Path(os.path.abspath(repository_root))
    candidate = Path(os.path.abspath(path))
    try:
        parts = candidate.relative_to(root).parts
    except ValueError as exc:
        raise _UnsafeAssessmentPath("path escapes repository") from exc
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise _UnsafeAssessmentPath("path is not a repository child")

    if os.name == "nt":
        handles: list[int] = []
        current = root

        def open_component(component: Path, *, directory: bool) -> int:
            flags = _FILE_FLAG_OPEN_REPARSE_POINT
            if directory:
                flags |= _FILE_FLAG_BACKUP_SEMANTICS
            handle = _KERNEL32.CreateFileW(
                str(component),
                _FILE_READ_ATTRIBUTES if directory else _GENERIC_READ,
                (_FILE_SHARE_READ | _FILE_SHARE_WRITE) if directory else _FILE_SHARE_READ,
                None,
                _OPEN_EXISTING,
                flags,
                None,
            )
            if handle == _INVALID_HANDLE_VALUE:
                error = ctypes.get_last_error()
                raise OSError(error, ctypes.FormatError(error), str(component))
            info = _BY_HANDLE_FILE_INFORMATION()
            if not _KERNEL32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                error = ctypes.get_last_error()
                _KERNEL32.CloseHandle(handle)
                raise OSError(error, ctypes.FormatError(error), str(component))
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                _KERNEL32.CloseHandle(handle)
                raise _UnsafeAssessmentPath("path uses a symlink or reparse point")
            if bool(info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY) != directory:
                _KERNEL32.CloseHandle(handle)
                raise OSError("path component has the wrong file type")
            return handle

        try:
            handles.append(open_component(current, directory=True))
            for part in parts[:-1]:
                current = current / part
                handles.append(open_component(current, directory=True))
            file_handle = open_component(candidate, directory=False)
            handles.append(file_handle)
            chunks: list[bytes] = []
            buffer = ctypes.create_string_buffer(1024 * 1024)
            while True:
                count = wintypes.DWORD()
                if not _KERNEL32.ReadFile(file_handle, buffer, len(buffer), ctypes.byref(count), None):
                    error = ctypes.get_last_error()
                    raise OSError(error, ctypes.FormatError(error), str(candidate))
                if count.value == 0:
                    return b"".join(chunks)
                chunks.append(buffer.raw[: count.value])
        finally:
            for handle in reversed(handles):
                _KERNEL32.CloseHandle(handle)

    descriptors: list[int] = []
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        current_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | nofollow)
        descriptors.append(current_descriptor)
        for part in parts[:-1]:
            current_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | nofollow,
                dir_fd=current_descriptor,
            )
            descriptors.append(current_descriptor)
        file_descriptor = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current_descriptor)
        descriptors.append(file_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise OSError("assessment path is not a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    except OSError as exc:
        if getattr(exc, "errno", None) in {errno.ELOOP, errno.ENOTDIR}:
            raise _UnsafeAssessmentPath("path uses a symlink or reparse point") from exc
        raise
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pointer(document: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise KeyError(f"unsupported non-local ref: {ref}")
    node = document
    for raw in ref[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def validate_instance(instance: Any, schema: dict[str, Any], definition: str | None = None) -> list[str]:
    """Validate the JSON Schema subset used by the BUG contract without dependencies."""
    root = schema
    node = schema["$defs"][definition] if definition else schema
    errors: list[str] = []

    def check(value: Any, rule: dict[str, Any], location: str) -> None:
        if "$ref" in rule:
            try:
                check(value, _pointer(root, rule["$ref"]), location)
            except KeyError as exc:
                errors.append(f"{location}: {exc}")
            return

        for child in rule.get("allOf", []):
            check(value, child, location)

        for keyword in ("anyOf", "oneOf"):
            if keyword not in rule:
                continue
            matches = 0
            for child in rule[keyword]:
                before = len(errors)
                check(value, child, location)
                branch_errors = errors[before:]
                del errors[before:]
                if not branch_errors:
                    matches += 1
            if matches == 0 or (keyword == "oneOf" and matches != 1):
                errors.append(f"{location}: {keyword} matched {matches} branches")

        if "if" in rule:
            before = len(errors)
            check(value, rule["if"], location)
            condition_matches = len(errors) == before
            del errors[before:]
            branch = rule.get("then" if condition_matches else "else")
            if branch:
                check(value, branch, location)

        if "const" in rule and value != rule["const"]:
            errors.append(f"{location}: expected const {rule['const']!r}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"{location}: value {value!r} is outside enum")

        expected_types = rule.get("type")
        if expected_types:
            choices = [expected_types] if isinstance(expected_types, str) else expected_types
            if not any(_type_matches(value, choice) for choice in choices):
                errors.append(f"{location}: expected type {choices}, got {type(value).__name__}")
                return

        if isinstance(value, dict):
            for name in rule.get("required", []):
                if name not in value:
                    errors.append(f"{location}: missing required property {name}")
            properties = rule.get("properties", {})
            if rule.get("additionalProperties") is False:
                for name in value.keys() - properties.keys():
                    errors.append(f"{location}: unexpected property {name}")
            for name, child in value.items():
                child_rule = properties.get(name)
                if child_rule:
                    check(child, child_rule, f"{location}.{name}")

        if isinstance(value, list):
            if len(value) < rule.get("minItems", 0):
                errors.append(f"{location}: too few items")
            if "maxItems" in rule and len(value) > rule["maxItems"]:
                errors.append(f"{location}: too many items")
            if rule.get("uniqueItems"):
                encoded = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
                if len(encoded) != len(set(encoded)):
                    errors.append(f"{location}: duplicate items")
            if "items" in rule:
                for index, child in enumerate(value):
                    check(child, rule["items"], f"{location}[{index}]")

        if isinstance(value, str):
            if len(value) < rule.get("minLength", 0):
                errors.append(f"{location}: string is too short")
            if "pattern" in rule and not re.search(rule["pattern"], value):
                errors.append(f"{location}: does not match {rule['pattern']}")
            if rule.get("format") == "date-time":
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        raise ValueError("timezone missing")
                except ValueError:
                    errors.append(f"{location}: invalid RFC 3339 date-time")

        if isinstance(value, int) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                errors.append(f"{location}: below minimum {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                errors.append(f"{location}: above maximum {rule['maximum']}")

    check(instance, node, definition or "$")
    return errors


def expected_paths(bug_id: str, revision: int) -> tuple[str, str]:
    root = f"docs/bugs/{bug_id}"
    return f"{root}/assessment-{revision}.md", f"{root}/assessment-{revision}.json"


def _secret_errors(values: Iterable[str], payloads: Iterable[tuple[str, bytes]]) -> list[str]:
    errors: list[str] = []
    materialized = list(payloads)
    for secret in values:
        if not secret:
            continue
        encoded = secret.encode("utf-8")
        for label, payload in materialized:
            if encoded in payload:
                errors.append(f"secret value appears in {label}")
    for label, payload in materialized:
        text = payload.decode("utf-8", errors="replace")
        if (
            SECRET_ASSIGNMENT_RE.search(text)
            or SECRET_SENTINEL_RE.search(text)
            or KNOWN_TOKEN_RE.search(text)
        ):
            errors.append(f"credential-shaped material appears in {label}")
    return errors


def validate_assessment(
    data: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
    repository_root: Path | None = None,
    sidecar_path: Path | None = None,
    sidecar_bytes: bytes | None = None,
    known_secret_values: Sequence[str] = (),
) -> list[str]:
    """Validate shape, semantics and optional on-disk path/hash binding."""
    schema = schema or _json(SCHEMA_PATH)
    errors = validate_instance(data, schema)
    if errors:
        return errors

    bug_id = data["bug_id"]
    revision = data["revision"]
    markdown_relative, sidecar_relative = expected_paths(bug_id, revision)
    if data["markdown"]["path"] != markdown_relative:
        errors.append("assessment Markdown path does not match bug_id and revision")

    hypotheses = data["hypotheses"]
    ids = [item["hypothesis_id"] for item in hypotheses]
    ranks = [item["rank"] for item in hypotheses]
    if len(ids) != len(set(ids)):
        errors.append("hypothesis IDs must be unique")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        errors.append("hypothesis ranks must be contiguous from 1")
    testing = [item["hypothesis_id"] for item in hypotheses if item["outcome"] == "testing"]
    active = data["active_hypothesis_id"]
    if len(testing) > 1:
        errors.append("only one hypothesis may be testing")
    if testing and active != testing[0]:
        errors.append("active_hypothesis_id must identify the testing hypothesis")
    if not testing and active is not None:
        errors.append("active_hypothesis_id must be null when no hypothesis is testing")

    verdict = data["verdict"]
    disposition = data["disposition"]
    verdict_dispositions = {
        "confirmed": {"delivery", "current-run", "upstream-reapproval", "deferred-inbox"},
        "likely": {"delivery", "current-run", "upstream-reapproval", "deferred-inbox"},
        "not-a-bug": {"standard-feature", "closed"},
        "insufficient-evidence": {"blocked", "deferred-inbox", "upstream-reapproval"},
    }
    if disposition not in verdict_dispositions[verdict]:
        errors.append("verdict and disposition are incompatible")

    relation = data["source"]["relation"]
    relation_dispositions = {
        "intake": {"delivery", "standard-feature", "closed", "blocked", "deferred-inbox"},
        "current-scope": {"current-run"},
        "affecting-current-work": {"upstream-reapproval"},
        "unrelated": {"deferred-inbox"},
    }
    if disposition not in relation_dispositions[relation]:
        errors.append("relation and disposition are incompatible")
    if relation == "intake" and data["source"]["work_id"] is not None:
        errors.append("intake assessment must not claim a source work")
    if relation != "intake" and data["source"]["work_id"] is None:
        errors.append("in-flight assessment requires source work_id")

    risk = data["risk"]
    if risk["security_privacy_or_data_risk"]:
        if not risk["redacted_summary"] or not risk["secure_evidence_refs"] or not risk["human_reviewer"]:
            errors.append("sensitive assessment requires redacted summary, secure refs and named reviewer")
    elif risk["secure_evidence_refs"] or risk["human_reviewer"] is not None:
        errors.append("non-sensitive assessment must not claim secure refs or human risk reviewer")

    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payloads: list[tuple[str, bytes]] = [("assessment JSON", canonical)]
    raw_sidecar = sidecar_bytes
    if repository_root is not None:
        lexical_root = Path(os.path.abspath(repository_root))
        markdown_path = lexical_root / Path(*markdown_relative.split("/"))
        if _has_reparse_component(markdown_path, lexical_root):
            errors.append("assessment Markdown path uses a symlink or reparse point")
        else:
            try:
                markdown_bytes = _stable_assessment_read(lexical_root, markdown_path)
            except _UnsafeAssessmentPath:
                errors.append("assessment Markdown path uses a symlink or reparse point")
            except OSError:
                errors.append("assessment Markdown file is missing or unreadable")
            else:
                payloads.append(("assessment Markdown", markdown_bytes))
                if sha256_bytes(markdown_bytes) != data["markdown"]["sha256"]:
                    errors.append("assessment Markdown hash mismatch")
        if sidecar_path is not None:
            lexical_sidecar = Path(os.path.abspath(sidecar_path))
            try:
                relative = lexical_sidecar.relative_to(lexical_root).as_posix()
            except ValueError:
                errors.append("assessment sidecar is outside repository")
            else:
                if relative != sidecar_relative:
                    errors.append("assessment sidecar path does not match bug_id and revision")
                if _has_reparse_component(lexical_sidecar, lexical_root):
                    errors.append("assessment sidecar path uses a symlink or reparse point")
                elif raw_sidecar is None:
                    try:
                        raw_sidecar = _stable_assessment_read(lexical_root, lexical_sidecar)
                    except FileNotFoundError:
                        # A prospective create-only assessment may not exist yet.
                        pass
                    except _UnsafeAssessmentPath:
                        errors.append("assessment sidecar path uses a symlink or reparse point")
                    except OSError:
                        errors.append("assessment sidecar is unreadable")
        if not any("symlink or reparse point" in error for error in errors):
            smallest = _smallest_available_revision(lexical_root, bug_id)
            if smallest < revision:
                errors.append(
                    f"assessment revision is not the smallest available positive integer; use {smallest}"
                )

    if raw_sidecar is not None:
        payloads.append(("assessment JSON raw bytes", raw_sidecar))
        try:
            decoded_sidecar = raw_sidecar.decode("utf-8")
            persisted = json.loads(
                decoded_sidecar,
                object_pairs_hook=_reject_duplicate_assessment_keys,
            )
        except _DuplicateAssessmentKey:
            errors.append("assessment sidecar contains a duplicate JSON object key")
        except (UnicodeError, json.JSONDecodeError):
            errors.append("assessment sidecar is not valid UTF-8 JSON")
        else:
            if not isinstance(persisted, dict):
                errors.append("assessment sidecar is not a JSON object")
            elif persisted != data:
                errors.append("assessment sidecar content differs from supplied assessment")

    errors.extend(_secret_errors(known_secret_values, payloads))
    return errors


def _is_reparse_path(path: Path) -> bool:
    """Inspect one lexical component without following its redirect target."""
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return os.name == "nt" and bool(attributes & 0x400)


def _has_reparse_component(path: Path, root: Path) -> bool:
    root_lexical = Path(os.path.abspath(root))
    path_lexical = Path(os.path.abspath(path))
    if _is_reparse_path(root_lexical):
        return True
    try:
        relative = path_lexical.relative_to(root_lexical)
    except ValueError:
        return True
    current = root_lexical
    for part in relative.parts:
        current = current / part
        if _is_reparse_path(current):
            return True
    try:
        path_lexical.resolve(strict=False).relative_to(root_lexical.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return True
    return False


def _topic_tokens(topic: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", topic).casefold().strip()
    tokens = re.findall(r"[a-z0-9]+", normalized)[:5]
    if not tokens:
        tokens = ["topic", hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]]
    elif len(tokens) == 1:
        tokens.append("issue")
    return tokens


def allocate_bug_id(repository_root: Path, topic: str, requested_id: str | None = None) -> str:
    """Read-only deterministic allocation; the writer must still create atomically."""
    bugs_root = repository_root / "docs" / "bugs"
    if requested_id and BUG_ID_RE.fullmatch(requested_id):
        stem = requested_id
    else:
        normalized = unicodedata.normalize("NFKC", topic).casefold().strip()
        tokens = _topic_tokens(topic)
        slug = "-".join(tokens)
        if len(slug) > 60:
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
            head = "-".join(tokens[:4])[:49].rstrip("-") or "topic"
            slug = f"{head}-{digest}"
        stem = f"bug-{slug}"
    candidate = stem
    suffix = 2
    while os.path.lexists(bugs_root / candidate):
        tail = f"-{suffix}"
        candidate = f"{stem[:64 - len(tail)].rstrip('-')}{tail}"
        suffix += 1
    return candidate


def _smallest_available_revision(repository_root: Path, bug_id: str) -> int:
    revision = 1
    while True:
        markdown, sidecar = expected_paths(bug_id, revision)
        if not any(
            os.path.lexists(repository_root / Path(*relative.split("/")))
            for relative in (markdown, sidecar)
        ):
            return revision
        revision += 1


def create_only_errors(repository_root: Path, bug_id: str, revision: int, work_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if not BUG_ID_RE.fullmatch(bug_id):
        return ["invalid bug_id"]
    markdown, sidecar = expected_paths(bug_id, revision)
    targets = [repository_root / Path(*markdown.split("/")), repository_root / Path(*sidecar.split("/"))]
    if work_id is not None:
        if not WORK_ID_RE.fullmatch(work_id):
            errors.append("invalid work_id")
        targets.append(repository_root / "docs" / "bugs" / bug_id / "verifications" / f"{work_id}.json")
    for target in targets:
        if os.path.lexists(target):
            errors.append(f"create-only target already exists: {target.relative_to(repository_root).as_posix()}")
        if _has_reparse_component(target.parent, repository_root):
            errors.append(f"target parent uses a symlink or reparse point: {target.parent}")
    if not any("symlink or reparse point" in error for error in errors):
        smallest = _smallest_available_revision(repository_root, bug_id)
        if revision != smallest:
            errors.append(
                f"assessment revision is not the smallest available positive integer; use {smallest}"
            )
    return errors


def list_scenarios() -> list[tuple[str, str]]:
    text = (SKILL_ROOT / "references" / "behavior-evaluation.md").read_text(encoding="utf-8")
    return EVAL_RE.findall(text)


def validate_owner_bundle() -> list[str]:
    errors: list[str] = []
    actual_files = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
    }
    missing = sorted(REQUIRED_FILES - actual_files)
    if missing:
        errors.append(f"missing owned files: {missing}")
    schema_bytes = SCHEMA_PATH.read_bytes() if SCHEMA_PATH.is_file() else b""
    if sha256_bytes(schema_bytes) != SCHEMA_SHA256:
        errors.append("assessment schema bytes changed without updating owner contract")
    try:
        schema = json.loads(schema_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"assessment schema is not valid UTF-8 JSON: {exc}")
        schema = {}
    if schema.get("$id") != "https://local.skills/bug-diagnosis/assessment.schema.json":
        errors.append("assessment schema $id drift")
    if schema.get("properties", {}).get("schema", {}).get("const") != "bug-assessment/v1":
        errors.append("assessment schema discriminator drift")
    required = set(schema.get("required", []))
    for field in {"bug_id", "revision", "markdown", "verdict", "reproduction", "root_cause", "hypotheses", "risk", "disposition"}:
        if field not in required:
            errors.append(f"assessment schema no longer requires {field}")

    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8") if (SKILL_ROOT / "SKILL.md").is_file() else ""
    for anchor in [
        "只診斷，不修改",
        "預期中的 BDD／TDD red",
        "3–5",
        "每次 probe 只改一個變因",
        "not-a-bug",
        "current-scope",
        "affecting-current-work",
        "unrelated",
        "不得說「已修復」",
    ]:
        if anchor not in skill:
            errors.append(f"SKILL.md missing behavior anchor: {anchor}")
    config = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8") if (SKILL_ROOT / "agents" / "openai.yaml").is_file() else ""
    if "allow_implicit_invocation: true" not in config or "$bug-diagnosis" not in config:
        errors.append("agents/openai.yaml does not enable implicit invocation with a valid default prompt")
    assessment_contract = (SKILL_ROOT / "references" / "assessment-contract.md").read_text(encoding="utf-8")
    for anchor in ("raw JSON bytes", "duplicate JSON object key", "last-key-wins"):
        if anchor not in assessment_contract:
            errors.append(f"assessment contract missing raw-byte safety anchor: {anchor}")
    validator_source = (SKILL_ROOT / "scripts" / "validate_contracts.py").read_text(encoding="utf-8")
    for anchor in ("sidecar_bytes", "_reject_duplicate_assessment_keys", "assessment JSON raw bytes"):
        if anchor not in validator_source:
            errors.append(f"assessment validator missing raw-byte safety primitive: {anchor}")
    scenarios = list_scenarios() if (SKILL_ROOT / "references" / "behavior-evaluation.md").is_file() else []
    if [item[0] for item in scenarios] != [f"EVAL-BUG-{index:03d}" for index in range(1, 9)]:
        errors.append("forward evaluation inventory must contain contiguous EVAL-BUG-001..008")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args(argv)
    if args.list_scenarios:
        for scenario_id, title in list_scenarios():
            print(f"{scenario_id}\t{title}")
        return 0
    errors = validate_owner_bundle()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("BUG DIAGNOSIS CONTRACTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
