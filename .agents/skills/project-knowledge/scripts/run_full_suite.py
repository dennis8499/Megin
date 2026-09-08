#!/usr/bin/env python3
"""Run project-knowledge and related owner checks without external dependencies."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


VALIDATION_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "implementation-execution/scripts/validation_evidence.py"
)


def _command(
    *arguments: str,
    command_id: str,
    timeout: int,
) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "arguments": [sys.executable, "-X", "utf8", "-B", *arguments],
        "timeout": timeout,
    }


def _commands(scope: str, fixture_root: Path) -> list[dict[str, Any]]:
    root = ".agents/skills/project-knowledge/scripts"
    commands = [
        _command(
            f"{root}/test_query.py",
            "--fixture-root",
            str(fixture_root),
            command_id="TEST-QUERY",
            timeout=180,
        ),
        _command(
            f"{root}/test_workflow.py",
            "--fixture-root",
            str(fixture_root),
            command_id="TEST-WORKFLOW",
            timeout=180,
        ),
        _command(
            f"{root}/test_behavior.py",
            *(("--group", "retrieval") if scope == "related" else ()),
            "--fixture-root",
            str(fixture_root),
            command_id="BDD-RELATED" if scope == "related" else "BDD-FULL",
            timeout=900,
        ),
        _command(
            ".agents/skills/requirements-discovery/scripts/validate_contracts.py",
            command_id="OWNER-REQUIREMENTS",
            timeout=120,
        ),
        _command(
            ".agents/skills/technical-planning/scripts/validate_contracts.py",
            command_id="OWNER-PLANNING",
            timeout=120,
        ),
        _command(
            ".agents/skills/implementation-execution/scripts/validate_contracts.py",
            command_id="OWNER-IMPLEMENTATION",
            timeout=120,
        ),
        _command(
            ".agents/skills/bug-diagnosis/scripts/validate_contracts.py",
            command_id="OWNER-BUG",
            timeout=120,
        ),
        _command(
            ".agents/skills/delivery-orchestrator/scripts/validate_contracts.py",
            command_id="OWNER-DELIVERY",
            timeout=180,
        ),
    ]
    if scope == "all":
        governance = Path(f"{root}/test_governance.py")
        validator = Path(f"{root}/validate_contracts.py")
        if governance.is_file():
            commands.insert(
                1,
                _command(
                    str(governance),
                    "--fixture-root",
                    str(fixture_root),
                    command_id="TEST-GOVERNANCE",
                    timeout=360,
                ),
            )
        if validator.is_file():
            commands.extend(
                [
                    _command(
                        str(validator),
                        "--syntax-all",
                        command_id="BUILD-FULL",
                        timeout=120,
                    ),
                    _command(
                        str(validator),
                        "--governance",
                        command_id="GOVERNANCE",
                        timeout=180,
                    ),
                ]
            )
        commands.append(
            _command(
                f"{root}/measure_search_quality.py",
                "--repo",
                ".",
                command_id="SEARCH-QUALITY",
                timeout=180,
            )
        )
        commands.extend(
            [
                _command(
                    ".agents/skills/requirements-discovery/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-REQUIREMENTS",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/technical-planning/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-PLANNING",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/implementation-execution/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-IMPLEMENTATION",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/bug-diagnosis/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-BUG",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/delivery-orchestrator/scripts/test_validate_contracts.py",
                    command_id="TEST-OWNER-DELIVERY-CONTRACT",
                    timeout=180,
                ),
                _command(
                    ".agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py",
                    command_id="TEST-OWNER-DELIVERY-WORKSPACE",
                    timeout=900,
                ),
            ]
        )
    return commands


DELIVERY_FUNCTIONAL_SHARDS = (
    ("SAFETY", ("DeliverySafetyTests",), 840),
    ("TRANSITIONS", ("DeliveryTransitionTests",), 830),
    ("BUG", ("DeliveryBugOverlayTests",), 1_050),
    ("AUTHORIZATION", ("UnifiedEntryAuthorizationTests",), 1_070),
    ("TERMINAL", ("DeliveryTerminalContractTests",), 740),
    ("WORKTREE", ("DeliveryWorktreeTests",), 610),
    ("DOCTOR", ("DeliveryDoctorTests",), 450),
    ("WORKFLOW-SPEED", ("WorkflowSpeedFixtureTests",), 60),
    ("ARCHITECTURE", ("DeliveryTransitionArchitectureTests",), 10),
)
DELIVERY_FUNCTIONAL_CASES = tuple(
    case
    for _, cases, _ in DELIVERY_FUNCTIONAL_SHARDS
    for case in cases
)

# Start the longest independent shards first.  The values are scheduling hints,
# not timing evidence or pass criteria; stable command IDs keep the policy
# deterministic when historical timings are unavailable.
PROFILE_SCHEDULE_PRIORITY = {
    "TEST-WORKFLOW": 1_200,
    "TEST-GOVERNANCE": 690,
    "TEST-QUERY": 610,
    "SEARCH-QUALITY": 210,
    "TEST-OWNER-DELIVERY-CONTRACT": 185,
    **{
        f"TEST-OWNER-DELIVERY-FUNCTIONAL-{shard_id}": priority
        for shard_id, _, priority in DELIVERY_FUNCTIONAL_SHARDS
    },
    **{
        f"BDD-FUNCTIONAL-{index}": priority
        for index, priority in enumerate((565, 350, 720, 835), 1)
    },
}

BDD_FUNCTIONAL_SHARD_COUNT = 4


def _profile_commands(
    commands: list[dict[str, Any]], *, profile: str | None = None
) -> list[dict[str, Any]]:
    """Split performance-heavy owners while preserving their logical obligations."""

    profiled: list[dict[str, Any]] = []
    for original in commands:
        item = {**original, "arguments": list(original["arguments"])}
        command_id = item["command_id"]
        if command_id == "BDD-FULL":
            functional = [
                {
                    **item,
                    "command_id": f"BDD-FUNCTIONAL-{index}",
                    "logical_command_id": "BDD-FULL",
                    "execution_class": "parallel_safe",
                    "arguments": [
                        *item["arguments"],
                        "--functional-shard",
                        f"{index}/{BDD_FUNCTIONAL_SHARD_COUNT}",
                    ],
                }
                for index in range(1, BDD_FUNCTIONAL_SHARD_COUNT + 1)
            ]
            performance = {
                **item,
                "command_id": "BDD-PERFORMANCE",
                "logical_command_id": "BDD-FULL",
                "execution_class": "sequential_performance",
                "arguments": [
                    *item["arguments"],
                    "--performance-only",
                    *(
                        ("--validation-profile", profile)
                        if profile is not None
                        else ()
                    ),
                ],
            }
            profiled.extend((*functional, performance))
            continue
        if command_id == "TEST-OWNER-DELIVERY-WORKSPACE":
            functional = [
                {
                    **item,
                    "command_id": (
                        f"TEST-OWNER-DELIVERY-FUNCTIONAL-{shard_id}"
                    ),
                    "logical_command_id": command_id,
                    "execution_class": "parallel_safe",
                    "arguments": [*item["arguments"], *cases],
                }
                for shard_id, cases, _ in DELIVERY_FUNCTIONAL_SHARDS
            ]
            performance = {
                **item,
                "command_id": "TEST-OWNER-DELIVERY-PERFORMANCE",
                "logical_command_id": command_id,
                "execution_class": "sequential_performance",
                "arguments": [*item["arguments"], "DeliveryPerformanceTests"],
            }
            profiled.extend((*functional, performance))
            continue
        item["logical_command_id"] = command_id
        item["execution_class"] = "parallel_safe"
        profiled.append(item)
    for index, item in enumerate(profiled, 1):
        item["worker_index"] = index
        item["schedule_priority"] = PROFILE_SCHEDULE_PRIORITY.get(
            str(item["command_id"]), 0
        )
    return profiled


def execute_profile_schedule(
    commands: list[dict[str, Any]],
    *,
    jobs: int,
    executor,
) -> dict[str, dict[str, Any]]:
    """Run bounded parallel work, then serialized performance work."""

    if jobs < 1:
        raise ValueError("jobs must be at least one")
    command_ids = [str(item.get("command_id", "")) for item in commands]
    if len(command_ids) != len(set(command_ids)) or any(not value for value in command_ids):
        raise ValueError("profile command IDs must be unique and non-empty")
    parallel = sorted(
        (
            item
            for item in commands
            if item.get("execution_class") == "parallel_safe"
        ),
        key=lambda item: (
            -int(item.get("schedule_priority", 0)),
            int(item.get("worker_index", 0)),
            str(item.get("command_id", "")),
        ),
    )
    performance = [
        item
        for item in commands
        if item.get("execution_class") == "sequential_performance"
    ]
    if len(parallel) + len(performance) != len(commands):
        raise ValueError("profile command has an unknown execution class")

    results: dict[str, dict[str, Any]] = {}
    failed = False
    next_index = 0
    active: dict[concurrent.futures.Future, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        while next_index < len(parallel) and len(active) < jobs:
            command = parallel[next_index]
            active[pool.submit(executor, command)] = command
            next_index += 1
        while active:
            done, _ = concurrent.futures.wait(
                active, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in sorted(
                done,
                key=lambda candidate: int(active[candidate].get("worker_index", 0)),
            ):
                command = active.pop(future)
                try:
                    result = dict(future.result())
                except BaseException as exc:
                    result = {
                        "command_id": command["command_id"],
                        "status": "failed",
                        "exit_code": 1,
                        "stdout": b"",
                        "stderr": f"profile worker failed: {type(exc).__name__}\n".encode(),
                    }
                results[command["command_id"]] = result
                if result.get("status") != "passed":
                    failed = True
            while not failed and next_index < len(parallel) and len(active) < jobs:
                command = parallel[next_index]
                active[pool.submit(executor, command)] = command
                next_index += 1

    for command in parallel:
        if command["command_id"] not in results:
            results[command["command_id"]] = {
                "command_id": command["command_id"],
                "status": "not_run",
                "exit_code": None,
                "not_run_reason": "fail_fast",
                "stdout": b"",
                "stderr": b"",
            }
    for command in performance:
        if failed:
            result = {
                "command_id": command["command_id"],
                "status": "not_run",
                "exit_code": None,
                "not_run_reason": "fail_fast",
                "stdout": b"",
                "stderr": b"",
            }
        else:
            try:
                result = dict(executor(command))
            except BaseException as exc:
                result = {
                    "command_id": command["command_id"],
                    "status": "failed",
                    "exit_code": 1,
                    "stdout": b"",
                    "stderr": f"profile worker failed: {type(exc).__name__}\n".encode(),
                }
            if result.get("status") != "passed":
                failed = True
        results[command["command_id"]] = result
    return results


def _is_redirect(path: Path) -> bool:
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return os.name == "nt" and bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def _profile_inventory(stdout: bytes, stderr: bytes, passed: bool) -> list[dict[str, str]]:
    value = _json_result(stdout)
    if isinstance(value.get("commands"), list):
        return [
            {
                "command_id": str(item["command_id"]),
                "status": "passed" if item.get("exit_code") == 0 else "failed",
            }
            for item in value["commands"]
            if isinstance(item, dict) and item.get("command_id")
        ]
    selected = value.get("selected")
    if isinstance(selected, list):
        child_status = "passed" if passed and value.get("failed") == 0 else "failed"
        return [
            {"command_id": str(identifier), "status": child_status}
            for identifier in selected
        ]
    tests = value.get("tests")
    if isinstance(tests, list):
        return [
            {
                "command_id": str(identifier),
                "status": "passed" if passed else "failed",
            }
            for identifier in tests
        ]
    decoded = stderr.decode("utf-8", errors="replace")
    names = re.findall(r"(?m)^(test_[A-Za-z0-9_]+) \([^\r\n]+\) \.\.\. (?:ok|FAIL|ERROR)$", decoded)
    return [
        {"command_id": name, "status": "passed" if passed else "failed"}
        for name in dict.fromkeys(names)
    ]


def execute_profile_item(
    command: dict[str, Any],
    *,
    workspace: Path,
    fixture_root: Path,
    fixture_argument: Path,
    worker_index: int,
    validation_profile: str | None = None,
) -> dict[str, Any]:
    """Execute one child with a private temp/registry/fixture namespace."""

    command_id = str(command["command_id"])
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "-", command_id).strip("-.")
    if not safe_id:
        raise ValueError("worker command ID is unsafe")
    # Keep the on-disk namespace deliberately short. Delivery tests create nested
    # repositories, worktrees, and submodules; descriptive worker directory names
    # can push their Git object paths past the Windows path limit.
    worker_root = fixture_root / f"{worker_index:03d}"
    worker_root.mkdir(exist_ok=False)
    child_fixture = worker_root / "fixture"
    child_temp = worker_root / "t"
    child_registry = child_temp / "r"
    child_fixture.mkdir()
    child_temp.mkdir()
    child_registry.mkdir()
    profile_path = worker_root / "p.json"
    arguments = list(command["arguments"])
    for index, argument in enumerate(arguments):
        if index and arguments[index - 1] == "--fixture-root":
            arguments[index] = str(child_fixture)
        elif argument == str(fixture_argument):
            arguments[index] = str(child_fixture)
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMP": str(child_temp),
            "TEMP": str(child_temp),
            "TMPDIR": str(child_temp),
            "DELIVERY_ORCHESTRATOR_ROOT": str(child_registry),
            "DELIVERY_FIXTURE_PROFILE": str(profile_path),
            "KNOWLEDGE_TEST_WORKER_ROOT": str(worker_root),
            "KNOWLEDGE_TEST_REGISTRY_ROOT": str(child_registry),
        }
    )
    if validation_profile is not None:
        environment["SDLC_RUNNER_VALIDATION_PROFILE"] = validation_profile
    else:
        environment.pop("SDLC_RUNNER_VALIDATION_PROFILE", None)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            arguments,
            cwd=workspace,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=command["timeout"],
            check=False,
            shell=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
        status = "passed" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = None
        status = "timeout"
    duration = round(time.perf_counter() - started, 6)
    profile: dict[str, Any] | None = None
    if profile_path.is_file() and not _is_redirect(profile_path):
        try:
            loaded_profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            status = "failed"
            stderr += b"invalid Delivery fixture profile\n"
        else:
            if isinstance(loaded_profile, dict):
                profile = loaded_profile
    try:
        _remove_tree_with_retries(worker_root)
        worker_cleanup = "passed" if not worker_root.exists() else "failed"
    except OSError as exc:
        worker_cleanup = "failed"
        stderr += f"worker cleanup failed: {type(exc).__name__}\n".encode("utf-8")
    failure_count, skipped_count = _result_counts(stdout, stderr)
    if status == "passed" and (
        failure_count not in {None, 0} or skipped_count not in {None, 0}
    ):
        status = "failed"
    if worker_cleanup != "passed":
        status = "failed"
        exit_code = exit_code if exit_code not in {None, 0} else 1
    return {
        "command_id": command_id,
        "logical_command_id": command.get("logical_command_id", command_id),
        "execution_class": command["execution_class"],
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "failure_count": failure_count,
        "skipped_count": skipped_count,
        "inventory_complete": status == "passed",
        "children": _profile_inventory(stdout, stderr, status == "passed"),
        "stdout": stdout,
        "stderr": stderr,
        "fixture_profile": profile,
        "worker_id": worker_root.name,
        "worker_cleanup": worker_cleanup,
        "not_run_reason": None,
    }


def _remove_tree_with_retries(path: Path, *, attempts: int = 6) -> None:
    """Remove a disposable tree after transient Windows file handles close."""

    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.05 * (2**attempt))


def _metrics_target(
    workspace: Path,
    value: str | None,
    *,
    allowed_missing_parent: Path | None = None,
) -> Path | None:
    if value is None:
        return None
    lexical = Path(value)
    if not lexical.is_absolute():
        lexical = workspace / lexical
    lexical = Path(os.path.abspath(lexical))
    current = lexical
    reached_workspace = False
    while True:
        if _is_redirect(current):
            raise ValueError("metrics output path is redirected")
        if current.resolve(strict=False) == workspace:
            reached_workspace = True
            break
        if current.parent == current:
            break
        current = current.parent
    candidate = lexical.resolve(strict=False)
    try:
        relative = candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("metrics output is outside the workspace") from exc
    if not reached_workspace:
        raise ValueError("metrics output path cannot be tied to the workspace")
    if not candidate.parent.is_dir() and candidate.parent != allowed_missing_parent:
        raise ValueError("metrics output parent does not exist")
    if candidate.exists() and (_is_redirect(candidate) or not stat.S_ISREG(candidate.lstat().st_mode)):
        raise ValueError("metrics output target is not a regular file")
    return candidate


def _bounded_directory_target(workspace: Path, value: str, *, root: Path) -> Path:
    lexical = Path(value)
    if not lexical.is_absolute():
        lexical = workspace / lexical
    lexical = Path(os.path.abspath(lexical))
    approved_root = Path(os.path.abspath(root)).resolve(strict=False)
    current = lexical
    reached_root = False
    while True:
        if _is_redirect(current):
            raise ValueError("evidence output path is redirected")
        if current.resolve(strict=False) == approved_root:
            reached_root = True
            break
        if current.parent == current:
            break
        current = current.parent
    candidate = lexical.resolve(strict=False)
    try:
        relative = candidate.relative_to(approved_root)
    except ValueError as exc:
        raise ValueError("evidence output is outside the approved path") from exc
    if not reached_root or not relative.parts:
        raise ValueError("evidence output cannot replace the approved root")
    if candidate.exists() and (not candidate.is_dir() or _is_redirect(candidate)):
        raise ValueError("evidence output target is not a regular directory")
    return candidate


def _load_validation_evidence():
    spec = importlib.util.spec_from_file_location(
        "project_knowledge_validation_evidence",
        VALIDATION_EVIDENCE_PATH,
    )
    if spec is None or spec.loader is None:
        raise OSError("validation evidence module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json_result(stdout: bytes) -> dict[str, Any]:
    try:
        value = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _result_counts(
    stdout: bytes, stderr: bytes = b""
) -> tuple[int | None, int | None]:
    value = _json_result(stdout)
    failed = value.get("failed")
    skipped = value.get("skipped")
    if failed is None and isinstance(value.get("summary"), dict):
        counts = value["summary"].get("counts", {})
        if isinstance(counts, dict):
            failed = counts.get("failed")
    if isinstance(failed, int) or isinstance(skipped, int):
        return (
            failed if isinstance(failed, int) else None,
            skipped if isinstance(skipped, int) else None,
        )
    unittest_output = stderr.decode("utf-8", errors="replace")
    if re.search(r"(?m)^Ran [0-9]+ tests? in ", unittest_output):
        skipped_match = re.search(r"skipped=([0-9]+)", unittest_output)
        skipped_value = int(skipped_match.group(1)) if skipped_match else 0
        if re.search(r"(?m)^OK(?: \(|$)", unittest_output):
            return 0, skipped_value
        failed_match = re.search(r"failures=([0-9]+)", unittest_output)
        errors_match = re.search(r"errors=([0-9]+)", unittest_output)
        return (
            sum(
                int(match.group(1))
                for match in (failed_match, errors_match)
                if match is not None
            ),
            skipped_value,
        )
    return None, None


def _execution_input(
    workspace: Path,
    scope: str,
    profile: str,
    jobs: int,
    commands: list[dict[str, Any]],
    *,
    ready_payload_sha256: str,
    ready_binding_source: str,
) -> dict[str, Any]:
    return {
        "schema": "validation-execution-input/v1",
        "cwd": str(workspace),
        "scope": scope,
        "profile": profile,
        "jobs": jobs,
        "ready_payload_sha256": ready_payload_sha256,
        "ready_binding_source": ready_binding_source,
        "git_snapshot": _git_snapshot(workspace),
        "commands": [
            {
                "command_id": item["command_id"],
                "logical_command_id": item.get(
                    "logical_command_id", item["command_id"]
                ),
                "arguments": item["arguments"],
                "timeout_seconds": item["timeout"],
                "execution_class": item.get("execution_class"),
            }
            for item in commands
        ],
    }


def _git_bytes(workspace: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            "Git snapshot failed: "
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    return completed.stdout


def _git_snapshot(workspace: Path) -> dict[str, Any]:
    head = _git_bytes(workspace, "rev-parse", "HEAD").decode("ascii").strip()
    status = _git_bytes(
        workspace, "status", "--porcelain=v1", "-z", "--untracked-files=all"
    )
    diff = _git_bytes(
        workspace,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "HEAD",
        "--",
    )
    tracked_changed = {
        value.decode("utf-8", errors="surrogateescape")
        for value in _git_bytes(
            workspace, "diff", "--name-only", "-z", "HEAD", "--"
        ).split(b"\0")
        if value
    }
    untracked = {
        value.decode("utf-8", errors="surrogateescape")
        for value in _git_bytes(
            workspace, "ls-files", "--others", "--exclude-standard", "-z"
        ).split(b"\0")
        if value
    }
    excluded_prefix = ".knowledge-test-tmp/"
    changed_paths = sorted(
        path
        for path in tracked_changed | untracked
        if path != ".knowledge-test-tmp" and not path.startswith(excluded_prefix)
    )
    untracked_manifest: list[dict[str, Any]] = []
    markdown_manifest: list[dict[str, Any]] = []
    for relative in changed_paths:
        candidate = workspace / Path(relative)
        if candidate.is_file() and not _is_redirect(candidate):
            raw = candidate.read_bytes()
            metadata = {
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
            if relative in untracked:
                untracked_manifest.append(metadata)
            if candidate.suffix.lower() == ".md":
                markdown_manifest.append(metadata)
        elif relative.lower().endswith(".md"):
            markdown_manifest.append({"path": relative, "deleted": True})
    return {
        "head_sha": head,
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "diff_sha256": hashlib.sha256(diff).hexdigest(),
        "changed_paths": changed_paths,
        "untracked_files": untracked_manifest,
        "changed_markdown": markdown_manifest,
    }


def _environment_identity() -> dict[str, Any]:
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


def _write_validation_evidence(
    evidence_root: Path,
    label: str,
    *,
    profile: str,
    execution_input: dict[str, Any],
    executions: list[dict[str, Any]],
    ready_payload_sha256: str,
    wall_duration_seconds: float | None = None,
) -> None:
    module = _load_validation_evidence()
    evidence_root.mkdir(parents=True, exist_ok=True)
    if _is_redirect(evidence_root):
        raise OSError("evidence output root is redirected")
    module.write_bundle(
        evidence_root,
        label,
        profile=profile,
        execution_input=execution_input,
        environment=_environment_identity(),
        ready_payload_sha256=ready_payload_sha256,
        executions=executions,
        wall_duration_seconds=wall_duration_seconds,
    )


def _profile_run(
    args: argparse.Namespace,
    *,
    workspace: Path,
    fixture_root: Path,
    metrics_path: Path | None,
    evidence_root: Path,
) -> int:
    commands = _profile_commands(
        _commands(args.scope, args.fixture_root), profile=args.profile
    )
    explicit_binding = args.ready_payload_sha256 or os.environ.get(
        "IMPLEMENTATION_READY_PAYLOAD_SHA256"
    )
    if explicit_binding:
        ready_payload_sha256 = explicit_binding
        ready_binding_source = (
            "cli" if args.ready_payload_sha256 is not None else "governed-environment"
        )
    else:
        ready_payload_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "schema": "runner-validation-contract/v1",
                    "scope": args.scope,
                    "profile": args.profile,
                    "commands": [item["command_id"] for item in commands],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        ready_binding_source = "unbound-runner-contract"
    execution_input = _execution_input(
        workspace,
        args.scope,
        args.profile,
        args.jobs,
        commands,
        ready_payload_sha256=ready_payload_sha256,
        ready_binding_source=ready_binding_source,
    )
    suite_started = time.perf_counter()
    if fixture_root.exists() or fixture_root.is_symlink():
        print("profile fixture root already exists", file=sys.stderr)
        return 2
    fixture_root.mkdir(parents=True)
    try:
        results = execute_profile_schedule(
            commands,
            jobs=args.jobs,
            executor=lambda command: execute_profile_item(
                command,
                workspace=workspace,
                fixture_root=fixture_root,
                fixture_argument=args.fixture_root,
                worker_index=int(command["worker_index"]),
                validation_profile=args.profile,
            ),
        )
    finally:
        try:
            _remove_tree_with_retries(fixture_root)
        except OSError:
            # Individual worker cleanup is already part of the pass/fail result.
            # Leave this bounded root in place so the caller can inspect evidence.
            pass
    wall_duration = time.perf_counter() - suite_started

    metrics: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    for command in commands:
        result = results[command["command_id"]]
        status = str(result.get("status"))
        metrics.append(
            {
                "command_id": command["command_id"],
                "logical_command_id": command.get(
                    "logical_command_id", command["command_id"]
                ),
                "execution_class": command["execution_class"],
                "status": status,
                "duration_seconds": result.get("duration_seconds"),
                "exit_code": result.get("exit_code"),
                "timeout_seconds": command["timeout"],
            }
        )
        executions.append(
            {
                **result,
                "logical_command_id": command.get(
                    "logical_command_id", command["command_id"]
                ),
                "execution_class": command["execution_class"],
                "inventory_complete": (
                    status == "passed"
                    and result.get("worker_cleanup") == "passed"
                ),
            }
        )
        if status == "not_run":
            continue
        outcome = {
            "command_id": command["command_id"],
            "exit_code": result.get("exit_code"),
            "stdout": (result.get("stdout") or b"").decode(
                "utf-8", errors="replace"
            ),
            "stderr": (result.get("stderr") or b"").decode(
                "utf-8", errors="replace"
            ),
        }
        if status == "timeout":
            outcome["timeout"] = True
        outcomes.append(outcome)

    passed = all(item["status"] == "passed" for item in metrics)
    functional = {
        "schema": "knowledge-suite-report/v1",
        "scope": args.scope,
        "outcome": "passed" if passed else "failed",
        "commands": outcomes,
    }
    try:
        _write_metrics(
            metrics_path,
            _metrics_report(args.scope, metrics, functional["outcome"]),
            create_parent=(
                metrics_path is not None and metrics_path.parent == fixture_root
            ),
        )
        _write_validation_evidence(
            evidence_root,
            args.run_label or f"validation-{time.time_ns()}",
            profile=args.profile,
            execution_input=execution_input,
            executions=executions,
            ready_payload_sha256=ready_payload_sha256,
            wall_duration_seconds=wall_duration,
        )
    except (OSError, ValueError, FileExistsError):
        functional["outcome"] = "failed"
        print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    stream = sys.stdout if passed else sys.stderr
    print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=stream)
    return 0 if passed else 1


def _metrics_report(scope: str, metrics: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    counts = {status: 0 for status in ("passed", "failed", "timeout", "not_run")}
    for item in metrics:
        counts[item["status"]] += 1
    return {
        "schema": "knowledge-suite-metrics/v1",
        "scope": scope,
        "outcome": outcome,
        "commands": metrics,
        "summary": {
            "counts": counts,
            "total_duration_seconds": round(
                sum(item["duration_seconds"] or 0.0 for item in metrics),
                6,
            ),
        },
    }


def _write_metrics(
    path: Path | None,
    report: dict[str, Any],
    *,
    create_parent: bool = False,
) -> None:
    if path is None:
        return
    if create_parent:
        path.parent.mkdir(exist_ok=True)
        if _is_redirect(path.parent):
            raise OSError("metrics output parent is redirected")
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["related", "all"], required=True)
    parser.add_argument("--fixture-root", type=Path, default=Path(".knowledge-test-tmp"))
    parser.add_argument("--metrics-output")
    parser.add_argument("--profile", choices=["local", "release"])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--evidence-root")
    parser.add_argument("--run-label")
    parser.add_argument("--ready-payload-sha256")
    args = parser.parse_args(argv)
    workspace = Path.cwd().resolve()
    fixture_root = args.fixture_root.resolve()
    approved_fixture_root = workspace / ".knowledge-test-tmp"
    if args.profile is None:
        fixture_is_valid = (
            fixture_root.parent == workspace
            and fixture_root.name == ".knowledge-test-tmp"
        )
    else:
        try:
            fixture_root.relative_to(approved_fixture_root)
            fixture_is_valid = fixture_root != approved_fixture_root
        except ValueError:
            fixture_is_valid = False
    if not fixture_is_valid:
        print("fixture root is outside the approved path", file=sys.stderr)
        return 2
    if args.jobs < 1:
        print("jobs must be at least one", file=sys.stderr)
        return 2
    if (args.profile is None) != (args.evidence_root is None):
        print("profile and evidence root must be provided together", file=sys.stderr)
        return 2
    evidence_root: Path | None = None
    if args.profile is not None:
        try:
            evidence_root = _bounded_directory_target(
                workspace,
                args.evidence_root,
                root=approved_fixture_root,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.ready_payload_sha256 is not None and (
        len(args.ready_payload_sha256) != 64
        or any(character not in "0123456789abcdef" for character in args.ready_payload_sha256)
    ):
        print("Ready payload digest must be 64 lowercase hexadecimal characters", file=sys.stderr)
        return 2
    try:
        metrics_path = _metrics_target(
            workspace,
            args.metrics_output,
            allowed_missing_parent=fixture_root,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.profile is not None:
        try:
            evidence_root.relative_to(fixture_root)
        except ValueError:
            pass
        else:
            print("evidence root cannot be inside the disposable fixture root", file=sys.stderr)
            return 2
        return _profile_run(
            args,
            workspace=workspace,
            fixture_root=fixture_root,
            metrics_path=metrics_path,
            evidence_root=evidence_root,
        )
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    outcomes: list[dict[str, Any]] = []
    commands = _commands(args.scope, args.fixture_root)
    evidence_executions: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = [
        {
            "command_id": item["command_id"],
            "status": "not_run",
            "duration_seconds": None,
            "exit_code": None,
            "timeout_seconds": item["timeout"],
        }
        for item in commands
    ]
    metrics_parent_is_fixture = (
        metrics_path is not None and metrics_path.parent == fixture_root
    )
    for index, item in enumerate(commands):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                item["arguments"],
                cwd=workspace,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=item["timeout"],
                check=False,
                shell=False,
            )
            outcome = {
                "command_id": item["command_id"],
                "exit_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="replace"),
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            }
            metrics[index].update(
                {
                    "status": "passed" if completed.returncode == 0 else "failed",
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "exit_code": completed.returncode,
                }
            )
            failure_count, skipped_count = _result_counts(completed.stdout)
            evidence_executions.append(
                {
                    "command_id": item["command_id"],
                    "status": "passed" if completed.returncode == 0 else "failed",
                    "exit_code": completed.returncode,
                    "duration_seconds": metrics[index]["duration_seconds"],
                    "failure_count": failure_count,
                    "skipped_count": skipped_count,
                    "inventory_complete": completed.returncode == 0,
                    "children": [
                        {
                            "command_id": child.get("command_id"),
                            "status": (
                                "passed"
                                if child.get("exit_code") == 0
                                else "failed"
                            ),
                        }
                        for child in _json_result(completed.stdout).get("commands", [])
                        if isinstance(child, dict) and child.get("command_id")
                    ],
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
        except subprocess.TimeoutExpired as exc:
            timeout_stdout = exc.stdout or b""
            timeout_stderr = exc.stderr or b""
            outcome = {
                "command_id": item["command_id"],
                "exit_code": None,
                "stdout": timeout_stdout.decode("utf-8", errors="replace"),
                "stderr": timeout_stderr.decode("utf-8", errors="replace"),
                "timeout": True,
            }
            metrics[index].update(
                {
                    "status": "timeout",
                    "duration_seconds": round(time.perf_counter() - started, 6),
                    "exit_code": None,
                }
            )
            evidence_executions.append(
                {
                    "command_id": item["command_id"],
                    "status": "timeout",
                    "exit_code": None,
                    "duration_seconds": metrics[index]["duration_seconds"],
                    "failure_count": None,
                    "skipped_count": None,
                    "inventory_complete": False,
                    "children": [],
                    "stdout": timeout_stdout,
                    "stderr": timeout_stderr,
                }
            )
        outcomes.append(outcome)
        if outcome["exit_code"] != 0:
            for remaining in commands[index + 1 :]:
                evidence_executions.append(
                    {
                        "command_id": remaining["command_id"],
                        "status": "not_run",
                        "exit_code": None,
                        "duration_seconds": None,
                        "failure_count": None,
                        "skipped_count": None,
                        "inventory_complete": False,
                        "children": [],
                        "not_run_reason": "fail_fast",
                        "stdout": b"",
                        "stderr": b"",
                    }
                )
            functional = {
                "schema": "knowledge-suite-report/v1",
                "scope": args.scope,
                "outcome": "failed",
                "commands": outcomes,
            }
            try:
                _write_metrics(
                    metrics_path,
                    _metrics_report(args.scope, metrics, "failed"),
                    create_parent=metrics_parent_is_fixture,
                )
                if evidence_root is not None:
                    _write_validation_evidence(
                        evidence_root,
                        args.run_label or f"validation-{time.time_ns()}",
                        profile=args.profile,
                        execution_input=execution_input,
                        executions=evidence_executions,
                        ready_payload_sha256=args.ready_payload_sha256,
                    )
            except OSError:
                print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
                return 2
            print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 1
    functional = {
        "schema": "knowledge-suite-report/v1",
        "scope": args.scope,
        "outcome": "passed",
        "commands": outcomes,
    }
    try:
        _write_metrics(
            metrics_path,
            _metrics_report(args.scope, metrics, "passed"),
            create_parent=metrics_parent_is_fixture,
        )
        if evidence_root is not None:
            _write_validation_evidence(
                evidence_root,
                args.run_label or f"validation-{time.time_ns()}",
                profile=args.profile,
                execution_input=execution_input,
                executions=evidence_executions,
                ready_payload_sha256=args.ready_payload_sha256,
            )
    except OSError:
        functional["outcome"] = "failed"
        print(json.dumps(functional, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(functional, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
