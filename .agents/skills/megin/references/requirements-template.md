# Requirements template

Use one Work ID per selected Repo or Group root. Write human-readable content in Traditional Chinese unless explicitly instructed otherwise; keep keys/IDs in English.

~~~markdown
# Requirements: <title>

- work_id: <work-id>
- requirements_revision: req-1
- mode: repo | group

## Problem, audience and outcome
<Observed problem, affected people, measurable desired result and acceptance.>

## Current behavior and source evidence
| Source | Observation | Established fact | Uncertainty |
| --- | --- | --- | --- |
| <Repo/path:line or user statement> | <observation> | <fact> | <gap> |

## Repo inventory
<All valid Group Repos and their purposes/dependencies, or the selected Repo.>

## Requirements and boundaries
- REQ-001: <observable requirement>
- In scope: <behavior>
- Exclusions: <explicit exclusions>
- Assumptions / technical suggestions: <separate, with disposition>

## Decisions and blockers
<Resolved decisions; unresolved behavior-changing questions block architecture/planning.>

## Behavior scenarios
<Observable Given/When/Then scenarios.>

## Acceptance and delivery
<User operations and expected outcomes; accepted feature commits for later user merge.>

## Architecture handoff
<Source questions, dependencies, tests and likely impact to explore next.>
~~~

Architecture exploration subsequently covers all source/entrypoints and records its own frozen evidence. The plan chooses only actual change Repos and binds remote master SHAs, BDD/TDD obligations, checks, review, human acceptance and feature-only delivery.
