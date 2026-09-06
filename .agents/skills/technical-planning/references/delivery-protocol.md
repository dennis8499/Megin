<!-- authority: planning-state -->

# 技術規劃交付協定

只有在規劃品質契約通過、遇到真正阻塞，或使用者要求提前查看目前成果時才讀取並執行本協定。人工核准展示遵守 [共用 Human Gate contract](../../project-knowledge/references/human-gate-review.md)（canonical path：`.agents/skills/project-knowledge/references/human-gate-review.md`）；一次只走一個符合目前狀態的分支。

Human Gate bundle inventory: plan primary, `handoff.json`, all supporting artifacts and contracts, `occurrence_map.yaml` or `occurrence_map.yml` for bulk edits, plus Knowledge postimages and deterministic finalizers.

## 狀態

- `Blocked`：必要規格、證據、一手資料或決策不可得。
- `Candidate—Awaiting confirmation`：品質契約通過，完整 immutable review bundle 已落檔並重驗，等待核准。
- `Ready`：同一 Candidate revision 已核准，且符合 [`ready-plan/v1`](ready-plan-contract.md) 的完整 bundle 已寫入確認 paths。

不存在「暫時 Ready」或以風險註記替代阻塞決策的狀態。

## 建議路徑

依序使用：

1. 使用者為本次規劃指定的位置。
2. 適用治理文件或專案既有的技術計畫慣例。
3. `docs/plans/YYYY-MM-DD-<topic>/plan.md`。

`<topic>` 使用二至五個小寫 ASCII kebab-case 單字。`plan.md`、`handoff.json` 與 supporting artifacts 位於同一計畫目錄；`contracts/` 也必須在該目錄內。

seal Candidate 前，檢查 manifest 中整個 artifact set 的精確路徑都尚未存在。任一路徑被占用時，保留既有內容，對 topic 目錄使用 `-2`、`-3` 等最小可用後綴；空目錄本身不構成衝突。

## Candidate—Awaiting confirmation

此分支的前置條件是[品質契約](quality-contract.md)已通過。

1. 依建議路徑配置完整 artifact set，產生唯一 Candidate revision、primary／supporting hashes、canonical payload digest 與 `handoff.json`，確認所有路徑可用。若delivery record含required knowledge overlay，使用`project-knowledge` planning stage builder把整組正式plan bundle與`planned` decision claim／sidecar／index封為同一promotion Candidate；若沒有新的planning knowledge，明列`decision: no-change`並仍封入精確promotion log與Ready receipt。以預期actor與stable evidence token建立prospective binding（不是預先核准）；不得將planned誤標為observed。Legacy或明列bootstrap exception維持既有bundle。
2. 以共用 review command 重驗 `candidate.json`、`review.json`、primary、`handoff.json`、全部 supporting／contract artifacts、bulk-edit occurrence map（若適用）、knowledge postimages與 deterministic finalizers；每個 direct path 必須可開啟且 bytes／hash／manifest一致。
3. Chat只呈現共用 contract 的七類摘要、方案關鍵決策／風險、全部 direct links、使用 `role`／`approval_status` 的manifest及 exact identity，不內嵌完整artifact、diff、postimage或raw output。
4. 使用共用 contract 的唯一問題取得整組Plan＋Knowledge（含occurrence map）的核准。同一回答是plan與knowledge的approval evidence，不新增第三個 gate。

**完成條件：** 與digest對應的每一個byte都已存在可直接開啟的immutable review files，全部paths重驗通過；Chat只有summary projection與一個問題，Ready工作區與外部系統未變更。

## 核准後寫入

只有使用者明確核准且清楚指向該 Candidate 與全部 paths 時：

1. 驗證核准回覆可定位到目前 revision、payload digest、review digest與完整manifest，再stable-read整組review files。
2. 任一路徑被占用或任一review file drift時保留現有內容、整組不寫入；配置最小可用後綴，重新seal並呈現新summary／identity後重新核准。
3. 依 [`ready-plan/v1`](ready-plan-contract.md)只更新 approval metadata 與 artifact approval statuses；重新驗證 primary／supporting bytes、hashes、revision 與 digest 未變。
4. Required overlay只可透過sealed Candidate的optimistic transaction，以同一approval evidence寫入整組plan artifacts與knowledge postimages；任何source／preimage drift、replace、lint或receipt失敗都不進Implementation。Legacy使用既有可復原一次性變更。部分寫入時停止、列出實際狀態，狀態維持非 Ready。
5. 重新讀取`handoff.json`、驗證schema與所有已寫入hashes；required overlay另要求`knowledge-promotion/v1.formal_paths`精確等於完整artifact manifest，透過Technical Planning owner validator重驗Ready approval、payload、primary/supporting bytes與handoff self-hash規則，再驗證stage/work ID、Candidate digest與passed lint，最後回報Primary、全部supporting、handoff與receipt paths。

Ready 只代表可交給 `$implementation-execution`；實作、commit、tickets、部署或其他外部變更需要各自既有授權。交接提供 `handoff.json` 與 Primary path，consumer 從 versioned contract 取得其餘索引。

## 要求修改

- 更新受影響的設計、BDD／TDD、commands、WP、revision impact、風險、追溯與 handoff。
- 建立新 Candidate／review revision 和 digest，重新執行品質契約並呈現新的Summary-only Chat projection，再取得核准。
- 使用者的修改指示只授權重算 Candidate；寫入仍依核准分支。

## Blocked

### 需求缺口

說明缺少的決策及其對範圍／驗收／設計／測試／WP 的影響，交回 `requirements-discovery`，只詢問最高影響決策。唯一有效輸出是缺口與交接，不形成 Candidate。

### 技術決策

若證據與選項都已完整，只向使用者提出目前最高影響的一項決策；回答後重算剩餘 frontier。

### 必要證據不可得

列出已查位置、缺失證據、受影響的設計／測試／工作包，以及解除阻塞所需的來源或責任角色。

Blocked 狀態的正式規劃 paths 保持不變。使用者要求保存時，先把標示 `Blocked` 的診斷紀錄與path封存為immutable review files並重驗；Chat只呈現摘要、direct links與identity，再另取寫入同意。它不使用Candidate／Ready或`ready-plan/v1`身分。

## 實作請求

- Candidate：回報待核准 revision／paths，維持規劃狀態。
- 無版本、版本不支援或缺少完整 `ready-plan/v1`：重新規劃並seal新版review bundle，以Summary-only Chat提供direct links與identity後重新核准；executor不補寫producer contract。
- Ready 且 contract 完整：結束規劃並交付 Primary 與 `handoff.json`；只有明確實作請求才啟動 `$implementation-execution`。
