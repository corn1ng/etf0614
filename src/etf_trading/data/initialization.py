"""Initialization and catch-up task services."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

import pandas as pd

from etf_trading.data.baseline_evidence import BaselineEvidenceResolver, write_baseline_evidence
from etf_trading.data.index_catalog import (
    DEFAULT_BASELINE_EVIDENCE_PATH,
    IndexCatalogEntry,
    catalog_entries_from_frame,
    default_index_catalog,
)
from etf_trading.data.indexes import INDEX_HISTORY_AUTO_START
from etf_trading.data.provider import DataProvider
from etf_trading.data.quality import (
    IndexHistoryCompleteness,
    assess_index_history_completeness,
    expected_latest_trade_date,
    has_official_baseline,
    index_history_freshness_message,
)
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
    completeness_status: str | None = None
    completeness_message: str | None = None


@dataclass(frozen=True)
class IndexHistoryProgress:
    done: int
    total: int
    index_code: str
    status: str


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
        self.evidence_resolver = BaselineEvidenceResolver()

    def initialize_master(self) -> pd.DataFrame:
        if self.provider is None:
            raise ValueError("provider is required to initialize ETF master")
        self.store.initialize_schema()
        master = self.provider.fetch_etf_list()
        self.store.upsert_etf_master(master)
        return master

    def sync_index_catalog(self, entries: Sequence[IndexCatalogEntry] | None = None) -> pd.DataFrame:
        """Persist the versioned index catalogue for use across server restarts."""

        catalog = tuple(entries or default_index_catalog())
        self.store.initialize_schema()
        self.store.upsert_index_catalog(catalog)
        return self.store.list_index_catalog(include_reserve=True)

    def validate_index_sources(
        self,
        through: date | str,
        entries: Sequence[IndexCatalogEntry] | None = None,
    ) -> pd.DataFrame:
        """Probe each configured source over the last ten calendar days only."""

        if self.provider is None:
            raise ValueError("provider is required to validate index sources")

        self.store.initialize_schema()
        catalog = tuple(entries or self._formal_catalog_entries())
        through_date = pd.Timestamp(through).date()
        start_date = through_date - timedelta(days=9)
        results: list[dict[str, object]] = []
        for entry in catalog:
            try:
                frame = self.provider.fetch_index_daily(entry, start_date, through_date)
                latest = _frame_latest_trade_date(frame)
                if frame.empty or latest is None:
                    status, message, latest_text = "EMPTY", "最近十日未返回行情", None
                else:
                    status, message, latest_text = "SUCCESS", "数据源可用", latest.isoformat()
                self.store.upsert_update_state(
                    "index_source_validation",
                    entry.index_code,
                    latest_text,
                    status=status,
                    error_message=None if status == "SUCCESS" else message,
                )
            except Exception as exc:  # noqa: BLE001 - validation continues for all catalogue entries
                status, message, latest_text = "FAILED", str(exc), None
                self.store.upsert_update_state(
                    "index_source_validation",
                    entry.index_code,
                    None,
                    status=status,
                    error_message=message[:1000],
                )
            results.append(
                {
                    "index_code": entry.index_code,
                    "source_kind": entry.source_kind,
                    "status": status,
                    "latest_trade_date": latest_text,
                    "message": message,
                }
            )
        return pd.DataFrame(results)

    def verify_index_baseline_evidence(
        self,
        through: date | str,
        write_evidence: bool = True,
    ) -> pd.DataFrame:
        """Reassess cached index coverage after resolving baseline evidence only."""

        self.store.initialize_schema()
        catalog = self._formal_catalog_entries()
        checked_at = pd.Timestamp(through).date()
        evidence = self.evidence_resolver.collect(catalog, checked_at)
        if write_evidence:
            write_baseline_evidence(DEFAULT_BASELINE_EVIDENCE_PATH, evidence)

        synchronized = tuple(_entry_with_resolved_evidence(entry, evidence) for entry in catalog)
        self.sync_index_catalog(synchronized)
        refreshed_catalog = self._formal_catalog_entries()
        covered_codes = set(
            self.store.list_index_history_coverage().get("index_code", pd.Series(dtype=str)).astype(str)
        )
        evidence_by_code = {
            str(row.get("index_code") or ""): row
            for row in evidence.to_dict(orient="records")
        }
        results: list[dict[str, object]] = []
        for entry in refreshed_catalog:
            record = dict(evidence_by_code.get(entry.index_code, {}))
            record["index_code"] = entry.index_code
            frame = self.parquet_store.read_index_prices(entry.index_code)
            if not frame.empty or entry.index_code in covered_codes:
                completeness = self._persist_index_history_coverage(entry, frame)
                record.update(
                    {
                        "completeness_status": completeness.status,
                        "completeness_message": completeness.message,
                        "local_first_trade_date": completeness.local_first_trade_date,
                        "latest_trade_date": completeness.latest_trade_date,
                        "history_rows": completeness.history_rows,
                    }
                )
            results.append(record)
        return pd.DataFrame(results)

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

    def ensure_index_history(
        self,
        index_code: str,
        through: date | str,
        *,
        repair_history: bool = False,
    ) -> IndexHistoryResult:
        if self.provider is None:
            raise ValueError("provider is required to fetch index history")

        self.store.initialize_schema()
        entry = self._catalog_entry(index_code)
        through_date = pd.Timestamp(through).date()
        expected_date = expected_latest_trade_date(through_date).date()
        existing = self.parquet_store.read_index_prices(entry.index_code)

        if existing.empty:
            fetch_start: date | str = INDEX_HISTORY_AUTO_START
            status = "INITIALIZED"
        else:
            existing = _normalize_existing_index_frame(existing, entry.index_code)
            last_date = pd.Timestamp(existing["trade_date"].max()).date()
            if last_date >= expected_date and not repair_history:
                completeness = self._persist_index_history_coverage(entry, existing)
                self.store.upsert_update_state("index_daily_price", entry.index_code, last_date.isoformat(), status="SUCCESS")
                return IndexHistoryResult(
                    index_code=entry.index_code,
                    status="SKIPPED",
                    fetched_rows=0,
                    total_rows=len(existing),
                    start_date=pd.Timestamp(existing["trade_date"].min()).date(),
                    end_date=last_date,
                    completeness_status=completeness.status,
                    completeness_message=completeness.message,
                )
            fetch_start = INDEX_HISTORY_AUTO_START if repair_history else last_date + timedelta(days=1)
            status = "REPAIRED" if repair_history else "UPDATED"

        fetched = self.provider.fetch_index_daily(entry, fetch_start, through_date)
        fetched_rows = len(fetched)
        if not fetched.empty:
            fetched = _normalize_existing_index_frame(fetched, entry.index_code)
            fetched["index_code"] = entry.index_code
        if fetched.empty and not existing.empty:
            completeness = self._persist_index_history_coverage(entry, existing)
            return self._stale_index_result(entry.index_code, existing, expected_date, fetched_rows, completeness)
        combined = fetched if existing.empty else pd.concat([existing, fetched], ignore_index=True)
        if combined.empty:
            completeness = self._persist_index_history_coverage(entry, combined)
            self.store.upsert_update_state(
                "index_daily_price",
                entry.index_code,
                None,
                status="EMPTY",
                error_message=completeness.message,
            )
            return IndexHistoryResult(
                index_code=entry.index_code,
                status="EMPTY",
                fetched_rows=0,
                total_rows=0,
                error_message=completeness.message,
                completeness_status=completeness.status,
                completeness_message=completeness.message,
            )

        combined = _normalize_existing_index_frame(combined, entry.index_code)
        featured = add_technical_features(combined.rename(columns={"index_code": "etf_code"})).rename(columns={"etf_code": "index_code"})
        self.parquet_store.write_index_prices(entry.index_code, featured)
        completeness = self._persist_index_history_coverage(entry, featured, source_frame=fetched)

        first_date = pd.Timestamp(featured["trade_date"].min()).date()
        last_date = pd.Timestamp(featured["trade_date"].max()).date()
        if last_date < expected_date:
            return self._stale_index_result(entry.index_code, featured, expected_date, fetched_rows, completeness)
        self.store.upsert_update_state("index_daily_price", entry.index_code, last_date.isoformat(), status="SUCCESS")
        return IndexHistoryResult(
            index_code=entry.index_code,
            status=status,
            fetched_rows=fetched_rows,
            total_rows=len(featured),
            start_date=first_date,
            end_date=last_date,
            completeness_status=completeness.status,
            completeness_message=completeness.message,
        )

    def _stale_index_result(
        self,
        index_code: str,
        frame: pd.DataFrame,
        expected_date: date,
        fetched_rows: int,
        completeness: IndexHistoryCompleteness,
    ) -> IndexHistoryResult:
        first_date = pd.Timestamp(frame["trade_date"].min()).date()
        last_date = pd.Timestamp(frame["trade_date"].max()).date()
        message = index_history_freshness_message(last_date, expected_date)
        self.store.upsert_update_state(
            "index_daily_price",
            index_code,
            last_date.isoformat(),
            status="STALE",
            error_message=message,
        )
        return IndexHistoryResult(
            index_code=index_code,
            status="STALE",
            fetched_rows=fetched_rows,
            total_rows=len(frame),
            start_date=first_date,
            end_date=last_date,
            error_message=message,
            completeness_status=completeness.status,
            completeness_message=completeness.message,
        )

    def ensure_all_index_history(
        self,
        through: date | str,
        index_codes: list[str] | None = None,
        *,
        repair_history: bool = False,
        on_progress: Callable[[IndexHistoryProgress], None] | None = None,
    ) -> pd.DataFrame:
        codes = index_codes or [entry.index_code for entry in self._formal_catalog_entries()]
        results: list[IndexHistoryResult] = []
        total = len(codes)
        for done, index_code in enumerate(codes, start=1):
            try:
                result = self.ensure_index_history(index_code, through, repair_history=repair_history)
            except Exception as exc:  # noqa: BLE001 - one failed index must not block the whole batch
                self.store.upsert_update_state("index_daily_price", index_code, None, status="FAILED", error_message=str(exc))
                result = IndexHistoryResult(
                    index_code=index_code,
                    status="FAILED",
                    fetched_rows=0,
                    total_rows=0,
                    error_message=str(exc),
                )
            results.append(result)
            if on_progress is not None:
                on_progress(IndexHistoryProgress(done=done, total=total, index_code=index_code, status=result.status))
        return pd.DataFrame([result.__dict__ for result in results])

    def _formal_catalog_entries(self) -> tuple[IndexCatalogEntry, ...]:
        self.store.initialize_schema()
        catalog = self.store.list_index_catalog()
        if catalog.empty:
            self.sync_index_catalog()
            catalog = self.store.list_index_catalog()
        return catalog_entries_from_frame(catalog)

    def _catalog_entry(self, index_code: str) -> IndexCatalogEntry:
        normalized_code = str(index_code)
        catalog = self.store.list_index_catalog(include_reserve=True)
        if not catalog.empty:
            matched = catalog[catalog["index_code"].astype(str) == normalized_code]
            if not matched.empty:
                return catalog_entries_from_frame(matched)[0]
        for entry in default_index_catalog():
            if entry.index_code == normalized_code:
                return entry
        raise KeyError(f"Unknown index code: {normalized_code}")

    def _persist_index_history_coverage(
        self,
        entry: IndexCatalogEntry,
        frame: pd.DataFrame,
        *,
        source_frame: pd.DataFrame | None = None,
    ) -> IndexHistoryCompleteness:
        completeness = assess_index_history_completeness(
            frame,
            entry.index_base_date,
            baseline_source=entry.baseline_source,
            index_code=entry.index_code,
            source_kind=entry.source_kind,
            evidence_name=entry.baseline_evidence_name,
            evidence_kind=entry.baseline_evidence_kind,
        )
        source_first = _frame_first_trade_date(source_frame) if source_frame is not None else None
        self.store.upsert_index_history_coverage(
            entry.index_code,
            **completeness.to_storage_values(source_first_trade_date=source_first),
        )
        return completeness


def _normalize_existing_index_frame(frame: pd.DataFrame, index_code: str) -> pd.DataFrame:
    result = frame.copy()
    if "index_code" not in result.columns:
        result["index_code"] = index_code
    result["index_code"] = result["index_code"].fillna(index_code)
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    result = result.drop_duplicates(subset=["index_code", "trade_date"], keep="last")
    return result.sort_values("trade_date").reset_index(drop=True)


def _entry_with_resolved_evidence(entry: IndexCatalogEntry, evidence: pd.DataFrame) -> IndexCatalogEntry:
    """Apply only resolver evidence that is safe for durable catalogue metadata."""

    matched = evidence[evidence["index_code"].astype(str) == entry.index_code]
    if matched.empty:
        return entry
    row = matched.iloc[0]
    status = str(row.get("evidence_status") or "")
    reference_date = pd.to_datetime(row.get("reference_date"), errors="coerce")
    if status not in {"OFFICIAL", "THIRD_PARTY_BASE_DATE", "THIRD_PARTY_PUBLICATION"} or pd.isna(reference_date):
        return entry
    candidate_source = str(row.get("baseline_source") or "").strip()
    candidate_date = pd.Timestamp(reference_date).date()
    if has_official_baseline(entry.baseline_source, entry.index_base_date) and not has_official_baseline(
        candidate_source,
        candidate_date,
    ):
        return entry
    checked_at = pd.to_datetime(row.get("checked_at"), errors="coerce")
    return replace(
        entry,
        index_base_date=candidate_date,
        baseline_source=candidate_source or entry.baseline_source,  # type: ignore[arg-type]
        baseline_evidence_kind=str(row.get("baseline_evidence_kind") or entry.baseline_evidence_kind),  # type: ignore[arg-type]
        baseline_evidence_name=str(row.get("baseline_evidence_name") or ""),
        baseline_evidence_url=str(row.get("baseline_evidence_url") or ""),
        baseline_checked_at=None if pd.isna(checked_at) else pd.Timestamp(checked_at).date(),
    )


def _frame_first_trade_date(frame: pd.DataFrame | None) -> str | None:
    if frame is None or frame.empty or "trade_date" not in frame:
        return None
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return pd.Timestamp(dates.min()).strftime("%Y-%m-%d")


def _frame_latest_trade_date(frame: pd.DataFrame | None) -> date | None:
    if frame is None or frame.empty or "trade_date" not in frame:
        return None
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return pd.Timestamp(dates.max()).date()


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
