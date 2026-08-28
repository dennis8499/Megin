# 技術規劃模板

`plan.md` 固定使用下列七節；只在適用時加入條件式小節或 supporting artifacts。成品移除提示文字、空表與佔位符。

## Primary artifact：`plan.md`

```markdown
# 技術規劃：〔功能名稱〕

- 規劃狀態：Candidate—Awaiting confirmation
- 日期：YYYY-MM-DD
- 來源規格：〔專案相對路徑、URL 或穩定識別碼〕
- 規劃範圍：〔單一可實作與驗證的成果〕
- 證據基準：〔branch／commit／工作區狀態；沒有 Git 時說明〕
- Primary artifact：〔本文件建議路徑〕

## 1. 成果、範圍與限制

### 目標成果

〔用一段話說明這份規劃交付的可觀察結果。〕

### 範圍外

- 〔來源規格排除或本計畫刻意不碰的內容。〕

### 強制限制

| 限制 ID | 限制 | 類型 | 來源 |
|---|---|---|---|
| CON-001 | 〔精確限制〕 | Required／Observed | 〔規格或專案證據〕 |

## 2. 證據與變更影響

| 證據 ID | 來源 | 已觀察事實 | 對規劃的影響 |
|---|---|---|---|
| EVD-001 | 〔路徑、符號、設定或官方連結〕 | 〔不含推測的事實〕 | 〔影響的決策／需求〕 |

### Current state

〔描述與本規格直接相關的現有結構、資料流、Interface、測試與限制；greenfield 則明確說明不存在的部分。〕

### 變更影響

| 影響 ID | 受影響能力／Module | 變更性質 | 對應需求 |
|---|---|---|---|
| IMP-001 | 〔名稱〕 | New／Modified／Removed／Preserved | 〔來源需求 ID〕 |

## 3. 設計與決策

### 技術 context

| 面向 | Current／Required | Proposed | 證據或決策 |
|---|---|---|---|
| 語言與版本 | 〔內容〕 | 〔內容〕 | 〔EVD-*／TD-*〕 |
| Runtime／平台 | 〔內容〕 | 〔內容〕 | 〔EVD-*／TD-*〕 |
| 主要依賴 | 〔內容〕 | 〔內容〕 | 〔EVD-*／TD-*〕 |
| 資料與儲存 | 〔內容〕 | 〔內容〕 | 〔EVD-*／TD-*〕 |
| 建置與測試 | 〔內容〕 | 〔內容〕 | 〔EVD-*／TD-*〕 |
| 品質與營運限制 | 〔內容〕 | 〔內容〕 | 〔需求／TD-*〕 |

只保留適用列。

### 技術決策

#### TD-001 — 〔決策名稱〕

- 狀態：Proposed
- 對應需求：〔需求 ID〕
- 證據：〔EVD-* 或一手來源〕
- 選定方案：〔選擇〕
- 理由：〔為何最符合需求與現況〕
- 替代方案：
  - 〔方案〕：〔拒絕原因〕
- 影響：〔Interface、資料、相容性、測試、營運與風險〕

只為具實質取捨的決策建立 `TD-*`。

### Module 與 Seam

| Module ID | Module／責任 | Caller-facing contract | Seam／Adapter 策略 | 隱藏的複雜度 | 對應需求 |
|---|---|---|---|---|---|
| MOD-001 | 〔名稱與單一責任〕 | 〔呼叫者需知道的完整契約摘要〕 | 〔SEAM-* 與依賴策略〕 | 〔Implementation 內部處理〕 | 〔需求 ID〕 |

### 主要流程

〔以步驟、sequence 或小型圖說明跨 Module 的事件與資料流；只在關係確實需要時使用圖。〕

### 條件式設計

只在適用時加入或連結：

- 資料模型、validation、關係與狀態轉換。
- 公開、跨程序或跨系統契約。
- 錯誤、超時、重試、部分成功、復原與降級。
- 安全、隱私、效能、容量、可觀測性與稽核。
- 移轉、相容、部署、rollback 與營運交接。

## 4. 測試策略

若內容已移至 `test-strategy.md`，本節只保留測試目標、Seams 摘要、關鍵命令及連結。

### 測試 Seams

| Seam ID | Interface／可觀察行為 | 依賴替身策略 | 適用測試層級 |
|---|---|---|---|
| SEAM-001 | 〔內容〕 | In-process／local substitute／owned Adapter／external fake | Unit／Integration／Contract／E2E／Manual |

### 驗證矩陣

| Test ID | 需求／驗收 | 情境與風險 | 層級／Seam | Fixture／前置狀態 | Oracle／預期結果 | 命令或程序 |
|---|---|---|---|---|---|---|
| TEST-001 | 〔需求與 AC〕 | 〔正常、邊界、失敗或品質情境〕 | 〔層級、SEAM-*〕 | 〔資料與環境〕 | 〔獨立判定方式〕 | 〔Observed 或 Proposed 命令／人工程序〕 |

### 驗證順序

1. 〔最小、快速且最接近核心風險的驗證。〕
2. 〔Adapter／contract／整合驗證。〕
3. 〔端到端與必要人工驗收。〕

## 5. 工作包

若內容已移至 `work-packages.md`，本節保留依賴摘要、交付順序及連結。

### WP-001 — 〔垂直交付名稱〕

- 目標與可觀察結果：〔獨立完成後能證明的行為〕
- 對應需求／驗收：〔需求 ID、AC ID〕
- Blocked by：None／〔WP-*〕
- 影響範圍：〔Modules、Interfaces、Seams，以及有證據或 Proposed 的檔案範圍〕
- Consumes：〔前置契約，沒有則寫 None〕
- Produces：〔後續依賴的契約或行為〕
- Implementation intent：〔足以保留設計決策，不含逐行程式碼〕
- 測試與驗證：〔TEST-*、命令／程序、預期結果〕
- 完成證據：〔可供 reviewer 判定完成的輸出〕
- 風險與注意事項：〔本包特有內容，沒有則省略〕

## 6. 風險與追溯

### 風險與取捨

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner／決策點 |
|---|---|---|---|---|
| RISK-001 | 〔條件〕 | 〔具體影響〕 | 〔降低或提早發現方式〕 | 〔角色或 WP-*〕 |

### 追溯矩陣

| 來源需求／驗收 | 技術決策／Module | Test | Work package | 完成證據 |
|---|---|---|---|---|
| 〔需求 ID／AC ID〕 | 〔TD-*／MOD-*〕 | 〔TEST-*〕 | 〔WP-*〕 | 〔證據〕 |

## 7. Artifacts 與 readiness

### Artifact manifest

| Artifact | 狀態 | 建立理由 | 權威內容 |
|---|---|---|---|
| plan.md | Required | Primary artifact | 整體方案與索引 |
| 〔條件式 artifact〕 | Proposed | 〔為何必須拆分〕 | 〔唯一權威內容〕 |

### Readiness

- 阻塞未知：無
- 未解衝突：無
- 經確認假設：〔沒有則寫「無」〕
- 品質門檻：通過
- 寫入授權：等待使用者針對本版本與精確路徑確認
```

## Supporting artifacts

### `research.md`

使用 `TD-*` 組織每項研究：問題、決定、版本化一手來源、證據摘要、理由、替代方案與影響。完整決策以本文件為權威；Primary artifact 只保留結論與連結。

### `data-model.md`

使用穩定的 `ENT-*` 與 `STATE-*` 記錄實體責任、欄位語義、validation、關係、所有權、生命週期與狀態轉換。資料庫或程式語言形狀只能在已成為技術決策時加入。

### `contracts/`

每份文件只描述一個公開或跨系統契約，包含版本、輸入輸出、invariants、錯誤、相容性與對應需求。優先使用專案既有的 OpenAPI、schema、IDL 或介面格式。

### `test-strategy.md`

保留完整 `SEAM-*`、`TEST-*`、環境矩陣、fixtures、測試資料、命令、人工驗收與證據保存方式。`plan.md` 只保留風險摘要與驗證順序。

### `work-packages.md`

保留完整 `WP-*` 與依賴圖。依 blocker frontier 排序，並以各包明列的 `Blocked by` 作為依賴權威。

## 拆分判準

只有任一條件成立才拆分：

- 內容被兩個以上主文件章節重複引用。
- 詳細表格或契約使 Primary artifact 的主線難以審閱。
- Artifact 有不同維護者、驗證方式或生命週期。
- 專案已有明確且相容的文件慣例。

拆分只由目前已成立的上述條件觸發。
