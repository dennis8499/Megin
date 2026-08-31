<!-- authority: bug-assessment-human-shape -->

# BUG assessment 模板

依 [Assessment 契約](assessment-contract.md)填入完整內容並移除提示。Markdown 是人類閱讀面；enum、hash、binding 與狀態以 JSON sidecar 為 machine authority。

```markdown
# BUG Assessment：〔bug_id 與短題目〕

- BUG ID：`bug-...`
- Revision：N
- Verdict：`confirmed | likely | not-a-bug | insufficient-evidence`
- Severity：`critical | high | medium | low`
- Relation：`intake | current-scope | affecting-current-work | unrelated`
- Source Work：`work-...` 或無
- Disposition：〔schema enum〕

## Observed／Expected／Impact

- Observed：〔可觀察事實〕
- Expected：〔來源支持的期望〕
- Impact：〔角色、範圍、頻率與風險〕
- Symptom oracle：〔如何判斷存在／不存在〕

## Reproduction／Amplification

- Status：`reproduced | intermittent | not-reproduced | not-attempted`
- 最小步驟：〔精確步驟〕
- 固定條件與樣本：〔flaky／效能適用〕
- Evidence refs：〔不含秘密的 refs〕

## Compare／Trace

- 最近正常／目前異常：〔有 evidence 的差異〕
- 最小案例：〔刪除過程與邊界〕
- Data／control flow：〔第一個 invariant 破裂位置〕

## Hypotheses

| Rank | ID | Causal statement | Variable | Prediction | Falsifier | Outcome | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | H-001 | 〔內容〕 | 〔單一變因〕 | 〔若為真〕 | 〔推翻條件〕 | `untested` | 〔ref〕 |

## Root cause confidence

- Status：`confirmed | hypothesized | unknown`
- Confidence：`high | medium | low`
- Summary：〔不把 correlation 當因果〕
- Evidence refs：〔refs〕

## Risks／Safety

- Security／privacy／data risk：是／否
- Redacted summary：〔適用時〕
- Secure evidence refs：〔適用時〕
- Named human reviewer：〔適用時〕

## Disposition 與下一步

- Disposition：〔為何符合 relation／verdict〕
- Next falsifiable action／owner：〔唯一下一步〕
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。
```
