<!-- authority: execution-orchestrated-delivery -->

# Orchestrated Delivery Gate

只在caller明示提供host-temp delivery-run/v1時載入。Standalone execution維持manifest-only dirty規則。

首次run只有全部條件成立，才把一個requirements檔視為額外唯讀upstream input：

1. Record通過 [delivery-run/v1 schema](../../delivery-orchestrator/references/delivery-run.schema.json)，位於host temp，phase/status精確為implementation/active。
2. repo_id、current generation canonical_worktree／worktree_key／branch／base與execution probes、binding及planning baseline全部相同；generation為ready。
3. 唯一例外path精確為current Ready requirements，形狀是 docs/work/work_id/requirements.md或最小requirements-N.md；Work ID、artifact root與plan path一致，已遮蔽的approval evidence refs非空且actual SHA相同。
4. Current handoff等於record ref；plan approval evidence相同；sources恰有一個kind spec，其location／SHA等於current requirements；Candidate payload與全部Ready／source hashes重算通過。
5. Requirements不是產品、測試、設定、dependency或command allowed-write；除manifest artifacts與此path外porcelain為空，且整個execution／review期間hash不變。

任一schema、approval、identity、path、source kind、SHA或current ref缺失／mismatch時不套用例外，以未記錄dirty path進入Blocked；不依branch名、path相似或Work ID猜測。

完成條件：唯一requirements path與delivery record、handoff spec source及actual bytes四方一致，且preflight／terminal snapshot證明它未修改。
