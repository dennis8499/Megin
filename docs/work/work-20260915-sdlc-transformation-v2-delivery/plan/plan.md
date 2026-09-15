# SDLC Transformation v2 Implementation Plan

## Goal

Deliver a portable `sdlc` Codex plugin with task classification, durable cross-project state, supervised implementation skills, verification, knowledge review, and Git draft-PR handoff.

## Architecture

The plugin owns portable skills, schemas, and a standard-library CLI. Each target repository opts in with `sdlc init`; runtime records live in a user state directory keyed by repository identity and Work ID. Existing repository-local v1 skills and records remain compatible and are not rewritten.

## Work packages

1. Package the plugin manifest and reusable skills.
2. Implement the portable CLI, v2 state schema, classification, and safe Git lifecycle.
3. Integrate the new routing and delegation rules into the repository-local contracts.
4. Add tests, documentation, and cross-platform validation.

## Verification

Run plugin validation, portable CLI unit tests in clean Git repositories, repository quick checks, and the existing owner contract suites. Verify that no target repository needs `.agents/skills` from this repository.
