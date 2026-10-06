---
name: megin-code-review
description: Perform a fresh read-only review of an approved Megin snapshot. Use for code review, quality review, scope review, knowledge integrity, 審查、檢視修改、品質檢查; do not edit, commit, delegate, or approve your own changes.
---


# Megin code review

Read [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md) and [../megin/references/quality-gates.md](../megin/references/quality-gates.md). Start from a fresh, independent, read-only context after the writer reports a frozen snapshot. The reviewer must not have authored the implementation.

Inspect the approved plan, changed paths, implementation, tests, and relevant Repo documentation. Trace each promised behavior to code and meaningful assertions. Look for correctness defects, regressions, unsafe input handling, missing failure cases, and stale or unsupported claims. Cite exact file and line locations. Do not modify files or stage changes.

Run the read-only review gate with `quality_gate.py check --repo <Repo> --work-id <Work ID> --gate review`. A passing structural gate does not substitute for reasoning about behavior. Record the reviewer context, `APPROVED` or `NEEDS_REVISION`, snapshot, findings, and raw evidence. Handoff only when the review is complete; any repair requires a new snapshot and independent review.
