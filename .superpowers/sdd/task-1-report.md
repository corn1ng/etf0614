# Task 1 report: 数据质量层中文状态说明

状态：`DONE_WITH_CONCERNS`

## 修改

- 扩展 `assess_index_history_completeness`，以可选的 `index_code` 和
  `source_kind` 接收数据源事实，保持原有调用可用。
- 为 `BASELINE_UNVERIFIED`、`MISSING_HISTORY`、`COMPLETE`、`INCOMPLETE`
  生成包含实际日期、覆盖范围或数据源的中文说明；保留读取失败说明不变。
- 新增 `index_history_freshness_message`，统一把日期输出为 `YYYY-MM-DD`。
- 为上述五类用户可见说明添加回归断言。

## RED

命令：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-quality-red
```

结果：失败，测试收集阶段报出预期的
`ImportError: cannot import name 'index_history_freshness_message'`；共 1 个收集错误。

## GREEN

命令：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_index_support.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-quality-green
```

结果：`17 passed in 9.57s`。

## 完整测试套件

命令：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest -q --basetemp C:\Users\cjj\AppData\Local\Temp\index-status-quality-full
```

结果：`297 passed, 1 failed in 22.22s`。

唯一失败为 `tests/test_storage_and_services.py::test_ensure_index_history_marks_incomplete_when_verified_base_date_is_not_covered`：该 Task 2 依赖测试仍断言旧的 `INCOMPLETE` 文案（“本地仅从 … 开始”），而本任务规格要求的新文案是“当前仅有 … 起的数据。”。根据 Task 1 文件范围，未修改该测试，待 Task 2 一并更新。

## 提交与文件

- 提交：`feat: explain index history data status`
- 本任务暂存文件：
  - `src/etf_trading/data/quality.py`
  - `tests/test_index_support.py`
  - `.superpowers/sdd/task-1-report.md`

## 自审

- 新增参数均为可选关键字参数，旧调用保持兼容。
- `csi`、`shenwan`、`hk` 均有中文数据源标签；缺少指数代码或来源时安全回退到通用空响应说明。
- `READ_FAILED` 两个既有错误说明未改动。
- 仅暂存本任务文件；用户未提交的设计文档和 pytest 临时目录不纳入提交。
