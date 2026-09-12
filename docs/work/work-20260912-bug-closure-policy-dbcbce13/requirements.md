# 需求分析：BUG 結案與阻塞處置規則 v2

- 文件狀態：Candidate—Awaiting confirmation
- 日期：2026-09-12
- 文件範圍：建立一套可追溯、可限時處理的 BUG verification 與結案處置規則；不直接修復本次 16 個 BUG。
- 需求來源：使用者同意重新制定可行規則；目前 16 個去重 BUG 的盤點與既有 assessment；專案既有 Delivery、Human Gate、create-only evidence 與 Windows/Linux 驗證治理。
- 確認者：待使用者核准本次 exact review bundle。

## 1. 執行摘要

### 問題或機會

目前專案有 17 份 assessment，按 BUG ID 去重為 16 項。既有 remediation 已取得多項 proxy、full-suite 與跨平台證據，但仍有原始症狀未完整重現、效能樣本超標、Ready handoff 契約缺口及獨立 reviewer 未完成等情況。若只有「已結案／未結案」或單一 Blocked 狀態，會把產品缺陷、證據不足、環境阻塞與契約阻塞混為一談，也容易造成無限期等待或過度宣稱修復。

### 為何現在做

目前 remediation work 的 16 項均只能列為部分驗證／待追蹤；其中至少一項性能樣本保留超過 2 秒門檻，且既有多 BUG work 無法以單一 bug_context 合法綁定逐項 verification。現在建立規則可使後續決策可追溯，也可在不改寫歷史 evidence 的前提下重新分類與限時升級。

### 預期成果

- BG-001：每個 BUG 都能以互斥且可查證的處置狀態描述目前結論，不把「無法驗證」誤稱為「已修復」或「仍存在」。
- BG-002：所有已宣告修復的 BUG 都有原始症狀、回歸、完整驗證與獨立審查的可查證鏈結。
- BG-003：多 BUG 工作能保留一個共同工作範圍，同時為每個 BUG 綁定獨立的 assessment、verification、風險與下一步。
- BG-004：證據、環境、契約與 reviewer 阻塞都有 owner、期限、升級與最終處置，不會永久停留在無責任的 Blocked。
- BG-005：超標、失敗及歷史 assessment evidence 具 append-only 保存與可重算追溯性。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | BUG／Implementation owner | 建立 reproduction、回歸、完整驗證與追蹤資料；更新 owner、期限及下一步 | 不得自行把 partial、blocked 或 failed 改成 fixed-verified |
| ACT-002 | Independent reviewer | 以不同 identity 核對修復 snapshot、verification 與 evidence | 不得審查自己產生的唯一修復證據 |
| ACT-003 | Product／Risk owner | 決定 accepted-risk、deferred 或 release boundary | Critical／High 的風險接受必須明確核准並設定到期日 |
| ACT-004 | Delivery／Governance owner | 驗證狀態轉換、契約綁定、人工 Gate 與歷史保留 | 不得繞過 Requirements、Planning、Implementation 或 Knowledge Gate |
| ACT-005 | Platform／Performance owner | 提供 Windows／Linux、效能基準與量測條件；處理環境阻塞 | 不得刪除超標樣本或以重跑結果覆寫失敗結果 |
| ACT-006 | Human approver | 核准 exact Candidate、政策版本與風險處置 | 核准只適用於明確列出的 review bundle 與 identity |

## 3. 範圍與優先順序

### 範圍內

- 定義 BUG verification result 與 disposition 的分工、合法狀態及轉換。
- 增加 evidence-pending、environment-blocked、contract-blocked、accepted-risk、deferred 等可追蹤處置。
- 保留既有 bug-verification/v1 的 verified、partial、failed 語義；新增規則不得用新狀態削弱既有 verified-fix 門檻。
- 定義多 BUG 工作的共同範圍與逐 BUG verification 綁定。
- 定義證據保留、效能超標處理、獨立 reviewer、owner、期限與升級。
- 重新盤點目前 16 項，但不回寫或改造歷史 assessment、既有 Approved Ready handoff 或既有 Outcome。

### 範圍外

- 本次 16 個 BUG 的產品程式修復本身。
- 變更公開 CLI、產品 JSON schema、性能 2 秒門檻或既有 assessment 內容。
- 以文件規則直接判定目前 16 項全部已修復或全部仍存在。
- 自動建立 issue、通知、commit、push、merge 或 deploy。

### 非目標

- 不以降低證據要求、放寬 reviewer 獨立性或刪除失敗樣本來提高結案率。
- 不把 not reproducible、environment-blocked 或 contract-blocked 當成 fixed-verified。
- 不將 accepted-risk 當成修復完成；它只是有期限、有人負責的風險決策。

### 優先順序

安全、資料完整性、稽核可追溯性優先於結案速度；Critical／High 優先處理。任何狀態在缺少必要 evidence、權限或人工核准時都必須 fail closed。

## 4. 使用者與業務旅程

### J-001 — BUG 從發現到結案或限時處置

- 主要角色：ACT-001、ACT-004、ACT-002、ACT-003
- 觸發與前置條件：存在有效 assessment 或新發現的 BUG，且有明確 BUG ID、版本與證據入口。
- 主要流程：建立或延續 BUG record；執行原始症狀 reproduction 與回歸；分別記錄 verification result 與 disposition；補齊 owner、期限、證據與下一步；在條件滿足時由獨立 reviewer 與適用人工 Gate 核對；將 fixed-verified 結案，或將其他狀態限時追蹤。
- 替代、例外與復原：原始症狀不可重現時進入 evidence-pending；工具鏈／平台不可用時進入 environment-blocked；Ready 或 verification schema 不可表達時進入 contract-blocked；產品風險暫不修復時進入 accepted-risk 或 deferred；新的 reproduction 或超標樣本出現時重新開啟並保留舊狀態與 evidence。
- 完成結果：每個 BUG 有一個 current disposition、可重算的 verification result、owner、下一步、期限與 evidence manifest；fixed-verified 以外的狀態不得輸出 resolved／fixed 結案語句。
- 相關需求：FR-001、FR-002、FR-003、FR-004、FR-005、FR-006、FR-007、FR-008、FR-009、FR-010、NFR-001、NFR-002、NFR-003、NFR-004。
- 驗收情境：AC-001 至 AC-010。

## 5. 需求

### BR-001 — verification 與 disposition 分離

- 需求：BUG record 必須分開保存既有 verification result（verified、partial、failed）與目前 disposition；兩者不得互相覆寫或推導成未經證據支持的結論。
- 理由與來源：BG-001、BG-002；既有專案治理要求 partial 不得宣稱 fixed，來源為 docs/work/work-20260903-unified-skill-entry-198002a2/implementation/outcome-3.md:7 與既有 bug-verification/v1 契約。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003。

### BR-002 — fixed-verified 的封閉條件

- 需求：只有同時具備原始症狀 pre／post 結果、regression red→green、所有必要 full verification 通過、獨立 reviewer 與適用人工 Gate 通過時，disposition 才可為 fixed-verified。
- 理由與來源：BG-002；既有 Human Gate 與跨平台 evidence 原則。
- 優先順序：Must。
- 驗收：AC-001。

### FR-001 — 互斥處置狀態

- 需求：系統必須支援且同一時間只選一個 current disposition：confirmed-open、fixed-verified、evidence-pending、environment-blocked、contract-blocked、accepted-risk、deferred 或 rejected。
- 理由與來源：BG-001；目前盤點需要區分產品結論與流程阻塞。
- 優先順序：Must。
- 驗收：AC-002、AC-003、AC-004、AC-005、AC-006。

### FR-002 — confirmed-open

- 需求：當目前版本仍能重現原始症狀時，BUG 必須標為 confirmed-open，並保留重現版本、command、oracle、raw evidence、owner 與修復下一步。
- 理由與來源：BG-001；assessment observed／expected／reproduction evidence。
- 優先順序：Must。
- 驗收：AC-002。

### FR-003 — evidence-pending

- 需求：當原始症狀無法判定、只有 proxy、缺少 red→green 或缺少必要 evidence 時，BUG 必須標為 evidence-pending，且不得標為 fixed-verified。
- 理由與來源：BG-001、BG-002；目前 16 項盤點的部分驗證結果。
- 優先順序：Must。
- 驗收：AC-003。

### FR-004 — environment-blocked

- 需求：當工具鏈、作業系統、檔案系統或測試環境阻止必要驗證時，BUG 必須標為 environment-blocked，並記錄環境 identity、缺失能力、替代方案、owner、期限與是否阻止發布；不得據此判定產品已修復或仍存在。
- 理由與來源：BG-001、BG-004；既有 Windows/Linux portability 與 evidence bundle 治理。
- 優先順序：Must。
- 驗收：AC-004。

### FR-005 — contract-blocked

- 需求：當 Ready plan、bug_context、verification schema、manifest 或 reviewer contract 無法表達目前工作時，BUG 必須標為 contract-blocked，並記錄缺口、受影響的驗證、負責修訂的角色與期限；不得直接改寫歷史核准 artifact。
- 理由與來源：BG-003、BG-004；目前多 BUG handoff 缺 bug_context 的實際阻塞。
- 優先順序：Must。
- 驗收：AC-005。

### FR-006 — accepted-risk 與 deferred

- 需求：accepted-risk 或 deferred 必須記錄風險 owner、核准角色、理由、緩解措施、影響範圍、到期日、重新開啟條件與下一次檢查；Critical／High 不得由單一 implementation owner 自行核准。
- 理由與來源：BG-004；使用者同意的限時風險處置方向。
- 優先順序：Must。
- 驗收：AC-006。

### FR-007 — 多 BUG 逐項綁定

- 需求：系統必須能以一個共同 work scope 綁定多個 BUG，並為每個 BUG 保存唯一 assessment revision、verification result、disposition、evidence、owner 與 next action；任何單一 BUG 的缺口不得被其他 BUG 的通過結果覆蓋。
- 理由與來源：BG-003；目前 16 BUG plan 與單一 bug_context 不相容。
- 優先順序：Must。
- 驗收：AC-005、AC-010。

### FR-008 — append-only 證據與歷史

- 需求：系統必須保留每次狀態轉換、失敗樣本、超標樣本、recovery material、journal、receipt、review identity 與 evidence hash；新結論只能新增 revision 或 transition，不得覆寫既有 assessment、Outcome 或失敗 raw output。
- 理由與來源：BG-005；create-only Outcome、Human Gate 與 project knowledge evidence 原則，來源為 docs/work/work-20260831-project-knowledge-system-19202d78/implementation/outcome.md:7。
- 優先順序：Must。
- 驗收：AC-007、AC-009。

### FR-009 — 效能樣本處置

- 需求：當任一正式效能樣本超過既有門檻時，系統必須保留該樣本與完整環境資訊，並將 BUG 保持在未完成的 disposition；只有經明確核准的量測異常分類、根因、重測條件與風險處置後，才可進入下一個決策，不得以成功重跑刪除或取代超標結果。
- 理由與來源：BG-005；BDD-016 assessment 與既有 2 秒契約。
- 優先順序：Must。
- 驗收：AC-007。

### FR-010 — 獨立 reviewer

- 需求：fixed-verified 與適用的 accepted-risk 必須記錄不同於 implementation owner 的 reviewer identity、review scope、review version、raw report 與核准結果；沒有適格 reviewer 時只能保持 blocked 或 pending。
- 理由與來源：BG-002、BG-004；既有 fresh reviewer contract。
- 優先順序：Must。
- 驗收：AC-001、AC-008。

### FR-011 — 可追蹤輸出

- 需求：每個 current BUG disposition 必須可輸出 BUG ID、assessment revision、verification result、evidence refs、owner、下一步、期限、阻塞分類、責任角色、風險核准與 reopen 條件。
- 理由與來源：BG-001、BG-004、BG-005。
- 優先順序：Must。
- 驗收：AC-008、AC-010。

### TR-001 — 歷史相容與重新盤點

- 需求：既有 assessment、Outcome、Ready plan、validation bundle 與 remediation run 必須保持可讀；新規則套用時只能新增 policy revision、status review 或 child record，不得回寫歷史 bytes；目前 16 項的既有「部分驗證」結果須保留並重新附加 disposition。
- 理由與來源：BG-005；既有 Human Gate 對 historical artifacts 不重寫的要求。
- 優先順序：Must。
- 驗收：AC-009、AC-010。

### NFR-001 — fail-closed 安全性

- 需求：缺少必要 evidence、hash、approval、reviewer identity、owner 或期限時，結案判定必須失敗並輸出明確阻塞原因。
- 理由與來源：BG-002、BG-004；Delivery 與 project-knowledge 的 fail-closed Gate。
- 優先順序：Must。
- 驗收：AC-001、AC-003、AC-004、AC-005。

### NFR-002 — 可追溯性

- 需求：每個 disposition 變更必須能追溯至 BUG ID、assessment revision、工作 ID、版本、命令、raw output、evidence hash、決策角色與時間。
- 理由與來源：BG-001、BG-005；來源為 docs/work/work-20260907-workflow-speed-d0b3946d/implementation/outcome.md:3。
- 優先順序：Must。
- 驗收：AC-008、AC-009。

### NFR-003 — 跨平台一致性

- 需求：適用的路徑、安全、資料完整性與效能結案規則必須在 Windows 與 Linux 使用相同語義；單一平台通過只能形成部分或平台限定證據，不得直接形成跨平台 fixed-verified。
- 理由與來源：BG-001、BG-002；既有 Windows/Linux portability evidence 要求。
- 優先順序：Must。
- 驗收：AC-004、AC-010。

### NFR-004 — 限時處置

- 需求：自 T0 起 1 個工作日內必須指定 owner 與下一步；T0+3 個工作日內必須分類 blocker；T0+5 個工作日內未解除時必須升級；T0+10 個工作日內必須做出 fix、replan、accepted-risk、deferred 或 rejected 的明確決策，並設定下一個期限。
- 理由與來源：BG-004；使用者同意的 timeboxed escalation 方向；具體日數為本政策的預設可行值。
- 優先順序：Must。
- 驗收：AC-008。

### NFR-005 — 量測完整性

- 需求：效能報告必須保存每一個正式樣本、readiness 與正式計時邊界、環境資訊、功能 hash、fixture 狀態及 cleanup 結果；不得只保存成功摘要。
- 理由與來源：BG-005；BDD-016／BDD-020 的固定 workload 與 evidence 要求。
- 優先順序：Must。
- 驗收：AC-007。

### NFR-006 — 人工 Gate 相容性

- 需求：政策 Candidate、review bundle 與核准必須遵守 file-first、Summary-only Chat、exact identity、payload hash 與 create-only 歷史規則；不得增加未綁定的第三道核准 Gate。
- 理由與來源：來源為 docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/requirements.md:105 與 docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/plan/plan.md:62。
- 優先順序：Must。
- 驗收：AC-009。

### NFR-007 — 既有結果相容

- 需求：既有 bug-verification/v1 的 verified、partial、failed 結果必須保持可讀且語義不變；新 disposition 欄位缺失時不得默認為 fixed-verified。
- 理由與來源：BG-002；既有 partial／verification 分離原則。
- 優先順序：Must。
- 驗收：AC-003、AC-009。

## 6. 驗收情境

### AC-001 — 未完整驗證不得固定結案

- Given：一個 BUG 有 proxy green 與 full suite pass，但缺少原始症狀 post-fix evidence 或獨立 reviewer。
- When：執行結案判定。
- Then：判定不得為 fixed-verified，輸出缺口並保持 evidence-pending 或 blocked。
- 驗證需求：BR-001、BR-002、FR-003、FR-010、NFR-001。

### AC-002 — 目前症狀仍存在

- Given：目前版本在受控 fixture 中仍重現原始症狀且 raw oracle 通過。
- When：更新 BUG current disposition。
- Then：結果為 confirmed-open，保留版本、命令、raw evidence 與下一步，不得標為 partial 或 fixed-verified。
- 驗證需求：FR-002。

### AC-003 — 只有 proxy 證據

- Given：proxy BDD 與 full suite 通過，但原始症狀 pre／post 結果 inconclusive。
- When：執行 verification 與結案判定。
- Then：verification_result 可為 partial，但 disposition 必須為 evidence-pending；摘要不得使用 fixed、resolved 或 equivalent wording。
- 驗證需求：BR-001、FR-003、NFR-007。

### AC-004 — 環境能力阻塞

- Given：必要 Linux native toolchain 或 Windows filesystem capability 不可用，導致必要案例無法執行。
- When：保存本次結果。
- Then：disposition 為 environment-blocked，保存環境 identity、缺失能力、替代方案與期限；產品修復結論保持未知。
- 驗證需求：FR-004、NFR-001、NFR-003。

### AC-005 — 多 BUG 契約阻塞與逐項隔離

- Given：同一 work scope 涵蓋兩個以上 BUG，但單一 bug_context 無法表達全部 BUG。
- When：提交 verification 或結案。
- Then：每個 BUG 都有獨立 context／record；未補契約前標為 contract-blocked；其中一個 BUG 的 pass 不得覆蓋另一個 BUG 的缺口。
- 驗證需求：FR-005、FR-007、FR-011、NFR-003。

### AC-006 — 有期限的風險接受

- Given：High BUG 暫不修復但有明確緩解措施。
- When：Product／Risk owner 提交 accepted-risk。
- Then：記錄 owner、核准者、理由、緩解、到期日、reopen 條件；缺任一欄位則拒絕 accepted-risk。
- 驗證需求：FR-006。

### AC-007 — 效能超標樣本保留

- Given：固定 workload 的正式樣本中有一筆超過 2 秒，後續重跑通過。
- When：產生效能 disposition。
- Then：超標 raw sample、環境與 hash 仍可查證；成功重跑不能覆蓋它；BUG 保持未完成，除非明確完成量測異常或風險處置。
- 驗證需求：FR-009、FR-008、NFR-005。

### AC-008 — 阻塞逾期升級

- Given：BUG 在 T0+3 被分類為 contract-blocked 或 environment-blocked，T0+5 仍未解除。
- When：執行追蹤排程。
- Then：系統產生升級事件，指定負責角色與新期限；T0+10 前必須有 fix、replan、accepted-risk、deferred 或 rejected 決策。
- 驗證需求：FR-011、NFR-002、NFR-004。

### AC-009 — 歷史與 Gate 不變

- Given：既有 assessment、Outcome、Ready handoff、失敗 evidence 與 promotion receipt 已存在。
- When：套用 Policy v2。
- Then：歷史 bytes 不變；新 policy／status／revision 以 create-only 或 append-only 方式產生；核准仍使用 file-first、Summary-only Chat 與 exact identity。
- 驗證需求：FR-008、TR-001、NFR-006、NFR-007。

### AC-010 — 跨平台與逐項結論

- Given：Windows 與 Linux 的同一測試案例結果不同，或共同 work scope 中不同 BUG 的結果不同。
- When：計算工作結論。
- Then：只對各平台／各 BUG 產生相應 evidence；整體不得因部分通過而標為無條件 fixed-verified。
- 驗證需求：FR-007、NFR-003。

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001、BG-004 | 有 current disposition、owner、next action、due date 的 BUG record ÷ current BUG record | 目前 16 項有盤點但缺統一處置欄位 | 100% | 每次 status review；16 項 verification／status artifacts |
| KPI-002 | BG-002 | fixed-verified record 中完整原始症狀、回歸、full、review evidence 齊全者 ÷ fixed-verified record | 目前 0 項 fixed-verified | 100% | 每次結案 Gate；verification validator 與 review bundle |
| KPI-003 | BG-005 | 正式超標樣本可由 index、stdout、stderr、環境 identity 重算者 ÷ 正式超標樣本 | 目前已保留至少一筆 BDD-016 超標樣本 | 100% | 每次效能報告；validation evidence |
| KPI-004 | BG-003 | 有獨立 BUG context／record 的 BUG ÷ 多 BUG work 中的 BUG | 目前多 BUG handoff 缺 bug_context | 100% | 每次多 BUG plan／verification Gate |
| KPI-005 | BG-004 | 於期限前完成分類、升級或明確 disposition 的阻塞項 ÷ 到期阻塞項 | 目前無統一 SLA | 100% | 每週追蹤；delivery ledger／status report |
| KPI-006 | BG-005 | 歷史 assessment／Outcome／failure evidence 未被政策套用修改者 ÷ 套用政策前歷史 artifacts | 既有歷史需保留 | 100% | 每次 policy revision；hash comparison |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | BR-001、FR-001、FR-002、FR-003 | AC-001、AC-002、AC-003 | KPI-001、KPI-002 |
| BG-002 | J-001 | BR-002、FR-010、NFR-001、NFR-007 | AC-001、AC-003 | KPI-002 |
| BG-003 | J-001 | FR-005、FR-007、FR-011、NFR-003 | AC-005、AC-010 | KPI-004 |
| BG-004 | J-001 | FR-004、FR-006、FR-010、NFR-004 | AC-004、AC-006、AC-008 | KPI-001、KPI-005 |
| BG-005 | J-001 | FR-008、FR-009、TR-001、NFR-002、NFR-005、NFR-006 | AC-007、AC-009 | KPI-003、KPI-006 |

## 9. 已確認決策、假設與依賴

### 已確認決策

- D-001：保留既有 verified-fix、Human Gate、跨平台與 fail-closed 門檻；使用者已同意重新制定可行處置規則。
- D-002：以 verification result 與 disposition 兩層模型區分產品結論與流程阻塞。
- D-003：多 BUG 工作採共同 scope 加逐 BUG record；任何 BUG 不因同 scope 其他項目通過而自動結案。
- D-004：政策套用只新增 revision／transition／status evidence，不回寫歷史 assessment、Outcome、Ready handoff 或失敗 raw output。
- D-005：T0+1、T0+3、T0+5、T0+10 工作日為預設追蹤時限；若組織已有更嚴格 SLA，應以後續核准 policy revision 取代。

### 已確認假設

- A-001：本成果是治理與 evidence contract 變更；實際欄位名稱、檔案位置、validator 介面與 migration 方式留給 Technical Planning 決定。
- A-002：目前 16 項盤點可作為初始 status review input，但不等於 16 項都仍存在或已修復。
- A-003：Critical／High 的 accepted-risk 需要至少 Product／Risk owner 與 Engineering／Delivery owner 的明確核准。
- A-004：若無適格 independent reviewer，系統保持 pending／blocked；不以自動測試取代獨立人工核對。

### 依賴與外部限制

- DEP-001：既有 bug-verification/v1、bug-assessment/v1、Delivery ledger、Human Gate 與 project-knowledge validators。
- DEP-002：Windows 與 Linux 測試能力、固定效能 fixture、Git filesystem 行為與可保存 raw evidence 的執行環境。
- DEP-003：可識別且與 implementation owner 不同的 independent reviewer。
- DEP-004：Work ID、assessment revision、evidence hash 與 repository append-only 儲存能力。

### 延後至技術規劃的決策

- TP-001：選擇以單一 batch schema 或逐 BUG child handoff 實作多 BUG context；必須滿足 FR-007 與 AC-005。
- TP-002：決定 disposition 的持久化檔案、schema revision、validator 與舊資料讀取策略；不得破壞 bug-verification/v1。
- TP-003：將 timebox、escalation、accepted-risk approval 與 status report 接入既有 Delivery ledger 的最小方式。
- TP-004：以何種固定 runner、環境 identity 與 evidence bundle 驗證性能 outlier disposition；不得刪除超標樣本。
- TP-005：定義 Policy v2 canonical knowledge page、review bundle 與後續 Requirements／Planning／Implementation Gate 的 exact path。

## 10. 完整性與開放事項

- 阻塞性開放事項：無；本文件目前是待 exact review bundle 核准的 Candidate，核准後才可成為 Ready Requirements。
- 品質門檻：已涵蓋問題、角色、範圍、旅程、功能需求、品質屬性、邊界／失敗／復原、相容性、驗收、指標與追溯；無法在本階段決定的 HOW 已移至 TP-*。
- 歷史限制：本 Candidate 不修改既有 remediation work 的 handoff、assessment、Outcome 或 validation evidence。
- 本文件目前不可作為無條件的技術規劃基準，直到 exact Candidate／review identity 經使用者核准並依 delivery protocol 寫入。

