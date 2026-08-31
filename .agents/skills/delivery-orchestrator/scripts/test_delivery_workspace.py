#!/usr/bin/env python3
"""Compatibility runner for the split delivery-orchestrator test suites."""

from __future__ import annotations

import unittest

from test_delivery_safety import DeliverySafetyTests
from test_delivery_transitions import (
    DeliveryBugOverlayTests,
    DeliveryTerminalContractTests,
    DeliveryTransitionTests,
)
from test_delivery_worktree import DeliveryWorktreeTests


if __name__ == "__main__":
    unittest.main(verbosity=2)
