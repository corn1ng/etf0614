from datetime import date, timedelta

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.data.storage import ParquetStore
from etf_trading.strategy.models import StrategySignal


def main() -> None:
    etf_code = input("ETF code: ").strip()
    prices = ParquetStore().read_prices(etf_code)
    if prices.empty:
        raise SystemExit(f"No local history for {etf_code}. Initialize data first.")
    signal = StrategySignal(
        etf_code=etf_code,
        trade_date=prices["trade_date"].min(),
        action="BUY",
        target_weight=0.06,
        reason="manual script backtest",
        trigger_rules=["manual"],
    )
    result = BacktestEngine().run_single_etf(etf_code, prices, [signal])
    print(result.metrics)
    print(result.trades[:5])


if __name__ == "__main__":
    main()
