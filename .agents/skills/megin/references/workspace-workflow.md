# Native Repo v3 / Group v5 workflow

## Roots and phases

Install all thirteen Skills at `<root>/.agents/skills/`. Repo mode uses a Git root; Group mode uses a non-Git directory outside any repository, containing real direct-child Git roots. Ignore ordinary directories, nested Repos, symlinks and junctions. Discovery covers all valid Group Repos; only the approved change set is written or branched. Records are `<root>/docs/work/<Work ID>/`.

Use the fixed order: `requirements → architecture → planning → approval → implementation → review → verification → acceptance → delivery`. Requirements settles intent before source architecture exploration. Planning includes BDD scenarios; implementation runs BDD/TDD after approval. Read [new-work-evidence.md](new-work-evidence.md) for discovery/approval/TDD/review schemas. Old Repo v1/v2 and Group v1–v4 work must finish using its original package; do not replace active Skills.

## Read-only preparation

Commands run from the installed root; each operation takes exactly one root flag.

~~~text
python .agents/skills/megin/scripts/unified_workflow.py detect
python .agents/skills/megin/scripts/unified_workflow.py inventory --group-root <Group>
python .agents/skills/megin/scripts/unified_workflow.py resolve --repo <Repo>
python .agents/skills/megin/scripts/unified_workflow.py baseline --repo <Repo> --destination <empty-system-temp-directory>
python .agents/skills/megin/scripts/unified_workflow.py resolve --group-root <Group> --repo-path <RepoName> [--remote <name>]
python .agents/skills/megin/scripts/unified_workflow.py fingerprint --repo <Repo>
~~~

Remote resolution uses explicit choice, configured Repo override/Group default, origin, then a sole remote. Otherwise request a choice. Optional `.megin/repo.json` is `{"schema":"megin-repo-config/v1","remote":"origin"}`. Group `.megin/group.json` keeps `megin-group-config/v1` with `defaults` and `repositories` containing remote/base_branch. New work requires base_branch master; other values are errors. Configuration is not a Repo allowlist. Save resolved values, source and configuration digest in the plan; later defaults do not rewrite an approved selection.

`resolve` reads live `refs/heads/master` with ls-remote. It does not fetch or create branches. Store credential-free remote identity and the full remote SHA. A local master may be behind, ahead or absent; new delivery never moves it.

## Workflow header

Repo v3:

~~~markdown
- schema: megin-repo-workflow/v3
- work_id: work-YYYYMMDD-slug
- repository: .
- base_branch: master
- base_commit: <full remote SHA>
- feature_branch: feature/<work-id>
- remote_name: origin
- remote_url: <credential-free URL>
- delivery_mode: feature_handoff
- phase: requirements
- status: active
- plan_version: plan-1
- requirements_revision: req-1
- quality_ref: docs/work/<work-id>/evidence/quality.json
- delivery_ref: docs/work/<work-id>/evidence/delivery.json
~~~

Group uses `schema: megin-skills-workflow/v5`, replaces the five Repo branch/remote fields with `repositories: repo-a,repo-b` in contract order, and keeps the other shared fields. Use only the approved change set here. Status values: active, awaiting_user, awaiting_review, blocked, needs_revision, complete. Preserve a dated progress ledger below the header.

## Architecture evidence

After requirements, scan each Repo with `functional_inventory.scan(repo, exclude_paths=quality_policy.SCAN_EXCLUSIONS)`. For potential change Repos whose source differs from remote master, use baseline with an empty external scratch directory (--group-root plus --repo-path for Group). It fetches/rechecks immutable master objects, copies regular source blobs without checkout filters/hooks/product writes, and emits scan JSON with source_commit and visible baseline_exclusions for links/submodules. Read the materialized files and reconcile their architecture; scanner output alone is not exploration.

Save scans and reconciled reports in megin-discovery/v1. Complete file/entrypoint coverage is mandatory. Claim and subsequent gates compare each selected Repo's frozen source inventory/entrypoints with its pinned master objects, allowing standard LF/CRLF representations. Unchanged Group Repos use current source and live claim checks. Baseline drift requires fresh exploration, architecture and exact-plan approval. Preparation fetches/rechecks again after approval.

The contract's `architecture_ref` is a hashed, predeclared evidence reference to:

~~~json
{
  "schema": "megin-architecture/v1",
  "work_id": "<work-id>",
  "requirements_revision": "req-1",
  "requirements_sha256": "<requirements.md SHA-256>",
  "discovery_sha256": "<discovery JSON SHA-256>",
  "repositories": [{
    "repo_path": ".",
    "snapshot_id": "<frozen functional snapshot>",
    "summary": "<boundaries, flow, impact and limits>",
    "components": [{"name": "<component>", "paths": ["src/app.py"]}],
    "data_flows": ["<input to observable result>"],
    "entrypoints": ["<source path and symbol>"],
    "dependencies": [],
    "test_paths": ["tests/test_app.py"],
    "impact_paths": ["src/app.py"]
  }]
}
~~~

Group uses real Repo names and covers every discovery Repo. Component/test paths are Repo-relative inventoried source paths. Other lists describe source-backed findings; use explicit empty lists where appropriate and explain gaps in the summary. New product paths can appear in impact_paths.

## Approved quality contract

Repo `megin-repo-quality-contract/v3` retains native v2 fields, adds hashed `architecture_ref`, requires nonempty remote_name/remote_url, base_branch master and delivery_mode feature_handoff. Group `megin-quality-contract/v5` uses the same common discovery/approval/TDD fields and a nonempty `repositories` array of:

~~~json
{
  "repo_path": "repo-a",
  "remote_name": "origin",
  "remote_url": "<credential-free URL>",
  "base_branch": "master",
  "base_commit": "<full remote SHA>",
  "feature_branch": "feature/<work-id>",
  "allowed_paths": ["src/", "tests/"]
}
~~~

Both contracts contain `work_id`, `plan_version`, `requirements_revision`, `requirements_ref`, `requirements_sha256`, hashed `discovery_ref`, `discovery_sha256`, `architecture_ref`, `approval_ref`, `max_corrections: 3`, four `review_records`, `scenario_ids`, `behavior_trace`, `checks`, `process_records`, `quality_ref`, `delivery_ref`, `skills_sha256`, `delivery_mode` and `handoff`. Repo branch/remote/allowed_paths fields are top-level. Checks use unique id, kind test|command, exact command and cwd. Repo cwd is "."; Group cwd is "." or a selected Repo name. Group scenario implementation paths and TDD test_path are Group-relative, including the Repo prefix.

Native allowed_paths also includes the Work ID directory for protected requirements/plan/contract files. Installed .agents/skills and reserved .megin metadata are explicit governance exclusions; the installed Skills fingerprint is bound separately. Otherwise only workflow.md and precisely declared process_records are excluded from its product snapshot. Group records stay central and protected records contribute to the combined snapshot. Evidence changes cannot broaden exclusions after approval. Unrelated staged files always block preparation/delivery.

`handoff` declares `dependencies` (all selected names mapped to prerequisite lists), `merge_order` (dependency-first commit/handoff order), `compatibility_check_ids`, `partial_delivery` instructions and, for independent multi-Repo work, `independent_reason`. Native name is ".". Multi-Repo work requires at least one approved compatibility check. The historical field name merge_order does not authorize a merge.

Predeclare quality.json, delivery.json, delivery-gate.json, discovery/scans, architecture, approval and its raw transcript, raw writer/check/TDD/acceptance outputs, review-attempt-0.json through -3.json, all review/correction outputs, and receipt.json when requested. All process_records stay under this Work ID's evidence directory. Never broaden after approval.

Quality evidence uses `megin-repo-quality-evidence/v3` or `megin-quality-evidence/v5`. Reuse the v2/v4 writer/check/TDD/review fields. Human acceptance additionally requires actor_kind human, literal response and timestamp. Raw claims bind work_id, version, snapshot, verdict, timestamp and JSON-encoded response. Fixtures and simulated actors cannot supply a real human decision.

## Explicit mutations and gates

After exact-plan approval:

~~~text
python .agents/skills/megin/scripts/unified_workflow.py claim --repo <Repo> --work-id <ID> --writer <context>
python .agents/skills/megin/scripts/unified_workflow.py prepare --repo <Repo> --work-id <ID> --writer <context>
python .agents/skills/megin/scripts/unified_workflow.py check --repo <Repo> --work-id <ID> --writer <context>
~~~

Group uses --group-root. Claim verifies approval, architecture, baseline-bound discovery and fingerprint before creating locks. Both modes lock `<Git common-dir>/megin/workspace.lock.json`, protecting linked worktrees. Group also locks `<Group>/.megin/workspace.lock.json`. Acquire targets in a stable order; failed claims release only newly acquired locks. Locks persist across interruptions, waiting and failures. If retained review attempts exist but the quality summary is missing, writes/claim stop until the evidence is recovered.

Prepare preflights all Repos, fetches master with --refmap= to ignore configured destination ref mappings, compares FETCH_HEAD with the approved SHA and rechecks all remotes before creating branches. Baseline exploration uses the same fetch isolation. Local master and tracking refs remain untouched. Dirty product changes, conflicting branches or tracked governance/current-work records that checkout would replace stop before switching any target. Use a compatible workspace that retains the approved installed package and records before retrying; never reset them. Switch hooks are isolated with a temporary command-only hooksPath. On resume use check to verify existing feature branches; do not rerun preparation after product changes. Before every write, check ownership, branch identity, review cap and fingerprint.

Read-only gates:

~~~text
python .agents/skills/megin/scripts/quality_gate.py snapshot --repo <Repo> --work-id <ID>
python .agents/skills/megin/scripts/quality_gate.py validate-record --group-root <Group> --work-id <ID>
python .agents/skills/megin/scripts/quality_gate.py check --group-root <Group> --work-id <ID> --gate review
~~~

Review is implementation/review phase; acceptance gate is verification/acceptance; delivery/completion gates are delivery phase. Acceptance gate verifies automated evidence and independent review, not the user's decision. Review/acceptance prohibit staged product paths. All approved checks, independent review and human acceptance bind the same combined snapshot.

## Feature-only delivery and recovery

After a literal human acceptance, set delivery/active and run:

~~~text
python .agents/skills/megin/scripts/unified_workflow.py deliver --repo <Repo> --work-id <ID> --writer <context>
~~~

The helper checks full evidence and all remote master SHAs before staging, stages only accepted paths, saves the passing gate and commits each Repo in dependency order. Git hooks are isolated with a temporary command-only hooksPath so they cannot rewrite the accepted index/tree; normal author/signing configuration is preserved. If project hooks are required, declare and run their checks before freezing review/acceptance. Native delivery result is megin-repo-delivery-result/v2; Group uses megin-delivery-result/v2. Records bind delivery_mode, accepted_snapshot, delivery_gate (exit_code plus hashed JSON output), ordered repositories with base_commit/feature_branch/feature_commit/product_sha256, status and completion result.

Each feature commit has exactly the pinned base as its sole parent and accepted product tree, including every declared TDD test. Ignored/untracked excluded tests cannot authorize acceptance. Live completion rechecks all remotes and reads TDD tests from committed objects; historical export never queries live tips. No merge commit or local master pointer is required. On success save status complete and completion_ok/completion_snapshot, mark workflow complete and release locks. Push, merge, deployment and cleanup are separate user-directed work.

A later commit failure leaves status partial, existing commits and locks. Resume deliver without resetting branches; it verifies retained commits and can recover a crash after git commit but before record save. Any remote/base, scope, requirements or accepted-content drift requires a new exact plan approval, fresh independent review/verification and human acceptance while preserving the review cap/history.

Use `install_skills.py --target <root> [--check]` from the unpacked bundle for installation/upgrades. It blocks unfinished work/locks, preserves other Skills and backs up replaced Megin directories. See [delivery-receipts.md](delivery-receipts.md) for historical exports.
