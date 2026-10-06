---
name: megin-bug-diagnosis
description: Diagnose a suspected bug with read-only evidence before repair. Use for bugs, errors, regressions, failures, 錯誤、異常、回歸、失效; do not implement a fix during diagnosis or confuse an explanation request with a repair request.
---


# Megin bug diagnosis

Read [../megin/references/language-policy.md](../megin/references/language-policy.md) and [../megin/references/repository-workflow.md](../megin/references/repository-workflow.md) before investigating. Work only in the selected Git repository.

Reproduce the reported symptom with a focused check, then trace the relevant code path, existing tests, and project documentation. Separate observed facts from hypotheses. Report the smallest evidence-backed cause, affected behavior, regression scenario, and proposed repair. Diagnosis is read-only until the user has approved an implementation plan. Do not scan sibling repositories or change files during diagnosis.

When evidence is incomplete, identify the next observation that would distinguish the remaining causes. Handoff: reproduction command and output, source locations, root-cause evidence, and a regression test proposal.
