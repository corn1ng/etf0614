"""Models shared by research signal generation and experiment runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyCandidate:
    """A parameterized trend rule used for research, not live advice."""

    name: str
    entry_ma: str = "ma51"
    trend_ma: str = "ma120"
    exit_ma: str = "ma120"
    momentum_windows: tuple[int, ...] = (20, 60)
    skip_momentum_windows: tuple[int, ...] = ()
    required_ma_relations: tuple[tuple[str, str], ...] = ()
    slope_field: str | None = None
    rs_rank_max: float | None = 0.30
    max_distance_from_entry_ma: float | None = 0.12
    max_recent_return_20: float | None = 0.25
    max_atr_distance_from_ma: float | None = None
    atr_distance_field: str = "distance_ma20_atr"
    trailing_atr_multiple: float | None = None
    trailing_atr_field: str = "atr20"
    min_trade_interval_days: int = 10
    target_weight: float = 1.0
    require_trend_regime: bool = False


@dataclass(frozen=True)
class ResearchResult:
    """One candidate's result for one ETF or one segment."""

    candidate_name: str
    etf_code: str
    category: str
    metrics: dict[str, float]
