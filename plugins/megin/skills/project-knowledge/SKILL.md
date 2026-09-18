---
name: project-knowledge
description: Search and review target-project knowledge for a Megin v2 delivery with source provenance, conflict checks, and explicit promotion boundaries.
---

# Project Knowledge

Resolve the target repository and its knowledge layout explicitly. Query and lint are read-only;
do not assume a `.agents/skills` tree or a fixed path from this plugin. Every proposed claim keeps
its source path, source digest, certainty, and the Work ID that supports it.

For v2, the approved `knowledge_scope` is the only promotion boundary. After implementation and
fresh product review, create a candidate and compare pre/post snapshots. Promote automatically only
when source, schema, lint, conflict, and scope checks all pass. Preserve conflicting or unsupported
claims as pending decisions and leave existing canonical claims unchanged. Never treat a passing
test or an old v1 approval as knowledge authorization.
