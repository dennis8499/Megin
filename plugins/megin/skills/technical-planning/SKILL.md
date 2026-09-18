---
name: technical-planning
description: Turn an explored Megin v3 request into a bounded plan with executable Gherkin, dependency-ordered tasks, TDD commands, review evidence, and an explicit local delivery destination.
---

# Technical Planning

Use this skill after read-only exploration and before the single plan approval. Read the target
repository, Project Knowledge, and current candidate directly. Produce a plan that names interfaces, work packages,
dependencies, allowed paths, focused and full test commands, evidence locations, knowledge scope,
and the approved Git publication destination.

Planning is read-only until the Planning gate. The Ready plan digest binds every work package and
command to the requirements identity. Do not silently add architecture, data, permission,
dependency, or publication scope. If the plan cannot prove a small bounded path, keep it on the
large route and request a new approval for any changed candidate.

Each package must state the exact allowed paths, interfaces, acceptance evidence, focused/related/
full commands, dependencies, and the writer/reviewer handoff. Every external behavior gets one
stable scenario ID and one executable `.feature` source; changing behavior, scope, or acceptance
requires a new plan version and approval.
