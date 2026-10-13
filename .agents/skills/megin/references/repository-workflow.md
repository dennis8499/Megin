# Megin repository and Group workflow

For new work read [workspace-workflow.md](workspace-workflow.md). Repo v3 and Group v6 share requirements → architecture → planning → approval → implementation/BDD/TDD → independent review → verification → human acceptance → feature-only delivery.

Repo mode selects one Git root and stores records there. Group mode selects a non-Git root, explores every valid direct-child Repo and centralizes records; only approved change Repos get branches. Every change Repo requires a pinned live remote master. Both modes use common-dir Repo locks, with an additional Group lock, and all thirteen Skills installed at the selected root.

Plan approval precedes product writes; human acceptance precedes staging/commits. Initial review is round 0 with at most three corrections, each reviewed in a new independent read-only context; stop early on approval, retain failed/exhausted history on resume.

Use exactly one of --repo / --group-root in quality_gate.py and unified_workflow.py. The former is read-only. The latter exposes explicit claim/prepare/check/deliver/release operations. Read [quality-gates.md](quality-gates.md), [branch-policy.md](branch-policy.md) and [new-work-evidence.md](new-work-evidence.md).

## Legacy compatibility

Repo v1/v2 records remain readable by their original native gate logic, with optional remotes and local --no-ff delivery. Their fingerprints/approval/snapshot semantics do not change. Group v1–v4 work continues on its existing GitlabWorkSpace package. Never migrate an unfinished Work ID or replace its installed Skills. Installation blocks unfinished work/locks; once complete, new work uses v3/v6.
