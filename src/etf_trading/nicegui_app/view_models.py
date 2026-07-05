"""UI-neutral view models for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class MetricTile:
    label: str
    value: str
    tone: str = "neutral"
    detail: str = ""


@dataclass(frozen=True)
class AuditFinding:
    page_slug: str
    problem: str
    fix: str


@dataclass(frozen=True)
class PlatformSnapshot:
    master: pd.DataFrame
    watchlist: pd.DataFrame
    index_summary: pd.DataFrame
    universe: pd.DataFrame
    gaps: pd.DataFrame
    coverage: pd.DataFrame
    generated_at: datetime


def current_ui_audit_findings() -> tuple[AuditFinding, ...]:
    return (
        AuditFinding("action", "状态、建议和计算池分散，打开后需要向下找重点。", "首屏压成状态条、行动摘要和计算池预览。"),
        AuditFinding("market", "指数筛选、说明和图表之间空隙过大，K线下沉。", "用工具栏承载筛选和区间，图表作为主视觉区域。"),
        AuditFinding("etf-data", "ETF主数据、行情和样本池入口语义混在一起。", "按ETF资产层拆成总览、行情、搜索、计算池和样本池。"),
        AuditFinding("maintenance", "数据健康和补齐动作不够贴近，错误/空状态不够明确。", "健康摘要、缺口表和补齐按钮同屏呈现。"),
        AuditFinding("research", "研究功能复杂，第一版不适合抢占高频页面节奏。", "先保留状态和结果入口，复杂回测后续迁移。"),
    )


def status_metrics(snapshot: PlatformSnapshot) -> list[MetricTile]:
    eligible = _count_allowed_indexes(snapshot.index_summary)
    gap_count = len(snapshot.gaps)
    return [
        MetricTile("ETF总数", str(len(snapshot.master)), "neutral", "主列表"),
        MetricTile("计算池", str(len(snapshot.watchlist)), "info", "每日跟踪"),
        MetricTile("可参与指数", str(eligible), "success" if eligible else "warning", "市场状态"),
        MetricTile("数据缺口", str(gap_count), "warning" if gap_count else "success", "维护项"),
    ]


def market_overview(snapshot: PlatformSnapshot) -> dict[str, object]:
    frame = snapshot.index_summary.copy()
    if frame.empty:
        return {"total_indexes": 0, "allowed_indexes": 0, "categories": []}

    allowed = _allowed_series(frame)
    categories = []
    if "category" in frame:
        grouped = frame.assign(_allowed=allowed).groupby("category", dropna=False)
        for category, group in grouped:
            categories.append({"category": str(category), "total": int(len(group)), "allowed": int(group["_allowed"].sum())})
    return {"total_indexes": int(len(frame)), "allowed_indexes": int(allowed.sum()), "categories": categories}


def etf_overview_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.master)


def maintenance_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.gaps)


def code_from_option(option: str | None) -> str:
    if not option:
        return ""
    return str(option).strip().split(maxsplit=1)[0]


def index_choice_options(index_summary: pd.DataFrame) -> list[str]:
    if index_summary.empty:
        return []

    options: list[str] = []
    for row in index_summary.fillna("").to_dict("records"):
        code = str(row.get("index_code", "")).strip()
        if not code:
            continue
        name = str(row.get("index_name", "")).strip()
        category = str(row.get("category", "")).strip()
        status = "可参与" if bool(row.get("allows_new_position", False)) else "观察"
        pieces = [code]
        if name:
            pieces.append(name)
        label = " ".join(pieces)
        suffix = [item for item in (category, status) if item]
        if suffix:
            label = f"{label} · {' · '.join(suffix)}"
        options.append(label)
    return options


def etf_choice_options(rows: list[dict[str, object]]) -> list[str]:
    options: list[str] = []
    for row in rows:
        code = _row_value(row, "ETF代码", "etf_code")
        if not code:
            continue
        name = _row_value(row, "ETF名称", "name")
        category = _row_value(row, "分类", "category")
        label = f"{code} {name}".strip()
        if category:
            label = f"{label} · {category}"
        options.append(label)
    return options


def category_options(rows: list[dict[str, object]]) -> list[str]:
    categories: list[str] = []
    seen: set[str] = set()
    for row in rows:
        category = _row_value(row, "分类", "category")
        if category and category not in seen:
            categories.append(category)
            seen.add(category)
    return ["全部分类", *categories]


def filter_etf_rows(
    rows: list[dict[str, object]],
    query: str = "",
    category: str = "全部分类",
    limit: int = 100,
) -> list[dict[str, object]]:
    normalized_query = query.strip().lower()
    filtered: list[dict[str, object]] = []
    for row in rows:
        row_category = _row_value(row, "分类", "category")
        if category not in {"", "全部", "全部分类"} and row_category != category:
            continue
        searchable = " ".join(
            _row_value(row, *keys)
            for keys in (
                ("ETF代码", "etf_code"),
                ("ETF名称", "name"),
                ("分类", "category"),
                ("交易所", "exchange"),
            )
        ).lower()
        if normalized_query and normalized_query not in searchable:
            continue
        filtered.append(row)
        if len(filtered) >= limit:
            break
    return filtered


def etf_category_for_code(rows: list[dict[str, object]], etf_code: str, default: str = "其他") -> str:
    for row in rows:
        if _row_value(row, "ETF代码", "etf_code") == etf_code:
            return _row_value(row, "分类", "category") or default
    return default


def _count_allowed_indexes(index_summary: pd.DataFrame) -> int:
    if index_summary.empty:
        return 0
    return int(_allowed_series(index_summary).sum())


def _allowed_series(frame: pd.DataFrame) -> pd.Series:
    if "allows_new_position" not in frame:
        return pd.Series(False, index=frame.index)
    return frame["allows_new_position"].fillna(False).astype(bool)


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return frame.fillna("").to_dict("records")


def _row_value(row: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return str(value).strip()
    return ""
