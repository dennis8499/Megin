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

- repository, base commit, branch, and Work ID;
- route, phase, status, and plan version;
- intent, scope, assumptions, risks, and acceptance scenarios;
- approved paths, interfaces, dependencies, commands, evidence, and knowledge scope;
- task ownership, fresh review, verification, user acceptance, delivery, blockers, and next action.

Append dated events. Do not overwrite an old approval or review; create a new plan/review version
when scope or the source snapshot changes. Preserve unrelated dirty changes and stop on branch,
scope, or evidence drift.

## Delivery sequence

Use `megin` for the complete route:

1. Explore requirements and source-backed project knowledge without mutation.
2. Define stable behavior scenarios and a dependency-ordered technical plan.
3. Present one exact plan approval for the current Work ID and version.
4. Implement with one writer and outside-in BDD/TDD evidence.
5. Obtain a fresh, read-only review from a different context.
6. Rerun every approved command and scenario against the reviewed snapshot.
7. Pause for the user's listed manual acceptance response.
8. Review the approved knowledge scope, stage approved paths, and create one local commit.

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
one local commit after acceptance. External publication and cleanup are separate authorization.

## Historical material

Historical `docs/work/` and `docs/knowledge/` records remain for traceability. Old runtime records,
approvals, and design references are not current authorization. New work must use the Skills-only
record and the current source snapshot.
