# Baseline and cleanup manifest

- captured: 2026-09-20
- repository: `C:/Users/denni/OneDrive/Desktop/新增資料夾/Megin`
- branch: `feat/work-20260919-installation-fix`
- base_commit: `1834c921b87462ef0ff5109de299d2d7f42fae52`
- worktrees: one registered worktree at the repository root

## Active records carried forward

- `work-20260919-installation-fix`: implementation complete, awaiting independent review; no claim
  of approval or acceptance is reused.
- `work-20260920-unused-artifacts-cleanup`: blocked because this non-interactive environment could
  not provide a working Windows Recycle Bin operation; this plan authorizes permanent deletion of
  the newly confirmed scratch scope instead.

## Local branches at baseline

The current feature branch contains the six commits missing from local `main`. The following local
branches are all behind the current feature branch and will be deleted only after ancestry is checked
against `main`:

- `delivery/work-20260912-bug-closure-policy-dbcbce13`
- `delivery/work-20260912-bug-remediation-0e0ea628`
- `delivery/work-20260915-sdlc-transformation-v2-c6af1272`
- `delivery/work-20260915-sdlc-transformation-v2-delivery`
- `delivery/work-20260915-sdlc-transformation-v2-impl`
- `delivery/work-20260916-delivery-revision-gap`
- `delivery/work-20260916-natural-language-sdlc-v2`
- `delivery/work-20260916-natural-language-sdlc-v2-r2`
- `delivery/work-20260917-megin-project-rename-e90fffe6`
- `feat/megin-ux-superpowers`
- `main`

`main` is retained as the integration destination; the other ten names are cleanup candidates after
fast-forward integration. No remote branch is in scope.

## Retained product manifest

- `.agents/skills/megin/`
- `.agents/skills/megin-behavior-contract/`
- `.agents/skills/megin-bug-diagnosis/`
- `.agents/skills/megin-code-review/`
- `.agents/skills/megin-finishing-delivery/`
- `.agents/skills/megin-human-acceptance/`
- `.agents/skills/megin-implementation-execution/`
- `.agents/skills/megin-project-knowledge/`
- `.agents/skills/megin-requirements-discovery/`
- `.agents/skills/megin-technical-planning/`
- `.agents/skills/megin-test-driven-development/`
- `.agents/skills/megin-verification-before-completion/`
- `README.md`
- `OPERATIONS.md`
- `.github/workflows/knowledge-portability.yml`
- `.gitignore`
- `.gitattributes`
- `megin-skills.zip`
- `docs/work/work-20260920-skills-cleanup-integration/`

## Retired product and local targets

- `.agents/skills/_shared/`
- `.agents/skills/writing-great-skills/`
- `tgrep.exe`
- `THIRD_PARTY_NOTICES.md`
- all prior `docs/work/*`, `docs/bugs/**`, and `docs/knowledge/**`
- all contents of `.test-run-tmp/` after the preserved checks are copied into this Work ID
