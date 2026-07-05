"""Build index-scoped ETF sample pools for strategy research."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from etf_trading.data.indexes import DEFAULT_INDEXES, IndexDefinition
from etf_trading.data.storage import ParquetStore


UNIVERSE_COLUMNS = [
    "index_code",
    "index_name",
    "market",
    "index_category",
    "etf_code",
    "etf_name",
    "tracking_index",
    "mapping_source",
    "confidence",
    "amount",
    "volume",
    "history_rows",
    "sample_rank",
    "is_top_sample",
]

INDEX_ALIASES: dict[str, tuple[str, ...]] = {
    "000300": ("沪深300", "300ETF", "HS300"),
    "000905": ("中证500", "500ETF"),
    "000852": ("中证1000", "1000ETF"),
    "932000": ("中证2000", "2000ETF"),
    "000510": ("中证A500", "A500"),
    "930050": ("中证A50", "A50"),
    "000016": ("上证50", "50ETF"),
    "399006": ("创业板", "创业板ETF"),
    "000688": ("科创50", "科创50ETF"),
    "931643": ("科创创业50", "双创50", "科创创业"),
    "000922": ("中证红利", "红利ETF"),
    "000015": ("上证红利", "红利ETF"),
    "H30269": ("红利低波",),
    "930955": ("红利低波100",),
    "399986": ("银行", "银行ETF"),
    "399975": ("证券", "证券ETF", "证券公司"),
    "000933": ("医药", "医药ETF"),
    "000932": ("消费", "消费ETF"),
    "000819": ("有色", "有色金属"),
    "000827": ("环保", "环保ETF"),
    "930997": ("新能源车", "新能源汽车"),
    "931152": ("创新药", "创新药ETF"),
    "931865": ("半导体", "芯片", "半导"),
    "HSI": ("恒生指数", "恒生ETF"),
    "HSCEI": ("恒生中国企业", "H股", "国企指数"),
    "HSTECH": ("恒生科技", "恒科"),
    "H30533": ("中国互联网50", "中概互联", "互联网"),
}


@dataclass(frozen=True)
class IndexEtfSampleConfig:
    max_per_index: int = 10
    min_history_rows: int = 252


def build_index_etf_universe(
    master: pd.DataFrame,
    parquet_store: ParquetStore,
    definitions: Sequence[IndexDefinition] = DEFAULT_INDEXES,
    config: IndexEtfSampleConfig | None = None,
) -> pd.DataFrame:
    """Return ETF samples grouped by their tracked or inferred index."""

    config = config or IndexEtfSampleConfig()
    normalized = _normalize_master(master)
    if normalized.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)

    rows: list[dict[str, object]] = []
    for definition in definitions:
        candidates = _candidates_for_index(normalized, definition)
        if candidates.empty:
            continue
        candidates = _attach_history_rows(candidates, parquet_store)
        candidates = candidates[candidates["history_rows"] >= config.min_history_rows]
        if candidates.empty:
            continue
        candidates = candidates.sort_values(
            ["amount", "history_rows", "etf_code"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        for rank, row in enumerate(candidates.to_dict("records"), start=1):
            row.update(
                {
                    "index_code": definition.index_code,
                    "index_name": definition.name,
                    "market": definition.market,
                    "index_category": definition.category,
                    "sample_rank": rank,
                    "is_top_sample": rank <= config.max_per_index,
                }
            )
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS)
    return pd.DataFrame(rows)[UNIVERSE_COLUMNS]


def selected_etf_codes(universe: pd.DataFrame, index_codes: Sequence[str]) -> list[str]:
    """Return deduplicated ETF codes selected as top samples for indexes."""

    if universe.empty or not index_codes:
        return []
    required_columns = {"index_code", "etf_code", "is_top_sample"}
    if not required_columns.issubset(universe.columns):
        return []

    allowed_indexes = {str(code) for code in index_codes}
    selected = universe[
        universe["index_code"].astype(str).isin(allowed_indexes)
        & universe["is_top_sample"].fillna(False).astype(bool)
    ]
    codes: list[str] = []
    seen: set[str] = set()
    for code in selected["etf_code"].map(_format_etf_code):
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _normalize_master(master: pd.DataFrame) -> pd.DataFrame:
    if master.empty:
        return pd.DataFrame(
            columns=["etf_code", "etf_name", "tracking_index", "amount", "volume", "is_active"]
        )

    normalized = master.copy()
    for column in ["etf_code", "name", "tracking_index", "amount", "volume", "is_active"]:
        if column not in normalized.columns:
            normalized[column] = None

    normalized["etf_code"] = normalized["etf_code"].map(_format_etf_code)
    normalized["etf_name"] = normalized["name"].fillna("").astype(str)
    normalized["tracking_index"] = normalized["tracking_index"].fillna("").astype(str).str.strip()
    normalized["amount"] = pd.to_numeric(normalized["amount"], errors="coerce").fillna(0.0)
    normalized["volume"] = pd.to_numeric(normalized["volume"], errors="coerce").fillna(0.0)
    normalized["is_active"] = pd.to_numeric(normalized["is_active"], errors="coerce").fillna(1).astype(int)
    normalized = normalized[(normalized["etf_code"] != "") & (normalized["is_active"] == 1)]
    return normalized[["etf_code", "etf_name", "tracking_index", "amount", "volume"]].reset_index(drop=True)


def _candidates_for_index(master: pd.DataFrame, definition: IndexDefinition) -> pd.DataFrame:
    explicit = master[_explicit_tracking_match(master["tracking_index"], definition)].copy()
    explicit["mapping_source"] = "data_source"
    explicit["confidence"] = "high"

    inferred = master[_name_match(master["etf_name"], definition)].copy()
    inferred["mapping_source"] = "name_inferred"
    inferred["confidence"] = "medium"

    combined = pd.concat([explicit, inferred], ignore_index=True)
    if combined.empty:
        return combined
    return combined.drop_duplicates(subset=["etf_code"], keep="first").reset_index(drop=True)


def _explicit_tracking_match(values: pd.Series, definition: IndexDefinition) -> pd.Series:
    normalized_values = values.fillna("").astype(str).str.strip().str.upper()
    accepted = {
        definition.index_code.upper(),
        definition.name.upper(),
        definition.provider_symbol.upper(),
    }
    return normalized_values.isin(accepted)


def _name_match(names: pd.Series, definition: IndexDefinition) -> pd.Series:
    aliases = _aliases_for(definition)
    if not aliases:
        return pd.Series(False, index=names.index)
    text = names.fillna("").astype(str)
    mask = pd.Series(False, index=names.index)
    for alias in aliases:
        mask |= text.str.contains(alias, case=False, regex=False)
    return mask


def _aliases_for(definition: IndexDefinition) -> tuple[str, ...]:
    aliases = [definition.name]
    aliases.extend(INDEX_ALIASES.get(definition.index_code, ()))
    result: list[str] = []
    for alias in aliases:
        text = str(alias).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _attach_history_rows(frame: pd.DataFrame, parquet_store: ParquetStore) -> pd.DataFrame:
    enriched = frame.copy()
    history_rows = []
    for code in enriched["etf_code"]:
        prices = parquet_store.read_prices(str(code))
        history_rows.append(int(len(prices)))
    enriched["history_rows"] = history_rows
    return enriched


def _format_etf_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text
