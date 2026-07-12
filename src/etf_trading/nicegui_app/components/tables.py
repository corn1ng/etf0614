"""Dense table helpers."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from nicegui import ui


COLUMN_LABELS = {
    "index_code": "指数代码",
    "index_name": "指数名称",
    "market": "市场",
    "category": "分类",
    "pool": "指数池",
    "index_base_date": "指数基日",
    "history_completeness_status": "历史完整性",
    "history_completeness_message": "历史完整性说明",
    "completeness_status": "历史完整性",
    "completeness_message": "历史完整性说明",
    "baseline_source": "基日来源",
    "baseline_evidence_kind": "起点证据",
    "baseline_evidence_name": "证据来源",
    "baseline_evidence_url": "证据链接",
    "baseline_checked_at": "检索日期",
    "evidence_status": "核验结果",
    "detail": "证据说明",
    "source_kind": "数据源类型",
    "provider_symbol": "数据源代码",
    "etf_mapping_count": "ETF映射数",
    "large_trend": "大趋势",
    "medium_trend": "中趋势",
    "small_trend": "小趋势",
    "allows_new_position": "允许新开仓",
    "latest_date": "最新日期",
    "history_rows": "历史行数",
    "trend_health_status": "趋势体检",
    "trend_health_reason": "趋势原因",
    "valuation_overview_label": "估值位置",
    "valuation_health_status": "估值体检",
    "valuation_health_reason": "估值原因",
    "valuation_latest_date": "估值日期",
    "valuation_coverage_years": "估值年限",
    "valuation_primary_source": "估值来源",
    "detail_kind": "明细类型",
    "metric_name": "指标名",
    "metric_label": "指标",
    "current_value": "当前值",
    "historical_percentile": "历史分位",
    "window_years": "窗口年限",
    "first_date": "首日",
    "trade_date": "交易日",
    "open": "开盘",
    "high": "最高",
    "low": "最低",
    "close": "收盘",
    "volume": "成交量",
    "pct_change": "涨跌幅",
    "change": "涨跌额",
    "turnover_rate": "换手率",
    "ma20": "20日均线",
    "ma51": "51日均线",
    "ma60": "60日均线",
    "ma120": "120日均线",
    "ma250": "250日均线",
    "ma850": "850日均线",
    "data_source": "数据源",
    "dataset": "数据集",
    "asset_code": "标的代码",
    "last_success_trade_date": "最近成功交易日",
    "log_id": "日志编号",
    "severity": "级别",
    "total": "总数",
    "allowed": "可参与数量",
    "etf_code": "ETF代码",
    "etf_name": "ETF名称",
    "name": "名称",
    "exchange": "交易所",
    "amount": "成交额",
    "latest_price": "最新价格",
    "tracking_index": "跟踪指数",
    "fund_company": "基金公司",
    "listing_date": "上市日期",
    "is_active": "启用",
    "allow_buy": "允许买入",
    "enabled": "纳入计算",
    "note": "备注",
    "status": "状态",
    "fetched_rows": "新增行数",
    "total_rows": "本地总行数",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "error_message": "状态说明",
    "data_status_message": "行情状态说明",
    "data_type": "数据类型",
    "scope": "范围",
    "code": "代码",
    "updated_at": "更新时间",
    "created_at": "创建时间",
    "last_success_at": "最近成功时间",
    "job_id": "任务编号",
    "job_type": "任务类型",
    "payload": "任务参数",
    "attempts": "尝试次数",
    "started_at": "开始时间",
    "finished_at": "完成时间",
    "message": "消息",
    "candidate_name": "候选策略",
    "sample_count": "样本数",
    "mean_total_return": "平均总收益",
    "median_annualized_return": "中位年化收益",
    "median_sharpe": "中位夏普",
    "median_calmar": "中位卡玛",
    "worst_max_drawdown": "最差最大回撤",
    "mean_trade_count": "平均交易次数",
    "score": "评分",
    "total_return": "总收益",
    "annualized_return": "年化收益",
    "max_drawdown": "最大回撤",
    "sharpe": "夏普",
    "calmar": "卡玛",
    "trade_count": "交易次数",
    "target_weight": "目标仓位",
    "reason": "原因",
    "trigger_rules": "触发规则",
    "risk_tags": "风险标签",
    "advice_id": "建议编号",
    "priority": "优先级",
    "mapping_source": "映射来源",
    "confidence": "置信度",
    "is_top_sample": "默认样本",
    "sample_rank": "样本排名",
    "return_20": "20日收益",
    "return_60": "60日收益",
    "return_20_rank_all": "20日全池排名",
    "return_60_rank_all": "60日全池排名",
    "return_20_rank_category": "20日同类排名",
    "return_60_rank_category": "60日同类排名",
    "history_status": "历史状态",
    "feature_status": "特征状态",
    "latest_trade_date": "最新交易日",
    "close_above_ma20": "收盘站上20日线",
    "ma20_above_ma60": "20日线高于60日线",
    "close_above_ma60": "收盘站上60日线",
    "weekly_close_above_ma10": "周收盘站上10周线",
    "weekly_close_above_ma30": "周收盘站上30周线",
    "avg_amount_5": "5日成交额",
    "avg_amount_20": "20日成交额",
    "amount_ratio_5_20": "5日/20日成交额",
    "distance_ma20_pct": "距20日线",
    "distance_ma20_atr": "距20日线ATR",
    "ma60_slope_20": "60日线20日斜率",
    "is_60d_close_breakout": "突破60日高点",
    "missing_feature_names": "缺失字段",
}

VALUE_LABELS = {
    "UP": "上升",
    "DOWN": "下降",
    "RANGE": "震荡",
    "BROKEN": "破位",
    "RIGHT_SIDE_START": "右侧开始",
    "PULLBACK": "回踩",
    "EXTENDED": "过热延伸",
    "RECOVERY": "修复",
    "REBOUND": "反弹",
    "TURNING_UP": "转强",
    "UNKNOWN": "未知",
    "complete": "完整",
    "missing_history": "历史缺失",
    "short_history": "历史不足",
    "read_failed": "读取失败",
    "missing_features": "特征缺失",
    "missing_field": "字段缺失",
    "invalid_trade_date": "交易日无效",
    "feature_calculation_failed": "特征计算失败",
    "feature_failed": "特征计算失败",
    "insufficient_history": "历史不足",
    "normal": "正常",
    "blocked": "未通过",
    "computed": "已计算",
    "partial": "部分缺失",
    "missing_valuation": "估值缺失",
    "low_percentile": "低分位",
    "mid_percentile": "中分位",
    "high_percentile": "高分位",
    "higher_is_more_expensive": "越高越贵",
    "higher_is_more_attractive": "越高越便宜",
    "higher_is_better": "越高越好",
    "trend": "趋势",
    "valuation": "估值",
    "UPDATED": "已补齐",
    "INITIALIZED": "已初始化",
    "REPAIRED": "已修复",
    "SKIPPED": "已是最新",
    "STALE": "行情仍滞后",
    "FAILED": "失败",
    "EMPTY": "无数据",
    "PENDING": "待处理",
    "RUNNING": "运行中",
    "SUCCESS": "成功",
    "READY": "就绪",
    "ready": "就绪",
    "building": "生成中",
    "failed": "失败",
    "experimental": "实验中",
    "adopted": "已采用",
    "disabled": "停用",
    "BUY": "买入",
    "SELL": "卖出",
    "HOLD": "持有",
    "WATCH": "观察",
    "FORBID": "禁止",
    "SKIP": "跳过",
    "manual_backtest": "手动回测",
    "history": "历史行情",
    "etf_daily_price": "ETF日行情",
    "index_daily_price": "指数日行情",
    "index_catalog_sync": "同步指数目录",
    "index_source_validation": "验证指数数据源",
    "index_history_full": "补齐全部指数历史",
    "index_history_repair": "仅补历史不完整",
    "index_history_incremental": "仅更新最新行情",
    "core": "核心交易池",
    "research": "研究池（仅研究）",
    "reserve": "候补池",
    "COMPLETE": "历史完整",
    "INCOMPLETE": "历史不完整",
    "BASELINE_REFERENCED": "第三方参考起点",
    "BASELINE_UNVERIFIED": "历史起点无法确认",
    "SOURCE_LIMITED": "数据源历史不完整",
    "MISSING_HISTORY": "历史缺失",
    "NOT_VALIDATED": "待校验",
    "OFFICIAL": "官方已核验",
    "THIRD_PARTY_PUBLICATION": "第三方参考起点",
    "UNRESOLVED": "起点无法确认",
    "official_methodology": "官方方法论",
    "official_factsheet": "官方资料",
    "official_api": "官方接口",
    "third_party_reference": "第三方参考",
    "third_party_publication": "第三方发布来源",
    "unverified": "尚未核验",
    "official_base_date": "官方基日",
    "third_party_base_date": "第三方参考基日",
    "publication_date": "第三方发布日期",
    "unresolved": "起点无法确认",
    "etf_master": "ETF主列表",
    "watchlist": "每日计算池",
    "warning": "警告",
    "WARNING": "警告",
    "error": "错误",
    "ERROR": "错误",
    "info": "信息",
    "INFO": "信息",
    "critical": "严重",
    "CRITICAL": "严重",
    "name_inferred": "名称推断",
    "direct": "直接匹配",
    "high": "高",
    "medium": "中",
    "low": "低",
    "SSE": "上交所",
    "SZSE": "深交所",
    "SH": "上交所",
    "SZ": "深交所",
}

FIELD_VALUE_LABELS = {
    "history_status": {
        "stale": "行情滞后",
    },
    "valuation_overview_label": {
        "missing": "估值缺失",
    },
    "status": {
        "stale": "待刷新",
    },
}

BOOLEAN_COLUMN_LABELS = {
    "allows_new_position",
    "allow_buy",
    "enabled",
    "is_active",
    "is_top_sample",
    "close_above_ma20",
    "ma20_above_ma60",
    "close_above_ma60",
    "weekly_close_above_ma10",
    "weekly_close_above_ma30",
    "is_60d_close_breakout",
}

COMPACT_COLUMN_WIDTHS = {
    "index_code": 88,
    "index_name": 116,
    "market": 72,
    "category": 96,
    "large_trend": 92,
    "medium_trend": 92,
    "small_trend": 100,
    "allows_new_position": 88,
    "latest_date": 104,
    "history_rows": 88,
    "etf_code": 88,
    "etf_name": 128,
    "name": 128,
    "exchange": 76,
    "amount": 104,
    "latest_price": 96,
    "status": 112,
    "fetched_rows": 96,
    "total_rows": 96,
    "end_date": 104,
    "sample_rank": 88,
    "ma60_slope_20": 120,
    "trend_health_status": 104,
    "valuation_overview_label": 104,
    "valuation_health_status": 104,
    "valuation_coverage_years": 88,
    "metric_label": 132,
    "current_value": 96,
    "historical_percentile": 96,
    "sample_count": 88,
}

PAGINATION_LABEL = "(first, end, total) => `${first}-${end} / ${total}`"


def render_table(
    rows: list[dict[str, object]],
    *,
    pagination: int | dict | None = None,
    row_key: str | None = None,
    compact: bool = False,
    ui_module=None,
):
    table_kwargs = {
        "columns": table_columns(rows, compact=compact),
        "rows": table_rows(rows),
        "pagination": pagination,
    }
    if row_key is not None:
        table_kwargs["row_key"] = row_key
    table_api = ui_module or ui
    table = table_api.table(
        **table_kwargs,
    )
    table_props = getattr(table, "props", None)
    if hasattr(table_props, "__setitem__"):
        table_props["rows-per-page-label"] = "每页行数"
        table_props[":pagination-label"] = PAGINATION_LABEL
        table_props["no-data-label"] = "暂无数据"
        table_props["no-results-label"] = "没有匹配结果"
        table_props["loading-label"] = "加载中..."
    return table


def table_columns(rows: list[dict[str, object]], *, compact: bool = False) -> list[dict[str, str]]:
    if not rows:
        return []
    columns: list[dict[str, str]] = []
    for key in rows[0].keys():
        column: dict[str, str] = {"name": key, "label": COLUMN_LABELS.get(key, key), "field": key, "align": "left"}
        if compact:
            width = COMPACT_COLUMN_WIDTHS.get(key)
            if width is not None:
                style = f"width: {width}px; min-width: {width}px; max-width: {width}px;"
                column["style"] = style
                column["headerStyle"] = style
            column["classes"] = "text-no-wrap"
            column["headerClasses"] = "text-no-wrap"
        columns.append(column)
    return columns


def table_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [{key: _display_value(key, value) for key, value in row.items()} for row in rows]


def _display_value(column: str, value: object) -> object:
    if _missing(value):
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if column in BOOLEAN_COLUMN_LABELS:
        return "是" if _truthy(value) else "否"
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    field_labels = FIELD_VALUE_LABELS.get(column, {})
    if text in field_labels:
        return field_labels[text]
    if text in VALUE_LABELS:
        return VALUE_LABELS[text]
    if column in {"large_trend", "medium_trend", "small_trend"} and text:
        return VALUE_LABELS.get(text, text.replace("_", " "))
    if column == "candidate_name" and text:
        return text.replace("_", " ")
    return value


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "是"}
    return bool(value)


def _missing(value: object) -> bool:
    return bool(pd.isna(value))
