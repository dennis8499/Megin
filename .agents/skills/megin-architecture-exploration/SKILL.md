---
name: megin-architecture-exploration
description: Reconcile source architecture after Megin requirements and before planning. Use for a Megin Work ID's components, entrypoints, flows, dependencies, tests and impact across one Repo or every valid Group Repo.
---

# Megin architecture exploration

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

1. Once intent and acceptance are clear, set `phase: architecture`. Explore read-only, including
   applicable instructions/docs and every safe direct-child Group Repo, even unchanged ones.
2. For potential change Repos, explore pinned live-master source with
   `unified_workflow.py baseline --repo <Repo> --destination <empty-external-directory>`;
   Group uses `--group-root` plus `--repo-path`. This caches objects without product checkout.
   Current-worktree exploration is valid only when source matches pinned master. Pin each
   unchanged Group Repo's clean HEAD. Baseline mismatch blocks claim.
3. Run the functional scanner with documented exclusions; reconcile every included file and
   candidate entrypoint. Trace components, normal/failure flows, contracts, dependencies,
   tests and likely change paths. Separate facts, assumptions, requirements and suggestions;
   retain `baseline_exclusions` for links/submodules and dependency limits.
4. In Group, apply [group-impact.md](../megin/references/group-impact.md): trace direct and
   indirect unchanged consumers, retain both ends and fixed-source searches, and terminate
   cycles with a visited set. Classify every candidate affected, unaffected or unknown with
   evidence. One name miss, empty evidence or missing necessary source cannot establish no impact.

Finish with validated scans and reconciled `megin-discovery/v1`, plus architecture/v1
(Repo) or v2 (Group), binding requirements revision/digest, discovery digest and all source
snapshots. Include component paths, flows, entrypoints, dependencies, tests and impact.
Scanner completeness alone is insufficient. Hand architecture and change candidates to
`$megin-technical-planning`; unchanged affected consumers enter `verification_repositories`.
This stage creates no product branches or changes.
