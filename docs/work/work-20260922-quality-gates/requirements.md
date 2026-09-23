# Megin 品質關卡改善需求

- work_id: work-20260922-quality-gates
- requirements_revision: req-1
- source: 使用者核准的「Megin 流程品質改善計畫 — plan-3」與本次實作指示
- ready_for_planning: true

## 目的與邊界

讓 Megin 的行為證據、獨立審查與驗證結果能在階段交接時被核對。受眾為使用 Megin Skills 交付軟體的 writer、reviewer 與驗收者。保留 Skills 與 Markdown 工作紀錄；小型唯讀檢查器只檢查確定性條件。

`Test` 與 `Test2` 僅提供已觀察缺口的最小案例，不修改其檔案。不建立通用測試 runner、流程控制器或新平台矩陣。

## 已決定能力與驗收

| 能力 | 決定 | 可觀察結果 | 情境 |
| --- | --- | --- | --- |
| 規劃與 TDD 證據 | include | 預期結果連到斷言；編譯錯誤不冒充行為 Red | QG-001 |
| 獨立審查 | include | 同一 writer 不核准自身變更；局部測試不冒充完整行為 | QG-002、QG-003 |
| 必要驗證關卡 | include | 失敗、受阻、零命中、跳過或未知不進入驗收 | QG-004 |
| 快照與交付 | include | 產品變更使舊核准失效；追加流程紀錄不造成循環失效 | QG-005 |
| checkpoint | include | 每個工作包留下完成、驗證、缺口及下一步 | QG-006 |
| 通用 runner／平台矩陣 | exclude | 沿用既有工具與 CI 設定 | — |

沒有待決的範圍、介面或驗收問題。腳本通過只代表證據結構一致；程式行為仍由測試與獨立 reviewer 判斷。
