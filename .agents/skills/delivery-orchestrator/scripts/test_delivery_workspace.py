#!/usr/bin/env python3
"""Compatibility runner for the split delivery-orchestrator test suites."""

from __future__ import annotations

import contextlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import _delivery_git as delivery_git
import _delivery_record as delivery_record
import _delivery_test_support as support
from test_delivery_safety import DeliverySafetyTests
from test_delivery_transitions import (
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryTransitionTests,
)
from test_delivery_worktree import DeliveryWorktreeTests


class DeliveryPerformanceTests(support.DeliveryFixture):
    def test_full_probe_and_ready_transition_stay_within_git_budgets(self) -> None:
        primary = self.make_repo("performance-project")
        commands: list[dict[str, object]] = []
        real_git = delivery_git._git
        lock_active = False

        def recording_git(
            repo: str | Path,
            arguments: list[str],
            *,
            check: bool = True,
            input_bytes: bytes | None = None,
        ) -> object:
            commands.append(
                {
                    "lock": "post" if lock_active else "pre",
                    "arguments": list(arguments),
                }
            )
            return real_git(
                repo,
                arguments,
                check=check,
                input_bytes=input_bytes,
            )

        git_patches = (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
        )
        with git_patches[0], git_patches[1], git_patches[2]:
            probe = support.workspace.probe_repository(primary)

        self.assertTrue(probe["strict_clean"])
        full_probe_commands = list(commands)
        self.assertEqual(
            [
                "rev-parse",
                "--is-bare-repository",
                "--show-toplevel",
                "--path-format=absolute",
                "--git-common-dir",
                "HEAD",
            ],
            full_probe_commands[0]["arguments"],
        )
        self.assertEqual(
            1,
            sum(
                item["arguments"][-3:] == ["ls-files", "--stage", "-z"]
                for item in full_probe_commands
            ),
        )
        self.assertFalse(
            any(
                item["arguments"][-2:] == ["ls-files", "-z"]
                for item in full_probe_commands
            )
        )

        delivery = Path(
            self.start(primary, "performance-transition-work")["worktree"]
        )
        commands.clear()
        real_lock = support.workspace._exclusive_lock

        @contextlib.contextmanager
        def recording_lock(path: Path) -> object:
            nonlocal lock_active
            with real_lock(path):
                lock_active = True
                try:
                    yield
                finally:
                    lock_active = False

        with (
            mock.patch.object(delivery_git, "_git", side_effect=recording_git),
            mock.patch.object(delivery_record, "_git", side_effect=recording_git),
            mock.patch.object(support.workspace, "_git", side_effect=recording_git),
            mock.patch.object(
                support.workspace,
                "_exclusive_lock",
                side_effect=recording_lock,
            ),
        ):
            transitioned = self.transition(
                delivery,
                "performance-transition-work",
                "requirements",
                "active",
                "requirements_started",
            )

        self.assertEqual("requirements", transitioned["phase"])
        self.assertEqual("active", transitioned["status"])
        failures: dict[str, object] = {}
        if len(full_probe_commands) > 6:
            failures["full_probe_git_calls"] = len(full_probe_commands)
        if len(commands) > 8:
            failures["ready_transition_git_calls"] = len(commands)
        pre_lock_calls = sum(item["lock"] == "pre" for item in commands)
        if pre_lock_calls != 1:
            failures["pre_lock_git_calls"] = pre_lock_calls
        if not any(
            item["lock"] == "post" and "status" in item["arguments"]
            for item in commands
        ):
            failures["post_lock_status_probe"] = "missing"
        self.assertEqual(
            {},
            failures,
            json.dumps(
                {
                    "failures": failures,
                    "full_probe_commands": full_probe_commands,
                    "ready_transition_commands": commands,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )


TEST_CASES = (
    DeliverySafetyTests,
    DeliveryTransitionTests,
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryWorktreeTests,
    DeliveryPerformanceTests,
)


def _test_ids(suite: unittest.TestSuite) -> list[str]:
    result: list[str] = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            result.extend(_test_ids(item))
        else:
            result.append(item.id().removeprefix("__main__."))
    return result


def _inventory() -> dict[str, object]:
    loader = unittest.defaultTestLoader
    tests = sorted(
        {
            test_id
            for case in TEST_CASES
            for test_id in _test_ids(loader.loadTestsFromTestCase(case))
        }
    )
    return {
        "schema": "delivery-test-inventory/v1",
        "discovered": len(tests),
        "tests": tests,
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--list-tests"]:
        print(json.dumps(_inventory(), ensure_ascii=False, sort_keys=True))
    else:
        unittest.main(verbosity=2)
