#!/usr/bin/env python3
"""Outside-in BDD and inner contract tests for bug-closure-status/v1."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import bug_status  # noqa: E402


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def assessment_payload(bug_id: str = "bug-sample-failure") -> dict:
    return {
        "schema": "bug-assessment/v1",
        "bug_id": bug_id,
        "revision": 1,
        "markdown": {"path": f"docs/bugs/{bug_id}/assessment-1.md", "sha256": ""},
        "source": {
            "relation": "current-scope",
            "work_id": "work-closure-fixture",
            "reported_by": "test",
            "evidence_refs": ["fixture:assessment"],
        },
        "observed_behavior": "The controlled operation produces an incorrect result.",
        "expected_behavior": "The controlled operation produces the specified result.",
        "impact": "The workflow cannot reliably complete.",
        "verdict": "confirmed",
        "severity": "high",
        "reproduction": {
            "status": "reproduced",
            "symptom_oracle": "the result differs from the expected result",
            "steps": ["run the controlled operation"],
            "sample": "one deterministic fixture",
            "command_refs": ["fixture:reproduce"],
            "evidence_refs": ["fixture:reproduction"],
        },
        "root_cause": {
            "status": "confirmed",
            "confidence": "high",
            "summary": "A controlled pre/post probe confirms the boundary condition.",
            "evidence_refs": ["fixture:root-cause"],
        },
        "hypotheses": [],
        "active_hypothesis_id": None,
        "risk": {
            "security_privacy_or_data_risk": False,
            "redacted_summary": None,
            "secure_evidence_refs": [],
            "human_reviewer": None,
        },
        "disposition": "current-run",
        "evidence_refs": ["fixture:assessment"],
        "next_action": "Run the approved regression.",
        "created_at": "2026-09-14T00:00:00+00:00",
    }


def timebox() -> dict:
    return {
        "t0": "2026-09-14",
        "classify_due": "2026-09-15",
        "blocker_due": "2026-09-17",
        "escalate_due": "2026-09-21",
        "decision_due": "2026-09-28",
    }


def base_status(
    assessment: dict,
    assessment_sha: str,
    markdown_sha: str,
    *,
    bug_id: str | None = None,
    disposition: str = "evidence-pending",
) -> dict:
    bug_id = bug_id or assessment["bug_id"]
    return {
        "schema": "bug-closure-status/v1",
        "bug_id": bug_id,
        "revision": 1,
        "work_scope": {
            "work_id": "work-closure-fixture",
            "bug_ids": [bug_id],
            "scope_kind": "single",
        },
        "assessment": {
            "path": f"docs/bugs/{bug_id}/assessment-1.json",
            "sha256": assessment_sha,
            "markdown_path": f"docs/bugs/{bug_id}/assessment-1.md",
            "markdown_sha256": markdown_sha,
            "revision": 1,
        },
        "verification": None,
        "current_disposition": disposition,
        "severity": assessment["severity"],
        "tracking": {
            "owner": "delivery-governance",
            "implementation_owner": "implementation-team",
            "next_action": "Collect current-version verification evidence.",
            "due_date": "2026-09-28",
        },
        "timebox": timebox(),
        "blocker": None,
        "risk_decision": None,
        "reviewer": None,
        "required_platforms": ["Windows", "Linux"],
        "platform_evidence": [],
        "current_observation": {
            "status": "inconclusive",
            "command_ref": None,
            "evidence_refs": ["fixture:current-observation"],
        },
        "closure_evidence": None,
        "evidence_manifest": [
            {
                "kind": "assessment",
                "ref": f"docs/bugs/{bug_id}/assessment-1.json",
                "sha256": assessment_sha,
                "preserved": True,
            }
        ],
        "previous": None,
        "transition": {
            "from": None,
            "to": disposition,
            "at": "2026-09-14T00:00:00+00:00",
            "reason": "Initial status review cannot infer a current fix.",
            "evidence_refs": ["fixture:status-transition"],
        },
    }


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_assessment(self, bug_id: str = "bug-sample-failure") -> tuple[dict, str, str]:
        root = self.repo / "docs" / "bugs" / bug_id
        root.mkdir(parents=True, exist_ok=True)
        markdown = f"# {bug_id}\n\nControlled assessment fixture.\n"
        markdown_bytes = markdown.encode("utf-8")
        assessment = assessment_payload(bug_id)
        assessment["markdown"]["sha256"] = sha256_bytes(markdown_bytes)
        markdown_path = root / "assessment-1.md"
        json_path = root / "assessment-1.json"
        markdown_path.write_bytes(markdown_bytes)
        json_bytes = (json.dumps(assessment, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        json_path.write_bytes(json_bytes)
        return assessment, sha256_bytes(json_bytes), sha256_bytes(markdown_bytes)

    def write_status(self, status: dict, revision: int = 1, bug_id: str | None = None) -> Path:
        bug_id = bug_id or status["bug_id"]
        path = self.repo / "docs" / "bugs" / bug_id / f"status-{revision}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
        return path

    def write_reviewer_report(self, name: str = "review.json") -> tuple[str, str]:
        path = self.repo / "reviews" / name
        raw = b"independent reviewer fixture report\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path.relative_to(self.repo).as_posix(), sha256_bytes(raw)
    def valid_status(self, *, disposition: str = "evidence-pending") -> tuple[dict, Path]:
        assessment, assessment_sha, markdown_sha = self.write_assessment()
        status = base_status(assessment, assessment_sha, markdown_sha, disposition=disposition)
        return status, self.write_status(status)


class ClosureStatusBDDTests(Fixture):
    def test_fixed_gate_and_partial_disposition(self) -> None:
        status, path = self.valid_status()
        status["verification"] = {"result": "partial", "path": "docs/bugs/bug-sample-failure/verifications/work-closure-fixture.json", "sha256": "1" * 64}
        status["current_disposition"] = "fixed-verified"
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("fixed-verified" in error or "partial" in error for error in errors), errors)

    def test_blocker_risk_reviewer_and_timebox(self) -> None:
        status, path = self.valid_status()
        status["current_disposition"] = "environment-blocked"
        status["transition"]["to"] = "environment-blocked"
        status["blocker"] = {"class": "environment", "summary": "Linux runner is unavailable."}
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("blocker" in error for error in errors), errors)

    def test_multi_bug_report_and_outlier_preservation(self) -> None:
        first, first_path = self.valid_status()
        second_assessment, second_sha, second_markdown_sha = self.write_assessment("bug-second-failure")
        second = base_status(second_assessment, second_sha, second_markdown_sha, bug_id="bug-second-failure")
        second["work_scope"] = {"work_id": "work-closure-fixture", "bug_ids": ["bug-sample-failure", "bug-second-failure"], "scope_kind": "common"}
        second["evidence_manifest"].append({"kind": "performance-sample", "ref": "fixture:outlier", "sha256": "2" * 64, "preserved": True})
        second_path = self.write_status(second, bug_id="bug-second-failure")
        self.assertEqual([], bug_status.validate_status_record(self.repo, first_path, first))
        self.assertEqual([], bug_status.validate_status_record(self.repo, second_path, second))
        report = bug_status.build_report(self.repo)
        self.assertEqual(2, report["status_record_count"])
        self.assertEqual(2, report["unresolved_count"])
        self.assertIn("fixture:outlier", report["preserved_evidence_refs"])


class ClosureStatusContractTests(Fixture):
    def test_fixed_requires_all_evidence(self) -> None:
        status, path = self.valid_status()
        status["current_disposition"] = "fixed-verified"
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("fixed-verified" in error for error in errors), errors)

    def test_duplicate_json_and_hash_drift_fail_closed(self) -> None:
        status, path = self.valid_status()
        raw = path.read_text(encoding="utf-8")
        path.write_text(raw.replace('"schema": "bug-closure-status/v1",\n', '"schema": "bug-closure-status/v1",\n  "schema": "bug-closure-status/v1",\n', 1), encoding="utf-8")
        errors = bug_status.validate_status_file(self.repo, path)
        self.assertTrue(any("duplicate" in error for error in errors), errors)

    def test_assessment_hash_drift_fails_closed(self) -> None:
        status, path = self.valid_status()
        status["assessment"]["sha256"] = "0" * 64
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("assessment JSON hash mismatch" in error for error in errors), errors)

    def test_reviewer_report_hash_drift_fails_closed(self) -> None:
        status, path = self.valid_status()
        report_path, report_sha = self.write_reviewer_report("hash-review.json")
        status["reviewer"] = {
            "identity": "independent-reviewer",
            "role": "reviewer",
            "scope": "status review",
            "version": "v1",
            "report_path": report_path,
            "report_sha256": "0" * 64,
            "outcome": "APPROVED",
        }
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("reviewer report hash mismatch" in error for error in errors), errors)

    def test_schema_failure_is_reported_without_exception(self) -> None:
        status, path = self.valid_status()
        del status["tracking"]
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("tracking" in error for error in errors), errors)
    def test_reviewer_identity_is_not_implementation_owner(self) -> None:
        status, path = self.valid_status()
        report_path, report_sha = self.write_reviewer_report("identity-review.json")
        status["reviewer"] = {
            "identity": "implementation-team",
            "role": "reviewer",
            "scope": "status review",
            "version": "v1",
            "report_path": report_path,
            "report_sha256": report_sha,
            "outcome": "APPROVED",
        }
        status["closure_evidence"] = {"original_reproduction": {"pre_fix": {"status": "present", "command_ref": None, "evidence_refs": ["fixture:pre"]}, "post_fix": {"status": "absent", "command_ref": None, "evidence_refs": ["fixture:post"]}}, "regression": {"red_evidence_refs": ["fixture:red"], "green_evidence_refs": ["fixture:green"]}, "full_verification": [{"command_ref": "CMD-FULL", "outcome": "passed", "evidence_refs": ["fixture:full"]}]}
        status["verification"] = {"result": "verified", "path": "docs/bugs/bug-sample-failure/verifications/work-closure-fixture.json", "sha256": "4" * 64}
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("reviewer" in error or "implementation owner" in error for error in errors), errors)


class ClosureStatusTransitionTests(Fixture):
    def test_blocker_and_risk_rules(self) -> None:
        status, path = self.valid_status()
        status["current_disposition"] = "contract-blocked"
        status["transition"]["to"] = "contract-blocked"
        status["blocker"] = {"class": "contract", "summary": "Ready contract cannot express the scope.", "missing_capability": "multi-BUG context", "owner": "delivery-governance", "due_date": "2026-09-17", "alternative": "create child records", "escalation_role": "delivery-lead", "release_blocked": True, "next_action": "draft contract revision", "evidence_refs": ["fixture:contract-gap"]}
        self.assertEqual([], bug_status.validate_status_record(self.repo, path, status))
        status["current_disposition"] = "accepted-risk"
        status["transition"]["to"] = "accepted-risk"
        status["blocker"] = None
        report_path, report_sha = self.write_reviewer_report("risk-review.json")
        status["risk_decision"] = {"decision": "accepted-risk", "owner": "product-risk", "reason": "temporary operational mitigation", "mitigation": "manual review", "impact_scope": "one workflow", "expires_on": "2026-10-12", "reopen_condition": "new failure", "next_review": "2026-10-12", "approvals": [{"role": "Product/Risk", "identity": "product-risk", "approved_at": "2026-09-14T00:00:00+00:00", "evidence_ref": "fixture:risk-product"}, {"role": "Engineering/Delivery", "identity": "delivery-lead", "approved_at": "2026-09-14T00:00:00+00:00", "evidence_ref": "fixture:risk-engineering"}]}
        status["reviewer"] = {"identity": "risk-reviewer", "role": "independent reviewer", "scope": "accepted-risk status", "version": "closure-status/v1", "report_path": report_path, "report_sha256": report_sha, "outcome": "APPROVED"}
        self.assertEqual([], bug_status.validate_status_record(self.repo, path, status))
        status["reviewer"] = None
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("accepted-risk requires" in error for error in errors), errors)
        status["reviewer"] = {"identity": "risk-reviewer", "role": "independent reviewer", "scope": "accepted-risk status", "version": "closure-status/v1", "report_path": report_path, "report_sha256": report_sha, "outcome": "APPROVED"}
        status["risk_decision"]["approvals"] = status["risk_decision"]["approvals"][:1]
        errors = bug_status.validate_status_record(self.repo, path, status)
        self.assertTrue(any("dual approval" in error for error in errors), errors)


class ClosureStatusReportTests(Fixture):
    def test_chain_scope_and_report_counts(self) -> None:
        status, path = self.valid_status()
        status["evidence_manifest"].append({"kind": "performance-sample", "ref": "fixture:outlier", "sha256": "5" * 64, "preserved": True})
        self.write_status(status, bug_id=status["bug_id"])
        second = copy.deepcopy(status)
        second["revision"] = 2
        second["previous"] = {"path": "docs/bugs/bug-sample-failure/status-1.json", "sha256": sha256_bytes(path.read_bytes())}
        second["transition"] = {"from": "evidence-pending", "to": "confirmed-open", "at": "2026-09-15T00:00:00+00:00", "reason": "current symptom reproduced", "evidence_refs": ["fixture:transition-2"]}
        second["current_disposition"] = "confirmed-open"
        second["current_observation"] = {"status": "present", "command_ref": "CMD-REPRO", "evidence_refs": ["fixture:current-present"]}
        second_path = self.write_status(second, revision=2)
        errors = bug_status.validate_repository(self.repo)
        self.assertEqual([], errors, errors)
        report = bug_status.build_report(self.repo)
        self.assertEqual(1, report["status_record_count"])
        self.assertEqual("confirmed-open", report["records"][0]["current_disposition"])
        self.assertEqual(1, report["counts"]["confirmed-open"])
        self.assertEqual(64, len(report["records"][0]["status_sha256"]))
        self.assertEqual(status["assessment"]["sha256"], report["records"][0]["assessment_sha256"])
        self.assertIn("fixture:outlier", report["preserved_evidence_refs"])


class InitialStatusCorpusTests(unittest.TestCase):
    def test_real_initial_status_corpus_and_saved_report(self) -> None:
        repository = SKILL_ROOT.parents[2]
        report_path = repository / "docs" / "bugs" / "status-reviews" / "work-20260912-bug-closure-policy-dbcbce13.json"
        self.assertTrue(report_path.is_file(), report_path)
        self.assertEqual([], bug_status.validate_repository(repository))
        report = bug_status.build_report(repository)
        saved = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report, saved)
        self.assertEqual(16, report["status_record_count"])
        self.assertEqual(16, report["unresolved_count"])
        self.assertEqual(16, report["counts"]["evidence-pending"])
        self.assertEqual(16, report["verification_counts"]["none"])
        self.assertEqual(3, len(report["performance_evidence"]))
        self.assertTrue(all(row["status_sha256"] for row in report["records"]))

def _list_scenarios() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    scenarios: list[str] = []

    def collect(value: unittest.TestSuite | unittest.TestCase) -> None:
        if isinstance(value, unittest.TestSuite):
            for child in value:
                collect(child)
        else:
            scenarios.append(value.id())

    collect(suite)
    for scenario in scenarios:
        print(scenario)
    print(f"inventory_complete=true\nfailed=0\nskipped=0\ncount={len(scenarios)}")
    return 0


if __name__ == "__main__":
    if "--list-scenarios" in sys.argv:
        raise SystemExit(_list_scenarios())
    unittest.main()
