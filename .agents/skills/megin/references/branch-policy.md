# Remote-master feature branch policy

New Repo v3 and Group v6 work follows [workspace-workflow.md](workspace-workflow.md). Only selected change Repos get `feature/<Work ID>`; Group discovery still includes unchanged Repos.

Select remotes by explicit instruction, configured override/default, origin, then a unique remote. Missing/ambiguous remotes require clarification. Pin live `refs/heads/master` with git ls-remote, credential-free remote identity and full SHA during planning. Main, local HEAD and remote-tracking refs cannot substitute. No remote or master means no development branch.

After plan approval acquire common-dir Repo locks and the Group lock when applicable. Preparation checks all targets before branch creation, fetches master with an empty refmap (ignoring configured destination mappings), verifies FETCH_HEAD against the approved SHA, rechecks all remote tips, then creates each feature branch from that exact commit. No local master or tracking branch is updated by these fetches. Stop before switching any target if checkout would replace tracked installed Skills, configuration or current-work records. Switching uses a temporary command-only hooksPath to prevent post-checkout hooks from staging or rewriting content. Preserve pre-existing dirty work and conflicting branches. Do not reset, stash, force-update or overwrite them. Resume verified existing branches without recreating them.

Before each product write verify lock, feature branch, base and installed Skills fingerprint. Recheck selected remotes before delivery. Changed remote URL/master SHA invalidates downstream approval/evidence: replan, obtain approval and repeat review/verification/acceptance, retaining review history and its correction cap.

After independent review, tests and human acceptance, create one feature commit per selected Repo in approved dependency order. Completion verifies direct descent from the pinned remote master and exact accepted trees. Leave branches for the user to merge later. Local master may be ahead, behind or absent and is not moved. Do not push, merge, create MRs, deploy or delete branches during native delivery.

Legacy Repo v1/v2 and Group v1–v4 work keeps its original package/approval/branch policy; finish it before upgrading. Historical local-merge receipts remain readable.
