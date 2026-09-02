# BUG Assessment：bug-knowledge-candidate-ancestor-redirect

- BUG ID：`bug-knowledge-candidate-ancestor-redirect`
- Revision：1
- Verdict：`confirmed`
- Severity：`high`
- Relation：`current-scope`
- Source Work：`work-20260831-project-knowledge-system-19202d78`
- Disposition：`current-run`

## Observed／Expected／Impact

- Observed：sealed Candidate loader 會跟隨 registry 內的 ancestor Windows junction；ancestor 是 reparse point、leaf 不是 symlink 時仍回傳可讀 Candidate path。
- Expected：從 canonical registry root 到 Candidate leaf 的任何 symlink／junction／reparse component 都必須 fail closed，並使用 stable no-follow read 防止交換競態。
- Impact：review／delivery snapshot 可能讀取 registry 外部的 Candidate bytes，破壞 sealed Candidate identity、資料完整性與 promotion 信任邊界。
- Symptom oracle：ancestor junction／symlink、leaf redirect 與 read-time swap 都必須以穩定 Candidate error 拒絕；普通 registry path 仍成功。

## Reproduction／Amplification

- Status：`reproduced`
- 最小步驟：在隔離 temporary registry 下把 `repos/<repo_id>` 建為指向 external candidate tree 的真實 Windows junction，leaf 保持普通檔案，再呼叫 `_candidate_path`。
- 固定條件與樣本：reviewer 1/1 與主代理獨立 probe 1/1 都接受 redirected Candidate；`ancestor_is_junction=true`、`leaf_is_symlink=false`。
- 對照：既有 shared `knowledge_promotion._redirected` 對同一 path 回 true。
- Evidence refs：`host-temp:evidence/bug-knowledge-candidate-ancestor-redirect-diagnosis.json`

## Compare／Trace

- 最近安全案例：repository query 與 promotion paths 已逐 component 檢查 redirect；Candidate loader 沒有套用同等 contract。
- 最小案例：registry root 普通、`repos/<repo_id>` 是 junction、Candidate leaf 是普通 file。
- Data／control flow：`build_knowledge_snapshot` → `_candidate_path` → `default_registry_root` 只檢查 root → leaf `is_symlink/is_file` → junction ancestor 被 transparently follow。

## Hypotheses

根因已由真實 junction 與 shared detector 對照確認，無開放假設。

## Root cause confidence

- Status：`confirmed`
- Confidence：`high`
- Summary：Candidate loader 缺少從 registry root 到 leaf 的 component walk 與 stable no-follow read；leaf-only check 無法偵測 ancestor junction。
- Evidence refs：`host-temp:evidence/bug-knowledge-candidate-ancestor-redirect-diagnosis.json`

## Risks／Safety

- Security／privacy／data risk：否（目前重現只證明 trust-boundary／integrity bypass，沒有讀取敏感資料或造成外洩）
- Redacted summary：不適用
- Secure evidence refs：無
- Named human reviewer：無

## Disposition 與下一步

- Disposition：`current-run`；這是 WP-002 project-knowledge safety 與 WP-003 delivery consumer 的直接缺陷，符合既有 path contract。
- Next falsifiable action／owner：Implementation executor 使 WP-002 與 downstream WPs 失效，先新增真實 junction／leaf／swap regression reds，再共用或實作等價的 stable component-safe Candidate read，重跑 Windows、Linux 與 fresh review。
- 禁止聲明：尚未修復；不得自動建立 Work／issue／commit／push／merge／deploy／通知。

