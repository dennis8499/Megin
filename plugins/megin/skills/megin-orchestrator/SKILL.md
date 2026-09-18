---
name: megin-orchestrator
description: Guide natural-language repository work through evidence-first questions, small/large/bug routing, design approval, TDD implementation, fresh review, and safe resume. Use for requests that may change a repository; do not use for pure explanations or read-only evaluation.
---

# Megin Orchestrator

Use this skill as the entry point whenever a request may change a repository. It owns classification, approval, work identity, phase routing, resume state, and the handoff to the other Megin skills.

## 1. Understand intent before mutating

Treat every new request as a conversation, not a command line translation. First determine
whether the user wants an explanation, a plan, a diagnosis, or a product change. A mention of
`error`, `API`, or `bug` is not a repair request by itself. If intent or scope is mixed, ask one
highest-impact question and keep the run read-only until the answer is clear. Use repository
evidence to answer discoverable facts; ask the user only for priorities, boundaries, or choices.

When there is a meaningful design choice, present two or three approaches with trade-offs and a
recommendation. Small, obvious edits do not need artificial alternatives. Keep the user's language
for the conversation and stable ASCII identifiers for state fields.

## 2. Explore before mutating

Inspect the repository, current branch, local instructions, existing work records, and available validation tools with read-only commands. Resolve the repository explicitly; do not assume that the target project contains this plugin or a fixed `.agents/skills` path. When the repository provides a validator or CLI, use it as the source of truth.

Do not create a delivery workspace, branch, record, or product diff until the applicable approval gate has passed. Read-only exploration, diagnosis, and review do not create a delivery run.

## 3. Classify the request

Choose exactly one route and record the reason:

- **Read-only**: explanation, evaluation, diagnosis, or review. Gather evidence and report findings without product mutation.
- **Small task**: one clear result in an existing flow, with known acceptance and no cross-module contract, data migration, permission, dependency, or architectural change.
- **Large change**: a new subsystem, architecture or contract change, migration, permission/dependency change, material uncertainty, or anything that cannot be proven small.
- **Bug**: a suspected defect. Diagnose the symptom first; only a `confirmed` or `likely` diagnosis may enter repair, then classify the repair by its impact.
- **Tiny formatting/text edit**: retain the repository's direct handling exception when it is genuinely limited to formatting or wording and has no behavior change.

Classification is based on impact and uncertainty, not line count. If a small task reveals a larger boundary, preserve its evidence, stop the current route, and re-enter the large-change requirements and planning gates for the expanded scope.

## 4. Bind approval to the work

Create a short, reviewable candidate before mutation. It must state the goal, in-scope and out-of-scope files or interfaces, acceptance criteria, implementation steps, test commands, knowledge-update scope, publication target, and the repository/work identity.

- A small task has **one integrated approval** for its design, acceptance, implementation, verification, knowledge review, and the stated Git publication target.
- A large change has **two approvals**: requirements first, then the technical plan. The second gate authorizes implementation of the exact approved plan.
- A bug repair keeps the diagnosis as evidence; requirements still own what to change and the plan owns how to change it.

Approval is valid only for the exact candidate revision and work identity. A changed acceptance criterion, expanded file set, new publication destination, or changed knowledge claim requires a new approval. Never treat a prompt, skill name, or child-agent report as write authorization.

## 5. Coordinate implementation and review

After approval, create or resume the approved workspace. New v2 work defaults to the current checkout:
resolve the repository's main/master base, verify a clean starting tree, and create `feat/<work-id>`.
Use `--workspace-mode worktree` only when the user or approved scope requests isolation. Keep product
files, work records, and evidence tied to the same work identity. Route implementation to the
authorized writer and apply `test-driven-development` to each behavior; use repository-specific
implementation tooling when it exists.

At most **one authorized writer** may change the workspace at a time. The controller coordinates dependencies and state; the writer edits product and explicitly allowed test files. A writer must not delegate again. If subagents are unavailable, execute sequentially while keeping the same authorization and review boundaries.

For every implementation unit, dispatch a handoff containing the approved acceptance, allowed paths, required interfaces, test commands, dependencies, and report location. Require a fresh read-only `code-review` after the writer reports completion. A reviewer cannot edit, commit, or approve its own changes. If an independent reviewer is unavailable, stop at awaiting review.

## 6. Review knowledge and resume

Treat knowledge changes as deliverables. The reviewer must check that each proposed claim is supported by the approved result, retains source references and content digests, and does not silently overwrite a conflicting canonical claim. Once the independent review passes, automatically promote an authorized knowledge update when the repository contract supports promotion; otherwise preserve a reviewed candidate and its pending action. Product correctness findings block completion; a knowledge-only dispute may leave the product complete with an explicit pending item, according to the repository contract.

Persist phase, approval identity, writer/reviewer reports, command evidence, current snapshot hashes, and the next action. On resume, validate the exact work identity and continue at the earliest incomplete action. Do not repeat completed work or bypass a failed gate. Scope drift, stale evidence, missing context, or repeated no-progress attempts require a blocker or a return to planning.

## 7. Report progress and route completion

Keep three kinds of communication distinct: discussion records provisional
decisions and open questions; formal approval names the exact candidate revision
and bound workspace/finish destination; progress reports only done, current, and
next. Do not ask the user to approve the same decision again after it is already
bound to the current candidate.

Keep updates compact and consistent:

```text
work: <id> / generation: <n>
route: <read-only | small | large | bug>
phase: <requirements | planning | implementation | review | verification | delivery>
approval: <required | approved | stale>
done: <completed units>
current: <active unit or blocker>
next: <one concrete action or decision>
```

Before declaring completion, invoke `verification-before-completion`. After a passing review and verification,
invoke `finishing-delivery`. The default delivery target is an unstaged, verified diff on the feature
branch plus a suggested commit message. Commit, push, and draft pull request require an explicitly
approved `finish_mode`; merge, deployment, and worktree cleanup remain separate authorization.
