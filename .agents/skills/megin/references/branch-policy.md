# Single-Repo branch and delivery policy

Select exactly one Git root and state its purpose and current evidence in the requirements record. Record the current local base branch and full commit SHA. The user may explicitly select a remote; if so, record its exact remote name, credential-free URL, base branch, and full remote SHA. A remote is optional and must not be inferred as a requirement merely because a Repo has one configured.

Create `feature/<Work ID>` from the approved base only after the plan is approved and the Repo lock is claimed. Every Git command must target the selected Repo. Before each product write, check lock ownership and the installed Skills fingerprint. Preserve unrelated changes. Never reset, stash, overwrite, force-update, push, or change a branch without explicit user authorization.

The approved plan names each behavior, allowed path, quality check, exact command and working directory, relevant knowledge update, and delivery step. Follow the approved dependency order within this Repo. A local base advance, branch change, changed selected remote URL or SHA, Skills drift, or product snapshot drift invalidates the relevant approvals and requires new review, verification, and acceptance.

After independent review, automated verification, and explicit human acceptance, stage only accepted product paths. Run the delivery gate before committing. Save the exact passing gate output and exit code in the predeclared `delivery_ref`. Commit the accepted feature snapshot on `feature/<Work ID>`. Then switch to the approved local base branch and integrate with:

```text
git merge --no-ff feature/<Work ID>
```

Save the full feature and merge commit SHAs in the delivery result. The completion gate verifies that the feature commit directly descends from the approved base, its tree matches the accepted snapshot, the merge has exactly the approved base and feature commits as parents, and the local base points to that merge with matching content. Only then set the workflow to `phase: delivery`, `status: complete`, and release the Repo lock.

Do not push or create a pull/merge request as part of native delivery. Keep commit and merge local; publishing is a separate user-directed action.
