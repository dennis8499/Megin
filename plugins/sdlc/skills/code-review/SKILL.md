---
name: code-review
description: Perform a fresh, read-only review of an approved work snapshot for requirements fit, code quality, tests, knowledge integrity, and scope safety.
---

# Code Review

Run this skill with fresh reviewer context after the authorized writer reports completion. The reviewer evaluates the exact approved work identity and current snapshot; it does not edit files, commit, push, delegate, or approve its own changes.

## Review procedure

1. Load the approved candidate or plan, acceptance criteria, allowed paths, required commands, knowledge-update scope, and current snapshot identity.
2. Inspect the full diff, surrounding code, tests, configuration, documentation, and generated artifacts that belong to the work. Confirm no unrelated or unauthorized path changed.
3. Check behavior against every acceptance criterion, including error paths, compatibility, security/privacy boundaries, data and permission effects, and operational failure handling relevant to the change.
4. Check tests for meaningful red-to-green coverage, regression protection, deterministic assertions, and appropriate focused/related coverage. Run the required commands when the reviewer environment can do so, preserving raw output.
5. Review knowledge updates separately: each claim must be supported by the approved outcome, retain source references and content digests, pass the repository knowledge lint, and handle conflicts without silently replacing canonical knowledge.
6. Recalculate or inspect the product snapshot and evidence bindings. Any drift after the reviewed snapshot invalidates the verdict and requires a new review.

## Findings and verdict

Report findings with severity (`blocking`, `major`, `minor`), path or symbol, evidence, and a concrete correction. Blocking findings include unmet acceptance, security or compatibility regressions, unauthorized scope, missing required tests, stale evidence, or an invalid knowledge claim that affects product correctness.

Return exactly one verdict:

- `APPROVED`: all required checks pass for the reviewed snapshot.
- `CHANGES_REQUIRED`: the writer must fix listed findings, then a fresh reviewer must inspect the new snapshot.
- `BLOCKED`: the environment, required context, or independent reviewer capability is unavailable; do not convert this into approval.

The review report must include the work identity, reviewer identity, snapshot digest, commands and results, coverage of obligations, knowledge result, findings, verdict, and next action. The controller may use an approved product result with a clearly recorded knowledge-only pending item only where the governing delivery contract permits it.
