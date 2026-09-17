# BUG Assessment: bug-delivery-plan-revision-gap

- BUG ID: bug-delivery-plan-revision-gap
- Revision: 2
- Verdict: confirmed
- Severity: medium
- Relation: intake
- Source Work: none
- Disposition: delivery

## Observed, expected and impact

- Observed: Delivery rejects approved Candidate-4 plan-3 with INVALID_REVISION and requests plan/, which is below Candidate-3 plan-2. The registry remains planning/active with no new event.
- Expected: revisions remain monotonic; the next candidate after plan-2 should use plan-3 even if a superseded plan/ directory is absent from the new generation.
- Impact: this feature is blocked before product files change; deployed products and user data are unaffected.
- Symptom oracle: transition returns INVALID_REVISION and run.json gains no event.

## Reproduction

- Status: reproduced
- Steps: transition the current generation-2 planning record using the Ready Candidate-4 plan-3 handoff.
- Fixed state: the record is planning/active and contains Candidate-3 plan-2; generation 2 has plan-2 and plan-3 but no plan/; generation 1 had plan/.
- Evidence: host-temp:bug-diagnosis/repos/c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99/works/work-20260916-natural-language-sdlc-v2/bug-delivery-plan-revision-gap/revision-1/evidence/transition-failure.json and host-temp:delivery-orchestrator/repos/c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99/works/work-20260916-natural-language-sdlc-v2/run.json

## Compare and trace

The Candidate-3 plan-2 transition succeeded in sequence 6 in generation 1. Generation 2 materializes the current Ready upstream, so the superseded plan/ directory is absent. The helper scans from revision 1 and reports the missing path, while record validation requires revisions to increase. Revision 1 goes backwards, revision 2 is already approved, and revision 3 is rejected by the gap check.

## Root cause

- Status: confirmed
- Confidence: high
- Summary: revision allocation scans from the lowest unused path across generations, but later generations materialize only current approved upstream. It must search for the smallest available revision after the maximum recorded revision and retain collision checks for unrecorded candidates.
- Evidence: host-temp:bug-diagnosis/repos/c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99/works/work-20260916-natural-language-sdlc-v2/bug-delivery-plan-revision-gap/revision-1/evidence/root-cause.json and host-temp:bug-diagnosis/repos/c02a0b6fa293bdbf99be435da6898d63abd509d25d61bdc9b4409ea9b8210b99/works/work-20260916-natural-language-sdlc-v2/bug-delivery-plan-revision-gap/revision-1/evidence/transition-failure.json

## Risk and disposition

- Security, privacy or data risk: no
- Disposition: delivery, for the independently authorized revision-allocation repair; the affected feature returns for a refreshed plan after this fix.
- Next action: Plan and implement the bounded revision-allocation repair with local-only validation, then refresh and reapprove the affected feature plan.
- Not fixed: do not mutate the Delivery registry directly or bypass its transition gate.
