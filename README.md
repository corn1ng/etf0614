# ETF Trading System

Repository initialized for the ETF trading workbench.

## 数据源配置

应用默认优先使用 Tushare；Tushare 缺少权限、接口不支持或调用异常时，会明确提示并自动回退到 AkShare。Token 只从进程环境变量读取，不要写入配置文件或提交到 Git：

```powershell
$env:TUSHARE_TOKEN = "你的 Token"
# 可选：覆盖默认代理地址
$env:TUSHARE_API_URL = "https://ts.gyzcloud.top/api"
```

未设置 Token 时，应用仍可通过 AkShare 工作，但任务和脚本会显示已回退告警。要执行真实代理的可选冒烟测试：

```powershell
$env:RUN_TUSHARE_SMOKE = "1"
.venv-win\Scripts\python.exe -m pytest tests\test_tushare_smoke.py -q
```

本项目是本地运行的 A 股 ETF 交易指引系统。第一版以 AkShare 为数据源，
使用 Streamlit 多 Tab 工作台、TradingView Lightweight Charts 风格 K 线、
本地 SQLite/Parquet 存储、趋势策略和回测模块。

## Research framework

Run candidate trend strategies over cached ETF Parquet data:

```bash
.venv/bin/python scripts/run_research.py --limit 20
```

The default candidates live in `configs/research.yaml`. Results are written to
`reports/research/research_results.csv` and `reports/research/candidate_ranking.csv`.
