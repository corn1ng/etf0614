"""Versioned A-share and Hong Kong index universe catalog."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Literal, TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from etf_trading.data.indexes import IndexDefinition


Pool = Literal["core", "research", "reserve"]
BaselineSource = Literal["official_methodology", "official_factsheet", "unverified"]
SourceKind = Literal["csi", "shenwan", "hk"]
DEFAULT_INDEX_CATALOG_PATH = Path(__file__).resolve().parents[3] / "configs" / "index_universe.yaml"
_LEGACY_CATEGORIES = {
    "000300": "A股宽基", "000905": "A股宽基", "000852": "A股宽基", "932000": "A股宽基",
    "000510": "A股宽基", "930050": "A股宽基", "000903": "A股宽基", "000906": "A股宽基",
    "000016": "A股宽基", "000001": "A股综合", "399001": "A股综合", "399006": "A股成长",
    "000688": "A股成长", "931643": "A股成长", "000922": "A股主题", "000015": "A股主题",
    "H30269": "A股主题", "930955": "A股主题", "931446": "A股主题", "000919": "A股主题",
    "000029": "A股主题", "930782": "A股主题", "930997": "A股主题", "930901": "A股主题",
    "931087": "A股主题", "H11052": "A股主题", "399986": "A股行业", "399975": "A股行业",
    "000933": "A股行业", "000932": "A股行业", "000934": "A股行业", "000935": "A股行业",
    "000928": "A股行业", "000819": "A股行业", "000827": "A股行业", "399812": "A股行业",
    "931152": "A股行业", "930707": "A股行业", "930697": "A股行业", "931009": "A股行业",
    "930743": "A股行业", "930633": "A股行业", "931865": "A股行业", "931775": "A股行业",
    "H30015": "A股行业", "H30533": "港股科技", "HSI": "港股宽基", "HSCEI": "港股宽基",
    "HSTECH": "港股科技",
}


@dataclass(frozen=True)
class IndexCatalogEntry:
    index_code: str
    name: str
    market: str
    category_level_1: str
    category_level_2: str
    index_type: str
    pool: Pool
    index_base_date: date | None
    baseline_source: BaselineSource
    source_kind: SourceKind
    provider_symbol: str
    aliases: tuple[str, ...] = ()

    def to_index_definition(self) -> "IndexDefinition":
        from etf_trading.data.indexes import IndexDefinition

        return IndexDefinition(
            self.index_code,
            self.name,
            self.market,
            _display_category(self),
            self.provider_symbol,
        )


def default_index_catalog() -> tuple[IndexCatalogEntry, ...]:
    return load_index_catalog(DEFAULT_INDEX_CATALOG_PATH)


def load_index_catalog(path: str | Path) -> tuple[IndexCatalogEntry, ...]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("index catalog root must be a mapping")
    entries = tuple(_entry_from_mapping(item) for item in _expand_catalog_mappings(raw))
    _validate_catalog(entries)
    return entries


def catalog_definitions(
    entries: Sequence[IndexCatalogEntry],
    *,
    pool: str | None = None,
    include_reserve: bool = False,
) -> tuple["IndexDefinition", ...]:
    selected = [entry for entry in entries if pool is None or entry.pool == pool]
    if not include_reserve:
        selected = [entry for entry in selected if entry.pool != "reserve"]
    return tuple(entry.to_index_definition() for entry in selected)


def catalog_entries_from_frame(frame: "pd.DataFrame") -> tuple[IndexCatalogEntry, ...]:
    """Rehydrate catalogue entries read from SQLite without changing their metadata."""

    import pandas as pd

    entries: list[IndexCatalogEntry] = []
    for row in frame.itertuples(index=False):
        base_value = getattr(row, "index_base_date", None)
        base_date = None if base_value is None or pd.isna(base_value) else pd.Timestamp(base_value).date()
        try:
            aliases = tuple(str(value) for value in json.loads(getattr(row, "aliases_json", "[]") or "[]"))
        except (TypeError, json.JSONDecodeError):
            aliases = ()
        entries.append(
            IndexCatalogEntry(
                index_code=str(row.index_code),
                name=str(row.name),
                market=str(row.market),
                category_level_1=str(row.category_level_1),
                category_level_2=str(row.category_level_2),
                index_type=str(row.index_type),
                pool=str(row.pool),  # type: ignore[arg-type]
                index_base_date=base_date,
                baseline_source=str(row.baseline_source),  # type: ignore[arg-type]
                source_kind=str(row.source_kind),  # type: ignore[arg-type]
                provider_symbol=str(row.provider_symbol),
                aliases=aliases,
            )
        )
    return tuple(entries)


def _expand_catalog_mappings(raw: dict[str, object]) -> Iterable[dict[str, object]]:
    direct_entries = raw.get("entries", [])
    if direct_entries:
        if not isinstance(direct_entries, list):
            raise ValueError("index catalog entries must be a list")
        for item in direct_entries:
            if not isinstance(item, dict):
                raise ValueError("each index catalog entry must be a mapping")
            yield item
        return

    groups = raw.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("index catalog groups must be a list")
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("each index catalog group must be a mapping")
        items = group.get("items", [])
        if not isinstance(items, list):
            raise ValueError("index catalog group items must be a list")
        defaults = {key: value for key, value in group.items() if key != "items"}
        for item in items:
            if not isinstance(item, list) or len(item) not in {2, 3}:
                raise ValueError("each index catalog group item must contain code, name, and optional aliases")
            code, name = item[:2]
            aliases = item[2] if len(item) == 3 else []
            yield {**defaults, "index_code": code, "name": name, "aliases": aliases}


def _entry_from_mapping(item: dict[str, object]) -> IndexCatalogEntry:
    index_code = _required_text(item, "index_code")
    source_kind = _required_text(item, "source_kind")
    provider_symbol = str(item.get("provider_symbol") or index_code.replace(".SI", "")).strip()
    baseline_source = str(item.get("baseline_source") or "unverified").strip()
    return IndexCatalogEntry(
        index_code=index_code,
        name=_required_text(item, "name"),
        market=_required_text(item, "market"),
        category_level_1=_required_text(item, "category_level_1"),
        category_level_2=str(item.get("category_level_2") or item.get("category_level_1") or "").strip(),
        index_type=_required_text(item, "index_type"),
        pool=str(item.get("pool") or "").strip(),  # type: ignore[arg-type]
        index_base_date=_parse_date(item.get("index_base_date")),
        baseline_source=baseline_source,  # type: ignore[arg-type]
        source_kind=source_kind,  # type: ignore[arg-type]
        provider_symbol=provider_symbol,
        aliases=tuple(str(value).strip() for value in item.get("aliases", []) if str(value).strip()),
    )


def _validate_catalog(entries: Sequence[IndexCatalogEntry]) -> None:
    seen: set[str] = set()
    for entry in entries:
        if entry.index_code in seen:
            raise ValueError(f"duplicate index_code: {entry.index_code}")
        seen.add(entry.index_code)
        if entry.market not in {"A股", "港股"}:
            raise ValueError(f"unsupported market: {entry.market}")
        if entry.pool not in {"core", "research", "reserve"}:
            raise ValueError(f"unsupported pool: {entry.pool}")
        if entry.source_kind not in {"csi", "shenwan", "hk"}:
            raise ValueError(f"unsupported source_kind: {entry.source_kind}")
        if entry.baseline_source not in {"official_methodology", "official_factsheet", "unverified"}:
            raise ValueError(f"unsupported baseline_source: {entry.baseline_source}")
        if entry.baseline_source != "unverified" and entry.index_base_date is None:
            raise ValueError(f"official baseline requires index_base_date: {entry.index_code}")


def _required_text(item: dict[str, object], key: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise ValueError(f"index catalog entry requires {key}")
    return value


def _parse_date(value: object) -> date | None:
    if value in {None, ""}:
        return None
    return date.fromisoformat(str(value))


def _display_category(entry: IndexCatalogEntry) -> str:
    if entry.index_code in _LEGACY_CATEGORIES:
        return _LEGACY_CATEGORIES[entry.index_code]
    if entry.market == "A股":
        return "A股行业" if entry.index_type == "行业" else "A股主题"
    return "港股行业" if entry.index_type == "行业" else "港股宽基"
