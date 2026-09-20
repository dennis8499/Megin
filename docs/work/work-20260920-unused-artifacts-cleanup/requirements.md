# Requirements: unused local artifact cleanup

## Goal

Remove only clearly obsolete local test leftovers while preserving current work evidence and all
tracked repository content.

## In scope

- Empty root `plugins/` directory.
- Eight stale `.test-run-tmp/v2-test-*` directories named in the Work ID plan.
- Recoverable move to the Windows Recycle Bin.
- Preflight and post-cleanup verification.

## Out of scope

- All tracked product, documentation, archive, binary, workflow, work-record, and knowledge files.
- `.test-run-tmp/work-20260919-installation-fix-*` evidence.
- `.test-run-tmp/megin-skills-extract*` and `.test-run-tmp/megin-skills-package`.
- Permanent deletion, staging, commit, push, deployment, or branch changes.

## Acceptance criteria

1. The exact target allowlist is validated immediately before mutation.
2. Every target is moved to the Recycle Bin, or the operation stops without forced deletion.
3. Protected paths remain present.
4. No tracked product path is added, modified, or deleted by the cleanup.
5. The Skills archive validator and `git diff --check` pass.
