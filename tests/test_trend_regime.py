import pandas as pd

from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features


def _row(**overrides):
    base = {
        "trade_date": pd.Timestamp("2026-06-18"),
        "close": 12.0,
        "ma20": 11.6,
        "ma51": 11.2,
        "ma120": 10.5,
        "ma250": 9.5,
        "ma850": 8.0,
        "ma51_slope_20": 0.04,
        "ma120_slope_20": 0.03,
        "ma250_slope_60": 0.08,
        "momentum_20": 0.06,
        "momentum_60": 0.12,
        "drawdown_120": -0.04,
    }
    base.update(overrides)
    return pd.Series(base)


def test_classifier_labels_large_medium_and_small_uptrends():
    regime = TrendRegimeClassifier().classify(_row())

    assert regime.large_trend == "UP"
    assert regime.medium_trend == "UP"
    assert regime.small_trend == "RIGHT_SIDE_START"
    assert regime.allows_new_position is True
    assert "large_uptrend" in regime.trigger_rules


def test_classifier_blocks_short_breakout_inside_large_downtrend():
    regime = TrendRegimeClassifier().classify(
        _row(
            close=9.8,
            ma20=9.5,
            ma51=9.2,
            ma120=10.4,
            ma250=12.0,
            ma850=13.0,
            ma51_slope_20=0.02,
            ma120_slope_20=-0.04,
            ma250_slope_60=-0.10,
            momentum_20=0.08,
            momentum_60=-0.05,
            drawdown_120=-0.25,
        )
    )

    assert regime.large_trend == "DOWN"
    assert regime.medium_trend == "REBOUND"
    assert regime.allows_new_position is False
    assert "large_downtrend" in regime.risk_tags


def test_add_trend_regime_features_adds_moving_average_slopes():
    prices = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=900, freq="B"),
            "open": range(900),
            "high": range(1, 901),
            "low": range(900),
            "close": [float(value) for value in range(1, 901)],
            "volume": 1000,
            "amount": 1_000_000,
        }
    )

    result = add_trend_regime_features(prices)
    last = result.iloc[-1]

    assert "ma20" in result.columns
    assert last["ma51_slope_20"] > 0
    assert last["ma120_slope_20"] > 0
    assert last["ma250_slope_60"] > 0
