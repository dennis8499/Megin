# SDLC Transformation v2 Requirements

## Goal

Provide a reusable, cross-project SDLC workflow for Codex that keeps repository traceability and approval guarantees while adopting task-sized workflows and supervised subagent implementation.

## Required outcomes

- Classify work as read-only, small, large, or bug before mutation.
- Use one integrated approval for a small task and separate requirements and plan approvals for a large task.
- Package the workflow as an installable `sdlc` Codex plugin whose runtime state is outside target repositories.
- Provide portable `init`, `doctor`, `start`, `resume`, `status`, and `finish` commands.
- Persist versioned delivery state, task assignments, review results, knowledge scope, and publication state without secrets.
- Permit one authorized implementation writer at a time, with a fresh read-only reviewer and a bounded fix loop.
- Run focused and full verification before completion; stale, skipped, or drifted evidence cannot complete a run.
- Automatically commit approved changes and, when a remote is configured, push the branch and create a draft pull request. Merge, deployment, and cleanup remain separate actions.
- Preserve existing v1 delivery records and skills; v2 records are used only for new portable runs.

## Boundaries

The first release targets Codex and validates Windows and Linux. It does not implement automatic merge, deployment, public marketplace publication, or multi-agent-platform adapters.

## Acceptance

The implementation must pass plugin manifest validation, portable CLI tests in clean Git repositories, classification and state-transition tests, existing repository quick checks, and documentation/contract checks. A package must work without a target project's `.agents/skills` tree.
