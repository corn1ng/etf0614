"""Small but strict ETF backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from etf_trading.strategy.models import StrategySignal
from etf_trading.universe.classification import is_hk_cross_market


@dataclass(frozen=True)
class Trade:
    etf_code: str
    trade_date: pd.Timestamp
    action: str
    price: float
    weight_before: float
    weight_after: float
    signal_date: pd.Timestamp


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    nav: pd.DataFrame = field(default_factory=pd.DataFrame)
    metrics: dict[str, float] = field(default_factory=dict)


class BacktestEngine:
    """Execute T-day close signals at T+1 open to avoid look-ahead bias."""

    def __init__(self, initial_cash: float = 1.0, commission_rate: float = 0.00015, slippage_rate: float = 0.0002) -> None:
        self.initial_cash = initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    def run_single_etf(
        self,
        etf_code: str,
        prices: pd.DataFrame,
        signals: list[StrategySignal],
        category: str = "A股宽基",
    ) -> BacktestResult:
        if prices.empty:
            return BacktestResult(metrics={"max_hk_cross_market_exposure": 0.0})

        frame = prices.copy()
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame = frame.sort_values("trade_date").reset_index(drop=True)

        signals_by_date = {pd.Timestamp(s.trade_date).normalize(): s for s in signals}
        cash = self.initial_cash
        shares = 0.0
        trades: list[Trade] = []
        nav_rows: list[dict[str, float | pd.Timestamp]] = []
        max_hk_trade_exposure = 0.0

        for idx, row in frame.iterrows():
            trade_date = pd.Timestamp(row["trade_date"]).normalize()
            open_price = float(row["open"])
            close_price = float(row["close"])

            if idx > 0:
                previous_date = pd.Timestamp(frame.loc[idx - 1, "trade_date"]).normalize()
                signal = signals_by_date.get(previous_date)
                if signal and signal.action in {"BUY", "SELL", "REDUCE"}:
                    execution_price = open_price * (1 + self.slippage_rate if signal.action == "BUY" else 1 - self.slippage_rate)
                    portfolio_value = cash + shares * execution_price
                    weight_before = 0.0 if portfolio_value == 0 else (shares * execution_price) / portfolio_value
                    target_weight = _target_weight_for_signal(signal, weight_before)
                    target_value = portfolio_value * target_weight
                    current_value = shares * execution_price
                    delta_value = target_value - current_value
                    commission = abs(delta_value) * self.commission_rate
                    shares += delta_value / execution_price
                    cash -= delta_value + commission
                    portfolio_after = cash + shares * execution_price
                    weight_after = 0.0 if portfolio_after == 0 else (shares * execution_price) / portfolio_after
                    trade = Trade(
                        etf_code=etf_code,
                        trade_date=trade_date,
                        action=signal.action,
                        price=round(execution_price, 6),
                        weight_before=round(weight_before, 4),
                        weight_after=round(weight_after, 4),
                        signal_date=pd.Timestamp(signal.trade_date).normalize(),
                    )
                    trades.append(trade)
                    if is_hk_cross_market(category):
                        max_hk_trade_exposure = max(max_hk_trade_exposure, trade.weight_after)

            nav = cash + shares * close_price
            weight = 0.0 if nav == 0 else (shares * close_price) / nav
            nav_rows.append({"trade_date": trade_date, "nav": nav, "weight": weight})

        nav_frame = pd.DataFrame(nav_rows)
        metrics = _metrics(nav_frame)
        metrics["max_hk_cross_market_exposure"] = round(max_hk_trade_exposure if is_hk_cross_market(category) else 0.0, 4)
        return BacktestResult(trades=trades, nav=nav_frame, metrics=metrics)


def _target_weight_for_signal(signal: StrategySignal, current_weight: float) -> float:
    if signal.action == "SELL":
        return 0.0
    if signal.action in {"BUY", "REDUCE"}:
        return signal.target_weight
    return current_weight


def _metrics(nav: pd.DataFrame) -> dict[str, float]:
    if nav.empty or len(nav) < 2:
        return {"total_return": 0.0, "max_drawdown": 0.0}
    returns = nav["nav"].pct_change().fillna(0.0)
    running_max = nav["nav"].cummax()
    drawdown = nav["nav"] / running_max - 1.0
    total_return = float(nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1.0)
    volatility = float(returns.std() * (252**0.5))
    return {
        "total_return": round(total_return, 6),
        "max_drawdown": round(float(drawdown.min()), 6),
        "volatility": round(volatility, 6),
    }
