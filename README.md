# SDLC Delivery System

這個 repository 同時提供兩條相容路徑：既有的 repository-local Skills 與 `delivery-run/v1`
治理流程，以及可跨專案安裝的 `sdlc` plugin 與 `delivery-run/v2` workflow。兩者都把需求探索、
技術規劃、實作、BUG 分診、Project Knowledge、核准與可追溯 evidence 串成一條可驗證的流程。
v2 另依任務大小分流，支援受監督的單一 implementation writer、fresh review、automatic
knowledge review 與 Git finish handoff。

系統的核心原則是：每筆變更都有穩定的 Work ID、隔離的 Git worktree、版本化契約、階段授權與雜湊綁定。README 提供入口與常用操作；各 owner contract 才是行為、資料格式與授權規則的唯一權威。

本文件主要服務：

- 第一次接觸 repository 的維護者
- 依流程工作的 Contributor／AI Agent
- 需要判讀測試、CI、metrics 與 evidence 的 CI Reviewer

## Portable `sdlc` plugin（v2）

這個 v2 workflow 參考 [obra/superpowers 的基本流程](https://github.com/obra/superpowers#the-basic-workflow)，
保留本 repository 原有的 Work ID、來源追溯、核准綁定與 v1 相容性。

要在其他 Git repository 使用 v2，先安裝本 repository 提供的 plugin；安裝不會替任何目標
repository 初始化設定或寫入程式碼：

~~~console
codex plugin install ./plugins/sdlc
~~~

進入目標 repository 後，初始化一次專案 binding，再讓 `start` 先做唯讀分類：

~~~console
sdlc init --repo .
sdlc doctor --repo .
sdlc start --repo . --request "<request>"
~~~

`start` 會將請求分類為 `read_only`、`small`、`large` 或 `bug`。read-only 只回報 evidence；
small 產生短 design brief 並只需一次 integrated approval；large 依序取得 Requirements 與
Planning approvals；bug 先完成唯讀 diagnosis，再依影響進入 small 或 large。核准前不建立
產品 worktree／branch。

核准後可由 `status`／`resume` 續跑，完成 review 後使用 `finish`：

~~~console
sdlc status --repo . --work-id <work-id>
sdlc resume --repo . --work-id <work-id>
sdlc finish --repo . --work-id <work-id>
~~~

v2 runtime state、dispatch assignment、review reports、測試 raw outputs 與 publication state
位於 plugin 管理的 repository 外部持久化 state root；`doctor` 會顯示實際 state path。目標
repository 不需要這個 repository 的 `.agents/skills` tree。`finish` 只會在核准範圍內完成
knowledge review、stage／commit；只有已核准 remote 且具備權限時才 push 並建立或重用 draft PR。
沒有核准目的地時保留 `publication_pending`，設定並核准目的地後再續跑發布。
Merge、deployment 與 worktree cleanup 必須另外執行。

完整的分類、核准、升級與相容規則見 [v2 任務分級與核准契約](.agents/skills/delivery-orchestrator/references/v2-task-routing.md)；writer、Reviewer、knowledge 與 finish 見
[v2 派工、審查與交付收尾契約](.agents/skills/implementation-execution/references/v2-dispatch-and-finish.md)。

## 快速開始

### 環境需求

- Python 3.13 或更新版本；CI 的基準版本為 Python 3.13
- Git
- ripgrep (rg)
- Windows PowerShell 或 POSIX shell

Windows checkout 另隨 repository 提供 `tgrep.exe` v1.0.4；它是可選的
Project Knowledge 搜尋加速器，`rg` 仍是所有平台的必要 fallback。

本專案只使用 Python standard library，沒有 production third-party dependency，也沒有需要啟動的 server、database 或 build service。

確認環境：

~~~console
python --version
git --version
rg --version
~~~

### 取得 repository 並執行第一個檢查

若尚未取得 repository，先以既有 Git URL 複製並進入專案目錄：

~~~console
git clone <repository-url>
cd SDLC
~~~

執行快速 gate：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_quick_checks.py
~~~

快速 gate 會依序檢查所有 Git-eligible Python 檔案與 JSON Schema、各 owner contract、文件／CI 契約，以及 canonical knowledge lint。任何命令失敗、timeout 或必要結果缺失，都不會被視為成功。

## 交付流程總覽

### Portable v2 一般變更

~~~text
request -> read-only classify
  -> read_only: evidence / report
  -> small: short design + one integrated approval
  -> large: Requirements approval + Planning approval
  -> approved Work ID worktree / branch
  -> single authorized writer (implementation subagent allowed)
  -> focused + full verification
  -> fresh read-only review
  -> automatic knowledge review
  -> finish: commit -> optional push -> draft PR
~~~

同一 worktree 同一時間只能有一名 writer，不能平行寫入；Reviewer 使用另一個 fresh、唯讀
session。小任務的 integrated approval、或大型變更的第二次 Planning approval，都會綁定
驗收、allowed paths、tests、knowledge scope 與 finish destination。scope drift、review
finding、knowledge conflict 或缺少能力時會停在可觀察的 awaiting／blocked state。

### Repository-local v1 一般變更（legacy）

一般功能、實質重構、介面／資料／依賴行為變更，從 delivery-orchestrator 開始：

~~~text
request
  -> workspace / Work ID
  -> Requirements discovery
  -> Requirements human gate
  -> Technical planning / Ready plan
  -> Planning human gate
  -> Implementation / BDD + TDD + fresh review
  -> Knowledge promotion gate（current policy 要求時）
  -> Complete
~~~

在 v1 path 中，Requirements 與 Planning 各自有一次完整的 human gate。Candidate 只有在使用者核准精確的 review bundle、payload、digest 與 paths 後才是 Ready；聊天中的摘要或「繼續」不會取代核准。Implementation 仍須完成 fresh review，required Knowledge policy 另須通過 Knowledge promotion gate。這些 v1 規則不會套用到明確使用 `delivery-run/v2` 的 portable run。

### BUG 變更

疑似 BUG 在建立 worktree 前先走唯讀 bug-diagnosis。只有 schema-valid 且 verdict 為 confirmed 或 likely 的 assessment，才能進入 bug delivery；診斷本身不會修改 repository、測試、設定或外部狀態。

預期行為改變不是 BUG 修復，應回到 Requirements；尚無足夠證據時，保留下一個可否證的 probe，不以猜測開始實作。

### 唯讀工作

純解說、需求／規格審查、診斷、plan-only、治理驗證與隔離測試，不需要建立新的 delivery run。先使用本文件的唯讀命令與相關 owner contract，避免為了查詢狀態而建立 worktree。

## Work ID、workspace 與產物

### Identity

合法 work_id 是 3–64 字元的 lowercase ASCII kebab-case。未明示時，系統可依日期、topic 與 request digest 產生類似下列格式的 ID：

~~~text
work-YYYYMMDD-<topic>-<request-sha256-prefix>
~~~

每筆工作都綁定 repository identity、base HEAD、worktree、branch、generation 與 append-only delivery record。不要手動改名、複製或重用另一筆工作的核准資料。

### 固定位置

| 資源 | 位置／規則 |
|---|---|
| Delivery worktree | primary-parent / repo-name.worktrees / work_id |
| Branch | delivery/<work_id> |
| Requirements | docs/work/<work_id>/requirements.md |
| Plan bundle | docs/work/<work_id>/plan/ |
| Implementation evidence | host-temp registry 的 run evidence，並由 repository Outcome 綁定 |
| Canonical knowledge | docs/knowledge/ |
| Disposable test fixture | .knowledge-test-tmp/ |
| Portable v2 runtime state | plugin 管理的 repository 外部 state root（由 `doctor` 顯示） |

Repository-local v1 Delivery helper 只負責建立／定位 worktree、驗證 identity、授權階段與追加狀態事件；不會替操作者 stage、commit、push、merge、deploy 或 cleanup。Portable v2 的 `finish` 是獨立 Git handoff，只有在 approved scope、fresh review 與 automatic knowledge review 通過後才可 stage／commit，並依 publication state 選擇 push／draft PR。

## 常用唯讀命令

以下命令用於探測、定位、診斷或驗證，不會建立 registry、不會改變 delivery phase，也不會寫入產品檔案。

### Delivery workspace

~~~console
# 探測 repository identity、HEAD 與 strict-clean 狀態
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py probe --repo .

# 定位目前 active run；有多筆時必須明示 Work ID
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py locate --repo . --work-id <work-id>

# 輸出版本化 continuity checks、diagnostics 與 next actions
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py doctor --repo . --work-id <work-id>

# 驗證目前 worktree 是否獲得指定 child phase 的寫入授權
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py authorize --repo . --phase <requirements|planning|implementation> --work-id <work-id>
~~~

doctor 的輸出 schema 是 delivery-doctor/v1。它只診斷，不會授權、修復、恢復、建立 worktree 或替你選擇多筆 active run。

### Project Knowledge

~~~console
# 依目前階段搜尋 repository-local evidence
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage <requirements|planning|implementation|bug|ad-hoc> --query "<查詢意圖>"

# 驗證 provenance、lifecycle、links、IDs、contradictions、index 與 promotion log
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py lint --repo .
~~~

query 最多使用五個結果；引用結果前要重新讀取 source_refs 指向的原始 repository 檔案。docs/knowledge/ 是人類檢索層，raw repository source 才是 canonical claim 的 evidence authority。

Windows 若要啟用 tgrep 的 on-disk index，必須由使用者明確初始化：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py tgrep-index --repo . [--force]
~~~

查詢不會自動建立 index，也不會啟動 `tgrep serve`。`.tgrep/` 與
`.tgrep/state.json` 是每個 worktree 各自維護的 ignored state；內容變更、
checkout、branch switch、Git index 或 binary 變更後，重新執行上述命令（必要時
加 `--force`）。state 驗證失敗或 tgrep 執行失敗時，查詢會靜默回到 `rg`。

## 會產生狀態的進階命令

下列命令不是一般查詢入口。它們必須由 Delivery Orchestrator 或對應 owner contract 路由，不能拿來繞過人工 gate、phase authorization 或 hash validation。

### Portable v2 lifecycle

以下是 plugin 的公開 CLI；它們使用目標 repository 的明確 `--repo`，不依賴目標專案的
`.agents/skills`。`init` 只建立 project binding；`start` 先分類並保存候選 state；
`doctor`／`status` 只讀取 state；`resume` 從第一個未完成 action 繼續；`finish` 是
implementation、review、knowledge 與 Git handoff 的唯一收尾入口：

~~~console
sdlc init --repo <target-repo>
sdlc doctor --repo <target-repo>
sdlc start --repo <target-repo> --request "<request>"
sdlc status --repo <target-repo> --work-id <work-id>
sdlc resume --repo <target-repo> --work-id <work-id>
sdlc finish --repo <target-repo> --work-id <work-id>
~~~

Approval and execution results are recorded explicitly. For a small task, bind the allowed
paths and tests to one integrated approval, then record the writer and fresh reviewer results:

~~~console
sdlc start --repo <target-repo> --request "<request>" --allowed-path src/example.py --test-command "python -m unittest" --approve --approval-ref user:approval
sdlc resume --repo <target-repo> --work-id <work-id> --writer-ticket <assignment-ticket> --writer-report <writer-report.json> --writer-complete
sdlc resume --repo <target-repo> --work-id <work-id> --review-verdict APPROVED --reviewer-id fresh-reviewer --review-report <review-report.json>
sdlc finish --repo <target-repo> --work-id <work-id>
~~~

Large work uses `--approve requirements` and `--approve plan` on separate approval steps. Bug
repair first runs `sdlc diagnose` with a read-only oracle and falsifiable hypothesis, then passes
`--diagnosis-file <assessment>` to `start`; otherwise `start` remains a read-only diagnosis response.
Writer／Reviewer／knowledge completion reports are external, snapshot-bound JSON evidence. The dependency-free self-check is
`python -X utf8 -B <plugin-root>/scripts/validate.py`.

v2 的 `start` 只在對應 approval 完成後建立 worktree／branch；同一 worktree 同一時間
最多一名 authorized writer，implementation subagent 可以擔任 writer。Fresh Reviewer
以不同 session 唯讀審查完整 diff 與 evidence。`finish` 通過 approved path、knowledge
scope 與 snapshot preflight 後建立 commit；有 remote／認證時 push 並建立或重用 draft PR，
否則保存 `publication_pending`，待目的地核准後供 `resume`／`finish` 重試。merge、deployment、cleanup
與刪除 worktree 不由 v2 自動執行。

### Repository-local v1 建立或續接 workspace

~~~console
# 進階：建立 Work ID 專用 worktree；執行前必須已有本次交付授權
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py start --repo <primary-repo> --work-id <work-id> --request-sha256 <request-sha256>

# BUG work 另須使用已核准的 bug assessment identity
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py start --repo <primary-repo> --work-id <work-id> --request-sha256 <request-sha256> --work-kind bug --bug-id <bug-id>
~~~

start 會建立 Git worktree／branch 與 host-temp registry binding。建立前必須通過 strict-clean、base HEAD、destination collision、Git trust 與 repository identity 檢查；失敗時不應自行 reset、clean 或刪除現場。

### v1 Phase transition

transition 會以 append-only 方式追加 delivery phase event，並驗證 current refs、approval、artifact hashes、generation、knowledge 或 BUG verification bindings。這個命令的參數很多，請依目前 phase 使用 owner contract，不要手動組合參數來模擬 Requirements、Planning 或 Complete：

~~~console
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py transition --help
~~~

實際寫入前，child 必須先取得 exact phase authorization：requirements/active、planning/active 或 implementation/active。doctor 或 prompt 本身不會授予寫入權。

### v1 Knowledge Candidate、Review 與 Apply

Project Knowledge 的生命週期是：

~~~text
draft -> candidate（create-only）-> review -> explicit human approval -> apply -> post-apply lint
~~~

建立 Candidate 只會封存待審閱 bundle，不代表已核准：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py candidate --repo . --draft <host-temp-draft.json> --approval-actor <expected-actor> --approval-evidence <stable-evidence-token>
~~~

重新檢視相同的 immutable bundle：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py review --repo . --candidate-ref <candidate-ref>
~~~

只有使用者明確核准目前 candidate_ref、payload_sha256、review_sha256 與完整 manifest 後，才能套用：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py apply --repo . --candidate-ref <candidate-ref> --review-sha256 <review-sha256> --approval-actor <actor> --approval-evidence <evidence-ref>
~~~

Chat 只呈現 human-gate-summary/v1 摘要與 direct links，不應貼上完整 payload、postimage 或 raw command output。source drift、preimage drift、manifest drift、path collision、缺少 review digest 或 approval ambiguity 都必須 fail closed。

### Recovery

只有命令回傳 RECOVERY_REQUIRED 時，才依 [OPERATIONS.md](OPERATIONS.md) 與 [Project Knowledge Skill](.agents/skills/project-knowledge/SKILL.md) 的 recovery 指引執行：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py recover --repo .
~~~

不要手動刪除 transaction journal、registry、worktree 或複製舊 approval。復原完成後，要重新執行 doctor／phase preflight，而不是假設交易已成功。

## 驗證、測試與 CI

### Portable v2 validation

Plugin release 前至少要在乾淨的 Git repository 驗證 manifest、CLI 與 state isolation；
驗證範圍包含四種 task class、small／large gate policy、single-writer lock、fresh
Reviewer、automatic knowledge review、finish idempotency，以及 Windows／Linux parity。
Plugin 的 validator／test entrypoint 位於 `plugins/sdlc/`，執行方式以該 plugin 的
README 或 `doctor` 輸出為準；它們不得把 runtime state 寫回目標 repository。

~~~console
# 在 plugin source checkout 驗證 manifest 與 portable CLI
python -X utf8 -B -c "import json, pathlib; p=pathlib.Path('plugins/sdlc/.codex-plugin/plugin.json'); m=json.loads(p.read_text(encoding='utf-8')); assert m['name'] == 'sdlc'; assert m['skills'] == './skills/'"
python -X utf8 -B plugins/sdlc/scripts/sdlc.py --help
python -X utf8 -B -m unittest discover -s plugins/sdlc/tests -p "test_*.py"
~~~

若 plugin 尚未安裝，先使用前面的 `codex plugin install ./plugins/sdlc`；上述命令不會
取代目標專案自己的 build／test。v2 `finish` 的 commit／push／draft PR evidence 也要
納入 CI artifact；沒有 remote 或 credentials 的測試應驗證 `publication_pending` 可續跑。

### 快速 gate

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_quick_checks.py
~~~

快速 gate 包含：

- 全部 Git-eligible Python syntax 與 JSON Schema 檢查
- Requirements、Planning、Implementation、BUG、Delivery owner validators
- 文件與 CI contract tests
- canonical knowledge lint

### Focused 或完整 suite

針對 Project Knowledge retrieval 相關變更，可以先執行較小範圍：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope related --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 4 --evidence-root .knowledge-test-tmp/evidence-related --ready-payload-sha256 <ready-payload-sha256>
~~~

日常 local completion check：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --profile local --fixture-root .knowledge-test-tmp/fixtures --jobs 4 --evidence-root .knowledge-test-tmp/evidence --run-label local-1 --ready-payload-sha256 <ready-payload-sha256>
~~~

Profile runner 會平行執行明確標示為 parallel-safe 的命令，每個 worker 使用獨立 fixture、temp 與 Delivery registry；performance scenarios 保持循序並最後執行。任一失敗或 timeout 會停止派發新工作，未啟動項目明列 `not_run`。all 涵蓋 BDD、workflow、governance、owner tests、syntax／schema、搜尋品質與 Delivery workspace integration；拆分後的 physical commands 以 logical ID 和完整 child inventory 證明原義務，避免重跑相同 BDD、build 或治理命令。Local profile 不執行需要跨平台 release evidence 的 `BDD-016`；release profile 與未帶 profile 的相容入口仍執行該 50k portability scenario，且 release 完成仍需 Windows／Linux CI reports。

驗證 bundle 可直接重驗或產生 reviewer 閱讀稿：

~~~console
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py verify --index .knowledge-test-tmp/evidence/local-1/index.json
python -X utf8 -B .agents/skills/implementation-execution/scripts/validation_evidence.py render --handoff docs/work/<work-id>/plan/handoff.json --index .knowledge-test-tmp/evidence/local-1/index.json
~~~

未帶 `--profile` 的舊 runner 仍維持循序相容行為。發布時改用 `--profile release`；跨平台完成仍須 CI 的 Windows／Linux reports，單一本機 release profile 不構成跨平台證據。

### Metrics 與搜尋品質

需要逐命令耗時與狀態時，將獨立 metrics sidecar 寫入已忽略的 fixture 目錄：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp --metrics-output .knowledge-test-tmp/final-metrics.json
~~~

舊 `knowledge-suite-metrics/v1` 只記錄 command ID、status、duration、exit code、timeout 與 not_run，不複製原始 stdout／stderr。Profile runner 的 `validation-evidence/v1` 另保存牆鐘時間、physical／logical command、完整原始輸出雜湊與fixture profile；metrics與evidence目標都必須位於 `.knowledge-test-tmp/`，不要寫入repository其他位置。

執行固定搜尋 corpus 的 Top-5 命中與 source-safety 檢查：

~~~console
python -X utf8 -B .agents/skills/project-knowledge/scripts/measure_search_quality.py --repo .
~~~

CI 位於 [.github/workflows/knowledge-portability.yml](.github/workflows/knowledge-portability.yml)：先執行 quick job，成功後才執行 Windows／Linux 完整矩陣，最後比較跨平台報告。.agents/skills/**、plugins/sdlc/**、docs/**、README.md、OPERATIONS.md、.gitattributes 與 workflow 變更都會觸發相關檢查；若存在 plugin manifest，quick／platform jobs 也會執行 portable v2 validator 與 CLI tests。

## 常見診斷與安全處理

先保存原始錯誤碼與 evidence，再執行：

~~~console
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py locate --repo . --work-id <work-id>
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py doctor --repo . --work-id <work-id>
~~~

| 診斷 | 意義與處理 |
|---|---|
| NO_ACTIVE_RUN | 沒有可續跑的 active run；確認 Work ID，必要時建立新工作。 |
| AMBIGUOUS_RUNS | 有多筆 active run；從 available_work_ids 明確選一筆，不讓工具猜測。 |
| RECORD_MISSING／INVALID_RECORD | record 遺失或不符合 schema；保留舊 worktree 與 evidence，重新建立並驗證新 Work ID。 |
| ARTIFACT_DRIFT | 正式 artifact 與核准 hash 不一致；回到擁有該來源的上游 phase 重新核准。 |
| EVIDENCE_MISSING | 需要的 approval／evidence 不存在；重新取得新證據，不複製舊 approval。 |
| RECOVERY_REQUIRED | 存在未完成 transaction journal；依 recovery 指引處理後重新診斷。 |
| IDENTITY_MISMATCH | 目前路徑不是 record 綁定的 canonical worktree；回到正確 workspace。 |
| ENVIRONMENT_UNAVAILABLE | Git、權限、registry 或檔案系統前提不可用；先修復環境再重跑。 |
| GIT_TRUST_REQUIRED | Git trust 檢查需要受控的額外權限；依提示重跑，不修改 global safe.directory 來繞過檢查。 |

若 delivery record 已是 Complete，代表狀態已凍結；不得追加 event、重用 approval 或從原 run 重新開始。新變更必須建立新的 Work ID。

更多續跑、Blocked、Complete 與安全重建細節請參閱 [OPERATIONS.md](OPERATIONS.md)。

## Repository 導覽

~~~text
.
├── plugins/sdlc/                    # portable v2 plugin、CLI、schemas、skills
├── .agents/skills/                 # repository-local Skills、contracts、scripts、schemas
├── docs/work/<work_id>/            # Requirements、Plan 與工作交接 artifacts
├── docs/knowledge/                 # canonical knowledge 與 provenance sidecars
├── .github/workflows/              # Windows／Linux portability CI
├── README.md                       # 本入口與常用使用方法
├── THIRD_PARTY_NOTICES.md          # bundled tgrep attribution／license
└── OPERATIONS.md                   # 續跑、診斷、Blocked、Complete、復原手冊
~~~

### 權威入口

| 主題 | 權威文件 |
|---|---|
| 工作區、phase routing 與唯一 mutation 入口 | [Delivery Orchestrator](.agents/skills/delivery-orchestrator/SKILL.md) |
| 階段授權與 read-only boundary | [stage-authorization.md](.agents/skills/delivery-orchestrator/references/stage-authorization.md) |
| v2 任務分級與 approval policy | [v2-task-routing.md](.agents/skills/delivery-orchestrator/references/v2-task-routing.md) |
| Worktree、Work ID、record 與 resume | [workspace-and-run.md](.agents/skills/delivery-orchestrator/references/workspace-and-run.md) |
| 新 workspace 建立與 Git safety | [workspace-creation.md](.agents/skills/delivery-orchestrator/references/workspace-creation.md) |
| Requirements | [Requirements Discovery](.agents/skills/requirements-discovery/SKILL.md) |
| Planning 與 Ready plan | [Technical Planning](.agents/skills/technical-planning/SKILL.md) |
| Implementation、BDD／TDD 與 fresh review | [Implementation Execution](.agents/skills/implementation-execution/SKILL.md) |
| v2 writer、Reviewer、knowledge 與 Git finish | [v2-dispatch-and-finish.md](.agents/skills/implementation-execution/references/v2-dispatch-and-finish.md) |
| BUG 唯讀分診 | [BUG Diagnosis](.agents/skills/bug-diagnosis/SKILL.md) |
| Knowledge 搜尋、Candidate 與 promotion | [Project Knowledge](.agents/skills/project-knowledge/SKILL.md) |
| 共用 human gate contract | [human-gate-review.md](.agents/skills/project-knowledge/references/human-gate-review.md) |
| Canonical knowledge 導覽 | [Knowledge index](docs/knowledge/index.md) |
| 日常操作與復原 | [OPERATIONS.md](OPERATIONS.md) |

README 只負責導覽與使用方法。若本文件與 owner contract、schema、validator、測試或 CI 行為不一致，應以最新且可驗證的 owner contract 為準，並修正 README 的導覽內容，而不是在 README 另建一套規則。

## 維護文件時

修改 Skills、contracts、schemas、docs 或根目錄指南前，先以對應 stage 執行 Project Knowledge query，並重新讀取引用的 raw source。文件變更至少應通過 quick gate；涉及交付、Schema、Knowledge、跨平台或 workspace 行為時，再執行完整 suite。

Repository-local v1 不提供自動備份還原、跨機遷移、核准流程重設、歷史 record 批次修補或自動發布流程。Portable v2 plugin 提供 scoped `finish` handoff，可自動 commit，並在 remote／credentials 可用時 push 與建立 draft PR；merge、deployment、cleanup 與歷史 record migration 仍不自動執行。
