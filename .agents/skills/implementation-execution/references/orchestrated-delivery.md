<!-- authority: execution-orchestrated-delivery -->

# Orchestrated Delivery Gate

所有 mutating execution（repository-local legacy path）都先依 `.agents/skills/delivery-orchestrator/references/stage-authorization.md` 取得 exact `implementation/active` 授權，再載入本 Gate 驗證完整 host-temp `delivery-run/v1`。只有 Ready plan 或 caller 自行提供 record 都不成立；缺失或錯誤 context 回 `routing_required`／typed error，且在 execution run、Ledger 或產品寫入前停止。Portable `delivery-run/v2` 另依 [v2 派工、審查與交付收尾契約](v2-dispatch-and-finish.md) 驗證 current assignment；沒有 v2 assignment 不能寫入。

歷史 standalone Ledger 與 Ready artifacts 只保留唯讀、原 bytes、原路徑；不遷移、不刪除，也不恢復 standalone mutation path。若要繼續修改，Delivery Orchestrator 必須先建立或續接合法 delivery context，再依原 Ready source binding 驗證。

首次或續接 run 只有全部條件成立，才取得 execution mutation 權並把一個 requirements 檔視為額外唯讀 upstream input：

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

## Portable v2 gate

v2 不會把 Ready plan 或 caller prompt 當成寫入權。Controller 先驗證 `delivery-run/v2`
state 的 repository identity、Work ID、task class、approval digest、allowed paths、
commands、knowledge scope 與 finish destination，再建立 single-writer assignment。
Implementation subagent 只有在 assignment current 且同一 worktree 沒有另一個 writer
時才能寫入；assignments 依 work package DAG 循序完成，不能平行寫入或自行再委派。

小任務使用一次 integrated gate；大型變更在 Requirements 與 Planning 兩個 gate 都通過
後才 dispatch。Implementation 及 full verification 完成後，另由不同 fresh、唯讀 Reviewer
檢查完整 diff、驗收、測試、snapshot 與 evidence。Reviewer 回報 `APPROVED`、
`CHANGES_REQUIRED` 或 `BLOCKED`；blocking finding 只交回同一 authorized writer，並以
新的 assignment／evidence／fresh review round 重跑 bounded fix loop。

Reviewer 通過後，Controller 依核准 knowledge scope 執行 automatic knowledge review：
候選、source／lint、pre／post snapshots、review digest 與操作都必須保存；任何衝突或
scope drift 停在 awaiting／blocked，不自動寫 canonical knowledge。v2 `finish` 再以
同一 approved scope 完成 stage、commit、可選 push 與 draft PR，保存各 publication
state；merge、deployment、cleanup 與刪除 worktree 不屬於 finish。

v1 的完整 Orchestrated Delivery Gate、host-temp Ledger、兩次人工核准與 terminal
knowledge promotion gate 仍保持原義；缺少 v2 discriminator 的 record 不套用本節。
