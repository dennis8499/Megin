# Megin repository and Group workflow

Start here when running Megin's development lifecycle or resuming its unfinished Work ID.
Stage Skills belong to that lifecycle; package maintenance, standalone coding, analysis
and review retain the user's selected workflow. Read [language-policy.md](language-policy.md) before
human-readable output. Install all thirteen Skills together.

## Select and resume

Select exactly one `--repo` (Git root) or `--group-root` (non-Git root outside any Repo),
or use `unified_workflow.py detect`. Repo work stays in its root. Group inventories every
real direct-child Git root; links, junctions and nested Repos are excluded. Records live
at `<selected root>/docs/work/<Work ID>/`; only approved change Repos are written/branched.

For an existing unfinished Work ID, inspect its schema, phase, approval, fingerprint,
locks and review history, then resume its earliest incomplete action. Reuse valid evidence
already loaded; completed/unrelated records confer no authority for new work.

New Repo v3 / Group v6 work follows requirements → architecture → planning → approval →
implementation/BDD/TDD → independent review → verification → human acceptance → feature
delivery. Each change Repo pins live remote `refs/heads/master`; local HEAD, tracking refs
and `main` cannot replace it. Plan approval precedes product writes; human acceptance
precedes staging/commits. Review is round 0 plus at most three corrections, each in a fresh
independent read-only context. Preserve attempts and locks across waits/resume.

## Load the current contract

Load only the rows needed for the current action, plus the selected stage Skill. Read the
linked section and any schema it depends on before producing its records; reuse it when
already available in context. These references define the fields rather than copying them
into every stage entrypoint.

| Current action | Required reference |
| --- | --- |
| Settle requirements or hand them to architecture | [requirements-discovery-protocol.md](requirements-discovery-protocol.md) |
| Initialize headers/root configuration or choose new-work baselines | [workspace-workflow.md](workspace-workflow.md#roots-and-phases), including read-only preparation and workflow header |
| Explore/freeze architecture and discovery | [workspace-workflow.md](workspace-workflow.md#architecture-evidence) and [new-work-evidence.md](new-work-evidence.md#discovery-and-approval) |
| Freeze BDD/plan, evidence paths or exact-plan approval | [workspace-workflow.md](workspace-workflow.md#approved-quality-contract) and [new-work-evidence.md](new-work-evidence.md#discovery-and-approval) |
| Claim, prepare, check a writer, or run TDD | [workspace-workflow.md](workspace-workflow.md#explicit-mutations-and-gates) and [new-work-evidence.md](new-work-evidence.md#tdd-and-review) |
| Review, verify or record human acceptance | [new-work-evidence.md](new-work-evidence.md#tdd-and-review) and [workspace-workflow.md](workspace-workflow.md#explicit-mutations-and-gates); acceptance fields are in its approved quality contract |
| Deliver feature commits or recover partial delivery | [workspace-workflow.md](workspace-workflow.md#feature-only-delivery-and-recovery) |
| Group architecture, planning, implemented impact, review or verification | Additionally [group-impact.md](group-impact.md); keep unchanged consumers in fixed-source verification |
| Gate schema/branch-policy troubleshooting | [quality-gates.md](quality-gates.md) and [branch-policy.md](branch-policy.md) |
| Declared fixed inputs/runner probes or requested historical receipt | [verification-extensions.md](verification-extensions.md) or [delivery-receipts.md](delivery-receipts.md), respectively |

`quality_gate.py` is read-only. `unified_workflow.py` exposes explicit
claim/prepare/check/deliver/release operations using the selected root. Gates prove
consistency; independent review and literal human decisions supply semantic approval and
acceptance. Common-dir Repo locks protect linked worktrees; Group also holds a root lock.

## Legacy compatibility

Repo v1/v2 retains its original native gate, fingerprint/approval/snapshot semantics,
optional remotes and local `--no-ff` delivery. Group v1–v4 continues on its original
GitlabWorkSpace package. Group v5 supports completed historical export only. Finish active
work with its original package; never migrate an unfinished Work ID, replace its installed
Skills or reset attempts. Installation blocks unfinished work/locks; new work uses v3/v6.

For stage-selection and recovery cases, read [workflow-examples.md](workflow-examples.md).
