"""Large/medium/small trend regime classification for ETF research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import math

import pandas as pd

from etf_trading.strategy.features import add_technical_features


LargeTrend = Literal["UP", "RECOVERY", "RANGE", "DOWN", "UNKNOWN"]
MediumTrend = Literal["UP", "TURNING_UP", "RANGE", "REBOUND", "DOWN", "UNKNOWN"]
SmallTrend = Literal["RIGHT_SIDE_START", "EXTENDED", "PULLBACK", "BROKEN", "RANGE", "UNKNOWN"]


@dataclass(frozen=True)
class TrendRegime:
    large_trend: LargeTrend
    medium_trend: MediumTrend
    small_trend: SmallTrend
    allows_new_position: bool
    trigger_rules: list[str]
    risk_tags: list[str]


class TrendRegimeClassifier:
    """Classify ETF trend state before research signals can buy."""

    def __init__(
        self,
        max_small_trend_extension: float = 0.12,
        large_downtrend_drawdown: float = -0.20,
    ) -> None:
        self.max_small_trend_extension = max_small_trend_extension
        self.large_downtrend_drawdown = large_downtrend_drawdown

    def classify(self, row: pd.Series) -> TrendRegime:
        close = _safe_float(row.get("close"), math.nan)
        ma20 = _safe_float(row.get("ma20"), math.nan)
        ma51 = _safe_float(row.get("ma51"), math.nan)
        ma120 = _safe_float(row.get("ma120"), math.nan)
        ma250 = _safe_float(row.get("ma250"), math.nan)
        ma850 = _safe_float(row.get("ma850"), math.nan)
        ma51_slope = _safe_float(row.get("ma51_slope_20"), 0.0)
        ma120_slope = _safe_float(row.get("ma120_slope_20"), 0.0)
        ma250_slope = _safe_float(row.get("ma250_slope_60"), 0.0)
        momentum_20 = _safe_float(row.get("momentum_20"), 0.0)
        momentum_60 = _safe_float(row.get("momentum_60"), 0.0)
        drawdown_120 = _safe_float(row.get("drawdown_120"), 0.0)

        large, large_rules, large_risks = self._large_trend(close, ma250, ma850, ma250_slope, drawdown_120)
        medium, medium_rules, medium_risks = self._medium_trend(close, ma51, ma120, ma51_slope, ma120_slope, momentum_60, large)
        small, small_rules, small_risks = self._small_trend(close, ma20, ma51, momentum_20)

        allows = (
            large in {"UP", "RECOVERY"}
            and medium in {"UP", "TURNING_UP"}
            and small in {"RIGHT_SIDE_START", "PULLBACK"}
        )
        return TrendRegime(
            large_trend=large,
            medium_trend=medium,
            small_trend=small,
            allows_new_position=allows,
            trigger_rules=large_rules + medium_rules + small_rules,
            risk_tags=large_risks + medium_risks + small_risks,
        )

    def _large_trend(
        self,
        close: float,
        ma250: float,
        ma850: float,
        ma250_slope: float,
        drawdown_120: float,
    ) -> tuple[LargeTrend, list[str], list[str]]:
        if _missing(close) or _missing(ma250):
            return "UNKNOWN", [], ["large_trend_unknown"]
        if not _missing(ma850) and close > ma250 > ma850 and ma250_slope > 0:
            return "UP", ["large_uptrend"], []
        if close > ma250 and ma250_slope > 0:
            return "RECOVERY", ["large_recovery"], []
        if close < ma250 and ma250_slope < 0 and drawdown_120 <= self.large_downtrend_drawdown:
            return "DOWN", [], ["large_downtrend"]
        return "RANGE", ["large_range"], ["large_range"]

    def _medium_trend(
        self,
        close: float,
        ma51: float,
        ma120: float,
        ma51_slope: float,
        ma120_slope: float,
        momentum_60: float,
        large_trend: LargeTrend,
    ) -> tuple[MediumTrend, list[str], list[str]]:
        if _missing(close) or _missing(ma51) or _missing(ma120):
            return "UNKNOWN", [], ["medium_trend_unknown"]
        if close > ma51 > ma120 and ma51_slope > 0 and ma120_slope > 0 and momentum_60 > 0:
            return "UP", ["medium_uptrend"], []
        if close > ma51 and close > ma120 and ma51_slope > 0 and momentum_60 > 0:
            return "TURNING_UP", ["medium_turning_up"], []
        if large_trend == "DOWN" and close > ma51 and momentum_60 <= 0:
            return "REBOUND", ["medium_rebound"], ["medium_rebound_in_large_downtrend"]
        if close < ma120 and ma120_slope < 0:
            return "DOWN", [], ["medium_downtrend"]
        return "RANGE", ["medium_range"], ["medium_range"]

    def _small_trend(self, close: float, ma20: float, ma51: float, momentum_20: float) -> tuple[SmallTrend, list[str], list[str]]:
        if _missing(close) or _missing(ma20) or _missing(ma51):
            return "UNKNOWN", [], ["small_trend_unknown"]
        distance = close / ma51 - 1.0 if ma51 else math.nan
        if close > ma20 > ma51 and momentum_20 > 0 and distance <= self.max_small_trend_extension:
            return "RIGHT_SIDE_START", ["small_right_side_start"], []
        if close > ma20 > ma51 and momentum_20 > 0:
            return "EXTENDED", ["small_extended"], ["small_trend_extended"]
        if close >= ma51 and momentum_20 <= 0:
            return "PULLBACK", ["small_pullback"], []
        if close < ma51:
            return "BROKEN", [], ["small_broken"]
        return "RANGE", ["small_range"], ["small_range"]


def add_trend_regime_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Add moving averages and slope features needed by trend regime classification."""

    featured = add_technical_features(prices)
    if featured.empty:
        return featured
    close = featured["close"].astype(float)
    featured["ma20"] = close.rolling(window=20, min_periods=20).mean()
    for window, lookback in [("ma51", 20), ("ma120", 20), ("ma250", 60)]:
        featured[f"{window}_slope_{lookback}"] = featured[window] / featured[window].shift(lookback) - 1.0
    return featured


def _safe_float(value: object, default: float) -> float:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value_float):
        return default
    return value_float


def _missing(value: float) -> bool:
    return math.isnan(value)
