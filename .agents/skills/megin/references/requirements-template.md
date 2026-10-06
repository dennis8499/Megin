# Requirements template

Use one document for one Work ID in one Git repository. Cite repository files, tests, documentation, user statements, or external primary sources for claims about current behavior. Keep unknowns visible; do not turn an unverified assumption into a requirement.

```markdown
# Requirements: <title>

- work_id: <work-id>
- requirements_revision: req-1
- repository: .

## User problem and desired outcome
<Observed problem, affected user, and measurable outcome.>

## Current behavior and evidence
| Source | Evidence | What it establishes | Uncertainty |
| --- | --- | --- | --- |
| <Repo-relative path or user statement> | <specific observation> | <claim> | <remaining gap> |

## Scope and exclusions
- In scope: <behavior and affected paths>
- Out of scope: <explicit exclusions>

## Decisions and open questions
| ID | Question or decision | Evidence/options | Status | Blocking |
| --- | --- | --- | --- | --- |
| Q-001 | <decision> | <sources> | open | yes/no |

## Behavior scenarios
<Given/When/Then scenarios using observable user outcomes.>

## Quality and delivery expectations
- Checks: <commands and expected proof>
- Knowledge: <Repo documentation to update, if needed>
- Acceptance: <user-visible operations and expected results>
- Delivery: <local feature commit and --no-ff merge>
```

If a requirement touches another Repo, record it as a dependency or open question and ask the user how that Repo should be handled. Do not inspect or modify sibling Repos under the single-Repo contract.
