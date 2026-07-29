from __future__ import annotations

import math

import pandas as pd
import pytest

from etf_trading.research.index_metrics import summarize_index_result, summarize_nav_by_year
from etf_trading.research.index_models import IndexBacktestResult, IndexBacktestTrade


def result_with_nav(values: list[float], *, weights: list[float] | None = None) -> IndexBacktestResult:
    return IndexBacktestResult(
        nav=pd.DataFrame(
            {
                "trade_date": pd.date_range("2024-01-02", periods=len(values), freq="B"),
                "nav": values,
                "weight": weights if weights is not None else [0.0] * len(values),
            }
        )
    )


def trade(
    action: str,
    trade_date: pd.Timestamp,
    price: float,
    *,
    commission: float = 0.0,
    reason: str = "fresh_upper_band_breakout",
) -> IndexBacktestTrade:
    return IndexBacktestTrade(
        index_code="000300",
        signal_date=trade_date,
        trade_date=trade_date,
        action=action,
        execution_price=price,
        weight_before=0.0 if action == "BUY" else 1.0,
        weight_after=1.0 if action == "BUY" else 0.0,
        commission=commission,
        delay_days=0,
        reason=reason,
    )


def result_with_round_trip(
    *,
    entry_index: int,
    exit_index: int,
    entry_price: float = 100.0,
    exit_price: float = 97.0,
    entry_commission: float = 0.0,
    exit_commission: float = 0.0,
    exit_reason: str = "normal_lower_band_exit",
    dates: pd.DatetimeIndex | None = None,
) -> IndexBacktestResult:
    dates = dates if dates is not None else pd.date_range("2024-01-02", periods=max(exit_index + 1, 2), freq="B")
    nav = pd.DataFrame({"trade_date": dates, "nav": [1.0] * len(dates), "weight": [0.0] * len(dates)})
    return IndexBacktestResult(
        nav=nav,
        trades=[
            trade("BUY", dates[entry_index], entry_price, commission=entry_commission),
            trade("SELL", dates[exit_index], exit_price, commission=exit_commission, reason=exit_reason),
        ],
    )


def test_drawdown_episode_reports_peak_trough_and_recovery():
    metrics = summarize_index_result(result_with_nav([1.0, 1.2, 0.9, 1.2]))

    assert metrics["max_drawdown"] == -0.25
    assert metrics["drawdown_start"] == "2024-01-03"
    assert metrics["drawdown_trough"] == "2024-01-04"
    assert metrics["drawdown_recovery"] == "2024-01-05"
    assert metrics["drawdown_recovered"] is True
    assert metrics["recovery_trading_days"] == 2


def test_losing_round_trip_within_twenty_trading_days_is_whipsaw():
    result = result_with_round_trip(entry_index=2, exit_index=12, entry_price=100, exit_price=97)

    metrics = summarize_index_result(result, whipsaw_max_holding_days=20)

    assert metrics["whipsaw_trade_count"] == 1
    assert metrics["whipsaw_trade_rate"] == 1.0
    assert metrics["whipsaw_trade_denominator"] == 1


@pytest.mark.parametrize(
    ("holding_days", "expected_whipsaws"),
    [(20, 1), (21, 0)],
)
def test_whipsaw_holding_limit_uses_inclusive_trading_day_boundary(holding_days, expected_whipsaws):
    result = result_with_round_trip(entry_index=0, exit_index=holding_days)

    metrics = summarize_index_result(result, whipsaw_max_holding_days=20)

    assert metrics["whipsaw_trade_count"] == expected_whipsaws


def test_whipsaw_holding_period_uses_trading_index_not_calendar_days():
    dates = pd.DatetimeIndex(["2024-01-02", "2024-02-01", "2024-06-03", "2025-01-02"])
    result = result_with_round_trip(entry_index=1, exit_index=3, dates=dates)

    metrics = summarize_index_result(result, whipsaw_max_holding_days=2)

    assert metrics["whipsaw_trade_count"] == 1
    assert metrics["avg_holding_days"] == 2.0


def test_round_trip_that_loses_only_after_costs_is_a_whipsaw():
    result = result_with_round_trip(
        entry_index=0,
        exit_index=1,
        entry_price=100.0,
        exit_price=100.1,
        entry_commission=0.001,
        exit_commission=0.001,
    )

    metrics = summarize_index_result(result)

    assert metrics["avg_trade_return"] < 0
    assert metrics["whipsaw_trade_count"] == 1
    assert metrics["cost_drag"] == pytest.approx(0.002)


def test_open_round_trip_is_excluded_from_completed_trade_and_whipsaw_denominators():
    result = result_with_round_trip(entry_index=0, exit_index=1)
    result = IndexBacktestResult(nav=result.nav, trades=[result.trades[0]])

    metrics = summarize_index_result(result)

    assert metrics["trade_count"] == 1
    assert metrics["closed_trade_count"] == 0
    assert metrics["whipsaw_trade_denominator"] == 0
    assert metrics["whipsaw_trade_rate"] == 0.0


def test_no_completed_trade_has_zero_quality_metrics_and_explicit_whipsaw_denominator():
    metrics = summarize_index_result(result_with_nav([1.0, 1.1]))

    assert metrics["closed_trade_count"] == 0
    assert metrics["win_rate"] == 0.0
    assert metrics["whipsaw_trade_count"] == 0
    assert metrics["whipsaw_trade_denominator"] == 0
    assert metrics["whipsaw_trade_rate"] == 0.0


def test_empty_single_constant_and_unrecovered_nav_are_safe():
    empty = summarize_index_result(IndexBacktestResult())
    single = summarize_index_result(result_with_nav([1.0]))
    constant = summarize_index_result(result_with_nav([1.0, 1.0, 1.0]))
    unrecovered = summarize_index_result(result_with_nav([1.0, 1.2, 0.9, 1.0]))

    for metrics in (empty, single, constant):
        assert metrics["total_return"] == 0.0
        assert metrics["annualized_return"] == 0.0
        assert metrics["volatility"] == 0.0
        assert metrics["sharpe"] == 0.0
        assert metrics["calmar"] == 0.0
    assert unrecovered["drawdown_recovered"] is False
    assert unrecovered["drawdown_recovery"] is None
    assert unrecovered["recovery_trading_days"] is None


def test_trade_quality_cost_and_atr_reentry_metrics_are_reported():
    result = result_with_round_trip(
        entry_index=0,
        exit_index=2,
        exit_price=110.0,
        entry_commission=0.001,
        exit_commission=0.0011,
        exit_reason="atr_emergency_exit",
        dates=pd.date_range("2024-01-02", periods=5, freq="B"),
    )
    result.trades.extend(
        [
            trade("BUY", result.nav["trade_date"].iloc[3], 105.0),
            trade("SELL", result.nav["trade_date"].iloc[4], 106.0),
        ]
    )

    metrics = summarize_index_result(result)

    assert metrics["trade_count"] == 4
    assert metrics["closed_trade_count"] == 2
    assert metrics["win_rate"] == 1.0
    assert metrics["atr_exit_count"] == 1
    assert metrics["reentry_count"] == 1
    assert metrics["avg_exposure"] == 0.0
    assert metrics["cost_drag"] == pytest.approx(0.0021)


def test_summarize_nav_by_year_uses_only_each_calendar_years_first_and_last_nav():
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2023-12-29", "2024-01-02", "2024-01-03", "2025-01-02"]),
            "nav": [1.0, 1.1, 1.0, 1.3],
            "weight": [0.0, 1.0, 1.0, 0.0],
        }
    )

    yearly = summarize_nav_by_year(nav)

    assert list(yearly["year"]) == [2023, 2024, 2025]
    assert yearly.loc[yearly["year"] == 2024, "total_return"].iloc[0] == pytest.approx(-0.090909)
    assert yearly.loc[yearly["year"] == 2025, "total_return"].iloc[0] == 0.0
    assert math.isfinite(float(yearly.loc[yearly["year"] == 2024, "max_drawdown"].iloc[0]))
