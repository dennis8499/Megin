#!/usr/bin/env python3
"""Mutation tests for requirements-discovery owner validation."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("validate_contracts.py")
SPEC = importlib.util.spec_from_file_location("requirements_contract_validator", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {SCRIPT}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
SOURCE_ROOT = SCRIPT.resolve().parents[1]


class RequirementsContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="requirements-contract-")
        self.root = Path(self.temporary.name) / "requirements-discovery"
        shutil.copytree(SOURCE_ROOT, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def mutate(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def assert_failure(self, fragment: str) -> None:
        errors = validator.validate_all(self.root)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_current_bundle_passes(self) -> None:
        self.assertEqual([], validator.validate_all(SOURCE_ROOT))

    def test_duplicate_authority_is_rejected(self) -> None:
        path = self.root / "references" / "delivery-protocol.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n<!-- authority: requirements-quality -->\n",
            encoding="utf-8",
            newline="\n",
        )
        self.assert_failure("duplicate authority requirements-quality")

    def test_broken_link_is_rejected(self) -> None:
        self.mutate("SKILL.md", "(references/quality-contract.md)", "(references/missing-quality.md)")
        self.assert_failure("broken local link")

    def test_coverage_mutation_is_rejected(self) -> None:
        self.mutate(
            "SKILL.md",
            "13. 驗收條件、成功指標、來源與追溯關係",
            "14. 驗收條件、成功指標、來源與追溯關係",
        )
        self.assert_failure("coverage map missing item 13")

    def test_high_risk_routing_mutation_is_rejected(self) -> None:
        self.mutate(
            "SKILL.md",
            "(references/high-risk-contract.md)",
            "(references/high-risk-contract.md#first-load)",
        )
        self.assert_failure("high-risk contract must load")

    def test_source_version_mutation_is_rejected(self) -> None:
        self.mutate("references/quality-contract.md", "ISO/IEC/IEEE 29148:2018", "ISO/IEC/IEEE 29148")
        self.assert_failure("quality source version drifted")

    def test_state_mutation_is_rejected(self) -> None:
        self.mutate("references/delivery-protocol.md", "Candidate—Awaiting confirmation", "Candidate")
        self.assert_failure("delivery state missing")

    def test_id_family_mutation_is_rejected(self) -> None:
        self.mutate("references/requirements-analysis-template.md", "CR-*", "CONTROL-*")
        self.assert_failure("template missing ID family: CR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
