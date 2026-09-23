"""Read-only structural checks for a Megin Work ID's quality evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "check"))
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--gate", choices=("review", "acceptance", "delivery"))
    args = parser.parse_args()
    try:
        if not WORK_ID_PATTERN.fullmatch(args.work_id):
            raise InvalidEvidence("invalid Work ID")
        repo = args.repo.resolve()
        if not repo.is_dir() or Path(line(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
            raise InvalidEvidence("--repo must identify the Git repository root")
        if args.action == "check" and not args.gate:
            raise InvalidEvidence("check requires --gate")
        result = snapshot(repo, args.work_id) if args.action == "snapshot" else check(repo, args.work_id, args.gate)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1 if result.get("ok") is False else 0
    except (InvalidEvidence, OSError, UnicodeError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
