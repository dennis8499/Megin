# Workflow records

Use the complete Repo v3 / Group v5 headers in [workspace-workflow.md](workspace-workflow.md). One Work ID belongs to one selected root and keeps workflow.md, requirements.md, plan-<version>/plan.md, quality-contract.json and evidence beneath docs/work/<Work ID>/.

workflow.md is the status surface. Preserve dated progress and the earliest incomplete action. Requirements precedes architecture, which precedes planning and exact-plan approval. Only approved change Repos appear in the Group workflow/contract; discovery and architecture still cover all valid Repos.

Predeclare every evidence path before approval. Requirements, architecture, plan, contract and BDD obligations are immutable under that approval. Snapshot changes invalidate downstream review/check/acceptance evidence; preserve attempts when a new version is approved. Initial review is round 0 with up to three corrections.

Complete means the accepted feature commits and final tree pass completion, delivery evidence is saved, workflow is delivery/complete and locks are released. Partial multi-Repo delivery records existing commits and remaining actions. Legacy Work IDs retain their original schema and package until complete.
