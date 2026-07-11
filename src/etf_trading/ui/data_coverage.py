"""Data coverage builders for ETF business and maintenance pages."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from etf_trading.data.quality import (
    HistoryReadiness,
    assess_price_history,
    expected_latest_trade_date,
    history_readiness_label,
    read_failed_assessment,
    trading_day_lag,
)


ETF_OVERVIEW_COLUMNS = [
    "ETF代码",
    "ETF名称",
    "分类",
    "交易所",
    "成交额",
    "追踪指数",
    "映射来源",
    "置信度",
    "每日计算池",
    "允许买入",
    "启用",
    "指数样本池",
    "本地历史",
    "历史长度",
    "最新日期",
    "状态说明",
]

GAP_COLUMNS = [
    "数据类型",
    "代码",
    "名称",
    "本地最新日期",
    "应有最新交易日",
    "缺失天数",
    "记录数",
    "状态",
    "修复建议",
]

SUMMARY_COLUMNS = [
    "数据类型",
    "总数",
    "完整",
    "缺失",
    "缺少",
    "历史不足",
    "读取失败",
    "覆盖率",
]

MAPPING_SOURCE_NAMES = {
    "data_source": "数据源",
    "name_inferred": "名称推断",
}

CONFIDENCE_NAMES = {
    "high": "高",
    "medium": "中",
    "low": "低",
}


def build_etf_data_overview(
    master: pd.DataFrame,
    watchlist: pd.DataFrame,
    parquet_store: Any,
    universe: pd.DataFrame,
    min_history_rows: int = 252,
    today: date | pd.Timestamp | None = None,
    holidays: tuple[date | pd.Timestamp | str, ...] = (),
) -> pd.DataFrame:
    """Build the business-facing ETF overview table."""

    if master.empty:
        return pd.DataFrame(columns=ETF_OVERVIEW_COLUMNS)

    normalized_master = _normalize_master(master)
    watchlist_map = _watchlist_map(watchlist)
    universe_map = _universe_map(universe)
    expected = expected_latest_trade_date(today, holidays)
    rows: list[dict[str, object]] = []

    for item in normalized_master.to_dict("records"):
        code = str(item["etf_code"])
        watchlist_item = watchlist_map.get(code, {})
        universe_item = universe_map.get(code, {})
        history = _read_history_profile(parquet_store, code, min_history_rows, expected, holidays)
        is_top_sample = bool(universe_item.get("is_top_sample", False))
        rows.append(
            {
                "ETF代码": code,
                "ETF名称": item["name"],
                "分类": item["category"],
                "交易所": item["exchange"],
                "成交额": item["amount"],
                "追踪指数": _tracked_index_name(item, universe_item),
                "映射来源": _display_mapping_source(universe_item.get("mapping_source", "")),
                "置信度": _display_confidence(universe_item.get("confidence", "")),
                "每日计算池": "是" if code in watchlist_map else "否",
                "允许买入": _yes_no(watchlist_item.get("allow_buy")) if watchlist_item else "",
                "启用": _yes_no(watchlist_item.get("enabled")) if watchlist_item else "",
                "指数样本池": "是" if is_top_sample else "否",
                "本地历史": history["status"],
                "历史长度": history["rows"],
                "最新日期": history["latest_date"],
                "状态说明": _etf_status_note(history, item, universe_item),
            }
        )

    return pd.DataFrame(rows, columns=ETF_OVERVIEW_COLUMNS)


def build_data_gap_detail(
    master: pd.DataFrame,
    watchlist: pd.DataFrame,
    index_summary: pd.DataFrame,
    universe: pd.DataFrame,
    parquet_store: Any,
    today: date | pd.Timestamp | None = None,
    min_history_rows: int = 252,
    holidays: tuple[date | pd.Timestamp | str, ...] = (),
) -> pd.DataFrame:
    """Build the global data-maintenance gap table."""

    expected = expected_latest_trade_date(today, holidays)
    expected_text = expected.strftime("%Y-%m-%d")
    rows: list[dict[str, object]] = []

    if master.empty:
        rows.append(
            _gap_row(
                data_type="ETF主列表",
                code="全部",
                name="ETF主列表",
                latest_date="",
                expected_date=expected_text,
                missing_days="",
                rows=0,
                status="未初始化",
                suggestion="到补齐任务初始化 ETF 主列表",
            )
        )
    else:
        for item in _normalize_master(master).to_dict("records"):
            code = str(item["etf_code"])
            history = _read_history_profile(parquet_store, code, min_history_rows, expected, holidays)
            status = _maintenance_history_status(history, expected)
            if status:
                rows.append(
                    _gap_row(
                        data_type="ETF历史",
                        code=code,
                        name=str(item["name"]),
                        latest_date=history["latest_date"],
                        expected_date=expected_text,
                        missing_days=history["missing_days"],
                        rows=int(history["rows"]),
                        status=status,
                        suggestion=_repair_suggestion("ETF历史", status),
                    )
                )

    if watchlist.empty:
        rows.append(
            _gap_row(
                data_type="每日计算池",
                code="全部",
                name="每日计算池",
                latest_date="",
                expected_date=expected_text,
                missing_days="",
                rows=0,
                status="未初始化",
                suggestion="到 ETF数据 搜索并加入常看的 ETF",
            )
        )

    for item in _normalize_index_summary(index_summary).to_dict("records"):
        status = _maintenance_index_status(item, expected, min_history_rows)
        if not status:
            continue
        rows.append(
            _gap_row(
                data_type="指数历史",
                code=str(item["index_code"]),
                name=str(item["index_name"]),
                latest_date=str(item["latest_date"]),
                expected_date=expected_text,
                missing_days=_missing_days_value(item["latest_date"], expected),
                rows=int(item["history_rows"]),
                status=status,
                suggestion=_repair_suggestion("指数历史", status),
            )
        )

    if not master.empty and universe.empty:
        rows.append(
            _gap_row(
                data_type="指数样本池",
                code="全部",
                name="指数样本池",
                latest_date="",
                expected_date=expected_text,
                missing_days="",
                rows=0,
                status="未初始化",
                suggestion="先补齐 ETF 主列表和 ETF 历史",
            )
        )

    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def build_data_coverage_summary(
    gaps: pd.DataFrame,
    master: pd.DataFrame,
    watchlist: pd.DataFrame,
    index_summary: pd.DataFrame,
    universe: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize coverage counts by data type."""

    totals = {
        "ETF主列表": 0 if master.empty else 1,
        "ETF历史": len(master),
        "指数历史": len(index_summary),
        "每日计算池": len(watchlist),
        "指数样本池": _top_sample_count(universe),
    }
    rows = [_summary_row(data_type, total, gaps) for data_type, total in totals.items()]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def _normalize_master(master: pd.DataFrame) -> pd.DataFrame:
    frame = master.copy()
    for column in ["etf_code", "name", "category", "exchange", "tracking_index", "amount", "is_active"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["etf_code"] = frame["etf_code"].map(_format_code)
    frame["name"] = frame["name"].fillna("").astype(str)
    frame["category"] = frame["category"].fillna("").astype(str)
    frame["exchange"] = frame["exchange"].fillna("").astype(str)
    frame["tracking_index"] = frame["tracking_index"].fillna("").astype(str)
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0)
    frame["is_active"] = pd.to_numeric(frame["is_active"], errors="coerce").fillna(1).astype(int)
    return frame[["etf_code", "name", "category", "exchange", "tracking_index", "amount", "is_active"]]


def _watchlist_map(watchlist: pd.DataFrame) -> dict[str, dict[str, object]]:
    if watchlist.empty or "etf_code" not in watchlist.columns:
        return {}
    frame = watchlist.copy()
    frame["etf_code"] = frame["etf_code"].map(_format_code)
    return {str(row["etf_code"]): row for row in frame.to_dict("records")}


def _universe_map(universe: pd.DataFrame) -> dict[str, dict[str, object]]:
    if universe.empty or "etf_code" not in universe.columns:
        return {}
    frame = universe.copy()
    frame["etf_code"] = frame["etf_code"].map(_format_code)
    if "sample_rank" in frame.columns:
        frame = frame.sort_values(["etf_code", "is_top_sample", "sample_rank"], ascending=[True, False, True])
    result: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        result.setdefault(str(row["etf_code"]), row)
    return result


def _normalize_index_summary(index_summary: pd.DataFrame) -> pd.DataFrame:
    if index_summary.empty:
        return pd.DataFrame(columns=["index_code", "index_name", "latest_date", "history_rows"])
    frame = index_summary.copy()
    for column in ["index_code", "index_name", "latest_date", "history_rows"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["index_code"] = frame["index_code"].fillna("").astype(str)
    frame["index_name"] = frame["index_name"].fillna("").astype(str)
    frame["latest_date"] = frame["latest_date"].fillna("").astype(str)
    frame["history_rows"] = pd.to_numeric(frame["history_rows"], errors="coerce").fillna(0).astype(int)
    return frame[["index_code", "index_name", "latest_date", "history_rows"]]


def _read_history_profile(
    parquet_store: Any,
    code: str,
    min_history_rows: int,
    expected: pd.Timestamp,
    holidays: tuple[date | pd.Timestamp | str, ...] = (),
) -> dict[str, object]:
    try:
        prices = parquet_store.read_prices(code)
    except Exception:  # noqa: BLE001 - one broken file should not break the whole table
        assessment = read_failed_assessment(expected)
    else:
        assessment = assess_price_history(prices, expected, min_history_rows, holidays)

    return {
        "readiness": assessment.readiness.value,
        "status": history_readiness_label(assessment.readiness),
        "rows": assessment.history_rows,
        "latest_date": assessment.latest_trade_date,
        "expected_date": assessment.expected_trade_date,
        "missing_days": "" if assessment.trading_day_lag is None else assessment.trading_day_lag,
        "reason_codes": "、".join(assessment.reason_codes),
    }


def _latest_date_text(frame: pd.DataFrame) -> str:
    if "trade_date" not in frame.columns:
        return ""
    values = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if values.empty:
        return ""
    return values.max().strftime("%Y-%m-%d")


def _etf_status_note(history: dict[str, object], item: dict[str, object], universe_item: dict[str, object]) -> str:
    status = str(history["status"])
    if status != "数据可用":
        return status
    if not str(item.get("tracking_index", "")).strip() and not universe_item:
        return "未匹配指数"
    if universe_item and not bool(universe_item.get("is_top_sample", False)):
        return "非默认Top样本"
    return "可用"


def _maintenance_history_status(history: dict[str, object], expected: pd.Timestamp) -> str:
    del expected
    return "" if history.get("readiness") == HistoryReadiness.READY.value else str(history["status"])


def _maintenance_index_status(item: dict[str, object], expected: pd.Timestamp, min_history_rows: int) -> str:
    data_status = str(item.get("data_status", "")).strip()
    if data_status:
        return "" if data_status == "数据可用" else data_status
    rows = int(item["history_rows"])
    if rows <= 0:
        return "历史缺失"
    if rows < min_history_rows:
        return "历史不足"
    if _missing_days_value(item["latest_date"], expected) > 0:
        return "行情滞后"
    return ""


def _missing_days_value(latest_date: object, expected: pd.Timestamp) -> int | str:
    lag = trading_day_lag(latest_date, expected)
    return "" if lag is None else lag


def _parse_date(value: object) -> pd.Timestamp | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def _gap_row(
    *,
    data_type: str,
    code: str,
    name: str,
    latest_date: object,
    expected_date: object,
    missing_days: object,
    rows: int,
    status: str,
    suggestion: str,
) -> dict[str, object]:
    return {
        "数据类型": data_type,
        "代码": code,
        "名称": name,
        "本地最新日期": latest_date,
        "应有最新交易日": expected_date,
        "缺失天数": missing_days,
        "记录数": rows,
        "状态": status,
        "修复建议": suggestion,
    }


def _summary_row(data_type: str, total: int, gaps: pd.DataFrame) -> dict[str, object]:
    data_gaps = gaps[gaps["数据类型"] == data_type] if not gaps.empty and "数据类型" in gaps.columns else pd.DataFrame()
    statuses = data_gaps["状态"].fillna("").astype(str) if not data_gaps.empty and "状态" in data_gaps.columns else pd.Series(dtype=str)
    missing = int((statuses == "历史缺失").sum())
    stale = int((statuses == "行情滞后").sum())
    short = int((statuses == "历史不足").sum())
    failed = int((statuses == "读取失败").sum())
    issue_count = missing + stale + short + failed
    complete = max(0, int(total) - issue_count)
    coverage = "" if total <= 0 else f"{complete / int(total):.1%}"
    return {
        "数据类型": data_type,
        "总数": int(total),
        "完整": complete,
        "缺失": missing,
        "缺少": stale,
        "历史不足": short,
        "读取失败": failed,
        "覆盖率": coverage,
    }


def _tracked_index_name(item: dict[str, object], universe_item: dict[str, object]) -> str:
    if universe_item:
        index_name = str(universe_item.get("index_name", "")).strip()
        index_code = str(universe_item.get("index_code", "")).strip()
        if index_name and index_code:
            return f"{index_name}（{index_code}）"
        if index_name:
            return index_name
    return str(item.get("tracking_index", "")).strip()


def _top_sample_count(universe: pd.DataFrame) -> int:
    if universe.empty or "is_top_sample" not in universe.columns:
        return 0
    return int(universe["is_top_sample"].fillna(False).astype(bool).sum())


def _repair_suggestion(data_type: str, status: str) -> str:
    if data_type == "ETF历史":
        return "到补齐任务拉取 ETF 历史" if status != "读取失败" else "检查本地 ETF 历史文件后重新拉取"
    if data_type == "指数历史":
        return "到补齐任务补齐指数历史" if status != "读取失败" else "检查本地指数历史文件后重新拉取"
    return "到补齐任务处理"


def _display_mapping_source(value: object) -> str:
    text = str(value).strip()
    return MAPPING_SOURCE_NAMES.get(text, text)


def _display_confidence(value: object) -> str:
    text = str(value).strip()
    return CONFIDENCE_NAMES.get(text, text)


def _yes_no(value: object) -> str:
    return "是" if bool(value) else "否"


def _format_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text
