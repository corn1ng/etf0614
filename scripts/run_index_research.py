"""Command-line runner for the locked index-trend V1 research package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etf_trading.research.index_report import run_and_publish_index_research


def main() -> None:
    parser = argparse.ArgumentParser(description="运行指数趋势基准策略 V1 回测")
    parser.add_argument("--config", default="configs/index_research.yaml")
    parser.add_argument("--parquet-root", default="data/parquet")
    parser.add_argument("--report-root", default="reports/index_research")
    parser.add_argument("--limit", type=int, default=None, help="仅用于确定性小样本冒烟运行")
    args = parser.parse_args()
    try:
        published = run_and_publish_index_research(
            config_path=args.config,
            parquet_root=args.parquet_root,
            report_root=args.report_root,
            limit=args.limit,
        )
    except Exception as exc:
        parser.exit(1, f"指数趋势回测失败：{exc}\n")
    print(f"指数趋势回测完成：run_id={published.run_id}，截止日={published.data_cutoff}")


if __name__ == "__main__":
    main()
