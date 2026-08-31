<!-- authority: execution-loop -->

# Outside-in BDD 與內層 TDD 執行契約

本文件是行為 slice 執行與 finding 修正的唯一權威，只在 Preflight 通過後讀取。主代理是唯一 writer，依 `WP-*` DAG 穩定拓撲序逐包執行；同一 frontier 依 Ready plan 順序、再依 WP ID 排序。Implementer subagent 不取得寫入責任。

## 1. 建立可執行 BDD 邊界

BDD 邊界依 framework 生命週期建立：

- `Observed`：既有 runner／feature／bindings 先執行獨立 `bdd-discovery` command。
- `Proposed` 且 target runtime 內建 framework：先執行 `BDD-FWK-*` 指定的 availability probe，再在對應 `WP-*` 只建立核准的 test runner／feature／bindings；不安裝 dependency、不改 manifest／lockfile，然後執行獨立 discovery。
- `Proposed` 且需額外安裝：先在對應 `WP-*` 依核准的 `bdd-install` command 加入最小 test-only dependency、runner wiring 與 lockfile，再執行獨立 discovery。

三條路徑都必須由 discovery 證明 runner、feature、bindings 與預期 inventory 可解析。Proposed 路徑另符合：

- 不引入 production runtime dependency；
- 不改變產品行為；
- 只有需額外安裝的路徑可改 manifest／lockfile，且必須在 plan 影響範圍及對應 `WP-*` 內；
- 安裝與 discovery 遵守 command 的 timeout、network、allowed writes／side effects，raw output、diff 及來源版本寫入 Ledger。

安裝／availability 失敗或實際 framework contract 與 Ready plan 不符時，停止產品變更並依證據進入 `Awaiting upstream reapproval` 或 `Blocked`。

### Code-empty greenfield 分支

Source manifest 證明第一個公開 seam／entrypoint 不存在時，先完整讀取 [Greenfield Bootstrap 契約](greenfield-bootstrap.md)。只有該契約完成條件成立，第一個 focused BDD 才可把核准 sentinel 的 assertion mismatch 視為正確 red；其他 production shape 仍維持不變。

### BUG plan 分支

`bug_context`存在時，在任何production修改前先保存assessment binding並重跑原始`bug-reproduction` command。`verified`目標必須先證明原始症狀`present`；`partial`目標必須保存無法可靠重現的嘗試證據，並只使用Plan已核准的proxy seam。接著取得`regression_bdd_refs`與`regression_test_refs`的正確red；預期中的這些red不是新BUG。

一次只實作一個最小根因修法。原始症狀、資料流或根因假設與assessment／Plan不符，修法沒有讓同一regression green，或需要改變需求、介面、資料契約、依賴或WP scope時，保存失敗證據並進`Awaiting upstream reapproval`；不得再疊第二個猜測式patch。

## 2. 每個行為切片的外層 red

從 slice order 中目前可執行的最小 `BDD-*` 開始。建立或聚焦 plan 指定的 feature、bindings、fixture 與 oracle，先保存 production snapshot，再執行 focused command。目前 scenario 完成 inner TDD 並 green 後，才建立下一個未實作 scenario。

正確 red 必須同時符合：

- scenario 已被 runner 發現並真正執行；
- fixture 到達 plan 指定的公開 seam；
- failure 是 oracle 所描述的目標行為差異；
- 不是語法／解析、undefined 或 pending step、fixture、載入、dependency、權限、網路、timeout、環境或 runner 錯誤；
- 修改 production code 前已保存 command、exit code、完整輸出與 snapshot。

若是錯誤 red，只修 feature、bindings、fixture 或環境前提並重跑；不得寫 production code。唯一可碰 production shape 的情況是前節已核准 `BOOT-*` 的 build／load 驗證尚未通過，而且修改仍嚴格限於其 declaration／wiring，不能加入行為；該失敗本身仍不算 red。

若 scenario 在任何對應 production 修改前已通過：

1. 保存 green 輸出與當前 snapshot。
2. 驗證 oracle 確實覆蓋需求，而非測試未執行、條件式跳過或 assertion 缺失。
3. 將切片記為 `Satisfied by existing implementation`。
4. 不製造假 red，也不為此切片新增 production behavior。

需要新增行為卻無法取得正確 red，表示測試 seam 或計畫契約失真；進入 `Awaiting upstream reapproval`。

## 3. 內層 TDD

外層 BDD 正確 red 後，依 `TEST-*` 在 plan 指定 seam 一次驅動一個最小行為：

1. **Red：** 加入一個觀察公開 contract 的 focused test；執行後必須因該最小行為缺失而失敗。先前已 green 時，重新檢查切片與 seam，不增加無法由 red 證明的 production code。
2. **Minimal green：** 只做讓目前 test 通過的最小 production 變更，立即重跑同一命令。
3. **Refactor-with-green：** 在不擴大行為範圍下改善結構；每次實質 refactor 後重跑 focused test。
4. 重跑目前 BDD scenario；仍 red 時，以下一個 `TEST-*` 重複。

每個轉換都在 Ledger 保存對應 `BDD-*`／`TEST-*`／`WP-*`、command outcome、raw output logical ref、前後 diff 與 oracle。唯一有效的產品變更由先前正確 red 驅動；刪除既有行為、弱化 assertion、skip 或只測 private implementation 都不能作為 red／green 證據。

## 4. 工作包驗證

一個 `WP-*` 只有在以下全部成立時可標為 `Verified`：

- 其所有 BDD scenarios 均通過或有有效的 `Satisfied by existing implementation` 證據。
- 每個新增 production behavior 都有時間順序正確的 test red → green 證據。
- plan 列出的 focused tests、相關 tests、工作包 build／test／governance commands 全部新鮮執行，exit code 0、零 failure、零 skipped。
- 完成證據、需求、`BDD-*`、`TEST-*`、seam、diff 與 commands 雙向可追溯。
- tracked 與未忽略新檔只在 plan 明列範圍；Ready sources、秘密、無關檔案與外部狀態未改變。
- BUG plan 的regression已有red→green；`verified`另重跑同一原始症狀並證明`absent`，`partial`只證明核准proxy red→green且保存殘餘風險與staging／人工follow-up。

若當前工作包失敗，下游維持 `Pending`。不得以其他工作的成功掩蓋本包失敗。

## 5. Finding 修正

主代理全量驗證 failure 或 Reviewer blocking finding 先映射到原始 `source_refs` 與受影響 `BDD-*`／`TEST-*`／`WP-*`：

- 缺少或錯誤行為：先新增或修正能重現 finding 的 BDD scenario，確認正確 red，再走內層 TDD。
- 局部實作缺陷：在既有 failing BDD 下建立最小 focused test red，再修正。
- 測試、fixture 或 oracle 缺陷：只修測試條件，直到它正確 red；尚未取得正確 red 前不改 production。
- Ready plan 的需求、seam、framework、命令或工作包缺陷：進入 `Awaiting upstream reapproval`，不得私自修改 plan。
- 環境、權限或工具失敗：進入 `Blocked`。

進入 `Fixing` 時，直接受影響 WP 及其必要 downstream closure 依序轉 `Verified → Invalidated → Executing → Verified`；原 evidence 保留為 `superseded`。每包重跑完整證據後才回全量 `Verifying`。

Reviewer command `failed` 依 failure 證據走上述修正或上游／環境分流；`blocked`／`not_run` 不能支持 APPROVED，依原因進入 `Blocked` 或 `Awaiting upstream reapproval`。`blocking: false` 的 advisory 保存但不驅動產品變更；只有來源要求支持的新行為才能實作。

途中發現的新BUG先保存唯讀診斷：由目前diff造成或違反已核准行為者，以`current-scope`留在同run的Fixing與既有驗收；影響成果但需要改變Requirements／Plan／契約者，以`affecting-current-work`進`Awaiting upstream reapproval`；不影響成果者以`unrelated`保存到全域BUG inbox，不順手改碼。Pending host-temp evidence必須在fresh review或任何terminal handoff前materialize成create-only assessment。
