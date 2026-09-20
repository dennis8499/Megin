# Plan 2: Skills-only installation and CI fix

## Approved scope

Keep the current Skills-only migration. Modify only the installation documentation, Skills
validator, portability workflow, generated Skills archive, and this Work ID's evidence. Do not
restore the old Plugin/CLI or rewrite historical records.

## Work packages

1. Update README and OPERATIONS with the supported `$CODEX_HOME/skills/` user-wide root, its
   default, the repository-local root, and the GitHub-only `$skill-installer` route.
2. Extend `validate_skills.py` with an optional archive argument and exact manifest/content checks:
   README plus all files recursively under the 12 expected Skill directories; reject duplicates,
   missing entries, unexpected entries, and SHA-256 byte drift.
3. Update CI to fetch enough history for a real base/head diff, invoke the same exact archive
   validator on Linux and Windows, and remove subset/count-only archive assertions.
4. Rebuild `megin-skills.zip`, run focused positive and negative checks, and record fresh evidence.

## Allowed paths

- `README.md`
- `OPERATIONS.md`
- `.agents/skills/megin/scripts/validate_skills.py`
- `.github/workflows/knowledge-portability.yml`
- `megin-skills.zip`
- `docs/work/work-20260919-installation-fix/**`

## Verification and handoff

The writer must leave the changes uncommitted, run the approved commands on the current snapshot,
and hand off to a different read-only reviewer. Verification must use the same snapshot as review;
human acceptance remains required before staging or commit.
