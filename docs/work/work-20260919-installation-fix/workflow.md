# Megin workflow: Skills-only installation and CI fix

- schema: megin-skills-workflow/v1
- work_id: work-20260919-installation-fix
- repository: C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin
- base_commit: e5ba5fa097d73910fc371af5a4f9f51b927e64d8
- branch: feat/work-20260919-installation-fix
- route: small
- phase: review
- status: awaiting_review
- plan_version: plan-2
- last_updated: 2026-09-20

## Intent and boundaries

The existing staged snapshot moves Megin to a Skills-only distribution. This plan fixes the
installation documentation, makes the release archive exact and source-backed, and makes CI check
the actual pull-request diff. The legacy Plugin/CLI, old schemas and tests, and historical work and
knowledge records remain out of scope.

The pre-existing staged snapshot is preserved. This work adds only the correction delta described in
plan-2; it does not reset, restage, commit, or publish anything.

## Acceptance

See [requirements.md](requirements.md) and [features/skills-installation.feature](features/skills-installation.feature).

## Plan and approval

Plan version: plan-2. The user explicitly approved implementation of the Skills-only installation
and CI correction plan in the current conversation. Allowed product paths are `README.md`,
`OPERATIONS.md`, `.agents/skills/megin/scripts/validate_skills.py`,
`.github/workflows/knowledge-portability.yml`, and `megin-skills.zip`. Workflow evidence paths
under this Work ID are also authorized. Legacy Plugin/CLI paths and historical `docs/work` and
`docs/knowledge` records are forbidden.

Knowledge scope: no canonical knowledge promotion. Source-backed inputs are the local
`skill-installer` contract, the current Skills-only README/operations contract, and the current
workflow/validator source; record the result as `no-change`.

Focused commands:

- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- isolated negative archive checks for missing, extra, duplicate, and byte-drift entries
- `git diff --check` against the PR base/head or dispatch parent

Full commands:

- the same validator and negative checks on Windows and Linux CI runners
- fresh read-only review of the complete current snapshot

Delivery destination: leave the verified product diff uncommitted and await human acceptance.

## Task ledger

| Task | Dependency | Owner | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 — Bind plan-2 record and scenarios | — | writer | completed | this workflow, requirements, feature |
| T2 — Correct installation documentation | T1 | writer | completed | README.md, OPERATIONS.md |
| T3 — Add exact archive validation | T1 | writer | completed | validate_skills.py, negative checks |
| T4 — Repair cross-platform CI checks | T2, T3 | writer | completed | knowledge-portability.yml |
| T5 — Rebuild archive and verify snapshot | T2, T3, T4 | writer | completed | megin-skills.zip, implementation/outcome.md |
| T6 — Fresh independent review | T5 | fresh reviewer | blocked | independent reviewer is not available in this session |

## Evidence

The earlier `.test-run-tmp` reports are stale: they approve a different snapshot containing the
retired `plugins/megin` paths and are not reused. Fresh command output and the final review report
will be recorded under this Work ID or in ignored test output with a path and digest.

## Blockers and next action

Implementation is complete. The required fresh independent read-only reviewer is unavailable in
this session; self-review cannot satisfy T6, so the Work ID remains `awaiting_review`.

## Delivery

Acceptance is not yet requested. No knowledge promotion, staging, commit, push, merge, deployment,
or cleanup is authorized.

## Event log

- 2026-09-20 — implementation — user-approved plan-2 bound to the current branch and staged baseline — implemented documentation, validator, archive, and CI corrections; awaiting fresh review.
- 2026-09-20 — review — writer read-only self-check passed focused evidence, but independent reviewer capability was unavailable — remain awaiting_review.
