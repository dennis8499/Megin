# Megin output language and style policy

This policy applies to all thirteen Megin Skills: progress messages, answers, and newly created or
updated human-readable work artifacts. Read it before responding or writing such artifacts.

## Human-readable output

Write progress messages, answers, and newly created or updated `requirements.md`, `workflow.md`, `plan.md`, `bug-diagnosis.md`,
Gherkin features, implementation evidence, review reports, verification records, human-acceptance
records, and knowledge notes in Traditional Chinese. This applies to titles, prose, table contents,
event logs, scenario descriptions, and manual operation steps. If the user or target project
explicitly requires another natural language, follow that explicit choice and record the decision in
the Work ID.

## Concise style

Follow [Claude Code Concise](https://code.claude.com/docs/en/output-styles#concise)
across hosts:

- Start with the answer or current result. Omit preambles, step-by-step narration, and closing recaps.
- Answer simple questions in one to three sentences. Provide full explanations when requested;
  formal work artifacts have no sentence limit.
- Put the main point in the artifact's existing summary or first prose paragraph. Preserve required
  sections, REQ/SCN mappings, approval records, acceptance steps, and evidence locators.
- Keep all findings, blockers, coverage gaps, and limitations. Preserve complete error reports,
  failing test output, security warnings, and destructive-action confirmations, with raw evidence
  and literal human responses unchanged.

## AI and technical content

Keep Skill instructions, Markdown control keys, schemas, status values, Work IDs, plan versions,
paths, commands, code, raw tool output, and original identifiers in English or verbatim so AI
execution and existing parsers remain reliable. Keep the Gherkin keywords `Feature`, `Scenario`,
`Given`, `When`, `Then`, and `And` in English; write the feature name, scenario descriptions, and
step text in Traditional Chinese.

## Requirements discovery waiting rule

The shared business rules for research triggers, source evidence, capability coverage, prerequisite-ready question
selection, completion, and recovery are in
[requirements-discovery-protocol.md](requirements-discovery-protocol.md). Before requirements discovery or any
handoff, apply that protocol and write its revision, blockers, and source references in the Work ID. If a protocol
condition is not met, ask exactly one question in Traditional Chinese, keep `phase: requirements` and
`status: awaiting_user`, and do not claim requirements are complete or create a planning handoff. This section keeps
the output-language and waiting-state contract; it does not duplicate the protocol's business rules.
