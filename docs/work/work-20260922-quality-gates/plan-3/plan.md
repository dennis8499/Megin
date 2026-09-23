# Megin 品質關卡改善計畫 — plan-3

- work_id: work-20260922-quality-gates
- plan_version: plan-3
- requirements_revision: req-1
- base_branch: main
- base_commit: 0ed737bb4cc3c9e1bb04f820f14694ee9ed7324c
- feature_branch: feature/work-20260922-quality-gates
- merge_strategy: --no-ff
- delivery_target: base_branch
- approval: 使用者以「PLEASE IMPLEMENT THIS PLAN」明確核准本 Work ID 的 plan-3

## 核准範圍

建立共用品質協定、唯讀 `quality_gate.py`、最小反例與正常案例，並讓相關 Skills 引用同一規則。允許 `.agents/skills/megin*/` 中與品質交接直接相關的來源、`tests/quality-gates/`、本 Work ID、`README.md`、`OPERATIONS.md`、既有 CI 與 `megin-skills.zip`。禁止修改其他 Work ID、`Test`、`Test2`、安裝副本或正式知識。知識結果預定為 `no-change`。

## 工作包與驗收

| 工作包 | 依賴 | 結果與證據 |
| --- | --- | --- |
| WP-01 共用規則 | — | 各階段引用同一交接與快照規則；QG-001、QG-002、QG-006 |
| WP-02 檢查器 | WP-01 | 缺證據、非通過、零命中、漂移受阻；正常案例通過；QG-004、QG-005 |
| WP-03 Skills 連接與重播 | WP-02 | 局部測試、自審及編譯型 Red 被辨識；QG-001～QG-004 |
| WP-04 封裝與交付準備 | WP-03 | 文件、CI、ZIP 與來源一致；獨立 review、驗證、人工驗收 |

核准的自動命令：`python -X utf8 -B tests/quality-gates/test_quality_gate.py`、`python -X utf8 -B tests/requirements-discovery/check_materials.py`、`python -X utf8 -B tests/requirements-discovery/test_materials.py`、`python -X utf8 -B tests/requirements-discovery/test_rules.py`、`python -X utf8 -B .agents/skills/megin/scripts/validate_skills.py --archive megin-skills.zip`、`git diff --check`。行為重播另保存各案原始結果與獨立評閱，不以靜態測試替代。

## 結果與斷言對應

| 情境 | 要保護的結果與關鍵斷言 | 證據／命令 | 必要環境與失敗情境 |
| --- | --- | --- | --- |
| QG-001 | 編譯錯誤不能充當行為 Red；reviewer 應指出測試根本未執行 | `Test` Red 重播、`evidence/locator-red.log`／`locator-green.log` | 唯讀 `Test`；區分 setup failure 與斷言 failure |
| QG-002 | 自審或缺少 review 時 `acceptance` exit `1` | `test_self_review_and_missing_review_stop_acceptance`，品質測試命令；`Test` review 重播 | 本機 Python、Git；writer/reviewer 相同或無結果 |
| QG-003 | 設定或局部替身不能證明 recovery、Kafka 完整流程 | `Test2` SCN-003／SCN-009 的獨立唯讀重播 | 唯讀 `Test2`；Docker 不可用須如實保留 blocked |
| QG-004 | failed、blocked、not_run、零命中、跳過、無定位輸出均阻擋驗收 | `test_failed_blocked_skipped_and_zero_tests_stop_acceptance`、`test_output_count_needs_a_locator_in_raw_log`，品質測試命令 | 本機 Python、Git；不得把未知結果改判通過 |
| QG-005 | staged、刪除、untracked、契約漂移使舊快照失效；純追加紀錄不使其失效 | `test_product_drift_including_untracked_file_stops_review`、`test_staged_change_and_deletion_change_snapshot`、`test_changed_cited_report_or_contract_stops_gate`、`test_new_process_record_keeps_product_snapshot`，品質測試命令 | 暫存 Git repo；相關引用檔被改寫亦須拒絕 |
| QG-006 | 後續人員能讀出完成、驗證、缺口與下一步 | `workflow.md` 的 WP checkpoint、writer handoff；人工驗收 | 可讀的本 Work ID 紀錄；欄位不完整則不得聲稱可恢復 |

`tests/requirements-discovery/test_materials.py` 與 `test_rules.py` 是已存在的有效回歸腳本；繼續執行核准命令，不製造新 Red。自訂腳本若只輸出成功行，證據以一次實際執行且具有斷言的腳本計數，不捏造測試框架的案例數。正常案例另由 `test_complete_evidence_passes_all_three_gates` 保護。所有實際執行輸出與 exit code 必須保存，未執行的 CI 不能標為通過。

`quality-contract.json` 是上述核准路徑、命令與明確流程紀錄路徑的機器可讀附錄。只有列入 `process_records` 的精確檔案可排除於產品摘要；相同目錄中的其他測試或 fixture 仍受保護。任何變更其義務、範圍或命令都須依本計畫重新核准；品質證據不得自行改寫它。

同一 writer 依序執行工作包。每包先讀目標檔、呼叫者與共用規則，完成後記錄已完成、已驗證、缺口與下一步。使用者於 2026-09-23 明確指示忽略 token 計費與額度，本計畫不再以 token 用量停止工作。產品或契約漂移依 branch policy 重新審查、驗證及人工驗收。使用者驗收前不提交或合併；驗收後在本機以 feature commit 與 `--no-ff` merge 交付。
