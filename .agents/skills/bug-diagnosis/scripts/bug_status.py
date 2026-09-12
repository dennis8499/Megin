#!/usr/bin/env python3
"""Read-only validation and reporting for bug-closure-status/v1."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_ROOT / "references" / "closure-status.schema.json"
ASSESSMENT_VALIDATOR_PATH = Path(__file__).with_name("validate_contracts.py")
_ASSESSMENT_SPEC = importlib.util.spec_from_file_location(
    "bug_assessment_contracts_for_status", ASSESSMENT_VALIDATOR_PATH
)
if _ASSESSMENT_SPEC is None or _ASSESSMENT_SPEC.loader is None:
    raise RuntimeError(f"cannot import {ASSESSMENT_VALIDATOR_PATH}")
_assessment = importlib.util.module_from_spec(_ASSESSMENT_SPEC)
sys.modules[_ASSESSMENT_SPEC.name] = _assessment
_ASSESSMENT_SPEC.loader.exec_module(_assessment)

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
BUG_ID_RE = re.compile(r"^bug-[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUS_PATH_RE = re.compile(
    r"^docs/bugs/(bug-[a-z0-9]+(?:-[a-z0-9]+)*)/status-([1-9][0-9]*)\.json$"
)
ASSESSMENT_PATH_RE = re.compile(
    r"^docs/bugs/(bug-[a-z0-9]+(?:-[a-z0-9]+)*)/assessment-([1-9][0-9]*)\.json$"
)
VERIFICATION_PATH_RE = re.compile(
    r"^docs/bugs/(bug-[a-z0-9]+(?:-[a-z0-9]+)*)/verifications/[^/]+\.json$"
)
UNRESOLVED_DISPOSITIONS = {
    "confirmed-open",
    "evidence-pending",
    "environment-blocked",
    "contract-blocked",
    "accepted-risk",
    "deferred",
}
DISPOSITIONS = [
    "confirmed-open",
    "fixed-verified",
    "evidence-pending",
    "environment-blocked",
    "contract-blocked",
    "accepted-risk",
    "deferred",
    "rejected",
]


class _DuplicateKey(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json(raw: bytes, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateKey as exc:
        return None, [f"{label} contains a duplicate JSON object key: {exc}"]
    except (UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"{label} is not valid UTF-8 JSON: {exc}"]
    if not isinstance(value, dict):
        return None, [f"{label} must be a JSON object"]
    return value, []


def _lexical_relative(repository: Path, value: str | Path) -> tuple[Path | None, str | None, list[str]]:
    errors: list[str] = []
    raw = Path(value)
    if not raw.is_absolute() and ".." in raw.parts:
        return None, None, ["path traversal is not allowed"]
    root = Path(os.path.abspath(repository))
    candidate = Path(os.path.abspath(raw if raw.is_absolute() else root / raw))
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None, None, ["path escapes repository"]
    if not relative or relative.startswith("/") or "\\" in relative:
        errors.append("path is not a normalized repository-relative path")
    return candidate, relative, errors


def _read_stable(repository: Path, path: Path, label: str) -> tuple[bytes | None, list[str]]:
    try:
        return _assessment._stable_assessment_read(repository, path), []
    except _assessment._UnsafeAssessmentPath as exc:
        return None, [f"{label} uses a symlink or reparse point: {exc}"]
    except (FileNotFoundError, OSError) as exc:
        return None, [f"{label} is missing or unreadable: {exc}"]


def _date(value: str) -> date | None:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _business_days_after(start: date, count: int) -> date:
    current = start
    remaining = count
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _path_hash_errors(value: Any, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if not isinstance(value.get("path"), str) or Path(value["path"]).is_absolute() or ".." in Path(value["path"]).parts:
        errors.append(f"{label}.path is unsafe")
    if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
        errors.append(f"{label}.sha256 is invalid")
    return errors


def _validate_assessment_binding(repository: Path, record: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    binding = record.get("assessment")
    errors = _path_hash_errors(binding, "assessment")
    if errors:
        return None, errors
    path = str(binding["path"])
    match = ASSESSMENT_PATH_RE.fullmatch(path)
    if match is None:
        return None, ["assessment.path is not an assessment JSON path"]
    if match.group(1) != record["bug_id"] or int(match.group(2)) != binding.get("revision"):
        errors.append("assessment binding does not match bug_id and revision")
    if binding.get("markdown_path") != f"docs/bugs/{record['bug_id']}/assessment-{binding.get('revision')}.md":
        errors.append("assessment markdown path does not match bug_id and revision")
    assessment_path = repository / Path(*path.split("/"))
    raw, read_errors = _read_stable(repository, assessment_path, "assessment JSON")
    errors.extend(read_errors)
    if raw is None:
        return None, errors
    if sha256_bytes(raw) != binding["sha256"]:
        errors.append("assessment JSON hash mismatch")
    data, parse_errors = _strict_json(raw, "assessment JSON")
    errors.extend(parse_errors)
    if data is None:
        return None, errors
    markdown_path = repository / Path(*str(binding["markdown_path"]).split("/"))
    sidecar_errors = _assessment.validate_assessment(
        data,
        repository_root=repository,
        sidecar_path=assessment_path,
        sidecar_bytes=raw,
    )
    errors.extend(sidecar_errors)
    if data.get("bug_id") != record["bug_id"]:
        errors.append("assessment bug_id differs from status bug_id")
    if data.get("revision") != binding.get("revision"):
        errors.append("assessment revision differs from status binding")
    if data.get("markdown", {}).get("path") != binding.get("markdown_path"):
        errors.append("assessment markdown binding differs from status binding")
    if data.get("markdown", {}).get("sha256") != binding.get("markdown_sha256"):
        errors.append("assessment markdown hash binding differs from status binding")
    if not markdown_path:
        errors.append("assessment markdown path is invalid")
    return data, errors


def _validate_verification_binding(repository: Path, record: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    verification = record.get("verification")
    if verification is None:
        return None, []
    errors = _path_hash_errors(verification, "verification")
    if errors:
        return None, errors
    path = str(verification["path"])
    match = VERIFICATION_PATH_RE.fullmatch(path)
    if match is None or match.group(1) != record["bug_id"]:
        return None, ["verification.path is not a child of this BUG's verification directory"]
    raw, read_errors = _read_stable(repository, repository / Path(*path.split("/")), "verification JSON")
    errors.extend(read_errors)
    if raw is None:
        return None, errors
    if sha256_bytes(raw) != verification["sha256"]:
        errors.append("verification JSON hash mismatch")
    data, parse_errors = _strict_json(raw, "verification JSON")
    errors.extend(parse_errors)
    if data is None:
        return None, errors
    if data.get("schema") != "bug-verification/v1":
        errors.append("verification JSON is not bug-verification/v1")
    if data.get("bug_id") != record["bug_id"]:
        errors.append("verification bug_id differs from status bug_id")
    if data.get("result") != verification.get("result"):
        errors.append("verification result differs between binding and file")
    return data, errors


def _validate_timebox(record: dict[str, Any]) -> list[str]:
    timebox = record["timebox"]
    names = ["t0", "classify_due", "blocker_due", "escalate_due", "decision_due"]
    dates = [_date(timebox[name]) for name in names]
    errors: list[str] = []
    if any(item is None for item in dates):
        return ["timebox contains an invalid date"]
    assert all(item is not None for item in dates)
    if any(item.weekday() >= 5 for item in dates):
        errors.append("timebox dates must be business days")
    expected = [
        dates[0],
        _business_days_after(dates[0], 1),
        _business_days_after(dates[0], 3),
        _business_days_after(dates[0], 5),
        _business_days_after(dates[0], 10),
    ]
    if dates != expected:
        errors.append("timebox must use the default T0+1/T0+3/T0+5/T0+10 business-day schedule")
    due_date = _date(record["tracking"]["due_date"])
    if due_date is None or due_date < dates[0]:
        errors.append("tracking.due_date must be on or after T0")
    return errors


def _validate_blocker_and_risk(record: dict[str, Any]) -> list[str]:
    disposition = record["current_disposition"]
    blocker = record.get("blocker")
    risk = record.get("risk_decision")
    errors: list[str] = []
    expected_class = {"environment-blocked": "environment", "contract-blocked": "contract"}.get(disposition)
    if expected_class is not None:
        if blocker is None:
            errors.append(f"{disposition} requires a blocker")
        elif blocker.get("class") != expected_class:
            errors.append(f"{disposition} requires blocker class {expected_class}")
    elif blocker is not None:
        errors.append("blocker is only valid for environment-blocked or contract-blocked")
    if disposition in {"accepted-risk", "deferred", "rejected"}:
        if risk is None:
            errors.append(f"{disposition} requires a risk decision")
        elif risk.get("decision") != disposition:
            errors.append("risk decision does not match current disposition")
    elif risk is not None:
        errors.append("risk decision is only valid for accepted-risk, deferred or rejected")
    if risk is not None:
        approvals = risk.get("approvals", [])
        identities = [item.get("identity") for item in approvals]
        if len(identities) != len(set(identities)):
            errors.append("risk approvals must have distinct identities")
        if record["severity"] in {"critical", "high"} and disposition in {"accepted-risk", "deferred"}:
            roles = {item.get("role") for item in approvals}
            if not {"Product/Risk", "Engineering/Delivery"}.issubset(roles):
                errors.append("High/Critical risk decisions require Product/Risk and Engineering/Delivery approvals")
            if len(approvals) < 2:
                errors.append("High/Critical risk decisions require dual approval")
    return errors


def _validate_fixed_gate(record: dict[str, Any]) -> list[str]:
    if record["current_disposition"] != "fixed-verified":
        return []
    errors: list[str] = []
    verification = record.get("verification")
    closure = record.get("closure_evidence")
    if not isinstance(verification, dict) or verification.get("result") != "verified":
        errors.append("fixed-verified requires verification result verified")
    if not isinstance(closure, dict):
        return errors + ["fixed-verified requires closure evidence"]
    original = closure.get("original_reproduction", {})
    pre = original.get("pre_fix", {})
    post = original.get("post_fix", {})
    if pre.get("status") != "present" or post.get("status") != "absent":
        errors.append("fixed-verified requires original symptom pre present and post absent")
    if set(pre.get("evidence_refs", [])) & set(post.get("evidence_refs", [])):
        errors.append("original symptom pre and post evidence must be distinct")
    regression = closure.get("regression", {})
    if not regression.get("red_evidence_refs") or not regression.get("green_evidence_refs"):
        errors.append("fixed-verified requires regression red and green evidence")
    if set(regression.get("red_evidence_refs", [])) & set(regression.get("green_evidence_refs", [])):
        errors.append("regression red and green evidence must be distinct")
    full = closure.get("full_verification", [])
    if not full or any(item.get("outcome") != "passed" for item in full):
        errors.append("fixed-verified requires every full verification to pass")
    platforms = {item.get("platform"): item for item in record.get("platform_evidence", [])}
    if any(platforms.get(platform, {}).get("outcome") != "passed" for platform in record["required_platforms"]):
        errors.append("fixed-verified requires passed evidence for every required platform")
    reviewer = record.get("reviewer")
    if not isinstance(reviewer, dict) or reviewer.get("outcome") != "APPROVED":
        errors.append("fixed-verified requires an APPROVED independent reviewer")
    elif reviewer.get("identity") == record["tracking"]["implementation_owner"]:
        errors.append("reviewer identity must differ from implementation owner")
    if record.get("blocker") is not None or record.get("risk_decision") is not None:
        errors.append("fixed-verified cannot retain a blocker or risk decision")
    return errors


def _validate_reviewer(repository: Path, record: dict[str, Any]) -> list[str]:
    reviewer = record.get("reviewer")
    if reviewer is None:
        if record["current_disposition"] == "accepted-risk":
            return ["accepted-risk requires an APPROVED independent reviewer"]
        return []
    if not isinstance(reviewer, dict):
        return ["reviewer must be an object"]
    errors: list[str] = []
    if reviewer.get("identity") == record["tracking"]["implementation_owner"]:
        errors.append("reviewer identity must differ from implementation owner")
    if record["current_disposition"] == "accepted-risk" and reviewer.get("outcome") != "APPROVED":
        errors.append("accepted-risk requires an APPROVED independent reviewer")
    report_ref = reviewer.get("report_path")
    if not isinstance(report_ref, str):
        errors.append("reviewer report_path must be a string")
    else:
        candidate, relative, path_errors = _lexical_relative(repository, report_ref)
        errors.extend(f"reviewer report path {error}" for error in path_errors)
        if candidate is None or relative is None:
            return errors
        if relative != report_ref:
            errors.append("reviewer report_path must be normalized and repository-relative")
        raw, read_errors = _read_stable(repository, candidate, "reviewer report")
        errors.extend(read_errors)
        if raw is not None and sha256_bytes(raw) != reviewer.get("report_sha256"):
            errors.append("reviewer report hash mismatch")
    return errors


def _validate_semantics(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    scope = record["work_scope"]
    if record["bug_id"] not in scope["bug_ids"]:
        errors.append("work_scope.bug_ids must include bug_id")
    if scope["scope_kind"] == "single" and len(scope["bug_ids"]) != 1:
        errors.append("single work scope must contain exactly one BUG")
    if scope["scope_kind"] == "common" and len(scope["bug_ids"]) < 2:
        errors.append("common work scope must contain at least two BUGs")
    assessment, assessment_errors = _validate_assessment_binding(Path.cwd(), record)
    # The public function supplies the repository through a private marker below.
    if assessment is not None:
        pass
    errors.extend(assessment_errors)
    errors.extend(_validate_timebox(record))
    errors.extend(_validate_blocker_and_risk(record))
    errors.extend(_validate_fixed_gate(record))
    errors.extend(_validate_reviewer(repository, record))
    if record["current_disposition"] == "confirmed-open" and record["current_observation"]["status"] != "present":
        errors.append("confirmed-open requires a present current symptom observation")
    if record.get("verification", {}).get("result") == "partial" and record["current_disposition"] == "fixed-verified":
        errors.append("partial verification cannot be fixed-verified")
    if record["transition"]["to"] != record["current_disposition"]:
        errors.append("transition.to must equal current_disposition")
    if record["revision"] == 1:
        if record.get("previous") is not None or record["transition"].get("from") is not None:
            errors.append("revision 1 must not have a previous status or transition.from")
    elif record.get("previous") is None:
        errors.append("revisions after 1 require previous path and hash")
    refs = [item["ref"] for item in record["evidence_manifest"]]
    if len(refs) != len(set(refs)):
        errors.append("evidence_manifest refs must be unique")
    for item in record["evidence_manifest"]:
        if "performance" in item["kind"].casefold() and not item["preserved"]:
            errors.append("performance evidence must remain preserved")
    return errors


def _validate_semantics_with_repository(repository: Path, record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    scope = record["work_scope"]
    if record["bug_id"] not in scope["bug_ids"]:
        errors.append("work_scope.bug_ids must include bug_id")
    if scope["scope_kind"] == "single" and len(scope["bug_ids"]) != 1:
        errors.append("single work scope must contain exactly one BUG")
    if scope["scope_kind"] == "common" and len(scope["bug_ids"]) < 2:
        errors.append("common work scope must contain at least two BUGs")
    _, assessment_errors = _validate_assessment_binding(repository, record)
    errors.extend(assessment_errors)
    _, verification_errors = _validate_verification_binding(repository, record)
    errors.extend(verification_errors)
    errors.extend(_validate_timebox(record))
    errors.extend(_validate_blocker_and_risk(record))
    errors.extend(_validate_fixed_gate(record))
    errors.extend(_validate_reviewer(repository, record))
    if record["current_disposition"] == "confirmed-open" and record["current_observation"]["status"] != "present":
        errors.append("confirmed-open requires a present current symptom observation")
    verification = record.get("verification")
    if isinstance(verification, dict) and verification.get("result") == "partial" and record["current_disposition"] == "fixed-verified":
        errors.append("partial verification cannot be fixed-verified")
    if record["transition"]["to"] != record["current_disposition"]:
        errors.append("transition.to must equal current_disposition")
    if record["revision"] == 1:
        if record.get("previous") is not None or record["transition"].get("from") is not None:
            errors.append("revision 1 must not have a previous status or transition.from")
    else:
        previous = record.get("previous")
        expected = f"docs/bugs/{record['bug_id']}/status-{record['revision'] - 1}.json"
        if not isinstance(previous, dict) or previous.get("path") != expected:
            errors.append("previous path must reference the immediately preceding BUG revision")
    refs = [item["ref"] for item in record["evidence_manifest"]]
    if len(refs) != len(set(refs)):
        errors.append("evidence_manifest refs must be unique")
    for item in record["evidence_manifest"]:
        if "performance" in item["kind"].casefold() and not item["preserved"]:
            errors.append("performance evidence must remain preserved")
    return errors


def validate_status_record(repository: str | Path, record_path: str | Path, data: dict[str, Any] | None = None) -> list[str]:
    """Validate one status record and all repository-side assessment bindings."""
    repo = Path(repository).resolve()
    candidate, relative, errors = _lexical_relative(repo, record_path)
    if candidate is None or relative is None:
        return errors
    match = STATUS_PATH_RE.fullmatch(relative)
    if match is None:
        errors.append("status path must be docs/bugs/<bug-id>/status-N.json")
    raw, read_errors = _read_stable(repo, candidate, "status JSON")
    errors.extend(read_errors)
    parsed: dict[str, Any] | None = None
    if raw is not None:
        parsed, parse_errors = _strict_json(raw, "status JSON")
        errors.extend(parse_errors)
    if data is None:
        data = parsed
    if data is None:
        return errors
    if match is not None:
        if data.get("bug_id") != match.group(1) or data.get("revision") != int(match.group(2)):
            errors.append("status path does not match bug_id and revision")
    schema_errors = _assessment.validate_instance(data, SCHEMA)
    errors.extend(schema_errors)
    if schema_errors:
        return errors
    errors.extend(_validate_semantics_with_repository(repo, data))
    return errors


def validate_status_file(repository: str | Path, record_path: str | Path) -> list[str]:
    return validate_status_record(repository, record_path)


def _status_paths(repository: Path) -> tuple[list[Path], list[str]]:
    root = repository / "docs" / "bugs"
    if not root.is_dir():
        return [], ["docs/bugs directory is missing"]
    paths: list[Path] = []
    errors: list[str] = []
    for directory in sorted(root.iterdir(), key=lambda item: item.name.encode("utf-8")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("status-*.json"), key=lambda item: item.name.encode("utf-8")):
            if not path.is_file() or _assessment._has_reparse_component(path, repository):
                errors.append(f"status path uses a symlink or reparse point: {path}")
            else:
                paths.append(path)
    return paths, errors


def validate_repository(repository: str | Path) -> list[str]:
    repo = Path(repository).resolve()
    paths, errors = _status_paths(repo)
    if not paths:
        return errors + ["no status records found"]
    grouped: dict[str, list[tuple[int, Path, dict[str, Any]]]] = {}
    for path in paths:
        relative = path.relative_to(repo).as_posix()
        match = STATUS_PATH_RE.fullmatch(relative)
        if match is None:
            errors.append(f"invalid status path: {relative}")
            continue
        raw, read_errors = _read_stable(repo, path, "status JSON")
        errors.extend(read_errors)
        if raw is None:
            continue
        data, parse_errors = _strict_json(raw, "status JSON")
        errors.extend(parse_errors)
        if data is None:
            continue
        revision = int(match.group(2))
        errors.extend(validate_status_record(repo, path, data))
        grouped.setdefault(match.group(1), []).append((revision, path, data))
    for bug_id, items in grouped.items():
        items.sort(key=lambda item: item[0])
        expected_revisions = list(range(1, items[-1][0] + 1))
        if [item[0] for item in items] != expected_revisions:
            errors.append(f"{bug_id} status revisions are not contiguous from 1")
        for revision, path, data in items:
            if revision == 1:
                continue
            previous_path = repo / "docs" / "bugs" / bug_id / f"status-{revision - 1}.json"
            raw_previous, previous_errors = _read_stable(repo, previous_path, "previous status JSON")
            errors.extend(previous_errors)
            if raw_previous is None:
                continue
            previous_data, previous_parse_errors = _strict_json(raw_previous, "previous status JSON")
            errors.extend(previous_parse_errors)
            if sha256_bytes(raw_previous) != data.get("previous", {}).get("sha256"):
                errors.append(f"{bug_id} revision {revision} previous hash mismatch")
            if isinstance(previous_data, dict) and data.get("transition", {}).get("from") != previous_data.get("current_disposition"):
                errors.append(f"{bug_id} revision {revision} transition.from mismatch")
    return errors


def _record_row(data: dict[str, Any], path: Path, repository: Path) -> dict[str, Any]:
    verification = data.get("verification")
    blocker = data.get("blocker")
    risk = data.get("risk_decision")
    status_raw = _assessment._stable_assessment_read(repository, path)
    assessment = data["assessment"]
    return {
        "bug_id": data["bug_id"],
        "status_path": path.relative_to(repository).as_posix(),
        "status_sha256": sha256_bytes(status_raw),
        "revision": data["revision"],
        "assessment_revision": data["assessment"]["revision"],
        "assessment_path": assessment["path"],
        "assessment_sha256": assessment["sha256"],
        "assessment_markdown_path": assessment["markdown_path"],
        "assessment_markdown_sha256": assessment["markdown_sha256"],
        "severity": data["severity"],
        "verification_result": verification.get("result") if isinstance(verification, dict) else None,
        "current_disposition": data["current_disposition"],
        "owner": data["tracking"]["owner"],
        "implementation_owner": data["tracking"]["implementation_owner"],
        "next_action": data["tracking"]["next_action"],
        "due_date": data["tracking"]["due_date"],
        "blocker_class": blocker.get("class") if isinstance(blocker, dict) else None,
        "risk_decision": risk.get("decision") if isinstance(risk, dict) else None,
        "required_platforms": data["required_platforms"],
        "platform_evidence": data["platform_evidence"],
    }


def build_report(repository: str | Path) -> dict[str, Any]:
    repo = Path(repository).resolve()
    errors = validate_repository(repo)
    if errors:
        raise ValueError("; ".join(errors))
    paths, _ = _status_paths(repo)
    latest: dict[str, tuple[Path, dict[str, Any]]] = {}
    preserved: set[str] = set()
    performance: list[dict[str, Any]] = []
    for path in paths:
        raw = _assessment._stable_assessment_read(repo, path)
        data, parse_errors = _strict_json(raw, "status JSON")
        if parse_errors or data is None:
            raise ValueError("; ".join(parse_errors or ["status JSON is invalid"]))
        current = latest.get(data["bug_id"])
        if current is None or data["revision"] > current[1]["revision"]:
            latest[data["bug_id"]] = (path, data)
        for item in data["evidence_manifest"]:
            if item["preserved"]:
                preserved.add(item["ref"])
            if "performance" in item["kind"].casefold():
                performance.append({"bug_id": data["bug_id"], "ref": item["ref"], "sha256": item["sha256"], "preserved": item["preserved"]})
    rows = [_record_row(data, path, repo) for path, data in sorted(latest.values(), key=lambda item: item[1]["bug_id"].encode("utf-8"))]
    counts = {disposition: 0 for disposition in DISPOSITIONS}
    verification_counts: dict[str, int] = {"verified": 0, "partial": 0, "failed": 0, "none": 0}
    for row in rows:
        counts[row["current_disposition"]] += 1
        verification_counts[row["verification_result"] or "none"] += 1
    return {
        "schema": "bug-status-report/v1",
        "status_record_count": len(rows),
        "records": rows,
        "counts": counts,
        "unresolved_count": sum(counts[name] for name in UNRESOLVED_DISPOSITIONS),
        "terminal_count": counts["fixed-verified"] + counts["rejected"],
        "verification_counts": verification_counts,
        "preserved_evidence_refs": sorted(preserved),
        "performance_evidence": sorted(performance, key=lambda item: (item["bug_id"], item["ref"])),
    }


def render_report(report: dict[str, Any]) -> str:
    lines = [
        "# BUG Status Review",
        "",
        f"- Status records: {report['status_record_count']}",
        f"- Unresolved: {report['unresolved_count']}",
        "",
        "| BUG | Severity | Verification | Disposition | Owner | Due |",
        "|---|---|---|---|---|---|",
    ]
    for row in report["records"]:
        lines.append(
            f"| {row['bug_id']} | {row['severity']} | {row['verification_result'] or 'none'} | "
            f"{row['current_disposition']} | {row['owner']} | {row['due_date']} |"
        )
    lines.extend(["", "## Counts", ""])
    for name in DISPOSITIONS:
        lines.append(f"- {name}: {report['counts'][name]}")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only BUG closure status validator and reporter.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    validate = subparsers.add_parser("validate", help="validate one status record")
    validate.add_argument("--repo", required=True)
    validate.add_argument("--path", required=True)
    report = subparsers.add_parser("report", help="render the current status report")
    report.add_argument("--repo", required=True)
    report.add_argument("--markdown", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.action == "validate":
            errors = validate_status_file(args.repo, args.path)
            payload = {"schema": "bug-closure-validation/v1", "path": args.path, "valid": not errors, "errors": errors}
        else:
            report = build_report(args.repo)
            payload = render_report(report) if args.markdown else report
    except (OSError, ValueError) as exc:
        payload = {"schema": "bug-status-report/v1", "valid": False, "errors": [str(exc)]}
    if isinstance(payload, str):
        print(payload, end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not isinstance(payload, dict) or not payload.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
