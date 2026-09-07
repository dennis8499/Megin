# SDLC Repository-local Delivery System

這個專案提供一套由 repository-local Skills、版本化契約、人工核准與可追溯證據組成的軟體交付流程。公開入口會建立獨立 Work ID worktree，再依 Requirements、Planning、Implementation 與 Knowledge 階段推進；各 owner contract 仍是授權與資料規則的唯一權威。

## 環境需求

- Python 3.13
- Git
- ripgrep (`rg`)
- Windows PowerShell 或 POSIX shell；正式 CI 同時在 Windows 與 Linux 執行

專案只使用 Python standard library，不需要安裝 production dependency。

## 快速導覽

| 主題 | 入口 |
|---|---|
| 工作區、階段與授權 | [Delivery Orchestrator](.agents/skills/delivery-orchestrator/SKILL.md) |
| 階段授權契約 | [Stage authorization](.agents/skills/delivery-orchestrator/references/stage-authorization.md) |
| 工作區建立規則 | [Workspace creation](.agents/skills/delivery-orchestrator/references/workspace-creation.md) |
| Requirements | [Requirements Discovery](.agents/skills/requirements-discovery/SKILL.md) |
| Planning 與 Ready plan | [Technical Planning](.agents/skills/technical-planning/SKILL.md) |
| Implementation 與驗證 | [Implementation Execution](.agents/skills/implementation-execution/SKILL.md) |
| Knowledge 搜尋與治理 | [Project Knowledge](.agents/skills/project-knowledge/SKILL.md) |
| BUG 分診 | [BUG Diagnosis](.agents/skills/bug-diagnosis/SKILL.md) |
| 日常操作與復原 | [OPERATIONS.md](OPERATIONS.md) |
| Canonical knowledge | [Knowledge index](docs/knowledge/index.md) |

## 唯讀入口

下列命令不建立 registry、不修改階段，也不寫入產品檔案：

```console
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py probe --repo .
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py locate --repo . --work-id <work-id>
python -X utf8 -B .agents/skills/delivery-orchestrator/scripts/delivery_workspace.py doctor --repo . --work-id <work-id>
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage implementation --query "目前實作意圖"
python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py lint --repo .
```

`doctor` 只提供診斷與下一步指引，絕不授予寫入或階段轉換權限。

## 驗證入口

快速 gate 先檢查語法、五份 Schema、owner contracts 與 canonical knowledge：

```console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_quick_checks.py
```

完整驗證會執行 BDD、owner tests、Delivery integration 與 portability 相關契約：

```console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp
```

若需獨立耗時報告，可將 sidecar 寫到已忽略的 fixture 目錄；功能報告格式不變：

```console
python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp --metrics-output .knowledge-test-tmp/final-metrics.json
python -X utf8 -B .agents/skills/project-knowledge/scripts/measure_search_quality.py --repo .
```

第一個命令會寫入一份 ignored fixture sidecar；操作者須在執行前以 human gate 確認輸出路徑位於 `.knowledge-test-tmp/`。`knowledge-suite-metrics/v1` 只記錄 command ID、狀態、耗時、退出碼與 timeout，不複製原始 stdout/stderr。固定搜尋 corpus 的 Top-5 命中率與來源安全檢查都是強制門檻。

測試缺少 inventory、報告、必要 artifact 或出現 skipped 都不是成功。CI 的 `quick` job 通過後，才啟動 Windows／Linux 完整矩陣。

## 治理邊界

人工決策、可寫階段、Ready／Outcome 證據及 terminal ordering 分別由各 owner contract 定義。請引用 [Requirements delivery protocol](.agents/skills/requirements-discovery/references/delivery-protocol.md)、[Planning delivery protocol](.agents/skills/technical-planning/references/delivery-protocol.md)與 [Implementation delivery protocol](.agents/skills/implementation-execution/references/delivery-protocol.md)，不要在應用程式或文件另建一套授權規則。
