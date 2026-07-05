import pandas as pd

from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import SQLiteStore


def test_sqlite_store_persists_etf_master_and_watchlist(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    master = pd.DataFrame(
        [
            {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1},
            {"etf_code": "513130", "name": "恒生科技ETF", "exchange": "SSE", "category": "港股科技", "is_active": 1},
        ]
    )

    store.upsert_etf_master(master)
    store.set_watchlist("513130", enabled=True, allow_buy=True, category="港股科技")

    assert store.list_etf_master()["etf_code"].tolist() == ["510300", "513130"]
    watchlist = store.list_watchlist()
    assert watchlist.iloc[0]["etf_code"] == "513130"
    assert watchlist.iloc[0]["allow_buy"] == 1


def test_initialization_service_selects_one_sample_per_required_category(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1, "amount": 900},
                {"etf_code": "512010", "name": "医药ETF", "exchange": "SSE", "category": "A股行业", "is_active": 1, "amount": 800},
                {"etf_code": "159920", "name": "恒生ETF", "exchange": "SZSE", "category": "港股宽基", "is_active": 1, "amount": 700},
                {"etf_code": "513130", "name": "恒生科技ETF", "exchange": "SSE", "category": "港股科技", "is_active": 1, "amount": 1000},
                {"etf_code": "513060", "name": "恒生医疗ETF", "exchange": "SSE", "category": "港股医药", "is_active": 1, "amount": 600},
            ]
        )
    )

    service = InitializationService(store)
    samples = service.select_sample_etfs(["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药"])

    assert samples["category"].tolist() == ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药"]
    assert samples[samples["category"] == "港股科技"].iloc[0]["etf_code"] == "513130"


def test_initialization_service_creates_history_jobs_for_all_master_etfs(tmp_path):
    store = SQLiteStore(tmp_path / "etf.sqlite")
    store.initialize_schema()
    store.upsert_etf_master(
        pd.DataFrame(
            [
                {"etf_code": "510300", "name": "沪深300ETF", "exchange": "SSE", "category": "A股宽基", "is_active": 1},
                {"etf_code": "512880", "name": "证券ETF", "exchange": "SSE", "category": "A股行业", "is_active": 1},
            ]
        )
    )

    count = InitializationService(store).create_history_jobs_for_all_master("2021-01-01", "2026-07-03")

    assert count == 2
    with store.connect() as conn:
        jobs = pd.read_sql_query("SELECT job_type, asset_code, start_date, end_date FROM data_fetch_job ORDER BY asset_code", conn)
    assert jobs["asset_code"].tolist() == ["510300", "512880"]
    assert jobs["job_type"].tolist() == ["history", "history"]
