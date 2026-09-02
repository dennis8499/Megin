# BUG Assessment：bug-knowledge-promotion-registry-component-validation

- BUG ID：`bug-knowledge-promotion-registry-component-validation`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：promotion `_candidate_path` 接受經 Windows junction ancestor 取得的普通 `candidate.json`；leaf 不是 link，而既有 component checker 對同一路徑回 true。
- Expected：sealing、loading、applying 都必須從 canonical registry root 逐 component 拒絕 link／junction／reparse，並以 stable regular-file read／create 邊界防止讀寫期間變化。
- Impact：promotion 可能接受或建立 canonical registry tree 外的 Candidate bytes，破壞 sealed identity 與 apply trust boundary。
- Symptom oracle：ancestor junction 必須在 parse／persist 前被拒絕；普通 registry path 維持成功。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在 system-temp 建立 registry，令 `repos/<repo-id>` 是真實 Windows junction，外部 tree 內 leaf 維持普通 file，再呼叫 promotion `_candidate_path`。
- 結果：`ancestor_is_junction=true`、`leaf_is_link=false`、`component_check=true`、`accepted=true`；fixture cleanup exit 0。
- Evidence refs：`host-temp:evidence/bug-knowledge-promotion-registry-component-validation-diagnosis.json`

## Compare／Trace

- `knowledge_delivery` 已有 component walk 與 stable read；promotion loader 仍只以 resolved-relative 與 leaf check 判斷。
- `_persist_candidate` 建立 nested registry paths 時也沒有共用相同 boundary。

## Hypotheses

根因已由真實 junction 與 component checker 對照確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：promotion Candidate load／persist 沒有從 registry root 驗證每個既存 component，也沒有共用 stable file boundary。

## Risks／Safety

- Security／privacy／data risk：否（只證明非敏感 fixture 的完整性邊界缺口）
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；直接屬於 WP-002。
- Next falsifiable action／owner：Implementation executor 新增 Windows junction、ordinary path 與 read／create drift reds，抽出 shared component-safe registry primitives，並重跑 Windows/Linux full。
- 禁止聲明：尚未修復；不得自動 commit／push／merge／deploy。
