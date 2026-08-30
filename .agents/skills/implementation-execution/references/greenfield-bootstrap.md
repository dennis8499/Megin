<!-- authority: execution-bootstrap -->

# Greenfield Bootstrap 契約

只在source manifest證明第一個public seam／必要entrypoint不存在，且Ready plan具有完整BOOT contract時載入。BOOT只建立讓oracle可觀察「尚未實作」的contract shape。

## Producer gate

BOOT contract精確列出paths、public declaration／signature、最小host wiring、deterministic Unimplemented sentinel／outcome、禁止行為、bootstrap command與第一個BDD／WP mapping。Sentinel與全部驗收結果互斥。

任一欄位缺失、放寬或無法證明互斥時，在production寫入前進入Awaiting upstream reapproval。

## First correct red

1. 先建立目前BDD scenario、bindings、fixture與獨立oracle，保存tracked／unignored snapshot。
2. Production diff只新增BOOT列出的shape；沒有領域分支、輸入轉換、規格輸出、runtime dependency、外部呼叫、network、persistence、state change或能滿足任一驗收的內容。
3. 執行CMD-BOOT build／load／discovery。只在核准shape內修正declaration／wiring；無法成功就回上游。
4. 保存command、raw output與前後diff，再執行focused BDD。Runner到達SEAM，fixture把sentinel當observed actual，report以assertion mismatch證明behavior缺失；load、exception、fixture、runner或environment error不算red。
5. 取得正確BDD red後，才由inner TDD最小green取代sentinel。後續scenarios各自仍需red。

Bootstrap已使scenario green、diff越界或sentinel可能等於驗收結果時立即Awaiting upstream reapproval。

完成條件：第一個production behavior發生在正確BDD red之後；red前production bytes只包含hash可核對的BOOT contract shape。
