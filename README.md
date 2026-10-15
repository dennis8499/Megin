# Megin Skills

Megin is a development workflow for **one Git repository or a local Group of repositories**. Install all thirteen Skills together. New work follows requirements → source architecture → planning → human plan approval → remote-master feature branches → BDD/TDD → independent review → verification → human acceptance → feature commits.

Every change Repo requires a live remote `master`. Megin pins its exact SHA, fetches/rechecks it after plan approval, and develops on `feature/<Work ID>`. All accepted Repos remain on feature branches for your later merge decision.

All thirteen Skills use the shared [output language and style policy](.agents/skills/megin/references/language-policy.md): Traditional Chinese, result-first Concise replies and work artifacts, with complete required records and raw evidence. Requested explanations remain full length.

## 0.8.1 update

All thirteen Skills use the shared Concise policy and load stage guidance on demand. Routing, completion criteria and workflow examples are clarified; Repo v3, Group v6 and architecture/v2 remain compatible.

## Install and upgrade

Download `megin-skills.zip` from the [Releases page](https://github.com/dennis8499/Megin/releases) and unpack it into a temporary directory. From that unpacked directory run:

~~~text
python -X utf8 -B megin/scripts/install_skills.py --target <Repo-or-Group-root>
~~~

Use --check for read-only preflight. The installer refuses unfinished work or active locks, preserves other Skills, and backs up replaced Megin directories. Manual extraction bypasses that upgrade preflight; finish active work with its existing package first.

Invoke `$megin` from a Git root for Repo mode or from a non-Git root containing direct-child Repos for Group mode. Individual stage Skills remain available. The canonical source is `.agents/skills/`; the same package contains both modes without requiring GitlabWorkSpace.

## Workflow guarantees

- Requirements clarifies intent before the distinct architecture phase. Architecture traces components, flows, entrypoints, dependencies, tests and impact with frozen source evidence.
- Group discovery covers all valid direct-child Repos; only approved change Repos get branches. Group records are central; Repo records remain local.
- Exact-plan approval precedes product writes. Each BDD scenario requires a real assertion-failing red and passing green; setup/import errors do not count.
- Initial independent review is round 0. Failures allow at most three correction/re-review attempts, each with a fresh independent read-only context. Stop early on approval; failed round 3 stays incomplete. Resume never resets attempts.
- Human acceptance of the exact snapshot precedes staging/commits. Both modes use shared Repo common-dir locks, and Group also holds a root lock.
- Completion verifies feature commits and accepted trees. Partial multi-Repo delivery resumes existing commits. Push, merge, MRs and deployment are separate user-directed work.

## Contracts and compatibility

Version 0.8.0 adds Group workflow/quality v6 and architecture/v2: fixed-source cross-Repo impact searches, indirect unchanged consumers, compatibility checks and separate actual-diff confirmation. Repo v3 and historical v2 receipts remain supported. See [Group impact evidence](.agents/skills/megin/references/group-impact.md), [workspace workflow](.agents/skills/megin/references/workspace-workflow.md), [quality gates](.agents/skills/megin/references/quality-gates.md) and [receipts](.agents/skills/megin/references/delivery-receipts.md).

Legacy Repo v1/v2 records remain readable without changing their approval/fingerprint/snapshot/local-merge rules. Existing Group v1–v4 work continues with its original GitlabWorkSpace package until complete. GitLab Issue/MR and simulated-work integrations stay in GitlabWorkSpace. Current MergeReviewer consumes legacy v1 receipts; v2 receipt support is a separate integration update.

## Validate

~~~text
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip
python -X utf8 -B -m unittest discover -s tests/quality-gates -p "test_*.py" -v
~~~

See [OPERATIONS.md](OPERATIONS.md) for maintenance and packaging.
