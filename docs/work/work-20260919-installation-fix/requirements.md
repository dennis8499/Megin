# Requirements: Skills-only installation and CI fix

## Goal

Make the Skills-only bundle installable through Codex's supported user-wide and repository-local
locations, and make CI fail closed when the distributable archive or pull-request whitespace checks
are incomplete.

## In scope

- Correct the user-wide installation destination in `README.md` and `OPERATIONS.md` to
  `$CODEX_HOME/skills/` with the `~/.codex/skills/` default.
- Describe `$skill-installer` only for GitHub repository/path installation; local checkouts use
  direct extraction or copying.
- Validate the exact archive entry set and bytes against the canonical README and all 12
  `megin*` Skill trees, including nested files and duplicate-entry rejection.
- Make CI compare whitespace in the actual PR or dispatch commit diff on both supported runners.
- Rebuild `megin-skills.zip` from the corrected source.

## Out of scope

- Restoring the retired Plugin, CLI, hooks, schemas, or old test suites.
- Rewriting historical `docs/work` or `docs/knowledge` records.
- Committing, pushing, merging, deploying, deleting branches, or cleaning worktrees.

## Acceptance criteria

1. A user-wide install instruction points to `$CODEX_HOME/skills/` and states its default; the
   repository-local install remains `<repo>/.agents/skills/`.
2. The archive validator passes only when README plus every canonical `megin*` file is present once
   with identical bytes and no unexpected entry.
3. CI runs the exact archive validation on Linux and Windows.
4. CI's whitespace check receives the PR base-to-head diff, or the current-to-parent diff for
   manual dispatch; a whitespace error causes failure.
5. The corrected archive and source validator agree, and no legacy Plugin/CLI is reintroduced.

## Risks

- The archive is a generated binary artifact and can drift from source unless rebuilt and checked in
  the same snapshot.
- Historical records refer to removed runtime paths; those links are intentionally not migrated in
  this work.
