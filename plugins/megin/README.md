# Megin

`megin` is a portable Codex plugin for evidence-driven repository delivery. Workflow v3 keeps one behavior contract shared by design, executable Gherkin, TDD, review, and human acceptance; it then promotes verified knowledge and creates one local commit.

New work uses `delivery-run/v3` and the `megin_v3.py` controller. The previous `delivery-run/v2` controller and records remain available only as migration history; v3 never continues an old approval as if it were a current plan.

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
| `finishing-delivery` | After human acceptance, review source-backed knowledge, stage approved paths, and create one local commit. |

## Workflow

1. Explore the repository without mutation, determine whether the request actually asks for a change, and classify it as read-only, small, large, or bug.
2. Prepare a reviewable candidate with a Chat Summary, File Details, stable scenario IDs, executable Gherkin, task boundaries, and human acceptance steps. Small and large changes share one plan approval; only the task decomposition and design depth differ.
3. `approve` is the only plan gate. It creates `feat/<work-id>` from the fetched base and dispatches one writer at a time. A fresh reviewer accepts or returns each task, and repeated identical findings block after three attempts.
4. `verify` runs approved commands and the Gherkin contract, then stops at `awaiting_user_acceptance`. It never commits or updates formal knowledge.
5. `accept` records the human response and exact acceptance version. `finish` then reviews/promotes source-backed knowledge, stages only approved paths, and creates one local commit. Push, merge, and deployment remain outside the plugin.

The plugin does not assume that a target repository contains `.agents/skills`. Resolve the target repository and its own validators or CLI explicitly. Repository-specific contracts remain authoritative for schemas, commands, and knowledge promotion.

## CLI

The portable entry point is `bin/megin` (or `bin/megin.cmd` on Windows). A source checkout can
invoke the Python implementation directly:

```console
<plugin-root>/bin/megin classify --repo <target-repo> --request "<request>"
<plugin-root>/bin/megin init --repo <target-repo>
<plugin-root>/bin/megin doctor --repo <target-repo>
<plugin-root>/bin/megin start --repo <target-repo> --request "<request>"
<plugin-root>/bin/megin approve --repo <target-repo> --work-id <work-id> --confirm
<plugin-root>/bin/megin status --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin verify --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin accept --repo <target-repo> --work-id <work-id> --confirm
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

For a small task, pass the approved scope and test command while starting. The start output is
the review gate; after checking its Chat Summary and File Details, confirm the exact Work ID and
plan version:

```console
<plugin-root>/bin/megin start --repo <target-repo> --request "<request>" \
  --allowed-path src/example.py --test-command "python -m unittest" \
  --workspace-mode current
<plugin-root>/bin/megin approve --repo <target-repo> --work-id <work-id> \
  --response "確認計畫 <work-id> plan-1，依此開始開發。"
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id> \
  --writer-ticket <assignment-ticket> --writer-report <writer-report.json> --writer-complete
<plugin-root>/bin/megin resume --repo <target-repo> --work-id <work-id> \
  --review-verdict APPROVED --reviewer-id fresh-reviewer \
  --review-report <review-report.json>
<plugin-root>/bin/megin verify --repo <target-repo> --work-id <work-id>
<plugin-root>/bin/megin accept --repo <target-repo> --work-id <work-id> \
  --response "驗測通過 <work-id> acceptance-1，同意更新知識並建立本機 commit。"
<plugin-root>/bin/megin finish --repo <target-repo> --work-id <work-id>
```

Large changes use the same single `approve` call after their complete design and Task graph are
reviewed. Bug repairs first require `megin diagnose --command <read-only-oracle> --disposition confirmed|likely
--hypothesis <falsifiable-cause>` and then `start --diagnosis-file <assessment>`. A diagnosis without
that evidence never creates a delivery workspace. Knowledge candidates remain external until
human acceptance, then `finish` promotes only the approved source-backed scope.

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

Approval authorizes only the recorded work identity, behavior contract, scope, acceptance, knowledge update, and local delivery target. Scope drift requires a new plan version and approval. Reviewers stay read-only. Automated verification stops at `awaiting_user_acceptance`; before that gate no knowledge promotion, staging, or commit is possible. `finish` creates one local commit after acceptance and never pushes, merges, deploys, deletes branches, or cleans worktrees. Re-running `megin init` on an existing project repairs the local `.megin/` Git exclude.

The manifest is at `.codex-plugin/plugin.json`; the plugin can be installed through the Codex plugin mechanism or a local marketplace that points at this directory.

## Measuring the workflow

`benchmarks/v3-cases.json` fixes six tasks, three comparison methods, and two runs per task.
Record observations without estimating unavailable token usage:

```console
python <plugin-root>/scripts/metrics.py record --output metrics.jsonl \
  --task small-1 --method megin-v3 --run 1 --acceptance-passed \
  --human-minutes 12 --repeat-questions 1 --rework-count 0
python <plugin-root>/scripts/metrics.py report --input metrics.jsonl
```

The report keeps acceptance quality, deviations, rework, regressions, human time, repeated
questions, test reruns, elapsed time, and available token usage separate so a lower cost cannot
hide a lower acceptance quality.
