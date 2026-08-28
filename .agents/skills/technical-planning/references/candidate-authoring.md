# Candidate 撰寫準則

只有證據門檻通過、準備形成 Candidate 時才讀取本文件。[技術規劃模板](technical-plan-template.md)是輸出 schema；[品質契約](quality-contract.md)負責二元驗收。本文件只定義如何做出規格與證據支持的設計選擇。

## Current state 與 target state

- 以規格造成的變更影響為中心描述 current state 與 target state，保留既有模式與契約。
- 來源需求使既有設計不足時，規劃最小的新 seam 或局部 prefactor；prefactor 必須直接降低需求變更風險且可獨立驗證。
- 專案相對路徑、symbols 與 signatures 只有在已觀察到時屬於 current state；尚未存在的形狀一律標為 `Proposed`。
- 每個難以反轉且有實質取捨的決策使用 `TD-*`，連接需求、證據、選定方案、理由、真實替代方案、拒絕原因及影響。

## Module、Interface、Seam 與 Adapter

- `Module`：內聚的行為邊界，由 Implementation 隱藏內部複雜度，對呼叫者提供小而一致的 contract。依專案證據可有一個或多個必要 entrypoints。
- `Interface`：呼叫者正確使用 Module 必須知道的完整 contract，包括輸入輸出、invariants、順序、錯誤、設定與品質特性。
- `Seam`：Interface 所在且行為可被觀察或替換的位置，也是呼叫者與測試驗證 contract 的邊界。
- `Adapter`：在 Seam 上滿足 Interface 的具體實作。

專案治理、ADR 與既有測試慣例是首選；下列分類只協助處理尚未由專案證據決定的依賴。優先沿用最高且穩定的既有 Seam。當依賴的執行位置、所有權或測試替身確實需要 contract 隔離時才建立 Adapter；單一 production implementation 直接留在 Module 內。

依依賴性質選擇驗證策略：

| 依賴性質 | 設計與測試策略 |
|---|---|
| In-process | 經 Module Interface 驗證，不新增 Adapter。 |
| Local-substitutable | 以本機可運行的真實替身跨內部 Seam 驗證。 |
| Remote but owned | Module 擁有 port，由 production 與 in-memory Adapter 分別滿足。 |
| True external | 注入外部 port，以受控 fake 或 mock Adapter 驗證自身行為。 |

只在來源規格適用時涵蓋資料模型、狀態轉換、公開契約、錯誤／超時／重試／復原、安全與隱私、效能與容量、可觀測性、移轉、部署與 rollback。

## 測試策略

Interface 是預設測試面。每項適用需求與驗收情境都指定：

- 測試目的與可觀察結果。
- 測試層級及 `SEAM-*`。
- fixture／輸入、前置狀態與獨立 oracle。
- 環境、Adapter 或外部替身。
- 可執行命令或具名人工程序，以及明確預期結果。

使用能穩定證明行為的最高 Seam；複雜純邏輯可使用更局部測試，契約與 Adapters 使用 integration／contract tests，關鍵旅程使用少量 E2E。人工驗證只承接無法可靠自動化的品質屬性，並指定角色、環境、步驟、結果與證據保存方式。

驗證公開行為與獨立 oracle；每個風險由最合適的一層證明一次。若實作採 TDD，工作包以行為切片完成 red → green。既有可執行命令標為 `Observed`；規劃新增的命令標為 `Proposed`，直到實作階段實際執行。

## 垂直工作包

每個 `WP-*` 是窄而完整的 tracer bullet，可單獨審查與驗證，並記錄：

- 目標、可觀察交付結果及需求／驗收情境。
- 真實 `Blocked by` 依賴；整體依賴圖保持無環。
- 受影響的 Modules、Interfaces、Seams 與有證據或 `Proposed` 的檔案範圍。
- `Consumes`／`Produces` contracts、implementation intent、測試方式與完成證據。

Setup、設定、文件、錯誤處理與測試跟隨需要它們的行為切片。獨立 prefactor 只在能先降低後續需求變更風險時成立，且本身具有可判定完成證據。以可觀察行為命名每包，使內容足以保留設計意圖而不展開逐行程式碼。

## 完整性要求

Candidate 必須讓每項適用來源義務沿 `需求／驗收 → TD-*／MOD-* → TEST-* → WP-* → 完成證據` 雙向追溯。每項設計都需規格或專案限制支持；規格範圍外的 future-proofing 不進入 Candidate。
