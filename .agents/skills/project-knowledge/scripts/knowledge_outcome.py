"""Persist implementation outcomes and derive reviewed knowledge Candidates."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

import knowledge_governance
from knowledge_governance import _ready_plan_contract_errors, render_index
from knowledge_promotion import _redirected, _scan_secrets
from knowledge_query import (
    KnowledgeError,
    _eligible_paths,
    _metadata_is_redirect,
    _run,
    normalized_path,
    sha256_bytes,
)


WORK_ID_RE = re.compile(r"^(?=[a-z0-9-]{3,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
REVIEW_REF_RE = re.compile(r"^review:fresh-review:[a-z0-9][a-z0-9._-]{2,127}$")
RUN_ID_RE = re.compile(r"^[a-f0-9]{64}$")
REVIEW_REPORT_REF_RE = re.compile(
    r"^reviews/[a-z0-9][a-z0-9._-]{2,127}/report\.json$"
)


def _load_implementation_contracts() -> tuple[Any, dict[str, Any]]:
    """Load the implementation owner's BUG validator without a package dependency."""

    skills_root = Path(__file__).resolve().parents[2]
    validator_path = skills_root / "implementation-execution" / "scripts" / "validate_contracts.py"
    schema_path = skills_root / "implementation-execution" / "references" / "execution-records.schema.json"
    spec = importlib.util.spec_from_file_location(
        "project_knowledge_implementation_contracts",
        validator_path,
    )
    if spec is None or spec.loader is None:
        raise KnowledgeError(
            "BUG_VALIDATOR_UNAVAILABLE",
            f"cannot load implementation BUG validator: {validator_path}",
            exit_code=4,
        )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise KnowledgeError(
            "BUG_VALIDATOR_UNAVAILABLE",
            "implementation BUG contracts are unavailable",
            exit_code=4,
        ) from exc
    return module, schema


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            f"{label} is not strict UTF-8 JSON",
            exit_code=2,
        ) from exc
    if not isinstance(value, dict):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            f"{label} is not an object",
            exit_code=2,
        )
    return value


def _implementation_run_root(implementation_run_id: str) -> Path:
    if not isinstance(implementation_run_id, str) or RUN_ID_RE.fullmatch(
        implementation_run_id
    ) is None:
        raise KnowledgeError(
            "IMPLEMENTATION_RUN_INVALID",
            "implementation_run_id must be a SHA-256 identifier",
            exit_code=2,
        )
    host_temp = Path(tempfile.gettempdir()).resolve()
    run_root = (
        host_temp
        / "implementation-execution"
        / "runs"
        / implementation_run_id
    )
    if _redirected(run_root, host_temp):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_REDIRECTED",
            "implementation review run root is redirected",
            exit_code=3,
        )
    try:
        run_root.resolve(strict=False).relative_to(host_temp)
    except (OSError, ValueError) as exc:
        raise KnowledgeError(
            "IMPLEMENTATION_RUN_INVALID",
            "implementation review run root escapes host temp",
            exit_code=3,
        ) from exc
    if not run_root.is_dir():
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_MISSING",
            "implementation review run root does not exist",
            exit_code=3,
        )
    return run_root


def _stable_read_evidence(run_root: Path, relative: str) -> bytes:
    normalized = normalized_path(relative)
    lexical = run_root / Path(*normalized.split("/"))
    if _redirected(lexical, run_root):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_REDIRECTED",
            f"implementation review evidence is redirected: {normalized}",
            exit_code=3,
        )
    try:
        before = lexical.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise OSError("evidence is not a regular file")
        raw = lexical.read_bytes()
        after = lexical.lstat()
    except OSError as exc:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_MISSING",
            f"implementation review evidence is missing: {normalized}",
            exit_code=3,
        ) from exc
    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if fingerprint_before != fingerprint_after or _redirected(lexical, run_root):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_DRIFT",
            f"implementation review evidence changed while read: {normalized}",
            exit_code=3,
        )
    return raw


def _stable_read_bound_file(root: Path, path: Path, label: str) -> bytes:
    """Read a regular file below an authoritative root without blessing redirects or swaps."""

    if _redirected(path, root):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_REDIRECTED",
            f"{label} is redirected",
            exit_code=3,
        )
    try:
        root_metadata = root.lstat()
        if _metadata_is_redirect(root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
            raise OSError(f"{label} root is not a regular directory")
        before = path.lstat()
        if _metadata_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            raise OSError(f"{label} is not a regular file")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_MISSING",
            f"{label} is unavailable",
            exit_code=3,
        ) from exc
    fingerprint_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    )
    fingerprint_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    )
    if (
        fingerprint_before != fingerprint_after
        or _metadata_is_redirect(after)
        or _redirected(path, root)
    ):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_DRIFT",
            f"{label} changed while read",
            exit_code=3,
        )
    return raw


def _bound_ready_for_run(
    run_root: Path,
    implementation_run_id: str,
) -> dict[str, Any]:
    """Resolve and validate the exact Ready handoff named by an implementation Ledger."""

    ledger = _strict_json_object(
        _stable_read_evidence(run_root, "run.json"),
        "implementation Ledger",
    )
    binding = ledger.get("binding")
    handoff_value = ledger.get("handoff_path")
    if (
        ledger.get("schema") != "implementation-ledger/v1"
        or ledger.get("run_id") != implementation_run_id
        or not isinstance(binding, dict)
        or binding.get("run_id") != implementation_run_id
        or not isinstance(binding.get("canonical_worktree"), str)
        or not binding.get("canonical_worktree")
        or not isinstance(handoff_value, str)
    ):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "implementation Ledger does not bind the requested run and Ready handoff",
            exit_code=3,
        )
    try:
        handoff_relative = normalized_path(handoff_value)
    except KnowledgeError as exc:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "implementation Ready handoff path is invalid",
            exit_code=3,
        ) from exc
    canonical_worktree = Path(binding["canonical_worktree"])
    if not canonical_worktree.is_absolute():
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "implementation canonical worktree path is not absolute",
            exit_code=3,
        )
    handoff_path = canonical_worktree / Path(*handoff_relative.split("/"))
    ready = _strict_json_object(
        _stable_read_bound_file(
            canonical_worktree,
            handoff_path,
            "implementation Ready handoff",
        ),
        "implementation Ready handoff",
    )
    ready_errors = _ready_plan_contract_errors(ready)
    if ready_errors or ready.get("approval", {}).get("status") != "Ready":
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "; ".join(
                dict.fromkeys(
                    [
                        *ready_errors,
                        *(
                            ["implementation handoff is not Ready"]
                            if ready.get("approval", {}).get("status") != "Ready"
                            else []
                        ),
                    ]
                )
            ),
            exit_code=3,
        )
    return ready


def _validated_preliminary_review(
    *,
    implementation_run_id: str,
    review: dict[str, Any],
    verification: list[dict[str, Any]],
    known_secret_values: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Load and verify the physically persisted review that may justify an outcome."""

    run_root = _implementation_run_root(implementation_run_id)
    report_ref = review.get("report_ref")
    report_sha256 = review.get("report_sha256")
    if (
        not isinstance(report_ref, str)
        or REVIEW_REPORT_REF_RE.fullmatch(report_ref) is None
        or not isinstance(report_sha256, str)
        or RUN_ID_RE.fullmatch(report_sha256) is None
    ):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "preliminary review report binding is invalid",
            exit_code=2,
        )
    report_raw = _stable_read_evidence(run_root, report_ref)
    if sha256_bytes(report_raw) != report_sha256:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_DRIFT",
            "preliminary review report hash drifted",
            exit_code=3,
        )
    report = _strict_json_object(report_raw, "preliminary review report")
    validator, schema = _load_implementation_contracts()
    errors = list(validator.validate_instance(report, schema, "reviewReport"))
    errors.extend(
        validator.validate_execution_record_semantics(
            report,
            known_secret_values=known_secret_values,
        )
    )
    ready = _bound_ready_for_run(run_root, implementation_run_id)
    errors.extend(
        validator.validate_review_against_ready(
            report,
            ready,
            known_secret_values,
        )
    )
    evidence_refs = review.get("evidence_refs", [])
    if (
        report.get("logical_ref") not in evidence_refs
        or len(evidence_refs) != 1
        or report.get("verdict") != review.get("verdict")
    ):
        errors.append("preliminary review report differs from the outcome review binding")
    if any(
        report.get(field) is not None
        for field in (
            "knowledge_snapshot_before",
            "knowledge_snapshot_after",
            "knowledge_candidate_ref",
            "knowledge_candidate_payload_sha256",
        )
    ):
        errors.append("preliminary review must precede outcome and knowledge Candidate creation")
    report_raw_refs = report.get("raw_output_refs", [])
    raw_refs = set(report_raw_refs) if isinstance(report_raw_refs, list) else set()
    if len(raw_refs) != len(report_raw_refs):
        errors.append("preliminary review raw output refs are duplicated")
    for raw_ref in raw_refs:
        try:
            if not isinstance(raw_ref, str) or normalized_path(raw_ref) != raw_ref:
                raise KnowledgeError("INVALID", "invalid", exit_code=2)
            _stable_read_evidence(run_root, raw_ref)
        except KnowledgeError:
            errors.append(f"preliminary review raw output is missing or invalid: {raw_ref}")
    report_commands = {
        item.get("command_id"): item
        for item in report.get("command_outcomes", [])
        if isinstance(item, dict)
    }
    for command in verification:
        report_command = report_commands.get(command.get("command_id"))
        output_ref = report_command.get("output_ref") if isinstance(report_command, dict) else None
        if (
            not isinstance(report_command, dict)
            or report_command.get("outcome") != command.get("outcome")
            or not isinstance(output_ref, str)
            or output_ref not in command.get("evidence_refs", [])
            or output_ref not in raw_refs
        ):
            errors.append(
                f"outcome verification differs from preliminary review: {command.get('command_id')}"
            )
    if errors:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "; ".join(dict.fromkeys(errors)),
            exit_code=3,
        )
    return report


def persist_preliminary_review_report(
    *,
    implementation_run_id: str,
    report_ref: str,
    report: dict[str, Any],
    raw_outputs: dict[str, str | bytes],
    known_secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    """Persist one fresh preliminary report and its exact raw outputs create-only."""

    run_root = _implementation_run_root(implementation_run_id)
    secrets = tuple(known_secret_values)
    if REVIEW_REPORT_REF_RE.fullmatch(report_ref) is None:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "preliminary report ref is not canonical",
            exit_code=2,
        )
    validator, schema = _load_implementation_contracts()
    errors = list(validator.validate_instance(report, schema, "reviewReport"))
    errors.extend(
        validator.validate_execution_record_semantics(
            report,
            known_secret_values=secrets,
        )
    )
    ready = _bound_ready_for_run(run_root, implementation_run_id)
    errors.extend(
        validator.validate_review_against_ready(
            report,
            ready,
            secrets,
        )
    )
    report_root = report_ref.rsplit("/", 1)[0]
    raw_refs = report.get("raw_output_refs", [])
    if (
        not isinstance(raw_outputs, dict)
        or set(raw_outputs) != set(raw_refs)
        or any(
            not isinstance(ref, str)
            or normalized_path(ref) != ref
            or not ref.startswith(f"{report_root}/outputs/")
            for ref in raw_outputs
        )
    ):
        errors.append("preliminary raw outputs must exactly match the report-scoped refs")
    if errors:
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_INVALID",
            "; ".join(dict.fromkeys(errors)),
            exit_code=2,
        )
    values: list[tuple[Path, bytes]] = []
    for relative in sorted(raw_outputs, key=lambda value: value.encode("utf-8")):
        raw_value = raw_outputs[relative]
        encoded = raw_value if isinstance(raw_value, bytes) else raw_value.encode("utf-8")
        target = run_root / Path(*relative.split("/"))
        if _redirected(target, run_root):
            raise KnowledgeError(
                "PRELIMINARY_REVIEW_REDIRECTED",
                f"preliminary review target is redirected: {relative}",
                exit_code=3,
            )
        _scan_secrets(encoded, secrets, relative)
        values.append((target, encoded))
    encoded_report = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    report_target = run_root / Path(*report_ref.split("/"))
    if _redirected(report_target, run_root):
        raise KnowledgeError(
            "PRELIMINARY_REVIEW_REDIRECTED",
            "preliminary review report target is redirected",
            exit_code=3,
        )
    _scan_secrets(encoded_report, secrets, report_ref)
    values.append((report_target, encoded_report))
    _write_pair_create_only(
        values,
        collision_code="PRELIMINARY_REVIEW_EXISTS",
        collision_message="preliminary review report or raw output already exists",
    )
    return {
        "schema": "preliminary-review-result/v1",
        "implementation_run_id": implementation_run_id,
        "logical_ref": report["logical_ref"],
        "report_ref": report_ref,
        "report_sha256": sha256_bytes(encoded_report),
        "verdict": report["verdict"],
    }


def _bullet_lines(values: list[str]) -> str:
    return "".join(f"- {value}\n" for value in values) if values else "- None\n"


def _render_outcome_markdown(
    *,
    result: str,
    summary: str,
    knowledge_decision: str,
    bug_details: dict[str, Any] | None,
) -> bytes:
    if bug_details is None:
        return (
            "# Implementation Outcome\n\n"
            f"Status: {result}\n\n"
            "## Summary\n\n"
            f"{summary}\n\n"
            "## Knowledge decision\n\n"
            f"{knowledge_decision}\n"
        ).encode("utf-8")

    original = bug_details["original_reproduction"]
    regression = bug_details["regression"]
    proxy = bug_details["proxy"]
    status = {
        "verified": "Verified",
        "partial": "Partial / Unresolved",
        "failed": "Failed / Unresolved",
    }[result]
    text = (
        f"# BUG Incident: {bug_details['bug_id']}\n\n"
        f"Status: {status}\n\n"
        "## Summary\n\n"
        f"{summary}\n\n"
        "## Original symptom\n\n"
        f"Original symptom before change: {original['pre_fix']['status']}\n\n"
        f"Original symptom after change: {original['post_fix']['status']}\n\n"
        "## Regression evidence\n\n"
        f"BDD refs: {', '.join(regression['bdd_refs']) or 'None'}\n\n"
        f"TEST refs: {', '.join(regression['test_refs']) or 'None'}\n\n"
        f"Red evidence: {', '.join(regression['red_evidence_refs']) or 'None'}\n\n"
        f"Green evidence: {', '.join(regression['green_evidence_refs']) or 'None'}\n"
    )
    if result == "partial":
        text += (
            "\n## Proxy evidence\n\n"
            f"BDD refs: {', '.join(proxy['bdd_refs']) or 'None'}\n\n"
            f"TEST refs: {', '.join(proxy['test_refs']) or 'None'}\n\n"
            f"Red evidence: {', '.join(proxy['red_evidence_refs']) or 'None'}\n\n"
            f"Green evidence: {', '.join(proxy['green_evidence_refs']) or 'None'}\n\n"
            "## Residual risks\n\n"
            f"{_bullet_lines(bug_details['residual_risks'])}\n"
            "## Follow-up\n\n"
            f"{_bullet_lines(bug_details['follow_up'])}"
        )
    text += (
        "\n## Knowledge decision\n\n"
        f"{knowledge_decision}\n"
    )
    return text.encode("utf-8")


def _publish_outcome_path_create_only(source: Path, destination: Path) -> None:
    knowledge_governance._rename_path_create_only(
        source,
        destination,
        unsafe_code="UNSAFE_OUTCOME",
        unsupported_message="atomic create-only review and Outcome publication is unsupported",
        filesystem_message="filesystem lacks atomic create-only review and Outcome publication",
    )


def _pair_publication_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    if _metadata_is_redirect(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise KnowledgeError(
            "UNSAFE_OUTCOME",
            "review and Outcome staging must remain regular files",
            exit_code=3,
        )
    return metadata.st_dev, metadata.st_ino


def _rollback_pair_publication(
    target: Path,
    expected: bytes,
    expected_identity: tuple[int, int],
    ownership_anchor: Path,
) -> None:
    retired = target.parent / (
        f".{target.name}.rollback-current.{uuid.uuid4().hex}.tmp"
    )
    try:
        _publish_outcome_path_create_only(target, retired)
    except FileNotFoundError:
        return
    try:
        current_identity = _pair_publication_identity(retired)
    except (KnowledgeError, OSError):
        current_identity = None
    try:
        anchor_identity = _pair_publication_identity(ownership_anchor)
    except (KnowledgeError, OSError):
        anchor_identity = None
    if current_identity == expected_identity == anchor_identity:
        try:
            current = retired.read_bytes()
        except OSError as exc:
            try:
                _publish_outcome_path_create_only(retired, target)
            except FileExistsError as restore_exc:
                raise KnowledgeError(
                    "OUTCOME_ROLLBACK_CONFLICT",
                    "rollback could not restore unreadable review or Outcome bytes",
                    exit_code=5,
                    evidence_refs=[os.fspath(target)],
                    recoverable=False,
                ) from restore_exc
            raise KnowledgeError(
                "OUTCOME_ROLLBACK_UNREADABLE",
                "rollback restored review or Outcome bytes that could not be verified",
                exit_code=5,
                evidence_refs=[os.fspath(target)],
                recoverable=False,
            ) from exc
        if current == expected:
            retired.unlink(missing_ok=True)
            return
    try:
        _publish_outcome_path_create_only(retired, target)
    except FileExistsError as exc:
        raise KnowledgeError(
            "OUTCOME_ROLLBACK_CONFLICT",
            "rollback preserved independently changed review or Outcome bytes",
            exit_code=5,
            evidence_refs=[os.fspath(target)],
            recoverable=False,
        ) from exc


def _write_pair_create_only(
    paths_and_values: list[tuple[Path, bytes]],
    *,
    collision_code: str = "OUTCOME_EXISTS",
    collision_message: str = "implementation outcome paths are create-only",
) -> None:
    staged: list[tuple[Path, Path, tuple[int, int], Path]] = []
    committed: list[tuple[Path, bytes, tuple[int, int], Path]] = []
    try:
        for target, value in paths_and_values:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
            ownership_anchor = target.parent / (
                f".{target.name}.{uuid.uuid4().hex}.owner"
            )
            with open(temporary, "xb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, ownership_anchor)
                identity = _pair_publication_identity(temporary)
            except (KnowledgeError, OSError) as exc:
                ownership_anchor.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
                if isinstance(exc, KnowledgeError):
                    raise
                raise KnowledgeError(
                    "UNSAFE_OUTCOME",
                    "filesystem lacks ownership-safe review and Outcome rollback",
                    exit_code=3,
                ) from exc
            staged.append((temporary, target, identity, ownership_anchor))
        if any(target.exists() for _, target, _, _ in staged):
            raise KnowledgeError(
                collision_code,
                collision_message,
                exit_code=3,
            )
        for (temporary, target, identity, ownership_anchor), (_, value) in zip(
            staged,
            paths_and_values,
        ):
            try:
                _publish_outcome_path_create_only(temporary, target)
            except FileExistsError as exc:
                raise KnowledgeError(
                    collision_code,
                    collision_message,
                    exit_code=3,
                ) from exc
            committed.append((target, value, identity, ownership_anchor))
    except BaseException as exc:
        for temporary, _, _, _ in staged:
            temporary.unlink(missing_ok=True)
        rollback_error: KnowledgeError | None = None
        for target, expected, identity, ownership_anchor in reversed(committed):
            try:
                _rollback_pair_publication(
                    target,
                    expected,
                    identity,
                    ownership_anchor,
                )
            except KnowledgeError as error:
                rollback_error = error
        if rollback_error is not None:
            raise rollback_error from exc
        raise
    finally:
        for _, _, _, ownership_anchor in staged:
            ownership_anchor.unlink(missing_ok=True)


def _validate_outcome_inputs(
    repo: Path,
    *,
    work_id: str,
    implementation_run_id: str,
    revision: int,
    work_kind: str,
    result: str,
    summary: str,
    changes: list[dict[str, str]],
    verification: list[dict[str, Any]],
    review: dict[str, Any],
    known_deviations: list[str],
    knowledge_decision: str,
    bug_verification_ref: str | None,
    bug_details: dict[str, Any] | None,
    created_at: str,
) -> None:
    if WORK_ID_RE.fullmatch(work_id) is None:
        raise KnowledgeError("OUTCOME_INVALID", "work_id is invalid", exit_code=2)
    if RUN_ID_RE.fullmatch(implementation_run_id) is None:
        raise KnowledgeError("OUTCOME_INVALID", "implementation_run_id is invalid", exit_code=2)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise KnowledgeError("OUTCOME_REVISION_INVALID", "outcome revision is invalid", exit_code=2)
    if work_kind not in {"standard", "bug"}:
        raise KnowledgeError("OUTCOME_INVALID", "work_kind is invalid", exit_code=2)
    if result not in {"complete", "verified", "partial", "failed"}:
        raise KnowledgeError("OUTCOME_INVALID", "result is invalid", exit_code=2)
    if work_kind == "standard" and result != "complete":
        raise KnowledgeError("OUTCOME_INVALID", "standard outcome result must be complete", exit_code=2)
    if work_kind == "bug" and result == "complete":
        raise KnowledgeError("OUTCOME_INVALID", "BUG outcome must use verification semantics", exit_code=2)
    if not isinstance(summary, str) or not summary.strip() or "\n" in summary or "\r" in summary:
        raise KnowledgeError("OUTCOME_INVALID", "summary must be one non-empty line", exit_code=2)
    if not isinstance(changes, list) or not changes:
        raise KnowledgeError("OUTCOME_INVALID", "changes must be non-empty", exit_code=2)
    eligible = _eligible_paths(repo)
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "summary"}:
            raise KnowledgeError("OUTCOME_INVALID", "change entry is invalid", exit_code=2)
        path = normalized_path(str(change["path"]))
        if path.startswith("docs/knowledge/") or path not in eligible:
            raise KnowledgeError("OUTCOME_INVALID", f"change path is not an eligible product path: {path}", exit_code=3)
        if not isinstance(change["summary"], str) or not change["summary"].strip():
            raise KnowledgeError("OUTCOME_INVALID", "change summary is empty", exit_code=2)
    if not isinstance(verification, list) or not verification:
        raise KnowledgeError("OUTCOME_INVALID", "verification must be non-empty", exit_code=2)
    for command in verification:
        if (
            not isinstance(command, dict)
            or set(command) != {"command_id", "outcome", "evidence_refs"}
            or command.get("outcome") not in {"passed", "failed", "not_run"}
            or not isinstance(command.get("evidence_refs"), list)
            or not command.get("evidence_refs")
            or any(not isinstance(ref, str) or not ref for ref in command.get("evidence_refs", []))
        ):
            raise KnowledgeError("OUTCOME_INVALID", "verification entry is invalid", exit_code=2)
    command_ids = [command["command_id"] for command in verification]
    if len(command_ids) != len(set(command_ids)):
        raise KnowledgeError("OUTCOME_INVALID", "verification command IDs are duplicated", exit_code=2)
    if (
        not isinstance(review, dict)
        or set(review) != {
            "verdict",
            "evidence_refs",
            "report_ref",
            "report_sha256",
        }
        or review.get("verdict") not in {"APPROVED", "CHANGES_REQUIRED", "BLOCKED"}
        or not isinstance(review.get("evidence_refs"), list)
        or not review["evidence_refs"]
        or any(
            not isinstance(ref, str) or REVIEW_REF_RE.fullmatch(ref) is None
            for ref in review.get("evidence_refs", [])
        )
        or len(review.get("evidence_refs", [])) != 1
        or not isinstance(review.get("report_ref"), str)
        or REVIEW_REPORT_REF_RE.fullmatch(review["report_ref"]) is None
        or not isinstance(review.get("report_sha256"), str)
        or RUN_ID_RE.fullmatch(review["report_sha256"]) is None
    ):
        raise KnowledgeError("OUTCOME_INVALID", "review binding is invalid", exit_code=2)
    if result in {"complete", "verified"} and any(
        command["outcome"] != "passed" for command in verification
    ):
        raise KnowledgeError(
            "OUTCOME_CERTAINTY_INVALID",
            f"{result} outcome requires every verification command to pass",
            exit_code=3,
        )
    if result in {"complete", "verified", "partial"} and review.get("verdict") != "APPROVED":
        raise KnowledgeError(
            "OUTCOME_CERTAINTY_INVALID",
            f"{result} outcome requires an accepted fresh review",
            exit_code=3,
        )
    if result == "failed" and review.get("verdict") == "APPROVED":
        raise KnowledgeError(
            "OUTCOME_CERTAINTY_INVALID",
            "failed outcome cannot claim an APPROVED review",
            exit_code=3,
        )
    if not isinstance(known_deviations, list) or any(
        not isinstance(value, str) or not value for value in known_deviations
    ):
        raise KnowledgeError("OUTCOME_INVALID", "known_deviations is invalid", exit_code=2)
    if knowledge_decision not in {"change", "no-change"}:
        raise KnowledgeError("OUTCOME_INVALID", "knowledge_decision is invalid", exit_code=2)
    if (work_kind == "bug") != isinstance(bug_verification_ref, str):
        raise KnowledgeError("OUTCOME_INVALID", "BUG verification binding is inconsistent", exit_code=2)
    if work_kind == "standard" and bug_details is not None:
        raise KnowledgeError("OUTCOME_INVALID", "standard outcome cannot contain BUG details", exit_code=2)
    if work_kind == "bug":
        expected_bug_fields = {
            "bug_id",
            "original_reproduction",
            "regression",
            "proxy",
            "residual_risks",
            "follow_up",
            "implementation_review_ref",
        }
        if not isinstance(bug_details, dict) or set(bug_details) != expected_bug_fields:
            raise KnowledgeError("OUTCOME_INVALID", "BUG outcome details are invalid", exit_code=2)
    if not isinstance(created_at, str) or "T" not in created_at:
        raise KnowledgeError("OUTCOME_INVALID", "created_at is invalid", exit_code=2)


def write_implementation_outcome(
    repo_value: str,
    *,
    work_id: str,
    implementation_run_id: str,
    work_kind: str,
    result: str,
    summary: str,
    changes: list[dict[str, str]],
    verification: list[dict[str, Any]],
    review: dict[str, Any],
    known_deviations: list[str],
    knowledge_decision: str,
    bug_verification_ref: str | None,
    created_at: str,
    bug_details: dict[str, Any] | None = None,
    known_secret_values: Iterable[str] = (),
    revision: int = 1,
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    secrets = tuple(known_secret_values)
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    _validate_outcome_inputs(
        repo,
        work_id=work_id,
        implementation_run_id=implementation_run_id,
        revision=revision,
        work_kind=work_kind,
        result=result,
        summary=summary,
        changes=changes,
        verification=verification,
        review=review,
        known_deviations=known_deviations,
        knowledge_decision=knowledge_decision,
        bug_verification_ref=bug_verification_ref,
        bug_details=bug_details,
        created_at=created_at,
    )
    _validated_preliminary_review(
        implementation_run_id=implementation_run_id,
        review=review,
        verification=verification,
        known_secret_values=secrets,
    )
    root = f"docs/work/{work_id}/implementation"
    suffix = "" if revision == 1 else f"-{revision}"
    markdown_path = f"{root}/outcome{suffix}.md"
    json_path = f"{root}/outcome{suffix}.json"
    for prior_revision in range(1, revision):
        prior_suffix = "" if prior_revision == 1 else f"-{prior_revision}"
        prior_paths = (
            repo / Path(*f"{root}/outcome{prior_suffix}.md".split("/")),
            repo / Path(*f"{root}/outcome{prior_suffix}.json".split("/")),
        )
        if not all(path.is_file() and not _redirected(path, repo) for path in prior_paths):
            raise KnowledgeError(
                "OUTCOME_REVISION_INVALID",
                "outcome revisions must be create-only and contiguous",
                exit_code=3,
            )
    markdown = _render_outcome_markdown(
        result=result,
        summary=summary,
        knowledge_decision=knowledge_decision,
        bug_details=bug_details,
    )
    recorded_changes = [
        {
            "path": normalized_path(change["path"]),
            "sha256": sha256_bytes(
                (repo / Path(*normalized_path(change["path"]).split("/"))).read_bytes()
            ),
            "summary": change["summary"],
        }
        for change in changes
    ]
    record = {
        "schema": "implementation-outcome/v1",
        "work_id": work_id,
        "implementation_run_id": implementation_run_id,
        "revision": revision,
        "work_kind": work_kind,
        "result": result,
        "summary": summary,
        "changes": recorded_changes,
        "verification": verification,
        "review": review,
        "known_deviations": known_deviations,
        "knowledge_decision": knowledge_decision,
        "bug_verification_ref": bug_verification_ref,
        "bug": bug_details,
        "markdown": {
            "path": markdown_path,
            "sha256": sha256_bytes(markdown),
        },
        "created_at": created_at,
    }
    encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    validator, schema = _load_implementation_contracts()
    contract_errors = validator.validate_instance(record, schema, "implementationOutcome")
    contract_errors.extend(validator.validate_execution_record_semantics(record))
    if contract_errors:
        raise KnowledgeError(
            "OUTCOME_INVALID",
            "; ".join(dict.fromkeys(contract_errors)),
            exit_code=2,
        )
    for relative, value in ((markdown_path, markdown), (json_path, encoded)):
        target = repo / Path(*relative.split("/"))
        if _redirected(target, repo):
            raise KnowledgeError("OUTCOME_REDIRECTED", f"outcome target is redirected: {relative}", exit_code=3)
        ignored = _run(
            ["git", "check-ignore", "--no-index", "-q", "--", relative],
            cwd=repo,
            accepted={0, 1},
            code="GIT_UNAVAILABLE",
        )
        if ignored.returncode == 0:
            raise KnowledgeError("OUTCOME_IGNORED", f"outcome target is ignored: {relative}", exit_code=3)
        _scan_secrets(value, secrets, relative)
    _write_pair_create_only(
        [
            (repo / Path(*markdown_path.split("/")), markdown),
            (repo / Path(*json_path.split("/")), encoded),
        ]
    )
    return {
        "schema": "implementation-outcome-result/v1",
        "path": json_path,
        "sha256": sha256_bytes(encoded),
        "markdown_path": markdown_path,
        "markdown_sha256": sha256_bytes(markdown),
        "record": record,
    }


def validate_implementation_outcome_result(
    repo_value: str,
    *,
    outcome: dict[str, Any],
    expected_work_id: str | None = None,
    expected_run_id: str | None = None,
    known_secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    """Re-derive a persisted outcome, including its preliminary review evidence."""

    repo = Path(repo_value).resolve()
    if not repo.is_dir():
        raise KnowledgeError("REPOSITORY_MISSING", "repository root does not exist", exit_code=4)
    if not isinstance(outcome, dict) or set(outcome) != {
        "schema",
        "path",
        "sha256",
        "markdown_path",
        "markdown_sha256",
        "record",
    } or outcome.get("schema") != "implementation-outcome-result/v1":
        raise KnowledgeError("OUTCOME_INVALID", "outcome result contract is invalid", exit_code=2)
    record = outcome.get("record")
    if not isinstance(record, dict):
        raise KnowledgeError("OUTCOME_INVALID", "outcome record is missing", exit_code=2)
    work_id = record.get("work_id")
    if not isinstance(work_id, str) or WORK_ID_RE.fullmatch(work_id) is None:
        raise KnowledgeError("OUTCOME_INVALID", "outcome Work ID is invalid", exit_code=2)
    revision = record.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise KnowledgeError("OUTCOME_INVALID", "outcome revision is invalid", exit_code=2)
    suffix = "" if revision == 1 else f"-{revision}"
    expected_paths = {
        "path": f"docs/work/{work_id}/implementation/outcome{suffix}.json",
        "markdown_path": f"docs/work/{work_id}/implementation/outcome{suffix}.md",
    }
    for prior_revision in range(1, revision):
        prior_suffix = "" if prior_revision == 1 else f"-{prior_revision}"
        prior_paths = (
            repo
            / Path(
                *f"docs/work/{work_id}/implementation/outcome{prior_suffix}.{extension}".split(
                    "/"
                )
            )
            for extension in ("md", "json")
        )
        if not all(path.is_file() and not _redirected(path, repo) for path in prior_paths):
            raise KnowledgeError(
                "OUTCOME_REVISION_INVALID",
                "persisted outcome revisions are not contiguous",
                exit_code=3,
            )
    persisted: dict[str, bytes] = {}
    for path_key, hash_key in (("path", "sha256"), ("markdown_path", "markdown_sha256")):
        relative = normalized_path(str(outcome.get(path_key, "")))
        if relative != expected_paths[path_key]:
            raise KnowledgeError("OUTCOME_INVALID", f"{path_key} is not canonical", exit_code=2)
        target = repo / Path(*relative.split("/"))
        if _redirected(target, repo) or not target.is_file():
            raise KnowledgeError("OUTCOME_DRIFT", f"outcome path is missing: {relative}", exit_code=3)
        raw = target.read_bytes()
        if sha256_bytes(raw) != outcome.get(hash_key):
            raise KnowledgeError("OUTCOME_DRIFT", f"outcome hash drifted: {relative}", exit_code=3)
        persisted[path_key] = raw
    persisted_record = _strict_json_object(persisted["path"], "implementation outcome")
    if persisted_record != record:
        raise KnowledgeError("OUTCOME_DRIFT", "outcome result differs from persisted JSON", exit_code=3)
    validator, schema = _load_implementation_contracts()
    errors = list(validator.validate_instance(record, schema, "implementationOutcome"))
    errors.extend(
        validator.validate_execution_record_semantics(
            record,
            known_secret_values=tuple(known_secret_values),
        )
    )
    if record.get("markdown") != {
        "path": outcome["markdown_path"],
        "sha256": outcome["markdown_sha256"],
    }:
        errors.append("outcome Markdown record differs from persisted bytes")
    if expected_work_id is not None and work_id != expected_work_id:
        errors.append("outcome Work ID differs from the expected delivery")
    if expected_run_id is not None and record.get("implementation_run_id") != expected_run_id:
        errors.append("outcome implementation run differs from the expected delivery")
    for change in record.get("changes", []):
        if not isinstance(change, dict):
            continue
        try:
            relative = normalized_path(str(change.get("path", "")))
            target = repo / Path(*relative.split("/"))
            if (
                _redirected(target, repo)
                or not target.is_file()
                or sha256_bytes(target.read_bytes()) != change.get("sha256")
            ):
                errors.append(f"outcome changed-file hash drifted: {relative}")
        except KnowledgeError:
            errors.append("outcome changed-file path is invalid")
    if errors:
        raise KnowledgeError(
            "OUTCOME_INVALID",
            "; ".join(dict.fromkeys(errors)),
            exit_code=3,
        )
    _validated_preliminary_review(
        implementation_run_id=record["implementation_run_id"],
        review=record["review"],
        verification=record["verification"],
        known_secret_values=tuple(known_secret_values),
    )
    return record


def write_bug_implementation_outcome(
    repo_value: str,
    *,
    ready: dict[str, Any],
    verification: dict[str, Any],
    implementation_run_id: str,
    changes: list[dict[str, str]],
    review: dict[str, Any],
    created_at: str,
    known_secret_values: Iterable[str] = (),
    revision: int = 1,
) -> dict[str, Any]:
    """Validate a BUG result with the execution owner's contract before persistence."""

    if not isinstance(ready, dict) or not isinstance(verification, dict):
        raise KnowledgeError("BUG_VERIFICATION_INVALID", "BUG contracts must be objects", exit_code=2)
    validator, schema = _load_implementation_contracts()
    raw = (
        json.dumps(verification, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    errors = validator.validate_instance(verification, schema, "bugVerification")
    errors.extend(
        validator.validate_bug_verification_against_ready(
            verification,
            ready,
            expected_work_id=verification.get("work_id"),
            known_secret_values=tuple(known_secret_values),
            raw_json_bytes=raw,
        )
    )
    if errors:
        raise KnowledgeError(
            "BUG_VERIFICATION_INVALID",
            "; ".join(dict.fromkeys(errors)),
            exit_code=3,
        )

    result = str(verification["result"])
    bug_details = {
        "bug_id": verification["bug_id"],
        "original_reproduction": verification["original_reproduction"],
        "regression": verification["regression"],
        "proxy": verification["proxy"],
        "residual_risks": verification["residual_risks"],
        "follow_up": verification["follow_up"],
        "implementation_review_ref": verification["implementation_review_ref"],
    }
    command_results = [
        {
            "command_id": item["command_id"],
            "outcome": item["outcome"],
            "evidence_refs": [item["output_ref"]] if item.get("output_ref") else [],
        }
        for item in verification["full_verification"]
    ]
    return write_implementation_outcome(
        repo_value,
        work_id=verification["work_id"],
        implementation_run_id=implementation_run_id,
        work_kind="bug",
        result=result,
        summary=verification["summary"],
        changes=changes,
        verification=command_results,
        review=review,
        known_deviations=list(verification["residual_risks"]),
        knowledge_decision="no-change" if result == "failed" else "change",
        bug_verification_ref=(
            f"bug-verification:{verification['work_id']}:{verification['bug_id']}"
        ),
        bug_details=bug_details,
        created_at=created_at,
        known_secret_values=known_secret_values,
        revision=revision,
    )


def _current_pages(repo: Path) -> list[dict[str, Any]]:
    eligible = _eligible_paths(repo)
    root = repo / "docs" / "knowledge" / "meta" / "pages"
    pages: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*.json"), key=lambda item: item.as_posix().encode("utf-8")):
            relative = path.relative_to(repo).as_posix()
            if relative in eligible:
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict) or value.get("schema") != "knowledge-page/v1":
                    raise KnowledgeError("PAGE_CONTRACT_INVALID", f"invalid page: {relative}", exit_code=3)
                pages.append(value)
    return pages


def build_implementation_candidate_draft(
    repo_value: str,
    *,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    repo = Path(repo_value).resolve()
    record = validate_implementation_outcome_result(repo_value, outcome=outcome)
    markdown_path = normalized_path(str(outcome.get("markdown_path", "")))
    markdown_raw = (repo / Path(*markdown_path.split("/"))).read_bytes()
    work_id = record["work_id"]
    if record["knowledge_decision"] == "no-change":
        return {
            "schema": "knowledge-candidate-draft/v1",
            "stage": "implementation",
            "work_id": work_id,
            "decision": "no-change",
            "source_snapshot": [],
            "operations": [],
        }
    summary = record["summary"]
    lines = markdown_raw.decode("utf-8").splitlines()
    matches = [index for index, line in enumerate(lines, 1) if line == summary]
    if len(matches) != 1:
        raise KnowledgeError("OUTCOME_INVALID", "outcome summary locator is ambiguous", exit_code=2)
    source_ref = {
        "path": markdown_path,
        "sha256": sha256_bytes(markdown_raw),
        "locator": {"start_line": matches[0], "end_line": matches[0]},
        "excerpt_sha256": sha256_bytes(summary.encode("utf-8")),
    }
    suffix = f"{work_id}-implementation"
    content_path = f"docs/knowledge/topics/{suffix}.md"
    content = f"# Implementation Outcome\n\n## implementation-outcome\n\n{summary}\n"
    content_bytes = content.encode("utf-8")
    page = {
        "schema": "knowledge-page/v1",
        "page_id": f"page-{suffix}",
        "content_path": content_path,
        "content_sha256": sha256_bytes(content_bytes),
        "title": "Implementation Outcome",
        "aliases": [],
        "tags": ["implementation"],
        "lifecycle": "current",
        "claims": [
            {
                "claim_id": f"claim-{suffix}",
                "evidence_class": "observed",
                "lifecycle": "current",
                "content_anchor": "implementation-outcome",
                "source_refs": [source_ref],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }
    sidecar_path = f"docs/knowledge/meta/pages/page-{suffix}.json"
    pages = [candidate for candidate in _current_pages(repo) if candidate.get("page_id") != page["page_id"]]
    pages.append(page)

    def operation(path: str, postimage: str) -> dict[str, str]:
        return {
            "kind": "update" if (repo / Path(*path.split("/"))).is_file() else "create",
            "path": path,
            "postimage": postimage,
        }

    return {
        "schema": "knowledge-candidate-draft/v1",
        "stage": "implementation",
        "work_id": work_id,
        "decision": "change",
        "source_snapshot": [source_ref],
        "operations": [
            operation(content_path, content),
            operation(
                sidecar_path,
                json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            ),
            operation("docs/knowledge/index.md", render_index(pages).decode("utf-8")),
        ],
    }


def build_bug_candidate_draft(
    repo_value: str,
    *,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Map a validated BUG outcome to one incident claim without inflating certainty."""

    repo = Path(repo_value).resolve()
    record = validate_implementation_outcome_result(repo_value, outcome=outcome)
    markdown_path = normalized_path(str(outcome.get("markdown_path", "")))
    try:
        markdown_raw = (repo / Path(*markdown_path.split("/"))).read_bytes()
    except OSError as exc:
        raise KnowledgeError("OUTCOME_DRIFT", "BUG outcome bytes are unavailable", exit_code=3) from exc
    if (
        record.get("work_kind") != "bug"
        or not isinstance(record.get("bug"), dict)
    ):
        raise KnowledgeError("OUTCOME_INVALID", "BUG outcome record is invalid", exit_code=2)
    work_id = str(record["work_id"])
    if record.get("knowledge_decision") == "no-change":
        return {
            "schema": "knowledge-candidate-draft/v1",
            "stage": "bug",
            "work_id": work_id,
            "decision": "no-change",
            "source_snapshot": [],
            "operations": [],
        }
    result = str(record.get("result"))
    if result not in {"verified", "partial"}:
        raise KnowledgeError("OUTCOME_INVALID", "BUG knowledge requires verified or partial evidence", exit_code=2)
    summary = str(record["summary"])
    lines = markdown_raw.decode("utf-8").splitlines()
    matches = [index for index, line in enumerate(lines, 1) if line == summary]
    if len(matches) != 1:
        raise KnowledgeError("OUTCOME_INVALID", "BUG summary locator is ambiguous", exit_code=2)
    source_ref = {
        "path": markdown_path,
        "sha256": sha256_bytes(markdown_raw),
        "locator": {"start_line": matches[0], "end_line": matches[0]},
        "excerpt_sha256": sha256_bytes(summary.encode("utf-8")),
    }
    bug_id = str(record["bug"]["bug_id"])
    content_path = f"docs/knowledge/incidents/{bug_id}.md"
    content = markdown_raw.decode("utf-8")
    page = {
        "schema": "knowledge-page/v1",
        "page_id": f"page-{bug_id}",
        "content_path": content_path,
        "content_sha256": sha256_bytes(content.encode("utf-8")),
        "title": f"BUG Incident: {bug_id}",
        "aliases": [],
        "tags": ["bug", "incident", result],
        "lifecycle": "current",
        "claims": [
            {
                "claim_id": f"claim-{bug_id}-{result}",
                "evidence_class": result,
                "lifecycle": "current",
                "content_anchor": "original-symptom",
                "source_refs": [source_ref],
                "supersedes": [],
                "contradicts": [],
            }
        ],
        "backlinks": [],
    }
    sidecar_path = f"docs/knowledge/meta/pages/page-{bug_id}.json"
    pages = [candidate for candidate in _current_pages(repo) if candidate.get("page_id") != page["page_id"]]
    pages.append(page)

    def operation(path: str, postimage: str) -> dict[str, str]:
        return {
            "kind": "update" if (repo / Path(*path.split("/"))).is_file() else "create",
            "path": path,
            "postimage": postimage,
        }

    return {
        "schema": "knowledge-candidate-draft/v1",
        "stage": "bug",
        "work_id": work_id,
        "decision": "change",
        "source_snapshot": [source_ref],
        "operations": [
            operation(content_path, content),
            operation(
                sidecar_path,
                json.dumps(page, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            ),
            operation("docs/knowledge/index.md", render_index(pages).decode("utf-8")),
        ],
    }
