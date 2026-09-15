# v2 任務分級與核准契約

本文件描述可攜式 `sdlc` workflow 的任務分級與核准邊界。它補充
[階段路由契約](stage-routing.md)，不改寫既有 `delivery-run/v1` record；沒有
`delivery-run/v2` state 的工作仍依 v1 owner contract 執行。

## 1. 先分類，再建立交付狀態

`sdlc start` 或 Delivery Orchestrator 先對請求做唯讀探索與分類。分類只依影響
範圍與不確定性，不依修改行數。分類結果、理由、輸入 digest 與建議流程要寫入
v2 state，供 `doctor`、`status` 與 `resume` 重算；分類前不建立產品 worktree、
branch 或 repository artifact。

| `task_class` | 判定 | 流程與寫入邊界 |
|---|---|---|
| `read_only` | 解說、評估、診斷或審查，不要求改變產品 | 只查證與回報；不建立 delivery run、worktree 或 branch |
| `small` | 既有流程內的單一明確成果；驗收可直接表達；沒有跨模組契約、資料遷移、權限、依賴或架構變更 | 保存一份精簡 design brief；一次 integrated human approval 後才建立 worktree 並執行 |
| `large` | 新子系統、架構／介面／資料契約、依賴、權限或跨模組行為變更，或無法證明符合 `small` | Requirements gate 與 Planning gate 分開；第二次核准後才建立 worktree 並自動進 Implementation |
| `bug` | 使用者描述的是既有行為的疑似錯誤 | 先走唯讀 bug diagnosis；只有 `confirmed`／`likely` 才依修復影響升級為 `small` 或 `large` bug run |

純格式及微小文字修改可沿用既有直接處理例外，但一旦改變產品行為或契約，
必須重新分類。`not-a-bug` 若代表期望行為改變，回到 `small`／`large` 的需求流程。

分類不確定或證據不足時，選擇較嚴謹的 class；不要藉由改寫分類繞過 gate。
若實作中發現跨模組影響、資料／權限／依賴變更或範圍擴張，保存目前進度，將
`small` 升級為 `large`，回到需求與計畫核准；原先的 approval 不涵蓋新增範圍。

## 2. Gate policy

v2 state 保存 `task_class` 與與它相符的 `approval_policy`。使用者核准的是目前
唯一的 design／requirements／plan bundle、驗收、允許修改範圍、test commands、
knowledge scope 與 Git finish destination；state 以 digest 綁定該 payload，
不要求使用者手動複製雜湊值。

- `read_only`：沒有 approval，也沒有 mutation。
- `small`：一份短 design brief 同時包含目標、in/out、驗收、修改位置、步驟、
  測試、knowledge scope 與 finish destination；一次 integrated approval 即授權
  scoped implementation、review、knowledge review 與 finish handoff。
- `large`：Requirements approval 只核准 WHAT；Planning approval 核准 HOW、
  work packages、commands、knowledge scope 與 finish destination。第二次 gate
  通過後自動 dispatch Implementation，不再詢問額外的「是否開始實作」。
- `bug`：diagnosis 是先決的 read-only evidence；修復仍必須有對應的 design／
  requirements／plan approval，且保留 BUG verification 語意。

Approval 失效的情況包括 payload／source／驗收 drift、跨 Work ID、越界寫入、
新增發布目的地或改變 knowledge scope。此時 state 進入 `awaiting_approval` 或
`blocked`，不得以「繼續」或舊 approval 推斷授權。

## 3. v2 lifecycle

可攜式 plugin 的 `init` 只建立專案設定與 ignore-safe state binding；它不自動
初始化其他 repository。v2 `start`、`resume`、`status`、`doctor` 的 runtime
state 位於使用者狀態區，依 repository identity 與 Work ID 隔離；產品 repository
只保存核准後的需求／計畫、Outcome 與必要的知識變更。

核准前的探索與候選 bundle 可以保存於該狀態區，但必須是唯讀／create-only，
不能成為產品或 Git diff。核准後才建立 Work ID 專用 worktree 與 branch，並以
state 的 exact identity 執行後續命令。

每次狀態回報至少包含：`work_id`、`task_class`、phase／status、已完成工作、
目前 writer／reviewer、下一個 action、knowledge state、publication state 及
state path。中斷後 `resume` 從第一個未完成 action 繼續，不重派已完成工作。

## 4. Legacy compatibility

`delivery-run/v1` 的五階段 legacy path、兩次人工 gate、repository-local host-temp
registry、主代理 writer 規則，以及「不 stage／commit／push／merge／deploy／cleanup」
的行為全部保持原義。v2 state 不會自動轉換 v1 record，也不會把 v1 的核准解讀成
v2 的概括授權；執行中的 v1 工作完成或明確續跑後，新的需求才可另開 v2 Work ID。
