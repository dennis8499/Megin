# 需求分析：Skills Script 執行效率改善

- 文件狀態：Ready
- 日期：2026-09-02
- 文件範圍：降低 Project Knowledge query、Delivery transition 與 knowledge scale benchmark 的執行成本，同時維持既有行為與安全契約
- 需求來源：使用者 2026-09-02 明示需求；現行 scripts、owner tests、Ready project-knowledge plan 與 Delivery behavior evidence
- 確認者：user；approval evidence `conversation:requirements-work-20260902-skill-script-performance-0ae7b62a-candidate-1`

## 1. 執行摘要

### 問題或機會

Repository maintainer 執行 Project Knowledge query 與 Delivery workflow 時，同一操作會重複啟動 Git／ripgrep child processes。診斷基準顯示 audit query 約 22 個 subprocess、完整 Delivery probe 約 10 個 Git processes，而單一 Ready transition 可達約 31 個 Git calls；大規模 benchmark 的 clean fixture setup 約 177 秒。

### 為何現在做

現有功能與安全測試已成熟，適合在可量測的行為等價門檻下減少重複 I/O。若不處理，日常 query、transition、測試與 CI feedback latency 會隨使用頻率累積，且目前只量 warm query，無法揭露 fresh-process 成本。

### 預期成果

- BG-001：在不犧牲公開行為、安全檢查或跨平台一致性的前提下，顯著降低目標 Skills scripts 的 child-process 與 wall-clock 成本。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Repository maintainer | 執行 query、Delivery workflow、tests 與 benchmark，取得較快且等價的結果 | 可啟動既有 CLI；不得因效能模式繞過安全或 drift gate |
| ACT-002 | Reviewer／CI operator | 驗證行為等價、效能 budget、full suites 與跨平台結果 | 只接受可重現 evidence；不得以單機結果冒充 Windows／Linux 證明 |
| ACT-003 | Skill owner | 維護 public JSON、error、安全與 benchmark contracts | 可核准 additive benchmark fields；其他 public contract 變更不在本成果內 |

## 3. 範圍與優先順序

### 範圍內

- Project Knowledge query 的重複 Git／ripgrep child-process 成本與結果等價。
- Delivery repository probe、start／locate／transition 路徑的重複 Git child-process 成本與 freshness/safety 等價。
- 50,000 tracked files／5,000 pages benchmark 的 cold／warm 可觀測性與 fixture setup 時間。
- 對應 owner BDD、inner tests、related/full suites 與 Windows／Linux portability evidence。

### 範圍外

- Tokenizer、ranking、citation、eligibility 或 versioned error 語義變更。
- Persistent index、daemon、跨 process cache、network service或新 runtime dependency。
- 未先證實行為等價的 `git fast-import` fixture 建立方式。
- Validators、Technical Planning BFS、Bug revision glob 與其他非主要瓶頸 scripts。

### 非目標

- 不追求零 child process。
- 不以刪除安全檢查、降低 full-suite coverage 或放寬 2 秒 portability ceiling 換取速度。
- 不要求本次同時變更所有 36 個 Python scripts。

### 優先順序

Must：行為與安全等價；Must：deterministic process budgets；Must：跨平台 benchmark contract；Should：同機 wall-clock 改善。任何 correctness/security regression 優先阻止交付。

## 4. 使用者與業務旅程

### J-001 — 執行 Project Knowledge query

- 主要角色：ACT-001
- 觸發與前置條件：Repository 可讀、Git/ripgrep 可用、query input 有效。
- 主要流程：maintainer 執行 query，系統搜尋符合資格的 evidence、驗證 drift，回傳既有 JSON 結果。
- 替代、例外與復原：cache drift、source drift、redirect、pathological path 或 tool error 仍依既有 contract fail closed／fallback。
- 完成結果：結果與 baseline 等價，且 child-process budget 與 cold latency 達標。
- 相關需求：BR-001、FR-001、NFR-001、NFR-003。
- 驗收情境：AC-001、AC-002。

### J-002 — 執行 Delivery transition

- 主要角色：ACT-001
- 觸發與前置條件：有效 delivery record、正確 worktree/branch、必要 lock 可取得。
- 主要流程：maintainer 執行 probe／locate／transition，系統驗證 repository identity、mutable state、安全 gate 與 Ready continuity。
- 替代、例外與復原：path、HEAD、lock freshness、submodule、filter、hook、trust、redirect 或 dirty-state 不符合時仍重新驗證或拒絕。
- 完成結果：public output/error 不變，freshness evidence 成立，Git process budget 與 transition latency 達標。
- 相關需求：BR-001、FR-002、NFR-002、NFR-003。
- 驗收情境：AC-003、AC-004。

### J-003 — 執行 scale benchmark 與 CI

- 主要角色：ACT-002
- 觸發與前置條件：可建立 50k/5k fixture 的隔離環境及 Windows／Linux runners。
- 主要流程：建立 fixture，分別量測 fresh-process cold 與 same-process warm queries，比較 ceiling 與 functional hash。
- 替代、例外與復原：任一 sample 超標、hash 不同、field 缺失或 fixture 未清除時失敗；未達 setup 改善門檻時停止擴 scope並另案 profile。
- 完成結果：report 可區分 cold/warm，兩平台結果一致，fixture cleanup 完成。
- 相關需求：FR-003、FR-004、NFR-001、TR-001。
- 驗收情境：AC-005、AC-006、AC-007。

## 5. 需求

### BR-001 — 效能改善不得改變既有契約

- 需求：Skills script 效能改善必須在不改變公開結果、錯誤與安全契約的前提下，降低 Project Knowledge query 與 Delivery transition 的 child-process 成本，並以 cold／warm benchmark 驗證。
- 理由與來源：BG-001、J-001..003；`.agents/skills/project-knowledge/scripts/test_behavior.py:2` 與 `.agents/skills/delivery-orchestrator/scripts/behavior-evaluation-report.md:1` 證明 owner behavior surfaces 已存在。
- 優先順序：Must；correctness/security 優先於速度。
- 驗收：AC-001、AC-003、AC-005、AC-007。

### FR-001 — Query process budget 與結果等價

- 需求：系統必須讓固定 audit query 在每次 invocation 使用不超過 10 個 child processes，且 JSON、排序、citation、cache、drift、redirect、golden evaluator 與 pathological-path fallback 結果與核准 baseline 等價。
- 理由與來源：J-001；observed baseline 為約 22 subprocess。
- 優先順序：Must。
- 驗收：AC-001、AC-002。

### FR-002 — Delivery Git budget 與 fresh safety evidence

- 需求：系統必須讓完整 repository probe 使用不超過 6 個 Git child processes、clean Ready transition 使用不超過 8 個，且 transition 在 lock 後仍持有與 canonical worktree、HEAD 及 mutable state 相符的 fresh evidence。
- 理由與來源：J-002；observed baseline 約 10／31 Git calls，既有 Delivery behavior contract要求 fail closed。
- 優先順序：Must。
- 驗收：AC-003、AC-004。

### FR-003 — Cold／warm benchmark report

- 需求：benchmark report 必須保留既有 `durations_seconds.queries` 作為五個 same-process warm samples，並新增五個 fresh-process cold samples與 fixture setup timing。
- 理由與來源：J-003；現行 benchmark 先 warm 再計時，不能代表 fresh CLI。
- 優先順序：Must。
- 驗收：AC-005、AC-006。

### FR-004 — 可回收的測試與 benchmark state

- 需求：所有新舊 performance tests與 benchmark 必須在成功及失敗路徑清除 repository fixture與 OS temporary state，完成後 Git status 必須回到執行前 baseline。
- 理由與來源：J-003、NFR-001；現有 owner runners使用 disposable fixtures。
- 優先順序：Must。
- 驗收：AC-006。

### NFR-001 — Query 與 portability 時間門檻

- 需求：normal cold query 的同機五次中位數必須相對 implementation 前 fresh baseline改善至少 25%；Windows／Linux 上每個 cold及warm benchmark sample必須不超過 2.0 秒。
- 理由與來源：BG-001；既有 50k/5k Ready plan以每個 timed operation ≤2秒為 portability contract，見 `docs/work/work-20260831-project-knowledge-system-19202d78/plan-3/handoff.json:1`。
- 優先順序：Must。
- 驗收：AC-002、AC-005。

### NFR-002 — Delivery transition 時間門檻

- 需求：clean Ready transition 的同機五次中位數必須相對 implementation 前 fresh baseline改善至少 25%。
- 理由與來源：BG-001、J-002。
- 優先順序：Should；deterministic Git budget與安全等價仍為 Must。
- 驗收：AC-003。

### NFR-003 — Runtime 與安全限制

- 需求：改善後系統不得新增 runtime dependency、network requirement、persistent daemon/index或跨 invocation cache，且不得降低 submodule、filter、hook、trust、redirect、dirty-state、HEAD/lock drift檢查。
- 理由與來源：BR-001、J-001、J-002及既有 Delivery behavior evidence。
- 優先順序：Must。
- 驗收：AC-004、AC-007。

### TR-001 — Benchmark consumer 相容性

- 需求：既有 consumer 必須能繼續讀取原 `durations_seconds.queries` warm field；新增 cold／fixture fields 必須由更新後 comparator與 Windows／Linux CI共同驗證。
- 理由與來源：J-003；避免現有 report contract被破壞。
- 優先順序：Must。
- 驗收：AC-005、AC-007。

## 6. 驗收情境

### AC-001 — Audit query 行為與 process budget

- Given：固定 repository fixture、audit query、baseline JSON與 recording child runner。
- When：ACT-001 執行一次 query。
- Then：完整結果與 baseline 等價，且 child process總數 ≤10。
- 驗證需求：BR-001、FR-001。

### AC-002 — Query drift與時間

- Given：cache hit、byte drift、redirect、ranking、golden與 pathological path fixtures，以及 implementation 前 fresh baseline。
- When：依序執行相關 query scenarios與五次 fresh normal queries。
- Then：所有既有 fail-closed/fallback oracle通過，五次中位數改善 ≥25%。
- 驗證需求：FR-001、NFR-001。

### AC-003 — Delivery probe／Ready transition budget

- Given：clean delivery fixture、recording Git runner與 implementation 前 transition baseline。
- When：執行 full probe與五次 clean Ready transition。
- Then：full probe ≤6 Git calls、每次 Ready transition ≤8，且 transition中位數改善 ≥25%。
- 驗證需求：FR-002、NFR-002。

### AC-004 — Delivery safety與freshness

- Given：HEAD、path、lock epoch、submodule、filter、hook、trust、redirect及dirty-state變化 fixtures。
- When：執行 probe reuse與transition。
- Then：只有相符的 fresh evidence可被接受；所有 mismatch重新驗證或以既有error contract拒絕，owner safety suites全綠。
- 驗證需求：FR-002、NFR-003。

### AC-005 — Cold／warm跨平台報告

- Given：Windows及Linux 50k tracked files／5k pages fixture。
- When：CI執行benchmark與comparator。
- Then：每份report含五個cold與五個warm samples且每個≤2.0秒，兩平台functional hash相同。
- 驗證需求：FR-003、NFR-001、TR-001。

### AC-006 — Fixture setup與cleanup

- Given：implementation前clean setup baseline及三次相同規模fixture runs。
- When：執行setup、測量與故障注入cleanup。
- Then：setup三次中位數改善 ≥15%，parent-directory操作只隨unique parents成長，成功／失敗後temp paths均不存在且Git status回復。
- 驗證需求：FR-004。

### AC-007 — Full regression與相容性

- Given：全部owner、related、full、validator與portability commands。
- When：ACT-002 fresh執行完整驗證。
- Then：零failure、零unexpected skip、public contracts相容，且沒有新dependency/network/persistent state。
- 驗證需求：BR-001、NFR-003、TR-001。

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | audit query child-process count | 約22 | ≤10 | 每次focused BDD／recording runner |
| KPI-002 | BG-001 | full probe／Ready transition Git calls | 約10／31 | ≤6／≤8 | 每次Delivery performance BDD |
| KPI-003 | BG-001 | normal cold query五次中位數 | implementation前fresh重測 | 改善≥25% | 同機、同fixture、WP-001完成時 |
| KPI-004 | BG-001 | clean Ready transition五次中位數 | implementation前fresh重測 | 改善≥25% | 同機、同fixture、WP-002完成時 |
| KPI-005 | BG-001 | clean fixture setup三次中位數 | 約177秒整體wall；implementation前拆出setup重測 | setup改善≥15% | 同機50k/5k、WP-003完成時 |
| KPI-006 | BG-001 | Windows/Linux query ceiling與hash | warm約0.802–0.898秒 | 每sample≤2.0秒且hash相同 | portability CI |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | BR-001、FR-001、NFR-001、NFR-003 | AC-001、002、007 | KPI-001、003、006 |
| BG-001 | J-002 | BR-001、FR-002、NFR-002、NFR-003 | AC-003、004、007 | KPI-002、004 |
| BG-001 | J-003 | FR-003、FR-004、NFR-001、TR-001 | AC-005、006、007 | KPI-005、006 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：correctness/security優先於效能；來源為使用者核准的改善範圍與既有owner contracts。
- D-002：本次只處理已量測的Query、Delivery與benchmark瓶頸，不擴到所有scripts。
- D-003：benchmark cold fields採additive contract，既有warm key保留。

### 已確認假設

- A-001：Python、Git、ripgrep仍為既有執行環境；依據現行scripts與CI。
- A-002：本成果不新增UI、外部使用者資料、權限角色或第三方整合，因此無障礙、在地化、隱私資料生命週期與法規控制面不適用。

### 依賴與外部限制

- DEP-001：Windows／Linux runner必須可建立50k/5k fixture並提供真實portability reports。
- DEP-002：Delivery owner tests必須保留Git hardening與fail-closed fixtures。
- DEP-003：Project Knowledge owner tests與golden evaluator是query等價的source of truth。

### 延後至技術規劃的決策

- TP-001：query invocation-scoped snapshot與fixed-pattern multi-search的internal shape。
- TP-002：Delivery identity/state probe decomposition、metadata batching與fresh-evidence provenance shape。
- TP-003：cold child runner、unique-parent fixture plan與comparator欄位實作。
- TP-004：若KPI-005未達標，是否另案採用`git fast-import`及其等價性證明。

## 10. 完整性與開放事項

- 阻塞性開放事項：無。
- 13面覆蓋：問題、角色、scope、journeys、功能、品質、邊界、相容、風險與acceptance已確認；無UI／外部資料／法規／人工營運流程的面向依A-002判定不適用。
- 單一需求品質：BR-001、FR-001..004、NFR-001..003、TR-001逐項通過必要、明確、單一、可行、可驗證與追溯檢查。
- 驗收品質：AC-001..007均有Given／When／Then、客觀門檻與對應需求。
- 整份文件品質：通過；沒有未定義關鍵詞、衝突、純HOW或阻塞性缺口。
