---
name: implementation-execution
description: Execute an approved v2 dispatch package with one authorized writer, TDD evidence, bounded fixes, and a fresh read-only review handoff.
---

# Implementation Execution

Accept work only from `megin-orchestrator` with a current v2 dispatch authorization. The package
must bind Work ID, state revision, worktree and branch, acceptance, required interfaces, allowed
and forbidden paths, test commands, evidence destination, knowledge scope, and finish destination.

Assign at most one writer to a worktree. The writer may be an implementation subagent and must
not delegate again or write outside the package. Run outside-in behavior red, inner test red,
minimal green, and refactor-with-green; preserve focused, related, and full command evidence.
Report `completed`, `needs_revision`, `blocked`, or `awaiting_upstream` with changed paths and
digests. After completion, a different fresh Reviewer reads the current diff and evidence in
read-only mode. Findings return to the same writer with a new assignment; repeated no-progress
rounds stop at blocked. Only an approved reviewer and verification result may hand off to
`project-knowledge` and `finishing-delivery`.
