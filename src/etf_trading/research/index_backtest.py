"""Strict T+1 execution for the locked index trend strategy."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Protocol

import pandas as pd

from etf_trading.research.index_models import (
    IndexBacktestCosts,
    IndexBacktestResult,
    IndexBacktestTrade,
)
from etf_trading.strategy.models import StrategySignal


class CloseStrategy(Protocol):
    def evaluate_close(
        self,
        previous: pd.Series | None,
        current: pd.Series,
        *,
        in_position: bool,
        highest_close: float | None = None,
    ) -> StrategySignal | None: ...


_CANCELLED_COLUMNS = ["index_code", "signal_date", "cancelled_date", "action", "reason", "trigger_rules"]


def run_index_backtest(
    index_code: str,
    frame: pd.DataFrame,
    strategy: CloseStrategy,
    costs: IndexBacktestCosts,
) -> IndexBacktestResult:
    """Run close-generated strategy targets at the next finite positive open."""

    if frame.empty:
        return _result([], [], [])
    prices = _prepare_prices(frame)
    cash = 1.0
    shares = 0.0
    highest_close: float | None = None
    pending: StrategySignal | None = None
    trades: list[IndexBacktestTrade] = []
    nav_rows: list[dict[str, object]] = []
    cancellations: list[dict[str, object]] = []
    previous: pd.Series | None = None

    for _, current in prices.iterrows():
        trade_date = pd.Timestamp(current["trade_date"]).normalize()
        open_price = _valid_price(current.get("open"))
        close_price = _valid_price(current.get("close"))

        if pending is not None and open_price is not None:
            cash, shares, trade = _execute_pending(
                index_code=index_code,
                signal=pending,
                trade_date=trade_date,
                open_price=open_price,
                cash=cash,
                shares=shares,
                costs=costs,
            )
            trades.append(trade)
            highest_close = None if pending.action == "SELL" else highest_close
            pending = None
        elif pending is not None and pending.action == "BUY" and _entry_invalidated(strategy, current):
            cancellations.append(_cancellation(index_code, pending, trade_date, "entry_invalidated_before_execution"))
            pending = None

        if close_price is not None:
            nav = cash + shares * close_price
            weight = 0.0 if nav == 0 else shares * close_price / nav
            nav_rows.append({"trade_date": trade_date, "nav": nav, "weight": weight})
            if shares > 0:
                highest_close = close_price if highest_close is None else max(highest_close, close_price)

            signal = strategy.evaluate_close(
                previous,
                current,
                in_position=shares > 0,
                highest_close=highest_close,
            )
            if signal is not None:
                signal = replace(signal, etf_code=index_code, trade_date=trade_date)
                if pending is None:
                    pending = signal
                elif _target_changed(pending, signal):
                    cancellations.append(_cancellation(index_code, pending, trade_date, "replaced_before_execution"))
                    pending = signal
        previous = current

    if pending is not None:
        cancellations.append(_cancellation(index_code, pending, pd.Timestamp(prices.iloc[-1]["trade_date"]).normalize(), "no_future_valid_open"))
    return _result(trades, nav_rows, cancellations)


def run_buy_hold(index_code: str, frame: pd.DataFrame, costs: IndexBacktestCosts) -> IndexBacktestResult:
    """Buy at the first finite positive open and hold without a synthetic final sale."""

    if frame.empty:
        return _result([], [], [])
    prices = _prepare_prices(frame)
    cash = 1.0
    shares = 0.0
    bought = False
    trades: list[IndexBacktestTrade] = []
    nav_rows: list[dict[str, object]] = []
    for _, current in prices.iterrows():
        trade_date = pd.Timestamp(current["trade_date"]).normalize()
        open_price = _valid_price(current.get("open"))
        if not bought and open_price is not None:
            signal = StrategySignal(index_code, trade_date, "BUY", 1.0, "buy_hold_entry", ["first_valid_open"])
            cash, shares, trade = _execute_pending(
                index_code=index_code,
                signal=signal,
                trade_date=trade_date,
                open_price=open_price,
                cash=cash,
                shares=shares,
                costs=costs,
            )
            trades.append(trade)
            bought = True
        close_price = _valid_price(current.get("close"))
        if close_price is not None:
            nav = cash + shares * close_price
            weight = 0.0 if nav == 0 else shares * close_price / nav
            nav_rows.append({"trade_date": trade_date, "nav": nav, "weight": weight})
    return _result(trades, nav_rows, [])


def _prepare_prices(frame: pd.DataFrame) -> pd.DataFrame:
    if "trade_date" not in frame:
        raise ValueError("index backtest frame requires trade_date")
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    if result["trade_date"].isna().any():
        raise ValueError("index backtest frame has invalid trade_date")
    return result.sort_values("trade_date").reset_index(drop=True)


def _execute_pending(
    *,
    index_code: str,
    signal: StrategySignal,
    trade_date: pd.Timestamp,
    open_price: float,
    cash: float,
    shares: float,
    costs: IndexBacktestCosts,
) -> tuple[float, float, IndexBacktestTrade]:
    buying = signal.action == "BUY"
    execution_price = open_price * (1 + costs.slippage_rate if buying else 1 - costs.slippage_rate)
    portfolio_value = cash + shares * execution_price
    current_value = shares * execution_price
    weight_before = 0.0 if portfolio_value == 0 else current_value / portfolio_value
    if buying:
        trade_value = portfolio_value / (1 + costs.commission_rate)
        shares += (trade_value - current_value) / execution_price
        cash -= trade_value - current_value + abs(trade_value - current_value) * costs.commission_rate
    else:
        trade_value = current_value
        shares = 0.0
        cash += trade_value * (1 - costs.commission_rate)
    commission = abs(trade_value - current_value) * costs.commission_rate if buying else trade_value * costs.commission_rate
    after_value = cash + shares * execution_price
    weight_after = 0.0 if after_value == 0 else shares * execution_price / after_value
    trade = IndexBacktestTrade(
        index_code=index_code,
        signal_date=pd.Timestamp(signal.trade_date).normalize(),
        trade_date=trade_date,
        action=signal.action,
        execution_price=execution_price,
        weight_before=weight_before,
        weight_after=weight_after,
        commission=commission,
        delay_days=(trade_date - pd.Timestamp(signal.trade_date).normalize()).days,
        reason=signal.reason,
        trigger_rules=list(signal.trigger_rules),
    )
    return cash, shares, trade


def _entry_invalidated(strategy: CloseStrategy, current: pd.Series) -> bool:
    checker = getattr(strategy, "entry_is_valid", None)
    return callable(checker) and not bool(checker(current))


def _target_changed(old: StrategySignal, new: StrategySignal) -> bool:
    return old.action != new.action or old.target_weight != new.target_weight


def _cancellation(index_code: str, signal: StrategySignal, date: pd.Timestamp, reason: str) -> dict[str, object]:
    return {
        "index_code": index_code,
        "signal_date": pd.Timestamp(signal.trade_date).normalize(),
        "cancelled_date": date,
        "action": signal.action,
        "reason": reason,
        "trigger_rules": list(signal.trigger_rules),
    }


def _result(
    trades: list[IndexBacktestTrade], nav_rows: list[dict[str, object]], cancellations: list[dict[str, object]]
) -> IndexBacktestResult:
    return IndexBacktestResult(
        trades=trades,
        nav=pd.DataFrame(nav_rows, columns=["trade_date", "nav", "weight"]),
        cancelled_signals=pd.DataFrame(cancellations, columns=_CANCELLED_COLUMNS),
    )


def _valid_price(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None
