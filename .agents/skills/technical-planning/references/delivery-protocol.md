<!-- authority: planning-state -->

# 技術規劃交付協定

只有在規劃品質契約通過、遇到真正阻塞，或使用者要求提前查看目前成果時才讀取並執行本協定。一次只走一個符合目前狀態的分支。

## 狀態

- `Blocked`：必要規格、證據、一手資料或決策不可得。
- `Candidate—Awaiting confirmation`：品質契約通過，完整 bundle 等待核准內容與路徑。
- `Ready`：同一 Candidate revision 已核准，且符合 [`ready-plan/v1`](ready-plan-contract.md) 的完整 bundle 已寫入確認 paths。

不存在「暫時 Ready」或以風險註記替代阻塞決策的狀態。

## 建議路徑

依序使用：

1. 使用者為本次規劃指定的位置。
2. 適用治理文件或專案既有的技術計畫慣例。
3. `docs/plans/YYYY-MM-DD-<topic>/plan.md`。

`<topic>` 使用二至五個小寫 ASCII kebab-case 單字。`plan.md`、`handoff.json` 與 supporting artifacts 位於同一計畫目錄；`contracts/` 也必須在該目錄內。

展示 Candidate 前，檢查 manifest 中整個 artifact set 的精確路徑都尚未存在。任一路徑被占用時，保留既有內容，對 topic 目錄使用 `-2`、`-3` 等最小可用後綴；空目錄本身不構成衝突。

## Candidate—Awaiting confirmation

此分支的前置條件是[品質契約](quality-contract.md)已通過。

1. 依建議路徑配置完整 artifact set，產生唯一 Candidate revision、primary／supporting hashes、canonical payload digest 與 `handoff.json`，確認所有路徑可用。
2. 在對話中按精確 path 展示每份 artifact 的完整序列化內容，包括 `approval.status: Candidate` 的 handoff；每個 path 使用獨立內容區塊，並維持檔案系統原狀。Hash、byte count、manifest、摘要或「內部已固定」不是 artifact bytes 的替代品；回覆長度不改變這項 payload。
3. 最後提供方案摘要、關鍵決策、主要風險及使用 `role`／`approval_status` 的 manifest。
4. 以本回合唯一問題詢問：「是否確認上述完整技術規劃，並同意寫入列出的所有 artifact paths？」

**完成條件：** 使用者已看到與 digest 對應的最後一份 artifact 最後一個 byte 及全部 paths；工作區與外部系統未變更。在此之前回覆只是未完成草稿，不宣告 `Candidate—Awaiting confirmation`、不詢問核准。

## 核准後寫入

只有使用者明確核准且清楚指向該 Candidate 與全部 paths 時：

1. 驗證核准回覆可定位到目前 revision、payload digest 與全部 paths，再重新檢查整組 paths。
2. 任一路徑被占用時保留現有內容、整組不寫入；配置最小可用後綴，重新展示並重新核准。
3. 依 [`ready-plan/v1`](ready-plan-contract.md)只更新 approval metadata 與 artifact approval statuses；重新驗證 primary／supporting bytes、hashes、revision 與 digest 未變。
4. 以可復原的一次性變更寫入整組 artifacts。部分寫入時停止、列出實際狀態，狀態維持非 Ready。
5. 重新讀取 `handoff.json`、驗證 schema 與所有已寫入 hashes，回報 Primary、supporting 與 handoff paths。

Ready 只代表可交給 `$implementation-execution`；實作、commit、tickets、部署或其他外部變更需要各自既有授權。交接提供 `handoff.json` 與 Primary path，consumer 從 versioned contract 取得其餘索引。

## 要求修改

- 更新受影響的設計、BDD／TDD、commands、WP、revision impact、風險、追溯與 handoff。
- 建立新 revision 和 digest，重新執行品質契約並完整展示，再取得核准。
- 使用者的修改指示只授權重算 Candidate；寫入仍依核准分支。

## Blocked

### 需求缺口

說明缺少的決策及其對範圍／驗收／設計／測試／WP 的影響，交回 `requirements-discovery`，只詢問最高影響決策。唯一有效輸出是缺口與交接，不形成 Candidate。

### 技術決策

若證據與選項都已完整，只向使用者提出目前最高影響的一項決策；回答後重算剩餘 frontier。

### 必要證據不可得

列出已查位置、缺失證據、受影響的設計／測試／工作包，以及解除阻塞所需的來源或責任角色。

Blocked 狀態的正式規劃 paths 保持不變。使用者要求保存時，先展示標示 `Blocked` 的診斷紀錄與 path，再另取寫入同意；它不使用 Candidate／Ready 或 `ready-plan/v1` 身分。

## 實作請求

- Candidate：回報待核准 revision／paths，維持規劃狀態。
- 無版本、版本不支援或缺少完整 `ready-plan/v1`：重新規劃、完整展示並重新核准；executor 不補寫 producer contract。
- Ready 且 contract 完整：結束規劃並交付 Primary 與 `handoff.json`；只有明確實作請求才啟動 `$implementation-execution`。
