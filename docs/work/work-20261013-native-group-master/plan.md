# 實作計畫與對照

本計畫落實使用者核准的完整改善計畫；不產生自己的人工成果驗收或繞過新流程的遠端 master 規則。

1. 新增 architecture 階段與第十三個 Skill，同步階段 Skills、模板及契約參考。
2. 納入必要 Group 能力，以 v3/v5 統一新流程；保留舊契約 dispatch，GitLab Issue/MR 留在原套件。
3. 實作 root inventory、遠端優先序／固定 master、committed source 探索與 shared common-dir 鎖。
4. 整合 BDD/TDD、精確核准、追加式 Review 與快照關卡；兩模式驗收後只建立 feature commit，部分提交可恢復。
5. 增加未完成升級阻擋、13 Skills 封裝與 CI，使用暫存 bare remotes 驗證新流程並保留既有測試。
6. 依 round 0 加三次修正的規則進行實際獨立唯讀 Review；原始測試輸出與結果保留於 evidence。

| 需求 | 可檢視實作 | 驗證 |
| --- | --- | --- |
| REQ-001 | architecture Skill、quality_policy architecture_ref | missing approval/architecture 與 upstream source 案例 |
| REQ-002/005 | workspace_context、workspace_lock、unified_workflow | Group 一／多目標、完整盤點、共享鎖及 combo delivery |
| REQ-003 | master resolver、baseline/prepare、branch-policy | main-only、live drift、lagging refs、fetch race、refmap 保留本機 master |
| REQ-004 | quality_policy、review_history、quality gates | red/self/stale/reuse/cap/reset 阻擋及提前通過 |
| REQ-006 | deliver/completion、v2 receipt | no acceptance、hook isolation、committed TDD、partial/crash resume |
| REQ-007 | installer/validator、README/OPERATIONS、CI | 既有 52 案例、upgrade block、reproducible ZIP/document links |

本次維護成果通過 Review 與測試後，使用者於後續訊息授權本機提交；詳見 evidence/commit-authorization.md。Megin 自身的 origin 只有 main，不能用其執行新的 master 強制流程；本次維護提交不宣稱執行該流程，不自動建立遠端 master。實際 Windows 測試、Linux 限制、套件雜湊與最後 Review 結果見 evidence/verification.md。
