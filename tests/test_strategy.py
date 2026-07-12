import numpy as np
import pandas as pd

from etf_trading.strategy.trend import TrendStrategy, TrendV1Strategy


def _featured_row(**overrides):
    base = {
        "etf_code": "513130",
        "trade_date": pd.Timestamp("2024-12-31"),
        "close": 10.0,
        "ma51": 9.5,
        "ma120": 9.0,
        "ma250": 8.0,
        "ma850": np.nan,
        "momentum_20": 0.05,
        "momentum_60": 0.12,
        "relative_strength_rank": 0.20,
        "category": "港股科技",
        "avg_amount_20": 80_000_000,
        "premium_rate": 0.002,
        "volatility_20": 0.018,
        "data_quality_score": 0.98,
        "underlying_market_open": True,
        "last_action_date": pd.Timestamp("2024-11-30"),
    }
    base.update(overrides)
    return pd.Series(base)


def _trend_v1_row(**overrides):
    base = {
        "etf_code": "510300",
        "trade_date": pd.Timestamp("2026-06-25"),
        "close": 10.0,
        "ma20": 9.7,
        "ma60": 9.2,
        "ma120": 8.8,
        "ma60_slope_20": 0.03,
        "momentum_60_skip5": 0.08,
        "momentum_120_skip5": 0.12,
        "momentum_20": 0.03,
        "relative_strength_rank": 0.20,
        "category": "A股宽基",
        "avg_amount_20": 150_000_000,
        "premium_rate": 0.001,
        "atr20": 0.18,
        "distance_ma20_atr": 1.67,
        "data_quality_score": 0.98,
        "underlying_market_open": True,
        "last_action_date": pd.Timestamp("2026-05-30"),
    }
    base.update(overrides)
    return pd.Series(base)


def test_trend_strategy_buys_strong_etf_when_filters_pass():
    strategy = TrendStrategy(min_trade_interval_days=10)

    signal = strategy.evaluate(_featured_row(), market_risk_on=True)

    assert signal.action == "BUY"
    assert "MA51" in signal.trigger_rules
    assert signal.target_weight > 0


def test_hong_kong_cross_market_filters_block_new_buys():
    strategy = TrendStrategy()

    signal = strategy.evaluate(
        _featured_row(underlying_market_open=False),
        market_risk_on=True,
    )

    assert signal.action == "FORBID"
    assert "底层市场休市" in signal.reason


def test_low_frequency_rule_prevents_frequent_active_buy():
    strategy = TrendStrategy(min_trade_interval_days=10)

    signal = strategy.evaluate(
        _featured_row(last_action_date=pd.Timestamp("2024-12-27")),
        market_risk_on=True,
    )

    assert signal.action == "HOLD"
    assert "低频" in signal.reason


def test_trend_v1_buys_when_all_core_filters_pass():
    strategy = TrendV1Strategy(min_trade_interval_days=10)

    signal = strategy.evaluate(_trend_v1_row(), market_risk_on=True)

    assert signal.action == "BUY"
    assert signal.target_weight > 0
    assert "price_above_MA60" in signal.trigger_rules
    assert "MA20_above_MA60" in signal.trigger_rules
    assert "not_overextended_2ATR" in signal.trigger_rules


def test_trend_v1_blocks_when_ma20_is_not_above_ma60():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(ma20=9.0), market_risk_on=True)

    assert signal.action == "HOLD"
    assert "趋势未满足" in signal.reason


def test_trend_v1_blocks_overheated_new_entries():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(distance_ma20_atr=2.4), market_risk_on=True)

    assert signal.action == "HOLD"
    assert "过热" in signal.reason
    assert "overextended_2ATR" in signal.risk_tags


def test_trend_v1_blocks_new_buys_when_ma60_is_missing():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(ma60=np.nan), market_risk_on=True)

    assert signal.action != "BUY"
    assert "required_indicator_missing" in signal.trigger_rules
    assert "required_indicator_missing" in signal.risk_tags


def test_trend_v1_blocks_new_buys_when_atr_distance_is_missing():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(distance_ma20_atr=np.nan), market_risk_on=True)

    assert signal.action != "BUY"
    assert "required_indicator_missing" in signal.trigger_rules
    assert "required_indicator_missing" in signal.risk_tags


def test_trend_v1_sells_when_close_breaks_ma60():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(close=9.0, ma60=9.2), market_risk_on=True, current_weight=0.10)

    assert signal.action == "SELL"
    assert signal.target_weight == 0.0
    assert "close_below_MA60" in signal.trigger_rules


def test_trend_v1_reduces_existing_position_before_additional_buy_logic():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(
        _trend_v1_row(close=9.5, ma20=9.7, ma60=9.2, momentum_20=-0.03),
        market_risk_on=True,
        current_weight=0.10,
    )

    assert signal.action == "REDUCE"
    assert signal.target_weight == 0.05
    assert "close_below_MA20" in signal.trigger_rules
    assert "momentum_20_negative" in signal.trigger_rules


def test_trend_v1_holds_existing_position_when_exit_indicator_is_missing():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(ma60=np.nan), market_risk_on=True, current_weight=0.10)

    assert signal.action == "HOLD"
    assert signal.target_weight == 0.10
    assert "required_indicator_missing" in signal.trigger_rules


def test_trend_v1_reduces_existing_position_when_market_risk_is_off():
    strategy = TrendV1Strategy()

    signal = strategy.evaluate(_trend_v1_row(), market_risk_on=False, current_weight=0.12)

    assert signal.action == "REDUCE"
    assert signal.target_weight == 0.06
