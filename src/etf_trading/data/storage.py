"""SQLite and Parquet storage helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


class SQLiteStore:
    def __init__(self, db_path: str | Path = "database/etf_system.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS etf_master (
                    etf_code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    exchange TEXT,
                    category TEXT,
                    tracking_index TEXT,
                    fund_company TEXT,
                    listing_date TEXT,
                    is_active INTEGER DEFAULT 1,
                    amount REAL,
                    volume REAL,
                    latest_price REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_etf_watchlist (
                    etf_code TEXT PRIMARY KEY,
                    enabled INTEGER DEFAULT 1,
                    allow_buy INTEGER DEFAULT 1,
                    category TEXT,
                    note TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS data_update_state (
                    dataset TEXT NOT NULL,
                    asset_code TEXT NOT NULL,
                    last_success_trade_date TEXT,
                    status TEXT DEFAULT 'PENDING',
                    error_message TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (dataset, asset_code)
                );

                CREATE TABLE IF NOT EXISTS data_fetch_job (
                    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_type TEXT NOT NULL,
                    asset_code TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'PENDING',
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS strategy_signal (
                    etf_code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_weight REAL NOT NULL,
                    reason TEXT,
                    trigger_rules TEXT,
                    risk_tags TEXT,
                    PRIMARY KEY (etf_code, trade_date, action)
                );

                CREATE TABLE IF NOT EXISTS daily_trade_advice (
                    advice_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    etf_code TEXT,
                    action TEXT NOT NULL,
                    target_weight REAL,
                    reason TEXT,
                    priority INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS data_quality_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT,
                    dataset TEXT,
                    asset_code TEXT,
                    severity TEXT,
                    message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def upsert_etf_master(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        columns = [
            "etf_code",
            "name",
            "exchange",
            "category",
            "tracking_index",
            "fund_company",
            "listing_date",
            "is_active",
            "amount",
            "volume",
            "latest_price",
        ]
        data = frame.copy()
        for column in columns:
            if column not in data.columns:
                data[column] = None
        data = data[columns]
        placeholders = ",".join("?" for _ in columns)
        update_clause = ",".join(f"{c}=excluded.{c}" for c in columns if c != "etf_code")
        sql = f"""
            INSERT INTO etf_master ({",".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(etf_code) DO UPDATE SET {update_clause}, updated_at=CURRENT_TIMESTAMP
        """
        with self.connect() as conn:
            conn.executemany(sql, data.itertuples(index=False, name=None))

    def list_etf_master(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query("SELECT * FROM etf_master ORDER BY etf_code", conn)

    def set_watchlist(self, etf_code: str, enabled: bool, allow_buy: bool, category: str | None = None, note: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_etf_watchlist (etf_code, enabled, allow_buy, category, note)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(etf_code) DO UPDATE SET
                    enabled=excluded.enabled,
                    allow_buy=excluded.allow_buy,
                    category=excluded.category,
                    note=excluded.note,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (etf_code, int(enabled), int(allow_buy), category, note),
            )

    def list_watchlist(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                """
                SELECT w.etf_code, COALESCE(w.category, m.category) AS category, w.enabled, w.allow_buy, w.note, m.name, m.exchange
                FROM user_etf_watchlist w
                LEFT JOIN etf_master m ON m.etf_code = w.etf_code
                ORDER BY w.etf_code
                """,
                conn,
            )

    def upsert_update_state(self, dataset: str, asset_code: str, last_success_trade_date: str | None, status: str = "SUCCESS", error_message: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO data_update_state (dataset, asset_code, last_success_trade_date, status, error_message)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(dataset, asset_code) DO UPDATE SET
                    last_success_trade_date=excluded.last_success_trade_date,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (dataset, asset_code, last_success_trade_date, status, error_message),
            )

    def create_fetch_job(self, job_type: str, asset_code: str | None, start_date: str | None, end_date: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO data_fetch_job (job_type, asset_code, start_date, end_date)
                VALUES (?, ?, ?, ?)
                """,
                (job_type, asset_code, start_date, end_date),
            )


class ParquetStore:
    def __init__(self, root: str | Path = "data/parquet") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_prices(self, etf_code: str, frame: pd.DataFrame) -> Path:
        path = self.root / "prices" / f"{etf_code}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_prices(self, etf_code: str) -> pd.DataFrame:
        path = self.root / "prices" / f"{etf_code}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def write_index_prices(self, index_code: str, frame: pd.DataFrame) -> Path:
        path = self.root / "indexes" / f"{index_code}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_index_prices(self, index_code: str) -> pd.DataFrame:
        path = self.root / "indexes" / f"{index_code}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
