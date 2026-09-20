# Megin Skills-only workflow

Megin is a reusable set of Codex Skills for evidence-driven software delivery. Install the Skills
once, then work through normal conversation. There is no Megin Plugin, Megin command, hook, MCP
server, or dedicated workflow controller to install or run.

The bundle keeps a complete delivery path:

`requirements → behavior contract and plan → one plan approval → BDD/TDD implementation → fresh review → automated verification → human acceptance → knowledge review and one local commit`

The workflow is driven by Skills and a readable `docs/work/<work-id>/workflow.md` record. Git,
repository search, project tests, and the project's own tools remain available as ordinary tools.

## Install the Skills

Download `megin-skills.zip` from this repository's release or checkout. The archive contains the
following folders at its top level:

`megin`, `megin-requirements-discovery`, `megin-technical-planning`, `megin-bug-diagnosis`,
`megin-project-knowledge`, `megin-behavior-contract`, `megin-implementation-execution`,
`megin-test-driven-development`, `megin-code-review`, `megin-verification-before-completion`,
`megin-human-acceptance`, and `megin-finishing-delivery`.

Extract those folders together into one of Codex's Skills locations:

- user-wide: `$CODEX_HOME/skills/` (defaults to `~/.codex/skills/`, for every repository)
- repository-local: `<repo>/.agents/skills/` (for a team or one repository)

The repository already contains the same source under `.agents/skills/`. If the Skills do not appear
after installation, restart Codex so it rescans the Skills directory. Skills are automatically
discoverable by their descriptions; `agents/openai.yaml` keeps implicit invocation enabled.

You can also invoke `$skill-installer` in a Codex conversation with this repository's GitHub
repository/path, asking it to install every `megin*` folder. For a local checkout, extract or copy
the folders directly into one of the two locations above. `$skill-installer` installs Skills only;
it does not register a Plugin or add a Megin executable.

For a local experiment, copy only the `megin*` folders into a temporary Skills directory. Keep the
folders together because the stage Skills share the workflow-record reference from `megin`.

## Use it from conversation

Explicit invocation names the Skill:

- `$megin 幫我新增登入功能` starts the complete workflow.
- `$megin-code-review 檢查目前的修改` performs a fresh, read-only review.
- `$megin-bug-diagnosis 分析這個錯誤` diagnoses without changing product files.

Implicit invocation works when the task matches a Skill description. Say “新增功能”、“修正錯誤”、
“規劃這個變更”、“檢查目前修改” or the equivalent English request and Codex can select the
appropriate Skill. A description match is a routing hint; it does not bypass approval, review, or
acceptance gates.

To continue work, say “繼續上次的 Megin 工作”. The Skill reads `docs/work/*/workflow.md`, resumes
the only active Work ID, or lists active IDs when there is more than one. Historical delivery-run
records and approvals are evidence only; they are never reused as current authorization.

## Workflow rules

The first pass is read-only. Megin inspects repository instructions, branch and status, relevant
code and tests, existing work records, and source-backed project knowledge. A request is classified
as read-only, small, large, or bug. A suspected bug is reproduced and assessed before repair; an
explanation of a bug ends with evidence and does not silently become a fix.

Changes have one plan approval. The approved plan binds Work ID, behavior scenarios, allowed paths,
interfaces, tests, knowledge scope, and the local delivery target. After approval, one writer works
in the workspace at a time. BDD/TDD evidence and a different fresh reviewer are required before
automated verification. Verification runs every approved command against the reviewed snapshot and
then pauses at `awaiting_user` for the listed manual acceptance scenarios.

After the user names the Work ID and acceptance version, Megin reviews only the approved,
source-backed knowledge scope, stages only approved paths, and creates one local commit. Push,
pull requests, merge, deployment, branch deletion, and worktree cleanup are separate actions and
are not performed by this workflow.

## Work records

Each work item uses `docs/work/<work-id>/workflow.md` with schema `megin-skills-workflow/v1`.
Requirements, plan, feature files, test output, review, verification, acceptance, and knowledge
notes stay beside that file. The record keeps the base commit, branch, plan version, evidence paths,
current status, blockers, and one next action. See [the workflow-record contract](.agents/skills/megin/references/workflow-record.md).

Do not put secrets in a record. When a repository has a formal knowledge or test evidence contract,
follow that contract and record the source path, command, result, and digest it requires.

## Verify the bundle

The repository's CI checks Skill frontmatter, implicit invocation metadata, package completeness,
archive contents, and removal of legacy Megin runtime references. The local development validator is
`.agents/skills/megin/scripts/validate_skills.py`; it checks the bundle but does not run a workflow.

The release archive is `megin-skills.zip`. It is assembled from the repository's canonical
`.agents/skills/megin*` folders, so the archive and source share one maintenance path.

## From the old installation

If an older Megin Plugin or command is installed in Codex, remove or disable that installation and
delete its old repository-local copies before installing this bundle. Existing historical work and
evidence under `docs/work/` and `docs/knowledge/` remain readable; their approvals are not migrated
or reused. New work starts with a new Skills workflow record.
