# Single-repository workflow contract

Megin runs from one Git repository root. Each Work ID belongs to that Repo and stores its readable workflow, requirements, plan, and evidence under `docs/work/<Work ID>/`. Do not scan parent or sibling folders for other Repos. Keep project-specific knowledge in the selected Repo's existing documentation structure.

## Base and branch

At planning time, record the selected Repo's root, current branch, full base commit, proposed `feature/<Work ID>` branch, allowed paths, exact checks, and their working directories. A repository with no remote is fully supported. Use its approved local base commit and never run remote commands. When the user explicitly selects a remote, freeze its name, URL, base branch, and full base SHA. The delivery gate checks that exact remote URL and `git ls-remote` base SHA again before a commit is made. Remote-tracking refs alone are not evidence of the current remote tip.

Preserve unrelated dirty work. Before implementation, confirm the approved base commit and create or verify the feature branch. Do not reset, stash, force-update, or overwrite existing user changes. A moved local base or selected remote base invalidates the approval and requires a new plan and acceptance cycle.

## Repo lock and Skills fingerprint

The quality contract records the SHA-256 fingerprint of every installed Megin Skill file. Compute it with `repo_workspace.py fingerprint --repo <Repo>` before approval. Compare it on resume and at each gate. Fingerprint drift requires reapproval and fresh review, verification, and acceptance.

Before the first product write, claim the Repo:

```text
python .agents/skills/megin/scripts/repo_workspace.py claim --repo <Repo> --work-id <Work ID> --writer <writer identity>
```

Before each product write, run the matching `check` command. The lock has no timeout; a waiting user, interruption, or blocked task does not release it. Continue only with the recorded Work ID and writer. Do not delete the lock manually. Release it only after the delivery record says `complete` and the completion gate passes:

```text
python .agents/skills/megin/scripts/repo_workspace.py release --repo <Repo> --work-id <Work ID> --writer <writer identity>
```

## Work record and gates

The workflow header uses `schema: megin-repo-workflow/v1`; the approved plan uses `megin-repo-quality-contract/v1`; gate evidence uses `megin-repo-quality-evidence/v1`. The contract freezes one Repo's `base_branch`, `base_commit`, optional `remote_name` and `remote_url`, `feature_branch`, `allowed_paths`, checks, `process_records`, `quality_ref`, `delivery_ref`, and `skills_sha256`. All evidence files must be predeclared under the Work ID's `evidence/` directory.

1. Approval precedes product writes. The exact plan includes behavior scenarios, implementation scope, check commands, review, user acceptance, and delivery.
2. Implementation follows BDD/TDD and changes only approved paths. Keep one writer and protect the Repo with the lock.
3. Review and verification bind the same product snapshot. Any code, test, plan, or Skills change invalidates downstream evidence.
4. Acceptance is the user's confirmation of the displayed Work ID, version, operations, and expected results. It is not inferred from passing automated checks.
5. After acceptance, stage only accepted product paths and run the `delivery` gate. Save its exact stdout, exit code, and SHA-256 in the predeclared delivery record. Commit the accepted product snapshot on the feature branch.
6. Switch to the approved base branch and run `git merge --no-ff <feature-branch>`. Save the full feature and merge commit SHAs in the delivery record. Run the `completion` gate; it verifies the saved delivery receipt, accepted tree, feature commit, exact merge parents, merge tree, and optional remote base. Set `status: complete` only after it passes, then release the Repo lock.

Delivery remains local. Native Megin does not push, create a pull/merge request, coordinate another Repo, or publish changes. Historical work records remain readable in place; new work uses this contract.
