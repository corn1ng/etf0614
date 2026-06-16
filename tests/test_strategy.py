import numpy as np
import pandas as pd

from etf_trading.strategy.trend import TrendStrategy


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
