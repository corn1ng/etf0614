"""Idempotent synchronization of official index valuation histories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

import pandas as pd

from etf_trading.data.index_valuations import OFFICIAL_INDEX_VALUATION_TS_CODES
from etf_trading.data.provider_runtime import redact_provider_text


@dataclass(frozen=True)
class OfficialIndexValuationProgress:
    """One index's completed official-valuation synchronization state."""

    done: int
    total: int
    index_code: str
    status: str


class OfficialIndexValuationSyncService:
    """Synchronize only the six explicitly mapped Tushare valuation indexes."""

    def __init__(
        self,
        provider: object,
        parquet_store: object,
        *,
        index_codes: tuple[str, ...] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.provider = provider
        self.parquet_store = parquet_store
        self.index_codes = tuple(index_codes or OFFICIAL_INDEX_VALUATION_TS_CODES)
        self.secrets = tuple(value for value in secrets if value)

    def sync_all(
        self,
        through: date | str,
        on_progress: Callable[[OfficialIndexValuationProgress], None] | None = None,
    ) -> pd.DataFrame:
        """Fetch missing official valuation rows while preserving prior good cache."""

        through_date = pd.Timestamp(through).normalize()
        results: list[dict[str, object]] = []
        for done, code in enumerate(self.index_codes, start=1):
            existing = self.parquet_store.read_index_valuations(code)
            latest = _latest_trade_date(existing)
            if pd.notna(latest) and latest >= through_date:
                status, fetched, message = "CURRENT", pd.DataFrame(), "Local valuation cache is current."
            else:
                start = pd.Timestamp("2004-01-01") if pd.isna(latest) else latest + pd.Timedelta(days=1)
                try:
                    fetched = self.provider.fetch_index_official_valuations(code, start, through_date)
                    _validate_fetched_valuations(fetched)
                    if fetched.empty:
                        status, message = "EMPTY", "Provider returned no new official valuations."
                    else:
                        merged = pd.concat([existing, fetched], ignore_index=True)
                        merged = (
                            merged.drop_duplicates(["index_code", "trade_date"], keep="last")
                            .sort_values("trade_date")
                            .reset_index(drop=True)
                        )
                        self.parquet_store.write_index_valuations(code, merged)
                        status = "INITIALIZED" if existing.empty else "UPDATED"
                        message = f"Stored {len(fetched)} official valuation rows."
                except Exception as exc:
                    fetched = pd.DataFrame()
                    status = "FAILED"
                    message = redact_provider_text(exc, secrets=self.secrets)
            results.append(
                {
                    "index_code": code,
                    "status": status,
                    "fetched_rows": len(fetched),
                    "message": message,
                }
            )
            if on_progress is not None:
                on_progress(OfficialIndexValuationProgress(done, len(self.index_codes), code, status))
        return pd.DataFrame(results)


def _latest_trade_date(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty or "trade_date" not in frame:
        return pd.NaT
    latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
    return latest.normalize() if pd.notna(latest) else pd.NaT


def _validate_fetched_valuations(frame: pd.DataFrame) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("official valuation response must be a DataFrame")
    if frame.empty:
        return
    if "trade_date" not in frame:
        raise ValueError("official valuation response missing trade_date")
    if not {"pe_static", "pe_ttm", "pb"}.intersection(frame.columns):
        raise ValueError("official valuation response missing valuation metric")
