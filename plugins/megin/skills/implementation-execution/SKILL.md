---
name: implementation-execution
description: Execute an approved Megin v3 task in the bound checkout or worktree with one fresh writer, BDD/TDD evidence, bounded fixes, and a fresh read-only review handoff.
---

# Implementation Execution

Accept work only from `megin-orchestrator` with a current v3 task authorization. The package
must bind Work ID, state revision, worktree and branch, acceptance, required interfaces, allowed
and forbidden paths, test commands, evidence destination, knowledge scope, and finish destination.

In current-directory mode, verify that the feature branch and baseline are unchanged before every
write. Never create a second writer for the same repository, and never stage or commit before
automated verification and human acceptance.

Assign at most one writer to a workspace. The writer may be an implementation subagent and must
not delegate again or write outside the package. Run outside-in behavior red, inner test red,
minimal green, and refactor-with-green; preserve focused, related, and full command evidence.
Report `completed`, `needs_revision`, `blocked`, or `awaiting_upstream` with changed paths and
digests. After completion, a different fresh Reviewer reads the current diff and evidence in
read-only mode. Findings return to the same writer with a new assignment; repeated no-progress
rounds stop at blocked. Only an approved reviewer and verification result may hand off to
`project-knowledge` and `finishing-delivery`.
