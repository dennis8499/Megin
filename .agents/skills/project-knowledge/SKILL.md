---
name: project-knowledge
description: Search and govern repository-local engineering knowledge. Use before requirements, planning, implementation, BUG diagnosis, or ad-hoc engineering answers; also use to bootstrap, lint, review, approve, apply, or recover the canonical Markdown Wiki.
---

# Project knowledge

Use the offline public seam at `scripts/knowledge_cli.py`. Git-eligible repository files are raw evidence, `docs/knowledge/**/*.md` is the human retrieval layer, JSON sidecars are the provenance contract, and Git is the formal history. The host-temp registry contains disposable sealed Candidates, transaction journals, and recovery material; it is never canonical knowledge.

## Choose one branch

- `query`: read-only context before requirements, planning, implementation, BUG work, or an ad-hoc answer.
- `bootstrap`: classify only owner-validated terminal evidence, Candidate, conflicts, and unknowns; seal one lint-clean baseline Candidate containing any contested quarantine without changing the repository.
- `lint`: validate provenance, lifecycle, links, IDs, contradictions, index, and promotion log; it may seal a repair Candidate but never applies it.
- `candidate`: validate full postimages and seal an immutable Candidate for human review.
- `apply`: after a new explicit human approval of the exact sealed payload, transactionally apply it and run post-apply lint.
- `recover`: when any command returns `RECOVERY_REQUIRED`, finish or roll back the recorded transaction before doing anything else.

Do not combine branches in one implicit action. Requirements may co-promote one current revision; planning must co-promote the entire owner-validated Ready-plan manifest, and each Ready receipt records exact `formal_paths`. Both use their owner skill's same approval gate. Implementation and BUG first bind a physically persisted preliminary fresh report to a create-only Outcome revision; their Candidates then wait for a different final fresh review and the separate knowledge approval gate.

## Query protocol

1. Run a stage-specific query before asking the first requirements question or changing implementation behavior:

   ```text
   python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage requirements --query "user intent"
   ```

2. Accept at most five results. Prefer `authority: canonical`, but treat Wiki text as navigation rather than evidence authority.
3. Re-read every returned `source_refs.path` at its locator and verify it still supports the intended statement before writing a formal artifact or code.
4. Exclude stale, contested, superseded, redirected, ignored, hash-drifted, or self-referential evidence. If verification fails, run `lint`; do not silently fall back to the claim.
5. Cite the raw repository path and locator in the produced requirement, plan, implementation decision, or BUG evidence.

Use the stage values `requirements`, `planning`, `implementation`, `bug`, or `ad-hoc`. Retrieval is deterministic for the same repository bytes and query; `generated_at` does not affect ranking. Repeated queries may reuse only a process-local, non-persisted match index whose key binds the complete staged Git inventory plus stable bytes for every modified, deleted, or untracked eligible path; byte drift invalidates it before reuse. Immediately before return, every selected result path, canonical sidecar metadata, and provenance is re-read with stable-file metadata, hash, locator, and excerpt verification so a cached match cannot outlive either its source bytes or lifecycle contract.

## Candidate and approval protocol

A draft is a closed `knowledge-candidate-draft/v1` object with `stage`, `work_id`, explicit `decision: change|no-change`, verified `source_snapshot`, and `operations`. Each operation contains `kind`, normalized repository `path`, and the complete UTF-8 postimage. Before sealing, allocate a prospective approval actor and stable evidence token. This binding identifies the payload the human will review; it is not itself approval.

```text
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py candidate --repo . --draft <host-temp-draft.json> --approval-actor <expected-actor> --approval-evidence <stable-evidence-token>
```

The seal always adds the exact `docs/knowledge/log.md` and Ready receipt pre/postimages to the digest and display. Present all returned `affected_paths`, complete `postimages`, `approval`, `candidate_ref`, and `payload_sha256`. Approval is valid only when the human has seen that exact payload after the latest source and preimage snapshot. A prior plan approval, a conversational “continue,” test success, or reviewer verdict is not knowledge approval unless the owner workflow explicitly binds it as the same requirements/planning gate.

After explicit approval, pass a non-secret actor and evidence reference:

```text
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py apply --repo . --candidate-ref <ref> --approval-actor <actor> --approval-evidence <evidence-ref>
```

Never stage, commit, push, merge, or delete a worktree as part of knowledge promotion. Apply holds the repository promotion lock while it revalidates finalizers, sources, operations, and target preimages; drift detected after initial validation fails before the journal or product writes. A successful apply returns `knowledge-apply/v1`, a persisted Ready receipt, and passing post-apply lint. Drift, a partial write, a secret pattern, or an unexpected target fails closed.

Bootstrap and repair sealing use the same prospective binding and remain read-only until a later exact apply. Plain `lint --repo .` is diagnostic-only; add both binding flags when a repair Candidate is required:

```text
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py bootstrap --repo . --approval-actor <expected-actor> --approval-evidence <stable-evidence-token>
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py lint --repo . --approval-actor <expected-actor> --approval-evidence <stable-evidence-token>
```

## Lifecycle and certainty

- Only Ready requirements, Ready plans, Complete implementations, and valid BUG verification may become canonical.
- Use `required`, `planned`, `observed`, `verified`, or `partial` exactly; do not inflate certainty.
- `partial` BUG knowledge remains unresolved, lists proxy evidence, residual risks, and follow-up, and never claims “fixed” or “resolved.”
- Symmetric contradictions are `contested`; asymmetric links are invalid. `stale`, `contested`, and `superseded` claims never enter automatic context.
- Canonical claims cite raw repository sources, never another `docs/knowledge` page, an index, a log, a Candidate, or chat text.

## Failure handling

The CLI writes one versioned success object to stdout or one `knowledge-error/v1` object to stderr. Exit codes are: `2` invalid input or contract, `3` drift/conflict/safety, `4` dependency or environment, and `5` recovery required. Do not retry with weaker validation. For exit `5`, run:

```text
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py recover --repo .
```

Run `scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp` for a release check. Its BUILD-FULL validation compiles every Git-eligible repository `*.py`, parses every Git-eligible `*.schema.json`, and reports the exact `python_files_checked` and `json_schema_files_checked` inventory counts; a partial skill-local scan is not sufficient. Cross-platform release evidence requires equivalent Windows and Linux reports from `.github/workflows/knowledge-portability.yml`; one local OS result is not Windows/Linux evidence. Machine shapes are defined in `schemas/knowledge-contracts.schema.json`.

