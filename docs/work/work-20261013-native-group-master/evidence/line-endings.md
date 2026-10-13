# 提交前換行與封裝一致性

git add 依 .gitattributes 將 git_snapshot.py 的 CRLF 正規化為 LF。既有 ZIP 含 CRLF，因此工作目錄也轉為 LF 並重建 ZIP，避免 Linux checkout 後來源／套件驗證失敗。

- 唯一來源變更：git_snapshot.py 的 CRLF → LF。
- Python AST：ast.dump(ast.parse(before), include_attributes=True) 與 after 完全相同。
- 正規化後的檔案與暫存索引內容相同。
- 舊／新 ZIP entry 名稱集合相同，逐檔 bytes 比對僅 megin/scripts/git_snapshot.py 不同；差異正好為 CRLF → LF。
- 舊檔案 SHA-256：00a6535731ca428debd3a5f3e3de57eb674ba546a0283094d7cf8048cc549855。
- 新檔案 SHA-256：c733001854f03615276af0174560ef136301b1877d968872747b7b798a0b982f。
- Review 時 Skills SHA-256：edce77e62052fb7537c39bb2b6f8689dac92e4cc5d2ce1865d17fee2e12d583e。
- 提交用 Skills SHA-256：c274709a7f3bd809a1d70700a502124972d105514c4181acd9d3de20a7b5c3bc。
- 新 ZIP SHA-256：bcdf86e4bab0c2c04072950cfe0338f432060a3b6b7080f861b6142784968bb8。

`validate_skills.py --build-archive megin-skills.zip --archive megin-skills.zip` 通過全部 13 Skills；`python -X utf8 -B -m unittest test_skill_package -v` 兩項通過（0.077 秒，exit 0）。完整 92 項回歸與 round 3 Review 為正規化前相同程式語意的證據，不冒稱重新執行 Linux CI 或完整回歸。
