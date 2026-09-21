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
3. Classify the request as `read_only`, `small`, `large`, or `bug` before creating a new record.
   A pure explanation or review is `read_only` and ends after evidence without a delivery record. A
   suspected defect is `bug` and goes through `megin-bug-diagnosis`; create a requirements record
   only if diagnosis hands off to an authorized repair.
4. If one active Megin record exists for this repository, verify its identity and resume its
   earliest incomplete action. If several records are active, show their Work IDs and ask which
   one to continue. If no active record exists for a `small` or `large` change, create a new
   requirements record; when major unknowns remain, initialize it at `phase: requirements` with
   `status: awaiting_user` instead of treating the request as understood.

The record format and append-only event rules are in [workflow-record.md](references/workflow-record.md).
The output language and requirements waiting rules are in [language-policy.md](references/language-policy.md);
read it before creating or updating any human-readable delivery document. The Git branch, acceptance,
and local integration rules are in [branch-policy.md](references/branch-policy.md); read it before
planning or executing a repository change.

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
4. `implementation`: after approval, create the recorded feature branch from the recorded base
   branch and use `megin-implementation-execution` and `megin-test-driven-development` only there.
   Keep one authorized writer in the workspace, follow outside-in behavior red → inner test red →
   minimal green → refactor, and save command evidence in the Work ID record. The base branch stays
   unchanged until human acceptance.
5. `review`: start a fresh read-only `megin-code-review` context. It must inspect the current
   snapshot, approved scope, tests, compatibility, and knowledge claims. A writer cannot
   approve its own work.
6. `verification`: use `megin-verification-before-completion` to rerun every approved command
   and scenario against the reviewed snapshot. A passing automated verification stops at
   `phase: acceptance` and `status: awaiting_user`.
7. `acceptance`: use `megin-human-acceptance` to show only the approved user-visible scenarios
   and wait for a response identifying the Work ID and acceptance version. Do not stage or
   commit before this response.
8. `delivery`: after the exact acceptance response, use `megin-project-knowledge` and
   `megin-finishing-delivery` to stage approved paths and create one feature commit. Confirm the
   base branch has not drifted, then merge the feature branch back locally with `git merge --no-ff`
   and record the parent and content checks. Push, pull requests, deployment, branch deletion, and
   worktree cleanup remain outside this workflow.

## Conversation and safety rules

- Read [language-policy.md](references/language-policy.md) before producing a work document. Ask at
  most one highest-impact requirements question at a time. When a major unknown remains, pause in
  `phase: requirements` with `status: awaiting_user`; do not infer a product decision or hand off
  to planning until the answer resolves it. Resolve discoverable facts by reading the repository
  first; ask the user about priorities, boundaries, and trade-offs.
- Natural-language approval is bound to the exact Work ID, plan version, scope, scenarios,
  tests, knowledge scope, and local delivery target shown in the current record. Do not infer
  approval from a skill mention, a test result, or “continue” without an exact current target.
- Keep the current checkout and branch identity visible in the record. Product writes after approval
  require the recorded feature branch; the base branch must remain free of the Work ID until
  acceptance. Preserve unrelated dirty changes. Scope drift, branch drift, stale evidence, missing
  context, or repeated no-progress findings return the work to planning or mark it blocked with
  evidence. Follow [branch-policy.md](references/branch-policy.md) for recovery.
- Never claim a test, review, acceptance, knowledge promotion, or commit that did not happen.
  If an independent reviewer is unavailable, stop at `awaiting_review`.
- Keep secrets out of records; store paths, summaries, byte counts, and digests where evidence
  must be referenced.

Completion means the record contains the final review, fresh verification, acceptance response,
knowledge result, feature commit, `--no-ff` merge identity, changed paths, integration checks, and
one clear next state. The workflow is governed by these Skills and Markdown records; there is no
Megin-specific executable to invoke.
