---
name: megin-verification-before-completion
description: Prove a Megin change is complete with fresh commands, scenarios, review evidence, and snapshot checks. Use for final verification, release readiness, 完成前驗證、驗證交付; do not skip failed or stale obligations.
---

# Megin verification

Load the exact approved scope, acceptance, commands, latest writer reports, fresh review verdict,
knowledge scope, and delivery destination. Inspect status, diff, branch, and snapshot; reject scope
drift or stale evidence. Run every approved focused, related, full, static, build, contract, and
scenario command that applies, recording the exact command, exit status, output path, and digest
where required.

Confirm the fresh reviewer approved the same snapshot and that knowledge claims retain source paths,
digests, certainty, and conflict results. A failed command returns the affected task to implementation
for a bounded fix, then requires a fresh review and verification.

When all automated obligations pass, write a final verification record and set `status:
awaiting_user` with `phase: acceptance`. Product files, knowledge, staging, and commit state remain
unchanged until the human acceptance response.
