# 需求探索評測材料

本目錄是 Megin 需求探索的常設材料契約。它驗證案例、來源快照、最小 fixture、結果模板及參照的結構
完整性；它不執行模型、不評分自然語言內容，也不把靜態檢查成功解讀為模型已遵守探索協定。

## 執行

```text
python -X utf8 -B tests/requirements-discovery/check_materials.py
python -X utf8 -B tests/requirements-discovery/test_materials.py
```

`cases/cases.json` 是案例索引；`sources/manifest.json` 保存官方來源的 URL、適用版本、定位、查證日期與
快照 SHA-256；`fixtures/` 提供最小 repository 背景；`results/result-template.md` 是後續模型對照的空白結果
格式。Quartz、來源失效與恢復案例預定各跑三次，其餘案例各跑一次，由不同於回答產生者的評閱者依
`scoring-rubric.md` 判讀。這些模型評測在本 Work ID 尚未執行。

檢查器會拒絕重複案例 ID、feature 參照不存在、來源參照不存在、來源快照缺少必要欄位或 fixture 遺失。
它不會因為需求文字看似完整而放行，也不會取代 Megin 的人工需求探索與驗收閘門。
