# 技術規劃交付協定

只有在規劃品質契約通過、遇到真正阻塞，或使用者要求提前查看目前成果時才讀取並執行本協定。一次只走一個符合目前狀態的分支。

## 狀態

- `Blocked`：必要規格、專案證據、一手資料或決策者不可得，無法可靠形成 Candidate。
- `Candidate—Awaiting confirmation`：品質契約全部通過，完整規劃正在等待使用者核准內容與路徑。
- `Ready`：Candidate 已由使用者核准，並已寫入確認過的 artifact paths。

不存在「暫時 Ready」或以風險註記替代阻塞決策的狀態。

## 建議路徑

依序使用：

1. 使用者為本次規劃指定的位置。
2. 適用治理文件或專案既有的技術計畫慣例。
3. `docs/plans/YYYY-MM-DD-<topic>/plan.md`。

`<topic>` 使用二至五個小寫 ASCII kebab-case 單字。Supporting artifacts 與 `plan.md` 位於同一計畫目錄，`contracts/` 除外時也必須位於該目錄下。

展示 Candidate 前，檢查整個建議 artifact set 的精確路徑都尚未存在。任一 Proposed artifact path 被占用時，保留既有內容，對 topic 目錄使用 `-2`、`-3` 等最小可用後綴；空目錄本身不構成衝突。

## Candidate—Awaiting confirmation

此分支的前置條件是[品質契約](quality-contract.md)已通過。

1. 依建議路徑規則配置完整 artifact set，確認所有路徑可用。
2. 在對話中按建議 path 分段展示每份完整 artifact；檔案系統維持原狀。
3. 最後提供精簡的方案摘要、關鍵決策、主要風險與 artifact manifest。
4. 以本回合唯一問題詢問：「是否確認上述完整技術規劃，並同意寫入列出的所有 artifact paths？」

**完成條件：** 使用者已看到要核准的完整內容與精確路徑；工作區、產品程式碼及外部系統均未變更。

## 核准後寫入

只有使用者明確核准且清楚指向該 Candidate 與全部 paths 時：

1. 寫入前重新檢查整組 paths。
2. 若任一路徑被占用，保留既有檔案且不寫入任何 artifact；改用最小可用後綴，重新展示 paths 並取得確認。
3. 將規劃狀態改為 `Ready`，補上確認者；除狀態與確認 metadata 外，內容必須與核准版本一致。
4. 以可復原的一次性變更寫入整組 artifacts；若只完成部分寫入，停止並明確列出實際狀態，不宣稱 Ready。
5. 回報 Primary artifact 與 supporting artifacts 的路徑。

Ready 只代表可交給實作者，不授權開始實作、commit、發布 tickets、部署或其他外部變更。

## 要求修改

- 將受影響的設計、測試、工作包、風險與追溯全部更新。
- 從使用者修改重算所有受影響內容，再重新執行品質契約。
- 重新展示完整 Candidate 與 paths，再取得新的核准。
- 修改回覆不構成寫入授權。

## Blocked

### 需求缺口

說明缺少的決策、對範圍／驗收及技術規劃的影響，交回 `requirements-discovery`。不要產生假設版技術計畫。

### 技術決策

若證據與選項都已完整，只向使用者提出目前最高影響的一項決策；回答後重算剩餘 frontier。

### 必要證據不可得

列出已查位置、缺失證據、受影響的設計／測試／工作包，以及解除阻塞所需的來源或責任角色。

Blocked 狀態不得寫入正式規劃 artifacts。使用者要求保存目前成果時，可先完整展示一份明確標示 `Blocked` 的診斷紀錄與精確 path，再另行取得寫入同意；它不是 Candidate 或 Ready 計畫。

## 實作請求

- Candidate 尚未 Ready：說明仍需核准的內容，不開始實作。
- Ready：明確結束技術規劃並交付 Primary artifact；實作仍需使用者另有授權或已存在的明確實作請求。
