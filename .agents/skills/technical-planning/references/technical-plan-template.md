# 技術規劃模板

`plan.md` 固定使用下列七節；成品移除提示、空表與佔位符。完整交接資料由同 bundle 的 [`handoff.json`](ready-plan-contract.md)提供，本模板不重複其 schema。

## Primary artifact：`plan.md`

```markdown
# 技術規劃：〔功能名稱〕

- 狀態與核准證據：見 `handoff.json.approval`
- Candidate revision：〔revision〕
- 日期：YYYY-MM-DD
- 來源規格：〔path／URI／ID〕
- 範圍：〔單一可實作、可驗證成果〕
- Planning baseline：〔repo_id、完整 HEAD SHA、status hash〕
- Primary／handoff：〔plan.md path〕／〔handoff.json path〕

## 1. 成果、範圍與限制

〔目標成果摘要。〕

- 範圍內：〔內容〕
- 範圍外：〔內容〕

| ID | Required／Observed 限制 | SRC-* |
|---|---|---|
| CON-001 | 〔精確限制〕 | SRC-001 |

## 2. 證據與變更影響

| SRC ID | Kind／location／revision | 事實 | Plan refs | 直接 WP refs |
|---|---|---|---|---|
| SRC-001 | 〔內容〕 | 〔Observed／Required〕 | 〔IDs〕 | WP-001 |

### Current → target

〔只描述受本規格影響的結構、資料流、Interface、測試與限制；greenfield 記錄不存在證據。〕

| 影響 ID | 能力／Module | New／Modified／Removed／Preserved | 來源要求 |
|---|---|---|---|
| IMP-001 | 〔內容〕 | 〔內容〕 | 〔ID〕 |

## 3. 設計與決策

| Context | Observed／Required | Proposed | SRC／TD |
|---|---|---|---|
| Runtime／版本／依賴／資料／營運 | 〔適用內容〕 | 〔內容〕 | 〔IDs〕 |

### TD-001 — 〔決策〕

- 需求／證據：〔IDs〕
- 選定方案與理由：〔內容〕
- 真實替代方案／拒絕原因：〔內容〕
- Interface、資料、相容性、測試與營運影響：〔內容〕

| MOD ID | 責任 | Caller-facing contract | SEAM／Adapter | 隱藏內容 | 要求 |
|---|---|---|---|---|---|
| MOD-001 | 〔內容〕 | 〔輸入、輸出、invariant、錯誤、品質〕 | SEAM-001 | 〔內容〕 | 〔IDs〕 |

〔必要時加入主要流程，並連結唯一權威的資料模型、公開契約、錯誤／復原、安全／效能／可觀測性或移轉 supporting artifact。〕

## 4. 測試策略

Bug plan在本節前加入「BUG diagnosis與verification target」：列出assessment JSON／Markdown binding、reproduction／root-cause status與confidence、單一最小causal fix、original `CMD-BUG-REPRO-*`、regression BDD／TEST refs，以及`verified | partial` target。Partial另完整列出reason、proxy red→green、residual risks與staging／人工follow-up；standard plan省略整節。

詳細矩陣可移至 `test-strategy.md`；本節保留目標、seams、順序、IDs 與連結。

| BDD-FWK ID | Observed／Proposed framework、版本與一手來源 | Test-only／安裝邊界 | Feature／binding／fixture | Discovery／report／zero-skip／CI |
|---|---|---|---|---|
| BDD-FWK-001 | 〔內容〕 | 〔內容〕 | 〔paths〕 | 〔CMD-* 與判定〕 |

| SEAM ID | 可觀察 Interface | 替身策略 | 測試層 |
|---|---|---|---|
| SEAM-001 | 〔內容〕 | 〔內容〕 | 〔內容〕 |

`BOOT-*`：〔不適用＋SRC-*；或 BOOT-001 的 absence evidence、精確 contract shape、deterministic sentinel、oracle 互斥證據、行為中立邊界、CMD-BOOT-*、第一個 BDD／WP。〕

| BDD ID | 要求／scenario | SEAM／fixture | Oracle／正確 red | Feature／binding | Focused CMD | WP／order |
|---|---|---|---|---|---|---|
| BDD-001 | 〔內容〕 | 〔內容〕 | 〔目標行為缺失的 assertion〕 | 〔paths〕 | CMD-BDD-FOCUSED-001 | WP-001／1 |

| TEST ID | BDD／風險 | 層級／SEAM／fixture | Oracle／red | Focused／related CMD |
|---|---|---|---|---|
| TEST-001 | BDD-001 | 〔內容〕 | 〔內容〕 | 〔CMD-*〕 |

| CMD ID | Purpose | Observed／Proposed | 摘要；完整 contract 在 handoff.json |
|---|---|---|---|
| CMD-BDD-DISCOVERY-001 | bdd-discovery | 〔狀態〕 | 〔預期 inventory〕 |
| CMD-BDD-FOCUSED-001 | bdd-focused | 〔狀態〕 | 〔scenario〕 |
| CMD-BDD-FULL-001 | bdd-full | 〔狀態〕 | 〔suite〕 |
| CMD-TDD-FOCUSED-001 | tdd-focused | 〔狀態〕 | 〔test〕 |
| CMD-RELATED-001 | related | 〔狀態〕 | 〔集合〕 |
| CMD-BUILD-FULL-001 | build-full | 〔狀態〕 | 〔build〕 |
| CMD-TEST-FULL-001 | test-full | 〔狀態〕 | 〔tests〕 |

順序：目前 BDD（必要時先驗證 BOOT）正確 red → 映射 TEST red／minimal green／refactor-with-green → focused BDD 與 related green；scenario green 後才進下一個。全部 WP 完成後 fresh 執行 full build、test、BDD 與治理 commands。

## 5. 工作包

完整內容可移至 `work-packages.md`；本節保留 DAG、順序與連結。

### WP-001 — 〔可觀察垂直成果〕

- 要求／結果／impact：〔IDs 與範圍〕
- Blocked by：〔None 或 WP-*〕
- Consumes／produces：〔contracts〕
- Intent：〔保留設計決策，不含逐行實作〕
- Slice order：〔BOOT-*（若適用）、BDD-* → TEST-*〕
- Commands／完成證據：〔CMD-* 與判定〕

## 6. 風險與追溯

### 風險與取捨

| Risk ID | 觸發條件 | 影響 | Mitigation／驗證 | Owner／決策點 |
|---|---|---|---|---|
| RISK-001 | 〔條件〕 | 〔具體影響〕 | 〔降低或提早發現方式〕 | 〔角色或 WP-*〕 |

### 追溯矩陣

| SRC／要求 | TD／MOD／SEAM | BDD | TEST | WP | CMD／證據 |
|---|---|---|---|---|---|
| SRC-001／〔ID〕 | 〔IDs〕 | BDD-001 | TEST-001 | WP-001 | 〔IDs〕 |

## 7. Artifacts 與 readiness

### Artifact manifest

完整 `role`／`approval_status`／SHA-256 manifest 以 `handoff.json` 為權威；本節只提供不隨核准 metadata 改變的閱讀索引。

| Path | Role | 建立理由 | 權威內容 |
|---|---|---|---|
| plan.md | primary | 主入口 | 整體方案與索引 |
| handoff.json | handoff | 版本化交接 | `ready-plan/v1` data |
| 〔path〕 | supporting | 〔符合拆分判準的理由〕 | 〔唯一詳細內容〕 |

### Readiness

- 缺口／未知／衝突：無
- BDD framework／BOOT／BDD／TDD／WP／commands：完整
- `handoff.json` schema 與 cross-references：通過
- 品質門檻：通過
- 核准狀態與寫入證據：見 `handoff.json.approval`
```

## Supporting artifacts

- `research.md`：`TD-*` 的版本化一手來源、證據、選項與取捨。
- `data-model.md`：`ENT-*`／`STATE-*` 的語義、validation、關係與生命週期。
- `contracts/`：一份一個版本化公開／跨系統契約，優先沿用 OpenAPI、schema、IDL。
- `test-strategy.md`：完整 `BDD-FWK-*`／`BDD-*`／`SEAM-*`／`TEST-*`／`CMD-*`、fixtures、環境與證據。
- `work-packages.md`：完整 `WP-*` DAG、blocker frontier 與 impact map。

## 拆分判準

只有內容被多處引用、細節妨礙 primary 主線、artifact 有不同維護者／驗證方式／生命週期，或專案已有相容慣例時拆分。每項資訊保留一個權威位置。
