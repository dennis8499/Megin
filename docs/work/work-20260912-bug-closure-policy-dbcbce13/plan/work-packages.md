# 工作包：BUG 結案處置規則 v2

## DAG

`WP-001 → WP-002 → WP-003`

## WP-001 — Status contract 與安全 validator

- Files：`.agents/skills/bug-diagnosis/references/closure-status.schema.json`、`.agents/skills/bug-diagnosis/scripts/bug_status.py`、`.agents/skills/bug-diagnosis/scripts/test_closure_status.py`、`.agents/skills/bug-diagnosis/scripts/validate_contracts.py` 的 additive owner checks。
- Consumes：`bug-assessment/v1` path／hash與既有 stable no-follow primitives；produces：`bug-closure-status/v1` schema、strict status parser、fixed/pending negative matrix。
- BDD／TDD：BDD-001 → TEST-001；先確認 schema／duplicate／redirect／assessment binding red，再 minimal green，再 focused/full。
- 完成：無未知 nested field、無 path/hash drift、無 missing verification default、partial overclaim 與 fixed false-positive 全 fail closed；既有 `bug-assessment/v1` tests 不變。

## WP-002 — Blocker、risk、reviewer、timebox 與 policy reference

- Files：`.agents/skills/bug-diagnosis/references/closure-policy.md`、`SKILL.md`、`references/behavior-evaluation.md`、owner test／schema tests。
- Consumes：WP-001 validator；Human Gate、Delivery ledger、fresh reviewer contracts；produces：blocker／risk／reviewer／platform／timebox invariants與EVAL-BUG-009 closure status case。
- BDD／TDD：BDD-002 → TEST-002；合法 environment／contract blocker、High/Critical dual approval、same reviewer、跨平台缺口與 dates。
- 完成：不增加第三道 Gate；任何 blocked／partial／accepted-risk 都不宣稱 fixed/resolved；歷史 policy／assessment bytes 不被修改。

## WP-003 — Multi-BUG report、16 項初始盤點與 cross-platform evidence

- Files：`bug_status.py` report path／rendering、16 個 `docs/bugs/<bug-id>/status-1.json`、`docs/bugs/status-reviews/work-20260912-bug-closure-policy-dbcbce13.json/.md`、相關 owner／integration tests。
- Consumes：WP-002 policy；現有 16 個 assessment pairs、BDD-016 performance evidence、既有 Windows/Linux workflow；produces：每 BUG current record、unresolved summary、append-only report。
- BDD／TDD：BDD-003 → TEST-003；revision chain／scope isolation／outlier preservation／cleanup，再執行 local full 與 Windows/Linux CI。
- 完成：16/16 records 都有 assessment binding、owner、next action、due date與 evidence-pending；report 可重算且不修改歷史 bytes；超標 sample hash仍存在；跨平台差異明列而不升級結案。

## Blocker frontier

若 WP-001 發現既有 assessment stable-read 不能安全重用，停止並回報 `contract-blocked` 的技術規劃缺口，不複製第二套 reader。若 WP-002 發現 Human Gate 欄位不足，保留既有 Gate 並建立新 Plan revision，不回寫歷史。若 WP-003 缺 Linux hosted runner，保留 `environment-blocked` evidence 與 owner／期限，local result 不能代替 release evidence。
