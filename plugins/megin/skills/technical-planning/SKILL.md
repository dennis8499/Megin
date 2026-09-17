---
name: technical-planning
description: Turn an approved requirements candidate into a bounded, evidence-linked implementation plan without mutating the target repository.
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
