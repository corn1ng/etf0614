import numpy as np
import pandas as pd

from etf_trading.strategy.features import add_technical_features


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
