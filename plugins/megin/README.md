# Megin

`megin` is a portable Codex plugin for evidence-driven repository delivery. It adapts the amount of process to the work, keeps approval tied to an immutable scope, delegates implementation to one authorized writer, and requires a fresh read-only review before delivery.

This implementation targets Megin **0.3.0** and keeps `delivery-run/v2` state compatible with older records that do not contain the new workspace and finish fields.
When those fields are absent, resume preserves the historical worktree and commit behavior; it never rewrites the old candidate or moves its workspace.

The workflow follows the task-sized explore/design/implement/review shape described in
[obra/superpowers' basic workflow](https://github.com/obra/superpowers#the-basic-workflow),
while retaining this repository's Work ID, evidence, approval, and v1 compatibility contracts.

## Included skills

| Skill | Responsibility |
| --- | --- |
| `megin-orchestrator` | Classify work, route phases, bind approvals, track identity, and resume safely. |
| `requirements-discovery` | Explore the target repository and produce an evidence-linked WHAT candidate. |
| `technical-planning` | Produce the approved HOW, work packages, commands, and scope. |
| `bug-diagnosis` | Reproduce suspected defects without mutation before repair. |
| `project-knowledge` | Search, review, and promote only source-backed knowledge updates. |
| `implementation-execution` | Dispatch one writer, preserve TDD evidence, and hand off for review. |
| `test-driven-development` | Run the behavior red → green → refactor loop and preserve test evidence. |
| `code-review` | Review the approved snapshot for requirements, quality, tests, scope, and knowledge. |
| `verification-before-completion` | Re-run required obligations and prove the completion state from fresh evidence. |
| `finishing-delivery` | Deliver a verified unstaged diff by default, or explicitly commit locally and optionally publish a draft pull request. |

## Workflow

1. Explore the repository without mutation, determine whether the request actually asks for a change, and classify it as read-only, small, large, or bug.
2. Prepare a reviewable candidate. Small tasks use one integrated approval; large changes use requirements and technical-plan gates.
3. After approval, new work uses the current checkout by default: Megin switches from the configured main/master branch to `feat/<work-id>`. Use `--workspace-mode worktree` when isolation is explicitly requested. Allow only one writer at a time, then obtain a fresh independent review.
4. Review authorized knowledge updates alongside the product snapshot, then automatically promote them when the repository contract permits it; retain source references and digests.
5. Verify the current snapshot and distinguish local verification, unstaged delivery, publication pending, and draft-PR-created states.
6. The default finish leaves the approved feature branch with an unstaged diff and a suggested commit message. `--finish-mode commit` creates only a local commit; `--finish-mode draft-pr` authorizes push and draft-PR creation.
   An explicit `--publish` is still required when retrying a previously approved publication handoff. After an unstaged delivery, changing that destination requires a new `resume` approval for the current snapshot.
7. `--workspace-mode worktree` can start from a dirty source checkout because it reads the approved base into an isolated worktree. `current` mode still requires a clean checkout.

The plugin does not assume that a target repository contains `.agents/skills`. Resolve the target repository and its own validators or CLI explicitly. Repository-specific contracts remain authoritative for schemas, commands, and knowledge promotion.

## CLI

The portable entry point is `bin/megin` (or `bin/megin.cmd` on Windows). A source checkout can
invoke the Python implementation directly:

```console
<plugin-root>/bin/megin classify --repo <target-repo> --request "<request>"
<plugin-root>/bin/megin init --repo <target-repo>
<plugin-root>/bin/megin doctor --repo <target-repo>
<plugin-root>/bin/megin start --repo <target-repo> --request "<request>"
<plugin-root>/bin/megin status --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin finish --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin status --repo <target-repo> --work-id <work-id> --human
<plugin-root>/bin/megin migrate --repo <target-repo> --dry-run
<plugin-root>/bin/megin migrate --repo <target-repo>
python -X utf8 -B <plugin-root>/scripts/validate.py
```

`classify` and `start` stop at `needs_clarification` when intent or scope is unresolved; they do not create a delivery run. Read-only exploration can pass a repository- and HEAD-bound `megin-routing/v1` record with `--routing-file`. The record adds evidence but never grants write authority.

Use `MEGIN_STATE_ROOT` to select a persistent state directory outside the target repository.
The CLI stores only redacted command evidence and digests in that directory; credentials are
never written to project configuration or runtime state.

`migrate` is the one-time transition for repositories that still have `.sdlc/config.json` or
legacy state. It validates source integrity, stages the converted files, rewrites Megin-owned
paths and schemas, refreshes derived digests, then publishes atomically. Use
`--from-state-root` and `--to-state-root` for custom locations. Successful migrations retain
`.sdlc.migrated-<digest>` and a state backup; `--dry-run` makes no changes and a repeat run
returns `already_migrated`. Normal commands never read the old configuration and do not expose
an `sdlc` alias.

For a small task, pass the approved scope and test command while starting, then record the
integrated approval and the independent results:

```console
<plugin-root>/bin/megin start --repo <target-repo> --request "<request>" \
  --allowed-path src/example.py --test-command "python -m unittest" \
  --workspace-mode current --finish-mode unstaged \
  --approve --approval-ref user:approval
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id> \
  --writer-ticket <assignment-ticket> --writer-report <writer-report.json> --writer-complete
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id> \
  --review-verdict APPROVED --reviewer-id fresh-reviewer \
  --review-report <review-report.json>
<plugin-root>/bin/megin finish --repo <target-repo> --work-id <work-id>
```

Large changes use `--approve requirements` and `--approve plan` on separate `resume` calls.
Bug repairs first require `megin diagnose --command <read-only-oracle> --disposition confirmed|likely
--hypothesis <falsifiable-cause>` and then `start --diagnosis-file <assessment>`. A diagnosis without
that evidence never creates a delivery workspace. Knowledge updates require a separate
`megin-knowledge-review/v1` report passed with `--knowledge-report`.

For large work, optional `--requirements-file` and `--plan-file` inputs are copied as redacted,
content-digested candidate bundles in the external state directory. The state exposes one-time
writer and fresh-review tickets; callers that identify a writer must return its `--writer-id`
with the matching `--writer-ticket`. A task-specific dispatch file can be passed at start with
`--work-package-file <packages.json>`; its acceptance, interfaces, path boundaries, dependency
order, and focused/related/full commands are included in the approval digest. Writer and Reviewer
results must conform to the `megin-writer-report-v1`, `megin-review-report-v1`, and
`megin-knowledge-review-v1` schemas under `schemas/`; a CLI flag without the corresponding
snapshot-bound report is rejected.

Each reviewer test-evidence item also carries its approved command, redacted output
path, byte length, SHA-256, and input/output snapshot. The controller copies that output
under the Work ID's persistent state and rejects missing, reused, stale, or drifted evidence.

If a deferred knowledge conflict changes source bytes after the product commit, the next
`knowledge-reviewed` transition creates a new deterministic candidate, binds a fresh review report
and verification snapshot, and only then promotes the resolved bytes. The product commit remains
anchored to its original product snapshot during this recovery.

## Safety boundaries

Approval authorizes only the recorded work identity, scope, acceptance, knowledge update, and publication target. Scope drift requires re-planning and re-approval. Reviewers stay read-only. The normal finishing path records a verified unstaged diff and commit suggestion; `commit` creates a local commit without an implicit push, while `draft-pr` publishes to the approved remote. An explicit `--publish` retries only the authorized publication handoff. If publication lacks an approved remote or credentials, it remains `publication_pending` until the destination is configured and approved. Re-running `megin init` on an existing project repairs the local `.megin/` Git exclude. Merge, deployment, branch deletion, worktree cleanup, and issue management are outside this plugin.

The manifest is at `.codex-plugin/plugin.json`; the plugin can be installed through the Codex plugin mechanism or a local marketplace that points at this directory.
