---
name: human-acceptance
description: Guide the Megin v3 human verification gate using only the approved behavior scenarios and preserve the uncommitted product snapshot until acceptance passes.
---

# Human Acceptance

Use this skill after automated verification and independent review have passed. Present the
approved Work ID, acceptance version, workspace path, environment, each requested user operation,
and its expected observable result. Do not turn internal unit tests or reviewer checks into extra
manual work.

The user can reply with the Work ID and acceptance version to confirm that all listed scenarios
passed. Record the response and product snapshot, then hand off to `finishing-delivery`. If any
scenario fails, record the scenario and observed result, return to the implementation and review
loop, and require a new verification and acceptance cycle. Before acceptance, do not update formal
Project Knowledge, stage product files, or create the feature commit.
