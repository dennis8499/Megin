<!-- authority: bug-diagnosis-loop -->

# Tight diagnosis loop

本文件擁有 BUG 唯讀調查順序與假設紀律；artifact shape 由 [Assessment 契約](assessment-contract.md)擁有。

## 1. Signal

固定 observed／expected、精確輸入、環境、時間、頻率、影響與 oracle。Flaky／效能問題使用可重複取樣與分布，不以單次成功或失敗下結論；效能 regression 必須固定 workload、warm-up、樣本數與比較基準。

## 2. Reproduce or amplify

優先取得最短、最穩定且不改產品狀態的 reproduction。無法穩定重現時，提高觀測率：縮小輸入、增加受控重複、加入唯讀 trace、固定 seed／clock／concurrency 或比較同一 request 的正常與異常樣本。Probe 不得把環境、fixture、syntax、load 或 runner error誤認為症狀。

完成條件：status 是 `reproduced | intermittent | not-reproduced | not-attempted`，且每個主張有 command／observation evidence ref。

## 3. Minimize and compare

刪除與症狀無關的輸入、步驟、依賴與併發，直到再刪一項就失去訊號。比對：

- 最近正常與目前異常；
- 相同版本的正常與異常輸入／環境；
- 近期 commit、設定、dependency、資料 shape 或契約差異；
- 上游產生值、邊界轉換與下游消費值。

比較只列有 evidence 的差異，不把 correlation 寫成 root cause。

## 4. Trace backward

從可觀察失敗點反向追查資料與控制流：錯誤值在哪裡首次出現、誰建立、經過哪些轉換、哪個 invariant 首次破裂。優先在 boundary 記錄帶 tag 的輸入／輸出 digest；不得保存秘密或敏感 payload 原文。

## 5. Falsifiable hypotheses

Root cause 未被證明時列出 3–5 項，以 likelihood、解釋力與可測成本排序。每項固定：

- 單一 causal statement；
- 一個可控制變因；
- 若為真會看到的 prediction；
- 能使它被推翻的 falsifier；
- probe 與 evidence ref。

同時最多一個 `testing`。一次 probe 只改一個變因；不把多個 patch 疊在一起後看是否變綠。結果只能 `untested | testing | supported | falsified`；`supported` 不是 `confirmed`。

## 6. Root-cause confidence

- `confirmed`：受控 probe 能使 invariant／symptom 可預期地失敗與恢復，並排除合理替代原因。
- `hypothesized`：有一致 evidence，但尚未完成因果 pre/post 證明。
- `unknown`：目前 evidence 不能支持單一原因。

診斷失真、假設失敗或範圍擴大時更新 assessment；不提出第二個猜測 patch。修法、regression red、green 與 full verification交給核准 Planning／Implementation。

## 來源原則

本迴圈綜合 [Matt Pocock `diagnosing-bugs`](https://github.com/mattpocock/skills/blob/main/skills/engineering/diagnosing-bugs/SKILL.md) 的 tight loop／最小化／ranked hypotheses、[Superpowers `systematic-debugging`](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) 的 root-cause-first／single hypothesis、[OpenSpec overview](https://github.com/Fission-AI/OpenSpec/blob/main/docs/overview.md) 的 artifacts traceability，以及 [Spec Kit agentic bugfix](https://github.github.com/spec-kit/reference/agentic-bugfix.html) 的 assess／fix／test 與 partial verdict。這些來源提供方法原則；本 repository contracts 是 runtime 權威。
