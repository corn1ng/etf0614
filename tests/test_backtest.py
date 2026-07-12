import pandas as pd

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.strategy.models import StrategySignal


def test_backtest_executes_signal_on_next_trading_day_open():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [10.0, 11.0, 12.0],
            "high": [10.5, 11.5, 12.5],
            "low": [9.5, 10.5, 11.5],
            "close": [10.2, 11.2, 12.2],
            "volume": [1000, 1000, 1000],
            "amount": [1_000_000, 1_000_000, 1_000_000],
        }
    )
    signals = [
        StrategySignal(
            etf_code="510300",
            trade_date=pd.Timestamp("2024-01-02"),
            action="BUY",
            target_weight=0.10,
            reason="test",
            trigger_rules=["unit-test"],
        )
    ]

    result = BacktestEngine(initial_cash=1.0, commission_rate=0.0, slippage_rate=0.0).run_single_etf(
        etf_code="510300",
        prices=prices,
        signals=signals,
    )

    assert len(result.trades) == 1
    assert result.trades[0].trade_date == pd.Timestamp("2024-01-03")
    assert result.trades[0].price == 11.0
    assert result.trades[0].weight_after == 0.10


def test_backtest_reports_hong_kong_cross_market_exposure():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [10.0, 10.5, 11.0],
            "high": [10.5, 11.0, 11.5],
            "low": [9.5, 10.0, 10.5],
            "close": [10.2, 10.8, 11.2],
            "volume": [1000, 1000, 1000],
            "amount": [1_000_000, 1_000_000, 1_000_000],
        }
    )
    signals = [
        StrategySignal(
            etf_code="513130",
            trade_date=pd.Timestamp("2024-01-02"),
            action="BUY",
            target_weight=0.06,
            reason="test",
            trigger_rules=["unit-test"],
        )
    ]

    result = BacktestEngine(initial_cash=1.0, commission_rate=0.0, slippage_rate=0.0).run_single_etf(
        etf_code="513130",
        prices=prices,
        signals=signals,
        category="港股科技",
    )

    assert result.metrics["max_hk_cross_market_exposure"] == 0.06
