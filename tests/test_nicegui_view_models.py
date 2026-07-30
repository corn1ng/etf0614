from datetime import datetime

import pandas as pd
import pytest

from etf_trading.nicegui_app.view_models import (
    ATOMIC_HEALTH_COLUMNS,
    ATOMIC_OPPORTUNITY_COLUMNS,
    AtomicIndicatorFilters,
    IndexAtomicFilters,
    IndexHealthFilters,
    IndexProfileView,
    PlatformSnapshot,
    atomic_data_update_health,
    atomic_data_health_summary,
    atomic_indicator_detail_groups,
    atomic_indicator_detail_options,
    atomic_indicator_rows,
    atomic_indicator_summary,
    build_index_atomic_rows,
    category_options,
    code_from_option,
    current_ui_audit_findings,
    default_etf_input,
    etf_choice_options,
    etf_overview_rows,
    filter_atomic_indicator_frame,
    filter_etf_rows,
    index_choice_options,
    index_atomic_detail_groups,
    index_atomic_overview,
    index_profile_view,
    index_health_detail_rows,
    index_health_filter_options,
    index_health_rows,
    index_health_summary,
    index_data_status_notice,
    maintenance_rows,
    market_overview,
    platform_data_status_summary,
    resolve_etf_code_from_query,
    status_metrics,
)


def _snapshot() -> PlatformSnapshot:
    return PlatformSnapshot(
        master=pd.DataFrame(
            {
                "ETF代码": ["510300", "512880"],
                "ETF名称": ["沪深300ETF", "证券ETF"],
                "分类": ["A股宽基", "A股行业"],
                "交易所": ["SH", "SH"],
                "成交额": [120000000.0, 80000000.0],
            }
        ),
        watchlist=pd.DataFrame({"etf_code": ["510300"], "allow_buy": [True], "enabled": [True]}),
        index_summary=pd.DataFrame(
            {
                "index_code": ["000300", "000905"],
                "index_name": ["沪深300", "中证500"],
                "category": ["A股宽基", "A股宽基"],
                "allows_new_position": [True, False],
                "history_rows": [300, 30],
                "latest_date": ["2026-07-03", "2026-07-03"],
            }
        ),
        universe=pd.DataFrame({"etf_code": ["510300"], "is_top_sample": [True]}),
        gaps=pd.DataFrame({"数据类型": ["指数历史"], "状态": ["历史不足"]}),
        coverage=pd.DataFrame({"数据类型": ["ETF历史"], "覆盖率": ["50.0%"]}),
        generated_at=datetime(2026, 7, 5, 10, 0, 0),
    )


def _atomic_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300", "512880"],
            "name": ["沪深300ETF", "证券ETF"],
            "category": ["A股宽基", "A股行业"],
            "exchange": ["SSE", "SSE"],
            "history_status": ["ready", "missing_history"],
            "feature_status": ["complete", "missing_features"],
            "is_rank_eligible": [True, False],
            "latest_trade_date": ["2026-07-03", ""],
            "history_rows": [520, 0],
            "return_20": [0.08, None],
            "return_60": [0.12, None],
            "return_20_rank_all": [1, None],
            "return_60_rank_all": [1, None],
            "return_20_rank_category": [1, None],
            "return_60_rank_category": [1, None],
            "close_above_ma20": [True, None],
            "ma20_above_ma60": [True, None],
            "close_above_ma60": [True, None],
            "ma60_slope_20": [0.015, None],
            "weekly_close_above_ma10": [True, None],
            "weekly_close_above_ma30": [False, None],
            "avg_amount_5": [2_000_000.0, None],
            "avg_amount_20": [1_500_000.0, None],
            "amount_ratio_5_20": [1.33, None],
            "distance_ma20_pct": [0.03, None],
            "distance_ma20_atr": [1.2, None],
            "is_60d_close_breakout": [True, None],
            "missing_feature_names": ["", "missing_history"],
        }
    )


def _index_health_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "000905"],
            "index_name": ["沪深300", "中证500"],
            "market": ["A股", "A股"],
            "category": ["A股宽基", "A股宽基"],
            "latest_date": ["2026-07-03", "2026-07-03"],
            "history_rows": [900, 320],
            "large_trend": ["UP", "RANGE"],
            "medium_trend": ["UP", "RANGE"],
            "small_trend": ["PULLBACK", "BROKEN"],
            "allows_new_position": [True, False],
            "trend_health_status": ["normal", "blocked"],
            "trend_health_reason": ["趋势门槛通过", "小趋势破位"],
            "valuation_overview_label": ["mid_percentile", "missing"],
            "valuation_health_status": ["complete", "missing_valuation"],
            "valuation_health_reason": ["核心估值可用", "没有本地估值历史"],
            "valuation_latest_date": ["2026-07-03", ""],
            "valuation_coverage_years": [3.1, 0.0],
            "valuation_primary_source": ["unit", ""],
        }
    )


def _index_health_details_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "000300", "000905"],
            "detail_kind": ["trend", "valuation", "valuation"],
            "metric_name": ["large_trend", "pe_ttm", "pe_ttm"],
            "metric_label": ["大趋势", "市盈率TTM", "市盈率TTM"],
            "current_value": ["UP", 12.5, pd.NA],
            "status": ["normal", "computed", "missing_valuation"],
            "reason": ["大趋势向上", "已计算历史分位", "没有本地估值历史"],
            "display_direction": ["higher_is_better", "higher_is_more_expensive", "higher_is_more_expensive"],
            "historical_percentile": [pd.NA, 42.0, pd.NA],
            "window_years": [pd.NA, 3.1, 0.0],
            "first_date": ["2022-01-03", "2023-01-03", ""],
            "latest_date": ["2026-07-03", "2026-07-03", ""],
            "sample_count": [900, 800, 0],
            "data_source": ["unit", "unit", ""],
        }
    )


def _atomic_details() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"index_code": "000300", "group_key": "price_ma", "metric_key": "close_vs_ma_20", "metric_label": "相对20日均线偏离率", "value": 0.034, "status": "computed", "reason": "已从本地指数历史计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "akshare_zh_em"},
            {"index_code": "000300", "group_key": "ma_cross", "metric_key": "ma_cross_up_20", "metric_label": "向上穿越20日均线", "value": True, "status": "computed", "reason": "已按相邻交易日计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "range_position", "metric_key": "range_20_high", "metric_label": "20日收盘新高", "value": False, "status": "computed", "reason": "已从本地指数历史计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "range_position", "metric_key": "range_20_from_high", "metric_label": "距20日收盘最高偏离率", "value": -0.05, "status": "computed", "reason": "已从本地指数历史计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "return_drawdown", "metric_key": "return_20", "metric_label": "20日收益率", "value": 0.08, "status": "computed", "reason": "已从本地指数历史计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "volatility_volume", "metric_key": "amount_avg_20", "metric_label": "20日平均成交额", "value": pd.NA, "status": "missing_input", "reason": "缺少 amount 字段", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "volatility_volume", "metric_key": "amount_avg_ratio_5_20", "metric_label": "5日与20日平均成交额比值", "value": 1.33, "status": "computed", "reason": "已从本地指数历史计算", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "data_quality", "metric_key": "latest_date", "metric_label": "最新交易日", "value": "2026-07-11", "status": "computed", "reason": "已读取本地指数历史", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "unit"},
            {"index_code": "000300", "group_key": "data_quality", "metric_key": "data_source", "metric_label": "数据源", "value": "akshare_hk_em", "status": "computed", "reason": "已读取本地指数历史", "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "akshare_hk_em"},
        ]
    )


def _overview_detail(metric_key: str, value: object, *, status: str = "computed", reason: str = "已从本地指数历史计算") -> dict[str, object]:
    return {
        "index_code": "000300", "group_key": "price_ma", "metric_key": metric_key,
        "metric_label": metric_key, "value": value, "status": status, "reason": reason,
        "as_of_date": "2026-07-11", "sample_count": 260, "data_source": "akshare_zh_em",
    }


def _profile_detail(
    metric_key: str,
    value: object,
    *,
    group_key: str = "valuation",
    status: str = "computed",
    reason: str = "已计算",
) -> dict[str, object]:
    return {
        "index_code": "000300",
        "group_key": group_key,
        "metric_key": metric_key,
        "metric_label": metric_key,
        "value": value,
        "status": status,
        "reason": reason,
        "as_of_date": "2026-07-29",
        "sample_count": 1000,
        "data_source": "tushare_index_dailybasic" if group_key == "valuation" else "unit",
        "window_start_date": "2021-07-29" if "5y" in metric_key else "",
        "window_end_date": "2026-07-29" if "5y" in metric_key else "",
    }


def _profile_summary() -> dict[str, object]:
    return {
        "index_code": "000300", "index_name": "沪深300", "latest_date": "2026-07-29",
        "valuation_as_of_date": "2026-07-29", "valuation_support_status": "supported",
        "valuation_freshness_status": "fresh", "pe_ttm": 11.6, "pe_ttm_5y_percentile": 0.18,
        "pb": 1.24, "pb_5y_percentile": 0.22, "close_above_ma_20": False,
        "close_vs_ma_20": -0.037, "drawdown_250": -0.079,
    }


def _profile_details() -> pd.DataFrame:
    return pd.DataFrame([
        _profile_detail("pe_ttm", 11.6),
        _profile_detail("pe_ttm_percentile_5y", 0.18),
        _profile_detail("pe_ttm_band_5y", "历史低位"),
        _profile_detail("pb", 1.24),
        _profile_detail("pb_percentile_5y", 0.22),
        _profile_detail("pb_band_5y", "偏低"),
        _profile_detail("close", 4569.52, group_key="price_ma"),
        _profile_detail("ma_20", 4743.52, group_key="price_ma"),
        _profile_detail("close_above_ma_20", False, group_key="price_ma"),
        _profile_detail("drawdown_250", -0.079, group_key="return_drawdown"),
        _profile_detail("rsi_14", 41.2, group_key="momentum_return"),
        _profile_detail("annualized_volatility_20", 0.146, group_key="drawdown_risk"),
        _profile_detail("amount_avg_20", 100_000_000, group_key="trading_activity"),
    ])


def test_index_profile_view_builds_approved_summary_and_five_domains():
    view = index_profile_view(_profile_summary(), _profile_details(), "000300")

    assert isinstance(view, IndexProfileView)
    assert view.identity == "000300 · 沪深300"
    assert [card.label for card in view.summary_cards] == ["PE-TTM", "PB", "趋势位置", "250日当前回撤"]
    assert view.valuation.pe_ttm.percentile_5y == "18.0%"
    assert view.valuation.pe_ttm.band_5y == "历史低位"
    assert [section.title for section in view.trend_risk_sections] == [
        "趋势结构", "动量与收益", "回撤与风险", "成交活跃度",
    ]


def test_index_profile_view_hides_valuation_tracks_when_unsupported():
    summary = _profile_summary() | {
        "index_code": "801010", "index_name": "农林牧渔", "valuation_support_status": "unsupported",
        "valuation_as_of_date": "",
    }
    details = _profile_details().copy()
    details["index_code"] = "801010"
    details = pd.concat([details, pd.DataFrame([{
        **_profile_detail("valuation_support_status", "unsupported", status="unsupported", reason="Tushare 官方估值暂不支持该指数"),
        "index_code": "801010",
    }])], ignore_index=True)

    view = index_profile_view(summary, details, "801010")

    assert view.valuation.visible is False
    assert view.valuation.reason == "Tushare 官方估值暂不支持该指数"
    assert view.trend.visible is True


def test_index_profile_view_exposes_stale_dates_without_relabeling_old_value():
    summary = _profile_summary() | {
        "valuation_as_of_date": "2026-07-20", "valuation_freshness_status": "stale",
    }

    view = index_profile_view(summary, _profile_details(), "000300")

    assert view.valuation.status == "估值数据已过期"
    assert view.price_as_of_date == "2026-07-29"
    assert view.valuation_as_of_date == "2026-07-20"


def test_index_profile_quality_formats_official_valuation_source_label():
    details = pd.concat([_profile_details(), pd.DataFrame([
        _profile_detail("valuation_source", "tushare_index_dailybasic"),
    ])], ignore_index=True)

    view = index_profile_view(_profile_summary(), details, "000300")

    source = next(item for item in view.quality if item.label == "valuation_source")
    assert source.value == "Tushare（官方指数每日指标）"


def test_index_profile_marks_not_synced_valuation_without_empty_tracks():
    summary = _profile_summary() | {
        "valuation_support_status": "not_synced", "valuation_freshness_status": "",
        "valuation_as_of_date": "",
    }
    details = pd.concat([_profile_details(), pd.DataFrame([{
        **_profile_detail("valuation_support_status", "not_synced", status="not_synced", reason="尚未同步官方估值"),
    }])], ignore_index=True)

    view = index_profile_view(summary, details, "000300")

    assert view.valuation.visible is False
    assert view.valuation.status == "官方估值尚未同步"
    assert view.valuation.reason == "尚未同步官方估值"
    assert view.valuation.pe_ttm is None


@pytest.mark.parametrize(
    ("status", "status_label"),
    [("insufficient_history", "历史不足"), ("calculation_failed", "计算失败")],
)
def test_index_profile_keeps_empty_atomic_values_and_statuses(status, status_label):
    details = _profile_details()
    details.loc[details["metric_key"] == "drawdown_250", ["value", "status", "reason"]] = [pd.NA, status, "原子指标不可用"]

    view = index_profile_view(_profile_summary(), details, "000300")

    risk = next(section for section in view.trend_risk_sections if section.title == "回撤与风险")
    drawdown = next(item for item in risk.items if item.metric_key == "drawdown_250")
    assert (drawdown.value, drawdown.status, drawdown.reason) == ("数据不足", status_label, "原子指标不可用")


def test_index_profile_all_groups_cover_every_nonquality_price_atom_in_stable_group_order():
    details = pd.DataFrame([
        _profile_detail("pe_ttm", 11.6),
        _profile_detail("history_rows", 1000, group_key="data_quality"),
        _profile_detail("close", 4569.52, group_key="price_ma"),
        _profile_detail("ma_20", 4743.52, group_key="price_ma"),
        _profile_detail("ma_cross_up_20", True, group_key="ma_cross"),
        _profile_detail("range_20_from_high", -0.04, group_key="range_position"),
        _profile_detail("return_20", 0.03, group_key="return_drawdown"),
        _profile_detail("annualized_volatility_20", 0.146, group_key="volatility_volume"),
        _profile_detail("rsi_14", 41.2, group_key="momentum_return"),
        _profile_detail("max_drawdown_250", -0.20, group_key="drawdown_risk"),
        _profile_detail("amount_avg_20", 100_000_000, group_key="trading_activity"),
    ])

    view = index_profile_view(_profile_summary(), details, "000300")

    assert [group.title for group in view.all_groups] == [
        "价格与均线", "均线穿越", "区间位置与突破", "收益与回撤", "波动与量能",
        "动量与收益", "回撤与风险", "成交活跃度",
    ]
    assert [item.metric_key for group in view.all_groups for item in group.items] == [
        "close", "ma_20", "ma_cross_up_20", "range_20_from_high", "return_20",
        "annualized_volatility_20", "rsi_14", "max_drawdown_250", "amount_avg_20",
    ]
    assert all(item.metric_key != "history_rows" for group in view.all_groups for item in group.items)


def test_index_atomic_overview_reads_stored_atoms_without_conclusions():
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", 100.0),
        _overview_detail("ma_20", 102.0), _overview_detail("ma_60", 98.0),
        _overview_detail("ma_120", 96.0), _overview_detail("ma_250", 90.0),
        _overview_detail("close_above_ma_20", False), _overview_detail("close_above_ma_60", True),
        _overview_detail("close_above_ma_120", True), _overview_detail("close_above_ma_250", True),
        _overview_detail("range_20_high", False), _overview_detail("range_20_low", False),
        _overview_detail("range_20_from_high", -0.05), _overview_detail("range_20_from_low", 0.05),
        _overview_detail("days_since_ma_cross_down_60", 1), _overview_detail("days_since_ma_cross_up_20", 9),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.trend.close.value == "100.00"
    assert [(level.label, level.value) for level in overview.trend.levels] == [
        ("MA20", "102.00"), ("MA60", "98.00"), ("MA120", "96.00"), ("MA250", "90.00"),
    ]
    assert overview.range_position.headline == "20日区间内"
    assert overview.range_position.marker == pytest.approx(0.475)
    assert [(event.label, event.days) for event in overview.events] == [
        ("下穿60日均线", "1 日前"), ("上穿20日均线", "9 日前"),
    ]
    assert [item.label for item in overview.quality] == ["快照状态", "历史覆盖", "有效交易日", "数据来源"]
    assert isinstance(overview.evidence_groups[0].items, tuple)
    assert "评分" not in repr(overview) and "买卖" not in repr(overview)


def test_index_atomic_overview_normalizes_finite_stored_trend_heights_for_ladder_display():
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", 100.0),
        _overview_detail("ma_20", 110.0), _overview_detail("ma_60", 90.0),
        _overview_detail("ma_120", 80.0), _overview_detail("ma_250", 120.0),
        _overview_detail("close_above_ma_20", False), _overview_detail("close_above_ma_60", True),
        _overview_detail("close_above_ma_120", True), _overview_detail("close_above_ma_250", False),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.trend.visible is True
    assert [(marker.label, marker.position) for marker in overview.trend.markers] == [
        ("收盘", pytest.approx(0.5)), ("MA20", pytest.approx(0.75)),
        ("MA60", pytest.approx(0.25)), ("MA120", pytest.approx(0.0)),
        ("MA250", pytest.approx(1.0)),
    ]


def test_index_atomic_overview_hides_unreliable_visuals_and_reports_empty_events():
    summary = {
        "index_code": "000300", "snapshot_status": "stale",
        "history_completeness_status": "INCOMPLETE", "history_rows": 18,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_high", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_low", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_from_high", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
        _overview_detail("range_20_from_low", pd.NA, status="insufficient_history", reason="历史不足 20 行"),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.trend.visible is False
    assert overview.range_position.marker is None
    assert overview.range_position.reason == "历史不足 20 行"
    assert overview.events == ()
    assert overview.events_empty_text == "暂无已记录事件"
    assert overview.quality[0].value == "待重建"


def test_index_atomic_overview_ignores_nonfinite_and_negative_event_ages():
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("days_since_ma_cross_up_20", float("inf")),
        _overview_detail("days_since_ma_cross_down_60", -2),
        _overview_detail("days_since_ma_cross_up_120", 4),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert [(event.label, event.days) for event in overview.events] == [("上穿120日均线", "4 日前")]


def test_index_atomic_overview_range_marker_uses_unrounded_stored_offsets():
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    details = pd.DataFrame([
        _overview_detail("close", 100.0),
        _overview_detail("range_20_high", False), _overview_detail("range_20_low", False),
        _overview_detail("range_20_from_high", -0.0004), _overview_detail("range_20_from_low", 0.0004),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.range_position.marker == pytest.approx(0.4998)


@pytest.mark.parametrize("metric_key", ["close", "range_20_from_high", "range_20_from_low"])
def test_index_atomic_overview_hides_computed_nonfinite_range_inputs(metric_key):
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    values = {
        "close": 100.0,
        "range_20_from_high": -0.05,
        "range_20_from_low": 0.05,
    }
    values[metric_key] = float("nan")
    details = pd.DataFrame([
        _overview_detail("close", values["close"]),
        _overview_detail("range_20_high", False), _overview_detail("range_20_low", False),
        _overview_detail("range_20_from_high", values["range_20_from_high"]),
        _overview_detail("range_20_from_low", values["range_20_from_low"]),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    assert overview.range_position.marker is None
    assert overview.range_position.headline == "数据不足"
    assert overview.range_position.reason == "数据不足"


@pytest.mark.parametrize("metric_key", ["close", "ma_60"])
def test_index_atomic_overview_hides_trend_for_computed_nonfinite_close_or_ma(metric_key):
    summary = {
        "index_code": "000300", "snapshot_status": "computed",
        "history_completeness_status": "COMPLETE", "history_rows": 260,
        "latest_date": "2026-07-11", "data_source": "akshare_zh_em",
    }
    values = {"close": 100.0, "ma_20": 102.0, "ma_60": 98.0, "ma_120": 96.0, "ma_250": 90.0}
    values[metric_key] = float("nan")
    details = pd.DataFrame([
        _overview_detail("close", values["close"]),
        _overview_detail("ma_20", values["ma_20"]), _overview_detail("ma_60", values["ma_60"]),
        _overview_detail("ma_120", values["ma_120"]), _overview_detail("ma_250", values["ma_250"]),
    ])

    overview = index_atomic_overview(summary, details, "000300")

    assert overview is not None
    broken_metric = overview.trend.close if metric_key == "close" else overview.trend.levels[1]
    assert broken_metric.status == "数据不足"
    assert broken_metric.reason == "快照中该原子指标不是有限数值"
    assert overview.trend.visible is False
    assert overview.trend.markers == ()


def test_status_metrics_are_dense_and_human_readable():
    metrics = status_metrics(_snapshot())

    assert [metric.label for metric in metrics] == ["ETF总数", "计算池", "可参与指数", "数据缺口"]
    assert [metric.value for metric in metrics] == ["2", "1", "1", "1"]
    assert metrics[-1].tone == "warning"


def test_current_ui_audit_findings_cover_high_frequency_pages():
    findings = current_ui_audit_findings()
    pages = {finding.page_slug for finding in findings}

    assert {"action", "market", "etf-data", "maintenance"}.issubset(pages)
    assert all(finding.problem and finding.fix for finding in findings)


def test_market_overview_groups_index_state():
    overview = market_overview(_snapshot())

    assert overview["total_indexes"] == 2
    assert overview["allowed_indexes"] == 1
    assert overview["categories"] == [{"category": "A股宽基", "total": 2, "allowed": 1}]


def test_market_overview_counts_core_research_and_incomplete_history_separately():
    snapshot = _snapshot()
    snapshot = PlatformSnapshot(
        master=snapshot.master,
        watchlist=snapshot.watchlist,
        index_summary=pd.DataFrame(
            {
                "index_code": ["000300", "801010", "801020", "801030"],
                "category": ["A股宽基", "A股行业", "A股行业", "A股行业"],
                "pool": ["core", "research", "research", "research"],
                "history_completeness_status": ["COMPLETE", "INCOMPLETE", "BASELINE_UNVERIFIED", "BASELINE_REFERENCED"],
                "allows_new_position": [True, False, False, False],
            }
        ),
        universe=snapshot.universe,
        gaps=snapshot.gaps,
        coverage=snapshot.coverage,
        generated_at=snapshot.generated_at,
    )

    overview = market_overview(snapshot)

    assert overview["core_indexes"] == 1
    assert overview["research_indexes"] == 3
    assert overview["incomplete_history_indexes"] == 3


def test_index_health_view_models_filter_summary_and_details():
    summary = _index_health_summary_frame()
    rows = index_health_rows(
        summary,
        IndexHealthFilters(query="300", category="A股宽基", trend_status="normal", valuation_status="complete"),
    )

    assert len(rows) == 1
    assert rows[0]["index_code"] == "000300"
    assert rows[0]["valuation_overview_label"] == "mid_percentile"
    assert "score" not in rows[0]
    assert index_health_filter_options(summary, "category", "全部分类") == ["全部分类", "A股宽基"]
    metrics = index_health_summary(summary)
    assert [metric.label for metric in metrics] == ["指数池", "趋势通过", "估值完整", "估值缺失"]
    assert [metric.value for metric in metrics] == ["2", "1", "1", "1"]

    details = index_health_detail_rows(_index_health_details_frame(), "000300", "valuation")
    assert details == [
        {
            "metric_label": "市盈率TTM",
            "current_value": "12.50",
            "status": "computed",
            "historical_percentile": "42.0%",
            "reason": "已计算历史分位",
            "sample_count": 800,
            "latest_date": "2026-07-03",
            "data_source": "unit",
        }
    ]


def test_index_atomic_rows_keep_catalog_order_within_each_pool_and_search_only_filters():
    summary = pd.DataFrame(
        [
            {"index_code": "399001", "index_name": "深证成指", "category": "仅分类匹配", "pool": "core", "catalog_order": 2},
            {"index_code": "000300", "index_name": "沪深300", "category": "A股宽基", "pool": "core", "catalog_order": 1},
            {"index_code": "000905", "index_name": "中证500", "category": "A股宽基", "pool": "core", "catalog_order": 1},
            {"index_code": "801010", "index_name": "农林牧渔", "category": "申万一级", "pool": "research", "catalog_order": 3},
            {"index_code": "930000", "index_name": "候补指数", "category": "候补", "pool": "reserve", "catalog_order": 0},
        ]
    )

    core = build_index_atomic_rows(summary, IndexAtomicFilters(pool="core"))
    searched = build_index_atomic_rows(summary, IndexAtomicFilters(pool="core", query="深证"))
    category_searched = build_index_atomic_rows(summary, IndexAtomicFilters(pool="core", query="仅分类匹配"))
    reserve = build_index_atomic_rows(summary, IndexAtomicFilters(pool="reserve"))

    assert [row["index_code"] for row in core] == ["000300", "000905", "399001"]
    assert [row["index_code"] for row in searched] == ["399001"]
    assert category_searched == []
    assert reserve == []


def test_index_atomic_rows_format_fixed_atomic_summary_columns_without_conclusions():
    summary = pd.DataFrame(
        [
            {
                "index_code": "000300",
                "index_name": "沪深300",
                "category": "A股宽基",
                "pool": "core",
                "catalog_order": 0,
                "latest_date": "2026-07-11",
                "close_vs_ma_20": 0.034,
                "close_vs_ma_60": -0.025,
                "range_20_high": False,
                "range_20_low": False,
                "range_20_status": "computed",
                "return_20": 0.018,
                "snapshot_status": "computed",
            }
        ]
    )

    row = build_index_atomic_rows(summary, IndexAtomicFilters())[0]

    assert row["index"] == "000300 沪深300"
    assert row["close_vs_ma_20"] == "高于 3.4%"
    assert row["close_vs_ma_60"] == "低于 2.5%"
    assert row["range_20"] == "区间内"
    assert row["return_20"] == "1.8%"
    assert row["data_status"] == "已计算"
    assert not {"估值", "趋势", "评分", "排名", "策略", "交易"}.intersection(row)


def test_index_atomic_rows_format_20_day_range_from_stored_high_low_facts():
    summary = pd.DataFrame(
        [
            {"index_code": "000300", "index_name": "沪深300", "pool": "core", "catalog_order": 0, "range_20_high": True, "range_20_low": True, "range_20_status": "computed"},
            {"index_code": "000905", "index_name": "中证500", "pool": "core", "catalog_order": 1, "range_20_high": False, "range_20_low": True, "range_20_status": "computed"},
            {"index_code": "399001", "index_name": "深证成指", "pool": "core", "catalog_order": 2, "range_20_high": False, "range_20_low": False, "range_20_status": "computed"},
            {"index_code": "801010", "index_name": "农林牧渔", "pool": "core", "catalog_order": 3, "range_20_high": pd.NA, "range_20_low": pd.NA, "range_20_status": "insufficient_history"},
        ]
    )

    rows = build_index_atomic_rows(summary, IndexAtomicFilters())

    assert [row["range_20"] for row in rows] == ["20日新高", "20日新低", "区间内", "数据不足"]


def test_index_atomic_detail_groups_are_fact_categories_without_strategy_conclusions():
    groups = index_atomic_detail_groups(_atomic_details(), "000300")

    assert [group.title for group in groups] == ["价格与均线", "均线穿越", "区间位置与突破", "收益与回撤", "波动与量能", "数据质量"]
    assert all("趋势" not in item.label and "交易" not in item.label for group in groups for item in group.items)

    items = {item.metric_key: item for group in groups for item in group.items}
    assert items["close_vs_ma_20"].value == "3.4%"
    assert items["ma_cross_up_20"].value == "是"
    assert items["range_20_from_high"].value == "-5.0%"
    assert items["amount_avg_20"].value == "数据不足"
    assert items["amount_avg_20"].status == "缺少输入字段"
    assert items["amount_avg_ratio_5_20"].value == "1.33"
    assert items["latest_date"].value == "2026-07-11"
    assert items["close_vs_ma_20"].data_source == "AkShare（东方财富指数行情）"
    assert items["data_source"].value == "AkShare（东方财富港股指数行情）"


def test_table_rows_convert_dataframes_to_records():
    snapshot = _snapshot()

    assert etf_overview_rows(snapshot)[0]["ETF代码"] == "510300"
    assert maintenance_rows(snapshot) == [{"数据类型": "指数历史", "状态": "历史不足"}]


def test_market_audit_names_density_and_chart_fixes():
    market_findings = [item for item in current_ui_audit_findings() if item.page_slug == "market"]

    assert any("K线" in item.problem or "图表" in item.problem for item in market_findings)
    assert any("工具栏" in item.fix or "图表" in item.fix for item in market_findings)


def test_etf_and_maintenance_audit_notes_are_explicit():
    findings = current_ui_audit_findings()
    by_page = {}
    for finding in findings:
        by_page.setdefault(finding.page_slug, []).append(finding)

    assert any("ETF" in item.problem for item in by_page["etf-data"])
    assert any("健康" in item.problem or "补齐" in item.fix for item in by_page["maintenance"])


def test_choice_options_keep_codes_readable_for_chart_selectors():
    snapshot = _snapshot()

    assert index_choice_options(snapshot.index_summary) == [
        "000300 沪深300 · A股宽基 · 可参与",
        "000905 中证500 · A股宽基 · 观察",
    ]
    assert etf_choice_options(etf_overview_rows(snapshot)) == [
        "510300 沪深300ETF · A股宽基",
        "512880 证券ETF · A股行业",
    ]
    assert code_from_option("510300 沪深300ETF · A股宽基") == "510300"
    assert code_from_option(None) == ""
    assert default_etf_input(etf_overview_rows(snapshot)) == "510300 沪深300ETF"
    assert resolve_etf_code_from_query("证券", etf_overview_rows(snapshot)) == "512880"
    with pytest.raises(ValueError, match="请输入完整代码"):
        resolve_etf_code_from_query("ETF", etf_overview_rows(snapshot))


def test_index_choice_options_default_to_core_pool_and_can_include_research():
    frame = pd.DataFrame(
        [
            {"index_code": "000300", "index_name": "沪深300", "pool": "core"},
            {"index_code": "801010", "index_name": "农林牧渔", "pool": "research"},
        ]
    )

    assert index_choice_options(frame) == ["000300 沪深300 · 观察"]
    assert index_choice_options(frame, include_research=True) == [
        "000300 沪深300 · 观察",
        "801010 农林牧渔 · 观察",
    ]


def test_etf_search_filters_by_query_category_and_limit():
    rows = etf_overview_rows(_snapshot())

    assert category_options(rows) == ["全部分类", "A股宽基", "A股行业"]
    assert [row["ETF代码"] for row in filter_etf_rows(rows, query="300")] == ["510300"]
    assert [row["ETF代码"] for row in filter_etf_rows(rows, query="证券")] == ["512880"]
    assert [row["ETF代码"] for row in filter_etf_rows(rows, category="A股行业")] == ["512880"]
    assert len(filter_etf_rows(rows, limit=1)) == 1


def test_atomic_indicator_summary_counts_data_readiness():
    metrics = atomic_indicator_summary(_atomic_frame())

    assert [metric.label for metric in metrics][:4] == ["ETF主池", "数据可用", "可参与机会排名", "行情滞后"]
    assert [metric.value for metric in metrics][:4] == ["2", "1", "1", "0"]


def test_atomic_indicator_rows_are_filtered_and_do_not_expose_advice():
    rows = atomic_indicator_rows(
        _atomic_frame(),
        AtomicIndicatorFilters(query="300", only_breakout=True, only_weekly_ma10=True),
    )

    assert len(rows) == 1
    assert rows[0]["ETF代码"] == "510300"
    forbidden = {"综合分", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint(rows[0].keys())


def test_atomic_indicator_rows_support_opportunity_and_health_views():
    opportunity = atomic_indicator_rows(_atomic_frame(), view_mode="机会特征")
    health = atomic_indicator_rows(_atomic_frame(), view_mode="体检特征")

    assert tuple(opportunity[0].keys()) == ATOMIC_OPPORTUNITY_COLUMNS
    assert tuple(health[0].keys()) == ATOMIC_HEALTH_COLUMNS
    assert opportunity[0]["ETF代码"] == "510300"
    assert opportunity[0]["20日收益"] == "8.0%"
    assert opportunity[0]["60日突破"] == "是"
    assert opportunity[0]["周线>10周"] == "是"
    assert health[0]["历史行数"] == 520
    assert health[0]["收盘>20日线"] == "是"
    assert health[0]["周线>30周"] == "否"
    assert "缺失字段" in health[1]


def test_atomic_indicator_view_switch_keeps_filter_results_stable():
    filters = AtomicIndicatorFilters(query="300", only_breakout=True, only_weekly_ma10=True)

    filtered = filter_atomic_indicator_frame(_atomic_frame(), filters)
    opportunity = atomic_indicator_rows(_atomic_frame(), filters, view_mode="机会特征")
    health = atomic_indicator_rows(_atomic_frame(), filters, view_mode="体检特征")

    assert filtered["etf_code"].tolist() == ["510300"]
    assert [row["ETF代码"] for row in opportunity] == ["510300"]
    assert [row["ETF代码"] for row in health] == ["510300"]


def test_atomic_indicator_detail_options_follow_current_filters():
    options = atomic_indicator_detail_options(
        _atomic_frame(),
        AtomicIndicatorFilters(category="A股宽基"),
    )

    assert options == ["510300 沪深300ETF · A股宽基"]
    assert code_from_option(options[0]) == "510300"


def test_atomic_indicator_detail_groups_show_all_atomic_sections_without_advice():
    groups = atomic_indicator_detail_groups(_atomic_frame(), "510300")

    assert [group.title for group in groups] == ["身份信息", "数据体检", "相对强度", "趋势结构", "量能位置", "偏离程度"]
    flattened = {
        row["指标"]: row["数值"]
        for group in groups
        for row in group.rows
    }
    assert flattened["ETF代码"] == "510300"
    assert flattened["历史状态"] == "数据可用"
    assert flattened["20日收益"] == "8.0%"
    assert flattened["60日线20日斜率"] == "0.01"
    assert flattened["5/20成交额"] == "1.33"
    assert flattened["距20日线ATR"] == "1.20"
    forbidden = {"综合分", "温度分", "买入", "卖出", "目标仓位"}
    assert forbidden.isdisjoint(flattened)


def test_atomic_indicator_detail_groups_return_empty_for_missing_code():
    assert atomic_indicator_detail_groups(_atomic_frame(), "999999") == []


def test_atomic_indicator_rows_display_stale_history_as_price_lag():
    frame = _atomic_frame()
    frame.loc[0, "history_status"] = "stale"

    health_rows = atomic_indicator_rows(frame, view_mode="体检特征")
    groups = atomic_indicator_detail_groups(frame, "510300")
    flattened = {
        row["指标"]: row["数值"]
        for group in groups
        for row in group.rows
    }

    assert health_rows[0]["历史状态"] == "行情滞后"
    assert flattened["历史状态"] == "行情滞后"
    assert "正在刷新" not in " ".join(str(value) for value in health_rows[0].values())


def test_atomic_data_update_health_counts_repair_states():
    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "159915", "588000", "560000"],
            "history_status": ["complete", "stale", "short_history", "missing_history", "read_failed"],
            "feature_status": ["complete", "complete", "missing_features", "missing_features", "missing_features"],
        }
    )

    items = atomic_data_update_health(frame)
    by_key = {item.key: item for item in items}

    assert [item.label for item in items] == ["数据可用", "行情滞后", "历史不足", "历史缺失", "读取失败", "特征缺失"]
    assert by_key["ready"].count == 1
    assert by_key["stale"].count == 1
    assert by_key["short_history"].count == 1
    assert by_key["missing_history"].count == 1
    assert by_key["read_failed"].count == 1
    assert by_key["missing_features"].count == 3
    assert by_key["stale"].filter_type == "history_status"
    assert by_key["stale"].filter_value == "stale"
    assert by_key["missing_features"].filter_type == "feature_status"
    assert by_key["missing_features"].filter_value == "missing_features"


def test_atomic_health_summary_counts_unique_assets_not_overlapping_reasons():
    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "159915", "588000", "560000"],
            "history_status": ["ready", "stale", "short_history", "missing_history", "read_failed"],
            "feature_status": ["complete", "complete", "missing_features", "missing_features", "missing_features"],
        }
    )

    summary = atomic_data_health_summary(frame)

    assert summary.total == 5
    assert summary.issue_count == 4
    assert summary.primary_status_counts == {
        "数据可用": 1,
        "行情滞后": 1,
        "历史不足": 1,
        "历史缺失": 1,
        "读取失败": 1,
    }
    assert summary.feature_missing_count == 3


def test_opportunity_rows_exclude_non_rank_eligible_but_health_rows_keep_them():
    frame = _atomic_frame()

    assert [row["ETF代码"] for row in atomic_indicator_rows(frame, view_mode="机会特征")] == ["510300"]
    assert [row["ETF代码"] for row in atomic_indicator_rows(frame, view_mode="体检特征")] == ["510300", "512880"]


def test_platform_status_summary_separates_snapshot_time_and_source_date():
    snapshot = _snapshot()
    snapshot = PlatformSnapshot(
        master=pd.DataFrame(
            {
                "ETF代码": ["510300", "512880"],
                "本地历史": ["数据可用", "行情滞后"],
                "最新日期": ["2026-07-03", "2026-07-01"],
            }
        ),
        watchlist=snapshot.watchlist,
        index_summary=pd.DataFrame({"data_status": ["数据可用", "行情滞后"], "latest_date": ["2026-07-03", "2026-07-01"]}),
        universe=snapshot.universe,
        gaps=snapshot.gaps,
        coverage=snapshot.coverage,
        generated_at=snapshot.generated_at,
    )

    summary = platform_data_status_summary(snapshot)

    assert summary.etf_label == "ETF：1/2 数据可用"
    assert summary.index_label == "指数：1/2 数据可用"
    assert summary.latest_trade_date == "2026-07-03"
    assert summary.generated_label == "页面计算 2026-07-05 10:00"


def test_index_data_status_notice_uses_index_effective_date_and_excludes_unready_data():
    snapshot = PlatformSnapshot(
        master=pd.DataFrame(),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(
            {
                "data_status": ["数据可用", "行情滞后"],
                "latest_date": ["2026-07-03", "2026-07-01"],
            }
        ),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 5, 15, 30),
    )

    assert index_data_status_notice(snapshot) == (
        "指数数据状态：指数：1/2 数据可用；最近有效交易日 2026-07-03。"
        "非“数据可用”的指数不应作为趋势或买卖依据。"
    )


def test_atomic_data_update_health_returns_zero_counts_for_empty_frame():
    items = atomic_data_update_health(pd.DataFrame())

    assert [item.count for item in items] == [0, 0, 0, 0, 0, 0]
