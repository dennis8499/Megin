# Megin Skills

Megin is a complete, single-repository development workflow. Install all twelve Skills in one Git repository to guide work from requirements and plan approval through BDD/TDD, independent review, verification, human acceptance, feature commit, and local `--no-ff` merge. Work records and project knowledge stay in that repository.

Each repository is independent. Start Codex from the selected Git root, or name one repository explicitly. Megin does not require a remote. If the approved plan explicitly selects a remote, it pins that remote's URL and base SHA and checks them again before delivery.

## Install

Download `megin-skills.zip` from the [Releases page](https://github.com/dennis8499/Megin/releases), then extract the twelve `megin*` directories together into `<Repo>/.agents/skills/`. Keep existing files unless they conflict with the bundle. Start Codex with the repository root as the current working directory. Invoke the main Skill with `$megin`; stage Skills remain individually available for requirements, planning, behavior contracts, implementation, review, verification, acceptance, delivery, and project knowledge.

The canonical source is `.agents/skills/`. The archive contains the same standalone Skills and no Group or GitLab modules. To validate the source and reproducible archive locally:

```text
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip
```

## Workflow

For a new request, Megin verifies the selected Git root and reads its instructions, source, tests, and project documentation. It writes an evidence-backed requirements record at `docs/work/<Work ID>/requirements.md` and an approved plan and quality contract under the same Work ID. It does not scan sibling repositories.

Product changes begin only after approval of the exact plan. Megin uses a per-Repo lock and Skills fingerprint, executes approved BDD/TDD checks, then passes a frozen snapshot to a fresh read-only reviewer. After all checks pass, it presents the planned operations for human acceptance. Delivery stages accepted files, records the passing gate, commits on `feature/<Work ID>`, merges locally using `git merge --no-ff`, verifies both commits and the final tree, and releases the lock.

New records use `megin-repo-workflow/v1`, `megin-repo-quality-contract/v1`, and `megin-repo-quality-evidence/v1`. Historical records remain in place. Read [the single-Repo workflow](.agents/skills/megin/references/repository-workflow.md) and [quality gates](.agents/skills/megin/references/quality-gates.md) for the complete contract.

Version 0.5.0 adds optional [fixed committed inputs, scenario tracing and runner preflight](.agents/skills/megin/references/verification-extensions.md) to the v1 contracts. Completed work can export a [historical delivery receipt](.agents/skills/megin/references/delivery-receipts.md) for a fixed MergeReviewer review. These tools use `--repo` and `--work-id` and keep human acceptance in the native workflow.

GitlabWorkSpace carries a separate overlay for Group scanning, cross-Repo work, centralized records, locks, GitLab issues, and merge requests. Those capabilities are not part of this native Megin package.
