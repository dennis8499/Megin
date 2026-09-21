---
name: megin-implementation-execution
description: Execute an approved Megin work package in the bound checkout with one writer, bounded TDD evidence, and a fresh review handoff. Use for approved implementation, coding, 實作、開發、套用已核准計畫; do not start without an exact plan approval.
---

# Megin implementation execution

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) before
creating implementation evidence. Write summaries and handoff notes in Traditional Chinese while
keeping commands, paths, identifiers, and raw output unchanged.

Accept work only when `workflow.md` contains the current Work ID, approved plan version, branch or
workspace, allowed paths, interfaces, acceptance scenarios, commands, knowledge scope, and delivery
destination. Before each write, confirm branch and baseline identity and preserve unrelated dirty
changes.

Keep one authorized writer in the workspace. Work package dependencies are sequential; the writer
does not delegate. Use `megin-test-driven-development` for each behavior, preserve focused, related,
full, static, and contract command evidence, and keep changed paths within the approved scope. A
package reports `completed`, `needs_revision`, `blocked`, or `awaiting_upstream` in the Work ID
ledger.

When all packages are complete, save the current snapshot and hand off to a different fresh,
read-only `megin-code-review` context. Do not stage, commit, update canonical knowledge, or claim
completion before verification and human acceptance.
