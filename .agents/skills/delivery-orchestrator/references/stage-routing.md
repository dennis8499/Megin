<!-- authority: delivery-routing -->

# 階段路由契約

本文件只把 child 的持久化狀態映射為 delivery transition；Candidate、Ready、BDD／TDD、review與品質規則仍由對應 child Skill唯一擁有。以下既有 phase table 描述 repository-local `delivery-run/v1`；portable `delivery-run/v2` 的 task class 與 gate policy 見 [v2 任務分級與核准契約](v2-task-routing.md)。

所有Chat人工核准邊界遵守 [共用 Human Gate contract](../../project-knowledge/references/human-gate-review.md)（canonical path：`.agents/skills/project-knowledge/references/human-gate-review.md`）。Human Gate bundle inventory: Requirements composite bundle, Plan composite bundle, and the post-Implementation Knowledge Candidate; each remains its existing single Gate.

## 先授權再 dispatch

每次進入 Requirements、Planning 或 Implementation 前，Orchestrator 都依 [階段授權](stage-authorization.md)對 current work ID 與 canonical worktree 呼叫 `authorize`。只有 exact `requirements/active`、`planning/active` 或 `implementation/active` 的 `outcome: authorized` 可 dispatch 對應 child；`routing_required`／typed error 先由 Orchestrator 建立、續接或修復 context，child 保持零寫入。

使用者直接點名 child 時也套用相同判定，不形成第二條 standalone mutation path。純解說、診斷、唯讀審查、plan-only、治理驗證、Project Knowledge 明示治理流程及隔離測試維持其唯讀／既有 Gate 例外；一旦要形成 Requirements／Plan／Implementation 階段成果，就回到本授權流程。

Requirements Ready 的人工 Gate 通過後自動 dispatch Planning；Plan Ready 的人工 Gate 通過後自動 dispatch Implementation，不再詢問額外的「是否開始實作」。Child 只回傳自身持久化結果，Delivery transition 仍由 Orchestrator 單獨持有。

## v2 task routing

v2 在任何 mutation 前先保存唯讀 classification：`read_only`、`small`、`large` 或
`bug`。`read_only` 只回報；`small` 以一份精簡 design brief 取得一次 integrated
approval；`large` 依序取得 Requirements 與 Planning approvals；`bug` 先完成
`confirmed`／`likely` diagnosis，再依影響進入 small 或 large。核准前不得建立
產品 workspace／branch；核准後才建立 v2 Work ID workspace。

v2 的 approval payload 同時綁定驗收、允許修改 paths、測試命令、knowledge scope、workspace mode
與 Git finish destination。小任務的同一份 approval 授權 scoped implementation、
fresh review、automatic knowledge review 與 finish handoff；大型變更只在第二次
Planning approval 後 dispatch Implementation。新增跨模組、資料、權限、依賴或架構
影響時，保存 progress 並升級至 large，要求受影響內容重新核准。

| v2 `task_class` | 可 dispatch 的 child | gate 與下一步 |
|---|---|---|
| `read_only` | query／diagnosis／review | 不建立 delivery run；回報 evidence |
| `small` | implementation → fresh review → knowledge review | 一次 integrated approval；通過後交給 `finish` |
| `large` | requirements → planning → implementation → fresh review → knowledge review | Requirements 與 Planning 各一次；第二次核准後自動 implementation |
| `bug` | diagnosis → small 或 large path | 保留 BUG verification；`failed` 不得完成 |

v2 Child 不直接執行 phase transition。Orchestrator 以 state 的 exact authorization
與 writer assignment dispatch，並在每次 child result 後原子保存 refs／state；缺少
授權、reviewer 或必要能力時保持零 mutation 並回報 `blocked`／`awaiting_user`。

| Current phase | Child 持久化結果 | Delivery transition |
|---|---|---|
| `workspace` | generation `ready` | `requirements/active` |
| `requirements` | Candidate完整review files已重驗，Summary-only Chat projection已呈現 | `requirements/awaiting_user` |
| `requirements` | 新 Ready revision 與 required knowledge promotion 已寫入且核准 | 同一次 transition保存 requirements path/hash、Ready receipt與相同approval refs，lint通過後進 `planning/active`；legacy無overlay維持原行為 |
| `planning` | Candidate bundle完整review files已重驗，Summary-only Chat projection已呈現 | `planning/awaiting_user` |
| `planning` | 新 Ready handoff 與 required knowledge promotion 已寫入且核准 | 同一次 transition保存 handoff/revision/payload、Ready receipt與相同approval refs，進 `implementation/active`；legacy無overlay維持原行為 |
| `planning` | 發現需求缺口 | 保存 gap refs，回 `requirements/active` |
| `implementation` | WP-local revision | 保存新 Ledger attempt，留在 `implementation/active` |
| `implementation` | `Awaiting upstream reapproval` | 保存 child refs，回 `planning/active` |
| `implementation` | global-baseline revision | 依 workspace-creation建立下一 generation |
| `implementation` | child `Complete` 且preliminary／final accepted product／knowledge review snapshots穩定 | Required overlay保存Ledger、latest create-only repo-side outcome revision、兩份不同review、Candidate與dual snapshots後進`knowledge/active`；legacy轉`complete/complete` |
| `knowledge` | reviewed Candidate完整files已重驗，Summary-only Chat projection已呈現 | `knowledge/awaiting_user`，不得先宣稱delivery Complete |
| `knowledge` | matching Ready promotion、approval與lint通過 | 重算product snapshot、保存receipt後進`complete/complete` |
| `knowledge` | 需要修改產品 bytes | 清除reviewed Candidate／snapshot／outcome binding，建立Active implementation attempt並回`implementation/active` |
| 任一 child | `Blocked` | phase不變，status轉 `blocked`並追加 blocker refs |

## Requirements overlay

Repository path 使用 `docs/work/<work_id>/requirements.md`；revision採最小可用 `requirements-N.md`。核准前沒有正式 artifact；重新核准必須建立新 revision。只有本次 transition新增或重新驗證 current Ready requirements才能進 planning。

完成條件：current requirements ref指向最新寫入、hash相同且具有非空 approval evidence的 Ready revision。

Bug run另要求同一approval transition create-only綁定schema-valid `bug-assessment/v1` JSON、其Markdown path/hash與primary `bug_id`；assessment verdict只接受`confirmed | likely`且disposition為delivery。缺assessment、hash drift、collision或秘密違規不得進Planning。Assessment仍只是evidence，Requirements維持WHAT權威。

## Planning overlay

Bundle root 使用 `docs/work/<work_id>/plan/`；revision採最小可用 `plan-N/`。Transition前以 producer validator重新讀取 current `handoff.json`，驗證 ready-plan/v1 schema、payload、contracts、commands、DAG、全部 hashes與恰好一個綁定 current requirements的 `kind: spec` source。Current Ready 引用的歷史 handoff 只重驗穩定 schema、原核准 evidence、payload與artifact hashes；不得把後來新增的 producer cross-reference 規則回溯套用到已核准歷史 revision。

這次 Ready approval是第二個人工 gate；transition成功後直接進 Implementation。

完成條件：current handoff ref與 producer-validated Ready bytes、current requirements及 delivery generation base一致。

Bug run的Ready handoff另必須含唯一`kind: bug` source與`bug_context`，其assessment JSON／Markdown bindings精確等於current approved assessment；verification target與partial safeguards由Planning producer驗證。

## Implementation overlay

首次 preflight只有在 delivery record、generation binding、current requirements與 handoff spec source全部相符時，才把 requirements視為額外唯讀 upstream input。Child Skill仍唯一擁有產品寫入、BDD／TDD、verification、fresh Reviewer、breaker及 terminal ordering。

完成條件：delivery implementation ref與host-temp `implementation-execution/runs/<run_id>/run.json`的binding、Ready revision及Complete attempt一致；terminal index內每個ref已保存。Latest Outcome使用`outcome.json`或最小連續`outcome-N.json`，通過完整execution schema／semantics，current run ID、Markdown、changed-file hashes、preliminary report logical ref／path／SHA與每個command raw output均由實體bytes重驗。Helper依final Reviewer authority重算當下`implementation-snapshot/v1`；final report必須是schema-valid `APPROVED` report，且其before／after完整object及ID同時等於持久化snapshot與當下重算值。Required overlay另外要求final report的knowledge before／after、Candidate ref／digest精確等於delivery gate；preliminary report不得含這些欄位，也不能兼任final report。Product snapshot只排除`docs/knowledge/**`，promotion後仍須重算相同。Legacy terminal Ledger transition與delivery event引用同一review及snapshot後可Complete；required record還必須通過knowledge approval。

Bug run另要求`bug-verification/v1` path/hash/result與current implementation run一致；legacy在同一次`complete/complete` transition綁定，required overlay在fresh-review的`implementation → knowledge/active` transition綁定並於promotion Complete重驗。其原始症狀、regression／proxy、full-command與review refs必須實際存在於該run的canonical evidence root並列入terminal index。Reviewer的`APPROVED`只核准implementation snapshot；verification result另為`verified | partial | failed`。`failed`不得Complete；`partial`只能在Ready target為partial且全部safeguards有evidence時共存，verification與review summary採fail-closed canonical wording，只有明示partial／原始症狀仍無法確認的固定句可通過，不能靠改寫繞過過度宣稱防線。

途中BUG依relation分流：`current-scope`保持`implementation/active`並納入Fixing／驗收；`affecting-current-work`要求child run為`Awaiting upstream reapproval`且原子回`planning/active`；`unrelated`保持目前implementation、不改產品，只寫create-only全域inbox。三類先追加pending host-temp refs，再以同ID／relation／refs追加materialized assessment；latest仍pending時不得fresh review terminal handoff或Complete。若含安全、隱私或資料風險，pending與materialized兩次事件都必須帶相同的sensitive flag、遮蔽摘要、安全evidence refs與具名人工reviewer，assessment的risk契約亦須完全一致。

Standard work的affecting assessment在重新核准後以`kind: supporting`來源追溯，不可暗中加入primary `kind: bug`／`bug_context`；若人類決定改成獨立primary bugfix，另開bug delivery。這避免途中分類繞過開案assessment gate或在standard Complete時遺漏BUG verification。

## Resume 與交付

Resume依 record phase/status進入最早未完成的 child action；不重跑已持久化核准或 Complete child。Blocked解除另追加 recovery evidence，再回同 phase active。

每次 v1 交付回報 identity、current refs、next action與 record path。完成條件：回報值可由 record與實際 workspace重算，且沒有 stage、commit、push、merge、deploy或cleanup。v2 交付另回報 `task_class`、writer／reviewer assignment、knowledge、workspace 與 publication state；預設 `finish` 交付未暫存 diff，只有核准 `commit`／`draft-pr` mode 才能 stage／commit／push／建立 draft PR；merge、deploy 與 cleanup 仍為獨立動作。

## v1 compatibility

缺少 `delivery-run/v2` state 的既有工作仍遵循本文件原有 v1 phases、兩次人工 gate、
host-temp registry 與 terminal checks。v2 不遷移或重寫 v1 record，也不把 v1 approval、
standalone Ledger 或舊 Knowledge Candidate 當成 v2 authorization。
