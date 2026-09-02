# BUG Assessment：bug-delivery-reviewer-identity-reuse

- BUG ID：`bug-delivery-reviewer-identity-reuse`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：Required overlay 的 preliminary 與 final implementation review 可以宣告相同 `attestation.agent_id`，Delivery 仍接受並完成 knowledge／terminal gate。
- Expected：preliminary 與 final review 必須由不同 fresh session／Reviewer identity 產生；相同 agent ID 必須 fail closed。
- Impact：同一 reviewer 可自我複核，繞過雙人 fresh review 的獨立性保證，使錯誤或偏差沒有真正第二視角。
- Symptom oracle：只要 preliminary 與 final `agent_id` 相同，required knowledge review transition 必須回 `INVALID_KNOWLEDGE_REVIEW`；不同且各自有效時仍通過。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：只把既有 preliminary fixture 的 `agent_id` 從 `preliminary-fresh-reviewer` 改為 final fixture 的 `fresh-reviewer`，其餘 bytes／commands／snapshots 不變後重跑完整 required-overlay test。
- 固定條件與樣本：1/1 isolated test 通過，0 failures／0 errors，且 `same_agent_preliminary_and_final=true`。
- Evidence refs：`host-temp:evidence/bug-delivery-reviewer-identity-reuse-diagnosis.json`

## Compare／Trace

- 已核准 contract：implementation reviewer contract 明定第二位、不同的 fresh Reviewer，preliminary 與 final 使用不同 fresh session。
- 最小案例：preliminary 與 final 兩份 report 都 schema-valid，但 `attestation.agent_id` 相同。
- Data／control flow：Outcome 綁定 preliminary report → Delivery 分別驗證 preliminary 與 terminal final report → 沒有跨 report identity comparison → 相同 reviewer 被接受。

## Hypotheses

根因已由單一欄位變更後 gate 結果不變確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：Delivery 只做每份 report 的局部有效性驗證，缺少 preliminary／final `attestation.agent_id` 不相等的跨 artifact invariant。
- Evidence refs：`host-temp:evidence/bug-delivery-reviewer-identity-reuse-diagnosis.json`

## Risks／Safety

- Security／privacy／data risk：否
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；這是 WP-003 required knowledge review gate 的直接缺陷，既有 Requirements 與 Plan 已要求不同 fresh Reviewer。
- Next falsifiable action／owner：Implementation executor 保持 Fixing，新增 same-agent regression red，在 terminal validation 比較已持久化 preliminary／final identities，並重跑 Delivery、Implementation consumer 與 fresh review。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。

