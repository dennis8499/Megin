# Planning Source Evidence

## Identity

- Work ID: `work-20260906-sdlc-maintainability-f997c61b`
- Repository ID: `0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`
- Base HEAD: `1532391a4ea056828e30893e749fe307118a1e24`
- Planning status SHA-256: `8bfa14c5cf9c0eb041907db0876a441c207384de658b0e45ca5e3eb09606e12b`
- Requirements SHA-256: `74c90df50b27d23486256c902e40ea80d3ed96a04118895021db6cadff1732ff`

## Fresh baseline

`python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp` returned `knowledge-suite-report/v1`, `outcome: passed` on the unmodified base.

- `TEST-QUERY`: 21/21 passed.
- `TEST-GOVERNANCE`: 18/18 passed.
- `TEST-WORKFLOW`: 34/34 passed.
- `BDD-FULL`: 24/24 passed, failed=0, skipped=0.
- Requirements, Planning, Implementation, BUG and Delivery owner contracts passed.
- BUILD-FULL parsed 37 Python files and 5 JSON Schema files with zero errors.
- Owner tests passed; Delivery worktree integration ran 65/65 tests in 677.496 seconds.
- 50k observation: probe 1.729636 seconds, transition 1.050254 seconds; both remained below 2 seconds.

This local Windows result is baseline evidence only. Cross-platform release evidence still requires both Windows and Linux workflow artifacts.

## Observed code and absence evidence

- `.github/workflows/knowledge-portability.yml` has explicit paths for six skill bundles and the workflow, but no `docs/**`, root guides or `.gitattributes` trigger.
- Repository root has no `README.md` or `OPERATIONS.md`.
- `_delivery_record.py` has 3,837 lines; `_transition_record_unlocked` begins at line 2881 and extends through the common persistence tail.
- `delivery_workspace.py` exposes probe/start/locate/authorize/transition; `doctor` is absent.
- `technical-planning/scripts/validate_contracts.py` exposes a local `validate_instance` subset; supported/ignored keyword sets and an unknown-keyword audit are absent.
- `run_full_suite.py` has no `--metrics-output` argument or command duration fields.
- `project-knowledge/scripts/test_behavior.py` has no `maintenance` group or BDD-026..031.
- Proposed focused classes `DocumentationAndCiImprovementTests`, `DeliveryDoctorTests`, `DeliveryTransitionArchitectureTests`, `SchemaSubsetContractTests`, `SuiteMetricsTests` and `SearchQualityBaselineTests` are absent.
- `knowledge_query.query_repository` returns at most five results and performs final snapshot validation; a repository-fixed search-quality corpus/evaluator is absent.

## Source boundaries

No external network source is required: public behavior and constraints are owned by approved Requirements and repository contracts. The plan does not claim a Linux execution result or a post-change performance result.
