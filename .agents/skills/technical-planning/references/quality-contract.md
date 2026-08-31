# 技術規劃品質契約

本契約只判定 Candidate 資格，不重新定義規則。設計語義見[撰寫準則](candidate-authoring.md)，交接資料見[`ready-plan/v1`](ready-plan-contract.md)，狀態與寫入見[交付協定](delivery-protocol.md)。每項只回報 `Pass` 或帶證據的 `Fail`。

## 1. 來源與證據門檻

- 唯一來源、範圍、規範性要求、驗收、品質限制及相容／移轉條件可引用。
- 每項 Required oracle 均由適用環境的一手平台規範支持為可保證；被平台允許抑制或改變的要求已走需求缺口分支，沒有 Candidate。
- 需求缺口、阻塞未知與規格／現況／治理／平台衝突均為零。

### 證據品質

- 影響範圍內的治理、ADR、專案結構、版本、契約、測試、BDD、CI 與 Git baseline 已查證；未查區域未宣稱已理解。
- Brownfield current state 與 greenfield absence 都有 `SRC-*`；時效敏感事實含版本／日期與一手來源。
- `Observed`／`Required`／`Proposed` 分明；輸出不含秘密值。

## 2. 技術設計

- Current／target state、change impact 與每個 `TD-*` 足以由證據重建方案及取捨。
- Module、Interface、Seam 與 Adapter 選擇符合撰寫準則，公開 contract 可觀察且完整。
- 所有適用的資料、狀態、錯誤、品質、營運及移轉義務有設計；不適用內容未擴張範圍。
- 新形狀均為 `Proposed`；沒有無關重構、套件替換或 future-proofing。

## 3. 測試與工作包

- `BDD-FWK-*` 的既有或一手相容證據完整；每項適用驗收有可執行 `BDD-*`、正確 oracle red、映射的 `TEST-*` 與順序化 slice。
- Greenfield `BOOT-*` 符合撰寫準則且與全部 oracle 互斥，或以 current-state evidence 證明不適用。
- 每個 `CMD-*` 符合 [`ready-plan/v1`](ready-plan-contract.md)；獨立 BDD discovery、零 skipped、side effects、allowed writes 與 Proposed absence evidence 都可判定。
- 每個 `WP-*` 是可獨立驗證的垂直 slice；DAG 無環，setup／test／docs 跟隨行為，prefactor 可獨立證明降低本次風險。
- 正常、邊界、失敗、復原與適用品質屬性均有唯一最適測試層或具名人工程序，沒有不可執行佔位語。

## 4. Artifacts、追溯與風險

- `plan.md` 是唯一 primary，`handoff.json` 是唯一 handoff；supporting artifacts 符合模板拆分判準且由 primary 連結。
- Artifact manifest 只用 `role` 與 `approval_status`；沒有空白、佔位、重複權威或未引用 artifact。
- `handoff.json` 通過 schema 與 [`ready-plan/v1`](ready-plan-contract.md)跨欄位不變量，包括 approval identity、payload digest、baseline、hashes、sources、contract index、DAG、impact map 與 commands。
- Bug plan另通過assessment binding、唯一bug source、bug-reproduction command、regression refs與target-specific safeguards；standard plan缺BUG欄位時仍完整有效。
- `SRC-* → plan refs → contracts → WP-* → CMD-*／evidence` 可雙向追溯，沒有孤立項目。

### 風險與安全

- 每項風險含 trigger、impact 與可驗證 mitigation；假設有證據或明確確認。
- 高風險／受規範領域引用一手規範並指定專業審查，不提前宣稱合規或認證。
- Observed 與未來 execution evidence 分明；規劃過程的產品與外部狀態雜湊不變。

## 二元判定

- `Pass`：全部項目通過，形成 Candidate。
- `Fail`：記錄項目、證據與擁有規則的 reference，回到該階段修正。
- 必要證據或決策不可得：依交付協定進入 `Blocked`。
