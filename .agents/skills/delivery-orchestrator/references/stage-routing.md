<!-- authority: delivery-routing -->

# 階段路由契約

本文件只把 child 的持久化狀態映射為 delivery transition；Candidate、Ready、BDD／TDD、review與品質規則仍由對應 child Skill唯一擁有。

| Current phase | Child 持久化結果 | Delivery transition |
|---|---|---|
| `workspace` | generation `ready` | `requirements/active` |
| `requirements` | Candidate 已完整展示 | `requirements/awaiting_user` |
| `requirements` | 新 Ready revision 已寫入且核准 | 同一次 transition保存 requirements path/hash/approval refs，進 `planning/active` |
| `planning` | Candidate bundle 已完整展示 | `planning/awaiting_user` |
| `planning` | 新 Ready handoff 已寫入且核准 | 同一次 transition保存 handoff/revision/payload/approval refs，進 `implementation/active` |
| `planning` | 發現需求缺口 | 保存 gap refs，回 `requirements/active` |
| `implementation` | WP-local revision | 保存新 Ledger attempt，留在 `implementation/active` |
| `implementation` | `Awaiting upstream reapproval` | 保存 child refs，回 `planning/active` |
| `implementation` | global-baseline revision | 依 workspace-creation建立下一 generation |
| `implementation` | child `Complete` 且 accepted review snapshot穩定 | 先保存 Ledger/review refs，再轉 `complete/complete` |
| 任一 child | `Blocked` | phase不變，status轉 `blocked`並追加 blocker refs |

## Requirements overlay

Repository path 使用 `docs/work/<work_id>/requirements.md`；revision採最小可用 `requirements-N.md`。核准前沒有正式 artifact；重新核准必須建立新 revision。只有本次 transition新增或重新驗證 current Ready requirements才能進 planning。

完成條件：current requirements ref指向最新寫入、hash相同且具有非空 approval evidence的 Ready revision。

Bug run另要求同一approval transition create-only綁定schema-valid `bug-assessment/v1` JSON、其Markdown path/hash與primary `bug_id`；assessment verdict只接受`confirmed | likely`且disposition為delivery。缺assessment、hash drift、collision或秘密違規不得進Planning。Assessment仍只是evidence，Requirements維持WHAT權威。

## Planning overlay

Bundle root 使用 `docs/work/<work_id>/plan/`；revision採最小可用 `plan-N/`。Transition前以 producer validator重新讀取 `handoff.json`，驗證 ready-plan/v1 schema、payload、contracts、commands、DAG、全部 hashes與恰好一個綁定 current requirements的 `kind: spec` source。

這次 Ready approval是第二個人工 gate；transition成功後直接進 Implementation。

完成條件：current handoff ref與 producer-validated Ready bytes、current requirements及 delivery generation base一致。

Bug run的Ready handoff另必須含唯一`kind: bug` source與`bug_context`，其assessment JSON／Markdown bindings精確等於current approved assessment；verification target與partial safeguards由Planning producer驗證。

## Implementation overlay

首次 preflight只有在 delivery record、generation binding、current requirements與 handoff spec source全部相符時，才把 requirements視為額外唯讀 upstream input。Child Skill仍唯一擁有產品寫入、BDD／TDD、verification、fresh Reviewer、breaker及 terminal ordering。

完成條件：delivery implementation ref與host-temp `implementation-execution/runs/<run_id>/run.json`的binding、Ready revision及Complete attempt一致；terminal index內每個ref已保存。Helper依Reviewer authority重算當下`implementation-snapshot/v1`，其完整object及ID同時等於持久化snapshot與schema-valid `APPROVED` report的before／after；terminal Ledger transition與delivery event引用同一review及snapshot後才可Complete。

Bug run另要求`bug-verification/v1` path/hash/result與current implementation run一致，且只能在同一次`complete/complete` transition綁定。其原始症狀、regression／proxy、full-command與review refs必須實際存在於該run的canonical evidence root並列入terminal index。Reviewer的`APPROVED`只核准implementation snapshot；verification result另為`verified | partial | failed`。`failed`不得Complete；`partial`只能在Ready target為partial且全部safeguards有evidence時共存，verification與review summary採fail-closed canonical wording，只有明示partial／原始症狀仍無法確認的固定句可通過，不能靠改寫繞過過度宣稱防線。

途中BUG依relation分流：`current-scope`保持`implementation/active`並納入Fixing／驗收；`affecting-current-work`要求child run為`Awaiting upstream reapproval`且原子回`planning/active`；`unrelated`保持目前implementation、不改產品，只寫create-only全域inbox。三類先追加pending host-temp refs，再以同ID／relation／refs追加materialized assessment；latest仍pending時不得fresh review terminal handoff或Complete。若含安全、隱私或資料風險，pending與materialized兩次事件都必須帶相同的sensitive flag、遮蔽摘要、安全evidence refs與具名人工reviewer，assessment的risk契約亦須完全一致。

Standard work的affecting assessment在重新核准後以`kind: supporting`來源追溯，不可暗中加入primary `kind: bug`／`bug_context`；若人類決定改成獨立primary bugfix，另開bug delivery。這避免途中分類繞過開案assessment gate或在standard Complete時遺漏BUG verification。

## Resume 與交付

Resume依 record phase/status進入最早未完成的 child action；不重跑已持久化核准或 Complete child。Blocked解除另追加 recovery evidence，再回同 phase active。

每次交付回報 identity、current refs、next action與 record path。完成條件：回報值可由 record與實際 workspace重算，且沒有 stage、commit、push、merge、deploy或cleanup。
