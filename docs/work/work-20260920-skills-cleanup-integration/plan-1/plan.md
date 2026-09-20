# Plan 1: Skills cleanup and local branch integration

## Approved design

Keep only the current twelve Megin Skills plus installation, operations, CI, archive validation, the
exact archive, and the new delivery record. Remove the retired implementation and historical records
after carrying forward their relevant status. Remove local scratch only after a literal-path preflight.

## Dependency-ordered work packages

1. Bind the current branch, baseline, active-record statuses, local branch list, and cleanup manifest.
2. Preserve the ZIP negative and CI whitespace scripts inside this Work ID, and define executable
   scenarios for package integrity and final repository shape.
3. Update README/OPERATIONS/.gitignore/.gitattributes to match the retained product, then remove the
   exact retired paths and scratch directories.
4. Rebuild the archive from the retained twelve Skills and rerun positive, negative, CRC, whitespace,
   manifest, and protected-path checks.
5. Obtain an independent fresh review of the complete snapshot; correct only findings within scope.
6. Show the approved manual acceptance scenarios, record the response, make one local commit, then
   fast-forward local `main` and delete only local branches confirmed as ancestors.

## Allowed and forbidden paths

Allowed: current `.agents/skills/megin*` directories, `README.md`, `OPERATIONS.md`,
`.github/workflows/knowledge-portability.yml`, `.gitignore`, `.gitattributes`, `megin-skills.zip`,
the new Work ID directory, and the exact retired paths listed in the cleanup outcome. Forbidden:
`.git`, sibling directories, remote refs, and any unlisted product path.

## Commands and evidence

Run the validator, the two preserved Python checks, ZIP entry/CRC inspection, `git diff --check`, and
branch/worktree/tracked-manifest checks on the reviewed snapshot. Record output paths and hashes in
`verification.md`; record no-change for canonical knowledge.

## Delivery

Leave the feature branch uncommitted until review, automated verification, and user acceptance pass.
Create one local commit, fast-forward local `main` from it, verify ancestry, and delete only merged
local branches. Do not push or remove remote branches.
