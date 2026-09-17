# 需求分析：跨世代 Delivery 修訂版配置的本地完成範圍

- 文件狀態：Candidate—Awaiting confirmation（本 revision 尚待 Requirements Gate 核准；核准前不生效）
- 日期：2026-09-17
- 文件範圍：修正 repository-local Delivery v1 在 generation 重建後配置下一個 Requirements／Plan 修訂版時的錯誤拒絕，並確認本 Work 以本地環境完成驗證即可交付。
- 需求來源：使用者授權的獨立 bug 修復、已確認的 BUG assessment、現有 Delivery v1 記錄與核准契約。
- 確認者：使用者（本地端執行即可；本 revision 待精確 Candidate 核准）

## 1. 執行摘要

### 問題或機會

Delivery 已記錄 plan revision 2 後，新 generation 只 materialize 目前核准的 upstream，較早的未登錄 plan/ 路徑因此缺席。有效 plan-3 transition 卻回報 INVALID_REVISION 並要求不存在的 plan/，使目前核准中的工作無法進入下一階段。[BUG assessment](../../../docs/bugs/bug-delivery-plan-revision-gap/assessment-1.md)（Markdown SHA-256：1b41d452c40b5532f5a2b5d2cc16f23dd4c04beed9a190f9f7826996a9c234a6；JSON SHA-256：050416643def2603de0c1b4e051446d2179f5ee2f6dc2680fe712fdfebe34118）。

### 為何現在做

這個可重現錯誤已阻擋一項核准中的工作，發生在產品程式碼變更之前。修正須保留遞增 revision、hash、Approval、Knowledge 與 transition 驗證。

### 預期成果

- BG-001：每個 Work ID 都能接受第一個高於已記錄最高核准版的有效 Requirements 或 Plan revision，即使目前 generation 未 materialize 更舊的歷史路徑。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Delivery 維護者／Agent | 依核准範圍準備 revision Candidate 及證據 | 只在目前 Work ID 與核准 scope 操作 |
| ACT-002 | 使用者 | 核准 Requirements 與技術 Plan | 核准只涵蓋精確版本；不得由「繼續」推定 |
| ACT-003 | Delivery transition | 驗證 Candidate 後追加狀態 | 不得略過驗證或覆寫歷史記錄 |

## 3. 範圍與優先順序

### 範圍內
- delivery-run/v1 中 Requirements 與 Plan 的 revision 驗證及跨 generation 續跑。
- 已記錄最高版、generation 缺席的較舊路徑、最高版之後的占用或缺席路徑。
- 保留 BUG、Approval、Knowledge receipt、hash 與 append-only history。

### 範圍外
- Hosted CI、Linux matrix 與跨平台 release evidence；它們可在發布後補做，但不屬於本地完成條件。
- Portable delivery-run/v2 plugin state。
- 修改既有 record／approval、migration、branch/worktree cleanup、push、PR、merge 或部署。
- 修改被阻擋 feature 的需求或預先核准它的新 Plan；修復後另行重新基線與核准。

### 非目標
- 不把本地結果宣稱為 hosted 或跨平台結果。
- 不補寫 generation 缺少的歷史 artifact。
- 不允許 revision 倒退、重用已核准版或放寬其他 transition 條件。

### 優先順序
Must：接受正常遞增的下一版，保留拒絕時零部分狀態變更及所有既有核准邊界。

## 4. 使用者與業務旅程

### J-001 — 從新 generation 接續核准中的工作
- 主要角色：ACT-001；ACT-002 核准內容；ACT-003 驗證 transition。
- 觸發與前置條件：Work ID 有 Ready revision N；新 generation 只物化目前核准 upstream；候選版高於 N。
- 主要流程：準備 N 後最小可用版；完成原有 artifact、hash、BUG、Knowledge 與 Approval 檢查；追加新 revision。
- 替代、例外與復原：低於或等於最高核准版則拒絕；候選版之前若缺少一個高於 N 的未占用路徑則拒絕並指出它；已占用中間路徑保留且不覆寫。
- 完成結果：有效新 revision 成為 current ref；本地完整驗證通過即可完成本 Work；失敗時 record、current ref 及既有路徑 bytes 不變。
- 相關需求：FR-001–FR-004、NFR-001、TR-001；驗收：AC-001–AC-007。

## 5. 需求

### 術語
- 最高核准 revision：同 Work ID Delivery record 中，數值最高且記錄為 Ready、具有 approval evidence 的 revision。
- 歷史缺席路徑：數值低於最高核准 revision，因 generation 只 materialize current upstream 而不存在的路徑。
- 占用路徑：目前 worktree 中已存在的 revision 路徑；新 Candidate 不得覆寫既有 bytes。

### FR-001 — 忽略最高核准版之前缺席的歷史路徑
- 需求：Delivery 必須接受高於最高核准 revision 的有效 Candidate，不得因低於該版的未登錄歷史路徑在目前 generation 缺席而拒絕。
- 理由與來源：[BUG assessment](../../../docs/bugs/bug-delivery-plan-revision-gap/assessment-1.md)；[revision transition 驗證](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1658)。
- 優先順序：Must。驗收：AC-001、AC-002。
FR-001: 新 Requirements 或 Plan 修訂版必須大於 Delivery run 已記錄的最高修訂版；低於該值的未登錄路徑即使在目前世代缺席，也不得阻擋它。

### FR-002 — Requirements 與 Plan 採一致規則
- 需求：Requirements 與 Plan 必須以相同的已記錄最高版為遞增邊界；沒有既有 history 時，既有首版路徑仍可用。
- 理由與來源：[Requirements history](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1337)、[Plan history](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1380)。
- 優先順序：Must。驗收：AC-002、AC-006。

### FR-003 — 保留最高核准版之後的 collision 防護
- 需求：若 Candidate 跳過高於最高核准版、未占用且缺席的中間路徑，Delivery 必須拒絕並指出第一個可用版；已存在中間路徑須視為占用且保持原 bytes。
- 理由與來源：[目前 revision 規則](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1658-L1675)。
- 優先順序：Must。驗收：AC-003、AC-004。

### FR-004 — 維持 revision 不倒退且不重用
- 需求：Delivery 必須拒絕低於最高核准版或重用已核准路徑的 Candidate。
- 理由與來源：[Requirements invariant](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1337)、[Plan invariant](../../../.agents/skills/delivery-orchestrator/scripts/_delivery_record.py#L1380)。
- 優先順序：Must。驗收：AC-005。

### NFR-002 — 本地驗證是完成門檻
- NFR-002：本地端完整驗證通過即可完成本 Work；hosted CI 與其他平台驗證屬可選發布後檢查，不是本地完成條件。
- 需求：在本地 target environment 執行完整 regression、related、build、test 與 governance commands 全部通過時，Delivery 可完成本 Work；hosted CI 與其他平台執行屬可選的發布後檢查，不得阻擋本地完成。
- 理由與來源：使用者明確確認只需要本地端執行；既有 validation-plan 將 local 與 release obligations 分開。
- 優先順序：Must。驗收：AC-008。

### NFR-001 — 拒絕操作保持原子性
- 需求：revision 無效時，record event count、current ref、Candidate bytes 及占用路徑 bytes 必須維持不變。
- 理由與來源：[append-only Delivery 契約](../../../.agents/skills/delivery-orchestrator/references/workspace-and-run.md#L57)。
- 優先順序：Must。驗收：AC-003、AC-005、AC-007。

### TR-001 — 相容既有 v1 工作與核准
- 需求：保留 delivery-run/v1 schema、既有 revisions、human-gate／Knowledge gate 次數與驗證順序；不得遷移既有 record。
- 理由與來源：[v1 相容契約](../../../.agents/skills/delivery-orchestrator/references/v2-task-routing.md#L83)、[既有 phase authorization 與歷史相容知識](../../../docs/work/work-20260903-unified-skill-entry-198002a2/implementation/outcome-3.md#L7)。
- 優先順序：Must。驗收：AC-001–AC-007。

### FR-005 — 治理知識可追溯
- 需求：本 Requirements Gate 必須把 revision 規則以 evidence_class required 加入 Project Knowledge；Knowledge postimages、index、promotion receipt、Requirements 與 BUG assessment 必須由同一精確 approval 綁定。
- 理由與來源：[檔案優先的人類核准 Gate](../../../docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/requirements.md#L105)。
- 優先順序：Must。驗收：AC-007。

## 6. 驗收情境

### AC-001 — Plan 首個遞增版不受缺席的歷史 plan/ 阻擋
- Given：record 已核准 plan revision 2；新 generation 沒有未登錄 plan/；plan-3 Candidate 與原有 approval、hash、BUG、Knowledge 條件有效。
- When：Delivery 執行 plan-3 核准 transition。
- Then：接受 revision 3，current Plan ref 指向 plan-3，record 只追加新 revision。
- 驗證需求：FR-001、FR-003、FR-004、TR-001。

### AC-002 — Requirements 首個遞增版不受缺席的歷史 requirements.md 阻擋
- Given：record 已核准 Requirements revision 2；新 generation 沒有未登錄 requirements.md；requirements-3 Candidate 與原有 gate 條件有效。
- When：Delivery 執行 requirements-3 核准 transition。
- Then：接受 revision 3，current Requirements ref 指向 requirements-3.md，record 只追加新 revision。
- 驗證需求：FR-001、FR-002、FR-003、TR-001。

### AC-003 — 不得跨越高於最高版的缺席路徑
- Given：最高核准 Plan revision 為 2；plan-3 未記錄且未占用；Candidate 放在 plan-4。
- When：Delivery 驗證 plan-4 transition。
- Then：以既有 INVALID_REVISION 類別拒絕並指出 plan-3；record 與 worktree bytes 不變。
- 驗證需求：FR-003、NFR-001–NFR-002、TR-001。

### AC-004 — 已占用中間 revision 保留且不覆寫
- Given：最高核准版為 2；未記錄的 plan-3 目錄已存在；plan-4 Candidate 及其他驗證有效。
- When：Delivery 驗證 plan-4 transition。
- Then：可追加 revision 4，plan-3 bytes 不變，history 仍嚴格遞增。
- 驗證需求：FR-003、NFR-001。

### AC-005 — 舊版或已核准 revision 不得重用
- Given：最高核准 revision 為 2。
- When：嘗試核准 revision 1 或再核准 revision 2。
- Then：拒絕且不新增 event；current ref 和既有 bytes 不變。
- 驗證需求：FR-004、NFR-001、TR-001。

### AC-006 — 首次 revision 保持相容
- Given：該 Work ID 沒有 Requirements／Plan history。
- When：提供原有首版路徑與有效 approval。
- Then：仍接受 requirements.md／plan/handoff.json，不改既有命名。
- 驗證需求：FR-002、TR-001。

### AC-008 — 本地驗證可完成 Work
- Given：本地 target environment 可用，regression、related、build、test 與 governance commands 均已執行且通過，hosted CI 沒有可用 run。
- When：Delivery 準備本 Work 的 implementation completion。
- Then：本地證據可作為完成判定；不要求 hosted CI 或 Linux evidence，且回報中明列它們未執行。
- 驗證需求：NFR-002、TR-001。

### AC-007 — Requirements gate 一次綁定完整材料
- Given：Candidate 包含 Ready Requirements、同 Work ID BUG assessment Markdown／JSON、required Knowledge claim／sidecar／index 與 promotion receipt。
- When：使用者核准精確 Candidate，Delivery 重驗 bytes 並執行原有 Requirements transition。
- Then：所有 postimages 綁定同一 approval evidence；create-only collision、hash drift 或 lint failure 時整組不套用，且不增加 Knowledge 核准問題。
- 驗證需求：FR-005、NFR-001、TR-001。

## 7. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 量測期間／資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | 本地 target environment 上，AC-001、002、004、006、008 成功；AC-003、005、007 仍 fail-closed | AC-001 目前 0 通過 | 100% | 本 Work 完整驗證期間；隔離 fixtures、Delivery transition tests、local reports |

## 8. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | FR-001–FR-004、NFR-001–NFR-002、TR-001 | AC-001–AC-006、AC-008 | KPI-001 |
| BG-001 | J-001 | FR-005 | AC-007 | KPI-001 |

## 9. 已確認決策、假設與依賴

### 已確認決策
- D-001：只修正已證實的 revision allocation 行為，保留 v1 schema、phase gates 與其他驗證。
- D-002：revision history 的排序權威為已持久化 Delivery record；新 generation 缺席舊路徑不撤銷 history。
- D-003：本次 Required Knowledge claim 與 Requirements 由同一 promotion Candidate co-promote，不新增人工核准問題。
- D-004：本 Work 不預設 push、PR、merge 或部署；Git 動作仍受既有授權。
- D-005：使用者確認本地端執行即可完成；hosted CI 與其他平台檢查列為可選發布後 follow-up，不作為本 Work 的必要 gate。

### 已確認假設
- A-001：generation materialization 省略較舊 superseded 路徑是既有行為。
- A-002：已存在但未記錄的 revision path 視為占用，以免覆寫 bytes。
- A-003：assessment 記錄 medium severity，沒有 security/privacy/data risk，亦無使用者資料影響。

### 依賴與外部限制
- DEP-001：Requirements／Plan 仍須通過各自 validator、approval evidence、hash、BUG binding 與 Knowledge receipt。
- DEP-002：regression、fresh review、local validation commands 由 Planning 依 repository tests 確定；hosted CI 與跨平台檢查僅在另有發布需求時執行。

### 延後至技術規劃的決策
- TP-001：共用 revision seam、high-water 計算、fixture、test commands、work packages 與 OS CI matrix。
- TP-002：是否需要更明確的 diagnostic message。

## 10. 完整性與開放事項

| Coverage 面向 | 狀態 | 證據或處置 |
|---|---|---|
| 目的、價值、時效、成果 | 已確認 | BG-001 與 assessment |
| 利害關係人、角色、權限 | 已確認 | ACT-001–ACT-003 |
| 範圍、優先順序、發布邊界 | 已確認 | 第 3 節與 D-004 |
| 現況、目標與替代旅程 | 已確認 | J-001 與 AC-001–AC-007 |
| 功能、規則、存取與狀態轉換 | 已確認 | FR、TR 與既有 Gate |
| 資料、實體、生命週期 | 不適用 | 不新增業務資料；只沿用 Work ID、record path、hash |
| 外部整合、上下游、失敗 | 不適用／已涵蓋 | 無新外部系統；transition failure 見 NFR-001 |
| 體驗、無障礙、在地化、人工介入 | 已確認 | 保持原有 human gate；錯誤指出第一個可用 revision |
| 品質屬性 | 已確認 | NFR-001、NFR-002 與 local KPI |
| 邊界、錯誤、重試、復原 | 已確認 | AC-003–AC-005 |
| 限制、依賴、相容、過渡 | 已確認 | TR-001；不做 migration |
| 風險、政策、必要人工審查 | 已確認 | medium; no security/privacy/data risk; existing Gates remain |
| 驗收、成功指標、追溯 | 已確認 | AC-001–AC-007、KPI-001、追溯矩陣 |

- 阻塞性開放事項：無。
- 品質門檻：單一義務、可判定 Given／When／Then、端到端旅程、失敗復原、相容及追溯均通過；來源包括本 BUG assessment、Delivery contract/code 與已重讀的 canonical Project Knowledge raw sources。Ready 僅於本 Candidate 的精確 approval 成功後生效。

### BUG diagnosis context

- bug_id：bug-delivery-plan-revision-gap
- 關係調整：原始診斷在 feature Work 中分類為 affecting-current-work／upstream-reapproval；本次另開的 primary bug Work 以 intake／delivery 提交同一確認症狀，原始 diagnosis evidence refs 保持不變。
- Assessment：docs/bugs/bug-delivery-plan-revision-gap/assessment-2.md（SHA-256 bba69d63908f71a3b84e55dde5fe8116f95bf030afa0a71b5010c327cd8d9af7）；docs/bugs/bug-delivery-plan-revision-gap/assessment-2.json（SHA-256 3d53b636309f0b4283ae92f6f292fec5d90449d98dd79b134f5511de0eb5080e）
- Verdict／severity／relation／disposition：confirmed／medium／intake／delivery
- Reproduction／root cause：reproduced／confirmed-high
- Observed／expected：revision 2 後較舊 plan/ 缺席使有效 plan-3 遭 INVALID_REVISION；第一個高於最高核准版的有效 revision 必須可繼續。
- Impact：原 feature 在產品碼變更前受阻；無已部署產品或使用者資料受影響。
