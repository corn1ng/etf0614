"""Metrics specific to the locked index-trend backtests."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from etf_trading.research.index_models import IndexBacktestResult, IndexBacktestTrade


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class _ClosedRoundTrip:
    entry: IndexBacktestTrade
    exit: IndexBacktestTrade
    entry_index: int
    exit_index: int
    net_return: float

    @property
    def holding_days(self) -> int:
        return self.exit_index - self.entry_index


def summarize_index_result(
    result: IndexBacktestResult,
    whipsaw_max_holding_days: int = 20,
) -> dict[str, object]:
    """Summarize one index result without treating an open position as a completed trade.

    Annualized return is a 252-observed-period CAGR, volatility uses daily returns
    with ``ddof=0``, and Sharpe is CAGR divided by that volatility.  Recovery days
    run from the most recent peak before the selected trough to its recovery.
    ``cost_drag`` is cumulative explicit transaction cost in NAV/cash units, not
    the final-NAV difference between costed and uncosted portfolios.
    """

    if whipsaw_max_holding_days < 0:
        raise ValueError("whipsaw_max_holding_days must be non-negative")

    nav = _normalized_nav(result.nav)
    metrics = _nav_metrics(nav, initial_nav=result.initial_nav)
    closed_round_trips = _closed_round_trips(result.trades, nav)
    metrics.update(_trade_metrics(result.trades, closed_round_trips, nav, whipsaw_max_holding_days))
    return metrics


def summarize_nav_by_year(nav: pd.DataFrame) -> pd.DataFrame:
    """Summarize each calendar year from that year's first NAV to its last NAV."""

    frame = _normalized_nav(nav)
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for year, segment in frame.groupby(frame["trade_date"].dt.year, sort=True):
        row: dict[str, object] = {"year": int(year)}
        row.update(_nav_metrics(segment.reset_index(drop=True)))
        rows.append(row)
    return pd.DataFrame(rows)


def _normalized_nav(nav: pd.DataFrame) -> pd.DataFrame:
    if nav.empty:
        return pd.DataFrame(columns=["trade_date", "nav", "weight"])
    required = {"trade_date", "nav"}
    missing = required - set(nav.columns)
    if missing:
        raise ValueError(f"nav missing required columns: {sorted(missing)}")

    frame = nav.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.normalize()
    frame["nav"] = pd.to_numeric(frame["nav"], errors="raise")
    if not frame["nav"].map(math.isfinite).all() or (frame["nav"] <= 0).any():
        raise ValueError("nav values must be finite and positive")
    if "weight" not in frame:
        frame["weight"] = 0.0
    frame["weight"] = pd.to_numeric(frame["weight"], errors="raise")
    if not frame["weight"].map(math.isfinite).all():
        raise ValueError("nav weights must be finite")
    return frame.sort_values("trade_date").reset_index(drop=True)


def _nav_metrics(nav: pd.DataFrame, *, initial_nav: float | None = None) -> dict[str, object]:
    if nav.empty:
        return _zero_nav_metrics()

    total_return = 0.0
    annualized_return = 0.0
    volatility = 0.0
    sharpe = 0.0
    if initial_nav is not None:
        if not math.isfinite(initial_nav) or initial_nav <= 0:
            raise ValueError("initial_nav must be finite and positive")
        # The base is capital immediately before the first dated close valuation,
        # so there are ``len(nav)`` observed holding periods for annualization.
        total_return = float(nav["nav"].iloc[-1] / initial_nav - 1.0)
        annualized_return = _annualized_return(total_return, len(nav))
    elif len(nav) >= 2:
        total_return = float(nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1.0)
        annualized_return = _annualized_return(total_return, len(nav) - 1)
    if len(nav) >= 2:
        daily_returns = nav["nav"].pct_change().iloc[1:]
        volatility = float(daily_returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))
        sharpe = 0.0 if volatility == 0 else annualized_return / volatility

    drawdown_metrics = _drawdown_metrics(nav)
    max_drawdown = float(drawdown_metrics["max_drawdown"])
    calmar = 0.0 if max_drawdown == 0 else annualized_return / abs(max_drawdown)
    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized_return, 6),
        "volatility": round(volatility, 6),
        "sharpe": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "calmar": round(calmar, 6),
        "avg_exposure": round(float(nav["weight"].mean()), 6),
        **drawdown_metrics,
        "max_drawdown": round(max_drawdown, 6),
    }


def _zero_nav_metrics() -> dict[str, object]:
    return {
        "total_return": 0.0,
        "annualized_return": 0.0,
        "volatility": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "calmar": 0.0,
        "avg_exposure": 0.0,
        "drawdown_start": None,
        "drawdown_trough": None,
        "drawdown_recovery": None,
        "drawdown_recovered": True,
        "recovery_trading_days": 0,
    }


def _drawdown_metrics(nav: pd.DataFrame) -> dict[str, object]:
    if nav.empty:
        return _zero_nav_metrics()
    running_max = nav["nav"].cummax()
    drawdowns = nav["nav"] / running_max - 1.0
    trough_index = int(drawdowns.idxmin())
    max_drawdown = float(drawdowns.iloc[trough_index])
    if max_drawdown == 0:
        return {
            "max_drawdown": 0.0,
            "drawdown_start": None,
            "drawdown_trough": None,
            "drawdown_recovery": None,
            "drawdown_recovered": True,
            "recovery_trading_days": 0,
        }

    peak_nav = float(running_max.iloc[trough_index])
    peak_candidates = nav.index[(nav.index <= trough_index) & (nav["nav"] == peak_nav)]
    peak_index = int(peak_candidates[-1])
    recovered_indices = nav.index[(nav.index > trough_index) & (nav["nav"] >= peak_nav)]
    recovered = len(recovered_indices) > 0
    recovery_index = int(recovered_indices[0]) if recovered else None
    return {
        "max_drawdown": max_drawdown,
        "drawdown_start": _date_text(nav["trade_date"].iloc[peak_index]),
        "drawdown_trough": _date_text(nav["trade_date"].iloc[trough_index]),
        "drawdown_recovery": _date_text(nav["trade_date"].iloc[recovery_index]) if recovered else None,
        "drawdown_recovered": recovered,
        "recovery_trading_days": recovery_index - peak_index if recovered else None,
    }


def _annualized_return(total_return: float, periods: int) -> float:
    if periods <= 0:
        return 0.0
    if total_return <= -1.0:
        return -1.0
    return (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0


def _closed_round_trips(trades: list[IndexBacktestTrade], nav: pd.DataFrame) -> list[_ClosedRoundTrip]:
    if nav.empty:
        return []
    dates = pd.DatetimeIndex(nav["trade_date"])
    cash = 1.0
    open_trade: tuple[IndexBacktestTrade, float, float, int] | None = None
    closed: list[_ClosedRoundTrip] = []

    for trade in trades:
        if trade.action == "BUY":
            if open_trade is not None or trade.execution_price <= 0:
                continue
            entry_cash = cash
            invested_cash = max(entry_cash - max(float(trade.commission), 0.0), 0.0)
            shares = invested_cash / float(trade.execution_price)
            open_trade = (trade, entry_cash, shares, _trading_index(dates, trade.trade_date))
            continue
        if trade.action != "SELL" or open_trade is None or trade.execution_price <= 0:
            continue

        entry, entry_cash, shares, entry_index = open_trade
        cash = max(shares * float(trade.execution_price) - max(float(trade.commission), 0.0), 0.0)
        exit_index = _trading_index(dates, trade.trade_date)
        net_return = 0.0 if entry_cash == 0 else cash / entry_cash - 1.0
        closed.append(_ClosedRoundTrip(entry, trade, entry_index, exit_index, net_return))
        open_trade = None
    return closed


def _trading_index(dates: pd.DatetimeIndex, trade_date: pd.Timestamp) -> int:
    position = int(dates.searchsorted(pd.Timestamp(trade_date).normalize(), side="left"))
    return min(position, len(dates) - 1)


def _trade_metrics(
    trades: list[IndexBacktestTrade],
    closed_round_trips: list[_ClosedRoundTrip],
    nav: pd.DataFrame,
    whipsaw_max_holding_days: int,
) -> dict[str, object]:
    closed_count = len(closed_round_trips)
    returns = [round_trip.net_return for round_trip in closed_round_trips]
    holding_days = [round_trip.holding_days for round_trip in closed_round_trips]
    whipsaw_count = sum(
        1
        for round_trip in closed_round_trips
        if round_trip.holding_days <= whipsaw_max_holding_days and round_trip.net_return < 0
    )
    atr_exit_count = sum(
        1 for trade in trades if trade.action == "SELL" and trade.reason == "atr_emergency_exit"
    )
    reentry_count = _atr_reentry_count(trades)
    annualized_trade_count = 0.0 if len(nav) < 2 else len(trades) * TRADING_DAYS_PER_YEAR / (len(nav) - 1)
    commission_cost = sum(max(float(trade.commission), 0.0) for trade in trades)
    slippage_cost = sum(max(float(trade.slippage_cost), 0.0) for trade in trades)
    commission_cost = round(commission_cost, 6)
    slippage_cost = round(slippage_cost, 6)
    explicit_transaction_cost = commission_cost + slippage_cost

    return {
        "trade_count": len(trades),
        "closed_trade_count": closed_count,
        "complete_trade_count": closed_count,
        "win_rate": round(sum(value > 0 for value in returns) / closed_count, 6) if closed_count else 0.0,
        "avg_trade_return": round(sum(returns) / closed_count, 6) if closed_count else 0.0,
        "avg_holding_days": round(sum(holding_days) / closed_count, 6) if closed_count else 0.0,
        "annualized_trade_count": round(annualized_trade_count, 6),
        "trades_per_year": round(annualized_trade_count, 6),
        "cost_drag": explicit_transaction_cost,
        "explicit_transaction_cost": explicit_transaction_cost,
        "commission_cost": commission_cost,
        "slippage_cost": slippage_cost,
        "atr_exit_count": atr_exit_count,
        "reentry_count": reentry_count,
        "atr_reentry_count": reentry_count,
        "whipsaw_trade_count": whipsaw_count,
        "whipsaw_trade_denominator": closed_count,
        "whipsaw_trade_rate": round(whipsaw_count / closed_count, 6) if closed_count else 0.0,
    }


def _atr_reentry_count(trades: list[IndexBacktestTrade]) -> int:
    awaiting_reentry = False
    reentries = 0
    for trade in trades:
        if trade.action == "SELL" and trade.reason == "atr_emergency_exit":
            awaiting_reentry = True
        elif trade.action == "BUY" and awaiting_reentry:
            reentries += 1
            awaiting_reentry = False
    return reentries


def _date_text(value: pd.Timestamp) -> str:
    return pd.Timestamp(value).date().isoformat()
