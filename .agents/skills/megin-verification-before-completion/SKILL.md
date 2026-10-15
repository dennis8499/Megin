---
name: megin-verification-before-completion
description: Verify an approved Megin snapshot using its exact checks, scenario evidence and independent review. Use before Megin human acceptance/delivery or after a snapshot changes; failed or stale obligations remain incomplete.
---

# Megin verification before completion

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and stage contracts,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

1. Verify exact approved Work ID/plan/snapshot. Run every approved command from recorded cwd,
   retaining original stdout/stderr, exit codes and test counts. Execute declared compatibility
   checks; test checks require nonzero execution, no failures and no skips. Keep each obligation
   rather than substituting a convenient check.
2. For Group, apply [group-impact.md](../megin/references/group-impact.md) to direct/indirect
   unchanged consumers, even with one change Repo. Bind compatibility to pinned source and
   actual-diff confirmation. Drift, stale searches, new interfaces or unknown necessary
   external dependencies block acceptance/delivery pending renewed evidence/approval.
3. When declared, apply [verification-extensions.md](../megin/references/verification-extensions.md)
   for fixed committed inputs and exact read-only runner probes; bind digests in structured
   and raw output, and resolve runner failures.

Finish by setting verification/acceptance phase and passing the read-only `acceptance` gate
for the selected root/Work ID. It validates automated evidence and independent review;
the human decision remains separate. Snapshot changes need repair, fresh review and
verification within the existing correction cap.
