from etf_trading.data.storage import SQLiteStore


def main() -> None:
    store = SQLiteStore()
    store.initialize_schema()
    print(f"Initialized database at {store.db_path}")


if __name__ == "__main__":
    main()
