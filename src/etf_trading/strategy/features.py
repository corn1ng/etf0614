"""Technical feature calculation shared by charts, strategies, and backtests."""

from __future__ import annotations

import pandas as pd


MA_WINDOWS = (20, 51, 60, 120, 250, 850)
MOMENTUM_WINDOWS = (20, 60, 120)


def add_technical_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Return prices with moving averages, momentum, ATR, and risk features."""

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

    result["momentum_60_skip5"] = close.shift(5) / close.shift(65) - 1.0
    result["momentum_120_skip5"] = close.shift(5) / close.shift(125) - 1.0
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0

    if "amount" in result.columns:
        result["avg_amount_20"] = result["amount"].astype(float).rolling(20, min_periods=1).mean()
    else:
        result["avg_amount_20"] = pd.NA

    result["return_1d"] = close.pct_change()
    result["volatility_20"] = result["return_1d"].rolling(20, min_periods=5).std()
    result["drawdown_120"] = close / close.rolling(120, min_periods=20).max() - 1.0

    if {"high", "low", "close"}.issubset(result.columns):
        high = result["high"].astype(float)
        low = result["low"].astype(float)
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1, skipna=False)
        result["atr20"] = true_range.rolling(20, min_periods=20).mean()
        result["distance_ma20_atr"] = (close - result["ma20"]) / result["atr20"]
    else:
        result["atr20"] = pd.NA
        result["distance_ma20_atr"] = pd.NA

    return result
