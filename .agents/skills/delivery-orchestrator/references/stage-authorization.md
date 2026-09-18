<!-- authority: delivery-stage-authorization -->

# 階段授權

本文件是 Requirements、Planning 與 Implementation 寫入權的唯一權威。Repository-local
legacy path 由既有 `delivery-run/v1` record 授權目前階段；portable path 由
`delivery-run/v2` state 的 current dispatch authorization 授權。呼叫端提供的旗標、
prompt、Ready artifact 或自行宣稱的 phase 都不是授權。

## Child call protocol

Child 在建立 Candidate、Ledger、正式 artifact、產品 diff 或任何其他 repository／host-temp／外部狀態前，對目前 repository path 呼叫：

```text
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py authorize --repo <current-worktree> --phase <requirements|planning|implementation> [--work-id <work-id>]
```

只有 `delivery-stage-authorization/v1` 的 `outcome: authorized` 可開啟該次 mutation。結果必須同時證明 requested work ID、registry candidate directory 與 validated record 的 `work_id` 完全一致，current record、latest generation、approved upstream、`status: active`、exact expected phase，以及 requested canonical worktree 等於 generation 的 canonical worktree。

`outcome: routing_required` 表示 child 保持零寫入並交還 `delivery-orchestrator`。固定 reason 為 `no_active_delivery`、`wrong_worktree`、`inactive_status` 或 `wrong_phase`；可辨識 current record 時只回傳 work ID、generation、phase 與 status。requested work ID、registry candidate directory 與 validated record identity 不一致時回 `INVALID_RECORD`。多個 active run、record/schema/source/hash/workspace drift、未知 phase 或其他驗證錯誤使用既有 typed `DeliveryError` fail closed，不降級為授權或猜測目標。

## Read-only boundary

`authorize` 與 `locate` 共用一次 repository probe 與同一 record validation path，且不呼叫 write、transition 或 Git mutation primitive。純解說、診斷、審查、plan-only、治理驗證與測試 fixture 可以唯讀執行；一旦要產生階段成果或改變狀態，仍須先取得上述授權。

Requirements 與 Plan 的人工 Gate、Implementation 的 fresh review，以及 required Knowledge promotion Gate 保持原有 owner 與順序。Child 只產出自身內容，不直接改 delivery phase；phase transition 仍由 Delivery Orchestrator 單獨持有。

## v2 dispatch authorization

v2 在建立產品 workspace／branch 前先完成唯讀 task classification 與核准 payload binding。
`read_only` 永遠沒有 writer authorization；`small` 必須有一次 integrated approval；
`large` 與 bug 修復必須具備對應 Requirements／Planning approval（bug 另需 diagnosis）。
核准 payload 的 digest 綁定 task class、驗收、allowed paths、commands、knowledge scope
與 workspace／finish destination。

Implementation dispatch 會產生只能使用一次的 writer assignment。Assignment 必須包含
`work_id`、state revision、canonical workspace／branch、approved scope、test commands
與 evidence destination；只有目前 assignment 的 implementation writer 可以寫入產品或
測試。Writer 可以是受監督 subagent，但同一 workspace 同一時間不得有平行 writers。
Assignment 完成或失敗後，Orchestrator 先保存 create-only result，再重新授權下一步；
子代理名稱、prompt、branch 或路徑都不能取代 authorization。

v2 的 fresh Reviewer 由不同 session 執行且保持唯讀；它不接收 writer 對話、預期 verdict
或前一位 Reviewer 的未驗證結論。缺少 writer assignment 或 fresh Reviewer capability
時，保持零 mutation 並回報 `blocked`／`awaiting_user`。v2 的 automatic knowledge
review 與 Git finish handoff 只在 implementation review 通過後執行，並受同一 approval
scope 與 state digest 約束。

## v1 compatibility

`delivery-stage-authorization/v1`、`outcome: authorized`、`authorize` CLI 與既有
`delivery-run/v1` record 的 exact phase checks 保持不變。新 v2 state 不會轉換舊 record；
v1 child 仍須依本文件原有 call protocol，不能用 v2 assignment 旁路 legacy gate。
