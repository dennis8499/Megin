# Megin maintenance operations

## Install and use

Megin is a standalone, single-Repo Skills bundle. Extract all twelve folders from `megin-skills.zip` into `<Repo>/.agents/skills/` and start Codex at that Git repository root. Invoke `$megin` for the full lifecycle or an individual `$megin-*` Skill for a stage. Every stage follows the same Repo-local contract in `.agents/skills/megin/references/repository-workflow.md`.

Native Megin supports repositories without remotes. It pins the approved local base commit and performs a local feature commit plus `--no-ff` merge. Only a remote explicitly selected in the approved plan is checked against its frozen URL and base SHA. Native Megin does not scan sibling Repos or create GitLab issues/MRs.

## Runtime evidence

New work records use `<Repo>/docs/work/<Work ID>/workflow.md` with `megin-repo-workflow/v1`. The plan's `megin-repo-quality-contract/v1` binds the base, feature branch, paths, checks, declared evidence files, and installed Skills fingerprint. Gate evidence uses `megin-repo-quality-evidence/v1`.

Use `quality_gate.py snapshot|check --repo <Repo> --work-id <Work ID>`; `check` accepts `--gate review|acceptance|delivery|completion`. Use `repo_workspace.py fingerprint|claim|check|release --repo <Repo>` for the Skills fingerprint and per-Repo writer lock. The helper checks structures and evidence; it does not run project tests or claim that review was independent.

## Validate and package

From the repository root, run:

```text
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py
python -X utf8 -B tests/quality-gates/test_quality_gate.py
python -X utf8 -B tests/quality-gates/test_repo_workflow.py
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --build-archive megin-skills.zip --archive megin-skills.zip
```

The archive builder uses stable paths, timestamps, and file modes. Release automation should record its SHA-256 and the source revision. Group/MR fixtures and tests are maintained in GitlabWorkSpace, not in the native Megin release.

## Source compatibility

The quality gate keeps the legacy `megin-quality-contract/v1` format for Megin's own historical maintainer fixtures. New user work uses only `megin-repo-*` schemas. Historical work records are preserved. In-progress Group records stay on their existing GitlabWorkSpace package until completion; update that workspace using its Group lock and approval flow.
