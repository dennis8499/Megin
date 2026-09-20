# Requirements: Skills cleanup and local branch integration

## Goal

Leave a small, self-contained Megin repository that distributes the current twelve Skills and the
documents and validation needed to install and maintain them. Complete the pending cleanup and
installation work, preserve honest evidence, and integrate the result into local `main`.

## In scope

- Keep the twelve current `megin*` Skill directories, README, operations documentation, CI workflow,
  archive validator, exact archive, and this Work ID record.
- Remove retired Skills support files, obsolete tgrep tooling and notice, historical work/bug/knowledge
  records after recording their status, and `.test-run-tmp` scratch.
- Rebuild and validate `megin-skills.zip` from the retained source.
- Commit locally, fast-forward local `main`, and remove local branches proven to be merged.

## Out of scope

- Remote pushes, pull requests, remote branch deletion, deployment, sibling directories, global
  installations, and `.git` internals.
- Claiming independent review or human acceptance until those gates actually occur.

## Acceptance criteria

1. The retained source has exactly twelve Megin Skills and their metadata passes the validator.
2. The archive has exactly the source manifest and byte content; missing, extra, duplicate, and drifted
   archives fail the negative checks.
3. Retired paths and local scratch are absent, or any inaccessible exact paths are documented as a
   blocker without an unsafe broad deletion.
4. Documentation no longer promises historical files that were removed.
5. A fresh review and user acceptance cover the same snapshot before the local commit.
6. Local `main` contains the cleanup commit by fast-forward and no unmerged local branch remains.
