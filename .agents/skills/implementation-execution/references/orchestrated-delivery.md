<!-- authority: execution-orchestrated-delivery -->

# Orchestrated Delivery Gate

只在caller明示提供host-temp delivery-run/v1時載入。Standalone execution維持manifest-only dirty規則。

首次run只有全部條件成立，才把一個requirements檔視為額外唯讀upstream input：

1. Record通過 [delivery-run/v1 schema](../../delivery-orchestrator/references/delivery-run.schema.json)，位於host temp，phase/status精確為implementation/active。
2. repo_id、current generation canonical_worktree／worktree_key／branch／base與execution probes、binding及planning baseline全部相同；generation為ready。
3. 唯一例外path精確為current Ready requirements，形狀是 docs/work/work_id/requirements.md或最小requirements-N.md；Work ID、artifact root與plan path一致，已遮蔽的approval evidence refs非空且actual SHA相同。
4. Current handoff等於record ref；plan approval evidence相同；sources恰有一個kind spec，其location／SHA等於current requirements；Candidate payload與全部Ready／source hashes重算通過。
5. Requirements不是產品、測試、設定、dependency或command allowed-write；除manifest artifacts與此path外porcelain為空，且整個execution／review期間hash不變。
6. BUG delivery另要求`work_kind: bug`、primary bug ID、assessment JSON／Markdown與Requirements同一approval binding、Ready `bug_context`完全相符；legacy Complete或required knowledge review gate時，delivery record、implementation run、review report與repository `bug-verification/v1`的path／hash／result四方一致。舊record缺`work_kind`仍視為standard。
7. Delivery record含required `knowledge_gate`時，先實體保存preliminary fresh report／raw outputs，再以current run ID、report path／hash與逐command binding寫入schema-valid、create-only且連續revision的`implementation-outcome/v1`並封存Candidate；不同final fresh report整組包含相同knowledge before／after snapshot、Candidate ref／payload。Delivery重驗Outcome schema、Markdown與changed-file hashes、preliminary report及raw outputs，且final report不能與preliminary report相同。Implementation Ledger Complete後只進`knowledge/active`，不得直接delivery Complete；absence明確代表legacy。

任一schema、approval、identity、path、source kind、SHA或current ref缺失／mismatch時不套用例外，以未記錄dirty path進入Blocked；不依branch名、path相似或Work ID猜測。

完成條件：唯一requirements path與delivery record、handoff spec source及actual bytes四方一致，且preflight／terminal snapshot證明它未修改。

途中BUG使用delivery-run/v1的append-only deferred history。`current-scope`留在implementation，`affecting-current-work`使implementation run成為`Awaiting upstream reapproval`並回Planning，`unrelated`只寫create-only全域inbox；安全風險只帶redacted refs。任何latest pending事件都在fresh review／terminal前materialize，generation續接時連同assessment bytes驗證後create-only複製。
