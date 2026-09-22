# Megin 需求文件模板

`requirements.md` 是本次 Work ID 的需求內容唯一主檔。小工作使用基本欄位；只有研究、能力或決策較多時
才展開表格或另建 `research.md`。控制鍵與識別碼保持英文，人類可讀內容依 language policy 使用繁體中文。

```markdown
# 需求：<title>

- work_id: <work-id>
- requirements_revision: req-1
- language: zh-TW

## 目的與邊界
目標、受眾、納入行為、排除行為、假設與風險。

## 來源（需要時）
| ID | 名稱或路徑 | 候選研究版本 | 已決定目標版本 | 定位 | 查證日期 | 確定性 | 未驗證 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SRC-001 | <source> | <candidate version> | <target version or undecided> | <locator> | YYYY-MM-DD | confirmed | <none or gap> |

## 能力與範圍（大型或外部技術需求）
| ID | 層級 | 來源 | 可觀察結果 | 範圍決定 | 情境 | 未解問題 |
| --- | --- | --- | --- | --- | --- | --- |
| CAP-001 | upstream/integration/application | SRC-001 | <result> | include/exclude/defer/undecided | SCN-001 | Q-001 |

## 決策與假設
| ID | 決策或假設 | 依賴 | 狀態 | 影響 |
| --- | --- | --- | --- | --- |
| Q-001 | <decision> | <prerequisite> | open/decided/deferred | blocking/non-blocking |

## 非功能需求（需要時）
工作負載、延遲或吞吐、可用性、失敗處理、安全、資料生命週期、可觀測性及限制；區分需求與實作設計。

## 驗收
以 `SCN-*` 建立穩定的 Given/When/Then 情境，並標示 automatic 或 manual-only。

## 探索缺口與完成判定
列出未解問題、矛盾、來源限制、延後理由與處理時機；說明是否仍阻礙 planning。
```

研究內容較多時，`requirements.md` 保留來源 ID、摘要、能力範圍與參照，另建 `research.md` 保存來源快照、
長摘要與查證證據。`workflow.md` 只引用 revision、主檔與阻礙，不複製需求內容。
