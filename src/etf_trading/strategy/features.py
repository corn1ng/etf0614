"""Technical feature calculation shared by charts, strategies, and backtests."""

from __future__ import annotations

import pandas as pd


MA_WINDOWS = (51, 120, 250, 850)
MOMENTUM_WINDOWS = (20, 60)


def add_technical_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Return prices with MA51/120/250/850 and core momentum features.

    The function does not forward-fill long moving averages. If an ETF has less
    than 850 observations, ``ma850`` remains missing, allowing strategy and UI
    layers to display "long-term trend data insufficient" instead of inventing
    a value.
    """

    if prices.empty:
        return prices.copy()

    required = {"trade_date", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing required columns: {sorted(missing)}")

    result = prices.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.sort_values("trade_date").reset_index(drop=True)

    close = result["close"].astype(float)
    for window in MA_WINDOWS:
        result[f"ma{window}"] = close.rolling(window=window, min_periods=window).mean()

    for window in MOMENTUM_WINDOWS:
        result[f"momentum_{window}"] = close / close.shift(window) - 1.0

    if "amount" in result.columns:
        result["avg_amount_20"] = result["amount"].astype(float).rolling(20, min_periods=1).mean()
    else:
        result["avg_amount_20"] = pd.NA

    result["return_1d"] = close.pct_change()
    result["volatility_20"] = result["return_1d"].rolling(20, min_periods=5).std()
    result["drawdown_120"] = close / close.rolling(120, min_periods=20).max() - 1.0
    return result
