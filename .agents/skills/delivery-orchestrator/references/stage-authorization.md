<!-- authority: delivery-stage-authorization -->

# 階段授權

本文件是 Requirements、Planning 與 Implementation 寫入權的唯一權威。Delivery Orchestrator 以既有 `delivery-run/v1` record 授權目前階段；呼叫端提供的旗標、prompt、Ready artifact 或自行宣稱的 phase 都不是授權。

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
