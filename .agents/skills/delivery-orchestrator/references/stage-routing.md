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

## Planning overlay

Bundle root 使用 `docs/work/<work_id>/plan/`；revision採最小可用 `plan-N/`。Transition前以 producer validator重新讀取 `handoff.json`，驗證 ready-plan/v1 schema、payload、contracts、commands、DAG、全部 hashes與恰好一個綁定 current requirements的 `kind: spec` source。

這次 Ready approval是第二個人工 gate；transition成功後直接進 Implementation。

完成條件：current handoff ref與 producer-validated Ready bytes、current requirements及 delivery generation base一致。

## Implementation overlay

首次 preflight只有在 delivery record、generation binding、current requirements與 handoff spec source全部相符時，才把 requirements視為額外唯讀 upstream input。Child Skill仍唯一擁有產品寫入、BDD／TDD、verification、fresh Reviewer、breaker及 terminal ordering。

完成條件：delivery implementation ref與host-temp `implementation-execution/runs/<run_id>/run.json`的binding、Ready revision及Complete attempt一致；terminal index內每個ref已保存。Helper依Reviewer authority重算當下`implementation-snapshot/v1`，其完整object及ID同時等於持久化snapshot與schema-valid `APPROVED` report的before／after；terminal Ledger transition與delivery event引用同一review及snapshot後才可Complete。

## Resume 與交付

Resume依 record phase/status進入最早未完成的 child action；不重跑已持久化核准或 Complete child。Blocked解除另追加 recovery evidence，再回同 phase active。

每次交付回報 identity、current refs、next action與 record path。完成條件：回報值可由 record與實際 workspace重算，且沒有 stage、commit、push、merge、deploy或cleanup。
