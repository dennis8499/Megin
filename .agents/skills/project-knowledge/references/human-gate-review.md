<!-- authority: human-gate-review -->

# Human approval Gate review contract

This file is the single source of truth for every Megin Gate that asks a human
for approval in Chat. It applies to Requirements, Plan, Knowledge/Apply,
bootstrap and repair Candidates, the BUG assessment co-gate, and a bulk-edit
occurrence map. Automatic validation, fresh review, test, performance,
security, lint, schema, and CI Gates keep their complete machine output and
existing pass/fail authority.

## Required sequence

1. The producer seals the complete Candidate as create-only, unapproved files.
   The immutable Candidate directory contains `candidate.json`, every complete
   `postimages/` file, every applicable `review-files/` supporting or automatic
   evidence file, and `review.json`.
2. The review adapter stable-reads every linked file, rejects redirects,
   collisions, missing bytes, source or preimage drift, and verifies each byte
   count and SHA-256 before producing Chat output. It then repeats the complete
   Candidate, source, preimage, manifest-file, and review validation pass; any
   cross-file change before return fails closed.
   Target paths are globally unique across postimage and review-file roles
   under case-insensitive comparison; a cross-role collision fails before any
   Candidate is published.
3. Chat renders only the closed `human-gate-summary/v1` projection. It must
   contain exactly these seven human-facing categories: `gate`, `summary`,
   `risk_and_compatibility`, `validation`, `review_bundle`, `identity`,
   and `prompt`. A newly sealed Candidate carries
   `review_projection: gate-specific-summary/v1`; its `summary` includes a
   deterministic purpose and change description derived from its stage and
   applicable sealed material, plus operation counts. It must not name an
   artifact that is absent from the review bundle. The
   `risk_and_compatibility.material` object contains the three closed nullable
   projections described below.
4. `review_bundle` gives a directly openable native path for `review.json`
   and for every Candidate/manifest entry. It never embeds an artifact, diff,
   postimage, or raw command output.
5. After an explicit approval, the owner stable-reads the same complete bundle
   again. Only then may the existing Ready, promotion, apply, or phase
   transition authority run.

The one canonical decision prompt is:

> Approve this exact review bundle or request modifications.

Owners reference this prompt; they do not copy it or introduce a second
approval question.

## Exact identity and lifecycle

The Chat projection identifies the Gate status as `Candidate` and binds the
repository, stage, work/mission, promotion revision, Candidate ref, Candidate
payload SHA-256, review SHA-256, prospective actor/evidence binding, and the
complete manifest. Prospective binding is not approval. The approval command
must supply the current Candidate ref, approval actor/evidence, and review
SHA-256.

Review files are disposable host-registry evidence, not Ready artifacts and
not canonical knowledge. Sealing them must not write product, canonical
knowledge, Ready receipts, or delivery phase state.

## Composite bundle inventory

- Requirements: the Requirements primary plus Knowledge postimages and
  deterministic finalizers; for a BUG delivery, the assessment Markdown and
  `bug-assessment/v1` JSON are prospective create-only postimages in that same
  Requirements Gate. Their canonical `docs/bugs/**` paths stay absent until
  the shared approved apply materializes the assessment pair and Requirements
  atomically; pre-existing or drifted targets fail the whole apply with no
  partial write.
- Plan: the primary plan, `handoff.json`, every supporting/contract artifact,
  Knowledge postimages and deterministic finalizers; a bulk-edit
  `occurrence_map.yaml` or `occurrence_map.yml` is supporting content in
  this same Plan Gate.
- Knowledge/Apply: `candidate.json`, all complete `postimages/`, deterministic
  promotion finalizers, `review.json`, linked full automatic validation evidence,
  and exact identity. A repair Candidate includes the complete `knowledge-lint/v1`
  JSON as an immutable `review-files/` entry while Chat shows only its outcome,
  diagnostic count/codes, and direct link.
- Implementation handoff: the latest `implementation-outcome/v1` and the
  sealed Knowledge Candidate are reviewed through the existing post-
  Implementation Knowledge Gate; automatic preliminary/final reviewer
  evidence is not converted into Chat summary evidence.

Every applicable file remains in one manifest and one approval scope,
regardless of payload size.

## Gate-specific safe projection

The projection is deterministic from the sealed files. It never accepts prose
written specifically for Chat and never copies arbitrary values from a full
artifact.

- Requirements plus BUG assessment exposes only verdict, severity, source
  relation, reproduction/root-cause status, disposition, the
  security/privacy/data-risk boolean, and a fixed classification-risk enum.
  Observed/expected behavior, impact, hypotheses, evidence text, next action,
  and Markdown remain file-only.
- Plan plus occurrence map exposes only the allowlisted `change_mode`, whether
  manual review is required, the count of entries explicitly classified
  `manual_review`, and a fixed classification-risk enum. Target/replacement,
  paths, category names, reasons, exceptions, and moves remain file-only.
- Implementation or BUG Outcome exposes only work kind, result, knowledge
  decision, and counts for changed paths, deviations, residual risks, and
  follow-up items. Outcome summary prose and evidence remain file-only.
- Bootstrap exposes only the four repository-classification path lists copied
  into and hashed with `candidate.json`; lint repair derives its outcome,
  diagnostic count, and distinct codes from the sealed automatic lint file.
  Initial and resumed review commands therefore project the same review-SHA-
  bound summary.
- An implementation-stage Candidate uses Outcome-specific purpose and change
  text only when a valid `implementation-outcome/v1` is present in the sealed
  review material. Without one, it identifies the Gate as a standalone
  Knowledge Candidate and leaves `implementation_outcome` null.

An inapplicable projection is `null`. This keeps the Chat object closed and
stable while making material Gate-specific status visible without revealing
the full Candidate.

## Failure, revision, and compatibility

Missing or unreadable files, path ambiguity, redirects, hash/byte-count drift,
source or preimage drift, manifest drift, a missing review digest, or an
ambiguous/stale approval fail closed with zero Ready/apply/product/phase
mutation. Preserve the old bytes, seal a new immutable revision with a new
prospective evidence token, and present a new Summary-only Chat projection.
Never paste the full payload into Chat as a fallback.

A sealed Candidate created before the projection marker remains valid: absence
of `review_projection` deliberately regenerates its original generic
`review.json` bytes, so an already reviewed Candidate is not rewritten or
silently reinterpreted. A pending legacy Candidate without `review.json` must
still return `LEGACY_RESEAL_REQUIRED`; it cannot be approved or applied.
Historical Ready receipts, canonical knowledge, Complete records, and
automatic Gate evidence remain byte-compatible and are not migrated.
