<!-- authority: delivery-routing -->

# 階段路由契約

本文件只管理 phase handoff，不重述 requirements、planning 或 implementation 的內部規則。每次只載入目前 phase 的 Skill 與其按需 references。

## Requirements

1. 在 delivery worktree 完整讀取並遵守 `requirements-discovery/SKILL.md`；把使用者最初的落地請求與已確認後續決策視為來源。
2. 明示第一版輸出為 `docs/work/<work_id>/requirements.md`。既有檔不可覆寫；revision 使用 `requirements-2.md`、`requirements-3.md` 的最小可用後綴。
3. Candidate 完整展示後把 delivery status 設為 `awaiting_user`；核准前不寫 repository artifact。
4. 使用者明確核准內容與 path 後，由 Requirements Skill 寫入 Ready 文件；重算 SHA-256、保存 approval evidence ref，再以同一個 atomic transition 追加 current requirements ref 並進入 `planning/active`。
5. 只有這次 transition 新增或重新驗證 current Ready requirements revision 才能進 `planning`；不得沿用回流前的舊 current ref 跳過重新核准。

若對話中斷，host-temp evidence 保存非秘密決策、Candidate bytes ref 與 digest；無法重建使用者看過的精確 Candidate 時重新展示並核准，不假設已核准。

## Planning

1. 完整讀取並遵守 `technical-planning/SKILL.md`，明示 current Ready requirements path 為唯一來源規格。
2. 第一版 bundle root 是 `docs/work/<work_id>/plan/`；既有 artifact set 不覆寫，revision 使用 `plan-2/`、`plan-3/` 的最小可用後綴。
3. Candidate 完整展示後設 `awaiting_user`。只有使用者明確核准同一 revision、digest 與全部 paths，才由 Technical Planning 寫入 Ready bundle。
4. 重新讀取 `handoff.json`，以 Technical Planning producer 的完整 `ready-plan/v1` schema 與 cross-reference validator 驗證 approval、payload digest、contracts、commands、WP DAG、artifact／source hashes；所有本地 source 重新雜湊，非 bundle／requirements source 必須可由 recorded base 重建。全部 `sources` 中恰有一個 `kind: spec`，且它綁定 current requirements path／SHA。暫態或未追蹤 source 必須先成為 hash 相同的 `supporting` artifact，不能只留 location。
5. Ready plan approval 同時完成 orchestrator 的第二個人工 gate；以同一個 atomic transition 保存 current handoff ref 並轉 `implementation/active`，不再詢問是否開始。

Technical Planning 判定需求缺口時，保存 gap refs 並回 `requirements`；純技術決策維持 `planning/awaiting_user`。Blocked 不自行改上游 artifacts。

## Implementation

1. 先以 helper transition 保存 `phase: implementation, status: active`、current Ready requirements 與 handoff refs。
2. 完整讀取並遵守 `implementation-execution/SKILL.md`。該 Skill 仍是唯一產品 writer，並擁有 BDD／TDD、verification、fresh Reviewer、breaker 與 terminal ordering。
3. Implementation Preflight 只在 delivery record、worktree binding、Ready requirements ref 與 handoff `kind: spec` source 全部相符時，把 requirements file 視為允許的唯讀 dirty upstream input。
4. `Awaiting upstream reapproval` 回 `planning`；新需求決策再由 Planning 路由 `requirements`。WP-local revision 依 execution Ledger 留在同 generation；global-baseline 依 workspace contract建立下一 generation。
5. Implementation `Complete` 且 Reviewer snapshot 穩定後，先保存 child Ledger／review refs，再把 delivery 設為 `complete/complete`。

## Resume、Blocked 與交付

Resume 依 record 的 phase／status 與 current refs 進入最早未完成的 child action；不重跑已持久化的核准寫入或 Complete child run。

任一 child `Blocked` 時追加 blocker evidence，delivery phase 保持該 child、status 設 `blocked`。能力或決策恢復後另追加解除證據，再回同 phase `active`；不覆寫原 blocker。

每次交付至少回報：`work_id`、generation、worktree／branch、phase／status、current requirements／handoff／implementation refs、下一個 action、run record path。Complete 另回報 fresh review verdict 與未提交 diff，且不 stage、commit、push、merge、deploy 或 cleanup。
