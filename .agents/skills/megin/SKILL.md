---
name: megin
description: Run an approved, end-to-end development workflow in one Git repository, from requirements and plan approval through BDD/TDD, independent review, verification, human acceptance, commit, and local merge.
---

# Megin

Megin operates on exactly one Git repository: the current repository root or one the user names. Start Codex inside that repository. All twelve Megin Skills are a coordinated workflow and must be installed together. Work records live in `<Repo>/docs/work/<Work ID>/`; project knowledge stays with that Repo. Read [repository-workflow.md](references/repository-workflow.md) before starting or resuming work.

## Start and resume

1. Confirm the selected path is the Git root with `git rev-parse --show-toplevel`. Do not scan sibling folders or infer a larger workspace.
2. Read the Repo's source files, tests, documentation, and relevant `docs/` knowledge. Search for an existing matching Work ID under `docs/work/`; resume its earliest incomplete approved action. Do not reuse a completed or unrelated record.
3. For a new request, create a unique Work ID and a `megin-repo-workflow/v1` record in `docs/work/<Work ID>/workflow.md`. The first pass is read-only. Ask focused questions only for missing product decisions.
4. Write evidence-backed requirements, user-visible BDD scenarios, and an executable plan. Obtain explicit approval for the exact plan before changing product files.
5. Freeze the installed Skills fingerprint and selected base. If the user explicitly chooses a remote, save its name, URL, base branch, and full SHA; otherwise use the current local base commit and do not require a remote.

## Governed phases

- `requirements` and `planning`: inspect one Repo, identify unknowns, record user-visible behavior and project knowledge needs, and prepare an executable plan. No product writes.
- `approval`: present scope, files, scenarios, checks, base commit, and delivery steps. Wait for approval of that exact version.
- `implementation`: claim the Repo with `repo_workspace.py claim` before product writes. Follow BDD/TDD for each behavior and preserve unrelated changes. Before every product write, run `repo_workspace.py check` with the same Work ID and writer.
- `review`: hand the frozen snapshot to a fresh, independent, read-only reviewer. The reviewer checks implementation, tests, allowed paths, and the approved plan. Do not review your own changes.
- `verification`: run every approved command from its recorded working directory. Record raw output, exit code, and test counts. Any failure or snapshot change requires repair and a fresh review.
- `acceptance`: present the approved user operations and expected results. Wait for the user's response to the exact Work ID and acceptance version. Do not stage or commit before acceptance.
- `delivery`: stage only accepted paths, run the delivery gate, commit the feature on its approved branch, then integrate locally with `git merge --no-ff`. Run the completion gate and release the Repo lock only after the completed record is saved.

Use `$megin-requirements-discovery`, `$megin-technical-planning`, `$megin-behavior-contract`, `$megin-test-driven-development`, `$megin-implementation-execution`, `$megin-code-review`, `$megin-verification-before-completion`, `$megin-human-acceptance`, `$megin-finishing-delivery`, and `$megin-project-knowledge` at their corresponding stages. The bug-diagnosis Skill supports the same single-Repo workflow. These stage Skills are installed together with this entry point.

## Evidence and stop conditions

The approved contract binds one Repo, a pinned base, feature branch, allowed paths, exact checks, declared evidence records, and the Skills fingerprint. Use `quality_gate.py snapshot|check --repo <Repo> --work-id <Work ID>`; `check` also takes `--gate review|acceptance|delivery|completion`. The helper is read-only. It does not prove that a test covers the intended behavior or that review was independent.

Stop on missing approval, unknown requirements that change behavior, a changed Skills fingerprint, base or remote drift, scope violations, stale evidence, failed checks, or a lock owned by another writer. Preserve evidence and describe the next action. Do not force-unlock a Repo or write outside the selected Repo.

Native Megin does not scan or coordinate other Repos and does not prepare GitLab issues, merge requests, or workspace handoffs. If work spans multiple repositories, create separately approved single-Repo workflows or use the GitlabWorkSpace distribution that provides its own Group workflow.
