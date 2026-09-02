---
name: technical-planning
description: 將已釐清的開發規格與專案證據轉成可核准的 Ready 技術計畫；在 Candidate 前攔截需求缺口、衝突與證據不足。用於實作前規劃；需求探索、直接實作與程式碼審查不適用。
---

<!-- authority: planning-entrypoint -->

# 技術規劃

把來源規格的 `WHAT` 與可引用的專案、治理及一手平台證據轉成可執行的 `HOW`。本入口是來源選擇、證據門檻、未知分類及 Candidate 路由的唯一權威。

## 邊界

- 規劃活動限於唯讀查證、對話中的 Candidate，以及核准後的規劃 artifacts。產品程式碼與外部狀態維持原狀。
- 來源規格決定行為；治理、ADR、現有公開契約與平台能力限制方案。明確限制優先，其餘選擇沿用有證據的專案慣例。
- 使用者核准完整 Candidate 與全部精確路徑後，唯一允許的寫入是[交付協定](references/delivery-protocol.md)所述的規劃 artifact set。
- 使用使用者的主要語言；秘密只描述取得機制或位置，不重現值。

## 1. 鎖定來源與證據

先執行 read-only 知識 preflight：

`python -X utf8 -B .agents/skills/project-knowledge/scripts/knowledge_cli.py query --repo . --stage planning --query "<目前規劃意圖>"`

保存 `knowledge-context/v1` 作為 source evidence，並在形成設計前重讀每個 result 的 `source_refs`。這個步驟不寫回 Wiki 或規劃 artifacts；typed dependency／contract error 使 evidence gate 保持 Blocked。只有 Ready BOOT plan 明列 skill 尚不存在時可使用其 bootstrap exception。

依序選取唯一來源規格：使用者明示來源、治理指定來源、工作區中唯一能對應成果的來源。若仍有多個合理候選，列出位置並只詢問使用者選擇來源。

擷取目標、範圍外、規範性需求、驗收、品質屬性、技術限制及相容／移轉條件。先讀適用的 `AGENTS.md` 與治理，再依影響範圍查證 README、詞彙、ADR、manifests、lockfiles、版本與入口、模組／資料／契約、測試、BDD framework、CI、支援環境與相關 Git 歷史；使用 `rg` 或 `rg --files` 定位。沒有應用程式碼是 greenfield 的 `Observed` 證據。

Bug run另讀取current approved `bug-assessment/v1` JSON與Markdown並重算hash；它只提供diagnosis evidence。Requirements仍決定WHAT；Planning在`bug_context`擁有root-cause／低信心假設、單一最小修法、regression seam與`verified | partial` target。

時效敏感或平台相關事實以官方文件、標準、上游原始碼或第一方 API 查證，記錄版本、日期與直接來源。每項主張只使用一種狀態：

- `Observed`：由專案或實際執行確認。
- `Required`：由來源規格或治理要求。
- `Proposed`：規劃選擇，尚未實作或執行。

建立 `需求 → 設計／BOOT → BDD → TEST → WP` 覆蓋圖。來源與規劃邊界唯一、每項會影響設計／測試／工作包的事實都有來源時，本階段完成。

## 2. 通過證據門檻

逐一將未知、矛盾或不可保證的要求分類，並只走一個分支：

1. `需求缺口`：會改變可見行為、範圍或驗收；交回 `requirements-discovery`，只詢問最高影響的一項決策。
2. `可研究事實`：以專案證據或版本化一手來源自行查證；新 BDD framework 必須證明與目標 runtime、runner、build、OS 及 CI 相容。
3. `技術決策`：呈現雙方證據、可行選項、取捨、影響與建議，只詢問目前最高影響的一項決策。
4. `必要證據不可得`：列出已查位置、缺失證據及受影響的設計、測試與工作包，進入 `Blocked`。

對每項 `Required` 驗收，先確認一手平台規範是否能在規格指定的全部環境保證該 oracle。若規範允許瀏覽器、OS、runtime 或外部服務抑制、忽略或改變必要行為，這是需求缺口；來源即使標示 `Ready` 也不得形成 Candidate。

規格、現有行為與治理衝突時，引用衝突雙方及受影響的需求、Modules、BDD／TEST 與 WP。只有不會改變設計、測試策略或工作包的事項可延後。

任一阻塞分支成立時，讀取[交付協定](references/delivery-protocol.md)並停在需求探索交接、單一技術決策或 `Blocked`；不要載入 Candidate references。所有需求缺口、矛盾與阻塞未知歸零時，本階段完成。

## 3. 形成 Candidate bundle

證據門檻通過後，完整讀取：

1. [Candidate 撰寫準則](references/candidate-authoring.md)
2. [技術規劃模板](references/technical-plan-template.md)
3. [`ready-plan/v1` 契約](references/ready-plan-contract.md)

依三者形成 current／target state、設計決策、Modules／Interfaces／Seams、可執行的 `BDD-FWK-*`／`BDD-*`、必要的 `BOOT-*`、內層 `TEST-*`、`CMD-*`、`WP-*` DAG、revision impact map、來源 manifest 與 `handoff.json`。Current state 只使用 `Observed`；新路徑、介面與架構使用 `Proposed`。

Bug Candidate另包含唯一`kind: bug` source、`purpose: bug-reproduction` command與conditional `bug_context`。可重現分支以original symptom與regression red為`verified` target；無法重現只可在reason、proxy red→green、residual risks與staging／人工follow-up完整時選`partial`。

模板內容完整、所有適用驗收可雙向追溯、`handoff.json` 符合 `ready-plan/v1`，且沒有阻塞未知時，本階段完成。

## 4. 驗證與交付

讀取[品質契約](references/quality-contract.md)，逐項二元檢查。失敗項回到擁有該規則的階段；必要證據或決策不可得時走 `Blocked`。

全部通過後讀取[交付協定](references/delivery-protocol.md)。該文件是 Candidate 展示、核准、安全寫入及交付狀態的唯一權威；依它在同一回合完成精確 artifact bytes、revision、hashes、digest 與 `handoff.json` 的序列化及完整展示。設計摘要不是終止狀態；命令全為有證據的 `Proposed` 也不妨礙形成 Candidate。本回合只能停在 `Blocked`、等待單一決策、`Candidate—Awaiting confirmation` 或已寫入的 `Ready`。

維護本 Skill 時才讀取[行為驗證契約](references/behavior-evaluation.md)，執行其開發期檢查器與全部案例；一般規劃不載入該文件。
