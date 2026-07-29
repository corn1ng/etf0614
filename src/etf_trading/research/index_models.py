"""Locked configuration and data contracts for index trend research."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


@dataclass(frozen=True)
class IndexResearchConfig:
    """Immutable parameters for the single approved index-trend research rule."""

    strategy_version: str
    locked_at: date
    ma_window: int
    slope_lookback: int
    buffer_rate: float
    atr_window: int
    atr_multiple: float
    buffer_ablation: tuple[float, ...]
    commission_rate: float
    slippage_rate: float
    stress_multiplier: float
    min_valid_rows: int
    rolling_years: int
    rolling_step_years: int
    whipsaw_max_holding_days: int
    stage_years: tuple[int, ...]
    min_drawdown_win_rate: float
    min_median_drawdown_reduction: float
    max_median_annual_return_lag: float


@dataclass(frozen=True)
class IndexAdmissionResult:
    """Admitted local index histories plus audit metadata and exclusions."""

    frames: dict[str, pd.DataFrame]
    metadata: pd.DataFrame
    exclusions: pd.DataFrame


_LOCKED_CONFIG = IndexResearchConfig(
    strategy_version="index_trend_v1",
    locked_at=date(2026, 7, 30),
    ma_window=60,
    slope_lookback=20,
    buffer_rate=0.02,
    atr_window=20,
    atr_multiple=3.0,
    buffer_ablation=(0.0, 0.02, 0.03),
    commission_rate=0.00015,
    slippage_rate=0.0002,
    stress_multiplier=2.0,
    min_valid_rows=1000,
    rolling_years=5,
    rolling_step_years=1,
    whipsaw_max_holding_days=20,
    stage_years=(2015, 2018, 2020, 2022),
    min_drawdown_win_rate=0.60,
    min_median_drawdown_reduction=0.20,
    max_median_annual_return_lag=0.02,
)

_CONFIG_SECTIONS = {
    "strategy": {
        "version", "locked_at", "ma_window", "slope_lookback", "buffer_rate", "atr_window",
        "atr_multiple", "buffer_ablation",
    },
    "costs": {"commission_rate", "slippage_rate", "stress_multiplier"},
    "validation": {
        "min_valid_rows", "rolling_years", "rolling_step_years", "whipsaw_max_holding_days", "stage_years",
    },
    "effectiveness": {
        "min_drawdown_win_rate", "min_median_drawdown_reduction", "max_median_annual_return_lag",
    },
}


def load_index_research_config(path: str | Path) -> IndexResearchConfig:
    """Load the configuration only when it exactly matches the V1 lock."""

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or set(raw) != set(_CONFIG_SECTIONS):
        raise ValueError("index research config must contain only the locked sections")
    for section, expected_keys in _CONFIG_SECTIONS.items():
        values = raw.get(section)
        if not isinstance(values, dict) or set(values) != expected_keys:
            raise ValueError(f"index research config section '{section}' must match the locked schema")

    strategy = raw["strategy"]
    costs = raw["costs"]
    validation = raw["validation"]
    effectiveness = raw["effectiveness"]
    locked_at = strategy["locked_at"]
    if isinstance(locked_at, str):
        locked_at = date.fromisoformat(locked_at)
    if not isinstance(locked_at, date):
        raise ValueError("locked_at must be an ISO date")
    config = IndexResearchConfig(
        strategy_version=strategy["version"],
        locked_at=locked_at,
        ma_window=int(strategy["ma_window"]),
        slope_lookback=int(strategy["slope_lookback"]),
        buffer_rate=float(strategy["buffer_rate"]),
        atr_window=int(strategy["atr_window"]),
        atr_multiple=float(strategy["atr_multiple"]),
        buffer_ablation=tuple(float(value) for value in strategy["buffer_ablation"]),
        commission_rate=float(costs["commission_rate"]),
        slippage_rate=float(costs["slippage_rate"]),
        stress_multiplier=float(costs["stress_multiplier"]),
        min_valid_rows=int(validation["min_valid_rows"]),
        rolling_years=int(validation["rolling_years"]),
        rolling_step_years=int(validation["rolling_step_years"]),
        whipsaw_max_holding_days=int(validation["whipsaw_max_holding_days"]),
        stage_years=tuple(int(value) for value in validation["stage_years"]),
        min_drawdown_win_rate=float(effectiveness["min_drawdown_win_rate"]),
        min_median_drawdown_reduction=float(effectiveness["min_median_drawdown_reduction"]),
        max_median_annual_return_lag=float(effectiveness["max_median_annual_return_lag"]),
    )
    for field in fields(IndexResearchConfig):
        if getattr(config, field.name) != getattr(_LOCKED_CONFIG, field.name):
            raise ValueError(f"locked index research config differs: {field.name}")
    return config
