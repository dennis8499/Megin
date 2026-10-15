---
name: megin-bug-diagnosis
description: Diagnose a Megin Work ID's suspected bug from read-only evidence before planning a repair. Use for Megin error/regression investigation; an explanation request authorizes diagnosis rather than implementation.
---

# Megin bug diagnosis

Read [repository-workflow.md](../megin/references/repository-workflow.md) for root/resume and reference selection,
then [language-policy.md](../megin/references/language-policy.md) for human-readable output.

Stay read-only until exact-plan approval. Use a focused reproduction check, then trace
relevant source, tests and docs. Repo stays in its root; Group may trace valid Repos and
cross-Repo dependencies. Preserve observations separately from hypotheses.

Finish with the reproduction command/output, smallest supported cause, affected behavior
and regression scenario. If reproduction is unavailable or inconclusive, record the gap
and next discriminating observation. A diagnosis-only request ends here. A requested repair
continues through `$megin` requirements, architecture and approved planning before writing.
