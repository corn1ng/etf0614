"""UI-neutral view models for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from etf_trading.data.index_valuations import OFFICIAL_INDEX_VALUATION_TS_CODES
from etf_trading.research.atomic_indicators import build_etf_atomic_indicator_snapshot


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


@dataclass(frozen=True)
class AtomicIndicatorFilters:
    query: str = ""
    category: str = "全部分类"
    history_status: str = "全部历史状态"
    feature_status: str = "全部特征状态"
    min_avg_amount_20: float | None = None
    only_breakout: bool = False
    only_weekly_ma10: bool = False


@dataclass(frozen=True)
class IndexHealthFilters:
    query: str = ""
    category: str = "全部分类"
    trend_status: str = "全部趋势体检"
    valuation_status: str = "全部估值体检"


@dataclass(frozen=True)
class IndexAtomicFilters:
    pool: str = "core"
    query: str = ""


ATOMIC_VIEW_MODES = ("机会特征", "体检特征")

INDEX_HEALTH_SUMMARY_COLUMNS = (
    "index_code",
    "index_name",
    "category",
    "pool",
    "index_base_date",
    "history_completeness_status",
    "history_completeness_message",
    "latest_date",
    "history_rows",
    "large_trend",
    "medium_trend",
    "small_trend",
    "allows_new_position",
    "trend_health_status",
    "valuation_overview_label",
    "valuation_health_status",
    "valuation_coverage_years",
)

ATOMIC_OPPORTUNITY_COLUMNS = (
    "ETF代码",
    "ETF名称",
    "分类",
    "20日收益",
    "60日收益",
    "20日全池排名",
    "60日全池排名",
    "20日同类排名",
    "60日同类排名",
    "60日突破",
    "周线>10周",
    "20日成交额",
)

ATOMIC_HEALTH_COLUMNS = (
    "ETF代码",
    "ETF名称",
    "分类",
    "最新交易日",
    "应有最新交易日",
    "缺失交易日",
    "历史状态",
    "状态原因",
    "特征状态",
    "可参与机会排名",
    "历史行数",
    "缺失字段",
    "收盘>20日线",
    "20日线>60日线",
    "收盘>60日线",
    "周线>30周",
    "距20日线",
    "距20日线ATR",
    "5/20成交额",
)


@dataclass(frozen=True)
class AtomicIndicatorDetailGroup:
    title: str
    rows: list[dict[str, object]]


@dataclass(frozen=True)
class IndexAtomicDetailItem:
    metric_key: str
    label: str
    value: str
    status: str
    reason: str
    as_of_date: str
    sample_count: str
    data_source: str


@dataclass(frozen=True)
class IndexAtomicDetailGroup:
    title: str
    items: list[IndexAtomicDetailItem]


@dataclass(frozen=True)
class IndexAtomicOverviewMetric:
    label: str
    value: str
    status: str
    reason: str


@dataclass(frozen=True)
class IndexAtomicTrendMarker:
    """A display-only relative height projected from finite stored trend facts."""

    label: str
    position: float


@dataclass(frozen=True)
class IndexAtomicTrendOverview:
    close: IndexAtomicOverviewMetric
    levels: tuple[IndexAtomicOverviewMetric, ...]
    relations: tuple[IndexAtomicOverviewMetric, ...]
    visible: bool
    markers: tuple[IndexAtomicTrendMarker, ...] = ()


@dataclass(frozen=True)
class IndexAtomicRangeOverview:
    headline: str
    from_high: IndexAtomicOverviewMetric
    from_low: IndexAtomicOverviewMetric
    marker: float | None
    reason: str


@dataclass(frozen=True)
class IndexAtomicOverviewEvent:
    label: str
    days: str


@dataclass(frozen=True)
class IndexAtomicOverviewEvidenceGroup:
    title: str
    items: tuple[IndexAtomicDetailItem, ...]


@dataclass(frozen=True)
class IndexAtomicOverview:
    trend: IndexAtomicTrendOverview
    range_position: IndexAtomicRangeOverview
    events: tuple[IndexAtomicOverviewEvent, ...]
    events_empty_text: str
    quality: tuple[IndexAtomicOverviewMetric, ...]
    evidence_groups: tuple[IndexAtomicOverviewEvidenceGroup, ...]


@dataclass(frozen=True)
class IndexProfileSummaryCard:
    label: str
    value: str
    detail: str
    available: bool


@dataclass(frozen=True)
class IndexProfileValuationMetric:
    label: str
    current_value: str
    percentile_3y: str
    percentile_5y: str
    percentile_10y: str
    band_5y: str
    median_5y: str
    median_deviation_5y: str
    sample_count_5y: int


@dataclass(frozen=True)
class IndexProfileValuationSection:
    visible: bool
    status: str
    reason: str
    pe_ttm: IndexProfileValuationMetric | None
    pb: IndexProfileValuationMetric | None
    metrics: tuple[IndexAtomicOverviewMetric, ...]


@dataclass(frozen=True)
class IndexProfileTrendSection:
    visible: bool
    close: IndexAtomicOverviewMetric
    rows: tuple[IndexAtomicOverviewMetric, ...]
    reason: str


@dataclass(frozen=True)
class IndexProfileMetricSection:
    title: str
    items: tuple[IndexAtomicDetailItem, ...]


@dataclass(frozen=True)
class IndexProfileView:
    identity: str
    price_as_of_date: str
    valuation_as_of_date: str
    summary_cards: tuple[IndexProfileSummaryCard, ...]
    valuation: IndexProfileValuationSection
    trend: IndexProfileTrendSection
    trend_risk_sections: tuple[IndexProfileMetricSection, ...]
    events: tuple[IndexAtomicOverviewEvent, ...]
    all_groups: tuple[IndexAtomicOverviewEvidenceGroup, ...]
    quality: tuple[IndexAtomicOverviewMetric, ...]


@dataclass(frozen=True)
class AtomicDataHealthItem:
    key: str
    label: str
    count: int
    detail: str
    filter_type: str
    filter_value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class AtomicDataHealthSummary:
    total: int
    issue_count: int
    primary_status_counts: dict[str, int]
    feature_missing_count: int
    items: list[AtomicDataHealthItem]


@dataclass(frozen=True)
class PlatformDataStatusSummary:
    etf_label: str
    index_label: str
    latest_trade_date: str
    generated_label: str


ATOMIC_HISTORY_STATUS_LABELS = {
    "ready": "数据可用",
    "complete": "数据可用",
    "stale": "行情滞后",
    "missing_history": "历史缺失",
    "short_history": "历史不足",
    "read_failed": "读取失败",
    "invalid_trade_date": "交易日无效",
}

ATOMIC_FEATURE_STATUS_LABELS = {
    "complete": "完整",
    "missing_features": "特征缺失",
    "feature_calculation_failed": "特征计算失败",
}

INDEX_ATOMIC_SNAPSHOT_STATUS_LABELS = {
    "ready": "已验证",
    "stale": "待重建",
    "missing": "不存在",
    "failed": "生成失败",
}

INDEX_ATOMIC_METRIC_STATUS_LABELS = {
    "computed": "已计算",
    "insufficient_history": "历史不足",
    "missing_input": "缺少输入字段",
    "read_failed": "读取失败",
    "calculation_failed": "计算失败",
}

INDEX_ATOMIC_HISTORY_COMPLETENESS_LABELS = {
    "COMPLETE": "历史完整",
    "INCOMPLETE": "历史不完整",
    "BASELINE_UNVERIFIED": "基日待核验",
    "SOURCE_LIMITED": "数据源历史不完整",
    "MISSING_HISTORY": "历史缺失",
    "NOT_VALIDATED": "待校验",
}

INDEX_ATOMIC_DATA_SOURCE_LABELS = {
    "akshare_zh_em": "AkShare（东方财富指数行情）",
    "akshare_zh_sina": "AkShare（新浪指数行情）",
    "akshare_csindex": "AkShare（中证官网指数行情）",
    "akshare_hk_sina": "AkShare（新浪港股指数行情）",
    "akshare_shenwan": "AkShare（申万指数行情）",
    "akshare_hk_em": "AkShare（东方财富港股指数行情）",
    "tushare_index_dailybasic": "Tushare（官方指数每日指标）",
}

INDEX_PROFILE_STATUS_LABELS = {
    "supported": "官方估值支持",
    "unsupported": "官方估值暂不支持",
    "not_synced": "官方估值尚未同步",
    "fresh": "估值数据新鲜",
    "stale": "估值数据已过期",
}

INDEX_PROFILE_ALL_GROUPS = (
    ("price_ma", "价格与均线"),
    ("ma_cross", "均线穿越"),
    ("range_position", "区间位置与突破"),
    ("return_drawdown", "收益与回撤"),
    ("volatility_volume", "波动与量能"),
    ("momentum_return", "动量与收益"),
    ("drawdown_risk", "回撤与风险"),
    ("trading_activity", "成交活跃度"),
)

INDEX_ATOMIC_DISPLAY_COLUMNS = (
    "index",
    "category",
    "latest_date",
    "close_vs_ma_20",
    "close_vs_ma_60",
    "range_20",
    "return_20",
    "data_status",
)

INDEX_ATOMIC_DETAIL_GROUPS = (
    ("price_ma", "价格与均线"),
    ("ma_cross", "均线穿越"),
    ("range_position", "区间位置与突破"),
    ("return_drawdown", "收益与回撤"),
    ("volatility_volume", "波动与量能"),
    ("data_quality", "数据质量"),
)


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


def platform_data_status_summary(snapshot: PlatformSnapshot) -> PlatformDataStatusSummary:
    """Build compact, source-data status for the global application chrome."""

    master = snapshot.master
    etf_total = int(len(master))
    etf_ready = int((master.get("本地历史", pd.Series(dtype=str)).fillna("").astype(str) == "数据可用").sum())
    indexes = snapshot.index_summary
    index_total = int(len(indexes))
    index_ready = int((indexes.get("data_status", pd.Series(dtype=str)).fillna("").astype(str) == "数据可用").sum())

    dates: list[str] = []
    for frame, column in ((master, "最新日期"), (indexes, "latest_date")):
        if column not in frame:
            continue
        values = pd.to_datetime(frame[column], errors="coerce").dropna()
        if not values.empty:
            dates.append(values.max().strftime("%Y-%m-%d"))

    return PlatformDataStatusSummary(
        etf_label=f"ETF：{etf_ready}/{etf_total} 数据可用",
        index_label=f"指数：{index_ready}/{index_total} 数据可用",
        latest_trade_date=max(dates) if dates else "",
        generated_label=f"页面计算 {snapshot.generated_at.strftime('%Y-%m-%d %H:%M')}",
    )


def index_data_status_notice(snapshot: PlatformSnapshot) -> str:
    """Describe index data readiness before users interpret market signals."""

    indexes = snapshot.index_summary
    latest_date = ""
    if "latest_date" in indexes:
        dates = pd.to_datetime(indexes["latest_date"], errors="coerce").dropna()
        if not dates.empty:
            latest_date = dates.max().strftime("%Y-%m-%d")
    status = platform_data_status_summary(snapshot)
    return (
        f"指数数据状态：{status.index_label}；最近有效交易日 {latest_date or '暂无'}。"
        "非“数据可用”的指数不应作为趋势或买卖依据。"
    )


def market_overview(snapshot: PlatformSnapshot) -> dict[str, object]:
    frame = snapshot.index_summary.copy()
    if frame.empty:
        return {
            "total_indexes": 0,
            "allowed_indexes": 0,
            "core_indexes": 0,
            "research_indexes": 0,
            "incomplete_history_indexes": 0,
            "categories": [],
        }

    allowed = _allowed_series(frame)
    pools = _string_series(frame, "pool")
    completeness = _string_series(frame, "history_completeness_status")
    categories = []
    if "category" in frame:
        grouped = frame.assign(_allowed=allowed).groupby("category", dropna=False)
        for category, group in grouped:
            categories.append({"category": str(category), "total": int(len(group)), "allowed": int(group["_allowed"].sum())})
    return {
        "total_indexes": int(len(frame)),
        "allowed_indexes": int(allowed.sum()),
        "core_indexes": int((pools == "core").sum()),
        "research_indexes": int((pools == "research").sum()),
        "incomplete_history_indexes": int(
            completeness.isin(["INCOMPLETE", "MISSING_HISTORY", "BASELINE_REFERENCED", "BASELINE_UNVERIFIED", "READ_FAILED", "NOT_VALIDATED"]).sum()
        ),
        "categories": categories,
    }


def etf_overview_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.master)


def maintenance_rows(snapshot: PlatformSnapshot) -> list[dict[str, object]]:
    return _records(snapshot.gaps)


def build_atomic_indicator_snapshot(snapshot: PlatformSnapshot, parquet_store, today: pd.Timestamp | None = None) -> pd.DataFrame:
    return build_etf_atomic_indicator_snapshot(snapshot.master, parquet_store, today=today)


def atomic_indicator_summary(frame: pd.DataFrame) -> list[MetricTile]:
    if frame.empty:
        return [
            MetricTile("ETF主池", "0", "warning", "场内"),
            MetricTile("数据可用", "0", "warning", "主状态"),
            MetricTile("可参与机会排名", "0", "warning", "数据与特征均可用"),
            MetricTile("行情滞后", "0", "neutral", "需补齐行情"),
            MetricTile("历史不足", "0", "neutral", "样本行数不足"),
            MetricTile("特征缺失", "0", "neutral", "指标暂不可算"),
        ]

    history = _string_series(frame, "history_status").replace({"complete": "ready"})
    feature = _string_series(frame, "feature_status")
    rank_eligible = _rank_eligible_series(frame)
    ready = int((history == "ready").sum())
    stale = int((history == "stale").sum())
    short = int((history == "short_history").sum())
    feature_missing = int((feature != "complete").sum())
    return [
        MetricTile("ETF主池", str(len(frame)), "neutral", "场内"),
        MetricTile("数据可用", str(ready), "success" if ready == len(frame) else "warning", "主状态"),
        MetricTile("可参与机会排名", str(int(rank_eligible.sum())), "success" if rank_eligible.any() else "warning", "数据与特征均可用"),
        MetricTile("行情滞后", str(stale), "warning" if stale else "success", "需补齐行情"),
        MetricTile("历史不足", str(short), "warning" if short else "success", "样本行数不足"),
        MetricTile("特征缺失", str(feature_missing), "warning" if feature_missing else "success", "指标暂不可算"),
    ]


def atomic_data_update_health(frame: pd.DataFrame) -> list[AtomicDataHealthItem]:
    history = _string_series(frame, "history_status").replace({"complete": "ready"})
    feature = _string_series(frame, "feature_status")

    return [
        AtomicDataHealthItem("ready", "数据可用", int((history == "ready").sum()), "本地行情满足行数与新鲜度要求", "history_status", "ready", "success"),
        AtomicDataHealthItem("stale", "行情滞后", int((history == "stale").sum()), "本地行情不是最新", "history_status", "stale", "warning"),
        AtomicDataHealthItem("short_history", "历史不足", int((history == "short_history").sum()), "样本行数不足", "history_status", "short_history", "warning"),
        AtomicDataHealthItem("missing_history", "历史缺失", int((history == "missing_history").sum()), "没有本地历史", "history_status", "missing_history", "danger"),
        AtomicDataHealthItem("read_failed", "读取失败", int((history == "read_failed").sum()), "文件或格式异常", "history_status", "read_failed", "danger"),
        AtomicDataHealthItem("missing_features", "特征缺失", int((feature == "missing_features").sum()), "指标字段暂不可算", "feature_status", "missing_features", "warning"),
    ]


def atomic_data_health_summary(frame: pd.DataFrame) -> AtomicDataHealthSummary:
    """Summarize one primary status per ETF without double-counting reasons."""

    items = atomic_data_update_health(frame)
    primary_items = items[:5]
    primary_status_counts = {item.label: item.count for item in primary_items}
    total = int(sum(primary_status_counts.values()))
    ready = primary_status_counts["数据可用"]
    feature_missing = next(item.count for item in items if item.key == "missing_features")
    return AtomicDataHealthSummary(
        total=total,
        issue_count=total - ready,
        primary_status_counts=primary_status_counts,
        feature_missing_count=feature_missing,
        items=items,
    )


def atomic_indicator_rows(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
    limit: int | None = None,
    view_mode: str = "机会特征",
) -> list[dict[str, object]]:
    data = filter_atomic_indicator_frame(frame, filters)
    if view_mode == "机会特征":
        data = data[_rank_eligible_series(data)]
    if data.empty:
        return []

    columns = ATOMIC_HEALTH_COLUMNS if view_mode == "体检特征" else ATOMIC_OPPORTUNITY_COLUMNS
    rows = []
    records = data.head(limit).to_dict("records") if limit is not None else data.to_dict("records")
    for row in records:
        display = _atomic_display_row(row)
        rows.append({column: display.get(column, "") for column in columns})
    return rows


def filter_atomic_indicator_frame(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    filters = filters or AtomicIndicatorFilters()
    data = frame.copy()
    query = filters.query.strip().lower()
    if query:
        searchable = (
            data.get("etf_code", "").astype(str)
            + " "
            + data.get("name", "").astype(str)
            + " "
            + data.get("category", "").astype(str)
        ).str.lower()
        data = data[searchable.str.contains(query, na=False)]

    if filters.category not in {"", "全部", "全部分类"} and "category" in data:
        data = data[data["category"].fillna("").astype(str) == filters.category]
    if filters.history_status not in {"", "全部", "全部历史状态"} and "history_status" in data:
        data = data[data["history_status"].fillna("").astype(str) == filters.history_status]
    if filters.feature_status not in {"", "全部", "全部特征状态"} and "feature_status" in data:
        data = data[data["feature_status"].fillna("").astype(str) == filters.feature_status]
    if filters.min_avg_amount_20 is not None and "avg_amount_20" in data:
        data = data[pd.to_numeric(data["avg_amount_20"], errors="coerce").fillna(0) >= float(filters.min_avg_amount_20)]
    if filters.only_breakout and "is_60d_close_breakout" in data:
        data = data[data["is_60d_close_breakout"].map(_truthy)]
    if filters.only_weekly_ma10 and "weekly_close_above_ma10" in data:
        data = data[data["weekly_close_above_ma10"].map(_truthy)]

    if "return_20_rank_all" in data:
        data = data.assign(_rank=pd.to_numeric(data["return_20_rank_all"], errors="coerce"))
        data = data.sort_values(["_rank", "etf_code"], na_position="last").drop(columns=["_rank"])
    return data


def atomic_indicator_detail_options(
    frame: pd.DataFrame,
    filters: AtomicIndicatorFilters | None = None,
    limit: int | None = None,
    opportunity_only: bool = False,
) -> list[str]:
    data = filter_atomic_indicator_frame(frame, filters)
    if opportunity_only:
        data = data[_rank_eligible_series(data)]
    options: list[str] = []
    records = data.head(limit).fillna("").to_dict("records") if limit is not None else data.fillna("").to_dict("records")
    for row in records:
        code = str(row.get("etf_code", "")).strip()
        if not code:
            continue
        name = str(row.get("name", "")).strip()
        category = str(row.get("category", "")).strip()
        label = f"{code} {name}".strip()
        if category:
            label = f"{label} · {category}"
        options.append(label)
    return options


def atomic_indicator_detail_groups(frame: pd.DataFrame, etf_code: str) -> list[AtomicIndicatorDetailGroup]:
    if frame.empty or not etf_code or "etf_code" not in frame:
        return []

    matches = frame[frame["etf_code"].fillna("").astype(str) == str(etf_code)]
    if matches.empty:
        return []

    display = _atomic_display_row(matches.iloc[0].to_dict())
    groups = (
        ("身份信息", ("ETF代码", "ETF名称", "分类", "交易所", "最新交易日")),
        ("数据体检", ("历史状态", "特征状态", "历史行数", "缺失字段")),
        ("相对强度", ("20日收益", "60日收益", "20日全池排名", "60日全池排名", "20日同类排名", "60日同类排名")),
        ("趋势结构", ("收盘>20日线", "20日线>60日线", "收盘>60日线", "周线>10周", "周线>30周", "60日突破", "60日线20日斜率")),
        ("量能位置", ("5日成交额", "20日成交额", "5/20成交额")),
        ("偏离程度", ("距20日线", "距20日线ATR")),
    )
    return [
        AtomicIndicatorDetailGroup(
            title=title,
            rows=[{"指标": label, "数值": display.get(label, "")} for label in labels],
        )
        for title, labels in groups
    ]


def code_from_option(option: str | None) -> str:
    if not option:
        return ""
    return str(option).strip().split(maxsplit=1)[0]


def index_choice_options(index_summary: pd.DataFrame, *, include_research: bool = False) -> list[str]:
    if index_summary.empty:
        return []

    frame = index_summary
    if "pool" in frame and not include_research:
        frame = frame[frame["pool"].fillna("").astype(str) == "core"]
    options: list[str] = []
    for row in frame.fillna("").to_dict("records"):
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


def index_health_summary(frame: pd.DataFrame) -> list[MetricTile]:
    if frame.empty:
        return [
            MetricTile("指数池", "0", "warning", "体检对象"),
            MetricTile("趋势通过", "0", "warning", "趋势门槛"),
            MetricTile("估值完整", "0", "warning", "PE/PB/ERP"),
            MetricTile("估值缺失", "0", "neutral", "需补缓存"),
        ]

    allowed = _allowed_series(frame)
    valuation_status = _string_series(frame, "valuation_health_status")
    complete = int((valuation_status == "complete").sum())
    missing = int(valuation_status.isin(["missing_valuation", "missing", "read_failed"]).sum())
    return [
        MetricTile("指数池", str(len(frame)), "neutral", "体检对象"),
        MetricTile("趋势通过", str(int(allowed.sum())), "success" if allowed.any() else "warning", "趋势门槛"),
        MetricTile("估值完整", str(complete), "success" if complete == len(frame) else "warning", "PE/PB/ERP"),
        MetricTile("估值缺失", str(missing), "warning" if missing else "success", "需补缓存"),
    ]


def index_health_filter_options(frame: pd.DataFrame, column: str, all_label: str) -> list[str]:
    if frame.empty or column not in frame:
        return [all_label]
    values: list[str] = []
    seen: set[str] = set()
    for value in frame[column].dropna().astype(str).tolist():
        text = value.strip()
        if not text or text in seen:
            continue
        values.append(text)
        seen.add(text)
    return [all_label, *values]


def index_health_rows(
    frame: pd.DataFrame,
    filters: IndexHealthFilters | None = None,
    limit: int = 300,
) -> list[dict[str, object]]:
    data = filter_index_health_frame(frame, filters)
    if data.empty:
        return []

    rows: list[dict[str, object]] = []
    for row in data.head(limit).fillna("").to_dict("records"):
        rows.append({column: row.get(column, "") for column in INDEX_HEALTH_SUMMARY_COLUMNS})
    return rows


def filter_index_health_frame(frame: pd.DataFrame, filters: IndexHealthFilters | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    filters = filters or IndexHealthFilters()
    data = frame.copy()
    query = filters.query.strip().lower()
    if query:
        searchable = (
            data.get("index_code", "").astype(str)
            + " "
            + data.get("index_name", "").astype(str)
            + " "
            + data.get("category", "").astype(str)
        ).str.lower()
        data = data[searchable.str.contains(query, na=False)]

    if filters.category not in {"", "全部", "全部分类"} and "category" in data:
        data = data[data["category"].fillna("").astype(str) == filters.category]
    if filters.trend_status not in {"", "全部", "全部趋势体检"} and "trend_health_status" in data:
        data = data[data["trend_health_status"].fillna("").astype(str) == filters.trend_status]
    if filters.valuation_status not in {"", "全部", "全部估值体检"} and "valuation_health_status" in data:
        data = data[data["valuation_health_status"].fillna("").astype(str) == filters.valuation_status]

    sort_columns = [column for column in ("category", "index_code") if column in data]
    return data.sort_values(sort_columns) if sort_columns else data


def index_health_detail_options(
    frame: pd.DataFrame,
    filters: IndexHealthFilters | None = None,
    limit: int = 300,
) -> list[str]:
    data = filter_index_health_frame(frame, filters)
    return index_choice_options(data.head(limit))


def index_health_detail_rows(details: pd.DataFrame, index_code: str, detail_kind: str) -> list[dict[str, object]]:
    if details.empty or not index_code or "index_code" not in details:
        return []

    kind_series = details["detail_kind"].fillna("").astype(str) if "detail_kind" in details else pd.Series("", index=details.index)
    data = details[
        (details["index_code"].fillna("").astype(str) == str(index_code))
        & (kind_series == str(detail_kind))
    ].copy()
    if data.empty:
        return []

    rows: list[dict[str, object]] = []
    for row in data.fillna("").to_dict("records"):
        rows.append(
            {
                "metric_label": _text(row.get("metric_label")),
                "current_value": _format_index_detail_value(row.get("current_value")),
                "status": _text(row.get("status")),
                "historical_percentile": _format_percentile(row.get("historical_percentile")),
                "reason": _text(row.get("reason")),
                "sample_count": _value_or_blank(row.get("sample_count")),
                "latest_date": _text(row.get("latest_date")),
                "data_source": _text(row.get("data_source")),
            }
        )
    return rows


def build_index_atomic_rows(
    summary: pd.DataFrame,
    filters: IndexAtomicFilters | None = None,
) -> list[dict[str, object]]:
    """Format stored index atomic summary facts for the fixed health table."""

    if summary.empty or "pool" not in summary:
        return []

    filters = filters or IndexAtomicFilters()
    if filters.pool not in {"core", "research"}:
        return []

    data = summary[_string_series(summary, "pool") == filters.pool].copy()
    query = filters.query.strip().lower()
    if query:
        searchable = (_string_series(data, "index_code") + " " + _string_series(data, "index_name")).str.lower()
        data = data[searchable.str.contains(query, regex=False, na=False)]
    if data.empty:
        return []

    if "catalog_order" in data:
        data = data.assign(_catalog_order=pd.to_numeric(data["catalog_order"], errors="coerce"))
        data = data.sort_values("_catalog_order", kind="stable", na_position="last").drop(columns=["_catalog_order"])

    return [_index_atomic_display_row(row) for row in data.to_dict("records")]


def index_atomic_detail_groups(details: pd.DataFrame, index_code: str) -> list[IndexAtomicDetailGroup]:
    """Group stored atomic detail rows without calculating additional metrics."""

    if details.empty or not index_code or "index_code" not in details:
        return []

    data = details[details["index_code"].fillna("").astype(str) == str(index_code)].copy()
    if data.empty:
        return []
    group_keys = _string_series(data, "group_key")

    groups: list[IndexAtomicDetailGroup] = []
    for group_key, title in INDEX_ATOMIC_DETAIL_GROUPS:
        items = [_index_atomic_detail_item(row) for row in data[group_keys == group_key].to_dict("records")]
        groups.append(IndexAtomicDetailGroup(title=title, items=items))
    return groups


def index_atomic_overview(summary: dict[str, object], details: pd.DataFrame, index_code: str) -> IndexAtomicOverview | None:
    if not index_code or details.empty or "index_code" not in details:
        return None
    data = details[details["index_code"].fillna("").astype(str) == str(index_code)].copy()
    if data.empty:
        return None
    rows = {str(row.get("metric_key") or ""): row for row in data.to_dict("records")}
    close = _overview_metric(rows.get("close"), "最新收盘")
    levels = tuple(_overview_metric(rows.get("ma_{}".format(window)), "MA{}".format(window)) for window in (20, 60, 120, 250))
    relations = tuple(_overview_metric(rows.get("close_above_ma_{}".format(window)), "相对MA{}".format(window)) for window in (20, 60, 120, 250))
    from_high = _overview_metric(rows.get("range_20_from_high"), "距20日高点")
    from_low = _overview_metric(rows.get("range_20_from_low"), "距20日低点")
    high_flag = _overview_metric(rows.get("range_20_high"), "20日收盘新高")
    low_flag = _overview_metric(rows.get("range_20_low"), "20日收盘新低")
    markers = _trend_ladder_markers(rows)
    trend_visible = (
        close.status == "已计算"
        and all(item.status == "已计算" for item in levels)
        and all(item.status == "已计算" for item in relations)
        and bool(markers)
    )
    headline = _range_headline(high_flag, low_flag, from_high, from_low)
    reason = next((item.reason for item in (from_high, from_low, high_flag, low_flag) if item.status != "已计算"), "")
    marker = _range_marker(rows.get("close"), rows.get("range_20_from_high"), rows.get("range_20_from_low")) if headline != "数据不足" else None
    if headline != "数据不足" and marker is None:
        headline = "数据不足"
        reason = "数据不足"
    return IndexAtomicOverview(
        trend=IndexAtomicTrendOverview(close, levels, relations, trend_visible, markers if trend_visible else ()),
        range_position=IndexAtomicRangeOverview(headline, from_high, from_low, marker, reason),
        events=_overview_events(rows),
        events_empty_text="暂无已记录事件",
        quality=_overview_quality(summary),
        evidence_groups=tuple(
            IndexAtomicOverviewEvidenceGroup(group.title, tuple(group.items))
            for group in index_atomic_detail_groups(details, index_code)
            if group.title != "数据质量"
        ),
    )


def index_profile_view(
    summary: dict[str, object],
    details: pd.DataFrame,
    index_code: str,
) -> IndexProfileView | None:
    """Project one published index snapshot into the five-tab read-only profile."""

    if not index_code or details.empty or "index_code" not in details:
        return None
    data = details[details["index_code"].fillna("").astype(str) == str(index_code)].copy()
    if data.empty:
        return None

    records = data.to_dict("records")
    rows = {str(row.get("metric_key") or ""): row for row in records}
    code = _text(summary.get("index_code")) or str(index_code)
    name = _text(summary.get("index_name"))
    identity = " · ".join(part for part in (code, name) if part) or "数据不足"
    price_as_of_date = _format_index_atomic_date(summary.get("latest_date"))
    valuation_as_of_date = _profile_date(summary.get("valuation_as_of_date"), rows.get("valuation_as_of_date"))
    valuation = _profile_valuation_section(summary, rows)
    trend = _profile_trend_section(records, rows)

    return IndexProfileView(
        identity=identity,
        price_as_of_date=price_as_of_date,
        valuation_as_of_date=valuation_as_of_date,
        summary_cards=_profile_summary_cards(summary, rows),
        valuation=valuation,
        trend=trend,
        trend_risk_sections=_profile_trend_risk_sections(records),
        events=_profile_events(rows),
        all_groups=_profile_all_groups(records),
        quality=_profile_quality(summary, records, rows),
    )


def _profile_summary_cards(
    summary: dict[str, object],
    rows: dict[str, dict[str, object]],
) -> tuple[IndexProfileSummaryCard, ...]:
    pe = _profile_summary_card("PE-TTM", rows.get("pe_ttm"), summary.get("pe_ttm"), rows.get("pe_ttm_percentile_5y"))
    pb = _profile_summary_card("PB", rows.get("pb"), summary.get("pb"), rows.get("pb_percentile_5y"))
    trend_row = rows.get("close_vs_ma_20")
    trend_value = trend_row.get("value") if trend_row is not None else summary.get("close_vs_ma_20")
    trend_available = _profile_row_available(trend_row, trend_value)
    trend_detail = _format_index_atomic_relative_ma(trend_value) if trend_available else _profile_reason(trend_row)
    drawdown_row = rows.get("drawdown_250")
    drawdown_value = drawdown_row.get("value") if drawdown_row is not None else summary.get("drawdown_250")
    drawdown_available = _profile_row_available(drawdown_row, drawdown_value)
    return (
        pe,
        pb,
        IndexProfileSummaryCard("趋势位置", trend_detail, "相对20日均线", trend_available),
        IndexProfileSummaryCard(
            "250日当前回撤",
            _format_index_atomic_percent(drawdown_value) if drawdown_available else "数据不足",
            "当前收盘相对250日内此前高点",
            drawdown_available,
        ),
    )


def _profile_summary_card(
    label: str,
    row: dict[str, object] | None,
    summary_value: object,
    percentile_row: dict[str, object] | None,
) -> IndexProfileSummaryCard:
    value = row.get("value") if row is not None else summary_value
    available = _profile_row_available(row, value)
    detail = _profile_percentile(percentile_row.get("value")) if percentile_row is not None else ""
    return IndexProfileSummaryCard(
        label,
        _format_index_atomic_number(value) if available else "数据不足",
        f"5年分位 {detail}" if detail else (_profile_reason(row) if not available else "5年分位数据不足"),
        available,
    )


def _profile_valuation_section(
    summary: dict[str, object],
    rows: dict[str, dict[str, object]],
) -> IndexProfileValuationSection:
    support_row = rows.get("valuation_support_status")
    support = _text(summary.get("valuation_support_status")) or _text(support_row.get("value") if support_row else "")
    freshness_row = rows.get("valuation_freshness_status")
    freshness = _text(summary.get("valuation_freshness_status")) or _text(freshness_row.get("value") if freshness_row else "")
    visible = support == "supported"
    reason = _profile_reason(support_row)
    if visible and freshness_row is not None and freshness != "fresh":
        reason = _profile_reason(freshness_row)
    if not reason:
        reason = INDEX_PROFILE_STATUS_LABELS.get(support, "数据不足")
    status_code = freshness if visible else support
    status = INDEX_PROFILE_STATUS_LABELS.get(status_code) or "数据不足"
    metric_rows = tuple(
        _profile_overview_metric(row, _index_atomic_detail_label(_text(row.get("metric_key")), row.get("metric_label")))
        for row in rows.values()
        if _text(row.get("group_key")) == "valuation"
    )
    return IndexProfileValuationSection(
        visible=visible,
        status=status,
        reason=reason,
        pe_ttm=_profile_valuation_metric("PE-TTM", "pe_ttm", rows) if visible else None,
        pb=_profile_valuation_metric("PB", "pb", rows) if visible else None,
        metrics=metric_rows,
    )


def _profile_valuation_metric(
    label: str,
    metric_key: str,
    rows: dict[str, dict[str, object]],
) -> IndexProfileValuationMetric:
    current = rows.get(metric_key)
    percentile = {window: rows.get(f"{metric_key}_percentile_{window}") for window in ("3y", "5y", "10y")}
    median = rows.get(f"{metric_key}_median_5y")
    deviation = rows.get(f"{metric_key}_median_deviation_5y")
    band = rows.get(f"{metric_key}_band_5y")
    return IndexProfileValuationMetric(
        label=label,
        current_value=_profile_number(current.get("value") if current else None),
        percentile_3y=_profile_percentile(percentile["3y"].get("value") if percentile["3y"] else None),
        percentile_5y=_profile_percentile(percentile["5y"].get("value") if percentile["5y"] else None),
        percentile_10y=_profile_percentile(percentile["10y"].get("value") if percentile["10y"] else None),
        band_5y=_text(band.get("value")) if band and _profile_row_available(band, band.get("value")) else "数据不足",
        median_5y=_profile_number(median.get("value") if median else None),
        median_deviation_5y=_profile_percentile(deviation.get("value") if deviation else None),
        sample_count_5y=_profile_sample_count(percentile["5y"]),
    )


def _profile_trend_section(
    records: list[dict[str, object]],
    rows: dict[str, dict[str, object]],
) -> IndexProfileTrendSection:
    close = _overview_metric(rows.get("close"), "最新收盘")
    trend_records = [
        row for row in records
        if _text(row.get("group_key")) in {"price_ma", "ma_cross", "range_position"}
        and _text(row.get("metric_key")) != "close"
    ]
    trend_rows = tuple(
        _overview_metric(row, _index_atomic_detail_label(_text(row.get("metric_key")), row.get("metric_label")))
        for row in trend_records
    )
    visible = close.status == "已计算"
    reason = "" if visible else close.reason
    if visible:
        reason = next((item.reason for item in trend_rows if item.status != "已计算"), "")
    return IndexProfileTrendSection(visible, close, trend_rows, reason)


def _profile_trend_risk_sections(records: list[dict[str, object]]) -> tuple[IndexProfileMetricSection, ...]:
    selectors = (
        ("趋势结构", lambda row: _text(row.get("group_key")) in {"price_ma", "ma_cross", "range_position"}),
        ("动量与收益", lambda row: _text(row.get("group_key")) == "momentum_return" or _text(row.get("metric_key")).startswith("return_") or _text(row.get("metric_key")) in {"rsi_14", "up_day_ratio_20"}),
        ("回撤与风险", lambda row: _text(row.get("group_key")) == "drawdown_risk" or _text(row.get("metric_key")).startswith(("drawdown_", "max_drawdown_")) or (_text(row.get("group_key")) == "volatility_volume" and not _text(row.get("metric_key")).startswith("amount_"))),
        ("成交活跃度", lambda row: _text(row.get("group_key")) == "trading_activity" or _text(row.get("metric_key")).startswith("amount_")),
    )
    return tuple(
        IndexProfileMetricSection(title, tuple(_index_atomic_detail_item(row) for row in records if selector(row)))
        for title, selector in selectors
    )


def _profile_all_groups(records: list[dict[str, object]]) -> tuple[IndexAtomicOverviewEvidenceGroup, ...]:
    return tuple(
        IndexAtomicOverviewEvidenceGroup(title, tuple(_index_atomic_detail_item(row) for row in records if _text(row.get("group_key")) == group_key))
        for group_key, title in INDEX_PROFILE_ALL_GROUPS
        if any(_text(row.get("group_key")) == group_key for row in records)
    )


def _profile_quality(
    summary: dict[str, object],
    records: list[dict[str, object]],
    rows: dict[str, dict[str, object]],
) -> tuple[IndexAtomicOverviewMetric, ...]:
    summary_quality = _overview_quality(summary)
    detail_quality = tuple(
        _overview_metric(row, _index_atomic_detail_label(_text(row.get("metric_key")), row.get("metric_label")))
        for row in records
        if _text(row.get("group_key")) == "data_quality"
    )
    valuation_quality = tuple(
        _profile_overview_metric(rows[key], _index_atomic_detail_label(key, rows[key].get("metric_label")))
        for key in ("valuation_support_status", "valuation_as_of_date", "valuation_freshness_status", "valuation_source")
        if key in rows
    )
    return summary_quality + detail_quality + valuation_quality


def _profile_events(rows: dict[str, dict[str, object]]) -> tuple[IndexAtomicOverviewEvent, ...]:
    price_events = _overview_events(rows)
    valuation_events = []
    for metric_key, label in (("pe_ttm_5y_band_changed", "PE-TTM 5年分位区间变化"), ("pb_5y_band_changed", "PB 5年分位区间变化")):
        row = rows.get(metric_key)
        if row is None or _text(row.get("status")) != "computed" or not _truthy(row.get("value")):
            continue
        valuation_events.append(IndexAtomicOverviewEvent(label, _format_index_atomic_date(row.get("as_of_date"))))
    return price_events + tuple(valuation_events)


def _profile_overview_metric(row: dict[str, object], label: str) -> IndexAtomicOverviewMetric:
    metric_key = _text(row.get("metric_key"))
    if metric_key in {"valuation_support_status", "valuation_freshness_status"}:
        value = INDEX_PROFILE_STATUS_LABELS.get(_text(row.get("value")), "数据不足")
        status = INDEX_PROFILE_STATUS_LABELS.get(_text(row.get("status"))) or _index_atomic_status_label(row.get("status"))
        return IndexAtomicOverviewMetric(label, value, status, _profile_reason(row))
    return _overview_metric(row, label)


def _profile_row_available(row: dict[str, object] | None, value: object) -> bool:
    if _missing(value) or value == "":
        return False
    return row is None or _text(row.get("status")) == "computed"


def _profile_reason(row: dict[str, object] | None) -> str:
    return _text(row.get("reason")) if row is not None else "数据不足"


def _profile_date(summary_value: object, row: dict[str, object] | None) -> str:
    value = summary_value if not _missing(summary_value) and summary_value != "" else (row.get("value") if row else None)
    return _format_index_atomic_date(value)


def _profile_number(value: object) -> str:
    return _format_index_atomic_number(value)


def _profile_percentile(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "数据不足"


def _profile_sample_count(row: dict[str, object] | None) -> int:
    if row is None or _missing(row.get("sample_count")):
        return 0
    try:
        return int(float(row["sample_count"]))
    except (TypeError, ValueError):
        return 0


def _trend_ladder_markers(rows: dict[str, dict[str, object]]) -> tuple[IndexAtomicTrendMarker, ...]:
    """Normalize stored close and MA facts into transient relative ladder heights."""

    sources = (("收盘", "close"), ("MA20", "ma_20"), ("MA60", "ma_60"), ("MA120", "ma_120"), ("MA250", "ma_250"))
    values: list[tuple[str, float]] = []
    for label, metric_key in sources:
        row = rows.get(metric_key)
        if row is None or _text(row.get("status")) != "computed":
            return ()
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            return ()
        if not math.isfinite(value):
            return ()
        values.append((label, value))

    lower = min(value for _, value in values)
    upper = max(value for _, value in values)
    span = upper - lower
    return tuple(
        IndexAtomicTrendMarker(label, 0.5 if span == 0 else (value - lower) / span)
        for label, value in values
    )


def _overview_metric(row: dict[str, object] | None, label: str) -> IndexAtomicOverviewMetric:
    if row is None:
        return IndexAtomicOverviewMetric(label, "数据不足", "数据不足", "快照中缺少该原子指标")
    metric_key = _text(row.get("metric_key"))
    raw_value = row.get("value")
    value = _format_index_atomic_detail_value(metric_key, raw_value)
    if metric_key == "close" or metric_key.startswith("ma_"):
        try:
            if not math.isfinite(float(raw_value)):
                return IndexAtomicOverviewMetric(label, "数据不足", "数据不足", "快照中该原子指标不是有限数值")
        except (TypeError, ValueError):
            pass
        value = _format_number(raw_value) if not _missing(raw_value) else value
    return IndexAtomicOverviewMetric(label, value, _index_atomic_status_label(row.get("status")), _text(row.get("reason")) or "数据不足")


def _range_headline(high_flag, low_flag, from_high, from_low) -> str:
    if high_flag.status != "已计算" or low_flag.status != "已计算":
        return "数据不足"
    if high_flag.value == "是":
        return "20日收盘新高"
    if low_flag.value == "是":
        return "20日收盘新低"
    return "20日区间内" if from_high.status == "已计算" and from_low.status == "已计算" else "数据不足"


def _range_marker(
    close: dict[str, object] | None,
    from_high: dict[str, object] | None,
    from_low: dict[str, object] | None,
) -> float | None:
    try:
        close_value = float(close.get("value"))
        high_offset = float(from_high.get("value"))
        low_offset = float(from_low.get("value"))
        if not all(math.isfinite(value) for value in (close_value, high_offset, low_offset)):
            return None
        high = close_value / (1 + high_offset)
        low = close_value / (1 + low_offset)
        if not all(math.isfinite(value) for value in (high, low)) or high <= low:
            return None
        marker = max(0.0, min(1.0, (close_value - low) / (high - low)))
        return marker if math.isfinite(marker) else None
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None


def _overview_events(rows: dict[str, dict[str, object]]) -> tuple[IndexAtomicOverviewEvent, ...]:
    events: list[tuple[int, IndexAtomicOverviewEvent]] = []
    for direction, label in (("up", "上穿"), ("down", "下穿")):
        for window in (20, 60, 120, 250):
            row = rows.get("days_since_ma_cross_{}_{}".format(direction, window))
            if row is None or _text(row.get("status")) != "computed":
                continue
            try:
                event_age = float(row.get("value"))
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(event_age) or event_age < 0:
                continue
            days = int(event_age)
            events.append((days, IndexAtomicOverviewEvent("{}{}日均线".format(label, window), "{} 日前".format(days))))
    return tuple(event for _, event in sorted(events, key=lambda item: item[0])[:2])


def _overview_quality(summary: dict[str, object]) -> tuple[IndexAtomicOverviewMetric, ...]:
    return (
        IndexAtomicOverviewMetric("快照状态", _index_atomic_status_label(summary.get("snapshot_status")), "", _text(summary.get("snapshot_reason"))),
        IndexAtomicOverviewMetric("历史覆盖", _index_atomic_status_label(summary.get("history_completeness_status")), "", _text(summary.get("history_completeness_message"))),
        IndexAtomicOverviewMetric("有效交易日", _format_index_atomic_count(summary.get("history_rows")), "", ""),
        IndexAtomicOverviewMetric("数据来源", _index_atomic_data_source_label(summary.get("data_source")), "", ""),
    )


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


def default_etf_input(rows: list[dict[str, object]]) -> str:
    for row in rows:
        code = _row_value(row, "ETF代码", "etf_code")
        if not code:
            continue
        name = _row_value(row, "ETF名称", "name")
        return f"{code} {name}".strip()
    return ""


def resolve_etf_code_from_query(query: str | None, rows: list[dict[str, object]]) -> str:
    text = str(query or "").strip()
    if not text:
        raise ValueError("请输入 ETF 代码或名称")

    normalized = text.lower()
    first_token = code_from_option(text).lower()
    fuzzy_matches: list[str] = []
    seen: set[str] = set()
    for row in rows:
        code = _row_value(row, "ETF代码", "etf_code")
        if not code:
            continue
        code_lower = code.lower()
        name = _row_value(row, "ETF名称", "name")
        category = _row_value(row, "分类", "category")
        if normalized == code_lower or first_token == code_lower:
            return code
        searchable = f"{code} {name} {category}".strip().lower()
        if normalized in searchable and code not in seen:
            fuzzy_matches.append(code)
            seen.add(code)

    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        preview = "、".join(fuzzy_matches[:5])
        raise ValueError(f"匹配到 {len(fuzzy_matches)} 只 ETF，请输入完整代码：{preview}")
    raise ValueError("ETF 不在主列表，请先初始化 ETF 主列表或输入完整代码")


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


def _string_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series("", index=frame.index, dtype=str)
    return frame[column].fillna("").astype(str).str.strip()


def _rank_eligible_series(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(False, index=frame.index, dtype=bool)
    if "is_rank_eligible" in frame:
        return frame["is_rank_eligible"].fillna(False).map(_truthy).astype(bool)
    history = _string_series(frame, "history_status").replace({"complete": "ready"})
    feature = _string_series(frame, "feature_status")
    return ((history == "ready") & (feature == "complete")).astype(bool)


def _atomic_display_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "ETF代码": _text(row.get("etf_code")),
        "ETF名称": _text(row.get("name")),
        "分类": _text(row.get("category")),
        "交易所": _text(row.get("exchange")),
        "最新交易日": _text(row.get("latest_trade_date")),
        "应有最新交易日": _text(row.get("expected_trade_date")),
        "缺失交易日": _value_or_blank(row.get("trading_day_lag")),
        "历史状态": _status_text(row.get("history_status"), ATOMIC_HISTORY_STATUS_LABELS),
        "状态原因": _text(row.get("history_reason_codes")),
        "特征状态": _status_text(row.get("feature_status"), ATOMIC_FEATURE_STATUS_LABELS),
        "可参与机会排名": _format_bool(row.get("is_rank_eligible")),
        "历史行数": _value_or_blank(row.get("history_rows")),
        "20日收益": _format_pct(row.get("return_20")),
        "60日收益": _format_pct(row.get("return_60")),
        "20日全池排名": _format_rank(row.get("return_20_rank_all")),
        "60日全池排名": _format_rank(row.get("return_60_rank_all")),
        "20日同类排名": _format_rank(row.get("return_20_rank_category")),
        "60日同类排名": _format_rank(row.get("return_60_rank_category")),
        "收盘>20日线": _format_bool(row.get("close_above_ma20")),
        "20日线>60日线": _format_bool(row.get("ma20_above_ma60")),
        "收盘>60日线": _format_bool(row.get("close_above_ma60")),
        "周线>10周": _format_bool(row.get("weekly_close_above_ma10")),
        "周线>30周": _format_bool(row.get("weekly_close_above_ma30")),
        "60日线20日斜率": _format_number(row.get("ma60_slope_20")),
        "5日成交额": _format_amount(row.get("avg_amount_5")),
        "20日成交额": _format_amount(row.get("avg_amount_20")),
        "5/20成交额": _format_number(row.get("amount_ratio_5_20")),
        "距20日线": _format_pct(row.get("distance_ma20_pct")),
        "距20日线ATR": _format_number(row.get("distance_ma20_atr")),
        "60日突破": _format_bool(row.get("is_60d_close_breakout")),
        "缺失字段": _text(row.get("missing_feature_names")),
    }


def _format_pct(value: object) -> str:
    if _missing(value):
        return "缺失"
    return f"{float(value):.1%}"


def _value_or_blank(value: object) -> object:
    if _missing(value):
        return ""
    return value


def _status_text(value: object, mapping: dict[str, str]) -> str:
    if _missing(value):
        return "缺失"
    text = str(value).strip()
    return mapping.get(text, text)


def _format_amount(value: object) -> str:
    if _missing(value):
        return "缺失"
    number = float(value)
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.1f}万"
    return f"{number:.0f}"


def _format_rank(value: object) -> str:
    if _missing(value):
        return "缺失"
    return str(int(float(value)))


def _format_number(value: object) -> str:
    if _missing(value):
        return "缺失"
    return f"{float(value):.2f}"


def official_index_valuation_comparison_rows(summary: pd.DataFrame) -> list[dict[str, object]]:
    """Project supported official valuation atoms from the published snapshot."""

    if summary.empty or "index_code" not in summary:
        return []
    by_code = {
        str(row["index_code"]): row
        for row in summary.to_dict("records")
        if (
            str(row.get("index_code", "")) in OFFICIAL_INDEX_VALUATION_TS_CODES
            and _text(row.get("valuation_support_status")) == "supported"
        )
    }
    return [
        {
            "指数代码": code,
            "指数名称": _text(by_code[code].get("index_name")) or "数据不足",
            "估值日期": _format_index_atomic_date(by_code[code].get("valuation_as_of_date")),
            "静态PE": _format_number(by_code[code].get("pe_static")),
            "PE-TTM": _format_number(by_code[code].get("pe_ttm")),
            "PE-TTM 5年分位": _format_index_atomic_percent(by_code[code].get("pe_ttm_5y_percentile")),
            "PB": _format_number(by_code[code].get("pb")),
            "PB 5年分位": _format_index_atomic_percent(by_code[code].get("pb_5y_percentile")),
            "新鲜度": _index_atomic_status_label(by_code[code].get("valuation_freshness_status")),
            "数据来源": _index_atomic_data_source_label(by_code[code].get("valuation_source")),
        }
        for code in OFFICIAL_INDEX_VALUATION_TS_CODES
        if code in by_code
    ]


def _format_index_detail_value(value: object) -> str:
    if _missing(value) or value == "":
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value).strip()


def _index_atomic_display_row(row: dict[str, object]) -> dict[str, object]:
    code = _text(row.get("index_code"))
    name = _text(row.get("index_name"))
    return {
        "index_code": code,
        "index": " ".join(item for item in (code, name) if item) or "数据不足",
        "category": _text(row.get("category")) or "数据不足",
        "latest_date": _format_index_atomic_date(row.get("latest_date")),
        "close_vs_ma_20": _format_index_atomic_relative_ma(row.get("close_vs_ma_20")),
        "close_vs_ma_60": _format_index_atomic_relative_ma(row.get("close_vs_ma_60")),
        "range_20": _format_index_atomic_range(row),
        "return_20": _format_index_atomic_percent(row.get("return_20")),
        "data_status": _index_atomic_status_label(row.get("snapshot_status")),
    }


def _index_atomic_detail_item(row: dict[str, object]) -> IndexAtomicDetailItem:
    metric_key = _text(row.get("metric_key"))
    return IndexAtomicDetailItem(
        metric_key=metric_key,
        label=_index_atomic_detail_label(metric_key, row.get("metric_label")),
        value=_format_index_atomic_detail_value(metric_key, row.get("value")),
        status=_index_atomic_status_label(row.get("status")),
        reason=_text(row.get("reason")) or "数据不足",
        as_of_date=_format_index_atomic_date(row.get("as_of_date")),
        sample_count=_format_index_atomic_count(row.get("sample_count")),
        data_source=_index_atomic_data_source_label(row.get("data_source")),
    )


def _index_atomic_detail_label(metric_key: str, value: object) -> str:
    label = _text(value) or metric_key or "数据不足"
    return label.replace("交易日", "日数" if metric_key.startswith("days_since_") else "日期")


def _format_index_atomic_relative_ma(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "数据不足"
    direction = "高于" if number >= 0 else "低于"
    return f"{direction} {abs(number):.1%}"


def _format_index_atomic_range(row: dict[str, object]) -> str:
    high = row.get("range_20_high")
    low = row.get("range_20_low")
    if not _missing(high) and _truthy(high):
        return "20日新高"
    if not _missing(low) and _truthy(low):
        return "20日新低"
    if (
        not _missing(high)
        and not _missing(low)
        and _text(row.get("range_20_status")) == "computed"
    ):
        return "区间内"
    return "数据不足"


def _format_index_atomic_detail_value(metric_key: str, value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    if metric_key in {"history_status", "history_completeness_status"}:
        return _index_atomic_status_label(value)
    if metric_key in {"data_source", "valuation_source"}:
        return _index_atomic_data_source_label(value)
    if metric_key in {"latest_date", "as_of_date"}:
        return _format_index_atomic_date(value)
    if _index_atomic_boolean_metric(metric_key):
        return "是" if _truthy(value) else "否"
    if metric_key.startswith(("close_vs_ma_", "range_", "return_", "drawdown_")):
        return _format_index_atomic_percent(value)
    if metric_key in {"amount_avg_5", "amount_avg_20"}:
        return _format_index_atomic_amount(value)
    return _format_index_atomic_number(value)


def _index_atomic_boolean_metric(metric_key: str) -> bool:
    if metric_key.startswith(("close_above_ma_", "ma_cross_up_", "ma_cross_down_")):
        return True
    return metric_key.startswith("range_") and metric_key.rsplit("_", 1)[-1] in {"high", "low"} and "_from_" not in metric_key


def _format_index_atomic_date(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return _text(value) or "数据不足"


def _format_index_atomic_percent(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "数据不足"


def _format_index_atomic_amount(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "数据不足"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.1f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.1f}万"
    return f"{number:.0f}"


def _format_index_atomic_number(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    if isinstance(value, bool):
        return "是" if value else "否"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value) or "数据不足"
    return str(int(number)) if number.is_integer() else f"{number:.2f}"


def _format_index_atomic_count(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return _text(value) or "数据不足"


def _index_atomic_status_label(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    text = _text(value)
    return (
        INDEX_ATOMIC_SNAPSHOT_STATUS_LABELS.get(text)
        or INDEX_ATOMIC_METRIC_STATUS_LABELS.get(text)
        or INDEX_ATOMIC_HISTORY_COMPLETENESS_LABELS.get(text)
        or INDEX_PROFILE_STATUS_LABELS.get(text)
        or text
    )


def _index_atomic_data_source_label(value: object) -> str:
    if _missing(value) or value == "":
        return "数据不足"
    text = _text(value)
    return INDEX_ATOMIC_DATA_SOURCE_LABELS.get(text, text)


def _format_percentile(value: object) -> str:
    if _missing(value) or value == "":
        return ""
    return f"{float(value):.1f}%"


def _format_bool(value: object) -> str:
    if _missing(value):
        return "缺失"
    return "是" if _truthy(value) else "否"


def _text(value: object) -> str:
    if _missing(value):
        return ""
    return str(value).strip()


def _truthy(value: object) -> bool:
    if _missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "是"}
    return bool(value)


def _missing(value: object) -> bool:
    return bool(pd.isna(value))
