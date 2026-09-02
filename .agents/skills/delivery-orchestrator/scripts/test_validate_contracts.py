#!/usr/bin/env python3
"""Mutation tests for delivery-orchestrator owner validation."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("delivery_contract_validator", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
SOURCE_SKILLS = SCRIPT.resolve().parents[2]


class DeliveryContractMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="delivery-validator-")
        self.skills = Path(self.temporary.name) / "skills"
        for name in (
            "delivery-orchestrator",
            "technical-planning",
            "implementation-execution",
            "requirements-discovery",
        ):
            shutil.copytree(SOURCE_SKILLS / name, self.skills / name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def errors(self) -> list[str]:
        return validator.validate_all(self.skills)

    def assert_failure(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(any(fragment in error for error in errors), errors)

    def mutate(self, relative: str, old: str, new: str) -> None:
        path = self.skills / "delivery-orchestrator" / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def test_current_bundle_passes(self) -> None:
        self.assertEqual([], validator.validate_all(SOURCE_SKILLS))

    def test_duplicate_authority_is_rejected(self) -> None:
        path = (
            self.skills
            / "delivery-orchestrator/references/stage-routing.md"
        )
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n<!-- authority: delivery-run -->\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assert_failure("duplicate authority delivery-run")

    def test_broken_link_is_rejected(self) -> None:
        self.mutate(
            "SKILL.md",
            "(references/workspace-and-run.md)",
            "(references/missing-run.md)",
        )
        self.assert_failure("broken local link")

    def test_schema_byte_mutation_is_rejected(self) -> None:
        path = (
            self.skills
            / "delivery-orchestrator/references/delivery-run.schema.json"
        )
        schema = json.loads(path.read_text(encoding="utf-8"))
        schema["title"] = "mutated"
        path.write_text(json.dumps(schema), encoding="utf-8", newline="\n")
        self.assert_failure("schema bytes drifted")

    def test_public_command_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/delivery_workspace.py",
            'add_parser("transition",',
            'add_parser("transition-x",',
        )
        self.assert_failure("public CLI commands drifted")

    def test_trust_marker_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_git.py",
            "detected dubious ownership",
            "untrusted repository",
        )
        self.assert_failure("missing safety primitive")

    def test_missing_private_module_is_rejected(self) -> None:
        (
            self.skills
            / "delivery-orchestrator/scripts/_delivery_record.py"
        ).unlink()
        self.assert_failure("missing required file")

    def test_recorded_base_byte_probe_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            '["cat-file", "blob"',
            '["cat-file", "-e"',
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_historical_handoff_uses_its_approval_time_trust_root(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "_validate_historical_ready_contract(historical)",
            "_validate_ready_contract(historical)",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_terminal_review_validation_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "validator.validate_review_against_ready(",
            "validator.validate_review_without_ready(",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_terminal_bug_evidence_forwarding_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "terminal_evidence_refs=terminal_refs,",
            "terminal_evidence_refs=(),",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_bug_raw_json_forwarding_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "raw_json_bytes=verification_bytes,",
            "raw_json_bytes=None,",
        )
        self.assert_failure("raw BUG verification bytes")

    def test_bug_raw_assessment_forwarding_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "sidecar_bytes=sidecar_bytes,",
            "sidecar_bytes=None,",
        )
        self.assert_failure("raw BUG assessment bytes")

    def test_early_bug_verification_binding_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "successful BUG verification may only bind at legacy Complete or the reviewed knowledge gate",
            "BUG verification accepted before terminal",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_terminal_snapshot_binding_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "candidate_snapshot == current_snapshot",
            "candidate_snapshot == candidate_snapshot",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_terminal_textconv_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            '"--no-textconv",',
            '"--textconv",',
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_secret_ref_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_runtime.py",
            "or _contains_sensitive_material(ref)",
            "or False",
        )
        self.assert_failure("runtime authority missing secret-ref guard")

    def test_bug_inbox_create_only_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_runtime.py",
            "os.O_CREAT | os.O_EXCL | os.O_WRONLY",
            "os.O_CREAT | os.O_WRONLY",
        )
        self.assert_failure("both inbox creation and record locking")

    def test_failed_bug_verification_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            "failed BUG verification cannot enter a terminal knowledge gate",
            "failed BUG verification accepted at the terminal knowledge gate",
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_pending_bug_materialization_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            'code="PENDING_BUG_EVIDENCE"',
            'code="MISSING_GATE"',
        )
        self.assert_failure("record authority missing semantic primitive")

    def test_affecting_bug_reapproval_guard_mutation_is_rejected(self) -> None:
        self.mutate(
            "scripts/_delivery_record.py",
            'code="BUG_REQUIRES_REAPPROVAL"',
            'code="INVALID_DEFERRED_BUG"',
        )
        self.assert_failure("record authority missing semantic primitive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
