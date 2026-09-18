#!/usr/bin/env python3
"""Small dependency-free validator for the portable plugin and v2 state records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from megin import SCHEMA, PLUGIN_VERSION, compatible_plugin_version, approved_verification_commands, assignment_digest_payload, assignment_ticket_payload, allowed_path, candidate_payload, digest_bytes, digest_json, normalize_paths, read_json, state_root, validate_work_id, _candidate_summary, validate_candidate_bundles, validate_knowledge_record, verification_payload, validate_delivery_schema, load_diagnosis_assessment, load_routing_evidence, _report_commands_passed, _report_commands_cover, _review_evidence_item_valid
except ImportError:  # pragma: no cover - supports `python -m plugins.megin.scripts.validate`
    from .megin import SCHEMA, PLUGIN_VERSION, compatible_plugin_version, approved_verification_commands, assignment_digest_payload, assignment_ticket_payload, allowed_path, candidate_payload, digest_bytes, digest_json, normalize_paths, read_json, state_root, validate_work_id, _candidate_summary, validate_candidate_bundles, validate_knowledge_record, verification_payload, validate_delivery_schema, load_diagnosis_assessment, load_routing_evidence, _report_commands_passed, _report_commands_cover, _review_evidence_item_valid


def validate_plugin(root: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:  # pragma: no cover - exercised by command-line users
        return [f"manifest: {exc}"]
    if manifest.get("name") != "megin":
        errors.append("manifest name must be megin")
    if not manifest.get("version"):
        errors.append("manifest version is required")
    elif manifest.get("version") != PLUGIN_VERSION:
        errors.append(f"manifest version must match the engine version {PLUGIN_VERSION}")
    skills_root = root / "skills"
    for name in (
        "megin-orchestrator", "requirements-discovery", "technical-planning", "bug-diagnosis",
        "project-knowledge", "implementation-execution", "test-driven-development", "code-review",
        "verification-before-completion", "finishing-delivery",
    ):
        skill = skills_root / name / "SKILL.md"
        if not skill.exists():
            errors.append(f"missing skill: {skill.relative_to(root)}")
    for entrypoint in (root / "bin" / "megin", root / "bin" / "megin.cmd"):
        if not entrypoint.exists():
            errors.append(f"missing executable wrapper: {entrypoint.relative_to(root)}")
    schema = root / "schemas" / "delivery-run-v2.schema.json"
    try:
        schema_value = read_json(schema)
        if schema_value.get("$id") is None:
            errors.append("v2 schema must define $id")
    except Exception as exc:  # pragma: no cover
        errors.append(f"schema: {exc}")
    for schema_name in (
        "knowledge-candidate-v2.schema.json", "bug-diagnosis-v1.schema.json",
        "megin-writer-report-v1.schema.json", "megin-review-report-v1.schema.json",
        "megin-knowledge-review-v1.schema.json", "megin-migration-v1.schema.json",
        "megin-routing-v1.schema.json",
    ):
        schema_path = root / "schemas" / schema_name
        try:
            schema_value = read_json(schema_path)
            if schema_value.get("$id") is None:
                errors.append(f"{schema_name} must define $id")
        except Exception as exc:  # pragma: no cover
            errors.append(f"{schema_name}: {exc}")
    return errors


def validate_state(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = read_json(path)
    except Exception as exc:  # pragma: no cover
        return [str(exc)]
    if state.get("schema") != SCHEMA:
        errors.append("schema must be delivery-run/v2")
    errors.extend(f"schema: {item}" for item in validate_delivery_schema(state))
    if state.get("version") != 2:
        errors.append("version must be 2")
    if state.get("plugin") != "megin" or not compatible_plugin_version(state.get("plugin_version")):
        errors.append(f"state must bind a compatible megin plugin version for engine {PLUGIN_VERSION}")
    try:
        validate_work_id(str(state["work_id"]))
    except Exception as exc:
        errors.append(f"invalid work_id: {exc}")
    try:
        expected = digest_json(candidate_payload(state))
        if state.get("approval", {}).get("payload_sha256") != expected:
            errors.append("approval payload digest does not match state")
    except Exception as exc:
        errors.append(f"approval payload is incomplete: {exc}")
    try:
        approval = state["approval"]
        expected_stages = {}
        for stage in sorted(set(approval.get("approved_stages", []))):
            expected_stages[stage] = digest_json({
                "stage": stage,
                "candidate_revision": approval.get("candidate_revision"),
                "policy": approval.get("policy"),
                "approval_status": approval.get("status"),
                "task_class": state["task"].get("task_class"),
                "repair_class": state["task"].get("repair_class"),
                "diagnosis": state["task"].get("diagnosis"),
                "scope": approval.get("scope"),
                "candidate": _candidate_summary((state.get("candidates") or {}).get("design" if stage == "integrated" else stage)),
                "ref": (approval.get("refs") or {}).get(stage, []),
            })
        if approval.get("stage_digests") != expected_stages:
            errors.append("approval stage digests do not match state")
    except Exception as exc:
        errors.append(f"approval stage digests are incomplete: {exc}")
    try:
        scope = state["approval"]["scope"]
        normalize_paths(scope.get("allowed_paths", []))
        normalize_paths(scope.get("knowledge_scope", []))
        if any(not allowed_path(item, scope.get("allowed_paths", [])) for item in scope.get("knowledge_scope", [])):
            errors.append("knowledge scope is outside the approved write scope")
        scope_publication = scope.get("publication", {})
        publication = state.get("publication", {})
        approved_base_sha = scope_publication.get("base_sha")
        if approved_base_sha and publication.get("base_sha") not in (None, approved_base_sha):
            errors.append("publication base SHA does not match the approved scope")
        mode = publication.get("finish_mode") or scope_publication.get("finish_mode")
        if mode == "unstaged" and publication.get("commit_sha"):
            errors.append("unstaged publication cannot contain a commit SHA")
        if publication.get("state") == "delivered_unstaged" and mode != "unstaged":
            errors.append("delivered_unstaged state requires finish_mode=unstaged")
        workspace = state.get("workspace", {})
        if workspace.get("mode") == "current" and workspace.get("worktree"):
            if Path(workspace["worktree"]).expanduser().resolve() != Path(state["repo"]["path"]).expanduser().resolve():
                errors.append("current workspace path does not match repository path")
    except Exception as exc:
        errors.append(f"invalid approved path scope: {exc}")
    if state.get("task", {}).get("task_class") == "bug":
        if state.get("task", {}).get("diagnosis") not in ("confirmed", "likely"):
            errors.append("bug state requires confirmed or likely diagnosis")
        assessment = state.get("task", {}).get("diagnosis_assessment")
        try:
            payload, assessment_path = load_diagnosis_assessment(
                assessment["path"], Path(state["repo"]["path"]),
                request_sha256=state["task"].get("request_sha256"),
            )
            if digest_bytes(assessment_path.read_bytes()) != assessment.get("sha256"):
                errors.append("diagnosis assessment digest does not match state")
            if payload.get("disposition") != state["task"].get("diagnosis"):
                errors.append("diagnosis disposition does not match state")
        except Exception as exc:
            errors.append(f"diagnosis assessment is invalid: {exc}")
    routing_record = (state.get("task", {}).get("classification") or {}).get("routing_evidence")
    if routing_record:
        try:
            checked_routing = load_routing_evidence(
                routing_record.get("path", ""),
                state.get("task", {}).get("request", ""),
                Path(state["repo"]["path"]),
                verify_head=False,
            )
            if checked_routing.get("sha256") != routing_record.get("sha256"):
                errors.append("routing evidence digest does not match state")
            if routing_record.get("head_sha") and checked_routing.get("head_sha") != routing_record.get("head_sha"):
                errors.append("routing evidence source changed")
        except Exception as exc:
            errors.append(f"routing evidence is invalid: {exc}")
    try:
        validate_candidate_bundles(state)
    except Exception as exc:
        errors.append(str(exc))
    task_records = state.get("tasks", [])
    task_ids = [task.get("id") for task in task_records if isinstance(task, dict)]
    if len(task_ids) != len(set(task_ids)):
        errors.append("work package identifiers must be unique")
    task_graph = {
        task.get("id"): set(task.get("depends_on", [])) | set(task.get("blocked_by", []))
        for task in task_records
        if isinstance(task, dict) and task.get("id")
    }
    task_id_set = set(task_graph)
    for identifier, dependencies in task_graph.items():
        if identifier in dependencies:
            errors.append(f"work package dependency graph contains a self-dependency: {identifier}")
        for dependency in sorted(dependencies - task_id_set):
            errors.append(f"work package {identifier} depends on unknown work package: {dependency}")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("work package dependency graph contains a cycle")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in task_graph.get(identifier, set()):
            if dependency in task_graph:
                visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
    try:
        for identifier in task_graph:
            visit(identifier)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        validate_knowledge_record(state)
    except Exception as exc:
        errors.append(str(exc))
    try:
        verification = state["verification"]
        if verification.get("record_sha256") != digest_json(verification_payload(verification)):
            errors.append("verification evidence digest does not match state")
        evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
        approved_commands = approved_verification_commands(state)
        legacy_commands = list(state["approval"]["scope"].get("test_commands", []))
        records = verification.get("commands", [])
        if not isinstance(records, list):
            errors.append("verification command evidence must be an array")
            records = []
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict) or not record.get("evidence_path"):
                errors.append(f"verification command evidence is missing: {index}")
                continue
            if index <= len(approved_commands) and record.get("command") != approved_commands[index - 1]:
                errors.append(f"verification command is not approved: {index}")
            evidence_path = Path(record["evidence_path"]).expanduser().resolve()
            try:
                evidence_path.relative_to(evidence_root)
            except ValueError:
                errors.append(f"verification evidence is outside state root: {index}")
                continue
            if not evidence_path.exists() or not evidence_path.is_file():
                errors.append(f"verification raw output is missing: {index}")
                continue
            raw = evidence_path.read_bytes()
            if digest_bytes(raw) != record.get("output_sha256") or len(raw) != record.get("output_bytes"):
                errors.append(f"verification raw output digest does not match: {index}")
        recorded_commands = [item.get("command") for item in records]
        if verification.get("status") == "passed" and recorded_commands not in (approved_commands, legacy_commands):
            errors.append("verification does not cover every approved command")
    except Exception as exc:
        errors.append(f"verification evidence is incomplete: {exc}")
    try:
        approval_digest = state["approval"].get("payload_sha256")
        task_ids = {task.get("id") for task in state.get("tasks", [])}
        for assignment in state.get("assignments", []):
            if assignment.get("task_id") not in task_ids:
                errors.append(f"assignment references unknown work package: {assignment.get('assignment_id')}")
            else:
                task = next((item for item in state.get("tasks", []) if item.get("id") == assignment.get("task_id")), None)
                if not task or any(
                    assignment.get(key) != task.get(key)
                    for key in (
                        "acceptance", "allowed_paths", "forbidden_paths", "interfaces", "focused_commands",
                        "related_commands", "full_commands", "blocked_by", "depends_on", "evidence_path",
                    )
                ):
                    errors.append(f"assignment does not match work package: {assignment.get('assignment_id')}")
            expected_ticket = digest_json(assignment_ticket_payload(state, assignment))
            if assignment.get("ticket_sha256") != expected_ticket:
                errors.append(f"assignment ticket does not match: {assignment.get('assignment_id')}")
            expected_assignment = digest_json(assignment_digest_payload(assignment))
            if assignment.get("assignment_sha256") != expected_assignment:
                errors.append(f"assignment digest does not match: {assignment.get('assignment_id')}")
            if assignment.get("status") == "completed" and not assignment.get("writer_result"):
                errors.append(f"completed assignment has no writer result: {assignment.get('assignment_id')}")
            if assignment.get("writer_result") is not None:
                if assignment.get("writer_result_sha256") != digest_json(assignment["writer_result"]):
                    errors.append(f"writer result digest does not match: {assignment.get('assignment_id')}")
                result = assignment["writer_result"]
                if result.get("status") not in ("completed", "needs_revision", "blocked", "awaiting_upstream"):
                    errors.append(f"writer result status is unsupported: {assignment.get('assignment_id')}")
                elif assignment.get("status") == "completed" and result.get("status") != "completed":
                    errors.append(f"completed assignment has a non-completed writer result: {assignment.get('assignment_id')}")
                elif assignment.get("status") == "needs_revision" and result.get("status") != "needs_revision":
                    errors.append(f"revision assignment has a mismatched writer result: {assignment.get('assignment_id')}")
                elif assignment.get("status") == "blocked" and result.get("status") not in ("blocked", "awaiting_upstream"):
                    errors.append(f"blocked assignment has a mismatched writer result: {assignment.get('assignment_id')}")
                if (
                    result.get("work_id") != state.get("work_id")
                    or result.get("assignment_id") != assignment.get("assignment_id")
                    or result.get("writer_id") != assignment.get("writer_id")
                    or result.get("reported_by") != assignment.get("writer_id")
                    or result.get("session_id") != assignment.get("session_id")
                    or result.get("ticket_sha256") != assignment.get("ticket_sha256")
                    or result.get("task_id") != assignment.get("task_id")
                    or result.get("snapshot") != assignment.get("completion_snapshot")
                ):
                    errors.append(f"writer result identity is not bound: {assignment.get('assignment_id')}")
                evidence_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "evidence"
                for field in ("evidence_path", "report_path"):
                    value = result.get(field)
                    if not value:
                        errors.append(f"writer result is missing {field}: {assignment.get('assignment_id')}")
                        continue
                    report_path = Path(value).expanduser().resolve()
                    try:
                        report_path.relative_to(evidence_root)
                    except ValueError:
                        errors.append(f"writer {field} is outside state root: {assignment.get('assignment_id')}")
                        continue
                    if not report_path.exists():
                        errors.append(f"writer {field} is missing: {assignment.get('assignment_id')}")
                    elif field == "report_path" and digest_bytes(report_path.read_bytes()) != result.get("report_sha256"):
                        errors.append(f"writer report digest does not match: {assignment.get('assignment_id')}")
        review = state.get("review", {})
        if review.get("verdict"):
            assignment = next((item for item in state.get("assignments", []) if item.get("assignment_id") == review.get("assignment_id")), None)
            if not assignment:
                errors.append("review references an unknown assignment")
            else:
                expected_review = digest_json({
                    "work_id": state["work_id"], "assignment_id": assignment.get("assignment_id"),
                    "assignment_sha256": assignment.get("assignment_sha256"), "snapshot": review.get("snapshot"),
                    "product_snapshot": review.get("product_snapshot"),
                    "round": review.get("round"), "reviewer_id": review.get("reviewer_id"),
                    "reviewer_session": review.get("reviewer_session"), "verdict": review.get("verdict"),
                    "findings": review.get("findings", []),
                    "test_evidence": review.get("test_evidence", []),
                    "no_progress_count": review.get("no_progress_count", 0),
                    "review_report_sha256": review.get("report_sha256"),
                    "reviewer_capability_sha256": review.get("reviewer_capability_sha256"),
                })
                if review.get("review_ticket_sha256") != expected_review:
                    errors.append("review ticket does not match state")
                report_path = Path(str(review.get("report_path", ""))).expanduser().resolve()
                review_root = state_root(state["repo"]["repo_id"], Path(state["repo"]["path"])) / state["repo"]["repo_id"] / state["work_id"] / "reviews"
                try:
                    report_path.relative_to(review_root)
                except ValueError:
                    errors.append("review report is outside state root")
                else:
                    if not report_path.exists() or digest_bytes(report_path.read_bytes()) != review.get("report_sha256"):
                        errors.append("review report is missing or drifted")
                    else:
                        report = read_json(report_path)
                        if (
                            report.get("schema") != "megin-review-report/v1"
                            or report.get("work_id") != state.get("work_id")
                            or report.get("assignment_id") != assignment.get("assignment_id")
                            or report.get("assignment_sha256") != assignment.get("assignment_sha256")
                            or report.get("reviewer_id") != review.get("reviewer_id")
                            or report.get("reviewer_session") != review.get("reviewer_session")
                            or report.get("verdict") != review.get("verdict")
                            or report.get("snapshot") != review.get("snapshot")
                            or report.get("product_snapshot") != review.get("product_snapshot")
                            or report.get("findings", []) != review.get("findings", [])
                            or report.get("test_evidence", []) != review.get("test_evidence", [])
                        ):
                            errors.append("review report is not bound to state")
                        review_commands = list(dict.fromkeys(
                            list(assignment.get("focused_commands", []))
                            + list(assignment.get("related_commands", []))
                            + list(assignment.get("full_commands", []))
                        ))
                        if (
                            not _report_commands_passed(report.get("test_evidence"), review_commands)
                            or not _report_commands_cover(
                                report.get("test_evidence"),
                                [assignment.get("focused_commands", []), assignment.get("related_commands", []), assignment.get("full_commands", [])],
                            )
                        ):
                            errors.append("review test evidence does not cover approved obligations")
                        persisted_evidence_root = review_root / "evidence"
                        seen_review_evidence = set()
                        for item in report.get("test_evidence", []):
                            evidence_path = Path(str(item.get("evidence_path", ""))).expanduser().resolve()
                            if evidence_path in seen_review_evidence:
                                errors.append("review raw test evidence is reused")
                            seen_review_evidence.add(evidence_path)
                            if not _review_evidence_item_valid(
                                item,
                                commands=review_commands,
                                expected_snapshot=review.get("snapshot"),
                                evidence_root=persisted_evidence_root,
                            ):
                                errors.append("review raw test evidence is missing, stale, or drifted")
    except Exception as exc:
        errors.append(f"assignment/review integrity is incomplete: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="validate portable megin plugin or v2 state")
    parser.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state", type=Path)
    args = parser.parse_args(argv)
    errors = validate_plugin(args.plugin_root.resolve())
    if args.state:
        errors.extend(f"state: {item}" for item in validate_state(args.state.resolve()))
    result = {"schema": "megin-validation/v1", "ok": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
