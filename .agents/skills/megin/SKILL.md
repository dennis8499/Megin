---
name: megin
description: Run the Megin Skills-only delivery workflow for repository changes. Use when the user asks to add, build, change, refactor, repair, migrate, or deliver software, including 新增功能、開發、修改、重構、修正錯誤、交付、繼續上次工作. Do not use for a pure explanation, read-only review, or diagnosis without a requested repair.
---

# Megin Skills-only workflow

This is the conversation entry point for repository work. It is a Skills workflow, not a
plugin, command-line product, hook, or state controller. Use the repository's normal Git,
search, editor, and test tools directly, and record the workflow in
`docs/work/<work-id>/workflow.md`.

## Start and resume

1. Read repository instructions and inspect the current branch, status, relevant files, tests,
   and existing `docs/work/*/workflow.md` records without changing product files.
2. Use `megin-project-knowledge` to retrieve applicable source-backed project knowledge. Treat
   repository-local contracts as evidence, not as permission to mutate.
3. If one active Megin record exists for this repository, verify its identity and resume its
   earliest incomplete action. If several records are active, show their Work IDs and ask which
   one to continue. If none exists, create a new record only after the request is understood.
4. Classify the request as `read_only`, `small`, `large`, or `bug`. A pure explanation or review
   ends after evidence. A suspected bug goes through `megin-bug-diagnosis` before repair.

The record format and append-only event rules are in [workflow-record.md](references/workflow-record.md).

## Complete delivery path

For a change, route the same Work ID through these phases:

1. `requirements`: use `megin-requirements-discovery` to establish the goal, boundaries,
   acceptance, risks, and stable behavior scenarios.
2. `planning`: use `megin-behavior-contract` and `megin-technical-planning` to create the
   executable behavior contract, dependency-ordered work packages, allowed paths, commands,
   knowledge scope, and delivery destination.
3. `approval`: present the exact current plan and wait for the user to name the Work ID and
   plan version. This is the one plan gate for small and large work. A changed scope,
   interface, scenario, or acceptance criterion creates a new plan version.
4. `implementation`: after approval, use `megin-implementation-execution` and
   `megin-test-driven-development`. Keep one authorized writer in the workspace, follow
   outside-in behavior red → inner test red → minimal green → refactor, and save command
   evidence in the Work ID record.
5. `review`: start a fresh read-only `megin-code-review` context. It must inspect the current
   snapshot, approved scope, tests, compatibility, and knowledge claims. A writer cannot
   approve its own work.
6. `verification`: use `megin-verification-before-completion` to rerun every approved command
   and scenario against the reviewed snapshot. A passing automated verification stops at
   `awaiting_user_acceptance`.
7. `acceptance`: use `megin-human-acceptance` to show only the approved user-visible scenarios
   and wait for a response identifying the Work ID and acceptance version. Do not stage or
   commit before this response.
8. `delivery`: use `megin-project-knowledge` to review approved source-backed knowledge, then
   use `megin-finishing-delivery` to stage only approved paths and create one local commit.
   Push, pull requests, merge, deployment, branch deletion, and worktree cleanup remain
   outside this workflow.

## Conversation and safety rules

- Ask at most one highest-impact requirements question at a time. Resolve discoverable facts by
  reading the repository first; ask the user about priorities, boundaries, and trade-offs.
- Natural-language approval is bound to the exact Work ID, plan version, scope, scenarios,
  tests, knowledge scope, and local delivery target shown in the current record. Do not infer
  approval from a skill mention, a test result, or “continue” without an exact current target.
- Keep the current checkout and branch identity visible in the record. Preserve unrelated dirty
  changes. Scope drift, stale evidence, missing context, or repeated no-progress findings return
  the work to planning or mark it blocked with evidence.
- Never claim a test, review, acceptance, knowledge promotion, or commit that did not happen.
  If an independent reviewer is unavailable, stop at `awaiting_review`.
- Keep secrets out of records; store paths, summaries, byte counts, and digests where evidence
  must be referenced.

Completion means the record contains the final review, fresh verification, acceptance response,
knowledge result, commit identity, changed paths, and one clear next state. The workflow is
governed by these Skills and Markdown records; there is no Megin-specific executable to invoke.
