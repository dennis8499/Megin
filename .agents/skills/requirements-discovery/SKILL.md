---
name: requirements-discovery
description: 探索仍待釐清的產品或軟體需求：以證據先行、一次一題的 frontier 訪談收斂範圍、規則、風險與驗收，產出可進入技術規劃的可追溯需求分析。適用於需求梳理與規格前訪談；已有核准規格的純實作、知識解說與純故障診斷不適用。
---

<!-- authority: requirements-entrypoint -->

# 需求探索

以專案證據與人類決策把構想收斂為可驗收、可追溯的需求。`frontier` 是前置決策已解決、目前可請使用者決定的未知節點；每輪只處理價值最高的一項。

## 呼叫邊界

| 請求結果 | 路由 |
|---|---|
| 需求仍有範圍、規則、風險或驗收未知 | 呼叫本 Skill |
| 已有核准規格，只需實作 | 交給 Implementation |
| 疑似 BUG 的純故障診斷 | 先使用 `bug-diagnosis`；本 Skill 不猜根因或修法 |
| 知識解說 | 使用對應的一般工作流 |

完成條件：請求已唯一落在一列；進入探索時只產生事實證據、問題與候選文件，不開始產品實作。

## 探索不變量

- 分析只描述 WHY、WHAT、WHO、WHEN 與可觀察驗收；外部強制限制可成為需求，純 HOW 交給技術規劃。
- Bug run把已核准assessment視為唯讀diagnosis evidence；本文件仍是observed／expected、影響、範圍與驗收的唯一WHAT權威。
- 使用者回答只確認當輪決策。Candidate 展示、路徑確認與寫入授權由交付協定管理。
- 每份文件涵蓋一個可獨立規劃、驗收或發布的成果。
- 使用者主要語言用於訪談與成文；穩定識別碼保持 ASCII。

## 1. 查明可取得事實

先執行 read-only 知識 preflight：

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage requirements --query "<目前需求意圖>"`

保存 `knowledge-context/v1` 作為 evidence，並在引用前重讀每個 result 的 `source_refs`。這個步驟不寫回 Wiki 或產品；typed dependency／contract error 使 evidence gate 保持 Blocked。只有 Ready BOOT plan 明列 skill 尚不存在時可使用其 bootstrap exception。

在第一題前讀取適用治理、README、既有規格、詞彙、資料／介面、程式碼與近期變更。必要且獲准時查一手外部來源。可由 evidence 解決的事項直接記錄；需要人類決策、優先順序或不可存取資訊的事項才進 frontier。

完成條件：所有目前可取得、且可能改變範圍、行為、風險或驗收的事實都有來源；剩餘未知需要人類決策或明示缺失來源。

## 2. 建立覆蓋圖與決策樹

每個覆蓋面標成 `已確認`、`未知`、`矛盾` 或 `不適用`：

1. 問題、價值、為何現在做、預期成果
2. 利害關係人、使用者、系統角色與決策權
3. 範圍、非目標、優先順序與發布邊界
4. 現況流程、目標流程、主要與替代旅程
5. 功能行為、業務規則、權限與狀態轉換
6. 領域詞彙、資料、實體、所有權與生命週期
7. 外部整合、上下游、契約與失敗處理
8. 使用體驗、無障礙、在地化與人工介入
9. 效能、可用性、安全、隱私、稽核等品質屬性
10. 邊界條件、錯誤、重試、復原與降級
11. 限制、依賴、移轉、相容性與過渡需求
12. 風險、法規、政策與必要的人工作業審查
13. 驗收條件、成功指標、來源與追溯關係

`不適用`需要事實支持。所有適用未知與矛盾都建立前置關係；未確認預設仍是未知，純 HOW 標記給 Planning。

若第 12 面或其他 evidence 顯示法規、契約、安全、隱私、醫療、金融、兒少、身分或相當風險，立即完整讀取 [高風險契約](references/high-risk-contract.md)，把其未知加入圖後才選下一題。

完成條件：13 面都有狀態；每個未知都有前置關係；frontier 只含前置已解決的節點，或在沒有可決策節點時為空。

## 3. 一次詢問一項 frontier 決策

以 `影響程度 × 不確定性 × 不可逆性` 排序；同分依範圍／成果、法規／安全／隱私、驗收、角色／規則／資料、體驗、營運／外部限制排序。

問題包含一至兩句脈絡與影響；適合時提供二至四個互斥選項及後果，允許一句自訂答案。只有 evidence 支持時才推薦。回合以單一決策請求結束。

完成條件：本回合只有一個可回答的問題，且它是 frontier 中價值最高的節點。

## 4. 保存決策並重算

保存答案、決策者或來源。含糊／衝突答案留在 frontier；多義詞先確認定義；跨成果的新需求先決定納入、延後或另立文件。多個可獨立成果先提出最小拆分與依賴，再只問先探索哪一份。

完成條件：答案有來源，衍生未知與矛盾均已入圖，frontier 已依最新前置關係重算。未完成時回到步驟 3。

## 5. 執行二元品質判定

Frontier 與 downstream 未知均為空，且沒有矛盾或未定義關鍵詞時，完整讀取 [品質契約](references/quality-contract.md)。高風險分支同時重新讀取 [高風險契約](references/high-risk-contract.md)，合併所有適用檢查。

未通過項目轉回 `未知`／`矛盾`並回到 frontier；必要事實、決策者、一手來源或適格審查者不可得時進入 Blocked 交付分支。

完成條件：每個適用檢查都有二元結果與可核對 evidence；只有全數通過才進 Candidate 交付。

## 6. 交付目前狀態

當品質通過、使用者要求提前停止／目前成果／開始實作時，完整讀取 [交付協定](references/delivery-protocol.md)，只執行符合目前狀態的分支。只有需要產生文件時才載入 [文件模板](references/requirements-analysis-template.md)。

完成條件：狀態、完整展示、建議路徑、寫入與 handoff 全部符合交付協定；本 Skill 沒有產品程式碼寫入。

## 維護本 Skill

修改本 bundle 時完整讀取 [行為驗證契約](references/behavior-evaluation.md)，執行 owner validator、mutation tests、八個 forward cases與 fresh read-only review。報告只記錄實際執行結果。
