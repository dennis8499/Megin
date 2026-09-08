#!/usr/bin/env python3
"""Plan local validation executions and persist verifiable evidence bundles."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import statistics
import subprocess
import tempfile
import sys
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


Executor = Callable[[dict[str, Any]], dict[str, Any]]
REQUIRED_PRECHECK_CHECKS = (
    "source_requirement_coverage",
    "diff_manifest",
    "test_oracles",
    "ready_evidence",
    "snapshot",
    "environment",
)


class EvidenceError(ValueError):
    """A persisted validation artifact cannot safely support a decision."""

    exit_code = 3


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_redirect(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return os.name == "nt" and bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _safe_relative(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvidenceError("evidence path is not a normalized relative path")
    candidate = Path(value)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise EvidenceError("evidence path escapes its bundle")
    return candidate


def _safe_regular_file(root: Path, relative: object) -> Path:
    lexical = root / _safe_relative(relative)
    current = lexical
    while True:
        if _is_redirect(current):
            raise EvidenceError(f"evidence path is redirected: {relative}")
        if current == root:
            break
        if current.parent == current:
            raise EvidenceError(f"evidence path escapes its bundle: {relative}")
        current = current.parent
    if not lexical.is_file() or not stat.S_ISREG(lexical.lstat().st_mode):
        raise EvidenceError(f"evidence file is missing or irregular: {relative}")
    return lexical


def _stream_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if value is None:
        return b""
    raise TypeError("stdout and stderr must be bytes or strings")


def _write_bytes(path: Path, value: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    return {"sha256": _sha_bytes(value), "bytes": len(value)}


def _write_json_create(path: Path, value: object) -> None:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode(
        "utf-8"
    ) + b"\n"
    _write_bytes(path, raw)


def _logical_command_summary(
    commands: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for command in commands:
        logical_id = command.get("logical_command_id", command.get("command_id"))
        if not isinstance(logical_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", logical_id
        ):
            raise EvidenceError("validation command has an unsafe logical ID")
        grouped.setdefault(logical_id, []).append(command)

    summaries: list[dict[str, Any]] = []
    for logical_id in sorted(grouped):
        physical = grouped[logical_id]
        statuses = {item.get("status") for item in physical}
        if statuses == {"passed"} and all(
            item.get("exit_code") == 0
            and item.get("inventory_complete") is True
            for item in physical
        ):
            status = "passed"
        elif "failed" in statuses:
            status = "failed"
        elif "timeout" in statuses:
            status = "timeout"
        else:
            status = "not_run"
        summaries.append(
            {
                "logical_command_id": logical_id,
                "status": status,
                "physical_command_ids": sorted(
                    str(item["command_id"]) for item in physical
                ),
            }
        )
    return summaries


def write_bundle(
    evidence_root: Path,
    label: str,
    *,
    profile: str,
    execution_input: dict[str, Any],
    environment: dict[str, Any],
    ready_payload_sha256: str,
    executions: Iterable[dict[str, Any]],
    wall_duration_seconds: float | None = None,
) -> Path:
    """Write a create-only validation-evidence/v1 directory via sibling rename."""

    root = Path(evidence_root)
    if not root.is_dir() or _is_redirect(root):
        raise EvidenceError("evidence root must be an existing regular directory")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise EvidenceError("bundle label is unsafe")
    if profile not in {"local", "release"}:
        raise EvidenceError("validation profile must be local or release")
    if not re.fullmatch(r"[a-f0-9]{64}", ready_payload_sha256):
        raise EvidenceError("Ready payload digest is invalid")
    bound_ready = execution_input.get("ready_payload_sha256")
    if bound_ready is not None and bound_ready != ready_payload_sha256:
        raise EvidenceError("execution input and evidence bind different Ready payloads")
    target = root / label
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    staging = Path(tempfile.mkdtemp(prefix=f".{label}.staging-", dir=root))
    try:
        command_entries: list[dict[str, Any]] = []
        counts = {value: 0 for value in ("passed", "failed", "timeout", "not_run")}
        for index, execution in enumerate(executions, 1):
            command_id = str(execution.get("command_id", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", command_id):
                raise EvidenceError(f"unsafe command ID: {command_id}")
            status = execution.get("status")
            if status not in counts:
                raise EvidenceError(f"unknown command status: {status}")
            counts[status] += 1
            stem = f"{index:03d}-{command_id}"
            stdout_relative = Path("outputs") / f"{stem}.stdout.txt"
            stderr_relative = Path("outputs") / f"{stem}.stderr.txt"
            stdout_value = _stream_bytes(execution.get("stdout"))
            stderr_value = _stream_bytes(execution.get("stderr"))
            stdout_meta = _write_bytes(staging / stdout_relative, stdout_value)
            stderr_meta = _write_bytes(staging / stderr_relative, stderr_value)
            fixture_profile = execution.get("fixture_profile")
            profile_entry: dict[str, Any] | None = None
            if fixture_profile is not None:
                if not isinstance(fixture_profile, dict) or fixture_profile.get("schema") != "delivery-fixture-profile/v1":
                    raise EvidenceError("Delivery fixture profile is invalid")
                profile_relative = Path("profiles") / f"{stem}.json"
                profile_raw = json.dumps(
                    fixture_profile,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                ).encode("utf-8") + b"\n"
                profile_entry = {
                    "path": profile_relative.as_posix(),
                    **_write_bytes(staging / profile_relative, profile_raw),
                }
            command_entries.append(
                {
                    "command_id": command_id,
                    "logical_command_id": execution.get(
                        "logical_command_id", command_id
                    ),
                    "execution_class": execution.get("execution_class"),
                    "status": status,
                    "exit_code": execution.get("exit_code"),
                    "duration_seconds": execution.get("duration_seconds"),
                    "failure_count": execution.get("failure_count"),
                    "skipped_count": execution.get("skipped_count"),
                    "inventory_complete": execution.get("inventory_complete") is True,
                    "children": execution.get("children", []),
                    "not_run_reason": execution.get("not_run_reason"),
                    "worker_id": execution.get("worker_id"),
                    "worker_cleanup": execution.get("worker_cleanup"),
                    "fixture_profile": profile_entry,
                    "stdout": {
                        "path": stdout_relative.as_posix(),
                        **stdout_meta,
                    },
                    "stderr": {
                        "path": stderr_relative.as_posix(),
                        **stderr_meta,
                    },
                }
            )
        index_value = {
            "schema": "validation-evidence/v1",
            "profile": profile,
            "execution_input": execution_input,
            "execution_input_identity": canonical_sha256(execution_input),
            "environment": environment,
            "environment_identity": canonical_sha256(environment),
            "ready_payload_sha256": ready_payload_sha256,
            "commands": command_entries,
            "summary": {
                "counts": counts,
                "logical_commands": _logical_command_summary(command_entries),
                "total_duration_seconds": round(
                    sum(
                        float(item.get("duration_seconds") or 0.0)
                        for item in command_entries
                    ),
                    6,
                ),
            },
        }
        if wall_duration_seconds is not None:
            if not isinstance(wall_duration_seconds, (int, float)) or wall_duration_seconds <= 0:
                raise EvidenceError("wall duration must be positive")
            index_value["summary"]["wall_duration_seconds"] = round(
                float(wall_duration_seconds), 6
            )
        _write_json_create(staging / "index.json", index_value)
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def verify_bundle(index_path: Path) -> dict[str, Any]:
    """Verify every indexed byte and reject missing, redirected, or partial bundles."""

    index = Path(index_path)
    if _is_redirect(index):
        raise EvidenceError("validation index is redirected")
    root = index.parent
    if index.name != "index.json" or _is_redirect(root):
        raise EvidenceError("validation index location is not canonical")
    if not index.is_file() or not stat.S_ISREG(index.lstat().st_mode):
        raise EvidenceError("validation index is missing or irregular")
    try:
        value = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("validation index is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema") != "validation-evidence/v1":
        raise EvidenceError("validation index schema is invalid")
    if value.get("profile") not in {"local", "release"}:
        raise EvidenceError("validation profile is invalid")
    if not isinstance(value.get("environment"), dict):
        raise EvidenceError("validation environment is invalid")
    ready_payload_sha256 = value.get("ready_payload_sha256")
    if not isinstance(ready_payload_sha256, str) or re.fullmatch(
        r"[a-f0-9]{64}", ready_payload_sha256
    ) is None:
        raise EvidenceError("Ready payload digest is invalid")
    if value.get("execution_input_identity") != canonical_sha256(
        value.get("execution_input")
    ):
        raise EvidenceError("execution input identity drifted")
    if value.get("environment_identity") != canonical_sha256(value.get("environment")):
        raise EvidenceError("environment identity drifted")
    counts = {status: 0 for status in ("passed", "failed", "timeout", "not_run")}
    command_ids: set[str] = set()
    commands = value.get("commands")
    if not isinstance(commands, list) or not commands:
        raise EvidenceError("validation command inventory is missing")
    execution_input = value.get("execution_input")
    if not isinstance(execution_input, dict):
        raise EvidenceError("validation execution input is invalid")
    if (
        execution_input.get("ready_payload_sha256") is not None
        and execution_input.get("ready_payload_sha256") != ready_payload_sha256
    ):
        raise EvidenceError("execution input and evidence Ready bindings differ")
    expected_commands = execution_input.get("commands")
    expected_by_id: dict[str, dict[str, Any]] = {}
    if expected_commands is not None:
        if not isinstance(expected_commands, list):
            raise EvidenceError("execution input command inventory is invalid")
        expected_ids: set[str] = set()
        for item in expected_commands:
            if isinstance(item, str):
                expected_id = item
            elif isinstance(item, dict):
                expected_id = item.get("command_id")
                if isinstance(expected_id, str):
                    expected_by_id[expected_id] = item
            else:
                raise EvidenceError("execution input command entry is invalid")
            if not isinstance(expected_id, str) or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]*", expected_id
            ) is None:
                raise EvidenceError("execution input command ID is invalid")
            if expected_id in expected_ids:
                raise EvidenceError("execution input repeats a command ID")
            expected_ids.add(expected_id)
        result_ids = {
            item.get("command_id") for item in commands if isinstance(item, dict)
        }
        if expected_ids != result_ids:
            raise EvidenceError("execution input and result command inventories differ")
    for command in commands:
        if not isinstance(command, dict):
            raise EvidenceError("validation command entry is invalid")
        command_id = command.get("command_id")
        if not isinstance(command_id, str) or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*", command_id
        ) is None:
            raise EvidenceError("validation command ID is invalid")
        if command_id in command_ids:
            raise EvidenceError("validation index repeats a command ID")
        command_ids.add(command_id)
        expected_command = expected_by_id.get(command_id)
        if expected_command is not None:
            for result_field, input_field in (
                ("logical_command_id", "logical_command_id"),
                ("execution_class", "execution_class"),
            ):
                if command.get(result_field) != expected_command.get(input_field):
                    raise EvidenceError(
                        f"validation command {result_field} differs from execution input"
                    )
        status = command.get("status")
        if status not in counts:
            raise EvidenceError("validation index has an unknown command status")
        counts[status] += 1
        duration = command.get("duration_seconds")
        if status == "not_run":
            if duration is not None:
                raise EvidenceError("not_run command cannot have a duration")
        elif not isinstance(duration, (int, float)) or duration < 0:
            raise EvidenceError("executed command duration is invalid")
        children = command.get("children")
        if not isinstance(children, list):
            raise EvidenceError("validation child inventory is invalid")
        child_ids: set[str] = set()
        for child in children:
            if not isinstance(child, dict):
                raise EvidenceError("validation child entry is invalid")
            child_id = child.get("command_id")
            if not isinstance(child_id, str) or not child_id or child_id in child_ids:
                raise EvidenceError("validation child inventory repeats or omits an ID")
            child_ids.add(child_id)
            if child.get("status") not in {"passed", "failed", "timeout", "not_run"}:
                raise EvidenceError("validation child status is invalid")
        for stream_name in ("stdout", "stderr"):
            metadata = command.get(stream_name, {})
            path = _safe_regular_file(root, metadata.get("path"))
            raw = path.read_bytes()
            if metadata.get("sha256") != _sha_bytes(raw) or metadata.get("bytes") != len(raw):
                raise EvidenceError(
                    f"validation {stream_name} bytes drifted for {command_id}"
                )
        profile_metadata = command.get("fixture_profile")
        if profile_metadata is not None:
            if not isinstance(profile_metadata, dict):
                raise EvidenceError("validation fixture profile metadata is invalid")
            profile_path = _safe_regular_file(root, profile_metadata.get("path"))
            profile_raw = profile_path.read_bytes()
            if (
                profile_metadata.get("sha256") != _sha_bytes(profile_raw)
                or profile_metadata.get("bytes") != len(profile_raw)
            ):
                raise EvidenceError("validation fixture profile bytes drifted")
            try:
                profile_value = json.loads(profile_raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise EvidenceError("validation fixture profile is unreadable") from exc
            if (
                not isinstance(profile_value, dict)
                or profile_value.get("schema") != "delivery-fixture-profile/v1"
            ):
                raise EvidenceError("validation fixture profile schema is invalid")
        if status == "passed" and (
            command.get("exit_code") != 0
            or command.get("inventory_complete") is not True
            or command.get("failure_count") not in {None, 0}
            or command.get("skipped_count") not in {None, 0}
            or any(child.get("status") != "passed" for child in children)
        ):
            raise EvidenceError("passed command lacks complete successful inventory")
        if status in {"timeout", "not_run"} and command.get("exit_code") is not None:
            raise EvidenceError(f"{status} command cannot have an exit code")
    if value.get("summary", {}).get("counts") != counts:
        raise EvidenceError("validation summary counts differ from command inventory")
    if value.get("summary", {}).get("logical_commands") != _logical_command_summary(
        commands
    ):
        raise EvidenceError("validation logical command coverage drifted")
    expected_total = round(
        sum(float(item.get("duration_seconds") or 0.0) for item in commands), 6
    )
    if value.get("summary", {}).get("total_duration_seconds") != expected_total:
        raise EvidenceError("validation total duration differs from command inventory")
    wall_duration = value.get("summary", {}).get("wall_duration_seconds")
    if wall_duration is not None and (
        not isinstance(wall_duration, (int, float)) or wall_duration <= 0
    ):
        raise EvidenceError("validation wall duration is invalid")
    return value


def make_reference(index_path: Path, command_id: str) -> dict[str, Any]:
    index = Path(index_path).resolve()
    value = verify_bundle(index)
    command = next(
        (item for item in value["commands"] if item["command_id"] == command_id),
        None,
    )
    if command is None:
        raise EvidenceError(f"producer command is absent: {command_id}")
    if command.get("status") != "passed" or command.get("exit_code") != 0:
        raise EvidenceError("only a complete passed command can be referenced")
    return {
        "schema": "validation-reference/v1",
        "producer_index": str(index),
        "producer_index_sha256": _sha_bytes(index.read_bytes()),
        "producer_command_id": command_id,
        "producer_command_sha256": canonical_sha256(command),
        "execution_input_identity": value["execution_input_identity"],
        "environment_identity": value["environment_identity"],
        "ready_payload_sha256": value["ready_payload_sha256"],
        "stdout_sha256": command["stdout"]["sha256"],
        "stderr_sha256": command["stderr"]["sha256"],
    }


def verify_reference(
    reference: dict[str, Any],
    *,
    expected_execution_input_identity: str | None = None,
    expected_environment_identity: str | None = None,
    expected_ready_payload_sha256: str | None = None,
) -> dict[str, Any]:
    if reference.get("schema") != "validation-reference/v1":
        raise EvidenceError("validation reference schema is invalid")
    index = Path(str(reference.get("producer_index", "")))
    if not index.is_absolute() or _is_redirect(index):
        raise EvidenceError("producer index path is invalid or redirected")
    if not index.is_file() or reference.get("producer_index_sha256") != _sha_bytes(
        index.read_bytes()
    ):
        raise EvidenceError("producer index is missing or drifted")
    value = verify_bundle(index)
    command = next(
        (
            item
            for item in value["commands"]
            if item["command_id"] == reference.get("producer_command_id")
        ),
        None,
    )
    if command is None or command.get("status") != "passed":
        raise EvidenceError("referenced producer did not pass")
    expected = {
        "producer_command_sha256": canonical_sha256(command),
        "execution_input_identity": value["execution_input_identity"],
        "environment_identity": value["environment_identity"],
        "ready_payload_sha256": value["ready_payload_sha256"],
        "stdout_sha256": command["stdout"]["sha256"],
        "stderr_sha256": command["stderr"]["sha256"],
    }
    for field, expected_value in expected.items():
        if reference.get(field) != expected_value:
            raise EvidenceError(f"validation reference drifted: {field}")
    requested = {
        "execution_input_identity": expected_execution_input_identity,
        "environment_identity": expected_environment_identity,
        "ready_payload_sha256": expected_ready_payload_sha256,
    }
    for field, expected_value in requested.items():
        if expected_value is not None and reference.get(field) != expected_value:
            raise EvidenceError(f"validation reference identity mismatch: {field}")
    return {
        "schema": "validation-reference-verification/v1",
        "outcome": "verified",
        "producer_command_id": reference["producer_command_id"],
        "producer_index_sha256": reference["producer_index_sha256"],
    }


def _command_identity(command: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "cwd": command.get("cwd", "."),
            "command": command.get("command"),
            "environment_prerequisites": command.get(
                "environment_prerequisites", []
            ),
        }
    )


def _passed_children(result: dict[str, Any]) -> set[str]:
    return {
        str(child.get("command_id"))
        for child in result.get("children", [])
        if isinstance(child, dict) and child.get("status") == "passed"
    }


def _edge_is_satisfied(edge: dict[str, Any], result: dict[str, Any]) -> bool:
    return bool(
        result.get("status") == "passed"
        and result.get("exit_code") == 0
        and result.get("inventory_complete") is True
        and edge.get("inventory") == "complete"
        and set(edge.get("required_child_ids", [])).issubset(
            _passed_children(result)
        )
    )


def _select_producers(
    validation: dict[str, Any], commands: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    edges = validation.get("coverage_edges", [])
    outgoing: dict[str, int] = {}
    for edge in edges:
        producer = str(edge.get("producer_command_ref"))
        outgoing[producer] = outgoing.get(producer, 0) + 1
    groups: dict[str, list[dict[str, Any]]] = {}
    for command in commands:
        groups.setdefault(_command_identity(command), []).append(command)
    selected = []
    for values in groups.values():
        selected.append(
            sorted(
                values,
                key=lambda item: (
                    -outgoing.get(str(item.get("command_id")), 0),
                    str(item.get("command_id")),
                ),
            )[0]
        )
    return sorted(selected, key=lambda item: str(item.get("command_id")))


def execute_plan(
    validation: dict[str, Any],
    commands: Iterable[dict[str, Any]],
    executor: Executor,
) -> dict[str, Any]:
    """Execute producers once and satisfy covered obligations only with child proof."""

    if validation.get("schema") != "validation-plan/v1":
        raise ValueError("validation plan schema must be validation-plan/v1")
    command_list = [dict(item) for item in commands]
    by_id = {str(item.get("command_id")): item for item in command_list}
    if len(by_id) != len(command_list):
        raise ValueError("command IDs must be unique")
    obligations = validation.get("required_obligations", [])
    obligation_ids = [str(item.get("obligation_id")) for item in obligations]
    if len(obligation_ids) != len(set(obligation_ids)):
        raise ValueError("obligation IDs must be unique")
    if any(item.get("command_ref") not in by_id for item in obligations):
        raise ValueError("obligation references an unknown command")

    results: dict[str, dict[str, Any]] = {}
    physical: list[str] = []
    for producer in _select_producers(validation, command_list):
        producer_id = str(producer["command_id"])
        results[producer_id] = dict(executor(producer))
        physical.append(producer_id)

    edges_by_covered = {
        str(edge.get("covered_command_ref")): edge
        for edge in validation.get("coverage_edges", [])
    }
    status: dict[str, str] = {}
    producer_for_identity = {
        _command_identity(by_id[producer_id]): producer_id
        for producer_id in physical
    }
    for obligation in obligations:
        obligation_id = str(obligation["obligation_id"])
        command_ref = str(obligation["command_ref"])
        selected_producer = producer_for_identity[_command_identity(by_id[command_ref])]
        producer_result = results[selected_producer]
        if command_ref == selected_producer:
            satisfied = (
                producer_result.get("status") == "passed"
                and producer_result.get("exit_code") == 0
                and producer_result.get("inventory_complete") is True
            )
        else:
            edge = edges_by_covered.get(command_ref)
            satisfied = bool(
                edge
                and edge.get("producer_command_ref") == selected_producer
                and _edge_is_satisfied(edge, producer_result)
            )
        if not satisfied:
            fallback = dict(executor(by_id[command_ref]))
            results[command_ref] = fallback
            physical.append(command_ref)
            satisfied = (
                fallback.get("status") == "passed"
                and fallback.get("exit_code") == 0
                and fallback.get("inventory_complete") is True
            )
        status[obligation_id] = "satisfied" if satisfied else "failed"

    return {
        "schema": "validation-execution-plan/v1",
        "profile": validation.get("profile"),
        "physical_execution_count": len(physical),
        "physical_command_refs": physical,
        "obligations": [
            {
                "obligation_id": obligation_id,
                "status": status[obligation_id],
            }
            for obligation_id in obligation_ids
        ],
        "results": results,
    }


def _required_identity(value: str, field: str) -> str:
    if re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise EvidenceError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _current_review_provenance(
    command: dict[str, Any],
    *,
    execution_input_identity: str,
    environment_identity: str,
    ready_payload_sha256: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observed = result or {}
    explicit_inventory = observed.get(
        "test_inventory_sha256", command.get("test_inventory_sha256")
    )
    if explicit_inventory is None:
        inventory_sha256 = canonical_sha256(
            observed.get("children", command.get("test_inventory", []))
        )
    else:
        inventory_sha256 = _required_identity(
            str(explicit_inventory), "test_inventory_sha256"
        )
    return {
        "mode": "executed",
        "producer_review_ref": None,
        "producer_index_ref": None,
        "producer_output_ref": None,
        "verifier_output_ref": None,
        "command_contract_sha256": canonical_sha256(command),
        "execution_input_identity": _required_identity(
            execution_input_identity, "execution_input_identity"
        ),
        "environment_identity": _required_identity(
            environment_identity, "environment_identity"
        ),
        "ready_payload_sha256": _required_identity(
            ready_payload_sha256, "ready_payload_sha256"
        ),
        "test_inventory_sha256": inventory_sha256,
    }


def run_review_precheck(
    checks: Iterable[dict[str, Any]],
    commands: Iterable[dict[str, Any]],
    executor: Executor,
    *,
    execution_input_identity: str,
    environment_identity: str,
    ready_payload_sha256: str,
) -> dict[str, Any]:
    """Run cheap review checks and start commands only when every check passes."""

    check_values = [dict(item) for item in checks]
    by_id = {str(item.get("check_id", "")): item for item in check_values}
    blocking_findings: list[dict[str, Any]] = []
    if len(by_id) != len(check_values):
        blocking_findings.append(
            {
                "finding_id": "F-precheck-duplicate",
                "message": "Precheck contains duplicate check IDs.",
            }
        )
    for check_id in REQUIRED_PRECHECK_CHECKS:
        check = by_id.get(check_id)
        if check is None:
            blocking_findings.append(
                {
                    "finding_id": f"F-precheck-missing-{check_id}",
                    "message": f"Required precheck is missing: {check_id}.",
                }
            )
            continue
        if check.get("outcome") != "passed":
            findings = check.get("findings", [])
            if isinstance(findings, list) and findings:
                blocking_findings.extend(
                    dict(item) for item in findings if isinstance(item, dict)
                )
            else:
                blocking_findings.append(
                    {
                        "finding_id": f"F-precheck-blocked-{check_id}",
                        "message": f"Required precheck did not pass: {check_id}.",
                    }
                )

    command_values = [dict(item) for item in commands]
    blocked = bool(blocking_findings)
    outcomes: list[dict[str, Any]] = []
    if blocked:
        for command in command_values:
            outcomes.append(
                {
                    "command_id": command["command_id"],
                    "outcome": "not_run",
                    "exit_code": None,
                    "failure_count": None,
                    "skipped_count": None,
                    "output_ref": None,
                    "not_run_reason": "precheck_blocked",
                    "provenance": _current_review_provenance(
                        command,
                        execution_input_identity=execution_input_identity,
                        environment_identity=environment_identity,
                        ready_payload_sha256=ready_payload_sha256,
                    ),
                }
            )
    else:
        for command in command_values:
            result = dict(executor(command))
            outcome = result.get("outcome", result.get("status"))
            if outcome == "passed":
                exit_code = 0
                failure_count = result.get("failure_count", 0)
                skipped_count = result.get("skipped_count", 0)
                not_run_reason = None
            else:
                exit_code = result.get("exit_code")
                failure_count = result.get("failure_count")
                skipped_count = result.get("skipped_count")
                not_run_reason = result.get("not_run_reason")
            outcomes.append(
                {
                    "command_id": command["command_id"],
                    "outcome": outcome,
                    "exit_code": exit_code,
                    "failure_count": failure_count,
                    "skipped_count": skipped_count,
                    "output_ref": result.get("output_ref"),
                    "not_run_reason": not_run_reason,
                    "provenance": result.get(
                        "provenance",
                        _current_review_provenance(
                            command,
                            execution_input_identity=execution_input_identity,
                            environment_identity=environment_identity,
                            ready_payload_sha256=ready_payload_sha256,
                            result=result,
                        ),
                    ),
                }
            )
    return {
        "schema": "review-precheck-execution/v1",
        "precheck": {
            "schema": "review-precheck/v1",
            "outcome": "blocked" if blocked else "passed",
            "checks": check_values,
            "blocking_findings": blocking_findings,
        },
        "command_outcomes": outcomes,
    }


def _terminal_addition(
    change: dict[str, Any],
    terminal_only_paths: Iterable[str],
    *,
    work_id: str | None = None,
) -> bool:
    path = change.get("path")
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or path.startswith("/")
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or change.get("change") != "added"
    ):
        return False
    if not any(fnmatch.fnmatchcase(path, pattern) for pattern in terminal_only_paths):
        return False
    if work_id is None:
        return True
    escaped_work_id = re.escape(work_id)
    fixed_terminal_patterns = (
        rf"docs/work/{escaped_work_id}/implementation/outcome(?:-[1-9][0-9]*)?\.(?:json|md)",
        r"knowledge/candidate-seal\.json",
        r"snapshots/(?:preliminary|final)-(?:product|knowledge)\.json",
        r"reviews/final/verifier(?:-[1-9][0-9]*)?\.json",
    )
    return any(re.fullmatch(pattern, path) for pattern in fixed_terminal_patterns)


def _outcome_revision(path: str, work_id: str) -> int | None:
    match = re.fullmatch(
        rf"docs/work/{re.escape(work_id)}/implementation/outcome(?:-([1-9][0-9]*))?\.json",
        path,
    )
    if match is None:
        return None
    return int(match.group(1) or "1")


def _outcome_sequence_is_continuous(
    changes: list[dict[str, Any]],
    existing_terminal_paths: Iterable[str],
    work_id: str,
) -> bool:
    existing_revisions = sorted(
        revision
        for path in existing_terminal_paths
        if (revision := _outcome_revision(str(path), work_id)) is not None
    )
    added_revisions = sorted(
        revision
        for change in changes
        if (revision := _outcome_revision(str(change.get("path", "")), work_id))
        is not None
    )
    if existing_revisions and existing_revisions != list(
        range(1, max(existing_revisions) + 1)
    ):
        return False
    if not added_revisions:
        return True
    expected_start = (max(existing_revisions) + 1) if existing_revisions else 1
    return added_revisions == list(
        range(expected_start, expected_start + len(added_revisions))
    )


def decide_review_execution(
    *,
    stage: str,
    reference: dict[str, Any],
    current_execution_input_identity: str,
    current_environment_identity: str,
    current_ready_payload_sha256: str,
    changes: Iterable[dict[str, Any]],
    terminal_only_paths: Iterable[str],
    work_id: str | None = None,
    existing_terminal_paths: Iterable[str] = (),
    verify: bool = True,
) -> dict[str, Any]:
    """Choose fresh execution or verified reuse for one independent review stage."""

    if stage not in {"preliminary", "final"}:
        raise ValueError("review stage must be preliminary or final")
    if stage == "preliminary":
        return {
            "schema": "review-execution-decision/v1",
            "stage": stage,
            "mode": "executed",
            "reasons": ["preliminary_requires_fresh_execution"],
            "verifier": None,
        }

    reasons: list[str] = []
    expected_identities = {
        "execution_input_identity": current_execution_input_identity,
        "environment_identity": current_environment_identity,
        "ready_payload_sha256": current_ready_payload_sha256,
    }
    for field, expected in expected_identities.items():
        if reference.get(field) != expected:
            reasons.append(f"{field}_drift")
    change_values = [dict(change) for change in changes]
    if any(
        not _terminal_addition(
            change,
            terminal_only_paths,
            work_id=work_id,
        )
        for change in change_values
    ):
        reasons.append("nonterminal_input")
    if work_id is not None and not _outcome_sequence_is_continuous(
        change_values,
        existing_terminal_paths,
        work_id,
    ):
        reasons.append("terminal_sequence")
    if reasons:
        return {
            "schema": "review-execution-decision/v1",
            "stage": stage,
            "mode": "fresh_required",
            "reasons": sorted(set(reasons)),
            "verifier": None,
        }

    if verify:
        try:
            verifier = verify_reference(
                reference,
                expected_execution_input_identity=current_execution_input_identity,
                expected_environment_identity=current_environment_identity,
                expected_ready_payload_sha256=current_ready_payload_sha256,
            )
        except EvidenceError:
            return {
                "schema": "review-execution-decision/v1",
                "stage": stage,
                "mode": "fresh_required",
                "reasons": ["referenced_evidence_invalid"],
                "verifier": None,
            }
    else:
        verifier = {
            "schema": "validation-reference-verification/v1",
            "outcome": "verification_skipped_for_classification",
        }
    return {
        "schema": "review-execution-decision/v1",
        "stage": stage,
        "mode": "referenced",
        "reasons": ["terminal_only_additions"],
        "verifier": verifier,
        "producer": {
            "index_ref": reference.get("producer_index"),
            "command_id": reference.get("producer_command_id"),
            "output_sha256": reference.get("stdout_sha256"),
        },
    }


def _markdown_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace(
        "\n", " "
    )


def render_review(handoff: dict[str, Any], index_path: Path) -> str:
    """Render stable reviewer material from structured Ready and evidence inputs."""

    if handoff.get("schema") != "ready-plan/v1":
        raise EvidenceError("render input is not a ready-plan/v1 handoff")
    for field in ("commands", "sources", "contract_index"):
        if not isinstance(handoff.get(field), list):
            raise EvidenceError(f"render input lacks {field}")
    evidence = verify_bundle(index_path)
    lines = ["# Validation review", "", "## Command summary", ""]
    lines.extend(
        [
            "| Command | Purpose | Contract |",
            "|---|---|---|",
        ]
    )
    for command in sorted(
        handoff["commands"], key=lambda item: str(item.get("command_id", ""))
    ):
        lines.append(
            "| {} | {} | {} |".format(
                _markdown_cell(command.get("command_id")),
                _markdown_cell(command.get("purpose")),
                _markdown_cell(command.get("command")),
            )
        )

    lines.extend(
        [
            "",
            "## Traceability",
            "",
            "| Source | BDD | Tests | Work packages |",
            "|---|---|---|---|",
        ]
    )
    contracts = [
        item for item in handoff["contract_index"] if isinstance(item, dict)
    ]
    for source in sorted(
        handoff["sources"], key=lambda item: str(item.get("source_id", ""))
    ):
        source_id = str(source.get("source_id", ""))
        linked = [
            item for item in contracts if source_id in item.get("source_refs", [])
        ]
        bdd_refs = sorted(
            {
                str(item.get("contract_id"))
                for item in linked
                if item.get("kind") == "bdd-scenario"
            }
        )
        test_refs = sorted(
            {
                str(item.get("contract_id"))
                for item in linked
                if item.get("kind") == "inner-test"
            }
        )
        wp_refs = sorted(
            {
                str(wp)
                for item in linked
                for wp in item.get("wp_refs", [])
            }
        )
        lines.append(
            "| {} | {} | {} | {} |".format(
                _markdown_cell(source_id),
                _markdown_cell(", ".join(bdd_refs)),
                _markdown_cell(", ".join(test_refs)),
                _markdown_cell(", ".join(wp_refs)),
            )
        )

    lines.extend(
        [
            "",
            "## Evidence overview",
            "",
            f"Profile: `{_markdown_cell(evidence.get('profile'))}`",
            "",
            "| Command | Status | Exit | Failures | Skips | Output SHA-256 |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for command in sorted(
        evidence["commands"], key=lambda item: str(item.get("command_id", ""))
    ):
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                _markdown_cell(command.get("command_id")),
                _markdown_cell(command.get("status")),
                _markdown_cell(command.get("exit_code")),
                _markdown_cell(command.get("failure_count")),
                _markdown_cell(command.get("skipped_count")),
                _markdown_cell(command.get("stdout", {}).get("sha256")),
            )
        )
    return "\n".join(lines) + "\n"


def _archive_identity(identity: dict[str, Any]) -> dict[str, str]:
    required = ("run_id", "repo_id", "worktree_key")
    value = {field: identity.get(field) for field in required}
    if any(not isinstance(value[field], str) or not re.fullmatch(r"[a-f0-9]{64}", value[field]) for field in required):
        raise EvidenceError("archive identity is incomplete or invalid")
    return value


def _archive_files(root: Path, known_secret_values: Iterable[str]) -> list[dict[str, Any]]:
    sentinels = [value.encode("utf-8") for value in known_secret_values if value]
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if _is_redirect(path):
            raise EvidenceError(f"archive source is redirected: {relative}")
        if path.is_dir():
            continue
        if not path.is_file() or not stat.S_ISREG(path.lstat().st_mode):
            raise EvidenceError(f"archive source is irregular: {relative}")
        raw = path.read_bytes()
        if any(sentinel in raw for sentinel in sentinels):
            raise EvidenceError("archive source contains a known secret sentinel")
        files.append(
            {
                "path": relative,
                "sha256": _sha_bytes(raw),
                "bytes": len(raw),
            }
        )
    if not files:
        raise EvidenceError("archive source has no evidence files")
    return files


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def export_archive(
    run_root: Path,
    archive_path: Path,
    *,
    identity: dict[str, Any],
    known_secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    """Export one run as a deterministic, create-only ZIP archive."""

    root = Path(run_root).resolve()
    target = Path(archive_path).resolve(strict=False)
    if not root.is_dir() or _is_redirect(root):
        raise EvidenceError("archive source root is missing or redirected")
    try:
        target.relative_to(root)
    except ValueError:
        pass
    else:
        raise EvidenceError("archive target must be outside the source run")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    if not target.parent.is_dir() or _is_redirect(target.parent):
        raise EvidenceError("archive target parent is missing or redirected")
    files = _archive_files(root, known_secret_values)
    manifest: dict[str, Any] = {
        "schema": "evidence-archive/v1",
        "identity": _archive_identity(identity),
        "retention": {
            "active_runs_auto_pruned": False,
            "complete_minimum_days": 30,
            "prune_requires_explicit_command": True,
        },
        "files": files,
    }
    manifest["archive_id"] = canonical_sha256(manifest)
    manifest_raw = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_raw)
            for item in files:
                archive.writestr(
                    _zip_info(item["path"]),
                    (root / _safe_relative(item["path"])).read_bytes(),
                )
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.rename(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def _safe_zip_name(name: str) -> Path:
    try:
        return _safe_relative(name)
    except EvidenceError as exc:
        raise EvidenceError(f"archive member path is unsafe: {name}") from exc


def verify_archive(
    archive_path: Path,
    *,
    expected_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify archive structure, identity, inventory, hashes, and byte counts."""

    path = Path(archive_path)
    if _is_redirect(path) or not path.is_file() or not stat.S_ISREG(path.lstat().st_mode):
        raise EvidenceError("archive is missing, redirected, or irregular")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise EvidenceError("archive repeats a member name")
            for info in infos:
                _safe_zip_name(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK or info.is_dir():
                    raise EvidenceError("archive contains a redirected or directory member")
            if "manifest.json" not in names:
                raise EvidenceError("archive manifest is missing")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("schema") != "evidence-archive/v1":
                raise EvidenceError("archive manifest schema is invalid")
            archive_id = manifest.get("archive_id")
            payload = dict(manifest)
            payload.pop("archive_id", None)
            if archive_id != canonical_sha256(payload):
                raise EvidenceError("archive manifest identity drifted")
            identity = _archive_identity(manifest.get("identity", {}))
            if expected_identity is not None and identity != _archive_identity(expected_identity):
                raise EvidenceError("archive run identity does not match")
            file_entries = manifest.get("files")
            if not isinstance(file_entries, list) or not file_entries:
                raise EvidenceError("archive file inventory is empty")
            expected_names = [str(item.get("path", "")) for item in file_entries]
            if expected_names != sorted(expected_names) or len(expected_names) != len(set(expected_names)):
                raise EvidenceError("archive file inventory is not canonical")
            if set(names) != {"manifest.json", *expected_names}:
                raise EvidenceError("archive members differ from the manifest")
            for item in file_entries:
                name = str(item.get("path", ""))
                _safe_zip_name(name)
                raw = archive.read(name)
                if item.get("sha256") != _sha_bytes(raw) or item.get("bytes") != len(raw):
                    raise EvidenceError(f"archive bytes drifted: {name}")
    except EvidenceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise EvidenceError("archive cannot be verified") from exc
    return manifest


def import_archive(
    archive_path: Path,
    imports_root: Path,
    *,
    expected_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Import verified bytes into a create-only quarantine without approval state."""

    manifest = verify_archive(archive_path, expected_identity=expected_identity)
    root = Path(imports_root)
    if not root.is_dir() or _is_redirect(root):
        raise EvidenceError("imports root is missing or redirected")
    target = root / manifest["archive_id"]
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    staging = Path(tempfile.mkdtemp(prefix=".import-staging-", dir=root))
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for item in manifest["files"]:
                relative = _safe_relative(item["path"])
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                _write_bytes(destination, archive.read(item["path"]))
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "schema": "evidence-archive-import/v1",
        "archive_id": manifest["archive_id"],
        "identity": manifest["identity"],
        "quarantine_root": str(target),
        "approval_inherited": False,
        "resume_evidence": {
            "manifest_sha256": canonical_sha256(manifest),
            "file_count": len(manifest["files"]),
        },
    }


def _local_environment() -> dict[str, str]:
    git_version = subprocess.run(
        ["git", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    ).stdout.decode("utf-8", errors="replace").strip()
    return {
        "os": platform.system().lower(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "git": git_version,
    }


def _command_input_class(scope: object, commands: object) -> str:
    if not isinstance(commands, list):
        raise EvidenceError("benchmark command inventory is absent")
    command_ids = [
        str(item.get("logical_command_id", item.get("command_id")))
        for item in commands
        if isinstance(item, dict) and item.get("command_id")
    ]
    if len(command_ids) != len(commands):
        raise EvidenceError("benchmark command inventory is incomplete")
    return canonical_sha256(
        {"scope": scope, "command_ids": sorted(set(command_ids))}
    )


def _baseline_sample(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("baseline benchmark sample is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema") != "knowledge-suite-metrics/v1":
        raise EvidenceError("baseline benchmark sample has the wrong schema")
    counts = value.get("summary", {}).get("counts", {})
    if (
        value.get("outcome") != "passed"
        or not isinstance(counts, dict)
        or counts.get("failed") != 0
        or counts.get("timeout") != 0
        or counts.get("not_run") != 0
    ):
        raise EvidenceError("baseline benchmark sample is not a complete pass")
    duration = value.get("summary", {}).get("wall_duration_seconds")
    if duration is None:
        duration = value.get("summary", {}).get("total_duration_seconds")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise EvidenceError("baseline benchmark duration is invalid")
    explicit_input = value.get("execution_input_class")
    input_class = (
        explicit_input
        if isinstance(explicit_input, str)
        else _command_input_class(value.get("scope"), value.get("commands"))
    )
    environment_identity = value.get("environment_identity")
    if not isinstance(environment_identity, str):
        environment_identity = canonical_sha256(_local_environment())
    return {
        "path": str(path),
        "file_sha256": _sha_bytes(path.read_bytes()),
        "duration_seconds": float(duration),
        "input_class": input_class,
        "explicit_input_class": isinstance(explicit_input, str),
        "environment_identity": environment_identity,
    }


def _optimized_sample(path: Path, *, exact_input: bool) -> dict[str, Any]:
    value = verify_bundle(path)
    counts = value.get("summary", {}).get("counts", {})
    if (
        value.get("profile") != "local"
        or counts.get("failed") != 0
        or counts.get("timeout") != 0
        or counts.get("not_run") != 0
        or any(item.get("status") != "passed" for item in value.get("commands", []))
    ):
        raise EvidenceError("optimized benchmark sample is not a complete local pass")
    duration = value.get("summary", {}).get("wall_duration_seconds")
    if duration is None:
        duration = value.get("summary", {}).get("total_duration_seconds")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise EvidenceError("optimized benchmark duration is invalid")
    execution_input = value.get("execution_input", {})
    input_class = (
        value.get("execution_input_identity")
        if exact_input
        else _command_input_class(
            execution_input.get("scope"), execution_input.get("commands")
        )
    )
    return {
        "path": str(path),
        "file_sha256": _sha_bytes(path.read_bytes()),
        "duration_seconds": float(duration),
        "input_class": input_class,
        "execution_input_identity": value.get("execution_input_identity"),
        "environment_identity": value.get("environment_identity"),
    }


def compare_benchmarks(
    baseline_paths: Iterable[Path],
    optimized_paths: Iterable[Path],
    *,
    minimum_improvement: float,
) -> dict[str, Any]:
    """Compare three complete local samples per side using wall-time medians."""

    baseline_values = [_baseline_sample(Path(path)) for path in baseline_paths]
    if len(baseline_values) != 3:
        raise EvidenceError("benchmark comparison requires exactly three baseline samples")
    exact_input = all(item["explicit_input_class"] for item in baseline_values)
    optimized_values = [
        _optimized_sample(Path(path), exact_input=exact_input)
        for path in optimized_paths
    ]
    if len(optimized_values) != 3:
        raise EvidenceError("benchmark comparison requires exactly three optimized samples")
    all_values = [*baseline_values, *optimized_values]
    if len({item["input_class"] for item in all_values}) != 1:
        raise EvidenceError("benchmark execution input classes differ")
    if len({item["environment_identity"] for item in all_values}) != 1:
        raise EvidenceError("benchmark environments differ")
    optimized_identities = {
        item["execution_input_identity"] for item in optimized_values
    }
    if len(optimized_identities) != 1 or None in optimized_identities:
        raise EvidenceError("optimized benchmark execution inputs differ")
    baseline_median = float(
        statistics.median(item["duration_seconds"] for item in baseline_values)
    )
    optimized_median = float(
        statistics.median(item["duration_seconds"] for item in optimized_values)
    )
    improvement = ((baseline_median - optimized_median) / baseline_median) * 100.0
    return {
        "schema": "validation-benchmark/v1",
        "outcome": "passed" if improvement >= minimum_improvement else "failed",
        "minimum_improvement_percent": float(minimum_improvement),
        "baseline_median_seconds": round(baseline_median, 6),
        "optimized_median_seconds": round(optimized_median, 6),
        "improvement_percent": round(improvement, 6),
        "execution_input_class": all_values[0]["input_class"],
        "environment_identity": all_values[0]["environment_identity"],
        "baseline_samples": baseline_values,
        "optimized_samples": optimized_values,
    }


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} is not an object")
    return value


def _run_identity(run_root: Path) -> dict[str, str]:
    ledger = _load_json_object(Path(run_root) / "run.json", "implementation Ledger")
    binding = ledger.get("binding", {})
    return _archive_identity(
        {
            "run_id": ledger.get("run_id"),
            "repo_id": binding.get("repo_id", ledger.get("repo_id")),
            "worktree_key": binding.get(
                "worktree_key", ledger.get("worktree_key")
            ),
        }
    )


def _optional_identity(arguments: argparse.Namespace) -> dict[str, str] | None:
    values = {
        "run_id": getattr(arguments, "run_id", None),
        "repo_id": getattr(arguments, "repo_id", None),
        "worktree_key": getattr(arguments, "worktree_key", None),
    }
    if all(value is None for value in values.values()):
        return None
    return _archive_identity(values)


def _add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id")
    parser.add_argument("--repo-id")
    parser.add_argument("--worktree-key")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)

    verify_parser = commands.add_parser("verify", help="verify one evidence index")
    verify_parser.add_argument("--index", type=Path, required=True)

    render_parser = commands.add_parser("render", help="render reviewer material")
    render_parser.add_argument("--handoff", type=Path, required=True)
    render_parser.add_argument("--index", type=Path, required=True)

    archive_parser = commands.add_parser("archive", help="export, verify, or import archives")
    archive_commands = archive_parser.add_subparsers(
        dest="archive_operation", required=True
    )
    export_parser = archive_commands.add_parser("export")
    export_parser.add_argument("--run-root", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    verify_archive_parser = archive_commands.add_parser("verify")
    verify_archive_parser.add_argument("--archive", type=Path, required=True)
    _add_identity_arguments(verify_archive_parser)
    import_parser = archive_commands.add_parser("import")
    import_parser.add_argument("--archive", type=Path, required=True)
    import_parser.add_argument("--imports-root", type=Path, required=True)
    _add_identity_arguments(import_parser)

    benchmark_parser = commands.add_parser("benchmark", help="compare validation samples")
    benchmark_commands = benchmark_parser.add_subparsers(
        dest="benchmark_operation", required=True
    )
    compare_parser = benchmark_commands.add_parser("compare")
    compare_parser.add_argument("--baseline", type=Path, action="append", required=True)
    compare_parser.add_argument("--optimized", type=Path, action="append", required=True)
    compare_parser.add_argument("--minimum-improvement", type=float, required=True)

    args = parser.parse_args(argv)
    try:
        if args.operation == "verify":
            result: object = verify_bundle(args.index)
        elif args.operation == "render":
            handoff = _load_json_object(args.handoff, "Ready handoff")
            print(render_review(handoff, args.index), end="")
            return 0
        elif args.operation == "archive" and args.archive_operation == "export":
            result = export_archive(
                args.run_root,
                args.output,
                identity=_run_identity(args.run_root),
            )
        elif args.operation == "archive" and args.archive_operation == "verify":
            result = verify_archive(
                args.archive,
                expected_identity=_optional_identity(args),
            )
        elif args.operation == "archive" and args.archive_operation == "import":
            result = import_archive(
                args.archive,
                args.imports_root,
                expected_identity=_optional_identity(args),
            )
        elif args.operation == "benchmark" and args.benchmark_operation == "compare":
            result = compare_benchmarks(
                args.baseline,
                args.optimized,
                minimum_improvement=args.minimum_improvement,
            )
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["outcome"] == "passed" else 1
        else:
            raise EvidenceError("unknown validation evidence operation")
    except (EvidenceError, FileExistsError) as exc:
        print(
            json.dumps(
                {
                    "schema": "validation-evidence-error/v1",
                    "outcome": "invalid",
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EvidenceError.exit_code
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
