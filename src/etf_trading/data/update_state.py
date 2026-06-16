"""Data update state helpers for catch-up and rolling refetch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DataUpdateState:
    last_success_trade_date: date | None = None

    def missing_trade_dates(self, trade_calendar: list[date], through: date) -> list[date]:
        if self.last_success_trade_date is None:
            return [d for d in trade_calendar if d <= through]
        return [d for d in trade_calendar if self.last_success_trade_date < d <= through]

    def rolling_refetch_dates(self, trade_calendar: list[date], window: int = 5) -> list[date]:
        if self.last_success_trade_date is None:
            return []
        eligible = [d for d in trade_calendar if d <= self.last_success_trade_date]
        return eligible[-window:]
