# Megin Skills-only operations

This repository distributes a folder of Codex Skills. The Skills are the product and the Markdown
workflow record is the state surface. There is no Plugin manifest, command-line entry point, hook,
MCP service, or Megin-specific controller.

## Installation and discovery

Start Codex from the GitLab Group root. The Group root is not a Git repository; each project folder
directly below it is an independent Git Repo. Extract the twelve `megin*` folders from
`megin-skills.zip` into `<Group>/.agents/skills/`, keeping the folders together. Codex reads
repository-local Skills from `$CWD/.agents/skills`; use the Group root as `$CWD`. If a new Skill
does not appear under `/skills`, restart Codex so it rescans. See the
[Codex Skills documentation](https://learn.chatgpt.com/docs/build-skills).

This installation is for Group-root work only. New product workflows do not run from a child Repo
or use a user-wide Megin installation.

The canonical source is `.agents/skills/`. `megin/scripts/validate_skills.py` is a static packaging
check only. It is not a workflow runner and is not part of the user interaction model.
`megin/scripts/quality_gate.py` is a separate read-only evidence check called by the relevant
Skills. It neither executes project tests nor changes the workflow state.

## Work record

Create one central `<Group>/docs/work/<Work ID>/workflow.md` with schema
`megin-skills-workflow/v2`. One Work ID can cover one or several selected direct-child Repos. The
record binds Group root, Repo paths, route, phase, status, plan version, requirements revision,
acceptance scenarios and the quality evidence path. The approved plan and its quality contract bind
each Repo's remote name/URL, base branch and exact remote commit, `feature/<Work ID>`, allowed paths,
check commands with explicit `cwd`, and the delivery mode.

Keep requirements, plan, feature files, evidence, review, verification, acceptance and knowledge
notes under that Work ID. Append dated events. Do not overwrite an old approval or review; create a
new plan/review version when scope or the composite snapshot changes. Preserve unrelated dirty
changes and stop on path, remote, branch, scope, or evidence drift.

## Delivery sequence

Use `megin` for the complete route:

1. Explore requirements and source-backed project knowledge without mutation.
2. Define stable behavior scenarios and a dependency-ordered technical plan.
3. Present one exact plan approval for the current Work ID and version.
4. Recheck and fetch each exact remote base SHA, then create the named feature branch in each Repo;
   implement with one writer and outside-in BDD/TDD evidence on those branches.
5. Obtain a fresh, read-only review from a different context.
6. Rerun every approved command and scenario against the reviewed snapshot.
7. Pause for the user's listed manual acceptance response.
8. Review the approved knowledge scope and stage only approved paths in each Repo.
9. Create a feature commit in every Repo. For one Repo, confirm the remote base, fast-forward the
   clean local base with `git merge --ff-only <confirmed-base-commit>`, then merge locally with
   `git merge --no-ff` and verify both parents and content. For multiple Repos, do not merge base
   branches; record per-Repo commits and provide manual-merge handoff. Preserve partial commits and
   resume the remaining Repo commits.

Pure explanations, reviews, and bug diagnosis can end without a delivery record or product
mutation. A bug repair requires a read-only diagnosis first. A changed requirement, interface,
scenario, test, path, or destination returns to planning and requires a new approval.

## Evidence and boundaries

Record commands, exit statuses, raw output paths, snapshots, and source references needed to prove
the result. A skipped, undefined, stale, or parser-only check is not passing evidence. A reviewer
cannot approve its own changes; if no independent reviewer is available, leave the work at
`awaiting_review`. A passing automated verification is not user acceptance.
For new work, use the [Group v2 quality contract](.agents/skills/megin/references/quality-gates.md).
The approved plan owns required checks, `workflow.md` owns phase and status, and `quality_ref` names
the execution evidence. Capture a composite snapshot and call the helper at
`<Group>/.agents/skills/megin/scripts/quality_gate.py` with `--group-root <Group> --work-id <Work ID>`
and `check --gate review|acceptance|delivery` at the corresponding handoff. Structural success does
not assert that behavior or independent review was correct. List exact Group-relative excluded
process-record paths; all other central work files and every Repo snapshot are protected. Run the
delivery gate after staging so it can compare staged blobs in every Repo with the accepted composite
snapshot and recheck every remote base. On any nonzero result, keep the current phase and record the
reason and next action.
Keep command, reviewer, and acceptance identities and outcomes as nonempty strings, and bind each
one to an exact line in its hashed raw evidence rather than repeating an unchecked summary.

Knowledge is read from each selected Repo and source-backed within that Repo's path space.
Unsupported or conflicting claims stay pending. Knowledge review does not stage or commit. Finishing
stages approved files and creates per-Repo feature commits after acceptance; it performs a local
fast-forward and `--no-ff` merge only when exactly one Repo is selected. Any remote advancement,
branch mismatch, conflict, or reviewed composite-snapshot change stops delivery and invalidates old
acceptance. Push, merge requests, deployment and cleanup are outside the workflow.

## Historical material

New product work uses Group v2 central records and does not migrate or reuse repo-local v1 work
records. Completed historical records in individual Repos are left untouched and never authorize
new work. The Megin source Repo retains its own source and maintenance history.

## 需求探索材料

`.agents/skills/megin/references/requirements-discovery-protocol.md` 是研究觸發、來源證據、能力覆蓋、
依賴式選題與 planning 交接的共用語義；`requirements.md` 是單一需求主檔，`workflow.md` 只引用
revision、摘要與阻礙。外部來源不可讀時必須保留查證限制，不能以模型記憶補成已確認事實。

常設材料位於 `tests/requirements-discovery/`。執行 `check_materials.py` 與 `test_materials.py` 可驗證
案例 ID、官方來源快照 SHA-256、fixture 與參照；這些命令不執行模型評測，也不會取代人工探索、審查或驗收。
