# Task 2 Report: 持久化指数历史状态说明

## RED

先在 `tests/test_storage_and_services.py` 添加了精确的陈旧行情和空响应回归测试，并更新唯一仍断言旧 `INCOMPLETE` 文案的测试。

执行：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-service-red
```

结果：`11 passed, 2 failed`，失败原因与预期一致：

- `STALE` 仍返回“本地最新交易日…未达到目标交易日”的技术短语；
- `EMPTY` 的 `IndexHistoryResult.error_message` 为 `None`。

## GREEN

- `InitializationService` 复用 `index_history_freshness_message()` 生成 `STALE` 说明，并同时写入结果和 `data_update_state.error_message`。
- 指数目录的 `index_code`、`source_kind` 现传给完整性评估；空响应能得到 Task 1 定义的带数据源与代码的说明。
- `EMPTY` 保持原有状态，但将同一说明写入结果、`completeness_message` 与 `data_update_state.error_message`。
- 历史覆盖测试改为 Task 1 定义的 `当前仅有 … 起的数据。` 文案。

聚焦回归：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_storage_and_services.py tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-service-green-final
```

结果：`30 passed`。

完整套件：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-service-full-final
```

结果：`300 passed`。

## 提交

`feat: persist index history status explanations`（本报告随同该任务提交）。

## 自审

- `git diff --check` 无空白错误。
- 仅将 `src/etf_trading/data/initialization.py`、`tests/test_storage_and_services.py` 与本报告纳入提交；未触碰用户已修改的设计文档或临时测试目录。
- `EMPTY` 测试同时断言结果、完整性说明和更新状态的 `error_message` 相同；`STALE` 测试也断言结果与更新状态相同。
