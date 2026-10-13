# Megin maintenance operations

## Runtime

Install the thirteen-Skill package with install_skills.py --target <root> [--check]. New Repo v3 / Group v6 work uses the same source, independent of GitlabWorkSpace. Installation blocks unfinished work and active locks. Preserve original installed packages for legacy/in-progress work.

Read [workspace-workflow.md](.agents/skills/megin/references/workspace-workflow.md) for headers, architecture/quality fields and examples. quality_gate.py snapshot|validate-record|check is read-only. unified_workflow.py detect|inventory|resolve|fingerprint is read-only; claim|prepare|check|deliver|release are explicit workflow operations. Each root selection is mutually exclusive --repo / --group-root; the workflow helper can detect cwd when neither is supplied.

Remote resolution selects explicit/configured/origin/unique remotes and pins refs/heads/master. No remote/main/local fallback exists for new work. baseline caches master objects and materializes regular source in an external scratch directory for architecture exploration, preserving product branches/worktrees. Both baseline/prepare disable configured fetch refmaps so local master/tracking refs stay untouched. claim/gates bind exploration to that actual committed baseline. prepare preflights all targets then fetches/rechecks every SHA before branching. It stops before any switch that would replace tracked installed Skills/configuration/current-work records. Checkout hooks are isolated for that command. check validates ownership/feature branches and retained review history before writes.

Repo common-dir locks are shared across modes and worktrees; Group has an additional root lock. Locks have no timeout and persist through waiting/partial failure. Do not delete them manually. deliver requires human acceptance and completes only after all feature commits and tree evidence pass. Existing commits are preserved on resume. Legacy native helpers still dispatch old contracts to the original logic.

## Verification and export

Optional runner/fixed-input helpers support --repo / --group-root for new contracts. Historical delivery_receipt.py exports native/Group v2 feature receipts, and continues legacy native v1 exports. Existing MergeReviewer only understands its old receipt version; do not mislabel v2 receipts as v1.

## Validate and package

~~~text
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py
python -X utf8 -B -m unittest discover -s tests/quality-gates -p "test_*.py" -v
python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --build-archive megin-skills.zip --archive megin-skills.zip
~~~

Run Windows/Linux CI. The archive builder uses stable paths, timestamps and file modes. It includes README/OPERATIONS and rewrites their local documentation links for the flat archive layout; Skill resource bytes remain exact. Record source revision and archive SHA-256 for a release. Do not publish or push as part of local development verification.

## Compatibility

Keep legacy schema paths intact. New work uses Repo v3/Group v6; Group v6 requires architecture/v2 and source-backed cross-Repo impact confirmation. Completed Group v5 records remain historically exportable. Unfinished old work keeps its original package/fingerprint; installation checks Group and child Repo workflows plus common-dir locks before replacing Skills. GitlabWorkSpace bundles this native core and retains its MR review adapter separately.
