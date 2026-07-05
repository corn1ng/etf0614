import numpy as np
import pandas as pd

from etf_trading.strategy.features import add_technical_features, add_weekly_trend_features


def _price_frame(days: int) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=days, freq="B")
    close = np.arange(1, days + 1, dtype=float)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(days, 1000),
            "amount": np.full(days, 1_000_000),
        }
    )


def test_adds_required_moving_averages_and_momentum():
    result = add_technical_features(_price_frame(900))

    last = result.iloc[-1]
    assert last["ma51"] == np.mean(np.arange(850, 901))
    assert last["ma120"] == np.mean(np.arange(781, 901))
    assert last["ma250"] == np.mean(np.arange(651, 901))
    assert last["ma850"] == np.mean(np.arange(51, 901))
    assert last["momentum_20"] > 0
    assert last["momentum_60"] > 0


def test_ma850_is_missing_until_enough_history_exists():
    result = add_technical_features(_price_frame(300))

    assert pd.isna(result.iloc[-1]["ma850"])
    assert not pd.isna(result.iloc[-1]["ma250"])


def test_adds_trend_v1_moving_averages_slope_skip_momentum_and_atr():
    result = add_technical_features(_price_frame(180))

    last = result.iloc[-1]
    expected_ma20 = np.mean(np.arange(161, 181))
    expected_ma60 = np.mean(np.arange(121, 181))
    expected_ma60_20_days_ago = np.mean(np.arange(101, 161))
    expected_atr20 = 1.5
    assert last["ma20"] == np.mean(np.arange(161, 181))
    assert last["ma60"] == np.mean(np.arange(121, 181))
    assert last["ma120"] == np.mean(np.arange(61, 181))
    assert np.isclose(last["ma60_slope_20"], expected_ma60 / expected_ma60_20_days_ago - 1.0)
    assert last["momentum_60_skip5"] == result["close"].iloc[-6] / result["close"].iloc[-66] - 1.0
    assert last["momentum_120_skip5"] == result["close"].iloc[-6] / result["close"].iloc[-126] - 1.0
    assert np.isclose(last["atr20"], expected_atr20)
    assert np.isclose(last["distance_ma20_atr"], (last["close"] - expected_ma20) / expected_atr20)


def test_atr_is_missing_when_high_low_or_close_are_missing():
    prices = _price_frame(80).drop(columns=["high"])

    result = add_technical_features(prices)

    assert "atr20" in result.columns
    assert result["atr20"].isna().all()
    assert result["distance_ma20_atr"].isna().all()


def test_atr_is_missing_when_recent_high_values_are_missing():
    prices = _price_frame(80)
    prices.loc[prices.index[-20:], "high"] = np.nan

    result = add_technical_features(prices)

    assert result["atr20"].tail(20).isna().all()
    assert result["distance_ma20_atr"].tail(20).isna().all()


def test_adds_atomic_daily_feature_columns():
    result = add_technical_features(_price_frame(120))

    last = result.iloc[-1]
    assert np.isclose(last["return_20"], last["momentum_20"])
    assert np.isclose(last["return_60"], last["momentum_60"])
    assert np.isclose(last["avg_amount_5"], 1_000_000)
    assert np.isclose(last["amount_ratio_5_20"], 1.0)
    assert np.isclose(last["distance_ma20_pct"], last["close"] / last["ma20"] - 1.0)
    assert last["rolling_high_close_60"] == result["close"].tail(60).max()
    assert bool(last["is_60d_close_breakout"]) is True


def test_add_weekly_trend_features_backfills_latest_week_state():
    result = add_weekly_trend_features(_price_frame(220))

    last = result.iloc[-1]
    assert "weekly_ma10" in result.columns
    assert not pd.isna(last["weekly_close"])
    assert not pd.isna(last["weekly_ma10"])
    assert not pd.isna(last["weekly_ma30"])
    assert isinstance(bool(last["weekly_close_above_ma10"]), bool)
