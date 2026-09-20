---
name: megin-bug-diagnosis
description: Diagnose a suspected bug with read-only evidence before repair. Use for bugs, errors, regressions, failures, 錯誤、異常、回歸、失效; do not implement a fix during diagnosis or confuse an explanation request with a repair request.
---

# Megin bug diagnosis

Keep diagnosis read-only. Reproduce the symptom with the smallest safe oracle, inspect relevant
history and code paths, and state a falsifiable root-cause hypothesis. Record environment, trigger,
observed result, expected result, reproduction command, evidence paths, confidence (`confirmed`,
`likely`, or `not-a-bug`), impact, and residual uncertainty in `bug-diagnosis.md`.

If the user only asks why something happens, stop with the evidence and proposed next checks. If
the behavior is intended, route any desired change through requirements. Only a `confirmed` or
`likely` diagnosis may enter the normal requirements and planning path for a repair. Never change
product files, tests, records outside the current Work ID, or canonical knowledge during diagnosis.

Handoff: either a read-only finding, or `phase: requirements` with the diagnosis identity attached.
