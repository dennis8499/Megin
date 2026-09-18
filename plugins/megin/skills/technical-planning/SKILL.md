---
name: technical-planning
description: Turn an approved Megin v2 requirements candidate into a bounded implementation plan with dependency-ordered work packages, TDD commands, review evidence, and an explicit workspace/finish destination. Use after requirements approval.
---

# Technical Planning

Use this skill after the Requirements gate for a large change. Read the target repository and
the approved requirements bundle directly. Produce a plan that names interfaces, work packages,
dependencies, allowed paths, focused and full test commands, evidence locations, knowledge scope,
and the approved Git publication destination.

Planning is read-only until the Planning gate. The Ready plan digest binds every work package and
command to the requirements identity. Do not silently add architecture, data, permission,
dependency, or publication scope. If the plan cannot prove a small bounded path, keep it on the
large route and request a new approval for any changed candidate.

Each package must state the exact allowed paths, interfaces, acceptance evidence, focused/related/
full commands, dependencies, and the writer/reviewer handoff. The plan carries the approved
current-directory or worktree mode and `unstaged`, `commit`, or `draft-pr` finish mode forward;
changing either requires a new candidate revision and approval.
