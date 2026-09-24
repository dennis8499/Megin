"""Read-only structural checks for Group v2 or Megin source v1 quality evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit


WORK_ID_PATTERN = re.compile(r"work-[0-9]{8}-[a-z0-9-]+\Z")
PLAN_VERSION_PATTERN = re.compile(r"plan-[a-z0-9-]+\Z")
RESULT_STATUSES = {"passed", "failed", "blocked", "not_run"}


class InvalidEvidence(Exception):
    """An input cannot be interpreted as this version of the evidence format."""


def git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, check=False,
    )
    if result.returncode:
        raise InvalidEvidence(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def line(repo: Path, *arguments: str) -> str:
    return git(repo, *arguments).decode("utf-8", errors="replace").strip()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidEvidence(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidEvidence(f"expected JSON object: {path}")
    return value


def workflow_fields(path: Path) -> dict[str, str]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidEvidence(f"cannot read workflow: {exc}") from exc
    header = contents.split("\n## ", maxsplit=1)[0]
    return dict(re.findall(r"(?m)^- ([a-z_]+): (.+)$", header))


def canonical_relative(relative: object) -> str:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise InvalidEvidence(f"invalid relative path: {relative!r}")
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or pure.as_posix() != relative
            or any(part in ("", ".", "..") for part in pure.parts)
            or (pure.parts and ":" in pure.parts[0])):
        raise InvalidEvidence(f"invalid relative path: {relative!r}")
    return relative


def within_repo(repo: Path, relative: object) -> Path:
    canonical = canonical_relative(relative)
    path = (repo / canonical).resolve()
    if not path.is_relative_to(repo) or path == repo:
        raise InvalidEvidence(f"path escapes repository: {relative}")
    return path


def evidence_file(repo: Path, work_id: str, relative: object) -> Path:
    path = within_repo(repo, relative)
    root = (repo / "docs" / "work" / work_id / "evidence").resolve()
    if not path.is_relative_to(root) or path == root:
        raise InvalidEvidence(f"source must be in this Work ID's evidence directory: {relative}")
    return path


def valid_allowed_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    candidate = value[:-1] if value.endswith("/") else value
    try:
        return canonical_relative(candidate) == candidate
    except InvalidEvidence:
        return False


def load_contract(repo: Path, work_id: str) -> tuple[dict[str, str], dict, set[str]]:
    work = repo / "docs" / "work" / work_id
    fields = workflow_fields(work / "workflow.md")
    if fields.get("work_id") != work_id:
        raise InvalidEvidence("workflow Work ID mismatch")
    plan_version = fields.get("plan_version", "")
    if not PLAN_VERSION_PATTERN.fullmatch(plan_version):
        raise InvalidEvidence("workflow plan_version is invalid")
    contract = read_json(work / plan_version / "quality-contract.json")
    if (contract.get("schema"), contract.get("work_id"), contract.get("plan_version")) != (
        "megin-quality-contract/v1", work_id, plan_version,
    ):
        raise InvalidEvidence("approved quality contract identity mismatch")

    checks, allowed = contract.get("checks"), contract.get("allowed_paths")
    records = contract.get("process_records")
    if (not isinstance(checks, list) or not checks or not isinstance(allowed, list)
            or not allowed or not isinstance(records, list) or not records):
        raise InvalidEvidence(
            "approved quality contract needs checks, allowed paths, and process records"
        )
    ids = [entry.get("id") for entry in checks if isinstance(entry, dict)]
    if (len(ids) != len(checks) or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)
            or any(entry.get("kind") not in ("test", "command")
                   or not isinstance(entry.get("command"), str) or not entry["command"]
                   for entry in checks)
            or any(not valid_allowed_path(rule) for rule in allowed)):
        raise InvalidEvidence("duplicate or invalid approved check IDs or paths")

    record_set: set[str] = set()
    for record in records:
        canonical = canonical_relative(record)
        evidence_file(repo, work_id, canonical)
        record_set.add(canonical)
    if len(record_set) != len(records):
        raise InvalidEvidence("duplicate process record paths")
    return fields, contract, record_set


def process_record(relative: str, work_id: str, records: set[str]) -> bool:
    return relative == f"docs/work/{work_id}/workflow.md" or relative in records


def digest_entries(entries: list[dict[str, str]]) -> str:
    encoded = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def worktree_entries(repo: Path, work_id: str, records: set[str]) -> list[dict[str, str]]:
    paths = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    entries: list[dict[str, str]] = []
    for raw in sorted(set(paths.split(b"\0")) - {b""}):
        relative = raw.decode("utf-8")
        if process_record(relative, work_id, records):
            continue
        path = within_repo(repo, relative)
        if path.is_file():
            entries.append({
                "path": relative,
                "content": line(repo, "hash-object", f"--path={relative}", relative),
            })
    return entries


def index_entries(repo: Path, work_id: str, records: set[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for record in git(repo, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", maxsplit=1)
        _mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise InvalidEvidence("unmerged index cannot be checked")
        relative = raw_name.decode("utf-8")
        if process_record(relative, work_id, records):
            continue
        entries.append({"path": relative, "content": object_id})
    return sorted(entries, key=lambda item: item["path"])


def snapshot(repo: Path, work_id: str) -> dict[str, object]:
    _fields, _contract, records = load_contract(repo, work_id)
    entries = worktree_entries(repo, work_id, records)
    return {
        "schema": "megin-quality-snapshot/v1",
        "branch": line(repo, "branch", "--show-current"),
        "head": line(repo, "rev-parse", "HEAD"),
        "product_sha256": digest_entries(entries),
        "path_count": len(entries),
    }


def cited_file(
    repo: Path, work_id: str, records: set[str], value: object, label: str,
    reasons: list[str], require_locator: bool = False,
) -> list[str] | None:
    if not isinstance(value, dict):
        reasons.append(f"{label}: missing source reference")
        return None
    relative, expected = value.get("path"), value.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        reasons.append(f"{label}: incomplete source reference")
        return None
    path = evidence_file(repo, work_id, relative)
    if relative not in records:
        raise InvalidEvidence(f"{label}: source is not an approved process record")
    if not path.is_file():
        reasons.append(f"{label}: source missing or digest changed")
        return None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        reasons.append(f"{label}: source missing or digest changed")
        return None
    lines = raw.decode("utf-8", errors="replace").splitlines()
    if require_locator:
        number, claimed = value.get("line"), value.get("text")
        if (type(number) is not int or number < 1 or number > len(lines)
                or not isinstance(claimed, str) or lines[number - 1] != claimed):
            reasons.append(f"{label}: raw output locator missing or changed")
    return lines


def cited_claims(
    repo: Path, work_id: str, records: set[str], value: object, label: str,
    reasons: list[str], expected: dict[str, str], require_locator: bool = False,
) -> None:
    lines = cited_file(
        repo, work_id, records, value, label, reasons, require_locator,
    )
    if lines is None or not isinstance(value, dict):
        return
    claims = value.get("claims")
    if not isinstance(claims, dict):
        reasons.append(f"{label}: raw claim locators missing")
        return
    for name, expected_text in expected.items():
        locator = claims.get(name)
        if not isinstance(locator, dict):
            reasons.append(f"{label}: {name} claim locator missing")
            continue
        number, claimed = locator.get("line"), locator.get("text")
        if (type(number) is not int or number < 1 or number > len(lines)
                or claimed != expected_text or lines[number - 1] != expected_text):
            reasons.append(f"{label}: raw {name} claim differs from structured evidence")


def path_set(repo: Path, *arguments: str) -> set[str]:
    return {
        value.decode("utf-8")
        for value in git(repo, *arguments, "-z").split(b"\0") if value
    }


def changed_paths(repo: Path, base_commit: str) -> set[str]:
    return (
        path_set(repo, "diff", "--name-only", base_commit)
        | path_set(repo, "ls-files", "--others", "--exclude-standard")
    )


def product_paths(paths: set[str], work_id: str, records: set[str]) -> set[str]:
    return {path for path in paths if not process_record(path, work_id, records)}


def validate_recorded_checks(
    repo: Path, work_id: str, records: set[str], obligations: list[dict],
    evidence: dict, digest: str, reasons: list[str], require_pass: bool,
) -> None:
    recorded = evidence.get("checks")
    valid_recorded = isinstance(recorded, list) and all(
        isinstance(entry, dict) and isinstance(entry.get("id"), str)
        for entry in recorded
    )
    by_id = {entry["id"]: entry for entry in recorded} if valid_recorded else {}
    if not valid_recorded or len(by_id) != len(recorded):
        reasons.append("duplicate or invalid recorded check IDs")
    approved_ids = {entry["id"] for entry in obligations}
    for extra in sorted(set(by_id) - approved_ids):
        reasons.append(f"{extra}: result is not an approved check")
    for obligation in obligations:
        identifier = obligation["id"]
        result = by_id.get(identifier)
        if not isinstance(result, dict):
            reasons.append(f"{identifier}: required result missing")
            continue
        status, exit_code = result.get("status"), result.get("exit_code")
        expected = {"command": f"Command: {obligation['command']}"}
        if "cwd" in obligation:
            expected["cwd"] = f"Working directory: {obligation['cwd']}"
        if type(exit_code) is int:
            expected["exit_code"] = f"Exit code: {exit_code}"
        cited_claims(
            repo, work_id, records, result.get("output"), identifier, reasons,
            expected, require_locator=True,
        )
        if result.get("snapshot") != digest:
            reasons.append(f"{identifier}: stale snapshot")
        if status not in RESULT_STATUSES or type(exit_code) is not int:
            reasons.append(f"{identifier}: result status or exit code is unknown")
        if obligation.get("kind") == "test":
            counts = tuple(result.get(name) for name in ("executed", "failed", "skipped"))
            if any(type(value) is not int or value < 0 for value in counts):
                reasons.append(f"{identifier}: test counts are missing or invalid")
            elif require_pass and (counts[0] <= 0 or counts[1] != 0 or counts[2] != 0):
                reasons.append(f"{identifier}: test count is zero, failed, skipped, or unknown")
        if require_pass and (status != "passed" or exit_code != 0):
            reasons.append(f"{identifier}: required command did not pass")


def check(repo: Path, work_id: str, gate: str) -> dict[str, object]:
    fields, contract, records = load_contract(repo, work_id)
    checks, allowed = contract["checks"], contract["allowed_paths"]
    reference = canonical_relative(fields.get("quality_ref", ""))
    quality_path = evidence_file(repo, work_id, reference)
    if reference not in records:
        raise InvalidEvidence("workflow quality_ref is not an approved process record")
    evidence = read_json(quality_path)
    plan_version = fields["plan_version"]
    if (evidence.get("schema"), evidence.get("work_id"), evidence.get("plan_version")) != (
        "megin-quality-evidence/v1", work_id, plan_version,
    ):
        raise InvalidEvidence("quality evidence identity mismatch")

    current = snapshot(repo, work_id)
    digest = current["product_sha256"]
    reasons: list[str] = []
    if current["branch"] != fields.get("feature_branch"):
        reasons.append("current branch differs from approved feature branch")
    base_branch, base_commit = fields.get("base_branch", ""), fields.get("base_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise InvalidEvidence("workflow base_commit is not a full Git SHA")
    if line(repo, "rev-parse", base_branch) != base_commit:
        reasons.append("base branch advanced")
    if evidence.get("snapshot") != digest:
        reasons.append("product or approved-contract snapshot changed")
    for relative in sorted(changed_paths(repo, base_commit)):
        if not any(
            relative.startswith(rule) if rule.endswith("/") else relative == rule
            for rule in allowed
        ):
            reasons.append(f"changed path outside approved scope: {relative}")

    writer = evidence.get("writer")
    writer_context = writer.get("context") if isinstance(writer, dict) else None
    writer_snapshot = writer.get("snapshot") if isinstance(writer, dict) else None
    if (not isinstance(writer_context, str) or not writer_context
            or not isinstance(writer_snapshot, str) or writer_snapshot != digest):
        reasons.append("writer handoff context or snapshot missing")
    else:
        cited_claims(
            repo, work_id, records, writer.get("source"), "writer handoff", reasons,
            {
                "context": f"- context: {writer_context}",
                "snapshot": f"- snapshot: {writer_snapshot}",
            },
        )

    sources = evidence.get("sources")
    if not isinstance(sources, list):
        reasons.append("supporting source references missing")
    else:
        for index, source in enumerate(sources, start=1):
            cited_file(
                repo, work_id, records, source, f"supporting source {index}", reasons,
            )

    validate_recorded_checks(
        repo, work_id, records, checks, evidence, digest, reasons,
        require_pass=gate in ("acceptance", "delivery"),
    )

    if gate in ("review", "acceptance"):
        staged = product_paths(
            path_set(repo, "diff", "--cached", "--name-only", "HEAD"), work_id, records,
        )
        if staged:
            reasons.append("product paths are staged before human acceptance")

    if gate in ("acceptance", "delivery"):
        reviewer = evidence.get("review")
        if not isinstance(reviewer, dict):
            reasons.append("independent review missing")
        else:
            review_context = reviewer.get("context")
            review_verdict = reviewer.get("verdict")
            review_snapshot = reviewer.get("snapshot")
            valid_review_fields = all(
                isinstance(value, str) and bool(value)
                for value in (review_context, review_verdict, review_snapshot)
            )
            if valid_review_fields:
                cited_claims(
                    repo, work_id, records, reviewer.get("source"), "review", reasons,
                    {
                        "context": f"- context: {review_context}",
                        "verdict": f"- verdict: {review_verdict}",
                        "snapshot": f"- snapshot: {review_snapshot}",
                    },
                )
            if (not valid_review_fields or review_verdict != "APPROVED"
                    or review_snapshot != digest or review_context == writer_context):
                reasons.append("independent APPROVED review for current snapshot missing")

    staged_digest: str | None = None
    staged_paths: list[str] | None = None
    if gate == "delivery":
        acceptance = evidence.get("acceptance")
        if not isinstance(acceptance, dict):
            reasons.append("human acceptance missing")
        else:
            accepted_work = acceptance.get("work_id")
            version = acceptance.get("version")
            accepted_snapshot = acceptance.get("snapshot")
            acceptance_verdict = acceptance.get("verdict")
            valid_acceptance_fields = all(
                isinstance(value, str) and bool(value)
                for value in (
                    accepted_work, version, accepted_snapshot, acceptance_verdict,
                )
            )
            if valid_acceptance_fields:
                cited_claims(
                    repo, work_id, records, acceptance.get("source"),
                    "acceptance", reasons,
                    {
                        "work_id": f"- work_id: {accepted_work}",
                        "version": f"- version: {version}",
                        "snapshot": f"- snapshot: {accepted_snapshot}",
                        "verdict": f"- verdict: {acceptance_verdict}",
                    },
                )
            if (not valid_acceptance_fields or accepted_work != work_id
                    or acceptance_verdict != "ACCEPTED"
                    or accepted_snapshot != digest):
                reasons.append("human acceptance does not bind current Work ID and snapshot")

        unstaged = product_paths(
            path_set(repo, "diff", "--name-only")
            | path_set(repo, "ls-files", "--others", "--exclude-standard"),
            work_id, records,
        )
        if unstaged:
            reasons.append("unstaged or untracked product paths remain before delivery")
        staged_digest = digest_entries(index_entries(repo, work_id, records))
        staged_paths = sorted(product_paths(
            path_set(repo, "diff", "--cached", "--name-only", base_commit),
            work_id, records,
        ))
        if staged_digest != digest:
            reasons.append("staged product bytes differ from accepted snapshot")

    result: dict[str, object] = {
        "gate": gate, "ok": not reasons, "snapshot": digest, "reasons": reasons,
    }
    if gate == "delivery":
        result.update(staged_snapshot=staged_digest, staged_paths=staged_paths)
    return result


GROUP_SHA_PATTERN = re.compile(r"[0-9a-f]{40,64}\Z")


def within_group(group_root: Path, relative: object) -> Path:
    canonical = canonical_relative(relative)
    path = (group_root / canonical).resolve()
    if not path.is_relative_to(group_root) or path == group_root:
        raise InvalidEvidence(f"path escapes Group root: {relative}")
    return path


def group_evidence_file(group_root: Path, work_id: str, relative: object) -> Path:
    path = within_group(group_root, relative)
    evidence_root = (group_root / "docs" / "work" / work_id / "evidence").resolve()
    if not path.is_relative_to(evidence_root) or path == evidence_root:
        raise InvalidEvidence(f"source must be in this Work ID evidence directory: {relative}")
    return path


def validate_group_root(group_root: Path) -> Path:
    group_root = group_root.resolve()
    if not group_root.is_dir():
        raise InvalidEvidence("Group root is not a directory")
    if any((parent / ".git").exists() for parent in (group_root, *group_root.parents)):
        raise InvalidEvidence("Group root must not be inside a Git repository")
    result = subprocess.run(
        ["git", "-C", str(group_root), "rev-parse", "--show-toplevel"],
        capture_output=True, check=False,
    )
    if result.returncode == 0:
        raise InvalidEvidence("Group root must not be inside a Git repository")
    if b"not a git repository" not in result.stderr.lower():
        raise InvalidEvidence("could not verify that Group root is outside Git")
    return group_root


def normalized_remote_url(value: str) -> str:
    """Return a credential-free remote identity suitable for a local work record."""
    if "://" in value:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if hostname is None:
            return value
        host = f"[{hostname}]" if ":" in hostname else hostname
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", ""))
    if re.match(r"^[^/\s]+@[^/\s]+:.+$", value):
        return value.rsplit("@", maxsplit=1)[1].rstrip("/")
    return value.rstrip("/")


def load_group_contract(
    group_root: Path, work_id: str,
) -> tuple[dict[str, str], dict, list[dict], set[str]]:
    if not WORK_ID_PATTERN.fullmatch(work_id):
        raise InvalidEvidence("invalid Group Work ID")
    within_group(group_root, f"docs/work/{work_id}")
    work = group_root / "docs" / "work" / work_id
    fields = workflow_fields(work / "workflow.md")
    if fields.get("schema") != "megin-skills-workflow/v2":
        raise InvalidEvidence("workflow schema is not megin-skills-workflow/v2")
    if fields.get("work_id") != work_id:
        raise InvalidEvidence("workflow Work ID mismatch")
    plan_version = fields.get("plan_version", "")
    if not PLAN_VERSION_PATTERN.fullmatch(plan_version):
        raise InvalidEvidence("workflow plan_version is invalid")
    reference = canonical_relative(fields.get("quality_ref", ""))
    group_evidence_file(group_root, work_id, reference)
    contract = read_json(work / plan_version / "quality-contract.json")
    if (contract.get("schema"), contract.get("work_id"), contract.get("plan_version")) != (
        "megin-quality-contract/v2", work_id, plan_version,
    ):
        raise InvalidEvidence("Group quality contract identity mismatch")

    repositories = contract.get("repositories")
    checks = contract.get("checks")
    process_records = contract.get("process_records")
    delivery_mode = contract.get("delivery_mode")
    if (not isinstance(repositories, list) or not repositories
            or not isinstance(checks, list) or not checks
            or not isinstance(process_records, list) or not process_records):
        raise InvalidEvidence("Group contract needs repositories, checks, and process_records")
    if delivery_mode not in ("local_merge", "feature_handoff"):
        raise InvalidEvidence("invalid Group delivery_mode")
    if (delivery_mode == "local_merge" and len(repositories) != 1
            or delivery_mode == "feature_handoff" and len(repositories) < 2):
        raise InvalidEvidence("delivery_mode does not match repository count")

    seen_paths: set[str] = set()
    validated: list[dict] = []
    for item in repositories:
        if not isinstance(item, dict):
            raise InvalidEvidence("invalid repository entry")
        repo_path = canonical_relative(item.get("repo_path"))
        if len(PurePosixPath(repo_path).parts) != 1:
            raise InvalidEvidence(f"repository must be a direct child of Group root: {repo_path}")
        if (group_root / repo_path).is_symlink():
            raise InvalidEvidence(f"repository path must not be a symlink: {repo_path}")
        repo = within_group(group_root, repo_path)
        if repo.parent != group_root:
            raise InvalidEvidence(f"repository must be a direct child of Group root: {repo_path}")
        if repo_path in seen_paths or not repo.is_dir():
            raise InvalidEvidence(f"duplicate or missing Group repository: {repo_path}")
        seen_paths.add(repo_path)
        top = Path(line(repo, "rev-parse", "--show-toplevel")).resolve()
        if top != repo:
            raise InvalidEvidence(f"repository path is not its Git root: {repo_path}")
        remote = item.get("remote")
        base_branch = item.get("base_branch")
        base_commit = item.get("base_commit")
        feature_branch = item.get("feature_branch")
        allowed = item.get("allowed_paths")
        if not all(isinstance(value, str) and value for value in (
            remote, base_branch, base_commit, feature_branch,
        )):
            raise InvalidEvidence(f"missing branch or remote identity for {repo_path}")
        remote_url = item.get("remote_url")
        if not isinstance(remote_url, str) or not remote_url:
            raise InvalidEvidence(f"missing remote_url for {repo_path}")
        if normalized_remote_url(remote_url) != remote_url:
            raise InvalidEvidence(f"remote_url must omit credentials for {repo_path}")
        if not GROUP_SHA_PATTERN.fullmatch(base_commit):
            raise InvalidEvidence(f"invalid base_commit for {repo_path}")
        if not isinstance(allowed, list) or not allowed or any(
            not valid_allowed_path(value) for value in allowed
        ):
            raise InvalidEvidence(f"invalid allowed_paths for {repo_path}")
        if len(set(allowed)) != len(allowed):
            raise InvalidEvidence(f"duplicate allowed_paths for {repo_path}")
        if feature_branch != f"feature/{work_id}":
            raise InvalidEvidence(f"feature_branch must be feature/{work_id} for {repo_path}")
        if base_branch == feature_branch:
            raise InvalidEvidence(f"base_branch cannot be the feature branch for {repo_path}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote):
            raise InvalidEvidence(f"invalid remote name for {repo_path}")
        configured_url = line(repo, "remote", "get-url", remote)
        if normalized_remote_url(configured_url) != remote_url:
            raise InvalidEvidence(f"configured remote differs from approved remote for {repo_path}")
        line(repo, "check-ref-format", "--branch", base_branch)
        line(repo, "check-ref-format", "--branch", feature_branch)
        resolved_base = line(repo, "rev-parse", "--verify", f"{base_commit}^{{commit}}")
        if resolved_base != base_commit:
            raise InvalidEvidence(f"approved base_commit is unavailable for {repo_path}")
        item = dict(item)
        item["repo"] = repo
        validated.append(item)

    check_ids: set[str] = set()
    for check_item in checks:
        if not isinstance(check_item, dict):
            raise InvalidEvidence("invalid Group check entry")
        identifier = check_item.get("id")
        kind = check_item.get("kind")
        command = check_item.get("command")
        cwd = check_item.get("cwd")
        if (not isinstance(identifier, str) or not identifier or identifier in check_ids
                or kind not in ("test", "command")
                or not isinstance(command, str) or not command
                or not isinstance(cwd, str) or cwd not in (".", *seen_paths)):
            raise InvalidEvidence("invalid or duplicate Group check ID, command, or cwd")
        check_ids.add(identifier)

    records: set[str] = set()
    for record in process_records:
        canonical = canonical_relative(record)
        group_evidence_file(group_root, work_id, canonical)
        records.add(canonical)
    if len(records) != len(process_records) or reference not in records:
        raise InvalidEvidence("quality_ref must be a unique approved process record")
    return fields, contract, validated, records


def group_index_entries(repo: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for record in git(repo, "ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", maxsplit=1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise InvalidEvidence("unmerged Group repository index cannot be checked")
        entries.append({
            "path": raw_name.decode("utf-8"), "mode": mode, "content": object_id,
        })
    return sorted(entries, key=lambda item: item["path"])


def group_file_mode(path: Path, indexed_mode: str | None, filemode: bool) -> str | None:
    if path.is_symlink():
        return "120000"
    if path.is_dir() or not path.is_file():
        return None
    if not filemode:
        if indexed_mode in ("100644", "100755"):
            return indexed_mode
        return "100644"
    return "100755" if path.stat().st_mode & 0o111 else "100644"


def group_repo_entries(repo: Path) -> list[dict[str, str]]:
    paths = git(repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    indexed = {entry["path"]: entry for entry in group_index_entries(repo)}
    filemode_result = subprocess.run(
        ["git", "-C", str(repo), "config", "--bool", "--get", "core.filemode"],
        text=True, encoding="utf-8", errors="replace", capture_output=True, check=False,
    )
    if filemode_result.returncode == 0:
        filemode = filemode_result.stdout.strip().lower() == "true"
    elif filemode_result.returncode == 1:
        filemode = os.name != "nt"
    else:
        raise InvalidEvidence("could not read Git core.filemode configuration")

    entries: list[dict[str, str]] = []
    for raw in sorted(set(paths.split(b"\0")) - {b""}):
        relative = canonical_relative(raw.decode("utf-8"))
        path = repo / relative
        resolved = path.resolve()
        if not resolved.is_relative_to(repo):
            raise InvalidEvidence(f"repository path escapes its Git root: {relative}")
        index_entry = indexed.get(relative)
        indexed_mode = index_entry["mode"] if index_entry else None

        if indexed_mode == "160000":
            content = index_entry["content"]
            if path.is_dir():
                result = subprocess.run(
                    ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
                    text=True, encoding="utf-8", errors="replace",
                    capture_output=True, check=False,
                )
                if result.returncode == 0:
                    status = subprocess.run(
                        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
                        text=True, encoding="utf-8", errors="replace",
                        capture_output=True, check=False,
                    )
                    if status.returncode != 0:
                        raise InvalidEvidence(f"could not inspect submodule status: {relative}")
                    if status.stdout:
                        raise InvalidEvidence(f"dirty submodule cannot be snapshotted: {relative}")
                    content = result.stdout.strip()
            entries.append({"path": relative, "mode": "160000", "content": content})
            continue

        mode = group_file_mode(path, indexed_mode, filemode)
        if mode is None:
            # Missing tracked paths are absent from the worktree tree and must
            # compare with their staged deletion at delivery.
            continue
        if mode == "120000":
            result = subprocess.run(
                ["git", "-C", str(repo), "hash-object", "--stdin"],
                input=os.fsencode(os.readlink(path)), capture_output=True, check=False,
            )
            if result.returncode != 0:
                raise InvalidEvidence(result.stderr.decode("utf-8", errors="replace").strip())
            content = result.stdout.decode("ascii").strip()
        else:
            content = line(repo, "hash-object", f"--path={relative}", relative)
        entries.append({"path": relative, "mode": mode, "content": content})
    return entries


def group_record_entries(
    group_root: Path, work_id: str, records: set[str],
) -> list[dict[str, str]]:
    work = group_root / "docs" / "work" / work_id
    workflow_relative = f"docs/work/{work_id}/workflow.md"
    entries: list[dict[str, str]] = []
    for path in sorted(work.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(group_root):
            raise InvalidEvidence(f"Group work record path escapes root: {path}")
        relative = path.relative_to(group_root).as_posix()
        if relative == workflow_relative or relative in records:
            continue
        entries.append({
            "path": f"@group/{relative}",
            "mode": "100755" if path.stat().st_mode & 0o111 else "100644",
            "content": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return entries


def group_snapshot(
    group_root: Path, work_id: str,
) -> dict[str, object]:
    _fields, _contract, repositories, records = load_group_contract(group_root, work_id)
    all_entries: list[dict[str, str]] = []
    repo_details: dict[str, dict[str, object]] = {}
    for item in sorted(repositories, key=lambda entry: entry["repo_path"]):
        repo = item["repo"]
        entries = group_repo_entries(repo)
        repo_digest = digest_entries(entries)
        repo_path = item["repo_path"]
        branch = line(repo, "branch", "--show-current")
        head = line(repo, "rev-parse", "HEAD")
        repo_details[repo_path] = {
            "branch": branch, "head": head,
            "product_sha256": repo_digest, "path_count": len(entries),
        }
        all_entries.extend({
            "path": f"{repo_path}/{entry['path']}",
            "mode": entry["mode"],
            "content": entry["content"],
        } for entry in entries)
    all_entries.extend(group_record_entries(group_root, work_id, records))
    return {
        "schema": "megin-quality-snapshot/v2",
        "work_id": work_id,
        "product_sha256": digest_entries(all_entries),
        "path_count": len(all_entries),
        "repositories": repo_details,
    }


def group_path_set(repo: Path, *arguments: str) -> set[str]:
    return {
        raw.decode("utf-8")
        for raw in git(repo, *arguments, "-z").split(b"\0") if raw
    }


def group_allowed_path(relative: str, allowed: list[str]) -> bool:
    return any(
        relative.startswith(rule) if rule.endswith("/") else relative == rule
        for rule in allowed
    )


def check_group(group_root: Path, work_id: str, gate: str) -> dict[str, object]:
    fields, contract, repositories, records = load_group_contract(group_root, work_id)
    reference = canonical_relative(fields["quality_ref"])
    quality_path = group_evidence_file(group_root, work_id, reference)
    evidence = read_json(quality_path)
    plan_version = fields["plan_version"]
    if (evidence.get("schema"), evidence.get("work_id"), evidence.get("plan_version")) != (
        "megin-quality-evidence/v2", work_id, plan_version,
    ):
        raise InvalidEvidence("Group quality evidence identity mismatch")

    current = group_snapshot(group_root, work_id)
    digest = current["product_sha256"]
    reasons: list[str] = []
    if evidence.get("snapshot") != digest:
        reasons.append("Group product or approved-contract snapshot changed")
    for item in repositories:
        repo_path = item["repo_path"]
        repo = item["repo"]
        details = current["repositories"][repo_path]
        if details["branch"] != item["feature_branch"]:
            reasons.append(f"{repo_path}: current branch differs from approved feature branch")
        ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor",
             item["base_branch"], item["base_commit"]],
            capture_output=True, check=False,
        )
        if ancestor.returncode != 0:
            reasons.append(f"{repo_path}: local base branch diverged from approved remote base")
        feature_ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor",
             item["base_commit"], item["feature_branch"]],
            capture_output=True, check=False,
        )
        if feature_ancestor.returncode != 0:
            reasons.append(f"{repo_path}: feature branch is not based on approved base_commit")
        if gate == "delivery":
            remote_result = subprocess.run(
                ["git", "-C", str(repo), "ls-remote", "--exit-code",
                 item["remote"], f"refs/heads/{item['base_branch']}"],
                text=True, encoding="utf-8", errors="replace",
                capture_output=True, check=False,
            )
            if remote_result.returncode != 0:
                reasons.append(f"{repo_path}: remote base branch could not be verified")
            else:
                exact_ref = f"refs/heads/{item['base_branch']}"
                exact_matches = [
                    entry.split("\t", maxsplit=1)[0]
                    for entry in remote_result.stdout.splitlines()
                    if len(entry.split("\t", maxsplit=1)) == 2
                    and entry.split("\t", maxsplit=1)[1] == exact_ref
                ]
                if len(exact_matches) != 1:
                    reasons.append(f"{repo_path}: exact remote base ref could not be verified")
                elif exact_matches[0] != item["base_commit"]:
                    reasons.append(f"{repo_path}: remote base branch advanced")

        changed = (
            group_path_set(repo, "diff", "--name-only", item["base_commit"])
            | group_path_set(repo, "ls-files", "--others", "--exclude-standard")
        )
        for relative in sorted(changed):
            if not group_allowed_path(relative, item["allowed_paths"]):
                reasons.append(f"{repo_path}: changed path outside approved scope: {relative}")

    writer = evidence.get("writer")
    writer_context = writer.get("context") if isinstance(writer, dict) else None
    writer_snapshot = writer.get("snapshot") if isinstance(writer, dict) else None
    if (not isinstance(writer_context, str) or not writer_context
            or writer_snapshot != digest):
        reasons.append("writer handoff context or Group snapshot missing")
    else:
        cited_claims(
            group_root, work_id, records, writer.get("source"), "writer handoff", reasons,
            {
                "context": f"- context: {writer_context}",
                "snapshot": f"- snapshot: {writer_snapshot}",
            },
        )

    sources = evidence.get("sources")
    if not isinstance(sources, list):
        reasons.append("supporting Group source references missing")
    else:
        for index, source in enumerate(sources, start=1):
            cited_file(
                group_root, work_id, records, source,
                f"supporting source {index}", reasons,
            )

    validate_recorded_checks(
        group_root, work_id, records, contract["checks"], evidence, digest, reasons,
        require_pass=gate in ("acceptance", "delivery"),
    )

    if gate in ("review", "acceptance"):
        for item in repositories:
            staged = group_path_set(
                item["repo"], "diff", "--cached", "--name-only", "HEAD",
            )
            if staged:
                reasons.append(f"{item['repo_path']}: product paths are staged before acceptance")

    if gate in ("acceptance", "delivery"):
        reviewer = evidence.get("review")
        if not isinstance(reviewer, dict):
            reasons.append("independent Group review missing")
        else:
            review_context = reviewer.get("context")
            review_verdict = reviewer.get("verdict")
            review_snapshot = reviewer.get("snapshot")
            valid_review = all(
                isinstance(value, str) and bool(value)
                for value in (review_context, review_verdict, review_snapshot)
            )
            if valid_review:
                cited_claims(
                    group_root, work_id, records, reviewer.get("source"),
                    "Group review", reasons,
                    {
                        "context": f"- context: {review_context}",
                        "verdict": f"- verdict: {review_verdict}",
                        "snapshot": f"- snapshot: {review_snapshot}",
                    },
                )
            if (not valid_review or review_verdict != "APPROVED"
                    or review_snapshot != digest or review_context == writer_context):
                reasons.append("independent APPROVED review for current Group snapshot missing")

    if gate == "delivery":
        acceptance = evidence.get("acceptance")
        if not isinstance(acceptance, dict):
            reasons.append("Group human acceptance missing")
        else:
            accepted_work = acceptance.get("work_id")
            version = acceptance.get("version")
            accepted_snapshot = acceptance.get("snapshot")
            verdict = acceptance.get("verdict")
            valid_acceptance = all(
                isinstance(value, str) and bool(value)
                for value in (accepted_work, version, accepted_snapshot, verdict)
            )
            if valid_acceptance:
                cited_claims(
                    group_root, work_id, records, acceptance.get("source"),
                    "Group acceptance", reasons,
                    {
                        "work_id": f"- work_id: {accepted_work}",
                        "version": f"- version: {version}",
                        "snapshot": f"- snapshot: {accepted_snapshot}",
                        "verdict": f"- verdict: {verdict}",
                    },
                )
            if (not valid_acceptance or accepted_work != work_id
                    or verdict != "ACCEPTED" or accepted_snapshot != digest):
                reasons.append("human acceptance does not bind current Group snapshot")

        repo_snapshots = current["repositories"]
        staged_details: dict[str, dict[str, object]] = {}
        for item in repositories:
            repo = item["repo"]
            repo_path = item["repo_path"]
            unstaged = (
                group_path_set(repo, "diff", "--name-only")
                | group_path_set(repo, "ls-files", "--others", "--exclude-standard")
            )
            if unstaged:
                reasons.append(f"{repo_path}: unstaged or untracked product paths remain")
            staged = digest_entries(group_index_entries(repo))
            expected = repo_snapshots[repo_path]["product_sha256"]
            if staged != expected:
                reasons.append(f"{repo_path}: staged bytes differ from accepted product snapshot")
            staged_details[repo_path] = {
                "staged_snapshot": staged,
                "staged_paths": sorted(group_path_set(
                    repo, "diff", "--cached", "--name-only", item["base_commit"],
                )),
            }

    result: dict[str, object] = {
        "gate": gate,
        "ok": not reasons,
        "snapshot": digest,
        "delivery_mode": contract["delivery_mode"],
        "repositories": current["repositories"],
        "reasons": reasons,
    }
    if gate == "delivery":
        result["staged_repositories"] = staged_details
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "check"))
    parser.add_argument("--repo", type=Path, help="legacy single-repository evidence root")
    parser.add_argument("--group-root", type=Path, help="non-Git Group directory")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--gate", choices=("review", "acceptance", "delivery"))
    args = parser.parse_args()
    try:
        if not WORK_ID_PATTERN.fullmatch(args.work_id):
            raise InvalidEvidence("invalid Work ID")
        if bool(args.repo) == bool(args.group_root):
            raise InvalidEvidence("provide exactly one of --group-root or --repo")
        if args.action == "check" and not args.gate:
            raise InvalidEvidence("check requires --gate")
        if args.group_root:
            group_root = validate_group_root(args.group_root)
            result = (
                group_snapshot(group_root, args.work_id)
                if args.action == "snapshot"
                else check_group(group_root, args.work_id, args.gate)
            )
        else:
            repo = args.repo.resolve()
            if not repo.is_dir() or Path(line(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
                raise InvalidEvidence("--repo must identify the Git repository root")
            result = snapshot(repo, args.work_id) if args.action == "snapshot" else check(repo, args.work_id, args.gate)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get("ok") is False else 0
    except (InvalidEvidence, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
