# Megin output language policy

This policy is the shared AI-facing instruction for every Megin Skill that creates or updates a
human-readable work artifact. Read it before writing any such artifact.

## Human-readable output

Write newly created or updated `requirements.md`, `workflow.md`, `plan.md`, `bug-diagnosis.md`,
Gherkin features, implementation evidence, review reports, verification records, human-acceptance
records, and knowledge notes in Traditional Chinese. This applies to titles, prose, table contents,
event logs, scenario descriptions, and manual operation steps. If the user or target project
explicitly requires another natural language, follow that explicit choice and record the decision in
the Work ID.

## AI and technical content

Keep Skill instructions, Markdown control keys, schemas, status values, Work IDs, plan versions,
paths, commands, code, raw tool output, and original identifiers in English or verbatim so AI
execution and existing parsers remain reliable. Keep the Gherkin keywords `Feature`, `Scenario`,
`Given`, `When`, `Then`, and `And` in English; write the feature name, scenario descriptions, and
step text in Traditional Chinese.

## Requirements discovery waiting rule

Before requirements discovery or any handoff, check the purpose, audience, functional boundaries,
exclusions, and observable acceptance results. If any unknown could change the product choice or
scope, ask exactly one highest-impact clarification question in Traditional Chinese and wait for the
user's answer. Keep the Work ID at `phase: requirements` and `status: awaiting_user`, record known
facts and the unanswered question, and do not claim requirements are complete, create a planning
handoff, or turn an unconfirmed product choice into an approved decision.

After the user answers, re-check the remaining unknowns and ask the next single question if needed.
When the information is sufficient to define the goal, boundaries, and acceptance, do not add a
formal question merely to satisfy a template and hand off to `phase: planning`. Resolve facts that
can be learned from code, tests, or project documentation before asking the user.
