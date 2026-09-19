#!/usr/bin/env python3
"""Megin Workflow v3 portable controller.

The v3 controller deliberately keeps the runtime dependency-free.  It owns the
workflow contract and evidence transitions; a target repository owns its test
runner and its product code.  The older ``megin.py`` remains available as a
read-only migration reference for v2 records, while the plugin entry points to
this module for all new work.
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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from gherkin import GherkinError, flatten_scenarios, load_features, parse_feature
except ImportError:  # pragma: no cover - supports package and direct execution
    from .gherkin import GherkinError, flatten_scenarios, load_features, parse_feature


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


SCHEMA = "delivery-run/v3"
CONFIG_SCHEMA = "megin-project/v3"
PLUGIN_VERSION = "0.4.0"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DELIVERY_SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "delivery-run-v3.schema.json"
WORK_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
SHA1_RE = re.compile(r"^[a-f0-9]{40}$")
TASK_CLASSES = ("read_only", "small", "large", "bug")
WORKSPACE_MODES = ("current", "worktree")
PHASES = ("exploration", "planning", "implementation", "review", "verification", "acceptance", "knowledge", "delivery")
READ_ONLY_MARKERS = (
    "explain", "review", "evaluate", "inspect", "assess", "audit", "check", "plan", "advice",
    "read-only", "without changing", "without changes", "no changes", "查詢", "說明", "解釋",
    "檢視", "評估", "審查", "分析", "計畫書", "唯讀", "不修改", "不需修改", "只檢查",
)
MUTATION_MARKERS = (
    "build", "implement", "fix", "update", "modify", "make changes", "create", "add", "write", "refactor",
    "repair", "execute", "改善", "修正", "修改", "新增", "開發", "實作", "執行",
)
SCENARIO_STATUSES = ("passed", "failed", "undefined", "skipped", "error", "not_run", "manual_pending")


class MeginError(RuntimeError):
    """A fail-closed error that includes the next human action."""


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode("utf-8"))


def digest_json(value: Any) -> str:
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def redact(value: str) -> str:
    value = re.sub(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+", r"\1<redacted>", value)
    value = re.sub(r"(?i)(\b(?:token|secret|password|passwd|api[_-]?key)\s*[:=]\s*)[^\s,;]+", r"\1<redacted>", value)
    return value


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the temporary name short so Windows can still create it when the
    # persistent state root and repository identity already make the directory
    # path long.  The random suffix supplied by mkstemp preserves uniqueness.
    descriptor, temporary = tempfile.mkstemp(prefix=".megin-", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json_dump(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MeginError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MeginError(f"JSON record must be an object: {path}")
    return value


def run_process(command: Sequence[str], cwd: Path, *, timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command), cwd=str(cwd), text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout, check=check,
        )
    except subprocess.TimeoutExpired as exc:
        raise MeginError(f"command timed out after {timeout}s: {' '.join(command)}") from exc
    except OSError as exc:
        raise MeginError(f"cannot execute {' '.join(command)}: {exc}") from exc


def run_approved_command(command: str, cwd: Path, *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run a plan-approved shell command with consistent quoting semantics."""
    if os.name == "nt":
        # Approved commands use POSIX-compatible quoting (for example, unittest
        # discovery patterns).  cmd.exe treats single quotes literally, while
        # Windows PowerShell preserves the intended shell behavior.
        for executable in ("powershell.exe", "pwsh.exe", "pwsh"):
            shell = shutil.which(executable)
            if shell:
                return run_process(
                    (shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command),
                    cwd,
                    timeout=timeout,
                )
    try:
        return subprocess.run(
            command, cwd=str(cwd), shell=True, text=True, encoding="utf-8", errors="replace",
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise MeginError(f"command timed out after {timeout}s: {command}") from exc
    except OSError as exc:
        raise MeginError(f"cannot execute approved command: {exc}") from exc


def git(repo: Path, *arguments: str, check: bool = True, timeout: int = 120) -> str:
    result = run_process(("git", *arguments), repo, timeout=timeout, check=False)
    if check and result.returncode != 0:
        message = redact((result.stdout or "") + (result.stderr or "")).strip()
        raise MeginError(f"git {' '.join(arguments)} failed ({result.returncode}): {message}")
    return result.stdout or ""


def require_git_repo(value: str | Path) -> Path:
    repo = Path(value).expanduser().resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        raise MeginError(f"not a Git repository: {repo}")
    return repo


def repo_identity(repo: Path) -> str:
    return digest_bytes(str(repo.resolve()).encode("utf-8"))


def current_branch(repo: Path) -> str:
    return git(repo, "branch", "--show-current").strip() or "HEAD"


def head_sha(repo: Path) -> str:
    value = git(repo, "rev-parse", "HEAD").strip()
    if not SHA1_RE.fullmatch(value):
        raise MeginError(f"Git HEAD is not a commit SHA: {value!r}")
    return value


def default_base_branch(repo: Path) -> str:
    symbolic = git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", check=False).strip()
    if symbolic.startswith("refs/remotes/"):
        remote_branch = symbolic.removeprefix("refs/remotes/")
        if "/" in remote_branch:
            return remote_branch.split("/", 1)[1]

    local = [
        candidate for candidate in ("main", "master")
        if git(repo, "show-ref", "--verify", f"refs/heads/{candidate}", check=False).strip()
    ]
    if len(local) == 1:
        return local[0]
    if len(local) > 1:
        raise MeginError("cannot resolve the default base branch because both main and master exist; pass --base-branch")

    remote = [
        candidate for candidate in ("main", "master")
        if git(repo, "show-ref", "--verify", f"refs/remotes/origin/{candidate}", check=False).strip()
    ]
    if len(remote) == 1:
        return remote[0]
    if len(remote) > 1:
        raise MeginError("cannot resolve the default base branch because origin has both main and master; pass --base-branch")
    raise MeginError("cannot resolve a default base branch; pass --base-branch explicitly")


def status_paths(repo: Path) -> list[str]:
    raw = git(repo, "status", "--porcelain=v1", "-z", "-uall", check=True)
    result: list[str] = []
    for item in raw.split("\0"):
        if not item:
            continue
        value = item[3:] if len(item) >= 3 else item
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        result.append(value.replace("\\", "/"))
    return sorted(set(result))


def snapshot(repo: Path) -> str:
    entries: list[dict[str, str]] = []
    for path in status_paths(repo):
        absolute = repo / path
        if absolute.is_file():
            entries.append({"path": path, "sha256": digest_bytes(absolute.read_bytes())})
        else:
            entries.append({"path": path, "sha256": "<missing>"})
    return digest_json({
        "repo_id": repo_identity(repo),
        "branch": current_branch(repo),
        "head": head_sha(repo),
        "entries": entries,
    })


def normalize_path(value: str) -> str:
    item = value.replace("\\", "/").strip()
    if not item:
        raise MeginError("approved paths cannot be empty")
    if item.startswith("/") or re.match(r"^[A-Za-z]:/", item) or item == ".." or item.startswith("../") or "/../" in item:
        raise MeginError(f"approved path escapes the repository: {value}")
    return "." if item == "." else item.rstrip("/")


def path_allowed(path: str, allowed: Iterable[str]) -> bool:
    normalized = normalize_path(path)
    for item in allowed:
        rule = normalize_path(item)
        if rule == "." or normalized == rule or normalized.startswith(rule + "/"):
            return True
    return False


def state_root(repo: Path) -> Path:
    configured = os.environ.get("MEGIN_STATE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return (base / "Megin" / "state").resolve()
    return (Path.home() / ".local" / "state" / "megin").resolve()


def state_path(repo: Path, work_id: str) -> Path:
    return state_root(repo) / repo_identity(repo) / f"{work_id}.json"


def evidence_root(repo: Path, work_id: str) -> Path:
    return state_root(repo) / repo_identity(repo) / work_id / "evidence"


def workspace_lock_path(repo: Path) -> Path:
    return state_root(repo) / repo_identity(repo) / "current-workspace.lock"


def acquire_workspace_lock(repo: Path, state: dict[str, Any]) -> Path:
    path = workspace_lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "megin-current-workspace-lock/v1",
        "repo_id": repo_identity(repo),
        "work_id": state["work_id"],
        "base_sha": state["repo"]["base_sha"],
        "created_at": now(),
    }
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        owner = "unknown"
        try:
            existing = read_json(path)
            owner = str(existing.get("work_id") or owner)
        except MeginError:
            owner = "unreadable-lock"
        raise MeginError(f"current workspace is already owned by Work ID {owner}; resolve it explicitly before retrying") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json_dump(payload))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


def release_workspace_lock(repo: Path, work_id: str) -> None:
    path = workspace_lock_path(repo)
    if not path.exists():
        return
    try:
        owner = read_json(path).get("work_id")
    except MeginError:
        return
    if owner == work_id:
        path.unlink(missing_ok=True)


def ensure_workspace_binding(state: dict[str, Any], worktree: Path, *, require_base_head: bool = True) -> None:
    expected = state.get("workspace", {})
    expected_path = Path(str(expected.get("worktree", ""))).expanduser().resolve()
    if expected_path != worktree.resolve():
        raise MeginError("current workspace does not match the approved Work ID")
    branch = current_branch(worktree)
    if branch != expected.get("branch"):
        raise MeginError("current branch does not match the approved Work ID; re-run review and verification")
    if require_base_head and head_sha(worktree) != expected.get("base_sha"):
        raise MeginError("workspace HEAD changed after approval; create a fresh plan instead of continuing")


def parse_scenario_evidence(raw: str, scenarios: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MeginError(f"scenario evidence is not valid JSON: {exc}") from exc
    values: Any = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise MeginError("scenario evidence must be a JSON array or an object with a scenarios array")
    known = {str(item.get("id")): item for item in scenarios}
    evidence: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, dict):
            raise MeginError("scenario evidence entries must be objects")
        identifier = str(item.get("id") or item.get("scenario_id") or "")
        if identifier not in known:
            raise MeginError(f"scenario evidence references an unknown scenario: {identifier}")
        if identifier in evidence:
            raise MeginError(f"scenario evidence contains duplicate results for {identifier}")
        status = str(item.get("status") or "").casefold()
        if status == "pass":
            status = "passed"
        if status not in SCENARIO_STATUSES:
            raise MeginError(f"scenario evidence has an unsupported status for {identifier}: {status}")
        evidence[identifier] = {
            "id": identifier,
            "status": status,
            "reason": redact(str(item.get("reason") or "runner evidence")),
        }
    results: list[dict[str, Any]] = []
    failed = False
    for scenario in scenarios:
        identifier = str(scenario["id"])
        if not scenario.get("automatic", True):
            results.append({"id": identifier, "status": "manual_pending", "reason": "scenario is reserved for human acceptance"})
            continue
        result = evidence.get(identifier)
        if result is None:
            results.append({"id": identifier, "status": "not_run", "reason": "runner returned no result for this scenario"})
            failed = True
            continue
        results.append(result)
        if result["status"] != "passed":
            failed = True
    return results, failed


def knowledge_snapshot(worktree: Path, paths: Iterable[str]) -> str:
    entries: list[dict[str, str]] = []
    for value in sorted(set(normalize_path(item) for item in paths)):
        target = worktree / value
        entries.append({
            "path": value,
            "sha256": digest_bytes(target.read_bytes()) if target.is_file() else "<missing>",
        })
    return digest_json(entries)


def validate_work_id(value: str) -> str:
    if not WORK_ID_RE.fullmatch(value):
        raise MeginError("work ID must contain lowercase letters, digits, and single hyphens")
    return value


def validate_branch_prefix(value: str) -> str:
    cleaned = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,39}", cleaned) or cleaned.endswith("/"):
        raise MeginError("branch prefix must be a short Git-safe path")
    return cleaned


def make_work_id(request: str) -> str:
    words = re.findall(r"[a-z0-9]+", request.casefold())
    prefix = "-".join(words[:3]) or "change"
    return validate_work_id(f"{prefix}-{digest_bytes(request.encode('utf-8'))[:8]}")


def load_config(repo: Path) -> dict[str, Any] | None:
    path = repo / ".megin" / "config.json"
    if not path.exists():
        return None
    config = read_json(path)
    if config.get("schema") not in (CONFIG_SCHEMA, "megin-project/v1"):
        raise MeginError(f"unsupported Megin configuration schema: {config.get('schema')!r}")
    return config


def ensure_megin_excluded(repo: Path) -> None:
    """Keep opt-in configuration out of product changes and commits."""

    git_dir = git(repo, "rev-parse", "--git-dir").strip()
    info = Path(git_dir)
    if not info.is_absolute():
        info = (repo / info).resolve()
    exclude = info / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    lines = existing.splitlines()
    if ".megin/" not in lines:
        suffix = "" if not existing or existing.endswith("\n") else "\n"
        exclude.write_text(existing + suffix + ".megin/\n", encoding="utf-8")


def fetch_base(repo: Path, branch: str, remote: str | None) -> str:
    if remote:
        result = run_process(("git", "fetch", "--quiet", remote, branch), repo, timeout=180, check=False)
        if result.returncode != 0:
            raise MeginError(f"fetch failed for {remote}/{branch}: {redact((result.stdout or '') + (result.stderr or '')).strip()}")
    candidates = [branch]
    if remote:
        candidates.insert(0, f"{remote}/{branch}")
    if not remote and git(repo, "show-ref", "--verify", f"refs/remotes/origin/{branch}", check=False).strip():
        candidates.insert(0, f"origin/{branch}")
    for candidate in candidates:
        result = run_process(("git", "rev-parse", candidate), repo, check=False)
        if result.returncode == 0 and SHA1_RE.fullmatch(result.stdout.strip()):
            return result.stdout.strip()
    raise MeginError(f"base branch does not resolve to a commit: {branch}; refusing to use the current HEAD")


def classify(request: str, task_class: str | None = None) -> dict[str, Any]:
    text = request.strip()
    folded = text.casefold()
    explicit_read_only = any(word in folded for word in READ_ONLY_MARKERS)
    mutation_requested = any(word in folded for word in MUTATION_MARKERS)
    read_only_intent = explicit_read_only and not mutation_requested
    bug_words = ("bug", "error", "regression", "錯誤", "異常", "壞掉", "失效")
    large_words = ("architecture", "cross-module", "migration", "system", "contract", "schema", "framework", "架構", "跨模組", "遷移", "契約", "綱要")
    if read_only_intent:
        chosen = "read_only"
        reason = "read-only intent cannot be overridden by an explicit mutating class"
    elif task_class:
        chosen = task_class
        reason = "explicit task class"
    elif any(word in folded for word in bug_words):
        chosen = "bug"
        reason = "keyword and impact routing"
    elif any(word in folded for word in large_words):
        chosen = "large"
        reason = "keyword and impact routing"
    else:
        chosen = "small"
        reason = "keyword and impact routing"
    if chosen not in TASK_CLASSES:
        raise MeginError(f"unknown task class: {chosen}")
    return {
        "task_class": chosen,
        "reason": reason,
        "needs_clarification": len(text) < 8,
        "read_only": chosen == "read_only",
    }


def make_behavior_contract(repo: Path, args: argparse.Namespace, work_id: str) -> dict[str, Any]:
    feature_files = list(getattr(args, "feature_file", None) or [])
    if feature_files:
        try:
            contracts, digests = load_features(feature_files)
        except GherkinError as exc:
            raise MeginError(str(exc)) from exc
        scenarios = flatten_scenarios(contracts)
        features = [
            {"path": str(Path(item).expanduser().resolve()), "sha256": digest}
            for item, digest in zip(feature_files, digests)
        ]
    else:
        scenario_id = f"BDD-{work_id.upper()}-001"
        title = str(getattr(args, "request", "requested behavior")).strip() or "requested behavior"
        scenarios = [{
            "id": scenario_id,
            "title": title,
            "source": "generated:chat",
            "gherkin": f"Feature: Megin requested behavior\n\nScenario: [{scenario_id}] {title}\n  Given the approved repository baseline is available\n  When the requested behavior is implemented\n  Then the approved acceptance criteria are observable",
            "steps": [
                "Given the approved repository baseline is available",
                "When the requested behavior is implemented",
                "Then the approved acceptance criteria are observable",
            ],
            "automatic": True,
            "manual": [],
        }]
        features = [{"path": "generated:chat", "sha256": digest_text(title)}]
    manual: list[dict[str, str]] = []
    for item in getattr(args, "manual_step", None) or []:
        parts = item.split("|", 4)
        if len(parts) != 5:
            raise MeginError("--manual-step must be scenario-id|path|environment|operation|expected")
        manual.append({
            "scenario_id": parts[0], "path": parts[1], "environment": parts[2],
            "operation": parts[3], "expected": parts[4],
        })
    scenario_ids = {str(item["id"]) for item in scenarios}
    for item in manual:
        if item["scenario_id"] not in scenario_ids:
            raise MeginError(f"manual acceptance references unknown scenario: {item['scenario_id']}")
    for scenario in scenarios:
        scenario["manual"] = [item["operation"] for item in manual if item["scenario_id"] == scenario["id"]]
    plan_version = getattr(args, "plan_version", None) or "plan-1"
    payload = {
        "version": 1,
        "plan_version": plan_version,
        "features": features,
        "scenarios": scenarios,
        "manual_acceptance": manual,
    }
    payload["digest"] = digest_json(payload)
    return payload


def build_scope(repo: Path, args: argparse.Namespace, config: dict[str, Any] | None) -> dict[str, Any]:
    allowed = [normalize_path(item) for item in (getattr(args, "allowed_path", None) or (config or {}).get("allowed_paths", []) or ["."])]
    commands = list(getattr(args, "test_command", None) or (config or {}).get("test_commands", []) or ["python -m unittest discover"])
    if any(not item.strip() for item in commands):
        raise MeginError("test commands cannot be empty")
    scenario_command = getattr(args, "scenario_command", None)
    if scenario_command is None:
        scenario_command = (config or {}).get("scenario_command")
    if scenario_command is not None and not str(scenario_command).strip():
        raise MeginError("scenario command cannot be empty")
    knowledge = [normalize_path(item) for item in (getattr(args, "knowledge_path", None) or (config or {}).get("knowledge_scope", []))]
    if any(not path_allowed(item, allowed) for item in knowledge):
        raise MeginError("knowledge scope must be contained in the approved allowed paths")
    acceptance = [redact(item) for item in (getattr(args, "acceptance", None) or [getattr(args, "request", "approved behavior")])]
    base_branch = getattr(args, "base_branch", None) or (config or {}).get("base_branch") or default_base_branch(repo)
    remote = getattr(args, "remote", None)
    if remote is None:
        remote = (config or {}).get("remote")
    return {
        "allowed_paths": sorted(set(allowed)),
        "test_commands": commands,
        "scenario_command": scenario_command,
        "knowledge_scope": sorted(set(knowledge)),
        "acceptance": acceptance,
        "publication": {
            "base_branch": base_branch,
            "remote": remote,
            "workspace_mode": getattr(args, "workspace_mode", None) or (config or {}).get("workspace_mode") or "current",
            "branch_prefix": validate_branch_prefix(getattr(args, "branch_prefix", None) or (config or {}).get("branch_prefix") or "feat"),
            "title": redact(getattr(args, "title", None) or getattr(args, "request", "Megin delivery"))[:200],
        },
    }


def make_design(repo: Path, args: argparse.Namespace, contract: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    summary = redact(getattr(args, "design_summary", None) or getattr(args, "request", "Approved behavior"))
    file_details = [{"path": path, "purpose": "approved implementation or test boundary"} for path in scope["allowed_paths"]]
    if getattr(args, "design_file", None):
        path = Path(args.design_file).expanduser().resolve()
        if not path.exists():
            raise MeginError(f"design file does not exist: {path}")
        try:
            design_value: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(design_value, dict):
                summary = redact(str(design_value.get("summary") or design_value.get("goal") or summary))
                file_details = design_value.get("file_details") or file_details
        except (OSError, UnicodeError, json.JSONDecodeError):
            summary = redact(path.read_text(encoding="utf-8"))[:4000]
    payload = {
        "chat_summary": summary,
        "file_details": file_details,
        "decisions": ["Use one plan approval for the current behavior contract and scope", "Keep product changes uncommitted until human acceptance"],
        "interfaces": ["CLI delivery-run/v3 state", "approved Gherkin scenarios", "target repository test commands"],
        "failure_modes": ["scope or base drift blocks the transition", "failed verification returns to implementation", "knowledge conflicts block promotion"],
        "implementation_strategy": "Dispatch dependency-ordered tasks to one writer at a time, then use a fresh read-only reviewer for each task and the integrated result.",
        "verification": list(scope["test_commands"]),
        "plan_version": contract["plan_version"],
    }
    payload["digest"] = digest_json(payload)
    return payload


def candidate_digest(state: dict[str, Any]) -> str:
    return digest_json({
        "work_id": state["work_id"], "task": state["task"], "exploration": state["exploration"],
        "behavior_contract": state["behavior_contract"], "design": state["design"],
        "scope": state["approval"]["scope"],
    })


def event(state: dict[str, Any], kind: str, **details: Any) -> None:
    state.setdefault("events", []).append({"sequence": len(state.get("events", [])) + 1, "at": now(), "kind": kind, **details})


def save_state(state: dict[str, Any], path: Path) -> None:
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = now()
    write_json_atomic(path, state)


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema") != SCHEMA or state.get("version") != 3:
        raise MeginError("state is not a delivery-run/v3 record; migrate the historical run into a new Work ID")
    validate_work_id(str(state.get("work_id", "")))
    if state.get("plugin") != "megin":
        raise MeginError("state is not owned by Megin")
    for key in ("repo", "task", "behavior_contract", "design", "approval", "workspace", "verification", "human_acceptance", "knowledge", "publication"):
        if not isinstance(state.get(key), dict):
            raise MeginError(f"v3 state is missing {key}")
    if state["approval"].get("candidate_digest") != candidate_digest(state):
        raise MeginError("approved candidate changed; return to planning and create a new Work ID")
    if state["approval"].get("status") == "approved" and not state["approval"].get("approved_at"):
        raise MeginError("approved v3 state has no approval timestamp")
    if state["task"].get("task_class") == "bug":
        assessment = state["task"].get("diagnosis_assessment")
        if not isinstance(assessment, dict) or assessment.get("disposition") not in ("confirmed", "likely"):
            raise MeginError("bug state has no valid read-only diagnosis assessment")
        assessment_path = Path(str(assessment.get("path", ""))).expanduser().resolve()
        if not assessment_path.is_file() or digest_bytes(assessment_path.read_bytes()) != assessment.get("sha256"):
            raise MeginError("bug diagnosis evidence is missing or drifted")


def load_state(repo: Path, work_id: str) -> tuple[dict[str, Any], Path]:
    path = state_path(repo, validate_work_id(work_id))
    if not path.exists():
        raise MeginError(f"no Megin v3 state for Work ID {work_id}: {path}")
    state = read_json(path)
    validate_state(state)
    if state.get("repo", {}).get("repo_id") != repo_identity(repo):
        raise MeginError("state belongs to a different repository")
    return state, path


def make_state(repo: Path, work_id: str, args: argparse.Namespace, classification: dict[str, Any], config: dict[str, Any] | None) -> dict[str, Any]:
    scope = build_scope(repo, args, config)
    base_branch = scope["publication"]["base_branch"]
    base_sha = fetch_base(repo, base_branch, scope["publication"].get("remote"))
    contract = make_behavior_contract(repo, args, work_id)
    design = make_design(repo, args, contract, scope)
    unresolved = list(getattr(args, "unresolved_question", None) or [])
    task_class = classification["task_class"]
    if task_class == "bug" and not getattr(args, "diagnosis", None):
        unresolved.append("Provide a confirmed or likely diagnosis before repair.")
    diagnosis_assessment: dict[str, Any] | None = None
    if task_class == "bug" and getattr(args, "diagnosis_file", None):
        assessment_path = Path(args.diagnosis_file).expanduser().resolve()
        assessment = read_json(assessment_path)
        if assessment.get("request_sha256") != digest_text(args.request) or assessment.get("disposition") not in ("confirmed", "likely"):
            raise MeginError("bug diagnosis evidence does not match the request")
        diagnosis_assessment = {
            "path": str(assessment_path), "sha256": digest_bytes(assessment_path.read_bytes()),
            "disposition": assessment.get("disposition"), "hypothesis": assessment.get("hypothesis"),
            "evidence_path": assessment.get("evidence_path"), "output_sha256": assessment.get("output_sha256"),
        }
        unresolved = [item for item in unresolved if item != "Provide a confirmed or likely diagnosis before repair."]
    task = {
        "request": redact(args.request), "request_sha256": digest_bytes(args.request.encode("utf-8")),
        "task_class": task_class, "repair_class": getattr(args, "repair_class", None),
        "classification": classification, "diagnosis": (diagnosis_assessment or {}).get("disposition") or getattr(args, "diagnosis", None), "diagnosis_assessment": diagnosis_assessment, "source_refs": list(getattr(args, "source", None) or []),
    }
    scenarios = contract["scenarios"]
    requested_tasks = list(getattr(args, "task", None) or [])
    if not requested_tasks:
        requested_tasks = [design["chat_summary"]]
    task_records: list[dict[str, Any]] = []
    for index, title in enumerate(requested_tasks, 1):
        task_records.append({
            "id": f"task-{index:02d}", "title": redact(title),
            "status": "pending", "depends_on": [f"task-{index - 1:02d}"] if index > 1 else [], "allowed_paths": scope["allowed_paths"],
            "acceptance": scope["acceptance"], "scenario_ids": [str(item["id"]) for item in scenarios],
            "test_commands": scope["test_commands"], "writer": None, "writer_session": None,
            "reviewer": None, "reviewer_session": None, "review_round": 0, "findings": [],
        })
    state: dict[str, Any] = {
        "schema": SCHEMA, "version": 3, "plugin": "megin", "plugin_version": PLUGIN_VERSION,
        "work_id": work_id, "revision": 0,
        "repo": {"repo_id": repo_identity(repo), "path": str(repo), "base_branch": base_branch, "base_sha": base_sha, "remote": scope["publication"].get("remote")},
        "task": task,
        "exploration": {"sources": list(getattr(args, "source", None) or []), "questions": unresolved, "answers": [], "unresolved": unresolved, "completed_at": None if unresolved else now()},
        "behavior_contract": contract,
        "design": design,
        "approval": {"policy": "plan", "status": "pending", "candidate_revision": "candidate-1", "plan_version": contract["plan_version"], "approved_at": None, "approved_by": None, "response": None, "candidate_digest": "", "refs": [], "scope": scope},
        "workspace": {"mode": scope["publication"]["workspace_mode"], "worktree": str(repo), "branch": current_branch(repo), "base_sha": base_sha, "created_at": now()},
        "phase": "exploration" if unresolved else "planning",
        "status": "awaiting_clarification" if unresolved else "awaiting_approval",
        "tasks": task_records, "assignments": [],
        "review": {"overall": "pending", "per_task": {}, "findings": [], "no_progress_count": 0, "snapshot": None},
        "verification": {"status": "not_run", "commands": [], "scenario_results": [], "snapshot": None, "record_sha256": None},
        "human_acceptance": {"status": "pending", "version": "acceptance-1", "response": None, "checked_scenarios": [], "observed": [], "snapshot": None, "accepted_at": None},
        "knowledge": {
            "scope": scope["knowledge_scope"], "status": "pending" if scope["knowledge_scope"] else "not_needed",
            "sources": list(getattr(args, "source", None) or []), "conflicts": [], "candidate_path": None,
            "promoted_at": None, "reviewed_snapshot": None, "pre_snapshot": None, "post_snapshot": None,
            "validation": None,
        },
        "publication": {"state": "not_ready", "commit_sha": None, "changed_paths": [], "suggested_commit": None},
        "events": [], "next_action": "resolve the recorded exploration questions" if unresolved else "provide the plan approval response",
        "created_at": now(), "updated_at": now(),
    }
    state["approval"]["candidate_digest"] = candidate_digest(state)
    event(state, "candidate_created", phase=state["phase"], status=state["status"])
    return state


def state_summary(state: dict[str, Any], path: Path) -> dict[str, Any]:
    current = next((item for item in state.get("tasks", []) if item.get("status") in ("active", "awaiting_review", "needs_revision")), None)
    return {
        "schema": state["schema"], "version": state["version"], "work_id": state["work_id"], "state_path": str(path),
        "task_class": state["task"].get("task_class"), "phase": state.get("phase"), "status": state.get("status"),
        "next_action": state.get("next_action"), "plan_version": state["design"].get("plan_version"),
        "approval": state["approval"].get("status"), "approval_policy": state["approval"].get("policy"),
        "workspace": state.get("workspace"), "current": current, "tasks": state.get("tasks", []),
        "review": state.get("review"), "verification": state.get("verification"),
        "human_acceptance": state.get("human_acceptance"), "knowledge": state.get("knowledge"),
        "publication": state.get("publication"), "chat_summary": state["design"].get("chat_summary"),
        "file_details": state["design"].get("file_details"), "behavior_contract": state["behavior_contract"],
    }


def emit(value: Any, args: argparse.Namespace) -> None:
    if getattr(args, "text", False):
        if isinstance(value, dict):
            print("\n".join(f"{key}: {json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else item}" for key, item in value.items()))
        else:
            print(value)
    else:
        print(json_dump(value), end="")


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Run a supplied symptom command without creating a delivery workspace."""

    repo = require_git_repo(args.repo)
    result = subprocess.run(args.diagnosis_command, cwd=str(repo), shell=True, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=300)
    raw = redact((result.stdout or "") + (result.stderr or ""))
    request_sha = digest_text(args.request)
    record_id = digest_json({"repo": repo_identity(repo), "request": request_sha, "command": args.diagnosis_command})[:16]
    diagnosis_dir = state_root(repo) / repo_identity(repo) / "diagnosis"
    diagnosis_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = diagnosis_dir / f"{record_id}.log"
    evidence_path.write_text(raw, encoding="utf-8")
    assessment = {
        "schema": "bug-diagnosis/v2", "repo_id": repo_identity(repo), "repo": str(repo),
        "request": redact(args.request), "request_sha256": request_sha, "command": args.diagnosis_command,
        "disposition": args.disposition, "hypothesis": redact(args.hypothesis), "read_only": True,
        "evidence_path": str(evidence_path), "output_sha256": digest_text(raw), "returncode": result.returncode,
        "created_at": now(),
    }
    assessment_path = diagnosis_dir / f"{record_id}.json"
    write_json_atomic(assessment_path, assessment)
    emit({**assessment, "assessment_path": str(assessment_path), "run_created": False, "next_action": "start a bug repair with --diagnosis-file <assessment>"}, args)
    return 0 if args.disposition != "blocked" else 2


def cmd_classify(args: argparse.Namespace) -> int:
    result = classify(args.request, args.task_class)
    result.update({"request_sha256": digest_bytes(args.request.encode("utf-8")), "run_created": False})
    result["next_action"] = "answer the highest-impact question" if result["needs_clarification"] else "start exploration or report the read-only result"
    emit(result, args)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    path = repo / ".megin" / "config.json"
    ensure_megin_excluded(repo)
    if path.exists() and not args.force:
        emit({"initialized": False, "already_initialized": True, "config_path": str(path), "config": read_json(path)}, args)
        return 0
    config = {
        "schema": CONFIG_SCHEMA, "plugin": "megin", "plugin_version": PLUGIN_VERSION,
        "workflow_schema": SCHEMA, "repo_id": repo_identity(repo), "repo_path": str(repo),
        "base_branch": args.base_branch or default_base_branch(repo), "branch_prefix": validate_branch_prefix(args.branch_prefix or "feat"),
        "workspace_mode": args.workspace_mode or "current", "test_commands": list(args.test_command or ["python -m unittest discover"]),
        "allowed_paths": list(args.allowed_path or ["." ]), "knowledge_scope": list(args.knowledge_path or []),
        "scenario_command": args.scenario_command,
        "remote": args.remote, "created_at": now(),
    }
    write_json_atomic(path, config)
    emit({"initialized": True, "config_path": str(path), "config": config, "state_root": str(state_root(repo))}, args)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    classification = classify(args.request, args.task_class)
    if classification["task_class"] == "read_only":
        emit({**classification, "request_sha256": digest_bytes(args.request.encode("utf-8")), "run_created": False, "next_action": "answer with repository and knowledge evidence; no delivery state is created"}, args)
        return 0
    if classification["task_class"] == "bug":
        if not args.diagnosis_file:
            emit({**classification, "request_sha256": digest_text(args.request), "run_created": False, "next_action": "run diagnose and provide --diagnosis-file before repair"}, args)
            return 0
        assessment = read_json(Path(args.diagnosis_file).expanduser().resolve())
        if assessment.get("request_sha256") != digest_text(args.request) or assessment.get("disposition") not in ("confirmed", "likely"):
            emit({**classification, "request_sha256": digest_text(args.request), "run_created": False, "next_action": "resolve the read-only diagnosis before starting repair"}, args)
            return 0
    if classification["needs_clarification"] and not getattr(args, "unresolved_question", None):
        emit({**classification, "request_sha256": digest_bytes(args.request.encode("utf-8")), "run_created": False, "next_action": "clarify intent, scope, or acceptance before creating a candidate"}, args)
        return 0
    work_id = validate_work_id(args.work_id) if args.work_id else make_work_id(args.request)
    path = state_path(repo, work_id)
    if path.exists():
        raise MeginError(f"Work ID already exists: {work_id}; use resume or choose a new Work ID")
    config = load_config(repo)
    state = make_state(repo, work_id, args, classification, config)
    save_state(state, path)
    result = state_summary(state, path)
    result["run_created"] = True
    result["review_gate"] = {
        "chat_summary": result["chat_summary"], "file_details": result["file_details"],
        "reply": f"確認計畫 {work_id} {state['design']['plan_version']}，依此開始開發。",
    }
    emit(result, args)
    return 0


def response_has_tokens(response: str, work_id: str, version: str) -> bool:
    normalized = " ".join(response.replace("，", " ").replace("。", " ").split()).casefold()
    return work_id.casefold() in normalized and version.casefold() in normalized


def make_assignment(state: dict[str, Any], task: dict[str, Any], role: str, identity: str, session: str) -> dict[str, Any]:
    sequence = len(state.get("assignments", [])) + 1
    assignment_id = f"{role}-{sequence:02d}"
    ticket = digest_json({"work_id": state["work_id"], "task_id": task["id"], "role": role, "identity": identity, "session": session, "revision": state["revision"]})
    record = {"assignment_id": assignment_id, "task_id": task["id"], "role": role, "identity": identity, "session": session, "ticket": ticket, "status": "active", "created_at": now()}
    state.setdefault("assignments", []).append(record)
    return record


def activate_workspace(state: dict[str, Any], repo: Path, args: argparse.Namespace) -> None:
    if status_paths(repo):
        raise MeginError("approval requires a clean starting worktree; inspect existing changes before continuing")
    base_sha = state["repo"]["base_sha"]
    if head_sha(repo) != base_sha:
        raise MeginError("the approved base SHA no longer matches HEAD; re-run exploration and create a new plan")
    expected_base_branch = state["repo"]["base_branch"]
    if current_branch(repo) != expected_base_branch:
        raise MeginError(f"approval must start from base branch {expected_base_branch}; current branch is {current_branch(repo)}")
    mode = state["workspace"]["mode"]
    prefix = validate_branch_prefix(getattr(args, "branch_prefix", None) or state["approval"]["scope"]["publication"].get("branch_prefix") or "feat")
    branch = f"{prefix}/{state['work_id']}"
    if mode == "current":
        lock_path = acquire_workspace_lock(repo, state)
        try:
            if git(repo, "show-ref", "--verify", f"refs/heads/{branch}", check=False).strip():
                raise MeginError(f"feature branch already exists: {branch}")
            git(repo, "switch", "-c", branch)
            worktree = repo
        except Exception:
            if lock_path.exists():
                release_workspace_lock(repo, state["work_id"])
            raise
    else:
        worktree = state_root(repo) / repo_identity(repo) / state["work_id"] / "worktree"
        if worktree.exists():
            raise MeginError(f"approved worktree already exists: {worktree}")
        worktree.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", "-b", branch, str(worktree), base_sha)
    state["workspace"].update({"worktree": str(worktree), "branch": branch, "base_sha": base_sha, "created_at": now()})


def cmd_approve(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    state, path = load_state(repo, args.work_id)
    if state["status"] == "awaiting_clarification" or state["exploration"].get("unresolved"):
        raise MeginError("approval is blocked until every behavior, scope, and acceptance question has an answer")
    if state["approval"].get("status") == "approved":
        emit(state_summary(state, path), args)
        return 0
    response = args.response or (f"確認計畫 {args.work_id} {state['design']['plan_version']}，依此開始開發。" if args.confirm else "")
    if not response_has_tokens(response, state["work_id"], state["design"]["plan_version"]):
        raise MeginError(f"provide an explicit response such as: 確認計畫 {state['work_id']} {state['design']['plan_version']}，依此開始開發。")
    if args.plan_version and args.plan_version != state["design"]["plan_version"]:
        raise MeginError("plan version does not match the current candidate")
    if state["approval"].get("candidate_digest") != candidate_digest(state):
        raise MeginError("candidate changed since start; create a new Work ID")
    activate_workspace(state, repo, args)
    state["approval"].update({"status": "approved", "approved_at": now(), "approved_by": args.approved_by or "human", "response": redact(response), "refs": list(args.approval_ref or [])})
    task = state["tasks"][0]
    task["status"] = "active"
    writer = args.writer or "implementation-agent-01"
    session = args.writer_session or f"writer:{writer}:01"
    assignment = make_assignment(state, task, "writer", writer, session)
    state["phase"] = "implementation"
    state["status"] = "active"
    state["next_action"] = "writer completes the active task with red-green-refactor evidence"
    event(state, "plan_approved", phase="implementation", status="active", assignment_id=assignment["assignment_id"])
    save_state(state, path)
    result = state_summary(state, path)
    result["assignment"] = assignment
    emit(result, args)
    return 0


def current_worktree(state: dict[str, Any]) -> Path:
    value = state.get("workspace", {}).get("worktree")
    if not value:
        raise MeginError("approved state has no workspace")
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise MeginError(f"approved workspace is missing: {path}")
    return path


def task_for_id(state: dict[str, Any], task_id: str | None = None) -> dict[str, Any]:
    if task_id:
        for task in state["tasks"]:
            if task.get("id") == task_id:
                return task
        raise MeginError(f"unknown task: {task_id}")
    for task in state["tasks"]:
        if task.get("status") in ("active", "needs_revision", "awaiting_review"):
            return task
    raise MeginError("there is no active task")


def advance_after_review(state: dict[str, Any], task: dict[str, Any], args: argparse.Namespace) -> None:
    """Advance the workflow after an APPROVED task review.

    A fresh review can be required for more than one task after snapshot drift.
    Those tasks must be reviewed before any new writer assignment is created.
    """
    if all(item.get("status") == "reviewed" for item in state["tasks"]):
        state["review"]["overall"] = "approved"
        state["phase"] = "verification"
        state["status"] = "awaiting_verification"
        state["next_action"] = "run verify to execute the approved commands and Gherkin contract"
        event(state, "task_review_approved", task_id=task["id"], next_phase="verification")
        return

    next_review = next((item for item in state["tasks"] if item.get("status") == "awaiting_review"), None)
    if next_review is not None:
        state["review"]["overall"] = "pending"
        state["phase"] = "review"
        state["status"] = "awaiting_review"
        state["next_action"] = f"fresh independent reviewer records an APPROVED or CHANGES_REQUIRED verdict for {next_review['id']}"
        event(state, "task_review_approved", task_id=task["id"], next_review_task=next_review["id"])
        return

    next_task = next(
        (
            item
            for item in state["tasks"]
            if item.get("status") == "pending"
            and all(
                previous.get("status") == "reviewed"
                for previous in state["tasks"]
                if previous["id"] in item.get("depends_on", [])
            )
        ),
        None,
    )
    if next_task is None:
        raise MeginError("no awaiting-review or dependency-ready pending task remains after review")

    state["review"]["overall"] = "pending"
    state["phase"] = "implementation"
    state["status"] = "active"
    next_task["status"] = "active"
    writer_number = 1 + sum(1 for item in state.get("assignments", []) if item.get("role") == "writer")
    next_writer = args.writer_id or f"implementation-agent-{writer_number:02d}"
    next_session = args.writer_session or f"writer:{next_writer}:01"
    assignment = make_assignment(state, next_task, "writer", next_writer, next_session)
    state["next_action"] = f"writer completes {next_task['id']}"
    event(state, "task_review_approved", task_id=task["id"], next_assignment=assignment["assignment_id"])


def changed_paths_for_report(report: dict[str, Any], worktree: Path) -> list[str]:
    values = report.get("changed_paths")
    if values is None:
        return status_paths(worktree)
    if not isinstance(values, list):
        raise MeginError("writer report changed_paths must be an array")
    return sorted(set(normalize_path(str(item)) for item in values))


def cmd_resume(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    state, path = load_state(repo, args.work_id)
    if bool(args.question) != bool(args.answer):
        raise MeginError("exploration resume requires both --question and --answer")
    if args.question and args.answer:
        unresolved = list(state["exploration"].get("unresolved", []))
        try:
            unresolved.remove(args.question)
        except ValueError:
            raise MeginError("question is not an unresolved exploration question")
        state["exploration"]["answers"].append({"question": args.question, "answer": redact(args.answer), "at": now()})
        state["exploration"]["unresolved"] = unresolved
        if not unresolved:
            state["exploration"]["completed_at"] = now()
            state["phase"] = "planning"
            state["status"] = "awaiting_approval"
            state["next_action"] = "provide the plan approval response"
        state["approval"]["candidate_digest"] = candidate_digest(state)
        save_state(state, path)
        emit(state_summary(state, path), args)
        return 0
    worktree = current_worktree(state)
    ensure_workspace_binding(state, worktree)
    if args.scenario_command:
        if args.writer_complete or args.review_verdict:
            raise MeginError("scenario-command recovery cannot be combined with writer or review updates")
        verification = state.get("verification", {})
        records = verification.get("commands", [])
        scenario_results = verification.get("scenario_results", [])
        if verification.get("status") != "failed" or state["approval"]["scope"].get("scenario_command"):
            raise MeginError("scenario-command recovery is only available after a failed verification without a scenario runner")
        if not records or any(item.get("status") != "passed" for item in records if isinstance(item, dict)):
            raise MeginError("scenario-command recovery requires every approved command to have passed")
        if not scenario_results or any(
            item.get("status") != "not_run" or item.get("reason") != "no approved scenario command was provided"
            for item in scenario_results if isinstance(item, dict)
        ):
            raise MeginError("scenario-command recovery requires the only verification gap to be a missing runner")
        state["approval"]["scope"]["scenario_command"] = args.scenario_command
        state["approval"]["candidate_digest"] = candidate_digest(state)
        state["verification"] = {"status": "not_run", "commands": [], "scenario_results": [], "snapshot": None, "record_sha256": None}
        for task in state["tasks"]:
            if task.get("status") == "reviewed":
                task["status"] = "awaiting_review"
        state["review"]["overall"] = "pending"
        state["review"]["findings"] = []
        state["review"]["no_progress_count"] = 0
        state["review"]["snapshot"] = snapshot(worktree)
        state["phase"] = "review"
        state["status"] = "awaiting_review"
        state["next_action"] = "fresh independent reviewer records an APPROVED verdict after adding the scenario runner"
        event(state, "scenario_command_added_after_missing_runner", phase="review", status="awaiting_review")
        save_state(state, path)
        emit(state_summary(state, path), args)
        return 0
    if args.writer_complete:
        task = task_for_id(state, args.task_id)
        assignment = next((item for item in reversed(state["assignments"]) if item["task_id"] == task["id"] and item["role"] == "writer" and item["status"] == "active"), None)
        if not assignment:
            raise MeginError("no active writer assignment for the task")
        if args.writer_id and args.writer_id != assignment["identity"]:
            raise MeginError("writer identity does not match the active assignment")
        if args.writer_ticket and args.writer_ticket != assignment["ticket"]:
            raise MeginError("writer ticket does not match the active assignment")
        report: dict[str, Any] = {}
        if args.writer_report:
            report = read_json(Path(args.writer_report).expanduser().resolve())
        changed = changed_paths_for_report(report, worktree)
        if any(not path_allowed(item, task["allowed_paths"]) for item in changed):
            raise MeginError("writer changed a path outside the task boundary")
        current_changed = status_paths(worktree)
        if changed != current_changed:
            raise MeginError("writer report changed_paths do not match the current worktree")
        evidence = report.get("tests") or [{"command": command, "status": "passed"} for command in task["test_commands"]]
        if any(str(item.get("status")).casefold() not in ("passed", "pass", "ok") for item in evidence if isinstance(item, dict)):
            raise MeginError("writer completion requires passing focused/related test evidence")
        tdd = report.get("tdd") or {"mode": "existing_coverage", "red": None, "green": evidence}
        if not isinstance(tdd, dict) or tdd.get("mode") not in ("red_green_refactor", "existing_coverage"):
            raise MeginError("writer report tdd.mode must be red_green_refactor or existing_coverage")
        if tdd.get("mode") == "red_green_refactor" and (not tdd.get("red") or not tdd.get("green")):
            raise MeginError("new behavior requires both red and green TDD evidence")
        assignment.update({"status": "completed", "report": report, "changed_paths": changed, "tdd": tdd, "completed_at": now()})
        task.update({"status": "awaiting_review", "writer": assignment["identity"], "writer_session": assignment["session"]})
        state["phase"] = "review"
        state["status"] = "awaiting_review"
        state["review"]["overall"] = "pending"
        state["review"]["snapshot"] = snapshot(worktree)
        state["next_action"] = "fresh independent reviewer records an APPROVED or CHANGES_REQUIRED verdict"
        event(state, "writer_completed", phase="review", status="awaiting_review", task_id=task["id"])
    if args.review_verdict:
        task = task_for_id(state, args.task_id)
        if task.get("status") != "awaiting_review":
            raise MeginError("review is only available after the active writer completion")
        reviewer = args.reviewer_id or "reviewer-01"
        session = args.reviewer_session or f"reviewer:{reviewer}:01"
        if reviewer == task.get("writer") or session == task.get("writer_session"):
            raise MeginError("reviewer must be a fresh independent identity and session")
        verdict = args.review_verdict.upper()
        if verdict not in ("APPROVED", "CHANGES_REQUIRED", "BLOCKED"):
            raise MeginError("review verdict must be APPROVED, CHANGES_REQUIRED, or BLOCKED")
        findings = [{"key": f"finding-{index + 1}", "text": redact(value), "severity": "blocking"} for index, value in enumerate(args.finding or [])]
        review_report: dict[str, Any] = {}
        if args.review_report:
            review_report = read_json(Path(args.review_report).expanduser().resolve())
            if review_report.get("verdict") and str(review_report.get("verdict")).upper() != verdict:
                raise MeginError("review report verdict does not match the supplied verdict")
            if isinstance(review_report.get("findings"), list):
                findings = [item for item in review_report["findings"] if isinstance(item, dict)]
        task["reviewer"], task["reviewer_session"] = reviewer, session
        task["findings"] = findings
        task["review_round"] = int(task.get("review_round") or 0) + 1
        state["review"]["per_task"][task["id"]] = {"verdict": verdict, "reviewer": reviewer, "session": session, "findings": findings, "report": review_report, "at": now()}
        if verdict == "APPROVED":
            task["status"] = "reviewed"
            advance_after_review(state, task, args)
        elif verdict == "CHANGES_REQUIRED":
            same = bool(state["review"].get("findings")) and state["review"].get("findings") == findings
            state["review"]["no_progress_count"] = int(state["review"].get("no_progress_count") or 0) + 1 if same else 0
            state["review"]["findings"] = findings
            if state["review"]["no_progress_count"] >= 3:
                task["status"] = "blocked"
                state["status"] = "blocked"
                state["phase"] = "review"
                state["next_action"] = "replace the repeated finding with new evidence or revise the approved plan"
            else:
                task["status"] = "needs_revision"
                assignment = make_assignment(state, task, "writer", task.get("writer") or "implementation-agent-01", task.get("writer_session") or "writer:revision")
                state["phase"] = "implementation"
                state["status"] = "active"
                state["next_action"] = "writer addresses the reviewer findings with a fresh assignment"
                event(state, "review_changes_required", task_id=task["id"], assignment_id=assignment["assignment_id"])
        else:
            task["status"] = "blocked"
            state["review"]["overall"] = "blocked"
            state["phase"] = "review"
            state["status"] = "blocked"
            state["next_action"] = "resolve the reviewer blocker and resume with a fresh review"
        state["review"]["snapshot"] = snapshot(worktree)
        event(state, "review_recorded", task_id=task["id"], verdict=verdict)
    save_state(state, path)
    emit(state_summary(state, path), args)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    state, path = load_state(repo, args.work_id)
    if any(item.get("status") != "reviewed" for item in state["tasks"]):
        raise MeginError("verification is blocked until every task has an independent APPROVED review")
    worktree = current_worktree(state)
    ensure_workspace_binding(state, worktree)
    current_snapshot = snapshot(worktree)
    review_snapshot = state["review"].get("snapshot")
    if review_snapshot is None:
        raise MeginError("verification is blocked until the approved review records a workspace snapshot")
    if current_snapshot != review_snapshot:
        state["verification"].update({"status": "stale", "snapshot": current_snapshot})
        drifted_tasks = []
        for task in state["tasks"]:
            if task.get("status") == "reviewed":
                task["status"] = "awaiting_review"
                drifted_tasks.append(task["id"])
        state["review"]["overall"] = "pending"
        state["review"]["findings"] = []
        state["review"]["no_progress_count"] = 0
        state["phase"] = "review"
        state["status"] = "awaiting_review"
        state["next_action"] = "the reviewed workspace changed; obtain a fresh independent review before verifying"
        event(
            state,
            "verification_blocked_snapshot_drift",
            phase="review",
            status="awaiting_review",
            task_ids=drifted_tasks,
            cleared_review_findings=True,
            cleared_review_retry_count=True,
        )
        save_state(state, path)
        raise MeginError("workspace changed after review; obtain a fresh independent review before verifying")
    if args.reuse_evidence and state["verification"].get("status") == "passed" and state["verification"].get("snapshot") == current_snapshot:
        state["phase"] = "acceptance"
        state["status"] = "awaiting_user_acceptance"
        state["human_acceptance"]["status"] = "pending"
        state["human_acceptance"]["snapshot"] = current_snapshot
        state["human_acceptance"]["checked_scenarios"] = [scenario["id"] for scenario in state["behavior_contract"]["scenarios"]]
        state["next_action"] = f"驗測通過 {state['work_id']} {state['human_acceptance']['version']}，同意更新知識並建立本機 commit。"
        event(state, "verification_evidence_reused", phase="acceptance", status="awaiting_user_acceptance")
        save_state(state, path)
        emit(state_summary(state, path), args)
        return 0
    state["verification"]["status"] = "running"
    state["verification"]["commands"] = []
    evidence_dir = evidence_root(repo, state["work_id"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for index, command in enumerate(state["approval"]["scope"]["test_commands"], 1):
        input_snapshot = snapshot(worktree)
        result = run_approved_command(command, worktree, timeout=300)
        raw = redact((result.stdout or "") + (result.stderr or ""))
        evidence_path = evidence_dir / f"verify-{index:02d}.log"
        evidence_path.write_text(raw, encoding="utf-8")
        output_snapshot = snapshot(worktree)
        record = {"command": command, "status": "passed" if result.returncode == 0 else "failed", "returncode": result.returncode, "evidence_path": str(evidence_path), "output_sha256": digest_bytes(raw.encode("utf-8")), "input_snapshot": input_snapshot, "output_snapshot": output_snapshot, "environment": {"python": sys.version.split()[0], "platform": sys.platform}}
        state["verification"]["commands"].append(record)
        if result.returncode != 0:
            failed = True
        if output_snapshot != input_snapshot:
            record["status"] = "failed"
            record["reason"] = "verification command changed the approved workspace"
            failed = True

    scenario_command = state["approval"]["scope"].get("scenario_command")
    scenario_results: list[dict[str, Any]]
    if scenario_command:
        input_snapshot = snapshot(worktree)
        result = run_approved_command(scenario_command, worktree, timeout=300)
        raw = redact((result.stdout or "") + (result.stderr or ""))
        evidence_path = evidence_dir / "scenario-evidence.json"
        evidence_path.write_text(raw, encoding="utf-8")
        scenario_failed = result.returncode != 0
        if result.returncode == 0:
            try:
                scenario_results, parsed_failed = parse_scenario_evidence(raw, state["behavior_contract"]["scenarios"])
                scenario_failed = scenario_failed or parsed_failed
            except MeginError as exc:
                scenario_results = [{"id": scenario["id"], "status": "error", "reason": str(exc)} for scenario in state["behavior_contract"]["scenarios"]]
                scenario_failed = True
        else:
            scenario_results = [{"id": scenario["id"], "status": "error", "reason": "scenario runner exited non-zero"} for scenario in state["behavior_contract"]["scenarios"]]
        output_snapshot = snapshot(worktree)
        scenario_record = {
            "command": scenario_command, "kind": "scenario_runner", "status": "passed" if not scenario_failed else "failed",
            "returncode": result.returncode, "evidence_path": str(evidence_path), "output_sha256": digest_bytes(raw.encode("utf-8")),
            "input_snapshot": input_snapshot, "output_snapshot": output_snapshot,
            "environment": {"python": sys.version.split(".")[0], "platform": sys.platform},
        }
        if output_snapshot != input_snapshot:
            scenario_failed = True
            scenario_record["status"] = "failed"
            scenario_record["reason"] = "scenario runner changed the approved workspace"
        state["verification"]["commands"].append(scenario_record)
        failed = failed or scenario_failed
    else:
        scenario_results = [{"id": scenario["id"], "status": "not_run", "reason": "no approved scenario command was provided"} for scenario in state["behavior_contract"]["scenarios"]]
        failed = True
    state["verification"]["scenario_results"] = scenario_results
    state["verification"]["snapshot"] = snapshot(worktree)
    state["knowledge"]["reviewed_snapshot"] = knowledge_snapshot(worktree, state["knowledge"].get("scope", []))
    state["verification"]["record_sha256"] = digest_json(state["verification"])
    if failed:
        state["verification"]["status"] = "failed"
        state["phase"] = "verification"
        state["status"] = "blocked"
        state["next_action"] = "fix the failing approved command, obtain a fresh review, and run verify again"
        event(state, "verification_failed", phase="verification", status="blocked")
    else:
        state["verification"]["status"] = "passed"
        state["phase"] = "acceptance"
        state["status"] = "awaiting_user_acceptance"
        state["human_acceptance"]["status"] = "pending"
        state["human_acceptance"]["snapshot"] = state["verification"]["snapshot"]
        state["human_acceptance"]["checked_scenarios"] = [scenario["id"] for scenario in state["behavior_contract"]["scenarios"]]
        state["next_action"] = f"驗測通過 {state['work_id']} {state['human_acceptance']['version']}，同意更新知識並建立本機 commit。"
        event(state, "verification_passed", phase="acceptance", status="awaiting_user_acceptance")
    save_state(state, path)
    emit(state_summary(state, path), args)
    return 0 if not failed else 2


def cmd_accept(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    state, path = load_state(repo, args.work_id)
    if state.get("status") != "awaiting_user_acceptance" or state["verification"].get("status") != "passed":
        raise MeginError("human acceptance is available only after successful automated verification")
    version = args.acceptance_version or state["human_acceptance"]["version"]
    response = args.response or (f"驗測通過 {args.work_id} {version}，同意更新知識並建立本機 commit。" if args.confirm else "")
    if version != state["human_acceptance"]["version"] or not response_has_tokens(response, state["work_id"], version):
        raise MeginError(f"provide an explicit response such as: 驗測通過 {state['work_id']} {state['human_acceptance']['version']}，同意更新知識並建立本機 commit。")
    worktree = current_worktree(state)
    ensure_workspace_binding(state, worktree)
    current = snapshot(worktree)
    if current != state["human_acceptance"].get("snapshot"):
        raise MeginError("product snapshot changed after verify; run the affected review and verification again")
    state["human_acceptance"].update({"status": "passed", "version": version, "response": redact(response), "observed": list(args.observed or []), "accepted_at": now()})
    state["phase"] = "delivery"
    state["status"] = "active"
    state["next_action"] = "finish to review knowledge, stage the approved paths, and create one local commit"
    event(state, "human_acceptance_passed", phase="delivery", status="active")
    save_state(state, path)
    emit(state_summary(state, path), args)
    return 0


def git_base_file_digest(repo: Path, base_sha: str, path: str) -> str:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{base_sha}:{path}"],
        cwd=str(repo), capture_output=True,
    )
    if result.returncode != 0:
        return "<missing>"
    return digest_bytes(result.stdout)


def block_knowledge_promotion(state: dict[str, Any], reason: str) -> str:
    safe_reason = redact(reason)
    state["knowledge"].update({"status": "blocked", "conflicts": [safe_reason]})
    state["phase"] = "knowledge"
    state["status"] = "blocked"
    state["next_action"] = "repair the knowledge source or Project Knowledge lint, then resume finish; source changes require fresh review and verification"
    event(state, "knowledge_promotion_blocked", phase="knowledge", status="blocked", reason=safe_reason)
    return safe_reason


def promote_knowledge(state: dict[str, Any], repo: Path, worktree: Path) -> None:
    knowledge = state["knowledge"]
    scope = [normalize_path(str(item)) for item in knowledge.get("scope", [])]
    if not scope:
        knowledge.update({"status": "not_needed", "conflicts": []})
        return

    # A later finish is a new validation attempt.  Keep the reviewed snapshot
    # as the gate, but do not let an earlier failure permanently poison it.
    knowledge.update({
        "status": "pending", "conflicts": [], "sources": [], "candidate_path": None,
        "pre_snapshot": None, "post_snapshot": None, "validation": None, "promoted_at": None,
    })
    try:
        reviewed_snapshot = knowledge.get("reviewed_snapshot")
        current_knowledge_snapshot = knowledge_snapshot(worktree, scope)
        if not reviewed_snapshot or reviewed_snapshot != current_knowledge_snapshot:
            raise MeginError("knowledge sources changed after verification; obtain a fresh review before promotion")

        sources: list[dict[str, str]] = []
        for path in scope:
            target = worktree / path
            if not target.exists() or not target.is_file():
                raise MeginError(f"knowledge source is missing: {path}")
            raw = target.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MeginError(f"knowledge source is not UTF-8: {path}") from exc
            if target.suffix.casefold() == ".json":
                try:
                    json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise MeginError(f"knowledge JSON is invalid: {path}: {exc}") from exc
            sources.append({
                "path": path,
                "pre_sha256": git_base_file_digest(worktree, state["repo"]["base_sha"], path),
                "post_sha256": digest_bytes(raw),
            })

        validated_snapshot = knowledge_snapshot(worktree, scope)
        if validated_snapshot != current_knowledge_snapshot:
            raise MeginError("knowledge sources changed during promotion validation")

        candidate_path = evidence_root(repo, state["work_id"]) / "knowledge-candidate.json"
        candidate = {
            "schema": "megin-knowledge-candidate/v3",
            "work_id": state["work_id"],
            "sources": sources,
            "pre_snapshot": digest_json([{item["path"]: item["pre_sha256"]} for item in sources]),
            "post_snapshot": current_knowledge_snapshot,
            "plan_version": state["design"]["plan_version"],
            "created_at": now(),
        }
        write_json_atomic(candidate_path, candidate)
        knowledge.update({
            "status": "reviewed", "sources": [item["path"] for item in sources], "candidate_path": str(candidate_path),
            "pre_snapshot": candidate["pre_snapshot"], "post_snapshot": current_knowledge_snapshot,
            "validation": {"source_checks": "passed", "schema_checks": "passed"},
        })

        validator = worktree / ".agents" / "skills" / "project-knowledge" / "scripts" / "knowledge_cli.py"
        if validator.is_file():
            result = run_process((sys.executable, "-X", "utf8", "-B", str(validator), "lint", "--repo", str(worktree)), worktree, timeout=300, check=False)
            raw = redact((result.stdout or "") + (result.stderr or ""))
            lint_path = evidence_root(repo, state["work_id"]) / "knowledge-lint.log"
            lint_path.write_text(raw, encoding="utf-8")
            knowledge["validation"] = {
                "source_checks": "passed", "schema_checks": "passed", "lint": "passed" if result.returncode == 0 else "failed",
                "evidence_path": str(lint_path), "output_sha256": digest_bytes(raw.encode("utf-8")),
            }
            if result.returncode != 0:
                raise MeginError("target Project Knowledge lint failed; knowledge was not promoted")
    except MeginError as exc:
        raise MeginError(block_knowledge_promotion(state, str(exc))) from exc
    except OSError as exc:
        raise MeginError(block_knowledge_promotion(state, f"knowledge validation failed: {exc}")) from exc


def cmd_finish(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    state, path = load_state(repo, args.work_id)
    if state["human_acceptance"].get("status") != "passed":
        raise MeginError("finish is blocked until the human acceptance response is recorded")
    worktree = current_worktree(state)
    ensure_workspace_binding(state, worktree)
    if snapshot(worktree) != state["human_acceptance"].get("snapshot"):
        raise MeginError("working tree changed after human acceptance; run review, verify, and acceptance again")
    changed = status_paths(worktree)
    allowed = state["approval"]["scope"]["allowed_paths"]
    if any(not path_allowed(item, allowed) for item in changed):
        raise MeginError("finish found a changed path outside the approved scope")
    if not changed:
        raise MeginError("finish found no product changes to commit")
    try:
        promote_knowledge(state, repo, worktree)
    except MeginError:
        save_state(state, path)
        raise
    git(worktree, "add", "-A", "--", *changed)
    staged = [item for item in status_paths(worktree)]
    if not staged:
        raise MeginError("finish found no staged product changes")
    message = f"megin({state['work_id']}): {state['approval']['scope']['publication']['title']}".replace("\n", " ")[:200]
    result = run_process(("git", "commit", "-m", message), worktree, timeout=180, check=False)
    if result.returncode != 0:
        raise MeginError(f"git commit failed ({result.returncode}): {redact((result.stdout or '') + (result.stderr or '')).strip()}")
    commit = head_sha(worktree)
    state["publication"].update({"state": "committed", "commit_sha": commit, "changed_paths": changed, "suggested_commit": message})
    if state["knowledge"].get("status") == "reviewed":
        state["knowledge"].update({"status": "promoted", "promoted_at": now()})
    state["phase"] = "delivery"
    state["status"] = "complete"
    state["next_action"] = "knowledge and local commit are complete; no push or merge was performed"
    event(state, "committed", phase="delivery", status="complete", commit_sha=commit)
    save_state(state, path)
    if state["workspace"].get("mode") == "current":
        release_workspace_lock(repo, state["work_id"])
    result_value = state_summary(state, path)
    result_value["commit"] = commit
    emit(result_value, args)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    if args.work_id:
        state, path = load_state(repo, args.work_id)
        emit(state_summary(state, path), args)
        return 0
    directory = state_root(repo) / repo_identity(repo)
    records: list[dict[str, Any]] = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                state = read_json(path)
                if state.get("schema") == SCHEMA:
                    records.append(state_summary(state, path))
            except MeginError:
                continue
    emit({"schema": SCHEMA, "repo": str(repo), "state_root": str(directory), "runs": records}, args)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    repo = require_git_repo(args.repo)
    checks = [
        {"name": "git_repository", "ok": True, "path": str(repo)},
        {"name": "python", "ok": sys.version_info >= (3, 13), "version": sys.version.split()[0], "required": "3.13+"},
        {"name": "git", "ok": shutil.which("git") is not None},
        {"name": "rg", "ok": shutil.which("rg") is not None, "required": "ripgrep"},
        {"name": "delivery_schema_v3", "ok": DELIVERY_SCHEMA_PATH.exists(), "path": str(DELIVERY_SCHEMA_PATH)},
        {"name": "hooks", "ok": (PLUGIN_ROOT / "hooks" / "hooks.json").exists(), "path": str(PLUGIN_ROOT / "hooks" / "hooks.json"), "read_only": True},
        {"name": "state_root", "ok": True, "path": str(state_root(repo))},
    ]
    config = load_config(repo)
    checks.append({"name": "project_config", "ok": config is not None, "optional": True, "path": str(repo / ".megin" / "config.json")})
    emit({"schema": "megin-doctor/v3", "ok": all(item["ok"] or item.get("optional") for item in checks), "workflow": SCHEMA, "checks": checks, "hook_trust": "read-only routing only; hooks never approve or mutate"}, args)
    return 0 if all(item["ok"] or item.get("optional") for item in checks) else 2


def add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--text", action="store_true")


def add_repo(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True)


def add_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allowed-path", action="append")
    parser.add_argument("--test-command", action="append")
    parser.add_argument("--scenario-command", help="command that emits JSON scenario evidence keyed by stable scenario ID")
    parser.add_argument("--knowledge-path", action="append")
    parser.add_argument("--acceptance", action="append")
    parser.add_argument("--feature-file", action="append")
    parser.add_argument("--manual-step", action="append", help="scenario-id|path|environment|operation|expected")
    parser.add_argument("--source", action="append")
    parser.add_argument("--unresolved-question", action="append")
    parser.add_argument("--plan-version")
    parser.add_argument("--design-file")
    parser.add_argument("--design-summary")
    parser.add_argument("--task", action="append", help="dependency-ordered task title; repeat for multiple independently reviewed tasks")
    parser.add_argument("--title")
    parser.add_argument("--base-branch")
    parser.add_argument("--remote")
    parser.add_argument("--workspace-mode", choices=WORKSPACE_MODES)
    parser.add_argument("--branch-prefix")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="megin", description="Megin Workflow v3")
    sub = parser.add_subparsers(dest="command", required=True)

    classify_parser = sub.add_parser("classify", help="read-only task routing")
    classify_parser.add_argument("--request", required=True)
    classify_parser.add_argument("--task-class", choices=TASK_CLASSES)
    add_output(classify_parser)

    init_parser = sub.add_parser("init", help="opt a repository into the v3 defaults")
    add_repo(init_parser)
    init_parser.add_argument("--base-branch")
    init_parser.add_argument("--branch-prefix")
    init_parser.add_argument("--workspace-mode", choices=WORKSPACE_MODES)
    init_parser.add_argument("--test-command", action="append")
    init_parser.add_argument("--scenario-command")
    init_parser.add_argument("--allowed-path", action="append")
    init_parser.add_argument("--knowledge-path", action="append")
    init_parser.add_argument("--remote")
    init_parser.add_argument("--force", action="store_true")
    add_output(init_parser)

    diagnose_parser = sub.add_parser("diagnose", help="run a read-only bug diagnosis command")
    add_repo(diagnose_parser)
    diagnose_parser.add_argument("--request", required=True)
    diagnose_parser.add_argument("--command", dest="diagnosis_command", required=True)
    diagnose_parser.add_argument("--disposition", required=True, choices=("confirmed", "likely", "partial", "not-a-bug", "blocked"))
    diagnose_parser.add_argument("--hypothesis", required=True)
    add_output(diagnose_parser)

    start_parser = sub.add_parser("start", help="create an external, read-only behavior candidate")
    add_repo(start_parser)
    start_parser.add_argument("--request", required=True)
    start_parser.add_argument("--work-id")
    start_parser.add_argument("--task-class", choices=TASK_CLASSES)
    start_parser.add_argument("--repair-class", choices=("small", "large"))
    start_parser.add_argument("--diagnosis", choices=("confirmed", "likely", "not-a-bug"))
    start_parser.add_argument("--diagnosis-file")
    add_scope(start_parser)
    add_output(start_parser)

    approve_parser = sub.add_parser("approve", help="approve one current plan and activate the workspace")
    add_repo(approve_parser)
    approve_parser.add_argument("--work-id", required=True)
    approve_parser.add_argument("--response")
    approve_parser.add_argument("--confirm", action="store_true")
    approve_parser.add_argument("--plan-version")
    approve_parser.add_argument("--approved-by")
    approve_parser.add_argument("--approval-ref", action="append")
    approve_parser.add_argument("--writer")
    approve_parser.add_argument("--writer-session")
    approve_parser.add_argument("--branch-prefix")
    add_output(approve_parser)

    resume_parser = sub.add_parser("resume", help="continue exploration, writer handoff, or independent review")
    add_repo(resume_parser)
    resume_parser.add_argument("--work-id", required=True)
    resume_parser.add_argument("--question")
    resume_parser.add_argument("--answer")
    resume_parser.add_argument("--task-id")
    resume_parser.add_argument("--writer-complete", action="store_true")
    resume_parser.add_argument("--writer-id")
    resume_parser.add_argument("--writer-session")
    resume_parser.add_argument("--writer-ticket")
    resume_parser.add_argument("--writer-report")
    resume_parser.add_argument("--scenario-command", help="supply a missing runner after all approved verification commands passed")
    resume_parser.add_argument("--review-verdict", choices=("APPROVED", "CHANGES_REQUIRED", "BLOCKED"))
    resume_parser.add_argument("--reviewer-id")
    resume_parser.add_argument("--reviewer-session")
    resume_parser.add_argument("--review-report")
    resume_parser.add_argument("--finding", action="append")
    add_output(resume_parser)

    verify_parser = sub.add_parser("verify", help="run approved commands and the Gherkin contract")
    add_repo(verify_parser)
    verify_parser.add_argument("--work-id", required=True)
    verify_parser.add_argument("--rerun", action="store_true")
    verify_parser.add_argument("--reuse-evidence", action="store_true", help="reuse a passed record only when command, input, and snapshot bindings still match")
    add_output(verify_parser)

    accept_parser = sub.add_parser("accept", help="record the human acceptance gate")
    add_repo(accept_parser)
    accept_parser.add_argument("--work-id", required=True)
    accept_parser.add_argument("--response")
    accept_parser.add_argument("--confirm", action="store_true")
    accept_parser.add_argument("--acceptance-version")
    accept_parser.add_argument("--observed", action="append")
    add_output(accept_parser)

    status_parser = sub.add_parser("status", help="show a resumable v3 state")
    add_repo(status_parser)
    status_parser.add_argument("--work-id")
    add_output(status_parser)

    doctor_parser = sub.add_parser("doctor", help="check v3 tools, hooks, and contract")
    add_repo(doctor_parser)
    add_output(doctor_parser)

    finish_parser = sub.add_parser("finish", help="promote approved knowledge and create the local commit")
    add_repo(finish_parser)
    finish_parser.add_argument("--work-id", required=True)
    add_output(finish_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        commands = {
            "classify": cmd_classify, "init": cmd_init, "diagnose": cmd_diagnose, "start": cmd_start, "approve": cmd_approve,
            "resume": cmd_resume, "verify": cmd_verify, "accept": cmd_accept, "status": cmd_status,
            "doctor": cmd_doctor, "finish": cmd_finish,
        }
        return commands[args.command](args)
    except (MeginError, GherkinError) as exc:
        print(f"megin: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("megin: interrupted; state was not reset", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
