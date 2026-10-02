# 計畫：強化 Megin Group 工作區驗證與隔離

- plan_version: plan-1
- requirements_revision: req-1
- repository: .
- base_branch: main
- base_commit: 10716d90c367cc00c0c23815c017390783c84f85
- feature_branch: feature/work-20261002-group-workspace-hardening
- delivery_mode: local_merge
- owner: Megin Skills source maintenance

## 核准範圍

依 Work ID 核准計畫實作第 1、4、5、6、7、8 項；第 2、3 項不實作。既有使用者要求、決策及六個 Given/When/Then 情境以本目錄 `requirements.md` 和 `features/group-hardening.feature` 為準。

## 修改範圍

- 十二個 `.agents/skills/megin*/` 技能及共用說明；現有 Group 品質 helper 與封裝檢查工具。
- `tests/group-workspace/` 隔離測試與 `.github/workflows/knowledge-portability.yml`。
- `README.md`、`OPERATIONS.md`、重建後的 `megin-skills.zip`。
- 僅本 Work ID 下的需求、核准計畫、情境與證據。

既有歷史 Work ID、其它產品檔案、遠端 branch 與發布動作不在核准修改範圍。

## 技術義務

1. 共用 helper 定義嚴格 workflow 標頭讀取、Group 設定解析和十二個 Skills 可重現 SHA-256；所有作業只信任 canonical direct-child Repo 與 Group-contained 設定路徑。Python caches 不納入指紋。
2. Group v3 在既有品質 helper 中以明確分支支持；Group v2 snapshot/gates、Repo v1 維護入口與歷史封裝驗證持續受回歸測試。工作紀錄欄位、Repo、delivery mode 及核准 contract 必須完全一致；技能或有效設定差異停止新 gate。
3. 排他 lock 以同一本機 Group 的 `<Group>/.megin/workspace.lock.json` 原子獨佔建立。`claim` 只在已核准 implementation 工作前取得；`check` 驗證 Work ID／writer；`release` 只可在完成 gate 通過後，或使用者確認舊 writer 已停止並提供原因後執行。不得按 PID、時間或心跳自動解鎖。
4. 多 Repo handoff 契約逐一列出所有 Repo、合併前置依賴和無重複的完整合併順序；順序遵守依賴圖且無循環。須以已核准的測試 ID 驗證相容性，或記錄明確不適用理由；列出部分完成後的合併與恢復操作。交付證據路徑須在核准合約中預先宣告。
5. `completion` 從預先宣告且有來源 digest 的 process record 讀取每個 Repo 的實際 feature commit；驗證對核准基線的祖先關係及 feature tree digest。單 Repo 另外驗證本機 `--no-ff` merge commit 的兩個預期父提交及 tree；多 Repo 不自行合併 base。
6. v3 完成檢查不得讀取目前已切換或已更新的 worktree 取代交付證據；透過核准記錄的 immutable Git objects 驗證，因此後續歷史查驗不依賴目前 branch checkout。
7. Linux／Windows 執行相同維護測試清單和 ZIP 驗證。測試用中文、空白路徑、CRLF、mode 與平行程序競爭涵蓋可觀察行為。無需提權建立 Windows symlink。

## 相容性與交付

新的使用者 Group Work ID 使用 v3 workflow／contract／evidence／snapshot；v1／v2 歷史不遷移。未完成舊 Work ID 經明確升級、新 plan 及全新審查／驗收。Skills SHA 不同即停止續作。Megin source 自身沿用受支持的 v1 `--repo` gate。

交付前執行所有核准檢查並保存原始輸出，交 fresh read-only context 審查，再交自動驗證；自動驗證通過後停在 `awaiting_user`。收到引用此 Work ID 與 acceptance version 的人工接受後，才可建立 feature commit 及本機 `--no-ff` merge。

## 驗證命令

所有命令在 Repo root 執行；原始結果各自存入同名核准 `evidence/*.log`。

- `python -X utf8 -B tests/group-workspace/test_workspace_hardening.py`
- `python -X utf8 -B tests/group-workspace/test_group_workflow.py`
- `python -X utf8 -B tests/quality-gates/test_quality_gate.py`
- `python -X utf8 -B tests/requirements-discovery/check_materials.py`
- `python -X utf8 -B tests/requirements-discovery/test_materials.py`
- `python -X utf8 -B tests/requirements-discovery/test_rules.py`
- `python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`
- `git diff --check`
