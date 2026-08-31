# Candidate 撰寫準則

只有證據門檻通過後才讀取。本文件只說明如何形成設計；[模板](technical-plan-template.md)定義文件形狀，[`ready-plan/v1`](ready-plan-contract.md)定義交接資料，[品質契約](quality-contract.md)只做二元判定。

## Current state 與 target state

- 以變更影響為中心描述 current／target state，保留有證據的模式與契約。
- 既有設計不足時，只規劃能直接降低本次需求風險且可獨立驗證的新 seam 或局部 prefactor。
- 路徑、symbol、signature 只有實際觀察到才屬於 current state；尚未存在的形狀是 `Proposed`。
- 難以反轉且有實質取捨的選擇使用 `TD-*`，連接需求、證據、選定方案、真實替代方案、拒絕原因與影響。

## Module、Interface、Seam 與 Adapter

- `Module`：內聚的行為邊界，由 Implementation 隱藏內部複雜度，對呼叫者提供小而一致的 contract。依專案證據可有一個或多個必要 entrypoints。
- `Interface`：呼叫者正確使用 Module 必須知道的完整 contract，包括輸入輸出、invariants、順序、錯誤、設定與品質特性。
- `Seam`：Interface 所在且行為可被觀察或替換的位置，也是呼叫者與測試驗證 contract 的邊界。
- `Adapter`：在 Seam 上滿足 Interface 的具體實作。

專案治理、ADR 與既有測試慣例優先。沿用最高且穩定的既有 Seam；只有依賴的執行位置、所有權或測試替身需要隔離時才建立 Adapter，單一 production implementation 留在 Module 內。

依依賴性質選擇驗證策略：

| 依賴性質 | 設計與測試策略 |
|---|---|
| In-process | 經 Module Interface 驗證，不新增 Adapter。 |
| Local-substitutable | 以本機可運行的真實替身跨內部 Seam 驗證。 |
| Remote but owned | Module 擁有 port，由 production 與 in-memory Adapter 分別滿足。 |
| True external | 注入外部 port，以受控 fake 或 mock Adapter 驗證自身行為。 |

只涵蓋來源規格實際觸及的資料／狀態、公開契約、錯誤／復原、安全／隱私、效能／容量、可觀測性、移轉、部署與 rollback。

## BDD、BOOT 與 scenario

Ready 計畫提供可執行的 outside-in contract。先沿用 manifests、lockfiles、feature／bindings、命令與 CI 已證明的 BDD framework；不存在時，以官方相容矩陣或上游版本證據選定 test-only framework、版本及安裝方式。無法證明與目標 runtime、build、runner、OS、CI 相容時進入 `Blocked`。

`BDD-FWK-*` 固定 framework／版本／來源／狀態、test-only 邊界、feature／binding／fixture／report paths、獨立 discovery、focused、full 與 CI commands，以及 filter、reporting 和零 skipped 判定。

每項適用驗收建立穩定的 `BDD-*`，連接來源要求、公開 `SEAM-*`、fixture、獨立 oracle、修改前正確 red、feature／binding、focused command、`TEST-*`、`WP-*` 與 slice order。正確 red 是目標行為缺失造成的 oracle assertion；syntax、undefined step、fixture、dependency、環境、load 或 runner error 都不是 red 證據。

完全 code-empty 且第一個公開 seam／entrypoint 不存在時，第一個行為 WP 內建立一個 `BOOT-*`；已有可載入 seam 時記錄不適用與 evidence。`BOOT-*` 只允許精確 path、公開 signature、最小 host wiring 與可由 fixture 觀察的 deterministic `Unimplemented` outcome。Sentinel 必須經公開 seam 成為 fixture 可捕捉的正常 observed actual；它不以未處理 exception、process crash、load 或 runner error 逸出。該 outcome 必須與所有驗收成功、錯誤及邊界 oracle 互斥；允許的內容不含領域分支、輸入轉換、規格輸出、外部呼叫、網路、持久化、狀態變更或新的 production dependency。

`BOOT-*` 另固定 build／load／discovery command、diff 邊界與第一個 BDD assertion mismatch。若無法建立同時可載入、行為中立且與所有 oracle 互斥的 bootstrap，進入 `Blocked`。

同一 WP 的 scenarios 依序執行；目前 `BDD-*` 取得正確 red、完成映射的 inner TDD 並 green 後，才開始下一個。非行為品質驗收若無法自動化，記錄理由、可判定程序與證據。

## BUG 修復 overlay

### Primary BUG plan

只有source assessment verdict為`confirmed | likely`且Requirements已核准時建立`bug_context`。它綁定assessment JSON／Markdown hashes、reproduction／root-cause狀態、verification target、original reproduction command與regression BDD／TEST refs。

- `verified`：original symptom已`reproduced | intermittent`且有`purpose: bug-reproduction` command；regression oracle必須能在修正前取得正確red並在修正後重跑原始症狀。
- `partial`：只用於原始症狀不能可靠pre/post；root cause維持低信心，並明列reason、proxy BDD／TEST red→green、residual risks及staging／具名人工follow-up。Reason明示不確定性，每項risk保留風險／可能性，每項follow-up使用驗證動作；不得用任何同義改寫把partial描述成已確定修復或validated／verified。

修法保持一個最小causal change。若實際red推翻assessment、修法失敗或scope擴大，計畫的執行分支是upstream reapproval，不是追加第二個猜測patch。

Standard delivery途中`affecting-current-work`回流的assessment，在重新核准WHAT後以`kind: supporting` evidence追溯，不建立`bug_context`。Primary `kind: bug`只用於已通過delivery assessment gate的bug work；若需要獨立primary bugfix則另開Work，不在Planning暗中轉換work kind。

## 測試策略

Interface 是預設測試面。每個 `TEST-*` 固定目的、層級／`SEAM-*`、fixture、前置狀態、獨立 oracle、替身、正確 red 與 focused／related command。使用能穩定證明行為的最高 seam；純邏輯才下沉 unit，契約／Adapter 使用 integration 或 contract，關鍵旅程只保留必要 E2E。

每個風險由最合適的一層證明一次。執行順序固定為目前 `BDD-*` outside-in red → 映射的 `TEST-*` red／minimal green／refactor-with-green → focused BDD 與 related green。命令資料完整形狀由 [`ready-plan/v1`](ready-plan-contract.md)唯一管理；未執行的新命令是 `Proposed`。

## 垂直工作包

每個 `WP-*` 是可單獨審查與驗證的窄垂直 tracer bullet：固定可觀察結果、需求／驗收、`blocked_by`、Modules／Seams／檔案範圍、consumed／produced contracts、implementation intent、依序 `BDD-*`／`TEST-*`、commands 與完成證據。整體 DAG 無環。

`BOOT-*` 跟隨第一個行為 slice，只建立可測 contract shape。Setup、設定、文件、錯誤與測試跟隨需要它們的行為；prefactor 只有能先降低本次變更風險且本身可判定時獨立成包。以可觀察行為命名，不展開逐行程式碼。

## 完整性要求

每項來源義務沿 `SRC-* → 需求／驗收 → TD-*／MOD-*／SEAM-* → BDD-* → TEST-* → WP-* → CMD-*／完成證據` 雙向追溯，且 `SRC-*` 直接映射受影響 WP。不可重取的對話或暫態來源依 Ready contract materialize；revision impact 由 direct mappings 加 DAG downstream closure 重算。每項設計由規格或專案限制支持；範圍外 future-proofing 不進入 Candidate。
