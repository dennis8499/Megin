# 需求分析：既有 BUG 改善與結案追蹤

- 文件狀態：Ready
- 日期：2026-09-12
- 文件範圍：盤點、驗證、修復與結案既有 16 個 Project Knowledge／Delivery BUG
- 需求來源：使用者核准的 BUG 改善與結案追蹤計畫；`docs/bugs/**` assessment；既有 work requirements、Ready plan、Outcome 與 owner contract
- 確認者：使用者（`conversation:user-implement-plan-20260912`）

## 1. 執行摘要

### 問題或機會

專案保存 16 個不重複的 confirmed BUG identity，但現有資料缺少逐項、可重算的 current status 與 `bug-verification/v1` 結案證據。部分既有 work 已完成並通過測試，若直接以 assessment 數量判定，會把已修復與仍可重現的問題混在一起。

### 為何現在做

BUG 涉及檔案發布、回滾、registry 路徑安全、Ready 契約、審查獨立性及 2 秒查詢效能門檻。這些邊界若沒有逐項驗證，後續交付無法可靠判定資料是否安全、審查是否獨立或效能是否穩定。

### 預期成果

- BG-001：每個 BUG identity 都有可查證的目前狀態、責任範圍、驗收結果與下一步。
- BG-002：仍可重現的既有行為缺陷完成最小修復並通過跨平台或適用環境回歸。
- BG-003：宣告修復的 BUG 都有獨立 verification，未完成項目保留明確的殘餘風險與 follow-up。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | 專案維護者 | 決定修復範圍與接受結案證據 | 核准 Requirements、Plan 與 Knowledge Gate |
| ACT-002 | Implementation executor | 執行現況驗證、最小修復、回歸測試與證據保存 | 只能修改 Ready plan 明列的產品、測試與追蹤 artifact |
| ACT-003 | Fresh reviewer | 以獨立 session 審查目前 snapshot、測試與 BUG verification | 不修改 repository，不接受主代理結論代替 evidence |
| ACT-004 | Project Knowledge／Delivery validator | 驗證 schema、path、hash、phase、receipt 與 evidence binding | 失敗時 fail closed，不宣告修復 |

## 3. 範圍與優先順序

### 範圍內

- 盤點既有 16 個 BUG identity，`knowledge-outcome-create-only-toctou` 的 revision 1/2 合併為一個 BUG。
- 重跑原始 symptom oracle、相關 BDD／TEST、完整治理與效能驗證。
- 修復目前仍可重現的資料完整性、路徑安全、契約完整性與效能問題。
- 新增 `docs/bugs/status-review.md`，並對可結案 BUG 保存 `docs/bugs/<bug-id>/verifications/<work-id>.json`。

### 範圍外

- 新增產品功能、外部 issue、部署、通知、commit、push、merge 或 release 操作。
- 改變公開 CLI、既有 JSON schema、既有 2 秒效能門檻或既有 assessment 的原始內容。
- 將無法取得證據的問題標記為已修復。

### 優先順序

先處理檔案發布、回滾與資料完整性，再處理路徑安全與跨平台分類，接著處理契約／審查完整性，最後驗證效能量測。安全、資料保留、原子性與可追溯性不得因效能或便利性降低。

## 4. 使用者與業務旅程

### J-001 — BUG 現況盤點

- 主要角色：ACT-001、ACT-002
- 觸發與前置條件：repository 位於指定 base，16 個 BUG assessment 可讀取。
- 主要流程：按 BUG ID 去重 → 讀取最新 assessment → 執行適用原始 oracle／回歸 → 保存 status、environment、evidence 與下一步。
- 替代、例外與復原：無法重現或缺平台證據時標為部分驗證或證據不足，保留風險與 follow-up。
- 完成結果：每個 BUG 都有唯一 status，且 status 可由證據重算。
- 相關需求：FR-001、FR-002、FR-006、FR-007、FR-008
- 驗收情境：AC-001、AC-002、AC-009

### J-002 — 安全發布與失敗復原

- 主要角色：ACT-002、ACT-004
- 觸發與前置條件：Candidate、Outcome 或 approved preimage 進入發布流程。
- 主要流程：驗證 target 與 preimage → 原子發布或拒絕碰撞 → 發生錯誤時只回滾本次 writer 擁有的 bytes／identity。
- 替代、例外與復原：競爭者變更或復原衝突時保留競爭者與復原材料，回報可復原錯誤或 `RECOVERY_REQUIRED`。
- 完成結果：沒有 partial target、誤刪競爭者、無聲覆寫或錯誤的 rolled-back journal。
- 相關需求：FR-003、NFR-001、NFR-004
- 驗收情境：AC-003、AC-004

### J-003 — 路徑、契約與審查邊界

- 主要角色：ACT-002、ACT-003、ACT-004
- 觸發與前置條件：系統讀取 registry、Ready report、page 或 review binding。
- 主要流程：沿 canonical root 驗證所有 path component、使用權威 schema／Ready validator、檢查 reviewer identity 與 manifest 完整性。
- 替代、例外與復原：祖先 redirect、未知欄位、缺 manifest、相同 reviewer 或 Ready error 時 fail closed，合法資料仍通過。
- 完成結果：所有 consumer 對相同輸入產生一致的接受／拒絕結果。
- 相關需求：FR-004、FR-005、NFR-002、NFR-003
- 驗收情境：AC-005、AC-006、AC-007

### J-004 — 查詢效能驗證

- 主要角色：ACT-002、ACT-003
- 觸發與前置條件：固定 50,000 files／5,000 pages fixture 與固定 query token。
- 主要流程：區分 readiness 與正式 cold／warm samples，執行五次各類樣本並比較功能 hash。
- 替代、例外與復原：任一正式 sample 超過 2 秒即保留失敗；資料變動時 cache 必須失效並重新取得結果。
- 完成結果：所有正式 samples ≤ 2 秒、功能結果一致、fixture 清除。
- 相關需求：FR-006、NFR-003、NFR-004
- 驗收情境：AC-008、AC-009

## 5. 需求

### FR-001 — 完整 BUG registry

- 需求：系統維護者必須能以 BUG ID 去重所有 assessment revisions，並為每個 identity 顯示最新 assessment、原始症狀、影響、責任 work、回歸測試、驗證環境、evidence 與下一步。
- 理由與來源：BG-001；`docs/bugs/**/assessment-*.json`；使用者計畫 WP-01。
- 優先順序：Must
- 驗收：AC-001

### FR-002 — 原始症狀現況判定

- 需求：對每個 BUG 必須執行其適用的原始 symptom oracle 與 regression oracle；結果必須分類為 `still-reproducible`、`verified-fixed`、`partial` 或 `insufficient-evidence`。
- 理由與來源：BG-001、BG-003；BUG diagnosis／implementation verification contract。
- 優先順序：Must
- 驗收：AC-002、AC-009

### FR-003 — 原子發布與所有權回滾

- 需求：發布、更新與雙檔 Outcome 操作必須保留 create-only、no-replace、preimage 與 writer ownership；並行碰撞或失敗時不得覆寫或刪除獨立擁有的 bytes。
- 理由與來源：BG-002；P0 BUG assessments；既有 transaction safety contract。
- 優先順序：Must
- 驗收：AC-003、AC-004

### FR-004 — 路徑安全與跨平台一致性

- 需求：所有 registry、Candidate 與 repository artifact 讀寫入口必須從 canonical root 檢查每個 ancestor／leaf component；普通 POSIX path 必須通過，真正 redirect 與 inspection error 必須拒絕。
- 理由與來源：P1 path BUG assessments；`_is_reparse_path`／component validation contract。
- 優先順序：Must
- 驗收：AC-005

### FR-005 — Ready 與 review 契約完整性

- 需求：Ready receipt、preliminary review、Outcome、page schema 與 Delivery consumer 必須驗證完整 manifest、權威 closed schema、bound Ready coverage 與 reviewer identity；任何不一致必須 fail closed。
- 理由與來源：P1 contract BUG assessments；既有 Ready／fresh review contract。
- 優先順序：Must
- 驗收：AC-006、AC-007

### FR-006 — 效能量測邊界

- 需求：效能驗證必須分離 readiness 與正式 cold／warm samples，保存五次各類樣本、功能 hash、fixture profile 與完整失敗結果；每個正式 sample 必須不超過 2.0 秒。
- 理由與來源：BG-003；P2 performance BUG assessments；既有 BDD-016／BDD-020 contract。
- 優先順序：Must
- 驗收：AC-008

### FR-007 — 結案分類規則

- 需求：只有原始症狀 post-fix 為 absent、regression red→green、適用 full verification 通過且 evidence 完整的 BUG 才能標為 `verified-fixed`；缺少其中任一項必須維持 `partial` 或 `insufficient-evidence`。
- 理由與來源：BG-003；BUG verification contract。
- 優先順序：Must
- 驗收：AC-002、AC-009

### FR-008 — 可追溯 verification

- 需求：每個宣告修復的 BUG 必須保存與 assessment revision、work ID、驗證版本、原始症狀、regression、full commands、review 與 hash 綁定的 verification；verification 失敗不得產生結案宣稱。
- 理由與來源：BG-003；`docs/bugs` assessment contract；使用者計畫 WP-04。
- 優先順序：Must
- 驗收：AC-009

### NFR-001 — 資料完整性

- 需求：任何發布碰撞、回滾衝突或 retirement 讀取失敗不得造成既有 approved bytes 遺失、競爭者 bytes 被刪除或 partial receipt。
- 理由與來源：P0 assessments。
- 優先順序：Must
- 驗收：AC-003、AC-004

### NFR-002 — 安全邊界

- 需求：redirect、junction、symlink、path escape、未知契約欄位、Ready coverage error 與 reviewer identity reuse 必須 fail closed；合法輸入不得被誤拒。
- 理由與來源：P1 assessments；security／path／schema contracts。
- 優先順序：Must
- 驗收：AC-005、AC-006、AC-007

### NFR-003 — 跨平台與效能

- 需求：適用的 Windows 與 Linux 驗證必須分別保存，普通 POSIX path 必須通過，且固定效能 workload 的每個正式 sample ≤ 2.0 秒。
- 理由與來源：既有 portability 與 performance contracts。
- 優先順序：Must
- 驗收：AC-005、AC-008

### NFR-004 — 可恢復性與可觀測性

- 需求：失敗必須保留 typed error、journal／復原材料、原始 command output、hash 與下一步；無法可靠判定時不得轉成成功或已修復。
- 理由與來源：delivery／implementation／BUG verification contracts。
- 優先順序：Must
- 驗收：AC-003、AC-004、AC-009

### TR-001 — 相容與範圍控制

- 需求：修復必須維持既有公開 CLI、JSON schema、2 秒門檻與現有 assessment bytes；若需求、介面或 schema 必須變更，工作必須停止並回到上游重新核准。
- 理由與來源：使用者計畫假設與 delivery revision contract。
- 優先順序：Must
- 驗收：AC-010

## 6. 驗收情境

### AC-001 — 16 個 BUG identity 可追蹤

- Given：repository 含 17 份 assessment、其中一個 BUG 有兩個 revision。
- When：執行盤點流程。
- Then：產生 16 個唯一 BUG rows，保留每個 revision 的連結，且每列含 status、owner、evidence 與 next action。
- 驗證需求：FR-001

### AC-002 — 修復狀態不被歷史數量取代

- Given：assessment 顯示 confirmed，但目前 BDD／regression 已通過或仍失敗。
- When：執行原始 symptom 與 regression oracle。
- Then：依實際 evidence 標示 `verified-fixed`、`still-reproducible`、`partial` 或 `insufficient-evidence`，不得只沿用 assessment disposition。
- 驗證需求：FR-002、FR-007

### AC-003 — 發布碰撞保留競爭者

- Given：兩個 writer 同時對同一 create-only target 發布。
- When：第二個 writer 遇到 collision。
- Then：只回報 collision；第一個 writer 的 target 保留，第二個 writer 的 temporary／partial target 清除，競爭者 bytes 不被覆寫。
- 驗證需求：FR-003、NFR-001

### AC-004 — 回滾只移除本次所有權

- Given：雙檔發布第一檔成功後，第二檔碰撞，且第一檔被獨立 writer 以相同 bytes 替換。
- When：目前 writer 執行 rollback。
- Then：獨立 replacement 與競爭者均保留；若復原無法安全完成，journal 保留 recovery-required 狀態與復原材料。
- 驗證需求：FR-003、NFR-001、NFR-004

### AC-005 — 路徑分類跨平台正確

- Given：普通 POSIX directory、真正 symlink／junction、ancestor redirect 與 inspection error。
- When：Candidate、promotion 與 Delivery 讀寫入口檢查 path。
- Then：普通 path 通過；redirect、escape 與 inspection error fail closed；Windows／Linux 結果符合同一語義。
- 驗證需求：FR-004、NFR-002、NFR-003

### AC-006 — Ready 與 schema 錯誤不繞過

- Given：缺 formal_paths、缺 Ready command coverage 或 page／claim／source 含未知 member 的輸入。
- When：各 persistence、Outcome、Delivery、seal 與 lint consumer 驗證。
- Then：全部拒絕並回傳 typed validation error；合法輸入仍通過。
- 驗證需求：FR-005、NFR-002

### AC-007 — fresh reviewer 必須獨立

- Given：preliminary 與 final report 使用相同 reviewer identity。
- When：required knowledge／terminal gate 驗證。
- Then：transition fail closed；不同 fresh identity 且其他條件通過時才可繼續。
- 驗證需求：FR-005、NFR-002

### AC-008 — 效能樣本可比較

- Given：固定 50,000 files／5,000 pages workload。
- When：執行 readiness、五次 cold 與五次 warm samples。
- Then：readiness 不計入正式樣本；每個正式 sample ≤ 2.0 秒、functional hash 相同、staged／dirty／untracked 變動結果正確、fixture 清除。
- 驗證需求：FR-006、NFR-003

### AC-009 — BUG 結案證據完整

- Given：一個 BUG 的 assessment、regression red／green、原始 pre/post oracle、full verification 與 reviewer evidence。
- When：產生結案 verification。
- Then：只有全部必要 evidence 通過才標 `verified-fixed`；否則標 `partial`／`insufficient-evidence`，並記錄殘餘風險與 follow-up。
- 驗證需求：FR-002、FR-007、FR-008、NFR-004

### AC-010 — 公開契約保持相容

- Given：修復工作完成。
- When：重算 Ready、schema、CLI、assessment bytes 與公開 command inventory。
- Then：無非核准 contract／schema／assessment 變更；若發現必要變更，工作回到重新規劃。
- 驗證需求：TR-001

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | status-review 中唯一 BUG rows 數 | 16 assessment identities | 16/16 有 status、owner、evidence、next action | WP-01；`docs/bugs/status-review.md` |
| KPI-002 | BG-002 | 具原始 pre/post、regression、full pass 與 reviewer binding 的 verification 數 | 0 | 每個宣告修復的 BUG 皆有 1 份 | WP-04；`docs/bugs/**/verifications/**` |
| KPI-003 | BG-002 | P0 競爭／回滾案例中資料遺失或覆寫次數 | 既有 assessment 所述失敗 | 0 | WP-02；Windows／Linux evidence |
| KPI-004 | BG-003 | 固定 workload 中正式 cold/warm sample 超過 2 秒的數量 | 既有尾延遲失敗 | 0 | WP-03；效能 runner report |
| KPI-005 | BG-003 | 完整適用 command 的 failure、skip、not_run 數 | 既有 work-specific baseline | 0 | WP-04；full validation report |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | FR-001、FR-002、FR-007 | AC-001、AC-002、AC-009 | KPI-001、KPI-002 |
| BG-002 | J-002、J-003 | FR-003、FR-004、FR-005 | AC-003 至 AC-007 | KPI-003 |
| BG-003 | J-001、J-004 | FR-006、FR-007、FR-008、NFR-003、NFR-004 | AC-002、AC-008、AC-009 | KPI-002、KPI-004、KPI-005 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：按 BUG identity 去重，assessment revision 保留在同一列；來源為使用者計畫與 `bug-assessment/v1` identity contract。
- D-002：以實際原始 oracle、regression 與 fresh review evidence 判定修復狀態；來源為 implementation／BUG verification contract。
- D-003：P0 資料完整性優先於其他工作；來源為使用者計畫的優先順序。
- D-004：維持公開 CLI、schema、2 秒門檻與原始 assessment bytes；來源為使用者計畫假設與相容性要求。

### 已確認假設

- A-001：目前 repository 內 16 個 BUG assessment 是本次盤點的完整清單；由 `rg --files docs/bugs` 驗證。
- A-002：既有 BDD／owner runner 為主要回歸入口；目前 governance 7、promotion 3、delivery 3、performance 2 個直接相關 scenario 已通過。
- A-003：沒有外部 issue tracker、部署或通知需求；本工作只保存 repository 與 Delivery evidence。

### 依賴與外部限制

- DEP-001：Windows／Linux execution capability；缺少任一適用平台時只能標示部分驗證。
- DEP-002：既有 `bug-assessment/v1`、`bug-verification/v1`、Ready plan、fresh review 與 Knowledge Gate validator。
- DEP-003：測試 runner 的 fixture safety policy；fixture 必須使用核准 temporary root 且完成清理。

### 延後至技術規劃的決策

- TP-001：哪些現有 runner、owner test 與 BDD scenario 可直接覆蓋每個 BUG，以及哪些需要新增 regression seam。
- TP-002：各 P0／P1／P2 BUG 的最小修復位置、WP DAG、Windows／Linux command inventory 與 verification file shape。
- TP-003：如何在不修改既有 assessment bytes 的前提下補足 status-review 與 verification artifacts。

## 10. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：需求已具備範圍、角色、旅程、功能與品質需求、負向／復原驗收、成功指標與追溯；純 HOW 保留給 Technical Planning。
