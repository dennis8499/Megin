# BUG Assessment：bug-knowledge-page-closed-contract-lint

- BUG ID：`bug-knowledge-page-closed-contract-lint`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：baseline lint passed；加入 `knowledge-page/v1` closed schema 禁止的 member 後，schema validator 回 1 error，但 full lint 仍 passed、0 diagnostics。
- Expected：sealing 與 full lint 都必須對 page 及 nested claim／source objects 執行同一 closed schema，任何 error 產生 `PAGE_CONTRACT_INVALID` 並 fail closed。
- Impact：非契約 knowledge state 可進入 canonical tree，後續 query、repair、Candidate 與跨平台結果可能建立在未知欄位語意上。
- Symptom oracle：任一 unknown page／claim／source member 必須使 sealing 與 lint 失敗；合法 page 不增加 diagnostics。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：建立 lint-clean isolated knowledge repo，在一個 valid page sidecar 加入單一 unknown member，再比較 closed schema 與 full lint。
- 結果：baseline passed／0；schema errors 1；mutated lint passed／0。
- Evidence refs：`host-temp:evidence/bug-knowledge-page-closed-contract-lint-diagnosis.json`

## Compare／Trace

- schema `$defs.page` 與 nested definitions 均為 `additionalProperties=false`。
- `lint_repository` 只手動檢查已知欄位，不執行 schema。
- `_validate_stage_semantics` 也只檢查 sidecar claims／evidence class，implementation stage 甚至在 page validation 前返回。

## Hypotheses

根因由 clean baseline、單變量 mutation 與 schema/lint differential 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：runtime governance 未將 authoritative closed page schema 納入 seal 與 lint boundaries。

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-002。
- Next falsifiable action／owner：Implementation executor 加入 page／claim／source unknown-member reds，集中 runtime schema validator，於 seal 與 full lint 共用並重跑 BDD-015 與 full suites。
- 禁止聲明：尚未修復；不得自動 commit／push／merge／deploy。
