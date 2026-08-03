"""Stateless, buffered MA60/ATR20 index trend rule locked for V1 research."""

from __future__ import annotations

import math

import pandas as pd

from etf_trading.strategy.models import StrategySignal


class IndexTrendV1:
    """Evaluate only one close at a time; execution state belongs to the backtest."""

    def __init__(self, buffer_rate: float = 0.02, atr_multiple: float = 3.0) -> None:
        if not math.isfinite(buffer_rate) or buffer_rate < 0:
            raise ValueError("buffer_rate must be a finite non-negative number")
        if not math.isfinite(atr_multiple) or atr_multiple <= 0:
            raise ValueError("atr_multiple must be a finite positive number")
        self.buffer_rate = buffer_rate
        self.atr_multiple = atr_multiple

    def evaluate_close(
        self,
        previous: pd.Series | None,
        current: pd.Series,
        *,
        in_position: bool,
        highest_close: float | None = None,
    ) -> StrategySignal | None:
        """Create a close signal only when all V1 inputs are finite."""

        close = _finite(current.get("close"))
        ma60 = _finite(current.get("ma60"))
        slope = _finite(current.get("ma60_slope_20"))
        atr20 = _finite(current.get("atr20"))
        if None in (close, ma60, slope, atr20):
            return None

        trade_date = pd.Timestamp(current.get("trade_date", pd.NaT))
        if not pd.isna(trade_date):
            trade_date = trade_date.normalize()
        index_code = str(current.get("index_code", ""))
        lower_band = ma60 * (1 - self.buffer_rate)
        if in_position:
            highest = _finite(highest_close)
            if highest is not None and close <= highest - self.atr_multiple * atr20:
                return _signal(
                    index_code,
                    trade_date,
                    "SELL",
                    "atr_emergency_exit",
                    ["atr_emergency_stop"],
                )
            if close < lower_band:
                return _signal(index_code, trade_date, "SELL", "lower_band_exit", ["price_below_lower_band"])
            return None

        if previous is None:
            return None
        previous_close = _finite(previous.get("close"))
        previous_ma60 = _finite(previous.get("ma60"))
        if previous_close is None or previous_ma60 is None:
            return None
        previous_upper_band = previous_ma60 * (1 + self.buffer_rate)
        upper_band = ma60 * (1 + self.buffer_rate)
        if previous_close <= previous_upper_band and close > upper_band and slope > 0:
            return _signal(
                index_code,
                trade_date,
                "BUY",
                "fresh_upper_band_breakout",
                ["fresh_upper_band_cross", "ma60_slope_20_positive"],
            )
        return None

    def entry_is_valid(self, current: pd.Series) -> bool | None:
        """Confirm, reject, or defer an unfilled entry when its close inputs are missing."""

        close = _finite(current.get("close"))
        ma60 = _finite(current.get("ma60"))
        slope = _finite(current.get("ma60_slope_20"))
        if None in (close, ma60, slope):
            return None
        return close > ma60 * (1 + self.buffer_rate) and slope > 0


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _signal(
    index_code: str,
    trade_date: pd.Timestamp,
    action: str,
    reason: str,
    trigger_rules: list[str],
) -> StrategySignal:
    return StrategySignal(
        etf_code=index_code,
        trade_date=trade_date,
        action=action,  # type: ignore[arg-type]
        target_weight=1.0 if action == "BUY" else 0.0,
        reason=reason,
        trigger_rules=trigger_rules,
    )
