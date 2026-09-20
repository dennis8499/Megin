# Megin workflow: unused local artifact cleanup

- schema: megin-skills-workflow/v1
- work_id: work-20260920-unused-artifacts-cleanup
- repository: C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin
- base_commit: b17ae5c66f4619390b0b2cce42bcbd67160ee8ec
- branch: feat/work-20260919-installation-fix
- route: small
- phase: implementation
- status: blocked
- plan_version: plan-1
- last_updated: 2026-09-20

## Intent and boundaries

Move only the explicitly identified local leftovers to the Windows Recycle Bin: the empty
`plugins/` directory and the eight stale `.test-run-tmp/v2-test-*` directories. Do not modify
tracked product files, the current installation-fix evidence, Skills packaging scratch, historical
work records, canonical knowledge, or Git history. This is a separate Work ID from
`work-20260919-installation-fix`.

The operation is recoverable and must stop before mutation if the exact target manifest, workspace
root, directory type, link attributes, or Git-tracking preconditions drift.

## Acceptance

See [features/cleanup.feature](features/cleanup.feature).

## Plan and approval

Plan version: plan-1. The user explicitly approved implementation in the current conversation with
the exact cleanup scope, target allowlist, Recycle Bin requirement, protected paths, and validation
commands.

Allowed mutation paths:

- `plugins/`
- `.test-run-tmp/v2-test-11852-ddf3011a32d14599ae1234f72c872045/`
- `.test-run-tmp/v2-test-13216-b4cf661e6eec4769a6ce9972213dbcff/`
- `.test-run-tmp/v2-test-13432-5f0d7c997412402ab9c2779ab50408ee/`
- `.test-run-tmp/v2-test-18252-9d57ccde1faa47c1939f2cf202d00b37/`
- `.test-run-tmp/v2-test-19472-0d4dfb86ef87486bbee79370a259d7bc/`
- `.test-run-tmp/v2-test-21036-f78ff95954464629b76a68e70dd1bfad/`
- `.test-run-tmp/v2-test-7828-c68c822c179844a3a3b85968c58adbd4/`
- `.test-run-tmp/v2-test-9940-07efa5204efa403eb61dd4b0a454b335/`

Workflow evidence is allowed under this Work ID. All other product, historical, current-work
evidence, and Skills-package paths are forbidden. No staging, commit, push, deployment, or
canonical knowledge update is authorized.

Commands:

- preflight exact target manifest and protected-path checks
- Windows Recycle Bin move using `Microsoft.VisualBasic.FileIO.FileSystem.DeleteDirectory`
- post-cleanup target/protected-path checks
- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- `git diff --check`
- Git status and tracked-file manifest comparison

Knowledge scope: no-change; this local cleanup does not alter source-backed project knowledge.
Delivery destination: local workspace cleanup with workflow evidence left uncommitted.

## Task ledger

| Task | Dependency | Owner | Status | Evidence |
| --- | --- | --- | --- | --- |
| T1 — Bind Work ID and verify preconditions | — | writer | completed | preflight command output |
| T2 — Move exact targets to Recycle Bin | T1 | writer | blocked | implementation/outcome.md |
| T3 — Verify protected paths and product snapshot | T2 | writer | completed | verification.md |
| T4 — Fresh read-only review and acceptance handoff | T3 | fresh reviewer | blocked | implementation/outcome.md |

## Evidence

The initial preflight ran on 2026-09-20 against base commit
`b17ae5c66f4619390b0b2cce42bcbd67160ee8ec` on branch
`feat/work-20260919-installation-fix`. It confirmed an exact eight-directory target manifest,
an empty non-reparse `plugins/` directory, no tracked target paths, and all protected paths present.
The first two targets were reported as removed by `Microsoft.VisualBasic.FileIO.FileSystem`, but
the local Recycle Bin remained empty and recoverability could not be confirmed. PowerShell 7 and
Windows PowerShell 5.1 both reported that the Recycle Bin API is unsupported for the next target;
Shell `MoveHere` left it unchanged, and native `SHFileOperation(FOF_ALLOWUNDO)` returned
`120 (ERROR_CALL_NOT_IMPLEMENTED)`. The remaining seven targets were preserved.

## Blockers and next action

Blocked: this non-interactive environment does not provide a working Windows Recycle Bin API, and
the Windows computer-use connection exposes no targetable File Explorer window for a safe UI
fallback.
`plugins/` and `v2-test-11852-ddf3011a32d14599ae1234f72c872045` are absent from the workspace but
not visible in the local Recycle Bin; the other seven approved targets remain intact. A user-side
interactive Windows cleanup or a supported Recycle Bin integration is required before T2 can be
completed safely.

## Delivery

Acceptance is not requested because implementation is blocked. No product commit was made; the
cleanup targets are ignored or empty local paths, and workflow evidence remains uncommitted.

## Event log

- 2026-09-20 — requirements/planning — user-approved plan-1 bound to the current branch and exact target allowlist — preflight passed; execute the Recycle Bin move next.
- 2026-09-20 — implementation — Recycle Bin move partially attempted — two targets were reported removed, all further recovery-preserving APIs failed or were unsupported; seven targets remain and the Work ID is blocked.
- 2026-09-20 — verification — Skills archive validation and `git diff --check` passed; protected paths remain present and no product diff exists — await a supported interactive Recycle Bin operation.
- 2026-09-20 — implementation — File Explorer fallback attempted — computer-use inventory exposed no controllable application/window, so no further deletion was attempted.
