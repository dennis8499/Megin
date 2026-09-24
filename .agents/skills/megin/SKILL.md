---
name: megin
description: Run the Megin Skills-only delivery workflow for repository changes. Use when the user asks to add, build, change, refactor, repair, migrate, or deliver software, including 新增功能、開發、修改、重構、修正錯誤、交付、繼續上次工作. Do not use for a pure explanation, read-only review, or diagnosis without a requested repair.
---

# Megin Skills-only workflow

This is the conversation entry point for repository work. It is a Skills workflow, not a
plugin, command-line product, hook, or state controller. Use the repository's normal Git,
search, editor, and test tools directly. New product work starts from a non-Git Group root,
selects one or more direct-child Git repositories, and records the workflow in
`<Group>/docs/work/<work-id>/workflow.md`. Read [group-workspace.md](references/group-workspace.md)
before selecting repositories or running commands.

## Start and resume

1. Confirm the current directory is the Group root and identify the requested direct-child Repo or
   Repos. Ask which Repo when the name/path is missing, ambiguous, nested, or outside the Group.
   Inspect each selected Repo's instructions, branch, status, relevant files and tests, plus the
   central `<Group>/docs/work/*/workflow.md` records without changing product files.
2. Use `megin-project-knowledge` to retrieve source-backed knowledge from each selected Repo.
   Treat repository-local contracts as evidence, not as permission to mutate.
3. Classify the request as `read_only`, `small`, `large`, or `bug` before creating a new record.
   A pure explanation or review is `read_only` and ends after evidence without a delivery record. A
   suspected defect is `bug` and goes through `megin-bug-diagnosis`; create a requirements record
   only if diagnosis hands off to an authorized repair.
4. Resume the earliest incomplete action in the uniquely matching Group Work ID. If several Group
   records are active and the request does not identify one, show their IDs and ask which to
   continue. If none exists for a `small` or `large` change, create the central requirements record;
   when major unknowns remain, set `phase: requirements` and `status: awaiting_user`.

The Group record format and append-only event rules are in [workflow-record.md](references/workflow-record.md).
The output language rules are in [language-policy.md](references/language-policy.md); the shared requirements
exploration semantics are in [requirements-discovery-protocol.md](references/requirements-discovery-protocol.md).
read it before creating or updating any human-readable delivery document. The Git branch, acceptance,
and local integration rules are in [branch-policy.md](references/branch-policy.md); read it before
planning or executing a repository change.
For a new or resumed change, read [quality-gates.md](references/quality-gates.md) before planning
the evidence or crossing a review, acceptance, or delivery gate. Keep the approved plan as the
obligation source and `workflow.md` as the status source.

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
4. `implementation`: after approval, recheck and fetch each recorded remote base SHA, then create
   one `feature/<Work ID>` branch per Repo from that exact commit. Use
   `megin-implementation-execution` and `megin-test-driven-development` only on those branches.
   Keep one authorized writer in the workspace, follow outside-in behavior red → inner test red →
   minimal green → refactor, and save command evidence centrally with its explicit Repo `cwd`.
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
   `megin-finishing-delivery` to stage approved paths and create a feature commit in every Repo.
   For one Repo, fast-forward its clean local base to the still-confirmed remote SHA, then integrate
   locally with `git merge --no-ff`. For multiple Repos, create feature commits only and provide a
   per-Repo manual-merge handoff. Push, pull requests, deployment, branch deletion, and worktree
   cleanup remain outside this workflow.

## Conversation and safety rules

- Read [language-policy.md](references/language-policy.md) and
  [requirements-discovery-protocol.md](references/requirements-discovery-protocol.md) before producing a work
  document. Ask at most one prerequisite-ready highest-impact requirements question at a time. When a major unknown
  remains, pause in `phase: requirements` with `status: awaiting_user`; do not infer a product decision or hand off
  to planning until the protocol's completion conditions hold. Resolve discoverable facts by reading the repository
  and applicable sources first; ask the user about priorities, boundaries, and trade-offs.
- Natural-language approval is bound to the exact Work ID, plan version, scope, scenarios,
  tests, knowledge scope, and local delivery target shown in the current record. Do not infer
  approval from a skill mention, a test result, or “continue” without an exact current target.
- Keep the Group root, selected Repo paths, each branch identity, and each command `cwd` visible in
  the central record. Product writes after approval require the corresponding recorded feature
  branch. Preserve unrelated dirty changes. Scope drift, remote/base drift, stale evidence, missing
  context, or repeated no-progress findings return the work to planning or mark it blocked with
  evidence. Follow [group-workspace.md](references/group-workspace.md) and
  [branch-policy.md](references/branch-policy.md) for recovery.
- Never claim a test, review, acceptance, knowledge promotion, or commit that did not happen.
  If an independent reviewer is unavailable, stop at `awaiting_review`.
- For new Group quality evidence, run `megin/scripts/quality_gate.py` with `--group-root` and
  `--work-id` at each relevant handoff. A structural pass does not replace independent judgment or
  executed tests.
- After each work package, record completed work, fresh verification, uncertainty, and the next
  action.
- Keep secrets out of records; store paths, summaries, byte counts, and digests where evidence
  must be referenced.

Completion means the central record contains the final review, fresh verification, acceptance
response, knowledge result, approved paths, and one clear next state. A single Repo also records
the feature and `--no-ff` merge commits plus integration checks. Multiple Repos record every feature
commit and the manual-merge handoff; Megin does not merge their base branches. The workflow is
governed by these Skills and Markdown records; there is no Megin-specific executable to invoke.
