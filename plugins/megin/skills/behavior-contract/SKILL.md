---
name: behavior-contract
description: Build and maintain Megin v3 executable Gherkin scenarios with stable IDs and explicit automatic or human acceptance coverage.
---

# Behavior Contract

Use this skill while the request is still read-only. Read the current code, tests, project
knowledge, and repository runner before writing the candidate. Give every external behavior a
stable scenario ID, keep one `.feature` wording as the source for BDD, TDD, and manual acceptance,
and record the command that will execute the feature in the approved scope.

A scenario is complete only when it has a concrete Given/When/Then path and an observable result.
Mark an existing passing scenario as existing coverage instead of manufacturing a red test. Add
manual acceptance only for the approved user-visible path, including the exact environment,
operation, and expected result. An undefined, pending, skipped, or environment-error step is not
valid evidence of a passing behavior.

After approval, changing a scenario ID, wording, expected result, or automatic/manual boundary
creates a new plan version and returns the work to the approval gate.
