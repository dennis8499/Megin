# WP-02 輸出定位的行為 Red／Green

- 承諾：測試結果若沒有指向原始輸出中的實際行，`acceptance` 關卡會拒絕。
- 斷言：`test_output_count_needs_a_locator_in_raw_log` 移除 `output.line`，要求 exit `1`。
- Red：快照 `5fdf5bc3b5c59b51a024d750d5664000ad17ecb28726aac4366f5c2bef4a0357`，命令 exit `1`，斷言顯示實際 exit `0`；原始結果見 `locator-red.log`。
- Green：加入來源行與文字檢查後，快照 `58fb2ff7e0682bb05df63239f6efd11384006b7e68103dd10c1a4457631750be`，同命令 exit `0`，10 tests passed；原始結果見 `locator-green.log`。
- 早期「缺少檢查器檔案」的失敗只屬 setup red，不能算上述行為 Red。
