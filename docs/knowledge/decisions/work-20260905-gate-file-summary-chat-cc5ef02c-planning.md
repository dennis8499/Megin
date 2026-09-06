# 人工核准 Gate 的 File-first 審閱架構

## planning-claim

- 選定方案與理由：重用既有 sealed Candidate 的 create-only postimage store，新增唯讀 review projection 與固定 Summary-only Chat contract；approval 仍綁 candidate ref 與 payload SHA，不新增第二套儲存或第三道 Gate。
