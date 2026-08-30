# Runtime context-load report

Development evidence only. Byte counts are UTF-8 with LF-normalized line endings so the comparison is independent of Windows checkout conversion. “Before” is base HEAD 7353419975c5a0df47bf28697b419f643c890fee; “after” is the current worktree. Maintenance references, schemas, scripts, tests and reports are excluded.

## Aggregate

| Runtime bundle | Before | After | Delta |
|---|---:|---:|---:|
| delivery-orchestrator | 14,914 | 14,841 | -73 |
| requirements-discovery | 22,410 | 20,613 | -1,797 |
| implementation-execution | 39,509 | 41,967 | +2,458 |
| Total | 76,833 | 77,421 | +588 |

Technical Planning runtime files are unchanged; only its maintenance validator/tests and shared Ready fixture changed.

The 588-byte aggregate increase is explained by the Implementation-owned terminal evidence contract added after adversarial review: physical capability/baseline/integrity records, exact command-output and review-output sets, source/WP continuity, six ordered terminal witnesses, snapshot binding, breaker-chain continuity, and explicit external-diff/textconv suppression are now runtime obligations rather than validator-only assumptions. Delivery and Requirements together remove 1,870 bytes; the net increase is the remaining cost of making those completion semantics discoverable and enforceable.

## Delivery branches

| Branch | Before | After | Delta |
|---|---:|---:|---:|
| Common identity / resume | 10,649 | 8,064 | -2,585 |
| New work / generation | 10,649 | 11,248 | +599 |
| Stage routing | 7,631 | 7,161 | -470 |

The new-work branch adds 599 bytes because creation now has its own complete preflight/post-verification contract and the evidence-backed `GIT_TRUST_REQUIRED` authorization route. Resume no longer loads those creation-only bytes. Stage routing remains smaller while adding only the terminal physical-verification handoff required to enforce Complete.

## Requirements branches

| Branch | Before | After | Delta |
|---|---:|---:|---:|
| Common exploration | 6,275 | 5,513 | -762 |
| High-risk discovery | 12,101 | 7,208 | -4,893 |
| Standard Candidate delivery | 22,410 | 18,918 | -3,492 |
| High-risk Candidate delivery | 22,410 | 20,613 | -1,797 |

High-risk discovery now loads only its dedicated criteria. Final high-risk quality intentionally combines the general and high-risk contracts.

## Implementation branches

| Branch | Before | After | Delta |
|---|---:|---:|---:|
| Standalone Preflight, including producer Ready contract | 23,704 | 20,267 | -3,437 |
| Orchestrated Preflight | 23,704 | 21,897 | -1,807 |
| Resume / revision Preflight | 23,704 | 22,385 | -1,319 |
| Standard execution / fixing | 11,602 | 10,381 | -1,221 |
| Greenfield first-red execution | 11,602 | 12,095 | +493 |
| Verification / review | 12,930 | 14,406 | +1,476 |
| Terminal delivery | 10,824 | 11,863 | +1,039 |

The greenfield branch gains an explicit producer gate, mutually exclusive sentinel rule and branch completion condition. Review grows because snapshot equality, output ownership, direct-source coverage, stable finding identity and breaker progress are one coherent review semantic. Terminal delivery grows because the six witnesses and physical evidence bindings must be known before Complete. Preflight and the standard execution branch remain materially smaller; the bundle-level increase is fully attributable to the new enforceable evidence semantics above.
