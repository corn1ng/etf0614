"""SQLite and Parquet storage helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from etf_trading.data.index_catalog import IndexCatalogEntry


@dataclass(frozen=True)
class MaintenanceTaskRun:
    task_id: int
    task_type: str
    state: str
    progress_done: int
    progress_total: int
    progress_detail: str
    result_json: str | None
    error_message: str | None
    started_at: str
    finished_at: str | None
    updated_at: str


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

                CREATE TABLE IF NOT EXISTS maintenance_task_run (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'running',
                    progress_done INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    progress_detail TEXT NOT NULL DEFAULT '',
                    result_json TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_maintenance_task_run_type_time
                    ON maintenance_task_run(task_type, task_id DESC);

                CREATE TABLE IF NOT EXISTS index_catalog (
                    index_code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    category_level_1 TEXT NOT NULL,
                    category_level_2 TEXT NOT NULL,
                    index_type TEXT NOT NULL,
                    pool TEXT NOT NULL,
                    index_base_date TEXT,
                    baseline_source TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    provider_symbol TEXT NOT NULL,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS index_history_coverage (
                    index_code TEXT PRIMARY KEY,
                    index_base_date TEXT,
                    baseline_source TEXT NOT NULL,
                    local_first_trade_date TEXT,
                    source_first_trade_date TEXT,
                    latest_trade_date TEXT,
                    history_rows INTEGER NOT NULL DEFAULT 0,
                    completeness_status TEXT NOT NULL,
                    completeness_message TEXT NOT NULL,
                    validated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS index_etf_mapping (
                    index_code TEXT NOT NULL,
                    etf_code TEXT NOT NULL,
                    mapping_source TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    is_tradable INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (index_code, etf_code)
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

    def upsert_index_catalog(self, entries: Sequence[IndexCatalogEntry]) -> None:
        if not entries:
            return
        columns = [
            "index_code", "name", "market", "category_level_1", "category_level_2", "index_type", "pool",
            "index_base_date", "baseline_source", "source_kind", "provider_symbol", "aliases_json",
        ]
        rows = [
            (
                entry.index_code,
                entry.name,
                entry.market,
                entry.category_level_1,
                entry.category_level_2,
                entry.index_type,
                entry.pool,
                entry.index_base_date.isoformat() if entry.index_base_date else None,
                entry.baseline_source,
                entry.source_kind,
                entry.provider_symbol,
                json.dumps(entry.aliases, ensure_ascii=False),
            )
            for entry in entries
        ]
        placeholders = ",".join("?" for _ in columns)
        update_clause = ",".join(f"{column}=excluded.{column}" for column in columns if column != "index_code")
        with self.connect() as conn:
            conn.executemany(
                f"""
                INSERT INTO index_catalog ({",".join(columns)}) VALUES ({placeholders})
                ON CONFLICT(index_code) DO UPDATE SET {update_clause}, updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )

    def list_index_catalog(self, *, pool: str | None = None, include_reserve: bool = False) -> pd.DataFrame:
        clauses: list[str] = []
        values: list[object] = []
        if pool is not None:
            clauses.append("pool = ?")
            values.append(pool)
        elif not include_reserve:
            clauses.append("pool != 'reserve'")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return pd.read_sql_query(f"SELECT * FROM index_catalog{where} ORDER BY index_code", conn, params=values)

    def upsert_index_history_coverage(
        self,
        index_code: str,
        *,
        index_base_date: str | None,
        baseline_source: str,
        local_first_trade_date: str | None,
        source_first_trade_date: str | None,
        latest_trade_date: str | None,
        history_rows: int,
        completeness_status: str,
        completeness_message: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO index_history_coverage (
                    index_code, index_base_date, baseline_source, local_first_trade_date,
                    source_first_trade_date, latest_trade_date, history_rows,
                    completeness_status, completeness_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_code) DO UPDATE SET
                    index_base_date=excluded.index_base_date,
                    baseline_source=excluded.baseline_source,
                    local_first_trade_date=excluded.local_first_trade_date,
                    source_first_trade_date=excluded.source_first_trade_date,
                    latest_trade_date=excluded.latest_trade_date,
                    history_rows=excluded.history_rows,
                    completeness_status=excluded.completeness_status,
                    completeness_message=excluded.completeness_message,
                    validated_at=CURRENT_TIMESTAMP
                """,
                (
                    index_code, index_base_date, baseline_source, local_first_trade_date,
                    source_first_trade_date, latest_trade_date, history_rows,
                    completeness_status, completeness_message,
                ),
            )

    def list_index_history_coverage(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query("SELECT * FROM index_history_coverage ORDER BY index_code", conn)

    def replace_index_etf_mappings(
        self,
        frame: pd.DataFrame,
        *,
        index_codes: Sequence[str] | None = None,
    ) -> None:
        required = ["index_code", "etf_code", "mapping_source", "confidence", "is_tradable"]
        data = frame.copy()
        for column in required:
            if column not in data:
                data[column] = None
        data = data[required]
        target_codes = sorted({str(code) for code in (index_codes or data["index_code"].dropna().astype(str).tolist()) if code})
        if not target_codes:
            return
        with self.connect() as conn:
            conn.executemany("DELETE FROM index_etf_mapping WHERE index_code = ?", [(code,) for code in target_codes])
            if not data.empty:
                conn.executemany(
                    """
                    INSERT INTO index_etf_mapping (index_code, etf_code, mapping_source, confidence, is_tradable)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            str(row.index_code),
                            str(row.etf_code),
                            str(row.mapping_source),
                            str(row.confidence),
                            int(bool(row.is_tradable)),
                        )
                        for row in data.itertuples(index=False)
                    ],
                )

    def list_index_etf_mappings(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query("SELECT * FROM index_etf_mapping ORDER BY index_code, etf_code", conn)

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

    def create_maintenance_task_run(self, task_type: str, *, progress_total: int = 0) -> MaintenanceTaskRun:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO maintenance_task_run (task_type, progress_total)
                VALUES (?, ?)
                """,
                (task_type, progress_total),
            )
            task_id = int(cursor.lastrowid)
        task = self.get_maintenance_task_run(task_id)
        if task is None:  # pragma: no cover - SQLite insert/read contract
            raise RuntimeError(f"maintenance task {task_id} was not persisted")
        return task

    def get_maintenance_task_run(self, task_id: int) -> MaintenanceTaskRun | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM maintenance_task_run WHERE task_id = ?", (task_id,)).fetchone()
        return _maintenance_task_run_from_row(row)

    def get_latest_maintenance_task_run(self, task_type: str) -> MaintenanceTaskRun | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM maintenance_task_run WHERE task_type = ? ORDER BY task_id DESC LIMIT 1",
                (task_type,),
            ).fetchone()
        return _maintenance_task_run_from_row(row)

    def get_running_maintenance_task_run(self, task_type: str) -> MaintenanceTaskRun | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM maintenance_task_run WHERE task_type = ? AND state = 'running' ORDER BY task_id DESC LIMIT 1",
                (task_type,),
            ).fetchone()
        return _maintenance_task_run_from_row(row)

    def update_maintenance_task_run(
        self,
        task_id: int,
        *,
        state: str | None = None,
        progress_done: int | None = None,
        progress_total: int | None = None,
        progress_detail: str | None = None,
        result_json: str | None = None,
        error_message: str | None = None,
    ) -> MaintenanceTaskRun:
        updates: list[str] = []
        values: list[object] = []
        for column, value in (
            ("state", state),
            ("progress_done", progress_done),
            ("progress_total", progress_total),
            ("progress_detail", progress_detail),
            ("result_json", result_json),
            ("error_message", error_message),
        ):
            if value is not None:
                updates.append(f"{column} = ?")
                values.append(value)
        if state in {"success", "failed", "interrupted"}:
            updates.append("finished_at = CURRENT_TIMESTAMP")
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(task_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE maintenance_task_run SET {', '.join(updates)} WHERE task_id = ?", values)
        task = self.get_maintenance_task_run(task_id)
        if task is None:
            raise KeyError(f"unknown maintenance task {task_id}")
        return task

    def mark_maintenance_task_interrupted(self, task_id: int, message: str) -> MaintenanceTaskRun:
        return self.update_maintenance_task_run(task_id, state="interrupted", error_message=message)


def _maintenance_task_run_from_row(row: sqlite3.Row | None) -> MaintenanceTaskRun | None:
    if row is None:
        return None
    return MaintenanceTaskRun(
        task_id=int(row["task_id"]),
        task_type=str(row["task_type"]),
        state=str(row["state"]),
        progress_done=int(row["progress_done"]),
        progress_total=int(row["progress_total"]),
        progress_detail=str(row["progress_detail"] or ""),
        result_json=row["result_json"],
        error_message=row["error_message"],
        started_at=str(row["started_at"]),
        finished_at=row["finished_at"],
        updated_at=str(row["updated_at"]),
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

    def write_index_valuations(self, index_code: str, frame: pd.DataFrame) -> Path:
        path = self.root / "index_valuations" / f"{index_code}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_index_valuations(self, index_code: str) -> pd.DataFrame:
        path = self.root / "index_valuations" / f"{index_code}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def write_macro_series(self, series_name: str, frame: pd.DataFrame) -> Path:
        path = self.root / "macro" / f"{series_name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        return path

    def read_macro_series(self, series_name: str) -> pd.DataFrame:
        path = self.root / "macro" / f"{series_name}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)
