# Development context-load report

This report is maintenance evidence, not a runtime reference. The “before” side is the Git index that existed before this optimization; the “after” side is the current working tree. Runtime Markdown includes `SKILL.md` and non-maintenance Markdown references. It excludes behavior evaluations, JSON schemas, scripts, tests, and this report.

## Aggregate

| Bundle | Before bytes | After bytes | Delta | Reduction |
|---|---:|---:|---:|---:|
| `technical-planning` | 38,801 | 34,717 | -4,084 | 10.5% |
| `implementation-execution` | 38,023 | 37,030 | -993 | 2.6% |
| Combined | 76,824 | 71,747 | -5,077 | 6.6% |

Frontmatter description characters changed from 148 to 87 for Technical Planning and from 207 to 122 for Implementation Execution.

## Runtime branches

Technical Planning before this change loaded:

- Common evidence/gate: `SKILL.md`.
- Blocked or decision route: `SKILL.md` plus `delivery-protocol.md`.
- Candidate route: `SKILL.md`, `candidate-authoring.md`, `technical-plan-template.md`, `quality-contract.md`, and `delivery-protocol.md`.
- Maintenance only: the above plus `behavior-evaluation.md`.

Technical Planning after this change loads:

- Common evidence/gate: `SKILL.md`.
- Blocked or decision route: `SKILL.md` plus `delivery-protocol.md`.
- Candidate route: `SKILL.md`, `candidate-authoring.md`, `technical-plan-template.md`, producer-owned `ready-plan-contract.md`, then `quality-contract.md` and `delivery-protocol.md`.
- Maintenance only: the applicable runtime branch plus `behavior-evaluation.md` and the development checker/tests.

| Technical Planning branch | Before bytes | After bytes | Delta |
|---|---:|---:|---:|
| Common evidence/gate | 5,968 | 5,275 | -693 |
| Blocked/decision route | 10,350 | 10,133 | -217 |
| Candidate route | 38,801 | 34,717 | -4,084 |

Implementation Execution before this change loaded:

- Preflight/resume: `SKILL.md` plus `preflight-and-ledger.md`.
- Execution/fixing: `SKILL.md` plus `bdd-tdd-loop.md`.
- Verification/review: `SKILL.md` plus `reviewer-contract.md`.
- Terminal delivery: `SKILL.md`, `quality-contract.md`, and `delivery-protocol.md`.
- Maintenance only: the above plus `behavior-evaluation.md`.

Implementation Execution after this change loads:

- Preflight/resume: `SKILL.md`, `preflight-and-ledger.md`, and the directly referenced producer-owned `ready-plan-contract.md`; machine validation reads the two JSON schemas.
- Execution/fixing: `SKILL.md` plus `bdd-tdd-loop.md`.
- Verification/review: `SKILL.md` plus `reviewer-contract.md`; report/snapshot shapes come from `execution-records.schema.json`.
- Terminal delivery: `SKILL.md`, binary `quality-contract.md`, and state-authoritative `delivery-protocol.md`.
- Maintenance only: the applicable runtime branch plus `behavior-evaluation.md` and the producer-owned development checker/tests.

| Implementation Execution branch | Before bytes | After bytes | Delta |
|---|---:|---:|---:|
| Preflight/resume, local bundle only | 15,587 | 12,808 | -2,779 |
| Preflight/resume, including producer Ready contract | 15,587 | 21,418 | +5,831 |
| Execution/fixing | 12,419 | 11,438 | -981 |
| Verification/review | 12,730 | 12,766 | +36 |
| Terminal delivery | 13,493 | 10,467 | -3,026 |

The effective Preflight branch intentionally gains the versioned producer contract that did not exist before. It replaces consumer-side handoff semantics rather than duplicating them; the combined deduplicated runtime corpus still falls by 6.6%.

## 2026-08-30 consumer ownership split

Technical Planning runtime contracts are unchanged in the predictability-first refactor. Its maintenance validator now owns only ready-plan/v1 plus shared JSON-schema helpers; execution schema, Ledger and review semantics moved to the Implementation consumer. Current cross-bundle branch bytes are recorded in the [Delivery context-load report](../../delivery-orchestrator/scripts/context-load-report.md).

The final closure measurement supersedes any mid-refactor Implementation figures above. Against base HEAD `7353419975c5a0df47bf28697b419f643c890fee`, Technical Planning runtime bytes remain byte-for-byte unchanged; the final Implementation aggregate and every current branch are recorded in the linked owner report. Its late increase is the documented cost of physical terminal-evidence, reviewer-output and breaker-chain invariants added after independent adversarial findings, not a return of producer-side execution ownership.
