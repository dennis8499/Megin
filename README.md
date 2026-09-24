# Megin Skills-only workflow

Megin is a reusable set of Codex Skills for evidence-driven software delivery. Install the Skills
once, then work through normal conversation. There is no Megin Plugin, Megin command, hook, MCP
server, or dedicated workflow controller to install or run.

Start Codex at the GitLab Group root. Every direct-child project folder is an independent Git repo;
the Group root itself is not a repo. One Work ID may cover several repos and keeps one central
requirements, plan, review, verification, and acceptance record under `<Group>/docs/work/`.

The bundle keeps a complete delivery path:

`requirements → behavior contract and plan → one plan approval → per-repo feature branches → BDD/TDD implementation → fresh review → automated verification → human acceptance → feature commits → local merge (one repo) or manual merge handoff (multiple repos)`

The workflow is driven by Skills and a readable `<Group>/docs/work/<work-id>/workflow.md` record. Git,
repository search, project tests, and each project's own tools remain available as ordinary tools.
The Skills bundle also includes a small read-only quality gate helper. It checks structural evidence
at review, acceptance, and delivery handoffs; it does not run a workflow or judge code behavior.

## 需求探索

面對陌生外部框架、版本差異或「完整支援」等廣泛需求時，需求探索會先依
`.agents/skills/megin/references/requirements-discovery-protocol.md` 查證必要來源，建立
`SRC-*`、`CAP-*`、`Q-*` 與 `SCN-*` 的能力和決策覆蓋，再一次提出一個前提已具備且影響最高的問題。
上游能力、整合能力與應用層需求分開記錄；重大未知、矛盾或會改變驗收的延後事項會留在
`phase: requirements`，不會因題數或 `ready_for_planning` 欄位而提前交接。

`tests/requirements-discovery/` 提供官方來源摘要、最小 fixtures、案例、評分規準與結構檢查器。
檢查器只驗證材料參照與雜湊，不代表模型對話行為已完成評測；後續新舊模型比較需另行保存對話、工具
順序、檔案差異及獨立評閱結果。

## Install the Skills

Download `megin-skills.zip` from this repository's release or checkout. The archive contains the
following folders at its top level:

`megin`, `megin-requirements-discovery`, `megin-technical-planning`, `megin-bug-diagnosis`,
`megin-project-knowledge`, `megin-behavior-contract`, `megin-implementation-execution`,
`megin-test-driven-development`, `megin-code-review`, `megin-verification-before-completion`,
`megin-human-acceptance`, and `megin-finishing-delivery`.

Extract the twelve `megin*` folders together into `<Group>/.agents/skills/`. Keep existing `.agents`
files if the Group already has Skills. The canonical source in this Megin repository is
`.agents/skills/`; the archive is distributed for installation at the Group root. Codex scans
repository-local Skills under `$CWD/.agents/skills`; start Codex with `$CWD` set to the Group root so
the installed Skills are discoverable. If they do not appear in `/skills`, restart Codex to rescan.
See [Codex Skills documentation](https://learn.chatgpt.com/docs/build-skills).

Keep all `megin*` directories together because the stage Skills share references from `megin`.
Install this bundle at the Group root; it does not create a single-repo workflow.

## Use it from conversation

Explicit invocation names the Skill while Codex is running at the Group root:

- `$megin 幫我新增登入功能` starts the complete workflow.
- `$megin-code-review 檢查目前的修改` performs a fresh, read-only review.
- `$megin-bug-diagnosis 分析這個錯誤` diagnoses without changing product files.

Implicit invocation works when the task matches a Skill description. Say “新增功能”、“修正錯誤”、
“規劃這個變更”、“檢查目前修改” or the equivalent English request and Codex can select the
appropriate Skill. A description match is a routing hint; it does not bypass approval, review, or
acceptance gates.

To continue work, say “繼續上次的 Megin 工作”. The Skill reads `<Group>/docs/work/*/workflow.md`, resumes
the only active Work ID, or lists active IDs when there is more than one. A retained work record is
the current state surface; completed historical records are available through Git history and are
never reused as current authorization.

## Workflow rules

The first pass is read-only. Megin selects only Group direct-child Git repos identified by the
request, then reads each selected Repo's own instructions, branch, status, relevant code, tests, and
source-backed knowledge. If the Repo is missing or ambiguous, it asks which one. Git commands always
name the target Repo; paths outside the Group, nested repos, and symlink escapes are rejected.
Existing central Work ID records are read at the Group root. A request is classified
as read-only, small, large, or bug. A suspected bug is reproduced and assessed before repair; an
explanation of a bug ends with evidence and does not silently become a fix.

Changes have one plan approval. The central approved plan binds selected Repo(s), each remote URL,
exact remote base SHA, `feature/<Work ID>`, allowed paths, command working directories, behavior
scenarios, tests, knowledge scope, and delivery mode. After approval, one writer works in each
recorded feature branch; base branches remain unchanged until acceptance.
BDD/TDD evidence and a different fresh reviewer are required before automated verification.
Verification runs every approved command against the reviewed snapshot and then pauses at
`awaiting_user` for the listed manual acceptance scenarios.
For new change work, [quality evidence rules](.agents/skills/megin/references/quality-gates.md)
bind observable assertions, raw command output, the approved snapshot, and reviewer provenance.
A compile error alone is setup evidence, and required tests that fail, are blocked, match zero
tests, or are skipped do not qualify as passing verification. The read-only helper installed at
`<Group>/.agents/skills/megin/scripts/quality_gate.py` checks these recorded conditions with
`--group-root <Group> --work-id <Work ID>`; the independent
reviewer still judges whether the tests prove the promised behavior.
The approved quality contract names every excluded process record exactly. At delivery, the helper
compares the staged Git blobs with the user-accepted product digest and rejects remaining unstaged
product paths. Structured command, review, and acceptance outcomes also point to the exact matching
lines in their hashed raw sources.

After the user names the Work ID and acceptance version, Megin reviews only the approved,
source-backed knowledge scope, stages only approved paths in each feature branch, and creates one
feature commit per Repo. For one Repo, it confirms the remote base SHA, fast-forwards the clean local
base, and merges with `git merge --no-ff`; for multiple Repos it makes no base merges and provides a
manual-merge handoff for every feature commit. Push, pull requests, deployment, branch deletion, and
worktree cleanup are outside this workflow.

The shared Git rules are in `.agents/skills/megin/references/branch-policy.md`. If any remote base
advances, a reviewed composite snapshot changes, or a conflict occurs, Megin preserves the state and
requires the baseline to be reconfirmed before fresh review, verification, and acceptance. In a
multi-repo task, partial feature commits are retained and remaining Repo commits resume later.

## Work records

Each work item uses `<Group>/docs/work/<work-id>/workflow.md` with schema
`megin-skills-workflow/v2`. Requirements, one shared plan, feature files, evidence, review,
verification, acceptance, and knowledge notes stay under that Work ID. Its quality contract binds
each Repo's remote, base commit, feature branch, allowed paths, and check command/`cwd`. One-repo
delivery records its feature and merge commits; multi-repo delivery records every feature commit and
manual-merge handoff. See [the workflow-record contract](.agents/skills/megin/references/workflow-record.md).

Do not put secrets in a record. When a repository has a formal knowledge or test evidence contract,
follow that contract and record the source path, command, result, and digest it requires.

## Verify the bundle

The repository's CI checks Skill frontmatter, implicit invocation metadata, package completeness,
archive contents, and removal of legacy Megin runtime references. The local development validator is
`.agents/skills/megin/scripts/validate_skills.py`; it checks the bundle but does not run a workflow.

The release archive is `megin-skills.zip`. It is assembled from the repository's canonical
`.agents/skills/megin*` folders, so the archive and source share one maintenance path.

## From the old installation

If an older Megin Plugin or command is installed in Codex, disable that installation before using
the Skills-only workflow. New product work uses only the Group v2 record format and does not migrate
or reuse repo-local v1 records. Existing `Test` and `Test2` histories are not changed. Old approvals
and design references do not authorize new work.
