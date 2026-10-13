# Group v6 cross-Repo impact evidence

Read this for architecture, planning, implementation, review and verification in
a Group. Repo v3 keeps architecture/v1. New Group work uses workflow, contract
and evidence v6 with `megin-architecture/v2`. Completed Group v5 records can be
exported historically; active older work must keep its original package and
fingerprint. Never upgrade an unfinished Work ID or reinterpret old approval
as approval of v6 evidence.

## Planned impact before approval

Explore every valid direct-child Repo, including unchanged consumers. Each
discovery scan records a full immutable `source_commit`; selected change Repos
use approved remote master, unchanged peers use their observed clean HEAD.
Use `source_baseline.scan_commit(repo, commit)` for pinned scans. Live gates
recheck unchanged peers' HEAD, scanner snapshots and full Git-normalized
product trees, including binary content, modes, deletions and nonignored
untracked inputs. Historical validation
reads those original Git objects. Source outside this declared Group is a
visible limitation; a missing source needed to decide compatibility is blocking.

Architecture/v2 retains architecture/v1's identity, requirements/discovery
digests and complete `repositories` component/flow/path rows. Add:

- `changed_contracts`: unique `id`, provider `repo_path`, `kind` (`api`,
  `event`, `package`, `data-contract`, `database`, `configuration`, `internal`),
  `description`, at least two distinct `symbols`, and fixed `source` locator.
  Terms must appear in that provider source or fixed `symbol_sources` entries.
  Provider-local entries use `{symbol, source}`. An unchanged downstream Repo
  may expose a renamed/wrapped interface: add `{symbol, source, via, reason}`,
  where source locates its alias, via locates its use of an already traced
  upstream symbol in the same Repo, and reason explains that mapping. Trace
  the root-backed edge into that Repo before enabling its alias for downstream
  searches. An alias cycle cannot bootstrap its own dependency. For example,
  A.get_customer -> B.summarize -> C.summarize works when C never names A.
  Preserve aliases, routes, event fields, package identities and settings.
- `searches`: unique `id`, `contract_id`, `repo_path`, full `commit`,
  `mode: literal`, `query` from that contract's anchored symbols, and exact
  `matches` (`path`, one-based `line`, literal `text`). Every anchored term
  must be searched in every candidate Repo (at least two terms). Search results,
  including no hits, are replayed against the fixed source. A name miss alone
  cannot establish no impact; inspect manifests, wrappers and aliases too.
- `impact_edges`: `contract_id`, fixed `provider` and `consumer` locators,
  source-backed `reason`, and nonempty `check_ids` from approved compatibility
  checks. Both endpoints must cite lines found by related searches. Follow
  indirect consumers until the visited set stops growing; cycles are valid.
  Disconnected edges are invalid. This graph is distinct from the delivery DAG.
- `repository_impacts`: every Group Repo exactly once with `repo_path`,
  `status: affected|unaffected|unknown`, a concrete `reason`, transitive
  `contract_ids`, and related `search_ids` covering every contract. Explain
  why same-named but unrelated code is unaffected. Unknown status blocks
  planning, as does any item in the required `unresolved` array.

A fixed locator is `{repo_path, commit, path, line, text}`. Paths are relative
to that Repo, must be inventoried regular source files, and the literal line
must match its Git blob. Preserve scanner exclusions and semantic limitations
in the architecture; searches do not magically establish architectural meaning.

The contract adds explicit `verification_repositories`, including every
affected unchanged consumer: `{repo_path, base_commit, check_ids}`. These
Repos supply fixed source, inputs and compatibility checks without write,
branch, lock or delivery authority. Their check IDs must be approved
`handoff.compatibility_check_ids`; checks may use their Repo as `cwd`.
Existing `verification_inputs` may name selected or verification Repos.
Their fixed product trees contribute to the combined accepted snapshot.
Even a single modification Repo needs compatibility checks when the impact
graph reaches another Repo. Delivery dependencies/order contain only the
selected modification Repos and remain acyclic.

Predeclare all evidence, including actual impact confirmation, before exact
plan approval. Validate architecture before progressing to approval:

~~~text
python .agents/skills/megin/scripts/impact_policy.py read --group-root GROUP --repo-path A --commit SHA --path src/api.py --line 12
python .agents/skills/megin/scripts/impact_policy.py search --group-root GROUP --repo-path B --commit SHA --query customer_id --contract-id CUSTOMER --id customer-b-field
python .agents/skills/megin/scripts/impact_policy.py validate-architecture --group-root GROUP --work-id WORK
~~~

These helpers inspect immutable source without running target code or changing
product files. `validate-architecture` needs the draft contract and referenced
discovery/architecture, but does not require a human approval record.

## Actual impact after implementation

Keep the approved architecture immutable. At `quality_ref`, add hashed
`impact_confirmation_ref` to a separate predeclared evidence JSON with:

- `schema: megin-impact-confirmation/v1`, `work_id`, `plan_version`,
  `requirements_revision`, `architecture_sha256` and combined `snapshot`.
- `diff_sha256` and `changed_paths` from `impact_policy.py diff`. The digest
  covers each changed product path's old/new Git-normalized mode/blob, with
  null for addition/deletion. Both staged and final product content must still
  satisfy normal delivery gates.
- `changes`: every changed product path exactly once with `repo_path`, `path`,
  `kind: interface|internal`, concrete `reason` and approved `contract_ids`.
  Changes to known contract source paths must associate that contract;
  interfaces require at least one matching provider contract. The top-level
  `contract_ids` is the sorted union of those associations.
- `searches`: exact output from `confirmation_searches(...)`, tracing those
  actual contract IDs against implemented product bytes plus pinned unchanged
  peers. Rows bind `source_product_sha256`, query and exact matches. The CLI
  `actual-searches --group-root GROUP --work-id WORK` emits searches for all
  planned contracts; retain those for IDs actually used by the changes.
- `repository_impacts`: the approved dispositions, unchanged; `unresolved: []`.

Review, acceptance, delivery and completion all validate this confirmation.
Each v6 review attempt also carries its hashed `impact_confirmation_ref`, and
the raw reviewer transcript locates `- impact_confirmation_sha256: ...`.
Retain that exact report once the attempt is recorded; predeclare up to four
report paths (for example impact-confirmation-0.json through -3.json) before
approval. The latest review binds the same report as quality evidence, so a
writer cannot change classifications after review while keeping product bytes.
Stale bytes, incomplete path classifications, unrelated searches, changed
consumer scope or an unapproved interface block progression. Renew the plan,
architecture, human approval and downstream review/acceptance when impact
expands; preserve prior review attempts and their correction cap.

The independent reviewer reads the actual diff and traces API signatures,
events, data fields, package dependencies, tables and settings across the
whole graph. Validators prove consistency and coverage of stated evidence;
only semantic review can establish that classifications, exclusions and
compatibility assertions are correct. Do not manufacture those judgments from
scanner success or substitute synthetic approvals for a real review/user.
