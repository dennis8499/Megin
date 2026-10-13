# Requirements discovery protocol

Select the Repo/Group root using [repository-workflow.md](repository-workflow.md). First pass is read-only. Clarify problem, audience, outcome, constraints and observable acceptance before prescribing a solution.

Resolve discoverable facts by reading applicable instructions, current behavior, meaningful tests and documentation. Use relevant primary research when facts are externally defined; preserve source paths, versions and uncertainty. Do not invent research obligations for ordinary local facts.

In Group mode safely enumerate all real direct-child Git roots and record their purposes/relationships; do not follow links or restrict discovery to configured Repos. In Repo mode stay within the selected root. Keep facts, assumptions, requirements and technical suggestions separate. Give every requirement a REQ ID. Ask the highest-impact prerequisite-ready product question when unresolved behavior/scope/acceptance blocks progress.

Save requirements.md with source-backed current behavior, scope/exclusions, decisions, risks and observable scenarios. Blocking assumptions/questions keep requirements/awaiting_user; no planning handoff until intent is stable. Nonblocking uncertainty needs a reason and remains visible.

Hand off to architecture exploration, which performs full file/entrypoint reconciliation, freezes discovery and creates architecture evidence before planning. Technical planning chooses actual change Repos, fixes BDD/check/path obligations and obtains exact-plan human approval. Discovery completion is not implementation approval.

Project knowledge stays in established Repo documentation; centralized Group work records reference it. Historical work preserves its original discovery contract.
