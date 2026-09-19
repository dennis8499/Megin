# Megin 操作手冊

新工作統一使用 portable `delivery-run/v3`。本手冊說明探索、單一計畫核准、BDD/TDD 派工、獨立 Review、自動驗證、人工驗測與本機 commit；舊 v1/v2 規則只作歷史 run 遷移參考，不能用舊核准續跑新工作。

## Portable v3 快速操作

先安裝 plugin；安裝只提供技能／CLI，不會替目標 repository 建立功能 branch、worktree 或寫入產品：

```console
codex plugin marketplace add .
```

Refresh the Plugin Directory and install `megin` from the repository-scoped `megin-local` market.
The repository provides both `plugin.json` (portable manifest) and `.codex-plugin/plugin.json`
(compatibility fallback). A source checkout can invoke `plugins/megin/bin/megin` or
`plugins/megin/bin/megin.cmd`; installation is not assumed to expose a global `megin` executable.

在目標 Git repository 執行一次 `init`，接著由 `start` 做唯讀分類與候選建立；核准前不建立功能 branch：

```console
megin init --repo <target-repo>
megin doctor --repo <target-repo>
megin start --repo <target-repo> --request "<request>"
```

分類與 gate policy：

| 類型 | 行為 |
|---|---|
| `read_only` | 只查證與回報，不建立 run、worktree 或 branch |
| `small` | 短 Design、必要 Gherkin，一次 plan approval |
| `large` | 完整 Design、Gherkin、Task graph，一次 plan approval |
| `bug` | 先唯讀 diagnosis，再依影響走 small 或 large path |

核准範圍同時綁定行為情境、驗收、allowed paths、測試命令、knowledge scope 與本機 commit 目標。
同一 workspace 同一時間最多一名 authorized writer；implementation subagent 可以擔任 writer，
但不得平行寫入或自行再委派。Implementation 完成後由不同 fresh、read-only Reviewer 審查；
blocking finding 回交同一 writer，沿用 bounded fix loop。

若使用 Gherkin，`start` 必須綁定 `--scenario-command`；命令輸出需以 stable scenario ID
回報每個 scenario 的實際狀態。只有 runner 回報 `passed` 才能通過 automatic scenario，
undefined、skipped、缺少結果或 parser-only 結果都會阻擋 `verify`。`verify`、`accept` 與
`finish` 會重新確認 approved review snapshot、branch、HEAD 與 knowledge source digest；
current workspace 另受 repository lock 保護。

續跑與收尾：

```console
megin status --repo <target-repo> --work-id <work-id>
megin approve --repo <target-repo> --work-id <work-id> --confirm
megin resume --repo <target-repo> --work-id <work-id>
megin verify --repo <target-repo> --work-id <work-id>
megin accept --repo <target-repo> --work-id <work-id> --confirm
megin finish --repo <target-repo> --work-id <work-id>
```

小任務的核准、派工、審查與人工驗測可用下列最小循序操作表示；每個結果都會寫入外部 v3 state：

```console
megin start --repo <target-repo> --work-id example-small-task \
  --request "<request>" --allowed-path src/example.py --test-command "python -m unittest" \
  --scenario-command "python -c \"import json; print(json.dumps({'scenarios': [{'id': 'BDD-EXAMPLE-SMALL-TASK-001', 'status': 'passed'}]}))\""
megin approve --repo <target-repo> --work-id example-small-task --response "確認計畫 example-small-task plan-1，依此開始開發。"
megin resume --repo <target-repo> --work-id example-small-task --writer-ticket <assignment-ticket> --writer-report <writer-report.json> --writer-complete
megin resume --repo <target-repo> --work-id example-small-task --review-verdict APPROVED --reviewer-id fresh-reviewer --review-report <review-report.json>
megin verify --repo <target-repo> --work-id example-small-task
megin accept --repo <target-repo> --work-id example-small-task --response "驗測通過 example-small-task acceptance-1，同意更新知識並建立本機 commit。"
megin finish --repo <target-repo> --work-id example-small-task
```

若 snapshot drift 使 `verify` 回到 `awaiting_review`，依序對所有 affected task 重新提交 fresh
APPROVED review，再執行 `verify`；若 knowledge validation 失敗，修正來源或 Project Knowledge
lint 後可沿用同一 Work ID 重跑 review → verify → accept → finish。source bytes 改變時不可跳過
snapshot gate，也沒有人工 unlock bypass。

大型變更仍在同一個 `approve` 關卡核准完整 bundle；疑似
BUG 先以 `diagnose` 的唯讀命令與根因假設保存 assessment，再以 `--diagnosis-file` 綁定修復。來源 checkout 可用
`python -X utf8 -B plugins/megin/scripts/validate.py` 驗證 manifest、技能、schema 與 state。

`verify` 通過後會停在 `awaiting_user_acceptance`，不更新正式 knowledge、不 stage、不 commit。
`accept` 記錄人工驗測版本；`finish` 才檢查 source-backed knowledge、限定 paths 並建立一筆本機 commit。
Push、Merge、deployment、cleanup 與刪除 worktree 永遠是獨立動作。runtime state、assignments、reports、
raw outputs、人工驗測與 publication state 存在 repository 外的持久化 state root；`doctor` 顯示實際路徑。

v3 的詳細規則見 [Megin v3 orchestrator](plugins/megin/skills/megin-orchestrator/SKILL.md)、[behavior-contract](plugins/megin/skills/behavior-contract/SKILL.md) 與 [human-acceptance](plugins/megin/skills/human-acceptance/SKILL.md)。

## 從舊版設定建立 v3 候選

Megin v3 不會直接讀取 `.sdlc/config.json`，也不會沿用 v1/v2 的核准。保留舊設定、run 與 evidence
作為來源，重新執行探索並建立新的 Work ID：

```console
megin classify --request "<new request>"
megin start --repo <target-repo> --request "<new request>" --source <historical-evidence>
```

新候選必須重新取得當前基底 SHA、計畫版本與使用者核准；必要時在 `--source` 保留舊決策的來源連結。任何衝突都停在探索或規劃，不自動覆寫歷史內容。

## Repository-local v1 開始一筆工作（legacy）

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

## Repository-local v1 正常續跑（legacy）

先執行唯讀定位及診斷：

```console
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py locate --repo . --work-id <work-id>
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py doctor --repo . --work-id <work-id>
```

預期：`locate` 回報唯一 run 的 phase／status／generation；`doctor` 回報 `delivery-doctor/v1`。只有對應階段的 `authorize` 結果為 `authorized` 時，owner Skill 才能繼續 mutation。

未指定 Work ID 時，系統只會在恰有一筆 active run 時選取；多筆候選必須由操作者明確指定，工具不代替人工選擇。

## Repository-local v1 Project Knowledge tgrep index

Windows 的 Project Knowledge 查詢可使用 repository-local tgrep index。index 不會由
query 隱式建立；每個 worktree 都要各自初始化一次：

```console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py tgrep-index --repo . [--force]
```

初始化只建立 ignored `.tgrep/` 與 `tgrep-index-state/v1` state，並在 index 前後
驗證 repository snapshot、binary SHA-256、版本與 index fingerprint。修改內容、
checkout、branch switch、Git index 或替換 `tgrep.exe` 後，重新執行命令；state
不一致時 query 維持唯讀並靜默使用 `rg`。本次不使用 `tgrep serve`，也不會在 query
期間下載或修復 index。

## Blocked（v1 與 v2 共用原則）

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

v2 `doctor` 另會指出 `task_class`、approval／scope drift、writer lock、reviewer capability
與 publication state。`WRITER_ASSIGNMENT_CONFLICT`、`SCOPE_DRIFT`、`REVIEW_REQUIRED`、
`KNOWLEDGE_CONFLICT` 或 `PUBLICATION_PENDING` 都保留 state 與 evidence；修復後用
`megin resume`／`megin finish` 從最早未完成 action 續跑，不複製舊 approval 或重複 commit／PR。

## Complete（v1 與 v2）

v1 Complete record 已凍結。可用 `locate --work-id` 與 `doctor --work-id` 唯讀檢查，但不得追加事件、重用核准或從原 run 重新開始。新變更必須建立新 Work ID。v2 在 `finish` 後也會凍結 approved state；`publication_pending` 是尚未完成的可續跑狀態，不得宣稱 draft PR 已建立，且只允許重試未完成的 push／PR handoff。

## 驗證與量測

Portable v2 另外驗證 plugin manifest、CLI、classification、single-writer dispatch、fresh
review、automatic knowledge review、finish idempotency 與 Windows／Linux parity；執行 plugin
提供的 validator／test entrypoint，不把 runtime state 寫入目標 repository。Repository-local
v1 runner 與下列 commands 維持既有循序／profile 相容行為。

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

v2 runtime state 遺失或損壞時，先用 `megin doctor --repo <target-repo> --work-id <work-id>`
保存診斷；不要刪除 state root、worktree 或 branch，也不要把 v1 host-temp registry 複製成
v2 state。只有能以 repository identity、Work ID、assignment、scope digest 與現有 diff
證明 continuity 時，才由 `megin resume` 續跑；否則建立新 v2 Work ID，重新取得所需 gate。

本專案不提供核准流程重設或歷史record批次修補；archive也不能把不同identity或不完整run變成可續跑狀態。
