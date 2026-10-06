# Single-Repo requirements discovery protocol

Discover the user's desired behavior in one explicitly selected Git repository. The selected Repo is the current Git root or a Repo the user names; never enumerate sibling folders to infer a larger scope. If the selected path is ambiguous, ask which single Repo to inspect before reading files.

## Evidence pass

1. Confirm the Git root and read its `AGENTS.md`, `Codex.md`, README, and relevant local instructions.
2. Read the current source, meaningful tests, configuration, and project knowledge for the reported behavior. Use version history or external primary sources only when needed to establish compatibility or provenance.
3. Record exact Repo-relative paths, observed behavior, test results, branch and full HEAD SHA, and dirty-worktree paths. Preserve relevant user statements as requirements evidence.
4. Separate confirmed behavior, hypotheses, unknowns, constraints, and decisions. Never treat an unreadable or missing source as proof that a capability is absent.
5. Ask focused questions only for decisions that change user-visible behavior, compatibility, scope, or acceptance. Do not ask questions already answered by repository evidence or the user.

## Requirements record

Write `docs/work/<Work ID>/requirements.md` using [requirements-template.md](requirements-template.md). Describe the problem and desired outcome, source-backed current behavior, included and excluded behavior, unresolved questions, risks, and observable Given/When/Then scenarios. Identify relevant error, boundary, recovery, and compatibility cases. Keep each scenario traceable to evidence and a later check.

Project knowledge remains in the selected Repo. The requirements record belongs to that Work ID and is not a substitute for durable documentation. If a requirement clearly needs changes in another repository, describe the dependency and ask whether the user wants a separate Repo workflow; do not inspect or modify that other repository under this contract.

## Exit criteria

Planning may begin when the desired behavior and user-visible scenarios are clear, important risks and dependencies are recorded, and every behavior-changing question is answered or explicitly accepted as an assumption. Otherwise keep the record in `requirements` with `status: awaiting_user` and name the blocking decision.
