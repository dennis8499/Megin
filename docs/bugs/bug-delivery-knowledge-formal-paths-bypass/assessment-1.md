# BUG Assessment：bug-delivery-knowledge-formal-paths-bypass

- BUG ID：`bug-delivery-knowledge-formal-paths-bypass`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：Delivery required knowledge gate 接受缺少 `formal_paths` 的 Requirements 與 Planning Ready receipts，並把不含 manifest 的 promotion binding 寫入 record。
- Expected：每個 Ready receipt 都必須有 canonical、Git-eligible 的 `formal_paths`；Requirements 必須精確綁定目前 revision，Planning 必須精確等於 Technical Planning owner 驗證的完整 Ready-plan bundle。
- Impact：不完整或錯誤的 formal artifact manifest 可繞過 Delivery phase gate，使 implementation 在沒有可重現完整 plan bundle 的情況下開始，破壞跨 owner 的資料完整性與交付可追溯性。
- Symptom oracle：同一缺少 `formal_paths` 的 receipt 必須由 Delivery 回報 `INVALID_KNOWLEDGE_PROMOTION`；有效完整 manifest 仍須通過並保存 exact `formal_paths`。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：執行現有 required-stage-gates fixture，攔截兩次 promotion binding；確認 receipt 與回存 binding 都沒有 `formal_paths`，但 transition 仍成功。
- 固定條件與樣本：同一 worktree snapshot；1/1 fixture 通過且記錄 2/2 invalid receipts 被接受。
- 對照：將完全相同 receipts 交給 project-knowledge `validate_stage_promotion`，2/2 均以 `MISSING_KNOWLEDGE_GATE` 拒絕。
- Evidence refs：`host-temp:evidence/bug-delivery-knowledge-formal-paths-bypass-diagnosis.json`

## Compare／Trace

- 已核准 contract：Delivery SKILL 與 Technical Planning delivery protocol 都要求 Planning receipt 的 `formal_paths` 精確等於完整 owner-validated Ready-plan manifest；project-knowledge consumer 已實作同一規則。
- 最小案例：test fixture 的 `persist_knowledge_receipt` 產生沒有 `formal_paths` 的 Ready receipt；Delivery 的 positive gate test 接受它。
- Data／control flow：`transition_record` → `_validated_knowledge_promotion_binding` → 驗證 schema／stage／work／approval／lint/status，但略過 `formal_paths` → 回存 binding 也略過欄位 → phase advance。

## Hypotheses

根因已由同一 receipt 的雙 consumer 對照確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：Delivery consumer 與 project-knowledge owner validator 發生契約漂移；前者重複但漏掉 manifest 驗證，且其 positive fixture 把遺漏固化為 green。
- Evidence refs：`host-temp:evidence/bug-delivery-knowledge-formal-paths-bypass-diagnosis.json`

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；這是 WP-003 Delivery knowledge overlay 的直接契約缺陷，修正履行既有需求與計畫，不需要 Requirements／Plan reapproval。
- Next falsifiable action／owner：Implementation executor 保持 Fixing，先新增缺失／錯誤／不完整 manifest 的 regression reds，再讓 Delivery 使用 owner-equivalent validation 並保存 exact `formal_paths`，重跑 producer／consumer／Delivery 全量與 fresh review。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。

