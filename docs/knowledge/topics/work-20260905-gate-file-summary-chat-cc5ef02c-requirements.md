# Human approval gates use file-first review

## requirements-claim

- 需求：所有需要人類在 Chat 核准的 Gate，都必須先將完整且不可變的審閱 payload 持久化為可直接開啟的檔案，再於 Chat 僅提供摘要、檔案連結、精確 identity 與核准提示。
