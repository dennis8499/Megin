# 測試策略：BUG 結案處置規則 v2

此 supporting artifact 補充 `docs/work/work-20260912-bug-closure-policy-dbcbce13/plan/plan.md` 的測試契約。所有新命令在 planning baseline 均為 Proposed；`CMD-BUILD-FULL-001`、`CMD-TEST-FULL-001`、`CMD-GOVERNANCE-001` 沿用已存在的 repo 入口。測試輸出只可寫 `.knowledge-test-tmp/` 或 OS temporary directory；status records 與報告是 implementation 受治理 artifact，不由 validation command 直接覆寫。

## BDD／TDD case matrix

### BDD-001 / TEST-001：verification 與 disposition 分離

- Fixtures：合法 assessment pair；status records 分別缺 post-fix、regression green、full verification、reviewer、required platform；另有 `verification_result=partial`。
- Red：舊系統沒有 status contract／fixed gate；測試先以 `fixed-verified` 假陽性 assertion 取得正確 red，確認不是 runner、fixture 或 syntax failure。
- Green：`validate_status_record` 對每個缺口回傳 deterministic blocking code；partial 只能進 evidence-pending；未知／缺失 verification 不可默認 verified。
- Edge：duplicate JSON key、assessment markdown hash drift、status path traversal、redirected ancestor、unknown nested field、previous hash drift。

### BDD-002 / TEST-002：阻塞、風險與獨立審查

- Fixtures：environment-blocked 缺能力、contract-blocked 缺口、High accepted-risk 僅一位 approver、same reviewer identity、期限倒置、合法 dual approval。
- Red：缺 owner／due／escalation 或同一 reviewer 時，舊系統沒有 fail-closed status result。
- Green：blocker class 與 disposition 一致；High/Critical accepted-risk 至少兩個不同責任角色；reviewer 與 implementation owner 不同；T0+1、+3、+5、+10 日期順序可判定；合法資料通過。
- Edge：`accepted-risk`／`deferred` 仍不是 fixed；`rejected` 需 decision；environment-blocked 不輸出產品修復結論；跨平台缺一項只保留 partial/blocker。

### BDD-003 / TEST-003：多 BUG、append-only 與效能 outlier

- Fixtures：至少兩個 BUG 共用 work scope；每個 BUG 兩個 status revisions；一份 16 項 initial status corpus；一筆超標 sample 與一筆後續成功 rerun。
- Red：舊系統沒有 contiguous chain、scope isolation 或 outlier preservation oracle。
- Green：report 依 BUG 與 severity 穩定排序；每個 current record 的 previous path/hash 可重算；其中一 BUG 的 fixed／pass 不改另一 BUG；unresolved count 對六種非 terminal disposition 全計入；outlier raw hash 保留。
- Edge：revision gap、same BUG duplicate current revision、case-fold path collision、report input swap、untracked／fixture cleanup failure、Windows／Linux report shape不同。

## Command completeness

每個 focused command 要保存 scenario inventory、failed、skipped、not_run、exit code、stdout/stderr hash、environment identity；`CMD-BDD-DISCOVERY-001` 的 inventory 必須先完整。`CMD-BDD-FULL-001`、`CMD-TEST-FULL-001`、`CMD-GOVERNANCE-001` 不以成功摘要取代完整 child inventory。`CMD-CI-001` 需在 Windows 與 Linux workflow jobs 各產生 report，compare gate 只比較同一 schema／欄位，不將單平台通過升級成 fixed-verified。

## Required post-implementation artifacts

- `docs/bugs/<bug-id>/status-1.json`：16 個逐 BUG create-only current records，均引用現有 assessment JSON／Markdown hash；沒有目前 post-fix verification 時使用 `evidence-pending`，不寫 `fixed-verified`。
- `docs/bugs/status-reviews/work-20260912-bug-closure-policy-dbcbce13.json`：`bug-status-report/v1`，含每 BUG current path/hash、severity、verification result、disposition、owner、next action、due date、blocker class 與 counts。
- `docs/bugs/status-reviews/work-20260912-bug-closure-policy-dbcbce13.md`：給 reviewer 的 summary-only readable table；完整 evidence 留在原始 status／assessment／validation paths。
- 16 項 report 的 `unresolved_count` 只有在 validator 對所有 current records 與 chain 通過後才輸出；缺 records、hash drift 或 scope ambiguity 時報告為 error，不猜測數字。
