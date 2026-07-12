# Task 4 完成报告：指数历史起点证据展示

## 改动

- `src/etf_trading/nicegui_app/components/tables.py`
  - 为起点证据、证据来源、证据链接、检索日期、核验结果和证据说明提供中文表头。
  - 将第三方参考起点及其证据枚举值翻译为中文，同时保留完整 URL 供复制。
- `src/etf_trading/nicegui_app/pages/maintenance.py`
  - 为“核验指数历史起点证据”任务增加专用摘要：`已核验 N，第三方参考 N，仍未确认 N，拒绝 N`。
  - 将 `BASELINE_REFERENCED` 纳入非官方/不完整历史统计。
- `src/etf_trading/nicegui_app/state.py`
  - 市场快照保留目录中的起点证据元数据。
  - 在没有持久化覆盖记录时，根据目录证据推导历史完整性；行情就绪度保持独立。
  - 第三方参考与未核验起点禁止新开仓，但不改变行情“数据可用”状态。
- `src/etf_trading/nicegui_app/view_models.py`
  - 将 `BASELINE_REFERENCED` 计入非官方/不完整历史统计。
- 测试覆盖第三方参考起点的行情状态、禁止新开仓、陈旧持久化完整记录的降级、中文展示、专用维护摘要与汇总计数。

## RED

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-red
```

结果：4 failed，55 passed；失败项分别覆盖证据表头、第三方参考快照状态、维护专用摘要与汇总计数。

补充 RED：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py::test_table_displays_baseline_reference_evidence_in_chinese -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-detail-red
```

结果：1 failed；确认“证据说明”表头尚未本地化。

审查后 RED：

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_app_import.py::test_market_snapshot_downgrades_persisted_complete_coverage_for_third_party_baseline -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-coverage-red
```

结果：1 failed；确认当持久化记录仍为 `COMPLETE`、目录已为第三方参考时，快照必须降级为 `BASELINE_REFERENCED`。

## GREEN

```powershell
$env:PYTHONPATH='H:\pythonproject\etf0614\etf0614\src'
& 'H:\pythonproject\etf0614\etf0614\.venv-win\Scripts\python.exe' -m pytest tests\test_nicegui_table_display.py tests\test_nicegui_app_import.py tests\test_nicegui_view_models.py tests\test_nicegui_maintenance_tasks.py -q --basetemp C:\Users\cjj\AppData\Local\Temp\baseline-ui-green
```

结果：76 passed in 1.50s。

另已执行 `git diff --check`，无空白错误。

## 提交

- 提交信息：`feat: show index baseline evidence`
- 提交范围：Task 4 指定源码、测试与本报告；未暂存用户已有的报告、规格或 `pytest-tmp-*` 文件。

## 顾虑

- 当前基线证据解析器不会产生 `REJECTED` 结果；维护摘要已按该状态保留计数位，以便未来解析器产生明确拒绝结果时仍保持准确。
- 表格使用完整外部 URL 文本，满足可复制要求；未修改 NiceGUI 表格单元格渲染为链接组件。
- 审查发现陈旧 `COMPLETE` 覆盖记录可能放宽第三方起点的交易准入，已用回归测试覆盖并修复：第三方目录证据始终覆盖持久化完整性状态。
