<!-- authority: execution-state -->

# 實作執行交付協定

只有需要停止或交付時才讀取本文件。一次只走一個符合目前證據的分支。

## 唯一狀態機

[Machine representation](execution-records.schema.json)必須與下圖一致：

```text
Preflight → Executing → Verifying → Reviewing → Complete
                          ↓              ↓
                        Fixing ←─────────┘
                          └────────→ Verifying

任何未完成狀態 → Awaiting upstream reapproval | Blocked
```

另有 `Reviewing → Verifying` 只表示 snapshot drift，未先進入 Fixing。`Verifying → Fixing` 表示主代理 full command failure；`Reviewing → Fixing` 表示 Reviewer blocking finding。Fixing 使 affected WP `Invalidated → Executing → Verified`，再回 Verifying。

`Awaiting upstream reapproval` 與 `Blocked` 終止目前 attempt。只有 Preflight/Ledger 判定為同 run 可接受的已核准 WP-local revision，才在同一 Ledger 追加 attempt；global-baseline revision 使用新 worktree／base／run。`Complete` 永遠凍結 run。

終止狀態只有：

- `Complete`：主代理full verification通過；preliminary fresh report已實體綁定最新create-only Outcome；另一位final fresh Reviewer對含Outcome與Candidate的相同snapshot `APPROVED`，且已按terminal ordering保存。
- `Awaiting upstream reapproval`：Ready plan、BDD contract、來源或追溯需要上游修改並重新核准。
- `Blocked`：能力、Git、環境、baseline、Ledger、Reviewer 或進展式熔斷阻止可靠完成。

只有上述 schema states 可寫入 Ledger；中間說明不建立別名狀態。

## Complete

進入terminal ordering前必須依序完成：preliminary fresh response → create-only保存其report與全部raw outputs → 以run ID、logical ref、report path／hash及逐command output binding寫入最新連續Outcome revision → 封存Candidate → 另一位fresh Reviewer完成final review。`Complete`再依序發生：final Reviewer response received → 寫入前重算product與required knowledge snapshots且相同 → 原樣保存raw response／outputs／report → 保存後重算snapshots且相同 → append implementation `Complete`。Knowledge snapshot必須由sealed Candidate與完整Git-eligible knowledge tree重建，不接受caller自行宣告相等。前六步各寫一份有序`terminal/<sequence>-<step>.json` machine witness，最後的Ledger transition證明`complete_appended`。Machine ordering的`report_persisted`代表current round raw response、report宣告的每個raw output ref與schema-valid final report整組均已有可讀bytes；consumer validator以canonical run root驗證連續report chain、terminal index、capability／baseline、main command raw outputs與六個witness的精確集合，不接受phantom ref或只列部分outputs。最後transition使用[Ledger terminal index](preflight-and-ledger.md)逐一引用；任一步失敗走Reviewer契約的drift或`Blocked`分支，不先凍結run。

Implementation Ledger `Complete`不等於required delivery Complete。若delivery record有`knowledge_gate.policy: required`，主代理把Ledger、accepted review、`implementation-outcome/v1`、product snapshot與knowledge Candidate binding原子交給delivery，進`knowledge/active`；完整diff展示後進`knowledge/awaiting_user`。只有使用者核准且matching `knowledge-promotion/v1` Ready receipt、actual完整knowledge post-tree等於reviewed expected post-tree與post-apply full lint通過，delivery才可`complete/complete`。Legacy record沒有overlay時維持既有terminal transition。

交付回報：

- Ready plan path／revision、base SHA 與 run ID；
- 完成或 `Satisfied by existing implementation` 的 `WP-*` 摘要；
- 主代理完整 build／test／BDD／治理 commands 的結果；
- Preliminary與final Reviewer attestation、連續round、各自snapshot-before／after、獨立command outcomes與`APPROVED`；
- 非 blocking advisories；
- Ledger 的精確 path。
- BUG run 的assessment path／hash、`bug-verification/v1` path／hash、implementation verdict與獨立`verified | partial`結果；`partial`明示原始症狀未驗證、殘餘風險及staging／人工follow-up。

交付後被審內容與 Ledger 只讀；不自動 stage、commit、push、merge、部署、建立 ticket、清理 artifacts 或刪除 worktree。

BUG run若缺verification、結果為`failed`、review與verification雙結論不一致、verification evidence未實際保存並列入terminal index，或仍有未materialize的途中BUG evidence，均不得Complete。Legacy verification只在同一次`complete/complete` transition綁定；required overlay則在accepted review進`knowledge/active`時綁定並於promotion後重驗，更早綁定不得占用create-only path。Critical／high只改變優先與風險回報，不繞過gate；安全／隱私／資料風險只引用遮蔽摘要、安全evidence ref與具名人工reviewer。

## Awaiting upstream reapproval

列出：

- 有缺陷或已改變的 Ready／source refs、hashes 與 planning／execution base evidence；
- 缺少或衝突的 approval、manifest、BDD／BOOT／TEST／command／WP 或 revision impact contract；
- provisional 受影響 `WP-*` 與 downstream closure；
- 在重新核准前仍保持原狀、尚未標為 `superseded` 的既有證據；
- 上游需重新規劃及核准的可觀察結果；
- Ledger path。

Ready artifacts 維持唯讀。收到重新核准版本後由 Preflight/Ledger 判定：WP-local 在同 run 正式 invalidation 並追加 attempt；global-baseline 或已 Complete 使用新 worktree／base／run。

## Blocked

回報精確 blocker、首次與最近證據、已檢查項目、受影響階段、未執行的寫入，以及解除阻塞所需的能力或環境變化。若為熔斷，另列：

- 同一 finding 的三輪 report refs；或
- 兩輪無進展的 blocking counts、resolved transitions 與 decision evidence；
- 最後 snapshot 與 Ledger path。

解除 blocker 的唯一動作是取得所列能力／環境／決策後重新 Preflight；已 `Blocked` 的 attempt 保持 terminal，若 Ready／base／binding／reviewed bytes 連續性相同則在同一 run 追加 `Preflight` attempt，否則使用新 worktree／base／run。熔斷只能由已核准且實質取代 required outcome 的來源決策解除。測試、fresh Reviewer、dirty-state 與 Ready 唯讀門檻維持不變。

## 中途狀態請求

使用者只詢問進度時，依 Ledger 回報目前 state、最後完成 `WP-*`、下一個未阻塞工作包、最近命令證據與 Ledger path，然後在既有授權範圍內繼續。不要把中途狀態誤報為終止結果。
