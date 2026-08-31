#!/usr/bin/env python3
"""Mutation and contract tests for bug-diagnosis."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("bug_contract_validator", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import infrastructure
    raise RuntimeError(f"cannot import {VALIDATOR_PATH}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def assessment_example(markdown_sha: str = "0" * 64) -> dict:
    hypotheses = [
        {
            "hypothesis_id": f"H-{index:03d}",
            "rank": index,
            "statement": f"controlled cause {index}",
            "variable": f"variable-{index}",
            "prediction": f"prediction-{index}",
            "falsifier": f"falsifier-{index}",
            "outcome": "testing" if index == 1 else "untested",
            "evidence_refs": [],
        }
        for index in range(1, 4)
    ]
    return {
        "schema": "bug-assessment/v1",
        "bug_id": "bug-sample-failure",
        "revision": 1,
        "markdown": {
            "path": "docs/bugs/bug-sample-failure/assessment-1.md",
            "sha256": markdown_sha,
        },
        "source": {
            "relation": "intake",
            "work_id": None,
            "reported_by": "user",
            "evidence_refs": ["conversation:bug-report"],
        },
        "observed_behavior": "The public command returns an incorrect result.",
        "expected_behavior": "The public command returns the specified result.",
        "impact": "The primary workflow cannot complete.",
        "verdict": "likely",
        "severity": "medium",
        "reproduction": {
            "status": "not-reproduced",
            "symptom_oracle": "expected and actual outputs differ",
            "steps": ["run the public command with the reported fixture"],
            "sample": "one controlled attempt",
            "command_refs": ["host-temp:commands/repro-1"],
            "evidence_refs": ["host-temp:outputs/repro-1"],
        },
        "root_cause": {
            "status": "hypothesized",
            "confidence": "low",
            "summary": "Evidence is consistent with one boundary error but does not prove causality.",
            "evidence_refs": ["host-temp:traces/boundary-1"],
        },
        "hypotheses": hypotheses,
        "active_hypothesis_id": "H-001",
        "risk": {
            "security_privacy_or_data_risk": False,
            "redacted_summary": None,
            "secure_evidence_refs": [],
            "human_reviewer": None,
        },
        "disposition": "delivery",
        "evidence_refs": ["host-temp:assessment/index"],
        "next_action": "Test H-001 without changing any other variable.",
        "created_at": "2026-08-30T00:00:00+08:00",
    }


class BugDiagnosisContractTests(unittest.TestCase):
    def test_public_assessment_contract_exists(self) -> None:
        required = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "references" / "assessment.schema.json",
            SKILL_ROOT / "references" / "assessment-contract.md",
            SKILL_ROOT / "references" / "assessment-template.md",
        ]
        missing = [path.relative_to(SKILL_ROOT).as_posix() for path in required if not path.is_file()]
        self.assertEqual([], missing, f"missing public BUG assessment contract: {missing}")

    def test_owner_bundle_and_forward_inventory_pass(self) -> None:
        self.assertEqual([], validator.validate_owner_bundle())
        self.assertEqual(
            [f"EVAL-BUG-{index:03d}" for index in range(1, 9)],
            [item[0] for item in validator.list_scenarios()],
        )

    def test_valid_low_confidence_assessment_passes(self) -> None:
        self.assertEqual([], validator.validate_assessment(assessment_example()))

    def test_unknown_field_and_missing_hypotheses_fail_closed(self) -> None:
        extra = assessment_example()
        extra["guessed_fix"] = "patch it"
        self.assertTrue(any("unexpected property guessed_fix" in item for item in validator.validate_assessment(extra)))

        too_few = assessment_example()
        too_few["hypotheses"] = too_few["hypotheses"][:2]
        too_few["active_hypothesis_id"] = "H-001"
        self.assertTrue(any("too few items" in item for item in validator.validate_assessment(too_few)))

    def test_confirmed_root_cause_may_close_hypothesis_frontier(self) -> None:
        value = assessment_example()
        value["root_cause"] = {
            "status": "confirmed",
            "confidence": "high",
            "summary": "A controlled pre/post probe reproduces and removes the invariant violation.",
            "evidence_refs": ["host-temp:probes/causal-pre-post"],
        }
        value["hypotheses"] = []
        value["active_hypothesis_id"] = None
        value["verdict"] = "confirmed"
        self.assertEqual([], validator.validate_assessment(value))

    def test_only_one_hypothesis_variable_may_be_active(self) -> None:
        value = assessment_example()
        value["hypotheses"][1]["outcome"] = "testing"
        errors = validator.validate_assessment(value)
        self.assertTrue(any("only one hypothesis" in item for item in errors), errors)

        mismatch = assessment_example()
        mismatch["active_hypothesis_id"] = "H-002"
        errors = validator.validate_assessment(mismatch)
        self.assertTrue(any("active_hypothesis_id" in item for item in errors), errors)

    def test_verdict_and_inflight_relation_control_disposition(self) -> None:
        value = assessment_example()
        value["verdict"] = "not-a-bug"
        self.assertTrue(any("verdict and disposition" in item for item in validator.validate_assessment(value)))
        value["disposition"] = "standard-feature"
        self.assertEqual([], validator.validate_assessment(value))

        unrelated = assessment_example()
        unrelated["source"].update({"relation": "unrelated", "work_id": "work-current-feature"})
        unrelated["disposition"] = "delivery"
        self.assertTrue(any("relation and disposition" in item for item in validator.validate_assessment(unrelated)))
        unrelated["disposition"] = "deferred-inbox"
        self.assertEqual([], validator.validate_assessment(unrelated))

    def test_sensitive_assessment_requires_redaction_secure_ref_and_named_reviewer(self) -> None:
        value = assessment_example()
        value["risk"]["security_privacy_or_data_risk"] = True
        errors = validator.validate_assessment(value)
        self.assertTrue(any("risk.redacted_summary" in item or "sensitive assessment" in item for item in errors), errors)
        value["risk"].update(
            {
                "redacted_summary": "Credential-like evidence is stored outside the repository.",
                "secure_evidence_refs": ["vault:case-123"],
                "human_reviewer": "Security owner Alice",
            }
        )
        self.assertEqual([], validator.validate_assessment(value))

    def test_known_secret_value_is_rejected(self) -> None:
        value = assessment_example()
        value["impact"] = "Leaked FAKE-TOKEN-7391 in output."
        errors = validator.validate_assessment(value, known_secret_values=["FAKE-TOKEN-7391"])
        self.assertTrue(any("secret value" in item for item in errors), errors)

        hidden_secret = "ultraviolet-harbor-9472"
        clean = assessment_example()
        canonical = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        duplicate = canonical.replace(
            '"impact":',
            f'"impact":"{hidden_secret}","impact":',
            1,
        ).encode("utf-8")
        errors = validator.validate_assessment(
            clean,
            sidecar_bytes=duplicate,
            known_secret_values=[hidden_secret],
        )
        self.assertTrue(any("duplicate JSON object key" in item for item in errors), errors)
        self.assertTrue(any("secret value" in item for item in errors), errors)
        self.assertNotIn(hidden_secret, "\n".join(errors))

    def test_credential_shaped_sentinel_is_rejected_without_known_value_input(self) -> None:
        value = assessment_example()
        value["impact"] = "Diagnostic output included FAKE_SECRET_SENTINEL_7391."
        errors = validator.validate_assessment(value)
        self.assertTrue(any("credential-shaped material" in item for item in errors), errors)

    def test_markdown_path_hash_and_sidecar_binding_are_exact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-assessment-test-") as temporary:
            root = Path(temporary)
            markdown = root / "docs" / "bugs" / "bug-sample-failure" / "assessment-1.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("# Redacted assessment\n", encoding="utf-8", newline="\n")
            value = assessment_example(hashlib.sha256(markdown.read_bytes()).hexdigest())
            sidecar = markdown.with_suffix(".json")
            self.assertEqual(
                [],
                validator.validate_assessment(value, repository_root=root, sidecar_path=sidecar),
            )

            wrong_hash = copy.deepcopy(value)
            wrong_hash["markdown"]["sha256"] = "f" * 64
            errors = validator.validate_assessment(wrong_hash, repository_root=root, sidecar_path=sidecar)
            self.assertTrue(any("hash mismatch" in item for item in errors), errors)

            wrong_sidecar = root / "docs" / "bugs" / "bug-sample-failure" / "assessment-2.json"
            errors = validator.validate_assessment(value, repository_root=root, sidecar_path=wrong_sidecar)
            self.assertTrue(any("sidecar path" in item for item in errors), errors)

    def test_in_root_redirect_is_rejected_before_path_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-redirect-test-") as temporary:
            root = Path(temporary).resolve()
            lexical = root / "docs" / "bugs" / "bug-sample-failure" / "assessment-1.md"
            resolved = root / "redirect-target" / "bugs" / "bug-sample-failure" / "assessment-1.md"
            original_resolve = Path.resolve

            def redirected_resolve(path: Path, strict: bool = False) -> Path:
                if path == lexical:
                    return resolved
                return original_resolve(path, strict=strict)

            inspected: list[Path] = []

            def lexical_reparse(path: Path) -> bool:
                inspected.append(path)
                return path == root / "docs"

            with (
                mock.patch.object(Path, "resolve", redirected_resolve),
                mock.patch.object(validator, "_is_reparse_path", side_effect=lexical_reparse),
            ):
                self.assertTrue(validator._has_reparse_component(lexical, root))
            self.assertIn(root / "docs", inspected)

    def test_public_assessment_rejects_directory_redirect_before_dereference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-public-redirect-test-") as temporary:
            root = Path(temporary).resolve()
            target = root / "redirect-target"
            target.mkdir()
            redirect = root / "docs"
            if os.name == "nt":
                created = subprocess.run(
                    ["cmd", "/d", "/c", "mklink", "/J", str(redirect), str(target)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(0, created.returncode, created.stderr.decode("utf-8", "replace"))
            else:
                redirect.symlink_to(target, target_is_directory=True)
            try:
                target_markdown = target / "bugs" / "bug-sample-failure" / "assessment-1.md"
                target_markdown.parent.mkdir(parents=True)
                target_markdown.write_text("# Redirected assessment\n", encoding="utf-8", newline="\n")
                markdown = redirect / "bugs" / "bug-sample-failure" / "assessment-1.md"
                sidecar = markdown.with_suffix(".json")
                value = assessment_example(hashlib.sha256(target_markdown.read_bytes()).hexdigest())
                original_is_file = Path.is_file
                original_read_bytes = Path.read_bytes
                original_resolve = Path.resolve
                guarded = {root, markdown, sidecar}

                def reject_is_file(path: Path) -> bool:
                    if path in {markdown, sidecar}:
                        raise AssertionError("redirected assessment was dereferenced by is_file")
                    return original_is_file(path)

                def reject_read_bytes(path: Path) -> bytes:
                    if path in {markdown, sidecar}:
                        raise AssertionError("redirected assessment was read")
                    return original_read_bytes(path)

                def reject_resolve(path: Path, strict: bool = False) -> Path:
                    if path in guarded:
                        raise AssertionError("redirected assessment was resolved before rejection")
                    return original_resolve(path, strict=strict)

                with (
                    mock.patch.object(Path, "is_file", reject_is_file),
                    mock.patch.object(Path, "read_bytes", reject_read_bytes),
                    mock.patch.object(Path, "resolve", reject_resolve),
                ):
                    errors = validator.validate_assessment(
                        value,
                        repository_root=root,
                        sidecar_path=sidecar,
                    )
                self.assertTrue(any("Markdown path uses a symlink or reparse point" in item for item in errors), errors)
                self.assertTrue(any("sidecar path uses a symlink or reparse point" in item for item in errors), errors)
            finally:
                os.rmdir(redirect) if os.name == "nt" else redirect.unlink()

    def test_public_assessment_rejects_redirect_swapped_after_precheck(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-public-race-test-") as temporary:
            root = Path(temporary).resolve()
            docs = root / "docs"
            markdown = docs / "bugs" / "bug-sample-failure" / "assessment-1.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("# Original assessment\n", encoding="utf-8", newline="\n")
            target = root / "redirect-target"
            redirected_markdown = target / "bugs" / "bug-sample-failure" / "assessment-1.md"
            redirected_markdown.parent.mkdir(parents=True)
            redirected_markdown.write_bytes(markdown.read_bytes())
            sidecar = markdown.with_suffix(".json")
            value = assessment_example(hashlib.sha256(markdown.read_bytes()).hexdigest())
            original_docs = root / "original-docs"
            swapped = False

            def swap_after_precheck(path: Path, repository_root: Path) -> bool:
                nonlocal swapped
                if not swapped and path == markdown:
                    docs.rename(original_docs)
                    if os.name == "nt":
                        created = subprocess.run(
                            ["cmd", "/d", "/c", "mklink", "/J", str(docs), str(target)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=False,
                        )
                        self.assertEqual(0, created.returncode, created.stderr.decode("utf-8", "replace"))
                    else:
                        docs.symlink_to(target, target_is_directory=True)
                    swapped = True
                return False

            try:
                with mock.patch.object(
                    validator,
                    "_has_reparse_component",
                    side_effect=swap_after_precheck,
                ):
                    errors = validator.validate_assessment(
                        value,
                        repository_root=root,
                        sidecar_path=sidecar,
                    )
                self.assertTrue(swapped)
                self.assertTrue(any("symlink or reparse point" in item for item in errors), errors)
            finally:
                if swapped:
                    os.rmdir(docs) if os.name == "nt" else docs.unlink()
                    original_docs.rename(docs)

    def test_allocator_prefers_legal_user_id_and_uses_minimum_collision_suffix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-id-test-") as temporary:
            root = Path(temporary)
            bugs = root / "docs" / "bugs"
            bugs.mkdir(parents=True)
            self.assertEqual("bug-user-choice", validator.allocate_bug_id(root, "sample failure", "bug-user-choice"))
            (bugs / "bug-user-choice").mkdir()
            self.assertEqual("bug-user-choice-2", validator.allocate_bug_id(root, "sample failure", "bug-user-choice"))
            (bugs / "bug-sample-failure").mkdir()
            (bugs / "bug-sample-failure-2").mkdir()
            self.assertEqual("bug-sample-failure-3", validator.allocate_bug_id(root, "sample failure"))

    def test_allocator_preserves_two_to_five_segments_for_non_ascii_single_and_long_topics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-id-topic-test-") as temporary:
            root = Path(temporary)
            bugs = root / "docs" / "bugs"
            bugs.mkdir(parents=True)

            cjk = validator.allocate_bug_id(root, "快取漂移")
            another_cjk = validator.allocate_bug_id(root, "登入失敗")
            self.assertNotEqual("bug-issue", cjk)
            self.assertNotEqual(cjk, another_cjk)
            self.assertTrue(validator.BUG_ID_RE.fullmatch(cjk), cjk)
            self.assertLessEqual(len(cjk), 64)
            self.assertIn(len(cjk.removeprefix("bug-").split("-")), range(2, 6))

            self.assertEqual("bug-cache-issue", validator.allocate_bug_id(root, "cache"))
            long_topic = validator.allocate_bug_id(root, "x" * 200)
            self.assertTrue(validator.BUG_ID_RE.fullmatch(long_topic), long_topic)
            self.assertLessEqual(len(long_topic), 64)
            self.assertIn(len(long_topic.removeprefix("bug-").split("-")), range(2, 6))

            (bugs / cjk).mkdir()
            self.assertEqual(f"{cjk}-2", validator.allocate_bug_id(root, "快取漂移"))

    def test_assessment_revision_must_be_the_smallest_available_positive_integer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-revision-test-") as temporary:
            root = Path(temporary)
            self.assertTrue(
                any(
                    "smallest available" in item
                    for item in validator.create_only_errors(root, "bug-sample-failure", 7)
                )
            )
            markdown = root / "docs" / "bugs" / "bug-sample-failure" / "assessment-7.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("# Revision seven\n", encoding="utf-8", newline="\n")
            value = assessment_example(hashlib.sha256(markdown.read_bytes()).hexdigest())
            value["revision"] = 7
            value["markdown"]["path"] = "docs/bugs/bug-sample-failure/assessment-7.md"
            errors = validator.validate_assessment(
                value,
                repository_root=root,
                sidecar_path=markdown.with_suffix(".json"),
            )
            self.assertTrue(any("smallest available" in item for item in errors), errors)

    def test_create_only_guard_rejects_existing_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bug-create-only-test-") as temporary:
            root = Path(temporary)
            markdown = root / "docs" / "bugs" / "bug-sample-failure" / "assessment-1.md"
            markdown.parent.mkdir(parents=True)
            markdown.write_text("existing\n", encoding="utf-8")
            errors = validator.create_only_errors(root, "bug-sample-failure", 1, "work-current-feature")
            self.assertTrue(any("already exists" in item for item in errors), errors)

    def test_schema_bytes_are_closed_against_required_field_mutation(self) -> None:
        schema = json.loads((SKILL_ROOT / "references" / "assessment.schema.json").read_text(encoding="utf-8"))
        value = assessment_example()
        value.pop("verdict")
        errors = validator.validate_instance(value, schema)
        self.assertTrue(any("missing required property verdict" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
