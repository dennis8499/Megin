---
name: megin-implementation-execution
description: Execute an approved Megin work package in the bound checkout with one writer, bounded TDD evidence, and a fresh review handoff. Use for approved implementation, coding, 實作、開發、套用已核准計畫; do not start without an exact plan approval.
---

# Megin implementation execution

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and
[../megin/references/branch-policy.md](../megin/references/branch-policy.md) before creating
implementation evidence. Write summaries and handoff notes in Traditional Chinese while keeping
commands, paths, identifiers, and raw output unchanged.

Accept work only when `workflow.md` contains the current Work ID, approved plan version,
`base_branch`, `base_commit`, `feature_branch`, workspace, allowed paths, interfaces, acceptance
scenarios, commands, knowledge scope, and delivery destination. After approval, create the named
feature branch from `base_commit` if it does not already exist, then before each write confirm the
current branch is exactly that feature branch and preserve unrelated dirty changes. Never write
product files directly on the base branch.

Keep one authorized writer in the workspace. Work package dependencies are sequential; the writer
does not delegate. Use `megin-test-driven-development` for each behavior, preserve focused, related,
full, static, and contract command evidence, and keep changed paths within the approved scope. A
package reports `completed`, `needs_revision`, `blocked`, or `awaiting_upstream` in the Work ID
ledger.
At each package boundary, follow [../megin/references/quality-gates.md](../megin/references/quality-gates.md):
record completed work, commands actually run, uncertainty, and the next action. Before a formal
review handoff, run its read-only `review` gate against the exact feature snapshot. A failed gate
keeps the package in implementation; an optional diagnostic review cannot approve it.
The cited writer handoff starts with the exact machine-readable `context` and `snapshot` lines
defined by the shared reference; do not copy different values into structured evidence.

When all packages are complete, save the current snapshot and hand off to a different fresh,
read-only `megin-code-review` context. Do not stage, commit, update canonical knowledge, or claim
completion before verification and human acceptance. A base-branch advance, feature-branch drift,
or any change after review invalidates the handoff and requires the recovery path in
[branch-policy.md](../megin/references/branch-policy.md).
