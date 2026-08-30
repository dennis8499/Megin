<!-- authority: execution-resume-revision -->

# Resume 與 Revision 契約

只在canonical worktree已有binding，或Ready／source bytes相對既有run改變時載入。

## Resume

由 bindings/worktree_key/binding.json取得run_id與initial_base_sha，不從目前plan或HEAD猜測。驗證binding、Ready/source hashes、目前Git狀態與最後snapshot。保留首次baseline；在含executor changes的workspace不重建它，依Ledger最後合法state執行下一個required action。

完成條件：continuity可由base、binding、append-only histories與snapshot證明；不可證明時Blocked且不修改產品。

## Unapproved drift

Ready/source hash改變時，先把目前attempt終止為Awaiting upstream reapproval。沒有新Ready approval時只保存provisional impact，不改WP、evidence或breaker。

完成條件：舊attempt與evidence保持不變，產品不再寫入，handoff明確列出上游需重新核准的bytes與outcome。

## Approved WP-local revision

只有 revision_impact全部為wp-local、planning head_sha等於initial_base_sha，且changed sources／contracts完整落在宣告impact內，才在同run追加attempt。Direct affected WP與DAG downstream轉Invalidated；舊evidence／review標superseded；未受影響WP只有source、input contract、snapshot與evidence全部相同才保留Verified。從最早invalidated WP續跑。

完成條件：invalidation closure完整、保留／superseded決策有hash evidence、首次baseline與binding不變。

## Global-baseline revision與Complete

BDD-FWK、BOOT global shape、Observed baseline、global command、cross-WP contract、planning base或無法證明完整的impact都是global-baseline；目前run保持Awaiting upstream reapproval，由orchestrator建立新worktree／base／run。Complete永遠凍結。

Finding counter只有source obligation／required outcome被新revision實質取代時標superseded；其餘延續。所有revision、attempt、evidence與binding只追加。

完成條件：revision唯一分類為wp-local或global-baseline，沒有在錯誤run重建baseline或重開Complete。
