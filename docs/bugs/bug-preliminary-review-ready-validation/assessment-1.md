# BUG Assessment：bug-preliminary-review-ready-validation

- BUG ID：`bug-preliminary-review-ready-validation`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：缺少 Ready command／source obligations 的 preliminary report 對 generic schema 與 semantics 都是 0 errors，Ready validator 回 2 errors，但 persistence 仍接受。
- Expected：report persistence、Outcome derivation 與 Delivery consumption 都必須載入同一 implementation run 綁定的 Ready handoff，並要求 `validate_review_against_ready` 回 0 errors。
- Impact：不完整的命令或 requirement coverage 可被固化並綁入 Outcome，弱化 spec→plan→review traceability。
- Symptom oracle：任何 Ready validation error 都必須在三個 consumer boundary fail closed。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：從 schema-valid report 移除 Ready coverage 與必要 full command outcomes，保留 generic schema／semantic validity，再呼叫 isolated persistence。
- 結果：`schema_error_count=0`、`semantic_error_count=0`、`ready_error_count=2`、`persistence_accepted=true`。
- Evidence refs：`host-temp:evidence/bug-preliminary-review-ready-validation-diagnosis.json`

## Compare／Trace

- owner function `validate_review_against_ready` 可正確拒絕 mutated report。
- `knowledge_outcome.persist_preliminary_review_report` 與 `_validated_preliminary_review` 未呼叫它。
- Delivery `_validated_knowledge_outcome` 的 preliminary report consumer 同樣只做 generic validation。

## Hypotheses

根因由 differential validator probe 確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：三個 consumer boundary 漏掉 bound Ready handoff 與 owner Ready-review validator。

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-003，受 WP-002 修正完成後再進入 Executing。
- Next falsifiable action／owner：Implementation executor 加入 persistence／Outcome／Delivery 三邊 differential reds，實作 stable bound-Ready load 與 owner validation，重跑 integration、full 與 fresh review。
- 禁止聲明：尚未修復；不得自動 commit／push／merge／deploy。
