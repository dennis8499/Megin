# Group 根目錄工作區契約

## 啟動位置與 Skills

使用者從 GitLab Group 根目錄啟動 Codex。該位置不是 Git repository；其中 `.agents/skills/` 放置整組 `megin*` Skills。Codex 會從目前工作目錄的 `.agents/skills/` 掃描 repository-local Skills；若 Skills 清單未更新，重新載入或啟動 Codex。不要把新工作的記錄放進個別 Repo。

## Repo 選擇與路徑邊界

1. 只列舉 Group 根目錄的直屬子目錄，再用每個候選目錄的 `git -C <path> rev-parse --show-toplevel` 確認它本身就是一個 Git Repo root。忽略一般資料夾、巢狀 Repo 和 Group 根目錄本身。
2. 依使用者請求中的 Repo 名稱或 Group 相對路徑選定目標。若沒有指定、找不到 Repo 或名稱／路徑對應多個 Repo，先詢問並等待選擇，不猜測目標。
3. 對每個選定 Repo，解析真實路徑，確認它是 Group 的直接子目錄、其 parent 正好是 Group root，且 Git top-level 正好等於該 Repo。拒絕 `..`、絕對路徑、穿越符號連結的路徑、巢狀 Repo 或任何逸出 Group 的路徑。
4. 每個 Git 命令都明確使用 `git -C <selected-repo>`；每個專案測試或建置命令記錄明確的 `cwd`。從 Repo 讀取該 Repo 自己的 `AGENTS.md`、README、知識文件、測試規則與工具設定。不同 Repo 的文件或知識不可互相套用。

Group 工作可包含一個或多個已選 Repo，但只用一個 Work ID、一份需求、計畫、行為契約、審查、驗證和驗收紀錄。紀錄集中於 Group root 的 `docs/work/<Work ID>/`，不屬於任何產品 Repo，也不隨 feature commit 放進產品分支。

## Group 工作目錄

```text
<Group>/
  .agents/skills/megin*/
  docs/work/<Work ID>/
    workflow.md
    requirements.md
    plan-<version>/plan.md
    plan-<version>/quality-contract.json
    features/*.feature
    implementation/...
    evidence/quality.json
    evidence/*.md
    evidence/*.log
  <Repo A>/
  <Repo B>/
```

`workflow.md` 是流程狀態來源；核准計畫和品質契約提供義務與路徑；品質證據記錄組合快照、逐 Repo 結果及來源。只支援此 Group 層啟動模型的新工作。Megin Skills 原始碼自身仍可在其獨立 Repo 維護；這不構成一般產品工作的單 Repo 啟動模式。

## 品質命令與證據

新增工作使用 Group v2 品質契約及 `--group-root`、`--work-id`：

```text
python <Group>/.agents/skills/megin/scripts/quality_gate.py snapshot --group-root <Group> --work-id <Work ID>
python <Group>/.agents/skills/megin/scripts/quality_gate.py check --group-root <Group> --work-id <Work ID> --gate review
python <Group>/.agents/skills/megin/scripts/quality_gate.py check --group-root <Group> --work-id <Work ID> --gate acceptance
python <Group>/.agents/skills/megin/scripts/quality_gate.py check --group-root <Group> --work-id <Work ID> --gate delivery
```

契約逐一記錄每個 Repo 的直接子目錄路徑、remote 名稱與不含認證資訊的 URL、base branch 和完整遠端提交 SHA、feature branch、Repo 相對核准路徑，以及每一個檢查的 `cwd`。不要把 remote URL 中的密碼、token 或其他憑證寫入中央紀錄。跨 Repo 指令採一個 check 綁定一個明確目錄；原始輸出以 `Working directory: <cwd>`、`Command:` 和 `Exit code:` 綁定實際檢查。`cwd` 只能是 Group root 的 `.` 或其中一個已選 Repo 名稱。

組合快照將每個 Repo 的 Git-normalized 檔案清單與內容摘要，以及目前 Work ID 中受保護的集中文件摘要合在一起。只排除 `workflow.md` 和核准品質契約中精確列出的 `process_records`；不得整批排除 `docs/work/**`。單一檢查、審查、驗證或人工驗收都必須引用同一組合快照。

遠端 base 的確切 SHA 在規劃時讀取，交付前再次檢查。品質 gate 遇到 remote URL、遠端提交、feature branch 或本機分支祖先不符就失敗。重新確認基線會使既有審查、驗證和人工驗收失效；需更新計畫版本並重新走核准到驗收流程。
