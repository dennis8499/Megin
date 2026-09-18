---
name: bug-diagnosis
description: Diagnose a suspected defect with reproducible, read-only evidence before a Megin v3 repair plan is authorized.
---

# Bug Diagnosis

Reproduce the reported symptom with the target repository's own commands and record the command,
environment, exit code, output digest, and a falsifiable root-cause hypothesis. Keep diagnosis
read-only: no product, test, configuration, dependency, Git, or canonical knowledge mutation.

Return exactly one disposition: `confirmed`, `likely`, `partial`, `not-a-bug`, or `blocked`.
Only `confirmed` or `likely` may enter a repair route, and the repair is classified separately as
small or large. A failed reproduction is evidence for `partial` or `blocked`; it is not permission
to guess. Keep the assessment identity and digest attached to later requirements and verification.
