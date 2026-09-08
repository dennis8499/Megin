# 規劃來源與基準證據：本地 AI SDLC 速度改善

## 規劃身分

- Work ID：`work-20260907-workflow-speed-d0b3946d`
- Repository ID：`0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c`
- HEAD：`4e9558da8ac59db6fff32340d0fcc3504610143c`
- Planning status SHA-256：`31206f6bb0ba5bc541019277938b9827bdda674e38a0a64642cd9c82e9be51de`
- 目標本機：Windows、Python 3.14.6、Git 2.51.0.windows.1、ripgrep 15.2.0。

## 已觀察基準

- `python -X utf8 -B .agents/skills/project-knowledge/scripts/run_quick_checks.py`：2.589 秒，通過。
- `python -X utf8 -B .agents/skills/project-knowledge/scripts/run_full_suite.py --scope all --fixture-root .knowledge-test-tmp`：18/18 子命令通過，848.248 秒。
- `TEST-OWNER-DELIVERY-WORKSPACE`：435.985 秒；`BDD-FULL`：236.851 秒；兩者合計約占完整 suite 79%。
- `run_full_suite.py` 已實際包含 `BDD-FULL`、`BUILD-FULL` 與 `GOVERNANCE`，但現行 `ready-plan/v1` 沒有 command coverage graph。
- `reviewer-contract.md` 要求主代理、preliminary Reviewer 與 final Reviewer 都自行重跑完整 build、test、BDD 與治理命令。
- `execution-records.schema.json` 的 command outcome 尚無 executed／referenced provenance、producer identity 或 precheck contract。
- `knowledge_query._query_terms` 以 `[\w.-]+` 取詞，會把連續中文句子當成單一 token；指定兩個中文自然問題在規劃前沒有結果。
- Delivery 測試聚合器包含 performance 與多個 Git integration class；共用 fixture lifecycle 未提供 setup/body/cleanup 分段或 worker isolation contract。
- Delivery doctor 只輸出 phase duration 與 return count，尚未區分 active work、commands、review、human wait 與 interruption。

## Absence probes

- `rg -n -- '--profile|--evidence-root|--jobs' .agents/skills/project-knowledge/scripts/run_full_suite.py`：沒有 validation profile、原子 evidence bundle 或 parallel jobs 入口。
- `rg -n 'validation-plan/v1|coverage_edges' .agents/skills/technical-planning/references/ready-plan.schema.json`：沒有 validation extension。
- `rg -n 'provenance|precheck|producer_output_ref' .agents/skills/implementation-execution/references/execution-records.schema.json`：沒有 evidence reuse 欄位。
- `rg -n 'workflow-speed' .agents/skills/project-knowledge/scripts/test_behavior.py`：沒有本工作 BDD group。
- `.agents/skills/implementation-execution/scripts/validation_evidence.py` 與 `test_validation_evidence.py` 不存在。

## 相容及發布證據

- `.github/workflows/knowledge-portability.yml` 保留 Windows／Linux jobs 與 compare gate，可繼續作為 release profile 的跨平台權威。
- 新資料形狀採 additive capability block；缺少整組 capability 的既有 Ready plan、Outcome、review 與 run 仍走 legacy validation。
- 所有 benchmark 必須在同機、同版本、同 snapshot 類型下執行三次；報告分開呈現實測值與不可得原因，不由 Windows／Linux 歷史差距推估。
