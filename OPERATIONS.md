# SDLC 操作手冊

本手冊集中說明開始、續跑、診斷、Blocked、Complete 與安全復原。規則細節仍以 [Delivery Orchestrator](.agents/skills/delivery-orchestrator/SKILL.md)、[stage-authorization.md](.agents/skills/delivery-orchestrator/references/stage-authorization.md)及各階段的 `delivery-protocol.md` 為準。

## 開始一筆工作

1. 唯讀探測 repository，保存 `repo_id`、HEAD 與建議 Work ID：

   ```console
   python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py probe --repo . --topic <topic> --request-sha256 <request-sha256>
   ```

   預期：退出碼 `0`，輸出 repository identity；沒有 worktree 或 registry 寫入。

2. 由 Delivery Orchestrator 使用探測結果建立 Work ID 專用 worktree。這一步會寫入 Git worktree 與 host-temp registry，必須已有本次交付授權。

3. 在 Requirements 與 Planning 各呈交一次 immutable review bundle。

   **人工決策點：** 使用者分別核准精確 Candidate、payload、review digest 與完整 paths。核准前不得把 Candidate 當成 Ready。

4. Ready plan 進入 Implementation 後，依 WP DAG 執行 BDD red、inner test red、minimal green、refactor 與完整驗證。

5. Required knowledge delivery 在產品 fresh review 後呈交 Implementation／Knowledge Candidate。

   **人工決策點：** 使用者核准完整 promotion bundle 後，才可套用 canonical knowledge 並完成 Delivery。

## 正常續跑

先執行唯讀定位及診斷：

```console
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py locate --repo . --work-id <work-id>
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py doctor --repo . --work-id <work-id>
```

預期：`locate` 回報唯一 run 的 phase／status／generation；`doctor` 回報 `delivery-doctor/v1`。只有對應階段的 `authorize` 結果為 `authorized` 時，owner Skill 才能繼續 mutation。

未指定 Work ID 時，系統只會在恰有一筆 active run 時選取；多筆候選必須由操作者明確指定，工具不代替人工選擇。

## Blocked

Blocked 表示 workspace、能力、工具、資料完整性或外部前提無法安全成立。先保存原始錯誤碼與 evidence refs，再執行 `doctor`。修正同一項環境前提後，blocked recovery 必須留在原 phase；不得用 `reset`、`clean`、刪除 registry 或複製核准資料繞過 gate。

常見分類：

| 診斷 | 動作 |
|---|---|
| `NO_ACTIVE_RUN` | 確認 Work ID；若證據確實遺失，建立新工作並重新驗證。 |
| `AMBIGUOUS_RUNS` | 從 `available_work_ids` 選定 Work ID 後重跑，不讓工具自行挑選。 |
| `RECORD_MISSING`／`INVALID_RECORD` | 保留 record 目錄與 worktree，建立新工作並重新驗證。 |
| `ARTIFACT_DRIFT` | 保留工作區差異，回到擁有該來源的上游階段重新核准。 |
| `EVIDENCE_MISSING` | 建立新工作重新取得人工證據，不複製或推定舊核准。 |
| `RECOVERY_REQUIRED` | 依既有 transaction recovery 指引處理 journal，再重跑診斷。 |
| `IDENTITY_MISMATCH` | 回到 registry 所記錄的 canonical worktree。 |
| `ENVIRONMENT_UNAVAILABLE` | 恢復 Git、權限或檔案系統可讀性後重跑。 |

## Complete

Complete record 已凍結。可用 `locate --work-id` 與 `doctor --work-id` 唯讀檢查，但不得追加事件、重用核准或從原 run 重新開始。新變更必須建立新 Work ID。

## 驗證與量測

未帶profile的舊runner保持循序執行及遇錯停止。新工作使用local profile：parallel-safe commands在有界worker pool中執行，每個worker有私有fixture、temp及Delivery registry；performance scenarios等所有parallel work完成後才循序執行。Fail-fast保留完整預定inventory，未啟動者為`not_run`，timeout不會被誤報為通過。Local profile排除要求跨平台release evidence的`BDD-016`；`--profile release`及未帶profile的相容入口仍執行50k portability scenario。Release完成仍以Windows／Linux CI reports為準。

```console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 4 --evidence-root .knowledge-test-tmp/evidence --run-label local-1 --ready-payload-sha256 <ready-payload-sha256>
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py verify --index .knowledge-test-tmp/evidence/local-1/index.json
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp --metrics-output .knowledge-test-tmp/final-metrics.json
python -X utf8 -B .agents/skills/project-knowledge/scripts/measure_search_quality.py --repo .
```

`validation-evidence/v1` create-only bundle保存執行時Git／Markdown輸入、Ready digest、環境、physical／logical command inventory、stdout／stderr、exit、failure／skip counts、牆鐘、worker cleanup與fixture建立／操作／清理耗時。相同logical obligation只由完整passed child inventory滿足。第三個命令示範舊runner的獨立`knowledge-suite-metrics/v1` sidecar。Evidence與metrics都只能位於已忽略的`.knowledge-test-tmp/`或正式Ledger；測試會驗證移除sidecar／worker fixture後產品bytes不變。

搜尋報告不輸出原始 excerpt；Top-5 hit rate 與 `source_safety` 都必須通過。中文流程問題會加入有界2／3-gram與domain aliases，owner contract只有在恰有一個authority marker且原始bytes可重驗時進入Top-5。階段耗時與回流次數由`doctor.process_metrics`從既有append-only events計算；activity另拆成commands、review、human wait、interruption與扣除已歸因區間的active work。缺少或仍開啟的區間維持`null`並附`activity_unavailable_reasons`，不推測時間。

### Evidence 保存與復原

```console
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py archive export --run-root <implementation-ledger-root> --output <new-archive.zip>
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py archive verify --archive <archive.zip> --run-id <sha256> --repo-id <sha256> --worktree-key <sha256>
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py archive import --archive <archive.zip> --imports-root <quarantine-root> --run-id <sha256> --repo-id <sha256> --worktree-key <sha256>
```

Archive是deterministic、create-only，manifest逐檔保存hash與run／repo／worktree identity。Import只進quarantine且固定`approval_inherited: false`；續跑仍須重新authorization、Ready／source／workspace preflight與Ledger continuity。Active run不自動prune，Complete evidence至少保留30天；prune必須明確執行，且不可刪除active run、未驗證archive或唯一證據副本。

## 安全復原與重建

1. **完整狀態仍在：** 由 `doctor` 指示目前 phase，重新執行該 phase 的 read-only authorization／preflight，再從 append-only Ledger 的最後合法狀態續跑。
2. **存在 recovery journal：** 使用 Project Knowledge 已有的 recovery 機制；先查閱 [Project Knowledge Skill](.agents/skills/project-knowledge/SKILL.md)，不手動刪除 journal 或猜測 transaction 已完成。

   ```console
   python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py recover --repo .
   ```
3. **registry、record 或正式 evidence 遺失：** 先驗證綁定同一run／repo／worktree的archive並匯入quarantine；成功只提供resume evidence，不繼承approval。沒有完整可信archive時，保留舊worktree與未提交修改，另建新Work ID，從Requirements重新驗證。安全重建不自動複製產品差異，也不繼承舊核准。

本專案不提供核准流程重設或歷史record批次修補；archive也不能把不同identity或不完整run變成可續跑狀態。
