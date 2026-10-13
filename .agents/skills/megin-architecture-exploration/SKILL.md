---
name: megin-architecture-exploration
description: Explore source architecture after Megin requirements discovery and before planning, for one Repo or all valid Repos in a Group. Trace components, entrypoints, flows, dependencies, tests and impact with frozen source evidence.
---

# megin-architecture-exploration

Read [repository-workflow.md](../megin/references/repository-workflow.md), [workspace-workflow.md](../megin/references/workspace-workflow.md), [new-work-evidence.md](../megin/references/new-work-evidence.md) and [language-policy.md](../megin/references/language-policy.md).

Start after problem, audience, outcome and acceptance are clear; set `phase: architecture`. Exploration is read-only. Repo mode inspects its Git root; Group mode explores every safe direct-child Git root, including unchanged Repos. Read applicable instructions and established documentation.

For potential change Repos, use `unified_workflow.py baseline --repo <Repo> --destination <empty-external-directory>` (or --group-root with --repo-path) to explore exact live-master source in a scratch directory. This caches Git objects without changing a product branch/worktree. Current-worktree exploration is valid when its source matches pinned master. Pin every unchanged Group Repo's clean HEAD as well. Mismatched baseline scans block claim.

Run the bundled functional scanner with documented exclusions, reconciling every included file and candidate entrypoint. Trace boundaries, normal/failure flows, contracts, dependencies, tests, gaps and likely change paths. Separate facts, assumptions, requirements and suggestions. Preserve visible baseline_exclusions for committed links/submodules and explain dependency limits. Scanner completeness alone does not prove semantic understanding.

Save scans and reconciled `megin-discovery/v1`; Repo uses `megin-architecture/v1`, Group uses v2. Architecture binds requirements revision/digest, discovery digest and per-Repo source snapshots. Include components with source paths, data flows, entrypoints, dependencies, test paths and impact paths.

For Group read [group-impact.md](../megin/references/group-impact.md). Trace expected API/event/package/data/table/configuration changes into unchanged and indirect consumers. Preserve contract-related fixed-source searches and both ends of each dependency, traversing cycles with a visited set. Reconcile every candidate as affected, unaffected or unknown with evidence; empty impact evidence, one name miss or an unresolved necessary external source cannot establish no impact. Validate architecture before planning. Only approved modification Repos get branches; unchanged consumers belong in verification_repositories.

Handoff source-backed architecture and affected-Repo candidates to `$megin-technical-planning`. This stage creates no branches or product changes.
