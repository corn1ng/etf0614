# ETF Trading System

Repository initialized for the ETF trading workbench.

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
