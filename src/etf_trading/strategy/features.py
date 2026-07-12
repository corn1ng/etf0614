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
        result[f"return_{window}"] = result[f"momentum_{window}"]

    result["momentum_60_skip5"] = close.shift(5) / close.shift(65) - 1.0
    result["momentum_120_skip5"] = close.shift(5) / close.shift(125) - 1.0
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0

    if "amount" in result.columns:
        amount = result["amount"].astype(float)
        result["avg_amount_5"] = amount.rolling(5, min_periods=1).mean()
        result["avg_amount_20"] = amount.rolling(20, min_periods=1).mean()
        result["amount_ratio_5_20"] = result["avg_amount_5"] / result["avg_amount_20"]
    else:
        result["avg_amount_5"] = pd.NA
        result["avg_amount_20"] = pd.NA
        result["amount_ratio_5_20"] = pd.NA

    result["distance_ma20_pct"] = close / result["ma20"] - 1.0
    result["rolling_high_close_60"] = close.rolling(60, min_periods=60).max()
    result["is_60d_close_breakout"] = close >= result["rolling_high_close_60"]

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


def add_weekly_trend_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Return prices with weekly trend fields forward-filled to daily rows."""

    if prices.empty:
        return prices.copy()

    required = {"trade_date", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing required columns: {sorted(missing)}")

    result = prices.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.sort_values("trade_date").reset_index(drop=True)
    weekly = (
        result.set_index("trade_date")["close"]
        .astype(float)
        .resample("W-FRI")
        .last()
        .dropna()
        .to_frame("weekly_close")
    )
    weekly["weekly_ma10"] = weekly["weekly_close"].rolling(10, min_periods=10).mean()
    weekly["weekly_ma30"] = weekly["weekly_close"].rolling(30, min_periods=30).mean()
    weekly["weekly_ma10_slope"] = weekly["weekly_ma10"] / weekly["weekly_ma10"].shift(4) - 1.0
    weekly["weekly_ma30_slope"] = weekly["weekly_ma30"] / weekly["weekly_ma30"].shift(4) - 1.0
    weekly["weekly_close_above_ma10"] = weekly["weekly_close"] > weekly["weekly_ma10"]
    weekly["weekly_close_above_ma30"] = weekly["weekly_close"] > weekly["weekly_ma30"]
    weekly = weekly.reindex(result["trade_date"], method="ffill").reset_index(drop=True)
    return pd.concat([result.reset_index(drop=True), weekly], axis=1)
