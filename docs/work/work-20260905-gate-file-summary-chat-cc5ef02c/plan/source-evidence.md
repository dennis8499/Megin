# Source evidence：人工核准 Gate 的 File-first 審閱

- Evidence revision：candidate-1
- 蒐集日期：2026-09-05
- Work ID：work-20260905-gate-file-summary-chat-cc5ef02c
- Repo ID：0c5534020993ce0e527ffefdd0bbbdf8e3e26138d3933defe22de1ed5ea2530c
- Planning baseline HEAD：6cf33bd5c0ef8a5658e3142ae1a6cc40d3c60de7
- Planning baseline status SHA-256：5a91e871cc09726a1a30b114ed8d2febecdfb35ee9107200f1bc58ee1a5bf45c

## 1. Observed architecture

1. knowledge_promotion.seal_candidate_draft 會先驗證完整 operations、source／preimage snapshot、secret 與 path 規則，再由 candidate registry create-only 保存 candidate.json 及逐項 postimages/*。完整 payload 因此已經 file-first；目前缺的是供人類 Gate 使用、可重驗且不含全文的 review projection。
2. knowledge_cli.py candidate 目前直接輸出 seal result，而 result 帶有完整 postimages 字串；bootstrap／lint 的 Candidate 分支沿用相同人類核准語意。這是 Summary-only Chat 的主要 leakage seam。
3. Requirements、Planning 與 Project Knowledge 的現行協定明文要求在 Chat 完整展示 Candidate 或 postimages；BUG assessment 與 Requirements 共用第一道 Gate；Delivery 的 requirements、planning、knowledge 三個 awaiting_user 邊界沿用這些 owner contract。
4. delivery-run/v1、ready-plan/v1、knowledge-candidate/v1、promotion receipt 及 apply transaction 已綁定 work／stage、candidate ref、payload SHA、approval evidence、preimage 與 create-only 寫入。選定方案可保留這些 state contract，不建立第二套 promotion store。
5. 本 repo 沒有 occurrence-map-template.yaml、occurrence-map schema 或 Spec Kitty mission metadata，且現行 trusted Planning bundle只接受 Markdown／JSON；本次 self-hosting bundle 因而以 occurrence_map.json 保存同一個八類完整分類契約，並由計畫要求未來 Gate 支援 doctrine 的 YAML filename，不假裝通過不存在的 runtime schema。

## 2. Observed verification surface

- Runtime：Python 3.14.6；測試使用標準庫 unittest 與既有 custom BDD runner，沒有新增 production／test dependency或網路需求。
- BDD discovery：test_behavior.py --list-scenarios 成功，baseline 共 19 scenarios、0 failed、0 skipped。
- Focused baseline：test_behavior.py --group governance --fixture-root .knowledge-test-tmp 成功，7／7 scenarios、0 skipped；fixture 已清除。
- Related baseline：run_full_suite.py --scope related --fixture-root .knowledge-test-tmp 成功；21 個 query／performance tests、23 個 workflow tests、4／4 related BDD，以及 Requirements、Planning、Implementation、BUG、Delivery owner validators 全部通過。
- Absence probe：rg -n "human-gate-review/v1|HumanGateReviewTests|candidate_review" .agents/skills 無命中；baseline 尚無共用 review schema、projection 或 focused inner-test class。
- Absence probe：rg --files . | rg "occurrence|bulk-edit" 無命中；baseline 尚無 repo-local occurrence map runtime。

## 3. Frozen source hashes

| Source | SHA-256 |
|---|---|
| docs/work/work-20260905-gate-file-summary-chat-cc5ef02c/requirements.md | 0be355804ca7ca0e0ddd3f7ef08b55d48342b41024d608fb2ef0e3bcc58db960 |
| .agents/skills/project-knowledge/scripts/knowledge_promotion.py | 2cec0ec9308d0d53c000cc5aeaa86f8fd8ef523c2f2e57dc5f51015f909ff12f |
| .agents/skills/project-knowledge/scripts/knowledge_cli.py | 0fb13bf50c1273b0681a5e6b047c03c7b1931a0b977ac8f24d2fba7de850fe09 |
| .agents/skills/project-knowledge/schemas/knowledge-contracts.schema.json | c9f684c87f3a75e1a440bc33162fd8ba115052d6cb37a5763303666d4552ba9e |
| .agents/skills/project-knowledge/SKILL.md | eb0423743321c988385a06e8f0fe9421475d364901846fb4498041544b05c60f |
| .agents/skills/requirements-discovery/references/delivery-protocol.md | f41d3100909a1032bb336e01de19580d7e8773eeeffa467b4e60de4433b47911 |
| .agents/skills/technical-planning/references/delivery-protocol.md | 1be600fc987bc77dad048f91ce23aecee52c404110deeec5f57964388f9f1ff6 |
| .agents/skills/delivery-orchestrator/references/stage-routing.md | 5329219b391f035cfe8a80c7ad1ce4d8a98babd49dd38e1ae2c08d8939a1ecf1 |
| .agents/skills/bug-diagnosis/SKILL.md | f6704a9823bdc84089afff4ac93ef03d0d48692a2c193d1ff90259f0cb2fd5c5 |
| .agents/skills/implementation-execution/references/delivery-protocol.md | 80adf7082d021fc2da2c5471633bd6f5ab5216fffd27d62279256464d81e9324 |
| .agents/skills/writing-great-skills/SKILL.md | 4d6ccbc3760b1bd4107c495a79872286ea69494003f3b0a719fc95b147457061 |
| .agents/skills/project-knowledge/scripts/test_behavior.py | bcdde03f8bb758e3be02ad076c31241c7902406b740cd0b8c10f7bff83478341 |
| .agents/skills/project-knowledge/scripts/test_workflow.py | d69a4e415260e83d8a97104bfe8d64186cb9f9b1731676c3298204cad7286689 |
| .agents/skills/project-knowledge/scripts/run_full_suite.py | 532062a432c8ad40c5768c3becda19d84bf1a950a981c3932624c38176432686 |

## 4. Planning conclusions

- Existing immutable Candidate store 是最高且穩定的 seam；新的 review index 應與 Candidate 原子封存，並由 apply／resume 前重新驗證，不應複製 canonical payload。
- Persisted review data只保存 allowlisted metadata、相對 stored paths、target paths、byte counts與 hashes；Chat adapter才投影直接可開啟的本機 paths。
- candidate_ref + payload_sha256 保持 promotion authority；新增 review SHA綁定完整 presentation manifest，owner在使用舊 approval前必須重驗。
- Active owner skills只保留 gate-specific inventory，完整 File-first／Summary-only contract放在單一 shared authority，避免跨 Skill duplication。
- Historical Ready、promotion receipt、delivery record與 raw automatic-gate evidence不需 migration；缺少新 review sidecar的 pending Candidate須以新 prospective evidence token重新 seal。
