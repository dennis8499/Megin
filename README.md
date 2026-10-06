# Megin Skills-only workflow

Megin is a reusable set of Codex Skills for evidence-driven software delivery. Install the Skills
once, then work through normal conversation. There is no Megin Plugin, workflow command, hook, MCP
server, or lifecycle controller to install or run; the small helper scripts validate records and
workspace ownership.

Start Codex at the GitLab Group root. Every direct-child project folder is an independent Git repo;
the Group root itself is not a repo. One Work ID may cover several repos and keeps one central
requirements, plan, review, verification, and acceptance record under `<Group>/docs/work/`.

The bundle keeps a complete delivery path:

`requirements → behavior contract and plan → one plan approval → per-repo feature branches → BDD/TDD implementation → fresh review → automated verification → human acceptance → mode-specific delivery`

## Megin 0.3.0

Requirements discovery inventories every valid direct-child Repo in the Group, records an evidence-backed disposition for each, and treats a named Repo as a feature clue. Only Repos that need changes enter the approved implementation plan and handoff; unchanged Repos remain in the requirements inventory without a feature branch or commit.

The release adds permanent multi-Repo discovery fixtures and static contract checks. These checks validate the materials and fixture behavior; model evaluation has not been run.

## Delivery modes

The approved plan fixes one delivery mode before implementation. Each mode retains the same review, verification, human acceptance, and accepted-snapshot requirements.

| Mode | Repo scope | Local commit and merge owner | Completion |
| --- | --- | --- | --- |
| `local_merge` | One Repo | Megin commits the accepted feature, fast-forwards the clean local base to the approved remote base SHA, then integrates the feature with `git merge --no-ff`. | Megin passes the completion gate, records the result, and releases the Group lock. |
| `feature_handoff` | Two or more Repos | Megin commits each accepted feature in the approved dependency order; it leaves base branches unmerged and records the ordered manual-merge handoff. | Megin verifies every feature commit, records the completion result, and releases the Group lock. |
| `gitlab_mr` | One or more Repos | After acceptance Megin prepares the native staged-content handoff and stops. GitlabWorkSpace takes the same Work ID lock and commits only the accepted index contents. | GitlabWorkSpace validates every commit and saves local completion before releasing the lock. Push and MR are separate follow-up actions using those saved commits. |

For an uncertain remote result in `gitlab_mr`, reconcile GitLab before retrying; do not push a different commit or create another MR for the same handoff. See [the native delivery contract](.agents/skills/megin/references/gitlab-delivery.md).

The workflow is driven by Skills and a readable `<Group>/docs/work/<work-id>/workflow.md` record. Git,
repository search, project tests, and each project's own tools remain available as ordinary tools.
The Skills bundle also includes small helpers for frozen Group settings, Skills fingerprints,
exclusive Group ownership, and read-only quality gates. They validate records and review, acceptance,
delivery, and completion evidence; they do not run product commands or advance workflow state.

## 需求探索

Megin 的需求探索 Scope 固定涵蓋目前 Group 根目錄下所有有效的直屬本地 Git Repo，包括尚未對應 GitLab 的 Repo。Repo 名稱只是功能線索，未指定 Repo 時不會先詢問要分析哪個 Repo；每個 Repo 都會在需求主檔中列出用途、來源、跨 Repo 關係及「需要改動／無需改動／待查證」判定。

面對陌生外部框架、版本差異或「完整支援」等廣泛需求時，需求探索會先依
`.agents/skills/megin/references/requirements-discovery-protocol.md` 查證必要來源，建立
`SRC-*`、`CAP-*`、`Q-*` 與 `SCN-*` 的能力和決策覆蓋，再一次提出一個前提已具備且影響最高的問題。
上游能力、整合能力與應用層需求分開記錄；重大未知、矛盾或會改變驗收的延後事項會留在
`phase: requirements`，不會因題數或 `ready_for_planning` 欄位而提前交接。

需求探索包含每個 Repo，交付集合只包含確實需要實際改動的 Repo；無需改動的 Repo 留在需求 Scope，不建立 feature branch、提交或 handoff 項目。相容性影響與必要檢查記在需求及計畫，並依核准的改動集合安排。選填的 `.megin/group.json` 可設定 remote 與 base branch，但不會限縮需求探索的 Repo 清單。

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

The first pass is read-only. Megin inventories every valid Group direct-child Git Repo, then reads
each Repo's own instructions, purpose, branch, HEAD, status, relevant code, tests, and source-backed
knowledge. A named Repo is a feature clue, not a scope filter; if a name is missing or ambiguous,
Megin asks about the product behavior after assessing the complete inventory. Git commands always
name the target Repo; paths outside the Group, nested repos, and symlink escapes are rejected.
The requirements master records the full Repo inventory and a sourced change/no-change/research
disposition. `workflow.repositories`, the approved quality contract and handoff contain only Repos requiring actual changes.
Unchanged Repos stay in the requirements inventory without a feature branch, commit or handoff item; compatibility checks are recorded as obligations of the approved change set. Existing central Work ID records are read at the Group root. A request is classified
as read-only, small, large, or bug. A suspected bug is reproduced and assessed before repair; an
explanation of a bug ends with evidence and does not silently become a fix.

Changes have one plan approval. The central approved plan binds selected Repo(s), each remote URL,
exact remote base SHA, `feature/<Work ID>`, allowed paths, command working directories, behavior
scenarios, tests, knowledge scope, and delivery mode. After approval, one Group writer works
sequentially across the selected feature branches; base branches remain unchanged until acceptance.
An optional `<Group>/.megin/group.json` provides remote/base defaults and per-Repo overrides without
limiting Repo selection. Freeze each resolved value and its source in the approved plan. Before
creating feature branches, Megin claims an exclusive Group lock and checks the Work ID and writer
before every product write; the lock remains through review, verification, acceptance, and blocked states.
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

Every new plan binds a reproducible SHA-256 over the twelve installed Skills. A changed fingerprint
stops resumption and requires a new approved plan plus fresh review, verification, and acceptance.
The multi-Repo plan records dependency order, required compatibility checks, and partial-delivery
instructions. `completion` verifies actual feature commit trees and, for one Repo, the local merge
parents and content before the workflow can become complete and release its Group lock.

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

Each new work item uses `<Group>/docs/work/<work-id>/workflow.md` with schema
`megin-skills-workflow/v3`. Requirements, one shared plan, feature files, evidence, review,
verification, acceptance, and knowledge notes stay under that Work ID. Its quality contract binds
each Repo's remote, base commit, feature branch, allowed paths, resolved settings, Skills fingerprint,
and check command/`cwd`. One-repo delivery records its feature and merge commits; multi-repo delivery
records every feature commit and ordered manual-merge handoff. Completed v1/v2 history stays unchanged;
unfinished v1/v2 Group work requires an explicitly approved v3 plan. See [the workflow-record
contract](.agents/skills/megin/references/workflow-record.md).

Do not put secrets in a record. When a repository has a formal knowledge or test evidence contract,
follow that contract and record the source path, command, result, and digest it requires.

## Verify the bundle

The repository's CI checks Skill frontmatter, implicit invocation metadata, package completeness,
archive contents, and removal of legacy Megin runtime references. The local development validator is
`.agents/skills/megin/scripts/validate_skills.py`; it checks the bundle but does not run a workflow.
Rebuild the distributable with `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py
--build-archive megin-skills.zip`, then validate it with `--archive megin-skills.zip`. The builder
uses sorted entries, a fixed timestamp, normalized `100644` modes, and excludes Python caches.
It rejects symlinks in the package README and Skill trees so external file contents cannot enter
the distributable.

The release archive is `megin-skills.zip`. It is assembled from the repository's canonical
`.agents/skills/megin*` folders, so the archive and source share one maintenance path.

## From the old installation

If an older Megin Plugin or command is installed in Codex, disable that installation before using
  the Skills-only workflow. New product work uses only the Group v3 record format and does not migrate
or reuse repo-local v1 records. Existing `Test` and `Test2` histories are not changed. Old approvals
and design references do not authorize new work.

## GitlabWorkSpace delivery (0.2.0)

Group evidence, repository, and work-record paths are checked against the resolved Group root so Windows temporary-directory
aliases and other equivalent root paths remain valid without allowing paths outside the Group.

Workspace tasks use `delivery_mode: gitlab_mr`. Megin completes the normal approved development, independent review, verification and human acceptance, stages only accepted paths, then prepares the native handoff and stops. GitlabWorkSpace verifies evidence, commits in approved order, saves completion and releases the Group lock. Push and MR can retry from fixed commit IDs after local completion. The [v0.2.0 Release](https://github.com/dennis8499/Megin/releases/tag/v0.2.0) includes this handoff and validates Windows Group-path aliases against the resolved Group root; its published `megin-skills.zip` SHA-256 is `7d0323f0f8d97a90adee8eca980c3b929c4d22130e2422cf729b35a4673347a4`. See `.agents/skills/megin/references/gitlab-delivery.md`.
