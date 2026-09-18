---
name: verification-before-completion
description: Prove that an approved Megin v3 change is complete using fresh snapshot-bound tests, executable Gherkin, review evidence, and human acceptance before delivery.
---

# Verification Before Completion

Use this skill immediately before asking for human acceptance or invoking `finishing-delivery`. Verification is a claim backed by current evidence, not a description of what was intended to happen.

## Verify the current snapshot

1. Load the exact approved scope, acceptance criteria, required validation commands, knowledge-update authorization, and the latest writer/reviewer reports.
2. Inspect repository status and the workspace diff. Confirm the work identity, branch, allowed paths, and product/test/configuration snapshot are unchanged since the reviewed snapshot.
3. Execute every logical obligation in the approved validation plan: focused tests, related tests, full checks, static checks, and applicable build or contract checks. Capture the exact command, exit status, and raw output.
4. Confirm that evidence is fresh for the current source, configuration, dependencies, test inputs, and generated artifacts. Any relevant change invalidates the affected evidence and requires a rerun.
5. Confirm a fresh read-only review has an `APPROVED` verdict with no blocking finding and covers the current snapshot.
6. Confirm authorized knowledge changes were reviewed, source references and digests are retained, and the canonical knowledge tree/lint result matches the approved outcome. Record a pending knowledge item when the contract allows product completion without promotion.

## Completion states

Use explicit v3 states so automated success is not confused with human acceptance or delivery:

- `awaiting_user_acceptance`: all automated commands and reviews pass; product, knowledge, staging, and commit state are unchanged.
- `accepted`: the user named the Work ID and acceptance version and confirmed the approved manual scenarios.
- `complete`: knowledge promotion and one local commit succeeded after acceptance.

Never report `DRAFT_PR_CREATED` without a real PR identity, and never call a failed or skipped command evidence of completion. A failed obligation returns the work to the authorized writer for a focused fix and then a fresh review/verification cycle; it is not waived by a passing unrelated test.

## Handoff

Save a final verification record containing work identity, snapshot digest, commands and outputs, review reference, knowledge result, delivery state, unresolved findings, and one next action. Only a passing verification record may authorize `finishing-delivery`; merge, deployment, and cleanup remain out of scope.
