"""Resolve and persist evidence for index-history baselines."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd
import yaml

from etf_trading.data.index_catalog import IndexCatalogEntry


CSINDEX_BASIC_INFO_URL = "https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/{index_code}"
JOINQUANT_INDEX_LIST_URL = "https://www.joinquant.com/data/dict/indexData"

RESULT_COLUMNS = [
    "index_code",
    "evidence_status",
    "reference_date",
    "baseline_source",
    "baseline_evidence_kind",
    "baseline_evidence_name",
    "baseline_evidence_url",
    "checked_at",
    "detail",
]
_WRITABLE_STATUSES = frozenset({"OFFICIAL", "THIRD_PARTY_BASE_DATE", "THIRD_PARTY_PUBLICATION"})


class BaselineEvidenceResolver:
    """Collect official and third-party baseline evidence without stopping a batch."""

    def __init__(
        self,
        *,
        http_get: Callable[[str], object] | None = None,
        third_party_index_list: pd.DataFrame | None = None,
    ) -> None:
        self._http_get = http_get or _default_http_get
        self._provided_third_party_index_list = third_party_index_list

    def collect(self, entries: Sequence[IndexCatalogEntry], as_of: date) -> pd.DataFrame:
        third_party = self._third_party_index_list()
        rows = [self._collect_one(entry, third_party, as_of) for entry in entries]
        return pd.DataFrame(rows, columns=RESULT_COLUMNS)

    def _collect_one(
        self,
        entry: IndexCatalogEntry,
        third_party: pd.DataFrame,
        as_of: date,
    ) -> dict[str, str | None]:
        official, rejection_detail = self._csindex_evidence(entry, as_of)
        if official is not None:
            return official

        publication = self._joinquant_publication_evidence(entry, third_party, as_of)
        if publication is not None:
            return publication

        detail = "未取得可核验的官方基日或第三方发布日期"
        if rejection_detail:
            detail = f"{rejection_detail}；{detail}"
        return _unresolved_evidence(entry, as_of, detail)

    def _csindex_evidence(
        self,
        entry: IndexCatalogEntry,
        as_of: date,
    ) -> tuple[dict[str, str | None] | None, str]:
        if entry.source_kind != "csi" and not entry.index_code.upper().startswith("H"):
            return None, ""

        url = CSINDEX_BASIC_INFO_URL.format(index_code=entry.index_code)
        try:
            payload = _as_mapping(self._http_get(url))
        except Exception as error:
            return None, f"中证官方接口请求失败：{error}"
        if payload is None:
            return None, "中证官方接口未返回可解析结果"
        if str(payload.get("code") or "").strip() != "200":
            return None, "中证官方接口业务码非 200"

        data = payload.get("data")
        if not isinstance(data, Mapping):
            return None, "中证官方接口未返回基础信息"
        returned_code = _normalise_code(data.get("indexCode"))
        if returned_code != _normalise_code(entry.index_code):
            return None, "中证官方接口返回代码不一致"
        basic_date = _iso_date(data.get("basicDate"))
        if basic_date is None:
            return None, "中证官方接口返回的基日无效"

        return (
            {
                "index_code": entry.index_code,
                "evidence_status": "OFFICIAL",
                "reference_date": basic_date,
                "baseline_source": "official_api",
                "baseline_evidence_kind": "official_base_date",
                "baseline_evidence_name": "中证指数官方基础信息",
                "baseline_evidence_url": url,
                "checked_at": as_of.isoformat(),
                "detail": "",
            },
            "",
        )

    def _third_party_index_list(self) -> pd.DataFrame:
        if self._provided_third_party_index_list is not None:
            return self._provided_third_party_index_list.copy()
        try:
            response = self._http_get(JOINQUANT_INDEX_LIST_URL)
        except Exception:
            return pd.DataFrame()
        return _as_frame(response)

    def _joinquant_publication_evidence(
        self,
        entry: IndexCatalogEntry,
        third_party: pd.DataFrame,
        as_of: date,
    ) -> dict[str, str | None] | None:
        required_columns = {"index_code", "display_name", "publish_date"}
        if not required_columns.issubset(third_party.columns):
            return None

        target_code = _normalise_code(entry.index_code)
        accepted_names = {_normalise_name(entry.name), *(_normalise_name(alias) for alias in entry.aliases)}
        for candidate in third_party.itertuples(index=False):
            candidate_code = _normalise_code(getattr(candidate, "index_code"))
            candidate_name = _normalise_name(getattr(candidate, "display_name"))
            if candidate_code != target_code or candidate_name not in accepted_names:
                continue
            publish_date = _iso_date(getattr(candidate, "publish_date"))
            if publish_date is None:
                continue
            return {
                "index_code": entry.index_code,
                "evidence_status": "THIRD_PARTY_PUBLICATION",
                "reference_date": publish_date,
                "baseline_source": "third_party_publication",
                "baseline_evidence_kind": "publication_date",
                "baseline_evidence_name": "聚宽",
                "baseline_evidence_url": JOINQUANT_INDEX_LIST_URL,
                "checked_at": as_of.isoformat(),
                "detail": "第三方仅提供发布日期，不能视为官方基日",
            }
        return None


def write_baseline_evidence(path: str | Path, frame: pd.DataFrame) -> None:
    """Write only verified or explicitly third-party evidence, ordered by code."""

    target = Path(path)
    existing = _load_evidence_mapping(target)
    evidence = dict(existing)
    for row in frame.to_dict(orient="records"):
        if str(row.get("evidence_status") or "") not in _WRITABLE_STATUSES:
            continue
        index_code = _normalise_code(row.get("index_code"))
        reference_date = _iso_date(row.get("reference_date"))
        if not index_code or reference_date is None:
            continue
        checked_at = _iso_date(row.get("checked_at"))
        evidence[index_code] = {
            "reference_date": reference_date,
            "source": str(row.get("baseline_source") or "").strip(),
            "kind": str(row.get("baseline_evidence_kind") or "").strip(),
            "source_name": str(row.get("baseline_evidence_name") or "").strip(),
            "source_url": str(row.get("baseline_evidence_url") or "").strip(),
            "checked_at": checked_at or "",
            "detail": str(row.get("detail") or "").strip(),
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    ordered_evidence = {code: evidence[code] for code in sorted(evidence)}
    target.write_text(
        yaml.safe_dump({"evidence": ordered_evidence}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _unresolved_evidence(entry: IndexCatalogEntry, as_of: date, detail: str) -> dict[str, str | None]:
    return {
        "index_code": entry.index_code,
        "evidence_status": "UNRESOLVED",
        "reference_date": None,
        "baseline_source": "unverified",
        "baseline_evidence_kind": "unresolved",
        "baseline_evidence_name": "",
        "baseline_evidence_url": "",
        "checked_at": as_of.isoformat(),
        "detail": detail,
    }


def _default_http_get(url: str) -> object:
    request = Request(url, headers={"User-Agent": "etf-trading-system/0.1"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - URLs are fixed module constants.
        body = response.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    json_method = getattr(value, "json", None)
    if callable(json_method):
        decoded = json_method()
        return decoded if isinstance(decoded, Mapping) else None
    return None


def _as_frame(value: object) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    try:
        if isinstance(value, Mapping):
            data = value.get("data", value)
            return pd.DataFrame(data)
        if isinstance(value, (list, tuple)):
            return pd.DataFrame(value)
    except (TypeError, ValueError):
        return pd.DataFrame()
    return pd.DataFrame()


def _load_evidence_mapping(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mappings = raw.get("evidence", {}) if isinstance(raw, Mapping) else {}
    if not isinstance(mappings, Mapping):
        return {}
    return {
        _normalise_code(code): dict(item)
        for code, item in mappings.items()
        if _normalise_code(code) and isinstance(item, Mapping)
    }


def _normalise_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return text[:-2] if re.fullmatch(r"\d+\.0", text) else text


def _normalise_name(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[\s\-_/（）()\[\]【】]", "", str(value)).casefold()


def _iso_date(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        return None
