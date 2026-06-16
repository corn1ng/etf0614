"""Shared strategy and backtest models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd


SignalAction = Literal["BUY", "SELL", "REDUCE", "HOLD", "FORBID"]


@dataclass(frozen=True)
class StrategySignal:
    etf_code: str
    trade_date: pd.Timestamp | date
    action: SignalAction
    target_weight: float
    reason: str
    trigger_rules: list[str] = field(default_factory=list)
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_weight", round(max(self.target_weight, 0.0), 4))
