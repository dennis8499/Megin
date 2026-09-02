<!-- authority: requirements-delivery -->

# 需求探索交付協定

本文件唯一擁有文件狀態、Candidate 展示、建議路徑、寫入授權與 Ready handoff。只在探索停止、索取成果、要求實作或品質通過時完整讀取，每次走一個分支。

## 文件狀態

- `Draft—Not ready`：仍有可繼續釐清的實質缺口、矛盾或不可驗收內容。
- `Blocked`：關鍵決策者、必要事實、一手來源或適格審查者不可得。
- `Candidate—Awaiting confirmation`：全部適用品質檢查通過，完整內容等待確認。
- `Ready`：品質通過，且使用者確認完整內容與精確路徑；可交給技術規劃。

同一文件同時只有一個狀態。探索答案與一般寫檔要求不改變狀態。

## 建議路徑

依序使用本次指定路徑、專案治理設定、`docs/requirements/YYYY-MM-DD-<topic>.md`。`topic` 是二至五個 lowercase ASCII kebab-case words。展示前檢查占用；已存在則使用最小 `-2`、`-3` 後綴，保留原檔。

## Candidate 分支

1. 完整讀取 [文件模板](requirements-analysis-template.md)。
2. 若delivery record含required knowledge overlay，使用`project-knowledge` requirements stage builder把正式Requirements與`required` claim page／sidecar／index組成同一sealed Candidate；若證據判定不需更新Wiki，則明列`decision: no-change`，仍將Requirements、精確promotion log與Ready receipt封入同一Candidate。以預期actor與stable evidence token建立prospective binding（不是預先核准），展示全部精確postimages、diff、payload digest與paths；不得另問第三次核准。Legacy或明列bootstrap exception維持單一文件Candidate。
3. 在對話中展示完整 `Candidate—Awaiting confirmation` 文件、knowledge diff（若適用）與精確建議路徑。
4. 以本回合唯一問題詢問是否確認該完整版本並同意寫入所有列出路徑。

完成條件：使用者已看到完整 bytes 與精確路徑，只收到一個確認問題，filesystem 尚未改變。

下一輪：

- 明確確認同一版本與路徑：再次確認路徑仍不存在；required overlay只可用同一approval evidence套用sealed Candidate，使Ready Requirements與knowledge postimages一起寫入，full lint與Ready promotion receipt成功後才進Planning。Legacy只改狀態與確認者後以 create-only 寫入 `Ready`。
- 路徑被占用：選最小後綴，重新展示路徑並單獨確認，本輪不寫。
- 內容修改：重跑品質，完整展示新 Candidate，再確認。
- 回覆含糊：只重新確認，本輪不寫。

Ready 完成條件：磁碟 bytes 除狀態／確認者外與核准 Candidate 相同，path 是已確認且先前不存在的路徑；required overlay另有相同approval evidence的`knowledge-promotion/v1` Ready receipt與passed lint，文件才可直接交給 Planning。

### BUG overlay

只有caller提供schema-valid、verdict為`confirmed | likely`的assessment Candidate時適用。Candidate分支同時按精確paths完整展示assessment Markdown、`bug-assessment/v1` sidecar與Requirements；仍只問一次既有Requirements確認。下一輪明確核准時，delivery／requirements writer以create-only一次寫入三者，重算Markdown／JSON／Requirements hashes，並在同一transition綁定相同approval evidence。

Assessment是診斷evidence，不取代Requirements。`not-a-bug`若是期望行為改變，改走standard Candidate且不materialize bug delivery binding；否則不建立delivery。Collision、hash drift、秘密或敏感原文使整組不寫並重新配置／遮蔽後展示，不能部分寫入。

## 提前停止／目前成果分支

Frontier 可繼續時使用 `Draft—Not ready`；必要來源／角色不可得時使用 `Blocked`。依模板完整展示已確認內容、缺口、影響與下一個必要決策，並聲明不可作為無條件 Planning baseline。

需要寫入時，先完整展示版本與精確路徑，再以唯一問題取得針對該版本／路徑的同意；寫入後狀態仍是 Draft 或 Blocked。

完成條件：狀態忠實、缺口具體、沒有 Ready 聲明；任何寫入都有獨立且精確的展示與確認。

## 探索期間要求實作

文件未 Ready：把「繼續一次一題，或依提前停止分支交付目前成果」作為唯一問題，不開始產品實作。文件已 Ready：結束探索，把 Ready path與純 HOW decisions交給 Planning。

完成條件：未 Ready 沒有 Implementation mutation；Ready handoff包含唯一文件 path、狀態與仍待 Planning 決定的 HOW。
