# Quality evidence and gate boundaries

New work launched from a GitLab Group root uses Group v2. The approved plan is the sole source of required behavior, commands, paths, and delivery mode; `workflow.md` remains the status surface. `quality_ref` points to execution evidence, not another plan or controller. Completed historical v1 records are not retroactively changed.

## Plan and implementation

For each observable result, name the assertion that proves it, its exact command, execution environment, and Repo `cwd`. Split unrelated results rather than claiming one `SCN-*` tag proves all behavior. Include relevant failure, retry, restart, concurrency, and external-dependency checks. Existing meaningful coverage can be reused without manufacturing a red test.

For new behavior, preserve the failing assertion and subsequent passing command with their snapshots and raw output. A compiler error or missing entry point is setup failure, not behavior-red evidence. A passing parser, configuration-value check, mock, or unrelated test is not end-to-end proof. Explain the observable promise and the assertion that would fail if it were absent.

Every approved check has `id`, `kind`, `command`, and `cwd`, where `cwd` is `.` (Group root) or the exact selected Repo path. Bind command evidence to raw lines `Working directory: <cwd>`, `Command: <command>`, and `Exit code: <code>`. Use one check per explicit working directory; do not rely on whichever directory Codex last used.

## Independent review

The reviewer is a different fresh read-only context. Save its actual invocation/source and raw result, not only a writer-authored claim of independence. If no independent reviewer exists, remain `awaiting_review`. Review every target Repo and the protected Group work record; trace each promise to its implementation and assertion. The reviewer must not approve code it wrote.

## Group snapshots and evidence

The approved plan and quality contract are protected with product, tests, configuration, documentation, and distribution content. A Group v2 snapshot hashes each selected Repo's tracked and non-ignored untracked worktree entries, including unstaged content and mode changes; removed paths appear as absent entries. Each entry binds its Git mode and normalized blob identity. A submodule entry binds mode `160000` and its checked-out commit; dirty initialized submodules stop snapshot creation. The snapshot combines those entries with protected files under `docs/work/<Work ID>/`. The aggregate is `product_sha256`; the report also includes each Repo's branch, HEAD, digest, and path count.

Within that Work ID directory, the snapshot excludes only `workflow.md` and the exact Group-relative files predeclared in `process_records`. Plans, feature files, quality contract, executable checks, and fixtures remain protected unless an exact path is an approved process record. Keep a SHA-256 digest for each cited process record. Editing or deleting cited evidence invalidates the citation. Never exclude all of `docs/work/**` or `evidence/**`.

Red evidence points to its failing preimplementation Group snapshot. Green, review, verification, and human acceptance must bind the same aggregate snapshot and approved-contract bytes. A change in any selected Repo or protected Group plan file invalidates later approvals. Never refresh a digest silently to make stale evidence appear current.

## Group v2 contract and evidence

For every new Work ID, the approved plan binds `docs/work/<Work ID>/plan-<version>/quality-contract.json` with schema `megin-quality-contract/v2`. It includes:

- `work_id`, `plan_version`, `delivery_mode` (`local_merge` for exactly one Repo, `feature_handoff` for two or more);
- `repositories`, each with direct-child `repo_path`, configured `remote` and credential-free `remote_url`, `base_branch`, full `base_commit`, `feature_branch`, and Repo-relative `allowed_paths`;
- `checks`, each with unique `id`, `kind` (`test` or `command`), exact `command`, and explicit Group-root-relative `cwd`;
- `process_records`, exact Group-root-relative paths inside `docs/work/<Work ID>/evidence/`, including the `quality_ref` file.

The `workflow.md` uses `megin-skills-workflow/v2` and puts `quality_ref` at `docs/work/<Work ID>/evidence/quality.json`. Evidence uses `megin-quality-evidence/v2`. All Group paths are canonical and contained by the Group root; Repo paths must be direct children and each selected path must itself be a Git root. Every Git operation receives an explicit target Repo.

Evidence records the aggregate `snapshot`, a writer context and source, a `sources` list, each required command result and output, and test executed/failed/skipped counts. Review adds reviewer context/verdict/snapshot/source. Acceptance adds Work ID/version/verdict/snapshot/source. Every cited `path` is Group-root-relative, resolves under this Work ID's evidence directory, and is listed in `process_records`; its SHA-256 and `claims` bind exact one-based source lines. Writer lines contain `- context:` and `- snapshot:`; review has `- context:`, `- verdict:`, `- snapshot:`; acceptance has `- work_id:`, `- version:`, `- snapshot:`, and `- verdict: ACCEPTED`.

## Gate outcomes

- `snapshot`: read and report a Group composite snapshot without changing files.
- `review`: validate selected Repo identities, exact feature branches and approved scope, the writer handoff, every required result and source, and the current aggregate digest. Failure results may be recorded at this handoff; the gate checks completeness, not success. Product paths must not be staged.
- `acceptance`: additionally require all approved commands to pass, nonzero test counts with zero failures and skips, and an independent `APPROVED` review for the same snapshot. Missing output, `blocked`, `not_run`, environment errors, failures, skips, or zero matching tests stop the gate.
- `delivery`: after every accepted product path is staged in each Repo, check the same accepted snapshot, reject unstaged/untracked product paths, and compare staged blobs to the accepted per-Repo digest. Recheck every configured remote URL and run `git ls-remote --exit-code` for every exact base ref; each remote tip must still equal its approved `base_commit`. Confirm the local base has not diverged and each feature branch descends from its approved base. A remote failure, advancement, branch drift, or divergence stops the whole Work ID and invalidates old acceptance.

The delivery result lists every Repo's accepted snapshot and staged paths. One Repo uses `local_merge` and follows the single-Repo fast-forward plus `--no-ff` procedure in [branch-policy.md](branch-policy.md). Several Repos use `feature_handoff`; all feature commits are recorded, no base branch is merged by Megin, and the user receives per-Repo manual-merge details. A partial sequence preserves completed Repo commits and resumes only missing commits.

The helper validates structure, identity, path/digest references, exit codes, numeric test counts, exact Repo bases, and fixed gate transitions. It does not run project commands, prove an assertion covers behavior, or determine whether a reviewer reasoned independently. A structural pass is not proof that the product works.

## Megin source maintenance

The Megin Skills source repository may retain the existing v1 `--repo` quality contract for changes to Megin itself and for historical records. This maintainer path is not an alternate invocation model for new Group product work; public Skills direct users to Group v2 with `--group-root` and `--work-id`.

After each work package, record completed work, fresh checks, remaining uncertainty, and the next action.
