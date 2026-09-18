---
name: requirements-discovery
description: Explore a natural-language repository change with read-only evidence, one decision question at a time, explicit alternatives, and a reviewable v2 requirements candidate. Do not use for pure explanations, already-approved implementation, or bug diagnosis.
---

# Requirements Discovery

Use this skill for the WHAT of a large change or a bug repair after diagnosis. Resolve the
target repository explicitly and inspect its own instructions, interfaces, tests, and history
without writing product files. Record the request digest, sources, constraints, acceptance
criteria, in/out scope, risks, and open questions in the v2 state candidate.

Begin with a read-only repository and Project Knowledge preflight. Resolve facts from evidence
before asking the user. When multiple decisions remain, rank them by impact, uncertainty, and
irreversibility; ask exactly one frontier question per turn. For a real design choice, show two or
three approaches and recommend one with its consequence. Preserve the user's language in the
conversation and candidate prose.

The candidate should make the approval easy to read: goal, in/out scope, acceptance, risks,
affected paths/interfaces, base branch and SHA, workspace mode, finish mode, test commands,
knowledge scope, and publication destination. The complete immutable bundle remains the authority;
the chat summary is only a projection.

Do not create a workspace, branch, product artifact, or canonical knowledge change before the
requirements gate. A candidate is not Ready until the user approves the exact current bundle.
If evidence is insufficient, keep the candidate pending or return a concrete question; do not
invent requirements. A changed scope or acceptance criterion creates a new candidate digest.
