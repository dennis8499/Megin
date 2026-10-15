---
name: megin-implementation-execution
description: Execute an exact approved Megin Repo or Group plan on remote-master feature branches. Use for a Megin Work ID's implementation or correction with one writer, TDD evidence and independent review handoff.
---

# Megin implementation execution

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

1. Read the approved plan; set `implementation / active`. Run `unified_workflow.py claim`,
   then `prepare` once with the same root, Work ID and writer. Preparation preflights every
   target, fetches/rechecks remote master and creates feature branches. Preserve dirty work.
   On resume verify existing branches/locks/evidence instead of recreating them.
2. Before every product write run `unified_workflow.py check` with that identity. Follow
   approved paths/dependency order and `$megin-test-driven-development`; preserve raw commands,
   cwd, output and counts. Scope, baseline or Skills changes require replanning.
3. In Group, apply [group-impact.md](../megin/references/group-impact.md): retain frozen
   architecture; save separate actual-diff confirmation and replay contract searches on
   implemented bytes and pinned peers. New consumers/interfaces need renewed planning/approval.
   Verification-only Repos supply fixed inputs/checks without product changes or branches.

Finish with the read-only review gate and a frozen combined snapshot, approved records and
raw evidence for a fresh independent reviewer. Repairs retain TDD/lock checks, append-only
attempts and the three-correction cap. Stage/commit only during accepted delivery.
