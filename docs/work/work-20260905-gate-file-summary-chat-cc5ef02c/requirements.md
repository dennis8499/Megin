# 需求分析：人工核准 Gate 的 File-first + Summary-only Chat

- 文件狀態：Ready
- 日期：2026-09-05
- 文件範圍：統一 repository 內所有需在 Chat 取得人類核准的 Gate；自動 validation、review、test 與 CI Gate 不變
- 需求來源：使用者 2026-09-05 的要求及範圍確認；現行 Requirements、Planning、Delivery、Knowledge、BUG 與 Implementation 契約
- 確認者：user；approval evidence `conversation:requirements-work-20260905-gate-file-summary-chat-cc5ef02c-candidate-1`

## 1. 執行摘要

### 問題或機會

目前 Requirements 與 Planning 要求核准前不寫正式檔案，卻把完整 Candidate bytes 放進 Chat；Knowledge Gate 也要求在 Chat 展示全部 postimages。Payload 變大時，審閱受到聊天長度、截斷與逐檔閱讀困難影響，摘要、檔案與 exact approval binding 分散在不同介面（`.agents/skills/requirements-discovery/references/delivery-protocol.md:20-34`、`.agents/skills/technical-planning/references/delivery-protocol.md:24-42`、`.agents/skills/project-knowledge/SKILL.md:38-52`）。

### 為何現在做

Governed mutation 已具有 Work ID、phase、digest、approval evidence、create-only 與 append-only transition，可將完整審閱面移到檔案而不弱化可追溯性。

### 預期成果

- BG-001：Maintainer 在每個人工核准 Gate 都先從穩定檔案審閱完整 payload，再於精簡 Chat 核准 exact Candidate，同時保留現行安全與自動 Gate 保證。

## 2. 利害關係人與角色

| 角色 ID | 角色 | 需求／責任 | 決策或權限邊界 |
|---|---|---|---|
| ACT-001 | Maintainer／核准者 | 從檔案審閱完整 Candidate並於 Chat 決策 | 只核准 Chat 指向的 exact revision、digest 與 manifest |
| ACT-002 | Gate producer | 先產生、驗證並連結完整 review bundle | 核准前不得形成 Ready／canonical 狀態或推進 phase |
| ACT-003 | Delivery／stage owner | 重驗 approval binding並執行 promotion | 只有合法核准後才可 Ready、apply 或 transition |
| ACT-004 | 自動 Gate consumer | 保留 machine-readable evidence 與判定 | 不以 Chat 摘要取代原始輸出 |

## 3. 範圍與優先順序

### 範圍內

- Requirements Candidate，含 BUG assessment 與 requirements knowledge co-gate。
- Plan Candidate，含 handoff、supporting artifacts、knowledge co-gate 與 bulk-edit `occurrence_map`。
- Implementation 後 Knowledge promotion。
- Project Knowledge candidate、bootstrap、repair、apply 等人類核准流程。
- 上述 Gate 的 revision、collision、drift、resume 與 pending legacy Candidate。
- Chat 摘要、直接檔案連結、identity 與核准提示。

### 範圍外

- 自動 validation、fresh review、test、performance、security、lint、schema 與 CI Gate。
- 一般訪談／技術決策問題、進度更新及純唯讀診斷。
- 重寫歷史 Ready artifacts、既有 approval evidence、Complete records 或 canonical knowledge。
- commit、push、merge、deploy、ticket、通知或 cleanup。

### 非目標

- 摘要不取代完整 payload；它只導向完整檔案。
- Candidate 檔案不因此成為 Ready、已套用或已核准。
- 不偵測使用者是否實際開啟或逐 byte 閱讀檔案。
- 不新增人工 Gate。

### 優先順序

Must 順序為完整 payload 可取得、approval exact binding、核准前零正式副作用、Summary-only Chat、相容與恢復。不得弱化 secret redaction、create-only、no-follow、hash、lint 或 phase authorization。

## 4. 詞彙

- TERM-001 — Human approval Gate：等待人類明確核准後才能 Ready、promotion、apply 或 transition 的邊界。
- TERM-002 — Review bundle：詢問核准前持久化的完整、不可變、可直接開啟之 Candidate artifacts、diff／postimages、manifest、validation 與 identity。
- TERM-003 — File-first：Chat 出現核准提示前，Review bundle 已完整存在且可讀。
- TERM-004 — Summary-only Chat：Chat 只含規定摘要、直接連結、exact identity 與單一核准提示，不內嵌完整 artifact、diff、postimages 或 raw output。
- TERM-005 — Ready artifact：人工核准後才形成或晉升的正式產物，與 unapproved review bundle 不可混同。

## 5. 使用者旅程

### J-001 — File-first 核准

- 主要角色：ACT-001、ACT-002、ACT-003
- 觸發與前置條件：Stage 品質通過，或 Knowledge 已封存 Candidate。
- 主要流程：Producer 先持久化並驗證 review bundle；Chat 回報摘要、風險、validation、連結及 exact identity；使用者核准；owner 重驗 bytes 後才 promotion／Ready／apply／transition。
- 替代、例外與復原：要求修改時建立新 revision；遺失、不可讀、collision 或 drift 時拒絕舊核准並重建。
- 完成結果：正式狀態只對可取得且 digest 綁定的完整檔案版本前進。
- 相關需求：BR-001、FR-002、FR-003、FR-004、FR-005、FR-006、FR-008
- 驗收情境：AC-001、AC-002、AC-003、AC-005、AC-006

### J-002 — 複合 Gate

- 主要角色：ACT-001、ACT-002、ACT-004
- 觸發與前置條件：Gate 同時包含 Requirements／Plan、Knowledge、BUG assessment或 occurrence map。
- 主要流程：全部共同核准項目進同一 bundle 與 manifest；Chat 只問一次；自動 Gate 的完整 machine output 留在 evidence files。
- 替代、例外與復原：任一必要檔案或 validation 缺失時整組 fail closed。
- 完成結果：共同 approval evidence 範圍完整，沒有隱藏 payload 或額外 Gate。
- 相關需求：FR-001、FR-007、NFR-003
- 驗收情境：AC-004、AC-008

### J-003 — 相容續接

- 主要角色：ACT-001、ACT-003
- 觸發與前置條件：存在歷史 Ready，或尚未核准的 chat-only Candidate。
- 主要流程：歷史 Ready 保持有效；pending Candidate 產生新 file-first revision後重新等待核准。
- 替代、例外與復原：無法重建 exact Candidate時維持 Blocked。
- 完成結果：不重寫歷史，未來每次核准均有 review files。
- 相關需求：TR-001、TR-002
- 驗收情境：AC-007

## 6. 需求

### BR-001 — 統一人工 Gate 審閱模式

- 需求：所有需要人類在 Chat 核准的 Gate，都必須先將完整且不可變的審閱 payload 持久化為可直接開啟的檔案，再於 Chat 僅提供摘要、檔案連結、精確 identity 與核准提示。
- 理由與來源：BG-001；使用者 2026-09-05 明確確認範圍；現行 Gate 分別要求完整 Chat 展示。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003、AC-004

### FR-001 — 完整 Gate inventory

- 需求：新模式必須涵蓋 Requirements、Plan、兩者的 Knowledge co-promotion、Implementation 後 Knowledge promotion、standalone Knowledge candidate／bootstrap／repair／apply、BUG assessment co-gate及 bulk-edit occurrence map；未來新增的人類核准 Gate 亦適用。
- 理由與來源：BR-001；BUG assessment 與 Requirements 共用 Gate（`.agents/skills/bug-diagnosis/SKILL.md:45-56`），Delivery 另有三種 awaiting-user transition（`.agents/skills/delivery-orchestrator/references/stage-routing.md:17-28`）。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003、AC-004

### FR-002 — 核准提示前完整落檔

- 需求：Producer 必須在 Chat 詢問核准前持久化完整 artifacts、diff／postimages、manifest、validation、revision、digest及全部共同核准項目，並驗證 Chat 連結所指 bytes 與宣告 identity 一致。
- 理由與來源：BR-001、J-001；使用者選擇 File-first。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003、AC-005

### FR-003 — Summary-only Chat

- 需求：人工 Gate 的 Chat 回覆必須只含 Gate 名稱與狀態、目的與變更摘要、重要風險／相容影響、validation 結果、review bundle 直接連結與 manifest、exact revision／digest，以及唯一核准或修改提示；不得內嵌完整 artifact、diff、postimages 或 raw command output。
- 理由與來源：BR-001、TERM-004；使用者已確認摘要、連結與核准提示。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003、AC-009

### FR-004 — Exact approval binding

- 需求：核准必須綁定 Gate、work／mission identity、Candidate revision、payload digest與完整 manifest；缺值、含糊回覆或舊 revision 不得 Ready、apply 或 transition。
- 理由與來源：J-001；Project Knowledge 已以 candidate ref、payload SHA與 approval evidence 綁定 exact payload（`.agents/skills/project-knowledge/SKILL.md:38-52`）。
- 優先順序：Must。
- 驗收：AC-005、AC-006

### FR-005 — 核准前零正式副作用

- 需求：Review bundle 必須標示 unapproved／Candidate；核准前不得建立或覆寫 Ready／canonical artifact、apply knowledge postimage、修改產品、推進 phase或執行其他外部 mutation。
- 理由與來源：TERM-005；保留現行 Gate 的安全意圖，同時允許隔離 review files。
- 優先順序：Must。
- 驗收：AC-001、AC-002、AC-003、AC-005

### FR-006 — Revision、collision 與 drift

- 需求：任一 review file、source、preimage、manifest或 digest 在詢問後改變、遺失、不可讀或 collision時，Gate 必須拒絕舊核准、保留既有 bytes並產生新 immutable revision後重新核准；不得覆寫或只用 Chat 補充。
- 理由與來源：J-001；現行 Requirements／Plan collision及 Knowledge drift皆 fail closed。
- 優先順序：Must。
- 驗收：AC-005、AC-006

### FR-007 — 複合 Gate 單次核准

- 需求：Requirements／Plan 與 Knowledge、BUG assessment或 occurrence map共用 approval evidence時，bundle與 Chat manifest必須列出全部檔案但只提出一次問題；不得把大型檔案移出 manifest、以摘要代替或新增第三道 Gate。
- 理由與來源：J-002；現行 overlays要求同一 Gate與 approval evidence。
- 優先順序：Must。
- 驗收：AC-004

### FR-008 — 不可取得時 fail closed

- 需求：任一 bundle檔案無法由 Chat 連結直接開啟、穩定讀取、缺少完整內容或未通過 validation時，Gate 必須保持原 phase並 Blocked／重建；不得退回完整 Chat 貼文作為核准面。
- 理由與來源：File-first 可用性是 approval 前置條件。
- 優先順序：Must。
- 驗收：AC-005、AC-006

### TR-001 — 歷史 Ready 相容

- 需求：已核准 Ready artifacts、canonical knowledge、approval evidence與 Complete records必須保持有效且不得為新展示模式重寫。
- 理由與來源：J-003；Delivery 的歷史與 append-only 相容要求。
- 優先順序：Must。
- 驗收：AC-007、AC-008

### TR-002 — Pending Candidate 過渡

- 需求：新模式生效時，尚未核准且沒有完整 review bundle的 chat-only Candidate必須建立新 file-first revision後才能核准；舊 pending Chat展示不得直接晉升。
- 理由與來源：J-003、FR-004。
- 優先順序：Must。
- 驗收：AC-007

### NFR-001 — 安全與秘密

- 需求：Bundle與 Chat摘要必須維持現有 secret redaction、sensitive refs、no-follow、path normalization、create-only、preimage、hash、duplicate-key與 least-authority規則；摘要不得洩漏只允許存在安全 evidence store的內容。
- 理由與來源：既有 Delivery、BUG與 Knowledge安全契約。
- 優先順序：Must。
- 驗收：AC-006、AC-009

### NFR-002 — 可驗證且不受 payload大小影響

- 需求：相同 Gate bytes與狀態必須產生 deterministic identity／manifest及等價摘要欄位；Summary-only必須能以 sentinel驗證，且大型 payload不得導致完整內容回退或必要連結省略。
- 理由與來源：BG-001；Summary-only 是契約而非文案偏好。
- 優先順序：Must。
- 驗收：AC-009

### NFR-003 — 自動 Gate 相容

- 需求：自動 validation、fresh review、test、performance、security、lint、schema與 CI Gate的 machine output、pass/fail、terminal ordering及 evidence retention必須維持；Chat摘要不得取代 machine evidence。
- 理由與來源：使用者 2026-09-05 明確排除自動 Gate。
- 優先順序：Must。
- 驗收：AC-008

## 7. 驗收情境

### AC-001 — Requirements Gate

- Given：Requirements品質通過且含 Knowledge overlay
- When：準備詢問核准
- Then：Requirements、knowledge diff／postimages、manifest、validation與 digest已存在 immutable review files；Chat只有摘要、連結、identity與一個問題；核准前無 Ready、apply或 planning transition
- 驗證需求：BR-001、FR-001、FR-002、FR-003、FR-005

### AC-002 — Plan Gate

- Given：Plan bundle、handoff、supporting artifacts、Knowledge overlay及 occurrence map已產生
- When：準備詢問核准
- Then：全部 bytes先進同一 review bundle與 manifest；Chat不含完整 bundle；核准前無 Ready plan或 Implementation transition
- 驗證需求：BR-001、FR-001、FR-002、FR-003、FR-005、FR-007

### AC-003 — Knowledge／Apply Gate

- Given：standalone或 implementation後 sealed Knowledge Candidate待核准
- When：進入 awaiting-user
- Then：完整 postimages、diff、paths、binding及 validation均可由 review files開啟；Chat只有摘要、連結、candidate ref／digest及一次提示；核准前無 apply／Complete
- 驗證需求：BR-001、FR-001、FR-002、FR-003、FR-005

### AC-004 — BUG與 bulk-edit內容

- Given：Requirements含 BUG assessment，或 Plan含 occurrence map
- When：建立 review bundle
- Then：assessment Markdown／JSON或 occurrence map全列入 manifest並可開啟；Chat只摘要 verdict／分類風險，不貼全文、不新增 Gate
- 驗證需求：FR-001、FR-007

### AC-005 — 核准與 promotion

- Given：使用者核准 exact revision、digest與 manifest
- When：owner嘗試 Ready／apply／transition
- Then：先重讀全部 review files；相同才執行既有 promotion、lint與 transition，否則保持原 phase
- 驗證需求：FR-002、FR-004、FR-005、FR-008

### AC-006 — 缺檔、collision、drift或含糊核准

- Given：任一 file缺失／不可讀／漂移／collision，或回覆未清楚核准 current identity
- When：Gate嘗試前進
- Then：零 Ready／apply／產品／phase mutation；保留舊 bytes，建立新 revision或 Blocked，Chat仍只回摘要
- 驗證需求：FR-004、FR-006、FR-008、NFR-001

### AC-007 — 歷史與 pending

- Given：歷史 Ready及 pending chat-only Candidate
- When：新模式生效
- Then：歷史 bytes與 approval不變；pending Candidate須先取得新 review bundle與 revision才能核准
- 驗證需求：TR-001、TR-002

### AC-008 — 自動 Gate不變

- Given：相同的 validation、review、test、performance、security、lint、schema與 CI fixtures
- When：執行完整 suite
- Then：machine schema、raw evidence、pass/fail與 ordering一致；只有人類 Chat presentation改變
- 驗證需求：TR-001、NFR-003

### AC-009 — Summary-only可測

- Given：每種人工 Gate payload含唯一 sentinel及大型 fixture
- When：產生 Chat回覆
- Then：必要摘要欄位與直接連結存在，而 sentinel全文、完整 diff／postimages及 raw outputs不在 Chat；payload大小不改變結果
- 驗證需求：FR-003、NFR-001、NFR-002

## 8. 成功指標

| 指標 ID | 對應成果 | 指標與計算方式 | 基準 | 目標 | 資料來源 |
|---|---|---|---|---|---|
| KPI-001 | BG-001 | 詢問前具完整 hash-valid bundle的人工 Gate cases ÷ 全部人工 Gate cases | Requirements／Plan核准前無正式檔 | 100% | owner／forward suite |
| KPI-002 | BG-001 | Chat未出現 sentinel全文或完整 payload的 cases ÷ 全部人工 Gate cases | 現行要求完整 Chat展示 | 100% | summary evaluator |
| KPI-003 | BG-001 | exact bundle重驗後正確 promotion的 cases ÷ approval cases | 既有各自綁定 | 100%，錯誤 promotion為0 | integration suite |
| KPI-004 | BG-001 | 既有自動 Gate regression pass數 ÷ 適用 cases | 現行 owner suites | 100% | full suite |

## 9. 追溯矩陣

| 業務成果 | 旅程 | 需求 | 驗收情境 | 成功指標 |
|---|---|---|---|---|
| BG-001 | J-001 | BR-001、FR-002..006、FR-008、NFR-001、NFR-002 | AC-001、AC-002、AC-003、AC-005、AC-006、AC-009 | KPI-001、KPI-002、KPI-003 |
| BG-001 | J-002 | FR-001、FR-007、NFR-003 | AC-004、AC-008 | KPI-001、KPI-004 |
| BG-001 | J-003 | TR-001、TR-002 | AC-007、AC-008 | KPI-003、KPI-004 |

## 10. 已確認決策、假設與依賴

### 已確認決策

- D-001：只改需在 Chat取得人類核准的 Gate；自動 validation／review／test／CI Gate不變。決策者：user，2026-09-05。
- D-002：Chat保留摘要、直接檔案連結、exact identity與核准提示；完整內容只在 review files。
- D-003：Requirements、Plan、Knowledge／Apply、bulk-edit map及與 Requirements共用核准的 BUG assessment皆適用。
- D-004：本次 self-hosting delivery在新契約生效前仍遵守現行 full-display Gate；完成後的新 Gate才採新模式。
- D-005：歷史 Ready不重寫；未核准 chat-only Candidate重新產生 file-first revision。

### 已確認假設

- A-001：Maintainer可存取 Chat直接連結的本機 review files；不可開啟時由 FR-008 fail closed。
- A-002：Summary-only禁止完整 payload，而不禁止必要風險、validation、manifest與 identity摘要；使用者回答「是」確認。

### 依賴與外部限制

- DEP-001：Delivery／Knowledge的 identity、phase authorization、candidate ref、payload SHA、approval evidence、create-only、lint與 transition維持安全邊界。
- DEP-002：Chat renderer須能直接連結本機檔案；不可用時不得降級貼全文。
- DEP-003：Review bundle與 Ready artifact須可區分，避免 Candidate被 consumer當作 baseline。

### 延後至技術規劃的決策

- TP-001：共用 review-bundle schema、路徑與 serializer。
- TP-002：worktree artifact root或 host-temp sealed store的穩定連結策略。
- TP-003：核准後形成 Ready artifacts的最小安全 promotion機制。
- TP-004：shared summary formatter／validator與 payload leakage防線。
- TP-005：pending legacy Candidate的偵測與 migration seam。

## 11. 完整性與開放事項

- 阻塞性開放事項：無。
- 品質門檻：13個覆蓋面均已分類；無新增高風險 domain。每項需求均有來源、正常／負向／復原／相容驗收與指標；純 HOW已移至 TP-001..005。需求品質契約通過。
