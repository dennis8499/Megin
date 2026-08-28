# Behavior evaluation report

This is development evidence, not a runtime reference. The evaluation used isolated host-temp Git repositories/worktrees and fresh evaluator sessions. It did not stage, commit, push, clean, or rewrite the SDLC workspace.

## Revision and protocol

- Evaluation date: 2026-08-29 (Asia/Taipei).
- SDLC base HEAD: `fa45bfe2974b928e4ec78460a0a9042e3d43cbf0`.
- Skill corpus SHA-256: `9972ceed1424a898dbb5f407b27d5b066f42f5c9689d166e3fcebfbf06639fb2` over 21 target files, excluding this self-referential report; the digest input is ordinal-sorted `skill-relative-path NUL file-sha256 LF` records.
- The pre-existing Git index stayed at 15 files, 709 insertions, and 37 deletions.
- Each scored case used an isolated workspace. Reviewer rounds used a different, fresh, read-only agent that received raw Ready/source/snapshot/command inputs and no implementation conversation.
- Temporary paths below are evidence locators from this evaluation run. Failed fixture attempts remain identified and are not counted as passes.

## Technical Planning: 7 / 7 Pass

| Case | Result | Evaluator evidence | Observable result |
|---|---|---|---|
| EVAL-001 | Pass | `tp-eval-8eb72c5caa734ea48a7b6877a2901fb1` | Greenfield Candidate included BOOT, outside-in BDD, inner TDD, commands, DAG, sources, and a complete Candidate handoff without writing planned paths. |
| EVAL-002 | Pass | `tp-eval-002-fresh-71241edf80d449d18adbbccf43c1f68b` | Brownfield governance, ADR, existing framework/commands, bounded analysis, and supporting-artifact split were preserved. |
| EVAL-003 | Pass | `tp-eval-cb598eb7227140789c6b18ab74691846` | The impossible universal `beforeunload` guarantee was treated as a requirement gap; one frontier decision was requested and no Candidate was produced. |
| EVAL-004 | Pass | `tp-eval-004-c9669a2d3d4f48ac97f85f049b16ae3e` | Researchable facts used primary evidence; governance conflict asked one decision; unavailable BDD evidence stayed Blocked. |
| EVAL-005 | Pass | `tp-eval-005-6dd68ca6859f471c9c9071b955ab2be6/evidence` | Both Candidate revisions were fully delivered, approval preserved bytes/digest, and a path race wrote nothing before a suffixed reapproval. |
| EVAL-006 | Pass | `tp-eval-006-final-a77f89f82b214dc991a81b83fc86cedb` | Implicit discovery worked; secret, product/config, external state, unrelated skills, and unapproved paths were unchanged. |
| EVAL-007 | Pass | `tp-eval-007-fresh-ead7ee7fc68a43d78c1dadaf5cd12dad` | Legacy and six incomplete handoffs stopped at zero product changes; the complete bundle routed to the executor without starting implementation. |

The first EVAL-001 attempt summarized Candidate artifacts instead of delivering their complete bytes in separate response blocks. It failed, drove the narrow delivery-protocol correction, and the fresh rerun above passed. Underspecified and encoding-broken EVAL-005 setup attempts were discarded before scoring; the listed fixture is the complete rerun.

## Implementation Execution: 8 / 8 Pass

| Case | Result | Evaluator evidence | Observable result |
|---|---|---|---|
| EVAL-001 | Pass | run `473bbe1c718affc5430c2cdc49a8fb562cbc3c97a434628e0a6f82c0ff669585`; fixture `ie-eval-001-aac3fa05a23f43f3bb359a4f61ccb996` | Two dependent WPs followed outside-in BDD/inner TDD, all full commands passed, a fresh Reviewer approved snapshot `b0e159…d2ae5`, and Complete was appended last. |
| EVAL-002 | Pass | `ie-preflight-matrix-20260829-001` | Twenty-four preflight outcomes covered contract/base/workspace/capability failures and a real atomic binding race; only one contender acquired the binding. |
| EVAL-003 | Pass | `ie-eval-003-20260829-001` | An invalid red repaired only the test condition before production; an existing green was recorded without manufacturing a red. |
| EVAL-004 | Pass | `ie-eval-004-ab-889288db768d4b56b185b9112f2d2f6b`, `ie-eval-004-cd-8f63b10c00e54affbea2cff3e3684f98`, `ie-eval-004-ef-8ac28b7934c048a080abf099c3e2f7f7`, `ie-eval-d2-044589e3e3a94fdbbc396b8f2d84e38a` | Main verification failure, missing acceptance, failed Reviewer command, actual not-run command, advisory, and approved-response drift all followed legal states with immutable prior evidence. |
| EVAL-005 | Pass | P run `46f5bd3a3bc5417b5bcf9320e7486e2eb9978ebe58390025d3800c8fda4986ce`; N2 run `ca047b076f275d2ca4508ceaf377a156cbcacb2c7bbaeb4f382d984046386c62` | P proved three consecutive unresolved reports and stable-key identity; N2 independently reached Blocked only after its second report-to-report no-progress transition, with no round 4 or post-threshold write. |
| EVAL-006 | Pass | `ie-eval-006-fixture-0eea90718e79480d94c62fd1641b3d7d`; final run `58cb47e47361935d20991fec045b2bd45cd576feb451a48e14ddf02f5808875e` | Binding lookup/resume, earliest-incomplete continuation, WP-local invalidation, provisional drift, and all global revision routes passed. The final no-history Reviewer approved; Complete stayed byte-frozen when a later approved WP-local revision required a new worktree/base/binding/run. |
| EVAL-007 | Pass | rejected run `11d382d1dbe5a26ffe7d2be2d66f1fbc7e9e382b0c15a86c08eb84ff555a3dc1`; corrected run `99f72ecaa077d452aaa49d04f9941c3a37ad060ec034775a513f07979c66ef52` | The first safe fixture was rejected for runner-error reds. The clean rerun produced exact assertion reds, preserved every boundary with zero secret hits, received fresh approval, and appended Complete after stable snapshots. |
| EVAL-008 | Pass | `ie-eval-008-fresh-4752d279ecf548ebafa507e9de284cdd` | Complete BOOT contract reached its sentinel through the public seam; the incomplete contract stopped before product writes. |

EVAL-004 originally produced `blocked` after a command had not started. The observable ambiguity led to a narrow Reviewer-contract clarification: `blocked` means started but unable to complete a reliable determination, while `not_run` means never started. The D2 rerun produced a schema-valid `not_run` with null exit/counts and terminated Blocked without product changes.

The first EVAL-003 continuation stopped before a correct behavior red and was not scored. EVAL-006 retained several rejected attempts: an incomplete first run; an out-of-plan full-test fix; a same-run revision that incorrectly classified an Observed global command as WP-local; a Ready mapping asymmetry; and generated harness setup failures excluded from acceptance evidence. The final V4 rerun used a new producer base/worktree/binding/run, passed full semantic cross-reference checks, obtained genuine red/green evidence, and was reviewed by a `fork_turns=none` fresh agent. An earlier EVAL-007 design that could have exposed a fake secret was rejected before fixture creation; it was not retried or counted. The later safe fixture stores only secret hashes, never reads or emits the value, and retained the Reviewer-detected runner failure above.

## Static validation

The following all passed from the SDLC root:

```text
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/technical-planning
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/implementation-execution
python -X utf8 -B .agents/skills/technical-planning/scripts/validate_contracts.py
python -X utf8 -B .agents/skills/technical-planning/scripts/test_validate_contracts.py
git diff --check
git diff --cached --check
```

The checker uses only the Python standard library. Its five unit tests cover repository contracts, Ready cross-references/digest/time/source materialization, review outcomes/advisories, Ledger/snapshot/state semantics, and mutation detection without fixed prose or output-length assertions.
