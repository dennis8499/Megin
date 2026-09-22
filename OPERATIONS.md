# Megin Skills-only operations

This repository distributes a folder of Codex Skills. The Skills are the product and the Markdown
workflow record is the state surface. There is no Plugin manifest, command-line entry point, hook,
MCP service, or Megin-specific controller.

## Installation and discovery

Install all `megin*` folders from `megin-skills.zip` into `$CODEX_HOME/skills/` for user-wide use
(`~/.codex/skills/` by default) or `<repo>/.agents/skills/` for repository-local use. Keep the
folders together. Codex discovers the `SKILL.md` frontmatter and may select a Skill implicitly when
its description matches the task; users may explicitly mention `$megin` or any stage Skill. Restart
Codex if a newly installed Skill does not appear.

The conversational `$skill-installer` can install the same `megin*` folders from this repository's
GitHub repository/path. For a local checkout, extract or copy the folders directly. It installs
Skills only and is not a Megin runtime command.

The canonical source is `.agents/skills/`. `megin/scripts/validate_skills.py` is a static packaging
check only. It is not a workflow runner and is not part of the user interaction model.

## Work record

Create `docs/work/<work-id>/workflow.md` using schema `megin-skills-workflow/v1`. The record binds:

- repository, base branch, base commit, feature branch, merge strategy, branch, and Work ID;
- route, phase, status, and plan version;
- intent, scope, assumptions, risks, and acceptance scenarios;
- approved paths, interfaces, dependencies, commands, evidence, and knowledge scope;
- task ownership, fresh review, verification, user acceptance, feature commit, local merge, delivery,
  blockers, and next action.

Append dated events. Do not overwrite an old approval or review; create a new plan/review version
when scope or the source snapshot changes. Preserve unrelated dirty changes and stop on branch,
scope, or evidence drift.

## Delivery sequence

Use `megin` for the complete route:

1. Explore requirements and source-backed project knowledge without mutation.
2. Define stable behavior scenarios and a dependency-ordered technical plan.
3. Present one exact plan approval for the current Work ID and version.
4. Create the named feature branch from the recorded base commit; implement with one writer and
   outside-in BDD/TDD evidence on that branch.
5. Obtain a fresh, read-only review from a different context.
6. Rerun every approved command and scenario against the reviewed snapshot.
7. Pause for the user's listed manual acceptance response.
8. Review the approved knowledge scope, stage approved paths, and create one feature commit.
9. Confirm the base branch has not advanced and merge the feature branch locally with
   `git merge --no-ff`; verify both parents and content equivalence.

Pure explanations, reviews, and bug diagnosis can end without a delivery record or product
mutation. A bug repair requires a read-only diagnosis first. A changed requirement, interface,
scenario, test, path, or destination returns to planning and requires a new approval.

## Evidence and boundaries

Record commands, exit statuses, raw output paths, snapshots, and source references needed to prove
the result. A skipped, undefined, stale, or parser-only check is not passing evidence. A reviewer
cannot approve its own changes; if no independent reviewer is available, leave the work at
`awaiting_review`. A passing automated verification is not user acceptance.

Knowledge is source-backed and scoped to the approved result. Unsupported or conflicting claims stay
pending. Knowledge review does not stage or commit. Finishing stages only approved files and creates
one feature commit after acceptance, then performs the local `--no-ff` merge. A base-branch advance,
branch mismatch, conflict, or reviewed-snapshot change stops delivery and requires fresh review,
verification, and acceptance. External publication and cleanup are separate authorization.

## Historical material

The working tree keeps only the current Skills source and active delivery records. Completed work,
bug, and knowledge history is recoverable from Git commits; old approvals and design references are
never current authorization. New work must use the Skills-only record and current source snapshot.

## 需求探索材料

`.agents/skills/megin/references/requirements-discovery-protocol.md` 是研究觸發、來源證據、能力覆蓋、
依賴式選題與 planning 交接的共用語義；`requirements.md` 是單一需求主檔，`workflow.md` 只引用
revision、摘要與阻礙。外部來源不可讀時必須保留查證限制，不能以模型記憶補成已確認事實。

常設材料位於 `tests/requirements-discovery/`。執行 `check_materials.py` 與 `test_materials.py` 可驗證
案例 ID、官方來源快照 SHA-256、fixture 與參照；這些命令不執行模型評測，也不會取代人工探索、審查或驗收。
