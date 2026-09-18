---
name: test-driven-development
description: Implement an approved Megin v2 change with an outside-in behavior red-green-refactor loop, focused evidence, and regression coverage for defects.
---

# Test-Driven Development

Use this skill only after `megin-orchestrator` has granted implementation authority for the exact work identity and scope. The approved acceptance criteria are the source of behavior; do not invent a broader contract while coding.

## The loop

For each dependency-ordered work item:

1. Translate one approved acceptance criterion into a public behavior scenario or equivalent contract test.
2. Run it before the implementation and preserve the genuine failure as the **red** evidence. A test that passes before the change does not prove the new behavior.
3. Add the smallest inner unit or integration test needed to expose the next design seam, when the codebase has such a test layer.
4. Implement the smallest production change that makes the focused test pass.
5. Refactor only with the relevant tests green; keep behavior and public interfaces within the approved scope.
6. Run the scenario, focused tests, and related suite. Record exact commands, exit status, and raw output before marking the work item verified.

Do not skip the red step merely because the change looks small. A small task may express the acceptance test through an existing public test harness; it does not require introducing a new BDD framework.

## Boundaries and evidence

The authorized writer is the only process that edits the workspace. Change only the product, test, and explicitly test-only configuration paths listed in the approved plan. If implementation needs an unlisted interface, dependency, migration, permission, or data change, stop and return to planning.

Every evidence record must identify the work item, source/test snapshot, command, timestamp, exit status, and output location. Re-run affected obligations whenever code, configuration, dependencies, or test inputs change. Never cite an earlier green result for a different snapshot.

## Bug overlay

For a bug repair, first re-run the original symptom oracle. Then create a regression test that fails for the diagnosed cause. Make one minimal root-cause fix, run the regression and related tests, and record whether the bug is `verified`, `partial`, or `failed`. Do not stack speculative fixes when the diagnosis or oracle is invalid; return to diagnosis or planning.

## Completion handoff

Report each work item as `verified`, `needs-fix`, `blocked`, or `scope-expanded`, with the evidence paths and next action. All work items must be verified before the controller can enter full verification. A green focused test alone is insufficient for completion when the approved plan requires related or full-suite checks.
