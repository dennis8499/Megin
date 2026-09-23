# WP-04 暫停與修正交接

- 已完成：來源及 ZIP 同步；六項核准本機命令 exit `0`；原始結果在 `evidence/commands/`；受保護快照為 `f35cba0f14a2158e7ed4a1d112c38bc32364cf3e4ee03fc77ae98d38bf90c01f`，`review` 結構關卡通過。
- 已驗證：全新唯讀 reviewer `/root/independent_quality_review` 對該快照回傳 `CHANGES_REQUIRED`；完整結果在 `evidence/review-1.md`。`acceptance` 結構關卡因缺少獨立核准而 exit `1`，所以不得進入人工驗收。
- 未完成／不確定：修正四項 review finding；Test/Test2 檔案多未追蹤，重播路徑引用未固定其內容雜湊；GitHub CI 未執行。token 無可靠計量，本工作段已達保守交接點，不聲稱精確額度。
- 下一步：先加入四項反例測試，再修正 `quality_gate.py`：縮小流程紀錄排除、拒絕 `.`／`..` 與跨證據目錄引用、讓 `review` 驗證必要命令結果及原始來源、使 staging 後內容能與使用者接受的位元組一致並留可稽核證據。更新共用規則／交付 Skill，重建 ZIP；重跑六項命令，重建證據與快照；另請全新 reviewer 重新審查。只有 `APPROVED` 且同快照全部檢查通過，才進人工驗收。驗收前不 commit/merge。
