# Delivery Orchestrator behavior evaluation report

This is development evidence, not a runtime record. Every Git fixture used a canonical host-temp repository, registry, worktree, and Ledger. No test created a branch or worktree in the SDLC repository, and no fixture was staged, committed after its initial base, pushed, merged, deployed, deleted, or cleaned up as part of delivery.

## Revision and protocol

- Evaluation date: 2026-08-30 (Asia/Taipei).
- SDLC base HEAD: `65f00eb74d2e35a542cc0cafe79e71f0c832cd5e`.
- Runtime/integration corpus SHA-256: `43f3f224730b6c0caf9c3160d4004add7835c492a3d87f1285fb9e63e07567ae` over 14 files: every delivery-orchestrator file except this report, plus the four changed implementation-execution contracts. The digest input is ordinal-sorted `skills-relative-path NUL lowercase-file-sha256 LF` records.
- The forward evaluator received the real minimal feature request, the selected runtime Skills, and an isolated fixture, but not the behavior-evaluation expected answers or prior review findings.
- The product Reviewer was a separate fresh session with no implementation conversation. It was read-only, made no writes, and did not delegate.
- Absolute workspace paths remain in host-temp evidence only. This report uses fixture IDs, run IDs, and repository-relative artifact paths.

Key reviewed file hashes:

| File | SHA-256 |
|---|---|
| `delivery-orchestrator/scripts/delivery_workspace.py` | `58895185d0dc76e81ce79b27cd7aac2e594dc48aeda29d5fd046242edf2d7368` |
| `delivery-orchestrator/scripts/test_delivery_workspace.py` | `0ae4b69d5d783112b83ae8ce43a45ff141318ae7066439cdb4cd075f0d6c114d` |
| `delivery-orchestrator/scripts/validate_contracts.py` | `ea9ceacda83a0e4e0144077cd40c6897ded1f94fc61fd48b8d1b11c99cd0a694` |
| `delivery-orchestrator/references/delivery-run.schema.json` | `cd1dd99aa2a9e4524b046f4860e50cd3b2b2fb6a48d29b27cfe5a2c507a03f12` |
| `delivery-orchestrator/references/workspace-and-run.md` | `ff3699bfaeb03387cf91ba2a442191681586336aa2988166e2bba4663f137307` |
| `implementation-execution/references/preflight-and-ledger.md` | `c599097566726600c2240de3e8f07adc6914457fbb6bbded86bca37fd760094` |

## Behavior matrix

| Case | Result | Evidence class | Observable result |
|---|---|---|---|
| EVAL-DEL-001 | Pass | Forward + automated | Generated `work-20260830-slugify-title-20d82345`, created its sibling worktree/branch from the exact base, completed both Candidate approvals, automatically entered implementation after approval 2, preserved reviewed uncommitted changes, received fresh approval, and froze at `complete/complete`. |
| EVAL-DEL-002 | Pass | Automated | Staged, unstaged, untracked, ignored output, dirty initialized submodule, detached HEAD, bare repository, branch/path/registry/permission collisions, and a same-ID race all failed closed. One race contender reserved the ID and at most one worktree was created. Hook/filter/fsmonitor sentinels stayed unchanged. |
| EVAL-DEL-003 | Pass | Automated | Same-session, explicit-ID, linked-worktree, dirty-primary, unique-active, and multiple-active lookup paths preserved record identity. Multiple active runs required explicit selection; missing/mismatched records were not inferred from names. |
| EVAL-DEL-004 | Pass | Forward + automated | Candidate presentation and approval were separate writes. Rejection/revision, minimal suffixes, both permitted upstream loops, stale approval rejection, Blocked resume, direct plan-ready-to-implementation routing, and Complete freeze passed. The forward run used exactly two approvals and no implementation prompt. |
| EVAL-DEL-005 | Pass | Automated + independent review fixture | `-r2` copied only hash-identical approved upstream inputs, recreated every local Ready source, did not copy product diff, retained generation 1, rejected unavailable/drifted sources before Git mutation, and rejected generation creation from Complete. |
| EVAL-DEL-006 | Pass (static boundary) | Static | `agents/openai.yaml` enables implicit invocation, while `SKILL.md` positively scopes product behavior, bug fixes, architecture/interface/data/dependency changes and material refactors, and excludes explanation, diagnosis, review, plan-only, formatting, and tiny prose edits. The current validation harness has no executable model-routing hook, so this result does not claim a programmatic trigger simulation. |
| EVAL-DEL-007 | Pass | Forward + automated + static | The legal forward record bound repo/worktree/branch/base, Work ID, generation, approvals, current requirements path/hash, current handoff, and its sole TOTAL `kind: spec` source. Schema extensions, binding/hash/evidence/source drift and extra product dirty paths failed closed. Standalone manifest-only behavior remains explicit and unchanged. |
| EVAL-DEL-008 | Pass | Forward + automated | Malicious checkout hooks, process/clean/smudge filters, fsmonitor hooks, initialized-submodule variants, fake secrets, and ignored output were isolated. Records contain command byte counts/digests rather than raw Git output. Primary and external sentinels were unchanged; the forward worktree, registry, Ledger, and reviewed uncommitted diff remain present. |
| implementation EVAL-009 | Pass | Forward + automated + static | The delivery-valid requirements exception was accepted only with the exact full binding and remained hash-stable through review. All invalid record/source/approval/path/hash and extra-dirty variants failed closed; standalone execution keeps the prior manifest-only whitelist. Existing implementation EVAL-001 through EVAL-008 evidence remains recorded in the [technical-planning behavior report](../../technical-planning/scripts/behavior-evaluation-report.md). |

## Forward end-to-end evidence

- Fixture locator: `delivery-forward-eval-262a077172de49daa08ea60c1d11e8a1`.
- Repository/worktree locator: `slug-fixture` / `slug-fixture.worktrees/work-20260830-slugify-title-20d82345`.
- Work ID and branch: `work-20260830-slugify-title-20d82345` / `delivery/work-20260830-slugify-title-20d82345`.
- Generation/base: `1` / `df6dbd6c4c31fa5c48d4f99c98c909adc460e046`.
- Requirements Candidate SHA-256: `226459550c03cd6c84b21850f2f3a2e8aa44312239a937334164900e13432d2c`.
- Ready requirements SHA-256: `17fc483edf966edb1f5f7968eebb10a8c4121df1bbca67d0a3accaae9174600e`; approval ref `fixture-controller:req-approval:rev-1`.
- Ready plan/evidence SHA-256: `45b4fe9e4e4c6100f4bf8f3ba16205b0fbe60ff95e473312fadaa5261ec64a1c` / `66a38bcf9ffe8ffd9a7ed9a6599bad6ec13ddea3e3aacd1e64ce332c5f6bb743`.
- Candidate payload digest: `28b6c32953ef0444122c6686a2c1a2a2e6cf1e2f90b91f77e0858923fb0b6c94`.
- Ready handoff SHA-256: `ec95983cee577ff31a654a402d7bd2cdb5a53574643064f641909707aa0be448`; approval ref `fixture-controller:plan-approval:slugify-title-r1`.
- Event order: `workspace_reserved`, `workspace_created`, `workspace-ready`, `requirements-candidate-presented`, `requirements-approved`, `plan-candidate-presented`, `plan-approved-implementation-started`, `implementation-run-complete`, `delivery-complete`.
- Implementation run ID: `59fe7af7416219d51271e0e19865204d92d36ddcde93c0ffb277dc67dd0a6321`; final `run.json` SHA-256 `90f1c048e62c80d29b9af38c9a58ef5607405d9492860949d03789ae1b110f5c`.
- BDD/TDD ordering: `BDD-001` and `BDD-003` produced behavior reds before their production changes; `TEST-001` and `TEST-002` each produced inner-TDD reds before green. Final discovery found 6 BDD scenarios, the build parsed 7 Python files, the full suite passed 8 tests, and the focused BDD suite passed 6 tests, all with zero failures and skips.
- Product/test SHA-256: `slugify_title.py` `ed3754d965e994b1fd835a2dc4908410fbcf95f54785944cf258528d0c293e7f`; BDD tests `5a33877684e5044b18b9a80c7847240626d1d93dd31dca4ff26e2df5b684332b`; unit tests `9d0f742ea3898e958060743131428a826e6fabb2f0495bae039eab2495b0bffa`; discovery runner `8165da1b03ca90399c4654734d0c5a28512f48b88cb76f4f64506720ba414785`.
- Canonical review snapshot before/after: `e3c794d0e69394f8b8b9fc293c7c59aa954e98a0da3623fcd7ec857ba876d0bd`.
- Fresh review report SHA-256: `014d74d45852c032a3bb2b6e3d4900f9f3ba7a4a722bafb5ab62c89f73683d4a`; verdict `APPROVED`; attestation `fresh_session=true`, `read_only=true`, `implementation_conversation_received=false`, `delegation_used=false`, `write_actions=false`.
- Primary before/after was identical: HEAD `df6dbd6c4c31fa5c48d4f99c98c909adc460e046`, index `8a99f56bd3599f16165eb30aa3c8c626923a7d63855907a5b97b98b5c6cdea2b`, status `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, and file inventory `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Delivery HEAD still equals the base, cached diff is empty, commit count remains one, there are no remotes, and all 11 delivery files remain untracked. The worktree, registry, and Ledger remain available for inspection.

## Commands and local outcomes

The following commands were run from the SDLC root; Python used UTF-8 mode, disabled bytecode output, and all Git-mutating fixtures lived under host temp:

```text
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/delivery-orchestrator
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/requirements-discovery
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/technical-planning
python -X utf8 -B <skill-creator>/scripts/quick_validate.py .agents/skills/implementation-execution
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/validate_contracts.py
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/test_delivery_workspace.py
python -X utf8 -B .agents/skills/technical-planning/scripts/validate_contracts.py
python -X utf8 -B .agents/skills/technical-planning/scripts/test_validate_contracts.py
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/capture_behavior_evidence.py
git diff --check
```

- All four quick validations passed.
- Delivery static contract validation passed.
- Delivery isolated Git suite: 21/21 passed in 104.722 seconds on the final runtime bytes. An independent correction-round Reviewer also ran 21/21 in 107.048 seconds.
- Technical-planning contract validation passed; its existing suite passed 5/5.
- `git diff --check` returned zero; the only emitted messages were line-ending conversion warnings.
- Clean-start witness: primary before/after equality was true; sibling branch `delivery/hash-witness-work` was attached, strict-clean, registered and non-primary. HEAD was `a0b9316053079543b165886dc9d85f243b5b8299`; file inventory SHA-256 `2d0619ecba853f226926a3612a99c689cd207079c5da8d27d03168ba765ffd9d`; index `31828b9b9eb797af0cedb98f789d0f8ef2c7a7ea3eea83790d083c21d51a2ef6`; status was the empty SHA-256; run record SHA-256 `773bda727aea43abcc8cea470b74c4d67e68072428e35f95beb760e018f34db6`.

## Failure and correction evidence

- The first independent code review returned `CHANGES_REQUIRED` for checkout hook/filter/fsmonitor side effects and raw Git output persistence; partial Ready/cross-reference/source reproduction; incomplete runtime schema enforcement; approval reuse after upstream loops; and absent EVAL-009/report evidence.
- Corrections added private hook routing, disabled active filters/fsmonitor/lazy-fetch/replace-object effects recursively through initialized submodules, digest-only command evidence, producer-valid full Ready validation, exact TOTAL spec and source reproduction, closed runtime schemas, and revision/approval reuse rejection.
- A forward Plan Candidate was rejected before approval with `SRC-REQ-001:FR-003 not text-materialized`; the Candidate was corrected, revalidated, then approved without weakening the producer contract.
- The correction-round Reviewer reran all commands and found every technical issue resolved. Its sole remaining finding was this then-missing report and the validator not requiring it. This report now exists, and `validate_contracts.py` lists it in `REQUIRED_FILES`.
- Closure review round 1 independently verified the evidence and found only that this report referenced a missing closure section. The section below records that review and this report-only correction; no runtime or integration file changed.

## Preserved user content

The four pre-existing untracked documents retained their initial SHA-256 values:

| Path | SHA-256 |
|---|---|
| `docs/plans/2026-08-29-dotnet-10-todo-list/handoff.json` | `afe401167a15b67616a55d4ab6bc858b0e05e966b71e6dbf45ceb9d3f8131e38` |
| `docs/plans/2026-08-29-dotnet-10-todo-list/plan.md` | `4447636865a3fe9237bfb949ce3d810f14da11f1f1c55c9367866c9307f258c1` |
| `docs/plans/2026-08-29-dotnet-10-todo-list/research.md` | `8d2ba43fb5152269cc24a68bf142b357d55e0bee4a7e5ce17c2414cfe6c79a5e` |
| `docs/requirements/2026-08-27-dotnet-10-todo-list.md` | `e5d24ba686b4600e79534ce639154edb0aec1335c6d92bcd3299a14143bc06dd` |

## Closure review

The independent, read-only closure Reviewer returned `CHANGES_REQUIRED` with one Low finding: the prior report SHA-256 `52293f5ccba0c2aa644ca787f18a7bbac4eef115f34c9c761b76a45bea4bb708` promised a closure section but ended before providing one. This section is the complete correction.

Before raising that finding, the Reviewer independently established all substantive closure conditions:

- The report exists and the validator requires it.
- The 14-file corpus digest independently recomputed to `43f3f224730b6c0caf9c3160d4004add7835c492a3d87f1285fb9e63e07567ae`.
- Neither repository report contains a Windows, Unix-home, or host-temp absolute path.
- The forward fixture, worktree, registry, and implementation Ledger remain present; hashes, event order, Complete state, one-commit/no-remote state, uncommitted diff, snapshot equality, product review verdict, and Reviewer attestations match this report.
- The technical-planning EVAL-009 addendum and relative link are valid.
- Four quick validations, both static validators, the five technical-planning tests, and `git diff --check` passed. Per review instruction, the already-recorded 21-test runs were not repeated.

Closure Reviewer attestation: `read_only=true`, `write_actions=false`, `delegation_used=false`.
