"""Initialization and catch-up task services."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, INDEX_HISTORY_AUTO_START
from etf_trading.data.provider import DataProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.strategy.features import add_technical_features


REQUIRED_ETF_HISTORY_COLUMNS = {
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "ma20",
    "ma60",
    "return_20",
    "return_60",
    "avg_amount_5",
    "avg_amount_20",
    "amount_ratio_5_20",
    "atr20",
    "distance_ma20_atr",
    "distance_ma20_pct",
    "rolling_high_close_60",
    "is_60d_close_breakout",
}


@dataclass(frozen=True)
class IndexHistoryResult:
    index_code: str
    status: str
    fetched_rows: int
    total_rows: int
    start_date: date | None = None
    end_date: date | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class EtfHistoryResult:
    etf_code: str
    status: str
    fetched_rows: int
    total_rows: int
    start_date: date | None = None
    end_date: date | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class EtfHistoryProgress:
    done: int
    total: int
    etf_code: str
    status: str


class InitializationService:
    def __init__(
        self,
        store: SQLiteStore,
        provider: DataProvider | None = None,
        parquet_store: ParquetStore | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.parquet_store = parquet_store or ParquetStore()

    def initialize_master(self) -> pd.DataFrame:
        if self.provider is None:
            raise ValueError("provider is required to initialize ETF master")
        self.store.initialize_schema()
        master = self.provider.fetch_etf_list()
        self.store.upsert_etf_master(master)
        return master

    def select_sample_etfs(self, required_categories: list[str]) -> pd.DataFrame:
        master = self.store.list_etf_master()
        if master.empty:
            return master
        if "amount" not in master.columns:
            master["amount"] = 0
        master["amount"] = pd.to_numeric(master["amount"], errors="coerce").fillna(0)
        rows = []
        for category in required_categories:
            candidates = master[(master["category"] == category) & (master["is_active"].fillna(1).astype(int) == 1)]
            if candidates.empty:
                continue
            rows.append(candidates.sort_values(["amount", "etf_code"], ascending=[False, True]).iloc[0])
        if not rows:
            return pd.DataFrame(columns=master.columns)
        return pd.DataFrame(rows).reset_index(drop=True)

    def create_history_jobs_for_watchlist(self, start_date: date | str | None = None, end_date: date | str | None = None) -> int:
        watchlist = self.store.list_watchlist()
        count = 0
        for row in watchlist.itertuples(index=False):
            self.store.create_fetch_job("history", row.etf_code, str(start_date) if start_date else None, str(end_date) if end_date else None)
            count += 1
        return count

    def create_history_jobs_for_all_master(self, start_date: date | str | None = None, end_date: date | str | None = None) -> int:
        master = self.store.list_etf_master()
        if master.empty or "etf_code" not in master.columns:
            return 0
        if "is_active" in master.columns:
            master = master[master["is_active"].fillna(1).astype(int) == 1]
        if "tradability_status" in master.columns:
            master = master[master["tradability_status"].fillna("exchange_traded").astype(str).isin(["", "exchange_traded"])]

        count = 0
        codes = master["etf_code"].astype(str).str.zfill(6).drop_duplicates().sort_values()
        for code in codes:
            self.store.create_fetch_job("history", code, str(start_date) if start_date else None, str(end_date) if end_date else None)
            count += 1
        return count

    def fetch_and_store_history(self, etf_code: str, start_date: date | str, end_date: date | str, adjust: str = "qfq") -> pd.DataFrame:
        if self.provider is None:
            raise ValueError("provider is required to fetch history")
        prices = self.provider.fetch_etf_daily(etf_code, start_date, end_date, adjust=adjust)
        features = add_technical_features(prices)
        self.parquet_store.write_prices(etf_code, features)
        if not features.empty:
            last_date = pd.Timestamp(features["trade_date"].max()).strftime("%Y-%m-%d")
            self.store.upsert_update_state("etf_daily_price", etf_code, last_date)
        return features

    def ensure_all_etf_history(
        self,
        start_date: date | str,
        through: date | str,
        *,
        refresh_master: bool = False,
        sleep_seconds: float = 0.0,
        on_progress: Callable[[EtfHistoryProgress], None] | None = None,
    ) -> pd.DataFrame:
        if self.provider is None:
            raise ValueError("provider is required to fetch ETF history")

        self.store.initialize_schema()
        master = self.store.list_etf_master()
        if refresh_master or master.empty:
            try:
                self.initialize_master()
            except Exception:
                if master.empty:
                    raise
            else:
                master = self.store.list_etf_master()

        codes = _active_master_etf_codes(master)
        expected_latest = _expected_latest_trade_date(through)
        results: list[EtfHistoryResult] = []
        total = len(codes)

        for done, etf_code in enumerate(codes, start=1):
            result = self._ensure_etf_history(etf_code, start_date, through, expected_latest)
            results.append(result)
            if on_progress is not None:
                on_progress(EtfHistoryProgress(done=done, total=total, etf_code=etf_code, status=result.status))
            if sleep_seconds > 0 and done < total:
                time.sleep(sleep_seconds)

        return pd.DataFrame([result.__dict__ for result in results])

    def _ensure_etf_history(self, etf_code: str, start_date: date | str, through: date | str, expected_latest: pd.Timestamp) -> EtfHistoryResult:
        try:
            existing = self.parquet_store.read_prices(etf_code)
            if _is_fresh_etf_history(existing, expected_latest):
                first_date = pd.Timestamp(existing["trade_date"].min()).date()
                last_date = pd.Timestamp(existing["trade_date"].max()).date()
                self.store.upsert_update_state("etf_daily_price", etf_code, last_date.isoformat(), status="SUCCESS")
                return EtfHistoryResult(
                    etf_code=etf_code,
                    status="SKIPPED",
                    fetched_rows=0,
                    total_rows=len(existing),
                    start_date=first_date,
                    end_date=last_date,
                )

            status = "INITIALIZED" if existing.empty else "UPDATED"
            features = self.fetch_and_store_history(etf_code, start_date, through)
            if features.empty:
                self.store.upsert_update_state("etf_daily_price", etf_code, None, status="EMPTY")
                return EtfHistoryResult(etf_code=etf_code, status="EMPTY", fetched_rows=0, total_rows=0)

            first_date = pd.Timestamp(features["trade_date"].min()).date()
            last_date = pd.Timestamp(features["trade_date"].max()).date()
            return EtfHistoryResult(
                etf_code=etf_code,
                status=status,
                fetched_rows=len(features),
                total_rows=len(features),
                start_date=first_date,
                end_date=last_date,
            )
        except Exception as exc:  # noqa: BLE001 - one ETF must not stop the whole batch
            message = str(exc)
            self.store.upsert_update_state("etf_daily_price", etf_code, None, status="FAILED", error_message=message[:1000])
            return EtfHistoryResult(
                etf_code=etf_code,
                status="FAILED",
                fetched_rows=0,
                total_rows=0,
                error_message=message,
            )

    def ensure_index_history(self, index_code: str, through: date | str) -> IndexHistoryResult:
        if self.provider is None:
            raise ValueError("provider is required to fetch index history")

        through_date = pd.Timestamp(through).date()
        existing = self.parquet_store.read_index_prices(index_code)

        if existing.empty:
            fetch_start: date | str = INDEX_HISTORY_AUTO_START
            status = "INITIALIZED"
        else:
            existing = _normalize_existing_index_frame(existing, index_code)
            last_date = pd.Timestamp(existing["trade_date"].max()).date()
            if last_date >= through_date:
                self.store.upsert_update_state("index_daily_price", index_code, last_date.isoformat(), status="SUCCESS")
                return IndexHistoryResult(
                    index_code=index_code,
                    status="SKIPPED",
                    fetched_rows=0,
                    total_rows=len(existing),
                    start_date=pd.Timestamp(existing["trade_date"].min()).date(),
                    end_date=last_date,
                )
            fetch_start = last_date + timedelta(days=1)
            status = "UPDATED"

        fetched = self.provider.fetch_index_daily(index_code, fetch_start, through_date)
        fetched_rows = len(fetched)
        if existing.empty:
            combined = fetched
        else:
            combined = pd.concat([existing, fetched], ignore_index=True)
        combined = _normalize_existing_index_frame(combined, index_code)
        featured = add_technical_features(combined.rename(columns={"index_code": "etf_code"})).rename(columns={"etf_code": "index_code"})
        self.parquet_store.write_index_prices(index_code, featured)

        if featured.empty:
            self.store.upsert_update_state("index_daily_price", index_code, None, status="EMPTY")
            return IndexHistoryResult(index_code=index_code, status="EMPTY", fetched_rows=0, total_rows=0)

        first_date = pd.Timestamp(featured["trade_date"].min()).date()
        last_date = pd.Timestamp(featured["trade_date"].max()).date()
        self.store.upsert_update_state("index_daily_price", index_code, last_date.isoformat(), status="SUCCESS")
        return IndexHistoryResult(
            index_code=index_code,
            status=status,
            fetched_rows=fetched_rows,
            total_rows=len(featured),
            start_date=first_date,
            end_date=last_date,
        )

    def ensure_all_index_history(self, through: date | str, index_codes: list[str] | None = None) -> pd.DataFrame:
        codes = index_codes or [item.index_code for item in DEFAULT_INDEXES]
        results: list[IndexHistoryResult] = []
        for index_code in codes:
            try:
                results.append(self.ensure_index_history(index_code, through))
            except Exception as exc:  # noqa: BLE001 - one failed index must not block the whole batch
                self.store.upsert_update_state("index_daily_price", index_code, None, status="FAILED", error_message=str(exc))
                results.append(
                    IndexHistoryResult(
                        index_code=index_code,
                        status="FAILED",
                        fetched_rows=0,
                        total_rows=0,
                        error_message=str(exc),
                    )
                )
        return pd.DataFrame([result.__dict__ for result in results])


def _normalize_existing_index_frame(frame: pd.DataFrame, index_code: str) -> pd.DataFrame:
    result = frame.copy()
    if "index_code" not in result.columns:
        result["index_code"] = index_code
    result["index_code"] = result["index_code"].fillna(index_code)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.drop_duplicates(subset=["index_code", "trade_date"], keep="last")
    return result.sort_values("trade_date").reset_index(drop=True)


def _active_master_etf_codes(master: pd.DataFrame) -> list[str]:
    if master.empty or "etf_code" not in master.columns:
        return []

    result = master.copy()
    if "is_active" in result.columns:
        result = result[result["is_active"].fillna(1).astype(int) == 1]
    if "tradability_status" in result.columns:
        result = result[result["tradability_status"].fillna("exchange_traded").astype(str).isin(["", "exchange_traded"])]
    return result["etf_code"].astype(str).str.zfill(6).drop_duplicates().sort_values().tolist()


def _expected_latest_trade_date(value: date | str | pd.Timestamp) -> pd.Timestamp:
    current = pd.Timestamp(value).normalize()
    while current.weekday() >= 5:
        current = current - pd.Timedelta(days=1)
    return current


def _is_fresh_etf_history(frame: pd.DataFrame, expected_latest: pd.Timestamp) -> bool:
    if frame.empty or not REQUIRED_ETF_HISTORY_COLUMNS.issubset(frame.columns):
        return False
    latest = pd.to_datetime(frame["trade_date"], errors="coerce").dropna().max()
    return bool(pd.notna(latest) and pd.Timestamp(latest).normalize() >= expected_latest)
