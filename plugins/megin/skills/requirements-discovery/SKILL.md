---
name: requirements-discovery
description: Explore an approved repository request with read-only evidence, produce a reviewable requirements candidate, and keep approval tied to its digest.
---

# Requirements Discovery

Use this skill for the WHAT of a large change or a bug repair after diagnosis. Resolve the
target repository explicitly and inspect its own instructions, interfaces, tests, and history
without writing product files. Record the request digest, sources, constraints, acceptance
criteria, in/out scope, risks, and open questions in the v2 state candidate.

Do not create a worktree, branch, product artifact, or canonical knowledge change before the
requirements gate. A candidate is not Ready until the user approves the exact current bundle.
If evidence is insufficient, keep the candidate pending or return a concrete question; do not
invent requirements. A changed scope or acceptance criterion creates a new candidate digest.
