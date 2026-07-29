"""Local-only index data admission and minimal trend features."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from etf_trading.data.index_catalog import IndexCatalogEntry
from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_models import IndexAdmissionResult, IndexResearchConfig


REQUIRED_COLUMNS = {"trade_date", "open", "high", "low", "close"}


def add_index_trend_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add only the V1 MA60, MA60 slope, and ATR20 features."""

    result = frame.sort_values("trade_date").copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    result["ma60"] = close.rolling(60, min_periods=60).mean()
    result["ma60_slope_20"] = result["ma60"] / result["ma60"].shift(20) - 1.0
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr20"] = true_range.rolling(20, min_periods=20).mean()
    return result


def load_index_frames(
    parquet_root: str | Path,
    catalog: Sequence[IndexCatalogEntry],
    config: IndexResearchConfig,
) -> IndexAdmissionResult:
    """Read, validate, cohort, and feature local Parquet index histories only."""

    store = ParquetStore(parquet_root)
    frames: dict[str, pd.DataFrame] = {}
    metadata: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    for entry in catalog:
        cohort = _cohort_or_exclude(entry, exclusions)
        if cohort is None:
            continue
        path = store.root / "indexes" / f"{entry.index_code}.parquet"
        if not path.exists():
            _exclude(exclusions, entry, "missing_price_file")
            continue
        frame = store.read_index_prices(entry.index_code)
        reason = _invalid_frame_reason(frame, entry, config)
        if reason is not None:
            _exclude(exclusions, entry, reason)
            continue

        prepared = _prepare_frame(frame, entry.index_base_date)
        raw_dates = pd.to_datetime(frame["trade_date"], errors="coerce")
        featured = add_index_trend_features(prepared)
        frames[entry.index_code] = featured
        metadata.append(
            {
                "index_code": entry.index_code,
                "name": entry.name,
                "market": entry.market,
                "index_type": entry.index_type,
                "pool": entry.pool,
                "cohort": cohort,
                "raw_start_date": raw_dates.min(),
                "raw_end_date": raw_dates.max(),
                "valid_start_date": featured["trade_date"].min(),
                "valid_end_date": featured["trade_date"].max(),
                "valid_rows": len(featured),
            }
        )
    return IndexAdmissionResult(
        frames=frames,
        metadata=pd.DataFrame(metadata),
        exclusions=pd.DataFrame(exclusions),
    )


def _cohort_or_exclude(entry: IndexCatalogEntry, exclusions: list[dict[str, object]]) -> str | None:
    if entry.baseline_evidence_kind == "official_base_date":
        cohort = "official"
    elif entry.baseline_evidence_kind == "third_party_base_date":
        cohort = "reference"
    elif entry.baseline_evidence_kind in {"publication_date", "unresolved"}:
        _exclude(exclusions, entry, entry.baseline_evidence_kind)
        return None
    else:
        _exclude(exclusions, entry, "unsupported_baseline_evidence")
        return None
    if entry.index_base_date is None:
        _exclude(exclusions, entry, "missing_index_base_date")
        return None
    return cohort


def _invalid_frame_reason(
    frame: pd.DataFrame,
    entry: IndexCatalogEntry,
    config: IndexResearchConfig,
) -> str | None:
    if not REQUIRED_COLUMNS.issubset(frame.columns):
        return "missing_required_columns"
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    if dates.isna().any():
        return "invalid_trade_date"
    if dates.duplicated().any():
        return "duplicate_trade_date"

    prepared = _prepare_frame(frame, entry.index_base_date)
    prices = prepared[["high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if prices.isna().any().any() or (prices <= 0).any().any():
        return "non_positive_ohlc"
    open_prices = pd.to_numeric(prepared["open"], errors="coerce")
    present_open = prepared["open"].notna()
    if (present_open & (open_prices.isna() | (open_prices <= 0))).any():
        return "non_positive_open"
    if len(prepared) < config.min_valid_rows:
        return "insufficient_valid_rows"
    return None


def _prepare_frame(frame: pd.DataFrame, index_base_date: object) -> pd.DataFrame:
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    return result.loc[result["trade_date"] >= pd.Timestamp(index_base_date)].sort_values("trade_date").copy()


def _exclude(exclusions: list[dict[str, object]], entry: IndexCatalogEntry, reason_code: str) -> None:
    exclusions.append(
        {
            "index_code": entry.index_code,
            "name": entry.name,
            "reason_code": reason_code,
        }
    )
