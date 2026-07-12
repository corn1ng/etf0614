import math

import pandas as pd

from etf_trading.backtest.engine import BacktestResult, Trade
from etf_trading.research.metrics import summarize_backtest, summarize_nav_by_year


def _result_with_completed_trade() -> BacktestResult:
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "nav": [1.0, 1.1, 1.05, 1.2],
            "weight": [0.0, 1.0, 1.0, 0.0],
        }
    )
    trades = [
        Trade(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-03"),
            action="BUY",
            price=10.0,
            weight_before=0.0,
            weight_after=1.0,
            signal_date=pd.Timestamp("2024-01-02"),
        ),
        Trade(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-05"),
            action="SELL",
            price=12.0,
            weight_before=1.0,
            weight_after=0.0,
            signal_date=pd.Timestamp("2024-01-04"),
        ),
    ]
    return BacktestResult(trades=trades, nav=nav, metrics={})


def test_summarize_backtest_reports_return_risk_and_trade_quality_metrics():
    metrics = summarize_backtest(_result_with_completed_trade())

    assert metrics["total_return"] == 0.2
    assert metrics["annualized_return"] > 1000
    assert metrics["volatility"] > 0
    assert metrics["sharpe"] > 0
    assert metrics["max_drawdown"] == -0.045455
    assert metrics["calmar"] > 0
    assert metrics["trade_count"] == 2
    assert metrics["closed_trade_count"] == 1
    assert metrics["win_rate"] == 1.0
    assert metrics["avg_trade_return"] == 0.2
    assert metrics["avg_holding_days"] == 2.0
    assert math.isclose(metrics["avg_exposure"], 0.5, abs_tol=0.000001)


def test_summarize_nav_by_year_produces_calendar_year_segments():
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2023-12-29", "2024-01-02", "2024-01-03", "2025-01-02"]),
            "nav": [1.0, 1.1, 1.0, 1.3],
            "weight": [0.0, 1.0, 1.0, 0.0],
        }
    )

    yearly = summarize_nav_by_year(nav)

    assert list(yearly["year"]) == [2023, 2024, 2025]
    assert yearly.loc[yearly["year"] == 2024, "total_return"].iloc[0] == -0.090909
    assert yearly.loc[yearly["year"] == 2025, "total_return"].iloc[0] == 0.0
