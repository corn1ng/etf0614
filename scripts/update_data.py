from datetime import date, timedelta

from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore


def main() -> None:
    store = SQLiteStore()
    store.initialize_schema()
    provider = AkShareProvider()
    parquet = ParquetStore()
    service = InitializationService(store=store, provider=provider, parquet_store=parquet)
    if store.list_etf_master().empty:
        master = service.initialize_master()
        print(f"Initialized ETF master: {len(master)} rows")
    watchlist = store.list_watchlist()
    if watchlist.empty:
        print("Watchlist is empty; select ETFs in the Streamlit workbench first.")
        return
    start = date.today() - timedelta(days=365 * 5)
    end = date.today()
    for row in watchlist.itertuples(index=False):
        if not row.enabled:
            continue
        try:
            frame = service.fetch_and_store_history(row.etf_code, start, end)
        except Exception as exc:  # noqa: BLE001
            store.upsert_update_state("etf_daily_price", row.etf_code, None, status="FAILED", error_message=str(exc))
            print(f"{row.etf_code}: failed: {exc}")
            continue
        print(f"{row.etf_code}: stored {len(frame)} rows")


if __name__ == "__main__":
    main()
