"""Metric calculations for strategy research runs."""

from __future__ import annotations

import math

import pandas as pd

from etf_trading.backtest.engine import BacktestResult, Trade


TRADING_DAYS_PER_YEAR = 252


def summarize_backtest(result: BacktestResult) -> dict[str, float]:
    """Return return, risk, exposure, and trade-quality metrics."""

    nav = _normalized_nav(result.nav)
    metrics = _nav_metrics(nav)
    trade_metrics = _trade_metrics(result.trades)
    metrics.update(trade_metrics)
    return metrics


def summarize_nav_by_year(nav: pd.DataFrame) -> pd.DataFrame:
    """Return NAV metrics grouped by calendar year."""

    frame = _normalized_nav(nav)
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | int]] = []
    for year, segment in frame.groupby(frame["trade_date"].dt.year):
        row = {"year": int(year)}
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
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["nav"] = frame["nav"].astype(float)
    if "weight" not in frame.columns:
        frame["weight"] = 0.0
    frame["weight"] = frame["weight"].astype(float)
    return frame.sort_values("trade_date").reset_index(drop=True)


def _nav_metrics(nav: pd.DataFrame) -> dict[str, float]:
    if nav.empty or len(nav) < 2:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "avg_exposure": 0.0,
        }

    start_nav = float(nav["nav"].iloc[0])
    end_nav = float(nav["nav"].iloc[-1])
    total_return = 0.0 if start_nav == 0 else end_nav / start_nav - 1.0

    days = max((nav["trade_date"].iloc[-1] - nav["trade_date"].iloc[0]).days, 0)
    annualized_return = _annualized_return(total_return, days)

    returns = nav["nav"].pct_change().fillna(0.0)
    volatility = float(returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR))
    sharpe = 0.0 if volatility == 0 else annualized_return / volatility

    running_max = nav["nav"].cummax()
    drawdown = nav["nav"] / running_max - 1.0
    max_drawdown = float(drawdown.min())
    calmar = 0.0 if max_drawdown == 0 else annualized_return / abs(max_drawdown)

    return {
        "total_return": round(float(total_return), 6),
        "annualized_return": round(float(annualized_return), 6),
        "volatility": round(volatility, 6),
        "sharpe": round(float(sharpe), 6),
        "max_drawdown": round(max_drawdown, 6),
        "calmar": round(float(calmar), 6),
        "avg_exposure": round(float(nav["weight"].mean()), 6),
    }


def _annualized_return(total_return: float, days: int) -> float:
    if days <= 0:
        return 0.0
    if total_return <= -1.0:
        return -1.0
    return (1.0 + total_return) ** (365.25 / days) - 1.0


def _trade_metrics(trades: list[Trade]) -> dict[str, float]:
    closed_returns: list[float] = []
    holding_days: list[float] = []
    open_trade: Trade | None = None

    for trade in trades:
        if trade.action == "BUY":
            open_trade = trade
            continue
        if trade.action != "SELL" or open_trade is None:
            continue
        if open_trade.price != 0:
            closed_returns.append(trade.price / open_trade.price - 1.0)
        holding_days.append(float((trade.trade_date - open_trade.trade_date).days))
        open_trade = None

    wins = sum(1 for value in closed_returns if value > 0)
    closed_count = len(closed_returns)
    return {
        "trade_count": float(len(trades)),
        "closed_trade_count": float(closed_count),
        "win_rate": round(wins / closed_count, 6) if closed_count else 0.0,
        "avg_trade_return": round(float(sum(closed_returns) / closed_count), 6) if closed_count else 0.0,
        "avg_holding_days": round(float(sum(holding_days) / len(holding_days)), 6) if holding_days else 0.0,
    }
