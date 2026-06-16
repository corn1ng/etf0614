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
