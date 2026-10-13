# Quality gates

New work uses Repo contract/evidence v3 or Group v5. Read [workspace-workflow.md](workspace-workflow.md) for fields and commands and [new-work-evidence.md](new-work-evidence.md) for approval/TDD/review evidence. Gates are read-only; they do not execute project tests, invent user responses or prove actual reviewer independence.

- snapshot: digest Git-normalized worktree content plus protected records and committed verification inputs. Group combines selected Repos and central work records.
- validate-record: validate root, schema pair, exact plan approval, architecture/discovery, selected Repos, dependency graph, checks, paths and Skills fingerprint.
- review: implementation/review phase; require current branch/approved base, allowed paths, writer/raw check/TDD evidence and no staged product files. Review may record findings.
- acceptance: verification/acceptance phase; additionally require every approved check to pass with nonzero tests/no failures/no skips and an independent APPROVED review for the same snapshot. This does not represent the user's acceptance.
- delivery: delivery phase; additionally require literal human acceptance, current remote master identities/SHAs and staged bytes equal to accepted content.
- completion: verify the passing delivery gate receipt, every feature commit's direct approved-base parent and the accepted combined committed trees. New work has no local merge requirement.

Any missing/stale evidence blocks advancement. Requirements/architecture/plan/contract changes require a revised approval; product changes require new review/verification/acceptance within the same append-only review cap. Wrong branches, scope drift, Skills drift and another writer's locks also stop writes.

Delivery results use native megin-repo-delivery-result/v2 or Group megin-delivery-result/v2. The gate JSON is a predeclared hashed process record. Partial results retain accepted commits; only all-target completion can mark complete and release locks. Historical receipt checks validate committed evidence without querying live remote tips or current product state.

Legacy native v1/v2 and maintainer v1 gates retain their original snapshot/local-merge semantics. Group v1–v4 work remains on its original package until completed.
