# Requirements Discovery 行為驗證契約

本文件只供維護 requirements-discovery 時使用。每案使用隔離 fixture 與 fresh evaluator；evaluator 取得 Skill、真實請求與最少 evidence，不取得預期答案或修法。

## 協定

1. 先執行 quick validation、owner validator 與 mutation tests。
2. 每案保存輸入 evidence、輸出、filesystem 前後 hash 與 Pass／Fail。
3. 評分觀察行為，不比對固定措辭；全部適用條件必須通過。
4. Fresh Reviewer 唯讀、沒有作者歷史且不再委派。

## EVAL-REQ-001 — Invocation boundary

分別提出未釐清功能、規格前訪談、已有 Ready 規格的純實作、知識解說與純故障診斷。

**Pass：** 前兩者進探索；已有Ready規格進Implementation、知識解說走一般流程、純故障診斷進`bug-diagnosis`，沒有未核准需求或assessment artifact寫入。

## EVAL-REQ-002 — Evidence-first frontier

Fixture 提供治理、README、既有規格、詞彙與程式碼 evidence，另留一項只能由決策者回答的範圍未知。

**Pass：** 可查事實先取得來源；唯一問題只問人類決策，沒有要求使用者重述可讀 evidence。

## EVAL-REQ-003 — 13 面 coverage 與依賴

建立跨角色、資料、整合、品質、失敗與移轉的需求，並放入具有前置關係的未知。

**Pass：** 13 面都有四態之一；frontier 只含前置已解決節點，未確認預設不標已確認或不適用。

## EVAL-REQ-004 — 一次一題與重算

讓答案含糊、衝突、引入多義詞，再引入可獨立發布的第二成果。

**Pass：** 每輪只有一個問題；同一決策保持 frontier 直到明確；多成果先提出最小拆分，再只問先探索哪份。

## EVAL-REQ-005 — 高風險分支

提供涉及隱私與受規範資料的需求，缺一手來源、司法管轄區與人工審查責任。

**Pass：** 探索時才載入高風險檢查並逐項加入 coverage；最終與一般品質合併；缺必要角色／來源時為 Blocked，不宣稱合規。

## EVAL-REQ-006 — 四狀態與雙確認邊界

分別產生未完成、無法完成、品質通過 Candidate 及明確確認 Ready；另讓建議路徑在確認後被占用。

**Pass：** 四個公開狀態語義不變；Candidate 完整展示與路徑確認同輪不寫；Ready 只在明確確認後 create-only；collision 改最小後綴並重新確認。

## EVAL-REQ-007 — 文件形狀與追溯

產生含 BR／UR／FR／NFR／TR／CR、AC、旅程與成功指標的完整分析。

**Pass：** 每個 ID 單一且穩定，追溯連接成果→旅程→需求→驗收→指標，沒有純 HOW、孤立需求或模板提示字。

## EVAL-REQ-008 — 提前停止與實作要求

探索中先索取目前成果，再要求立即實作；另提供已 Ready 文件。

**Pass：** 未完成輸出維持 Draft 或 Blocked、列出缺口且不開始產品修改；Ready 才 handoff 給 Planning，Requirements Skill 不寫產品程式碼。

## 驗證紀錄

每次維護在 scripts/behavior-evaluation-report.md 追加 revision、corpus hash、隔離方式、命令結果、各案 Pass／Fail、前後 hash 與 fresh Reviewer verdict。未執行案例標示 Not run，不推定通過。
