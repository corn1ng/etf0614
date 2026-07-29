from __future__ import annotations

import pandas as pd
import pytest

from etf_trading.research.index_backtest import (
    run_buy_hold,
    run_index_backtest,
)
from etf_trading.research.index_models import IndexBacktestCosts, load_index_research_config
from etf_trading.research.index_metrics import summarize_index_result
from etf_trading.research.index_trend_v1 import IndexTrendV1
from etf_trading.strategy.models import StrategySignal


def default_costs() -> IndexBacktestCosts:
    return IndexBacktestCosts(commission_rate=0.00015, slippage_rate=0.0002)


def prices(rows: list[dict[str, float | str]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    return frame


class AlwaysBuyStrategy:
    def evaluate_close(self, previous, current, *, in_position, highest_close=None):
        if not in_position:
            return StrategySignal("", current["trade_date"], "BUY", 1.0, "always_buy", ["test"])
        return None


class BuyThenSellStrategy:
    def evaluate_close(self, previous, current, *, in_position, highest_close=None):
        action = "SELL" if in_position else "BUY"
        weight = 0.0 if in_position else 1.0
        return StrategySignal("", current["trade_date"], action, weight, f"always_{action.lower()}", ["test"])


class BuyThenSingleSellStrategy:
    def evaluate_close(self, previous, current, *, in_position, highest_close=None):
        if not in_position:
            return StrategySignal("", current["trade_date"], "BUY", 1.0, "buy", ["test"])
        if bool(current.get("request_exit", False)):
            return StrategySignal("", current["trade_date"], "SELL", 0.0, "single_sell", ["test"])
        return None


class ReplacingTargetStrategy:
    def evaluate_close(self, previous, current, *, in_position, highest_close=None):
        action = str(current["target"])
        return StrategySignal("", current["trade_date"], action, 1.0 if action == "BUY" else 0.0, "replacement", ["test"])


def test_costs_can_be_built_from_locked_default_or_doubled_stress_config():
    config = load_index_research_config("configs/index_research.yaml")

    assert IndexBacktestCosts.from_config(config) == default_costs()
    assert IndexBacktestCosts.from_config(config, stress=True) == IndexBacktestCosts(0.0003, 0.0004)


def test_signal_executes_at_next_valid_open():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 10.0, "close": 10.0, "ma60": 100.0, "ma60_slope_20": 1.0, "atr20": 2.0},
                {"trade_date": "2024-01-03", "open": float("nan"), "close": 10.0, "ma60": 100.0, "ma60_slope_20": 1.0, "atr20": 2.0},
                {"trade_date": "2024-01-04", "open": 12.0, "close": 12.0, "ma60": 100.0, "ma60_slope_20": 1.0, "atr20": 2.0},
            ]
        ),
        AlwaysBuyStrategy(),
        default_costs(),
    )

    trade = result.trades[0]
    assert trade.trade_date == pd.Timestamp("2024-01-04")
    assert trade.execution_price == pytest.approx(12.0 * 1.0002)
    assert trade.delay_days == 2


def test_gap_exit_uses_actual_open_not_lower_band_or_atr_stop():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 100.0, "close": 100.0},
                {"trade_date": "2024-01-03", "open": 100.0, "close": 100.0},
                {"trade_date": "2024-01-04", "open": 80.0, "close": 80.0},
            ]
        ),
        BuyThenSellStrategy(),
        default_costs(),
    )

    assert result.trades[-1].execution_price == pytest.approx(80.0 * 0.9998)


def test_pending_buy_is_cancelled_when_entry_condition_invalidates():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 100.0, "close": 101.9, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-03", "open": 100.0, "close": 103.0, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-04", "open": float("nan"), "close": 101.0, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
            ]
        ),
        IndexTrendV1(),
        default_costs(),
    )

    assert result.trades == []
    assert result.cancelled_signals.iloc[0]["reason"] == "entry_invalidated_before_execution"


@pytest.mark.parametrize("missing_field", ["close", "ma60", "ma60_slope_20"])
def test_pending_buy_waits_when_entry_revalidation_data_is_missing(missing_field):
    missing_row = {"trade_date": "2024-01-04", "open": float("nan"), "close": 103.0, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0}
    missing_row[missing_field] = float("nan")
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 100.0, "close": 101.9, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-03", "open": 100.0, "close": 103.0, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                missing_row,
                {"trade_date": "2024-01-05", "open": 104.0, "close": 104.0, "ma60": 100.0, "ma60_slope_20": 0.01, "atr20": 2.0},
            ]
        ),
        IndexTrendV1(),
        default_costs(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].trade_date == pd.Timestamp("2024-01-05")
    assert result.cancelled_signals.empty


def test_pending_sell_is_not_cancelled_by_rebound_and_executes_original_signal():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 100.0, "close": 100.0, "request_exit": False},
                {"trade_date": "2024-01-03", "open": 100.0, "close": 100.0, "request_exit": True},
                {"trade_date": "2024-01-04", "open": float("nan"), "close": 120.0, "request_exit": False},
                {"trade_date": "2024-01-05", "open": 110.0, "close": 110.0, "request_exit": False},
            ]
        ),
        BuyThenSingleSellStrategy(),
        default_costs(),
    )

    sell = result.trades[-1]
    assert sell.action == "SELL"
    assert sell.signal_date == pd.Timestamp("2024-01-03")
    assert sell.trade_date == pd.Timestamp("2024-01-05")
    assert "replaced_before_execution" not in set(result.cancelled_signals["reason"])


def test_pending_signal_at_period_end_is_cancelled_with_no_future_valid_open():
    result = run_index_backtest(
        "000300",
        prices([{"trade_date": "2024-01-02", "open": 10.0, "close": 10.0}]),
        AlwaysBuyStrategy(),
        default_costs(),
    )

    assert result.trades == []
    assert result.cancelled_signals.iloc[0]["reason"] == "no_future_valid_open"


def test_new_target_replaces_a_pending_target_with_an_audit_record():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": float("nan"), "close": 10.0, "target": "BUY"},
                {"trade_date": "2024-01-03", "open": float("nan"), "close": 10.0, "target": "SELL"},
            ]
        ),
        ReplacingTargetStrategy(),
        default_costs(),
    )

    assert result.cancelled_signals.iloc[0]["reason"] == "replaced_before_execution"
    assert result.cancelled_signals.iloc[0]["action"] == "BUY"


def test_commission_is_deducted_and_nav_tracks_only_the_actual_position():
    costs = IndexBacktestCosts(commission_rate=0.01, slippage_rate=0.0)
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 10.0, "close": 10.0},
                {"trade_date": "2024-01-03", "open": 10.0, "close": 10.0},
            ]
        ),
        AlwaysBuyStrategy(),
        costs,
    )

    assert result.trades[0].commission == pytest.approx(0.01 / 1.01)
    assert result.nav.iloc[-1]["nav"] == pytest.approx(1 / 1.01)
    assert result.nav.iloc[-1]["weight"] == pytest.approx(1.0)


def test_trade_record_and_metrics_audit_buy_and_sell_slippage_costs_once():
    costs = IndexBacktestCosts(commission_rate=0.01, slippage_rate=0.02)
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 100.0, "close": 100.0},
                {"trade_date": "2024-01-03", "open": 100.0, "close": 100.0},
                {"trade_date": "2024-01-04", "open": 100.0, "close": 100.0},
            ]
        ),
        BuyThenSellStrategy(),
        costs,
    )

    buy, sell = result.trades
    assert buy.reference_price == 100.0
    assert sell.reference_price == 100.0
    assert buy.execution_price == pytest.approx(102.0)
    assert sell.execution_price == pytest.approx(98.0)
    assert buy.slippage_cost > 0
    assert sell.slippage_cost == pytest.approx(buy.slippage_cost)

    metrics = summarize_index_result(result)
    assert metrics["commission_cost"] == pytest.approx(round(buy.commission + sell.commission, 6))
    assert metrics["slippage_cost"] == pytest.approx(round(buy.slippage_cost + sell.slippage_cost, 6))
    assert metrics["cost_drag"] == pytest.approx(metrics["commission_cost"] + metrics["slippage_cost"])
    assert metrics["explicit_transaction_cost"] == metrics["cost_drag"]


def test_highest_close_starts_on_actual_entry_execution_date():
    result = run_index_backtest(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": 203.9, "close": 203.9, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-03", "open": 205.0, "close": 205.0, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-04", "open": 200.0, "close": 200.0, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-05", "open": 197.0, "close": 197.0, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-06", "open": 194.0, "close": 194.0, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
                {"trade_date": "2024-01-07", "open": 193.0, "close": 193.0, "ma60": 200.0, "ma60_slope_20": 0.01, "atr20": 2.0},
            ]
        ),
        IndexTrendV1(),
        default_costs(),
    )

    assert [trade.action for trade in result.trades] == ["BUY", "SELL"]
    assert result.trades[-1].trade_date == pd.Timestamp("2024-01-07")
    assert result.trades[-1].reason == "atr_emergency_exit"


def test_buy_hold_uses_first_valid_open_and_does_not_create_terminal_sale():
    result = run_buy_hold(
        "000300",
        prices(
            [
                {"trade_date": "2024-01-02", "open": float("nan"), "close": 10.0},
                {"trade_date": "2024-01-03", "open": 12.0, "close": 13.0},
            ]
        ),
        default_costs(),
    )

    assert len(result.trades) == 1
    assert result.trades[0].action == "BUY"
    assert result.trades[0].trade_date == pd.Timestamp("2024-01-03")
    assert result.trades[0].execution_price == pytest.approx(12.0 * 1.0002)
    assert result.nav.iloc[-1]["nav"] > 1.0
