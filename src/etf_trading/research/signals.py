"""Signal generation for parameterized research candidates."""

from __future__ import annotations

import math

import pandas as pd

from etf_trading.research.models import StrategyCandidate
from etf_trading.research.regime import TrendRegimeClassifier
from etf_trading.strategy.models import StrategySignal


def generate_candidate_signals(
    etf_code: str,
    featured_prices: pd.DataFrame,
    candidate: StrategyCandidate,
    category: str = "A股行业",
) -> list[StrategySignal]:
    """Generate close-of-day research signals for one ETF and candidate."""

    if featured_prices.empty:
        return []

    frame = featured_prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)

    signals: list[StrategySignal] = []
    in_position = False
    last_action_date: pd.Timestamp | None = None
    highest_close_since_entry = math.nan
    regime_classifier = TrendRegimeClassifier()

    for _, row in frame.iterrows():
        trade_date = pd.Timestamp(row["trade_date"]).normalize()
        close = _safe_float(row.get("close"), default=math.nan)

        if in_position and not _is_missing(close):
            highest_close_since_entry = close if _is_missing(highest_close_since_entry) else max(
                highest_close_since_entry, close
            )

        trailing_exit, trailing_rules = _trailing_atr_exit(row, candidate, close, highest_close_since_entry)
        if in_position and (trailing_exit or _exit_condition(row, candidate, close)):
            trigger_rules = trailing_rules or [f"price_below_{candidate.exit_ma}"]
            signals.append(
                StrategySignal(
                    etf_code=etf_code,
                    trade_date=trade_date,
                    action="SELL",
                    target_weight=0.0,
                    reason=f"{candidate.name}: exit rule triggered",
                    trigger_rules=trigger_rules,
                )
            )
            in_position = False
            highest_close_since_entry = math.nan
            last_action_date = trade_date
            continue

        if in_position:
            continue

        entry_ok, trigger_rules = _entry_condition(row, candidate, close)
        if not entry_ok:
            continue
        risk_tags = [category]
        if candidate.require_trend_regime:
            regime = regime_classifier.classify(row)
            if not regime.allows_new_position:
                continue
            trigger_rules = trigger_rules + regime.trigger_rules
            risk_tags.extend(regime.risk_tags)
        if not _trade_interval_ok(last_action_date, trade_date, candidate.min_trade_interval_days):
            continue

        signals.append(
            StrategySignal(
                etf_code=etf_code,
                trade_date=trade_date,
                action="BUY",
                target_weight=candidate.target_weight,
                reason=f"{candidate.name}: right-side entry",
                trigger_rules=trigger_rules,
                risk_tags=risk_tags,
            )
        )
        in_position = True
        highest_close_since_entry = close
        last_action_date = trade_date

    return signals


def _entry_condition(row: pd.Series, candidate: StrategyCandidate, close: float) -> tuple[bool, list[str]]:
    trigger_rules: list[str] = []
    entry_ma_value = _safe_float(row.get(candidate.entry_ma), default=math.nan)
    trend_ma_value = _safe_float(row.get(candidate.trend_ma), default=math.nan)
    if _is_missing(close) or _is_missing(entry_ma_value) or _is_missing(trend_ma_value):
        return False, trigger_rules

    if close <= entry_ma_value:
        return False, trigger_rules
    trigger_rules.append(f"price_above_{candidate.entry_ma}")

    if close <= trend_ma_value:
        return False, trigger_rules
    trigger_rules.append(f"price_above_{candidate.trend_ma}")

    for window in candidate.momentum_windows:
        value = _safe_float(row.get(f"momentum_{window}"), default=math.nan)
        if _is_missing(value) or value <= 0:
            return False, trigger_rules
        trigger_rules.append(f"momentum_{window}_positive")

    for left_field, right_field in candidate.required_ma_relations:
        left_value = _safe_float(row.get(left_field), default=math.nan)
        right_value = _safe_float(row.get(right_field), default=math.nan)
        if _is_missing(left_value) or _is_missing(right_value) or left_value <= right_value:
            return False, trigger_rules
        trigger_rules.append(f"{left_field}_above_{right_field}")

    if candidate.slope_field is not None:
        slope = _safe_float(row.get(candidate.slope_field), default=math.nan)
        if _is_missing(slope) or slope <= 0:
            return False, trigger_rules
        trigger_rules.append(f"{candidate.slope_field}_positive")

    for window in candidate.skip_momentum_windows:
        field = f"momentum_{window}_skip5"
        value = _safe_float(row.get(field), default=math.nan)
        if _is_missing(value) or value <= 0:
            return False, trigger_rules
        trigger_rules.append(f"{field}_positive")

    if candidate.rs_rank_max is not None:
        rs_rank = _safe_float(row.get("relative_strength_rank"), default=math.nan)
        if _is_missing(rs_rank) or rs_rank > candidate.rs_rank_max:
            return False, trigger_rules
        trigger_rules.append(f"relative_strength_top_{int(candidate.rs_rank_max * 100)}pct")

    if candidate.max_distance_from_entry_ma is not None:
        distance = close / entry_ma_value - 1.0
        if distance > candidate.max_distance_from_entry_ma:
            return False, trigger_rules
        trigger_rules.append(f"not_overextended_from_{candidate.entry_ma}")

    if candidate.max_recent_return_20 is not None:
        recent_return_source = "return_20" if "return_20" in row else "momentum_20"
        recent_return = _safe_float(row.get(recent_return_source), default=math.nan)
        if _is_missing(recent_return) or recent_return > candidate.max_recent_return_20:
            return False, trigger_rules
        trigger_rules.append(f"not_overheated_{recent_return_source}")

    if candidate.max_atr_distance_from_ma is not None:
        atr_distance = _safe_float(row.get(candidate.atr_distance_field), default=math.nan)
        if _is_missing(atr_distance) or atr_distance > candidate.max_atr_distance_from_ma:
            return False, trigger_rules
        trigger_rules.append(f"not_overextended_{candidate.max_atr_distance_from_ma:g}ATR")

    return True, trigger_rules


def _exit_condition(row: pd.Series, candidate: StrategyCandidate, close: float) -> bool:
    exit_ma_value = _safe_float(row.get(candidate.exit_ma), default=math.nan)
    return not _is_missing(close) and not _is_missing(exit_ma_value) and close < exit_ma_value


def _trailing_atr_exit(
    row: pd.Series,
    candidate: StrategyCandidate,
    close: float,
    highest_close_since_entry: float,
) -> tuple[bool, list[str]]:
    if candidate.trailing_atr_multiple is None:
        return False, []
    atr = _safe_float(row.get(candidate.trailing_atr_field), default=math.nan)
    if _is_missing(close) or _is_missing(atr) or _is_missing(highest_close_since_entry):
        return False, []
    stop = highest_close_since_entry - candidate.trailing_atr_multiple * atr
    if close <= stop:
        return True, ["trailing_ATR_stop"]
    return False, []


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value_float):
        return default
    return value_float


def _is_missing(value: float) -> bool:
    return math.isnan(value)


def _trade_interval_ok(last_action_date: pd.Timestamp | None, trade_date: pd.Timestamp, min_days: int) -> bool:
    if last_action_date is None:
        return True
    return (trade_date - last_action_date).days >= min_days
